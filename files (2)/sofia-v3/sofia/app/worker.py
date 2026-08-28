"""
Sofia — background execution of tool runs.

Why this module exists
----------------------
Passenger on shared cPanel cuts a request long before a twelve-section
business plan finishes generating. Running the model call inline meant the
highest-credit tools were the ones most likely to die at the proxy, leaving
the user with a browser error and a debited balance.

So the request thread does the cheap, ordered part — validate, extract,
charge, insert the job row — and hands the expensive part here. The client
polls until the job leaves 'running'.

Design notes
------------
Threads, not Celery. cPanel gives no reliable long-lived worker process, and
at Sofia's volume a small bounded pool is the right amount of machinery. If
that stops being true the seam is `submit()`, which is the only thing the
API layer knows about.

The pool is bounded and never holds a database connection across the model
call. `engines.run()` touches no database; the connection is borrowed only
to write the outcome. That keeps WORKER_THREADS from starving DB_POOL_SIZE.

Nothing here touches Flask's request or session context — by the time the
worker runs, the request that created it is gone. Everything the job needs
is passed in as plain data.
"""

from __future__ import annotations

import atexit
import logging
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from app import engines
from app.ai.kimi import AIError
from app.credits import complete_job, fail_job, _now
from app.db import query_all
from config import Config

log = logging.getLogger("sofia.worker")

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()

# Jobs currently in flight in this process, by public_id. Only used to give
# the poll endpoint a sharper answer than the database can — the database
# remains the source of truth.
_inflight: set[str] = set()


def _pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=Config.WORKER_THREADS,
                    thread_name_prefix="sofia-job",
                )
                atexit.register(_shutdown)
                log.info("Job worker started with %d threads", Config.WORKER_THREADS)
    return _executor


def _shutdown() -> None:
    if _executor is not None:
        # Let running jobs finish writing their result. A job killed between
        # the model call and complete_job() looks identical to a crash, and
        # the sweeper would refund a user who actually got their document.
        _executor.shutdown(wait=True, cancel_futures=True)


def submit(job: dict, tool: dict, inputs: dict) -> None:
    """Queue a job. Returns immediately; the row is already 'running'."""
    _inflight.add(job["public_id"])
    _pool().submit(_execute, job, tool, inputs)


def is_inflight(public_id: str) -> bool:
    return public_id in _inflight


def _execute(job: dict, tool: dict, inputs: dict) -> None:
    """
    Run one tool and record the outcome. Never raises — a worker thread that
    throws loses the job silently and strands the row at 'running' until the
    sweeper finds it.
    """
    slug = tool["slug"]
    try:
        try:
            result, usage = engines.run(tool, inputs)

        except engines.EngineError as exc:
            log.info("Job %s (%s) rejected: %s", job["public_id"], slug, exc)
            fail_job(job, exc.code)
            return

        except AIError as exc:
            log.warning("Job %s (%s) AI failure: %s", job["public_id"], slug, exc)
            fail_job(job, exc.code)
            return

        except Exception:
            error_id = secrets.token_hex(6)
            log.exception("Job %s (%s) failed unexpectedly [%s]",
                          job["public_id"], slug, error_id)
            fail_job(job, "internal", error_id)
            return

        complete_job(job, result, usage)
        log.info("Job %s (%s) succeeded", job["public_id"], slug)

    except Exception:
        # Reaching here means fail_job or complete_job itself failed — most
        # likely the database went away. Log loudly; the sweeper is the
        # backstop that returns the user's credits.
        log.exception("Job %s could not be finalised", job.get("public_id"))
    finally:
        _inflight.discard(job["public_id"])


# --------------------------------------------------------------------------- #
#  Stale job sweeper
# --------------------------------------------------------------------------- #
def sweep_stale(minutes: int | None = None) -> int:
    """
    Refund jobs stuck in 'running' past the stale threshold.

    A job gets stranded when the process restarts mid-flight — a deploy, an
    out-of-memory kill, Passenger recycling an idle app. The user has been
    charged and will never receive output, so the credits go back.

    Run from cron:  * * * * *  python manage.py sweep-jobs

    Returns the number of jobs refunded.
    """
    cutoff = _now() - timedelta(minutes=minutes or Config.JOB_STALE_MINUTES)

    rows = query_all(
        "SELECT id, public_id, user_id, credits_charged FROM jobs "
        "WHERE status = 'running' AND created_at < %s",
        (cutoff,),
    )

    swept = 0
    for row in rows:
        # Skip anything this process is still working on. Two app processes
        # can both sweep; the refund inside fail_job is written so that a
        # second attempt on an already-refunded job is a no-op.
        if is_inflight(row["public_id"]):
            continue
        try:
            fail_job(
                {"id": row["id"], "public_id": row["public_id"],
                 "user_id": row["user_id"], "credits_charged": row["credits_charged"]},
                "stalled",
            )
            swept += 1
            log.warning("Swept stalled job %s (refunded %d credits)",
                        row["public_id"], row["credits_charged"] or 0)
        except Exception:
            log.exception("Could not sweep job %s", row["public_id"])

    return swept

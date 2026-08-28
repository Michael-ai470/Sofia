"""
The paths where a bug costs money: credit deduction, refund, and the races
introduced by moving execution onto a worker thread.
"""
import threading
import pytest
from datetime import timedelta

from app import catalog
from app.credits import (CreditError, complete_job, fail_job, open_job,
                         balance, _now)
from app.db import execute, query_one, query_all
from app.worker import sweep_stale


def _tool(slug="business-plan"):
    return catalog.get(slug)


COST = catalog.get("business-plan")["credits"]      # read, never hardcode


# --------------------------------------------------------------- charging --
def test_charge_deducts_exactly_once(user):
    tool = _tool()
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    open_job(user, tool, "1.2.3.4")
    assert balance(user["id"]) == 20 - COST


def test_cannot_overdraw(user):
    execute("UPDATE users SET credits = %s WHERE id = %s", (COST - 1, user["id"]))
    with pytest.raises(CreditError):
        open_job(user, _tool(), "1.2.3.4")
    assert balance(user["id"]) == COST - 1


def test_concurrent_runs_cannot_overdraw(user):
    """Balance covers exactly one run: exactly one of six may succeed."""
    execute("UPDATE users SET credits = %s WHERE id = %s", (COST, user["id"]))
    tool = _tool()
    results, lock = [], threading.Lock()

    def attempt():
        try:
            open_job(user, tool, "1.2.3.4")
            outcome = "ok"
        except CreditError:
            outcome = "declined"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert results.count("ok") == 1, results
    assert balance(user["id"]) == 0


# ---------------------------------------------------------------- refunds --
def test_failure_refunds(user):
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    job = open_job(user, _tool(), "1.2.3.4")
    assert balance(user["id"]) == 20 - COST
    fail_job(job, "timeout")
    assert balance(user["id"]) == 20
    assert query_one("SELECT status FROM jobs WHERE id=%s", (job["id"],))["status"] == "refunded"


def test_refund_is_idempotent(user):
    """The worker and the sweeper can both decide a job failed."""
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    job = open_job(user, _tool(), "1.2.3.4")
    fail_job(job, "timeout")
    fail_job(job, "stalled")
    fail_job(job, "internal")
    assert balance(user["id"]) == 20           # refunded once, not three times
    ledger = query_all(
        "SELECT * FROM credit_ledger WHERE job_id = %s AND reason='refund'", (job["id"],))
    assert len(ledger) == 1


def test_concurrent_refund_pays_once(user):
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    job = open_job(user, _tool(), "1.2.3.4")

    threads = [threading.Thread(target=fail_job, args=(job, "stalled")) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert balance(user["id"]) == 20


def test_complete_after_refund_is_rejected(user):
    """
    The sweeper refunds a slow job; the model then returns. The user must not
    receive a document they were refunded for.
    """
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    job = open_job(user, _tool(), "1.2.3.4")
    fail_job(job, "stalled")

    assert complete_job(job, {"kind": "document", "markdown": "# Late"}) is False
    row = query_one("SELECT status, output_json FROM jobs WHERE id=%s", (job["id"],))
    assert row["status"] == "refunded"
    assert row["output_json"] is None


def test_success_marks_succeeded(user):
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    job = open_job(user, _tool(), "1.2.3.4")
    assert complete_job(job, {"kind": "document", "markdown": "# Plan"}) is True
    assert query_one("SELECT status FROM jobs WHERE id=%s", (job["id"],))["status"] == "succeeded"
    assert balance(user["id"]) == 20 - COST   # no refund on success


# ---------------------------------------------------------------- sweeper --
def test_sweeper_refunds_stalled_job(user):
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    job = open_job(user, _tool(), "1.2.3.4")
    execute("UPDATE jobs SET created_at = %s WHERE id = %s",
            (_now() - timedelta(hours=2), job["id"]))

    assert sweep_stale() == 1
    assert balance(user["id"]) == 20


def test_sweeper_leaves_fresh_jobs_alone(user):
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    open_job(user, _tool(), "1.2.3.4")
    assert sweep_stale() == 0
    assert balance(user["id"]) == 20 - COST


def test_sweeper_ignores_finished_jobs(user):
    execute("UPDATE users SET credits = 20 WHERE id = %s", (user["id"],))
    job = open_job(user, _tool(), "1.2.3.4")
    complete_job(job, {"kind": "document", "markdown": "# Done"})
    execute("UPDATE jobs SET created_at = %s WHERE id = %s",
            (_now() - timedelta(hours=5), job["id"]))
    assert sweep_stale() == 0
    assert balance(user["id"]) == 20 - COST


# ------------------------------------------------------------- anon rules --
def test_anonymous_blocked_on_paid_tool():
    with pytest.raises(CreditError) as exc:
        open_job(None, _tool("business-plan"), "1.2.3.4")
    assert exc.value.status == 401


def test_anonymous_allowed_on_free_tool():
    job = open_job(None, _tool("cv-analysis"), "1.2.3.4")
    assert job["credits_charged"] == 0
    assert job["user_id"] is None

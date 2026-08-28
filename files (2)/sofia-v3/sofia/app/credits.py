"""
Sofia — credits.

The rule that matters: charge BEFORE the AI call, refund on failure.

Charging after the call means every timeout, every truncated response and
every 502 leaves the user debited with nothing to show for it. Charging
first and refunding is the only ordering where a crash mid-flight cannot
take someone's money.

The deduction itself is a single conditional UPDATE. `WHERE credits >= %s`
makes the balance check and the deduction one atomic operation, so two
concurrent requests cannot both pass a check-then-deduct race and push the
balance negative.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone

from app.db import connection, query_one
from config import Config

log = logging.getLogger("sofia.credits")

_ALPHABET = string.ascii_letters + string.digits


class CreditError(Exception):
    def __init__(self, message: str, status: int = 402):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def public_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(22))


# --------------------------------------------------------------------------- #
#  Job lifecycle
# --------------------------------------------------------------------------- #
def open_job(user: dict | None, tool: dict, ip: str, inputs_summary: dict | None = None) -> dict:
    """
    Create the job row and take payment for it in one transaction.

    Returns the job dict. Raises CreditError when the user cannot afford it,
    before any AI call has been made.
    """
    import json

    cost = int(tool.get("credits", 0))
    pid = public_id()

    # Anonymous runs are only permitted for tools explicitly marked free.
    if user is None:
        if not tool.get("free_preview"):
            raise CreditError("Create a free account to use this tool.", status=401)
        cost = 0

    charge = cost > 0 and Config.ENFORCE_CREDITS and not (user or {}).get("unlimited")

    with connection() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            if charge:
                # Atomic: the balance check and the deduction are one statement.
                cur.execute(
                    "UPDATE users SET credits = credits - %s "
                    "WHERE id = %s AND credits >= %s",
                    (cost, user["id"], cost),
                )
                if cur.rowcount != 1:
                    row = query_one("SELECT credits FROM users WHERE id = %s", (user["id"],))
                    have = row["credits"] if row else 0
                    raise CreditError(
                        f"This uses {cost} credits and you have {have}. Top up to continue."
                    )

                cur.execute("SELECT credits FROM users WHERE id = %s", (user["id"],))
                balance = cur.fetchone()["credits"]

                cur.execute(
                    "INSERT INTO credit_ledger (user_id, delta, balance_after, reason) "
                    "VALUES (%s, %s, %s, %s)",
                    (user["id"], -cost, balance, f"tool:{tool['slug']}"),
                )

            cur.execute(
                "INSERT INTO jobs (public_id, user_id, engine, tool, status, credits_charged, "
                "input_json, ip) VALUES (%s, %s, %s, %s, 'running', %s, %s, %s)",
                (
                    pid,
                    user["id"] if user else None,
                    tool["engine"],
                    tool["slug"],
                    cost if charge else 0,
                    json.dumps(inputs_summary or {})[:60000],
                    ip,
                ),
            )
            job_id = cur.lastrowid
        finally:
            cur.close()

    return {
        "id": job_id,
        "public_id": pid,
        "tool": tool["slug"],
        "credits_charged": cost if charge else 0,
        "user_id": user["id"] if user else None,
    }


def complete_job(job: dict, output: dict, usage: dict | None = None) -> bool:
    """
    Record a successful run. Returns False when the job was already
    finalised — the sweeper having refunded it while the model was still
    working. In that case the result is dropped rather than handing over a
    document the user has been refunded for.
    """
    import json

    usage = usage or {}
    with connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE jobs SET status='succeeded', output_json=%s, model=%s, "
                "tokens_in=%s, tokens_out=%s, tokens_cached=%s, cost_usd=%s, "
                "duration_ms=%s, ruleset_id=%s, ruleset_version=%s, completed_at=%s "
                "WHERE id = %s AND status IN ('pending','running')",
                (
                    json.dumps(output)[:16_000_000],
                    usage.get("model"),
                    usage.get("tokens_in"),
                    usage.get("tokens_out"),
                    usage.get("tokens_cached"),
                    usage.get("cost_usd"),
                    usage.get("duration_ms"),
                    usage.get("ruleset_id"),
                    usage.get("ruleset_version"),
                    _now(),
                    job["id"],
                ),
            )
            if cur.rowcount != 1:
                log.warning(
                    "Job %s completed but was already finalised — result discarded.",
                    job.get("public_id"),
                )
                return False
        finally:
            cur.close()
    return True


def fail_job(job: dict, error_code: str, error_id: str | None = None) -> None:
    """
    Mark the job failed and put the credits back.

    Refunding is unconditional: if we charged, we return it. A user should
    never pay for output they did not receive, and reconciling that by hand
    later is not a plan.
    """
    refunded = False
    with connection() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            cost = int(job.get("credits_charged") or 0)
            uid = job.get("user_id")

            # Claim the job FIRST, conditional on it still being open. Two
            # callers can race here — the worker finishing at the same moment
            # the sweeper decides the job is stalled, or two app processes
            # both sweeping. Exactly one wins the UPDATE; the loser sees
            # rowcount 0 and returns without touching the balance. Refunding
            # before claiming would pay the user twice.
            cur.execute(
                "UPDATE jobs SET status='failed', error_code=%s, error_id=%s, "
                "completed_at=%s WHERE id = %s AND status IN ('pending','running')",
                ((error_code or "unknown")[:64], error_id, _now(), job["id"]),
            )
            if cur.rowcount != 1:
                log.info("Job %s was already finalised; no refund issued.",
                         job.get("public_id"))
                return

            if cost > 0 and uid:
                cur.execute(
                    "UPDATE users SET credits = credits + %s WHERE id = %s", (cost, uid)
                )
                cur.execute("SELECT credits FROM users WHERE id = %s", (uid,))
                balance = cur.fetchone()["credits"]
                cur.execute(
                    "INSERT INTO credit_ledger (user_id, delta, balance_after, reason, job_id) "
                    "VALUES (%s, %s, %s, 'refund', %s)",
                    (uid, cost, balance, job["id"]),
                )
                cur.execute(
                    "UPDATE jobs SET status='refunded' WHERE id = %s", (job["id"],)
                )
                refunded = True
        finally:
            cur.close()

    log.warning(
        "Job %s failed (%s); credits %s",
        job.get("public_id"), error_code, "refunded" if refunded else "none charged",
    )


# --------------------------------------------------------------------------- #
#  Manual adjustments (admin, payments)
# --------------------------------------------------------------------------- #
def grant(user_id: int, amount: int, reason: str, reference: str | None = None) -> int:
    if amount == 0:
        raise CreditError("Amount must not be zero.", status=400)

    with connection() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            if amount < 0:
                cur.execute(
                    "UPDATE users SET credits = credits + %s WHERE id = %s AND credits >= %s",
                    (amount, user_id, -amount),
                )
                if cur.rowcount != 1:
                    raise CreditError("That user does not have enough credits to deduct.", 400)
            else:
                cur.execute(
                    "UPDATE users SET credits = credits + %s WHERE id = %s", (amount, user_id)
                )

            cur.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise CreditError("No such user.", 404)
            balance = row["credits"]

            cur.execute(
                "INSERT INTO credit_ledger (user_id, delta, balance_after, reason, reference) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, amount, balance, reason[:64], reference),
            )
            return balance
        finally:
            cur.close()


def balance(user_id: int) -> int:
    row = query_one("SELECT credits FROM users WHERE id = %s", (user_id,))
    return int(row["credits"]) if row else 0

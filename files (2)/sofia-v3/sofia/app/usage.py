"""
Sofia — credit usage analytics.

Powers the user-facing usage dashboard and the admin margin view.

The dashboard exists to answer three questions a paying user actually asks:
where did my credits go, how fast am I spending them, and how long will what
I have left last. Everything here serves one of those. A chart that answers
none of them is decoration on a page someone opened because they were worried
about money.

All figures come from the `jobs` and `credit_ledger` tables. Nothing is
estimated — a usage dashboard that disagrees with the ledger is worse than
no dashboard, because it turns a billing question into a trust question.
"""

from __future__ import annotations

from datetime import date, timedelta

from app import catalog
from app.db import query_all, query_one


ENGINE_LABELS = {
    "E1": "Career & CV",
    "E2": "Recruiter",
    "E3": "Plans & Proposals",
    "E4": "Tax & Compliance",
    "E5": "Contracts",
    "E6": "Financial Documents",
    "E7": "Correspondence",
}


def summary(user_id: int, days: int = 30) -> dict:
    """Headline numbers for the top of the dashboard."""
    since = date.today() - timedelta(days=days)

    spent = query_one(
        "SELECT COALESCE(SUM(-delta),0) AS credits FROM credit_ledger "
        "WHERE user_id=%s AND delta < 0 AND created_at >= %s",
        (user_id, since),
    )["credits"]

    totals = query_one(
        "SELECT COUNT(*) AS runs, "
        "SUM(status='succeeded') AS succeeded, "
        "SUM(status='refunded') AS refunded "
        "FROM jobs WHERE user_id=%s AND created_at >= %s",
        (user_id, since),
    ) or {}

    balance_row = query_one("SELECT credits FROM users WHERE id=%s", (user_id,))
    balance = balance_row["credits"] if balance_row else 0

    # Burn rate over the window, and what that implies for the balance. Only
    # meaningful once there is some history — projecting a month of runway
    # from a single day's use would be a made-up number.
    per_day = round(spent / days, 2) if days else 0.0
    runway = None
    if per_day > 0 and (totals.get("runs") or 0) >= 3:
        runway = int(balance / per_day)

    return {
        "balance": balance,
        "spent": int(spent),
        "runs": int(totals.get("runs") or 0),
        "succeeded": int(totals.get("succeeded") or 0),
        "refunded": int(totals.get("refunded") or 0),
        "per_day": per_day,
        "runway_days": runway,
        "window_days": days,
    }


def daily(user_id: int, days: int = 30) -> list[dict]:
    """
    Credits spent per day, gap-filled.

    Gap-filling matters: a sparse series drawn as a line implies the user was
    active on days they were not, and a chart that lies about the shape of
    spending is worse than a table.
    """
    since = date.today() - timedelta(days=days - 1)

    rows = query_all(
        "SELECT DATE(created_at) AS day, COALESCE(SUM(-delta),0) AS credits "
        "FROM credit_ledger WHERE user_id=%s AND delta < 0 AND created_at >= %s "
        "GROUP BY DATE(created_at) ORDER BY day",
        (user_id, since),
    )
    by_day = {r["day"]: int(r["credits"]) for r in rows}

    series = []
    for offset in range(days):
        day = since + timedelta(days=offset)
        series.append({"date": day.isoformat(), "credits": by_day.get(day, 0)})
    return series


def by_tool(user_id: int, days: int = 30) -> list[dict]:
    """Where the credits went, biggest first."""
    since = date.today() - timedelta(days=days)

    rows = query_all(
        "SELECT tool, engine, COUNT(*) AS runs, "
        "COALESCE(SUM(credits_charged),0) AS credits "
        "FROM jobs WHERE user_id=%s AND created_at >= %s "
        "AND status IN ('succeeded','running') "
        "GROUP BY tool, engine ORDER BY credits DESC",
        (user_id, since),
    )

    total = sum(int(r["credits"]) for r in rows) or 1
    out = []
    for row in rows:
        tool = catalog.get(row["tool"])
        credits = int(row["credits"])
        out.append({
            "slug": row["tool"],
            "name": tool["name"] if tool else row["tool"],
            "engine": row["engine"],
            "engine_label": ENGINE_LABELS.get(row["engine"], row["engine"]),
            "accent": tool.get("accent") if tool else "indigo",
            "runs": int(row["runs"]),
            "credits": credits,
            "share": round(credits / total * 100, 1),
        })
    return out


def by_engine(user_id: int, days: int = 30) -> list[dict]:
    """Rolled up to engine, for the donut."""
    buckets: dict[str, dict] = {}
    for row in by_tool(user_id, days):
        bucket = buckets.setdefault(row["engine"], {
            "engine": row["engine"],
            "label": row["engine_label"],
            "accent": row["accent"],
            "credits": 0,
            "runs": 0,
        })
        bucket["credits"] += row["credits"]
        bucket["runs"] += row["runs"]

    total = sum(b["credits"] for b in buckets.values()) or 1
    out = sorted(buckets.values(), key=lambda b: -b["credits"])
    for bucket in out:
        bucket["share"] = round(bucket["credits"] / total * 100, 1)
    return out


def ledger(user_id: int, limit: int = 40) -> list[dict]:
    """
    Every credit movement, newest first.

    Refunds are shown, not hidden. A user who sees a failed run followed by
    a visible refund trusts the meter; one who just sees a balance drop and
    no document does not.
    """
    rows = query_all(
        "SELECT l.delta, l.balance_after, l.reason, l.created_at, "
        "j.public_id, j.tool, j.status "
        "FROM credit_ledger l LEFT JOIN jobs j ON j.id = l.job_id "
        "WHERE l.user_id = %s ORDER BY l.id DESC LIMIT %s",
        (user_id, limit),
    )

    out = []
    for row in rows:
        reason = row["reason"] or ""
        tool = catalog.get(row["tool"]) if row["tool"] else None

        if reason.startswith("tool:"):
            label = tool["name"] if tool else reason.split(":", 1)[1]
            kind = "spend"
        elif reason == "refund":
            label = f"Refund — {tool['name']}" if tool else "Refund"
            kind = "refund"
        elif reason.startswith("purchase:"):
            label = f"Purchase — {reason.split(':', 1)[1].replace('-', ' ').title()}"
            kind = "purchase"
        elif reason.startswith("signup"):
            label = "Welcome credits"
            kind = "bonus"
        else:
            label = reason.replace("_", " ").capitalize() or "Adjustment"
            kind = "adjustment"

        out.append({
            "delta": int(row["delta"]),
            "balance_after": int(row["balance_after"]),
            "label": label,
            "kind": kind,
            "job_id": row["public_id"],
            "at": row["created_at"],
        })
    return out


def dashboard(user_id: int, days: int = 30) -> dict:
    """Everything the usage page needs, in one call."""
    return {
        "summary": summary(user_id, days),
        "daily": daily(user_id, days),
        "by_tool": by_tool(user_id, days),
        "by_engine": by_engine(user_id, days),
        "ledger": ledger(user_id),
    }


# --------------------------------------------------------------------------- #
#  Admin — measured cost per credit
# --------------------------------------------------------------------------- #
def measured_cost_per_credit(days: int = 30) -> float:
    """
    Actual USD of AI spend per credit sold, from job telemetry.

    This is the number that makes the margin table honest after a model
    migration. The financial analysis computed margins on Claude pricing;
    once traffic moves to cheaper providers the real figure drops sharply,
    and guessing at it defeats the purpose of having tracked it.
    """
    since = date.today() - timedelta(days=days)
    row = query_one(
        "SELECT COALESCE(SUM(cost_usd),0) AS cost, "
        "COALESCE(SUM(credits_charged),0) AS credits "
        "FROM jobs WHERE created_at >= %s AND status='succeeded'",
        (since,),
    ) or {}
    credits = float(row.get("credits") or 0)
    if credits <= 0:
        return 0.0
    return round(float(row.get("cost") or 0) / credits, 6)


def provider_mix(days: int = 30) -> list[dict]:
    """Which providers served traffic, and how often the fallback fired."""
    since = date.today() - timedelta(days=days)
    return query_all(
        "SELECT model, COUNT(*) AS runs, "
        "COALESCE(SUM(cost_usd),0) AS cost_usd, "
        "COALESCE(SUM(tokens_in),0) AS tokens_in, "
        "COALESCE(SUM(tokens_cached),0) AS tokens_cached "
        "FROM jobs WHERE created_at >= %s AND status='succeeded' "
        "GROUP BY model ORDER BY runs DESC",
        (since,),
    )

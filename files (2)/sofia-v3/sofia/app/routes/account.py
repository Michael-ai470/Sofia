"""Sofia — the signed-in area."""

from __future__ import annotations

import json

from flask import (Blueprint, abort, flash, g, make_response, redirect,
                   render_template, request, url_for)

from app import catalog, export, payments, pricing, usage
from app.auth_service import login_required
from app.db import query_all, query_one
from app.engines import render_markdown
from config import Config

bp = Blueprint("account", __name__)


@bp.route("/")
@login_required
def dashboard():
    uid = g.current_user["id"]

    jobs = query_all(
        "SELECT public_id, tool, status, credits_charged, created_at FROM jobs "
        "WHERE user_id = %s ORDER BY created_at DESC LIMIT 25",
        (uid,),
    )
    totals = query_one(
        "SELECT COUNT(*) AS jobs_total, COALESCE(SUM(credits_charged),0) AS credits_used "
        "FROM jobs WHERE user_id = %s AND status IN ('succeeded','running')",
        (uid,),
    ) or {"jobs_total": 0, "credits_used": 0}

    return render_template(
        "account/dashboard.html",
        jobs=jobs,
        stats=totals,
        tool_names={t["slug"]: t["name"] for t in catalog.TOOLS},
    )


@bp.route("/credits")
@login_required
def credits():
    return render_template(
        "account/credits.html",
        packages=pricing.for_display(g.current_user.get("country")),
        balance=g.current_user["credits"],
    )


@bp.route("/usage")
@login_required
def usage_page():
    """
    Where did my credits go, how fast am I spending, how long will they last.
    Everything on this page answers one of those three questions.
    """
    days = 30
    try:
        days = max(7, min(90, int(request.args.get("days", 30))))
    except ValueError:
        pass

    data = usage.dashboard(g.current_user["id"], days)
    return render_template(
        "account/usage.html",
        days=days,
        summary=data["summary"],
        daily=data["daily"],
        by_tool=data["by_tool"],
        by_engine=data["by_engine"],
        ledger=data["ledger"],
        daily_json=json.dumps(data["daily"]),
    )


@bp.route("/buy", methods=["POST"])
@login_required
def buy():
    package_id = (request.form.get("package") or "").strip()
    if not pricing.package(package_id):
        flash("That package does not exist.", "err")
        return redirect(url_for("account.credits"))

    callback = url_for("account.payment_return", _external=True)
    try:
        result = payments.initiate(g.current_user, package_id, callback)
    except payments.PaymentError as exc:
        flash(str(exc), "err")
        return redirect(url_for("account.credits"))

    return redirect(result["checkout_url"])


@bp.route("/payment/return")
@login_required
def payment_return():
    """
    Where the gateway sends the user back to.

    This never grants credits by itself — the webhook does that. It asks the
    gateway for the current state so the page tells the truth to someone who
    is standing there watching, and settles if the webhook has not landed yet.
    """
    reference = (request.args.get("reference")
                 or request.args.get("paymentReference") or "").strip()
    if not reference:
        flash("We could not identify that payment.", "err")
        return redirect(url_for("account.credits"))

    try:
        result = payments.verify(reference)
    except payments.PaymentError as exc:
        flash(str(exc), "err")
        return redirect(url_for("account.credits"))

    if result["status"] == "paid":
        flash(f"Payment confirmed — {result['credits']} credits added.", "ok")
        return redirect(url_for("account.usage_page"))

    flash("Your payment is still being confirmed. Credits appear as soon as "
          "the provider confirms it, usually within a minute.", "warn")
    return redirect(url_for("account.credits"))


@bp.route("/job/<public_id>")
@login_required
def job(public_id):
    row = query_one(
        "SELECT * FROM jobs WHERE public_id = %s AND user_id = %s",
        (public_id, g.current_user["id"]),
    )
    if not row or row["status"] != "succeeded":
        abort(404)

    output = row["output_json"]
    if isinstance(output, (str, bytes)):
        output = json.loads(output)

    tool = catalog.get(row["tool"])
    return render_template(
        "account/job.html",
        job=row,
        tool_name=tool["name"] if tool else row["tool"],
        payload_json=json.dumps(output or {}),
        downloadable=bool((output or {}).get("markdown")),
    )


@bp.route("/job/<public_id>/download.<fmt>")
def download(public_id, fmt):
    """
    Export a finished job as PDF or Word.

    Not decorated with @login_required: the free CV tools run anonymously,
    and a user who just paid nothing still owns what they produced. The
    session carries the public_id for those, exactly as the poll endpoint
    does. Ownership is checked either way — a job is never served on the
    strength of knowing its id alone.
    """
    from flask import session

    row = query_one(
        "SELECT public_id, user_id, tool, status, output_json FROM jobs "
        "WHERE public_id = %s",
        (public_id,),
    )
    if not row or row["status"] != "succeeded":
        abort(404)

    if row["user_id"] is not None:
        if not g.current_user or g.current_user["id"] != row["user_id"]:
            abort(404)
    elif public_id not in session.get("anon_jobs", []):
        abort(404)

    output = row["output_json"]
    if isinstance(output, (str, bytes)):
        output = json.loads(output)

    tool = catalog.get(row["tool"])
    try:
        data, mimetype, filename = export.build(
            output or {}, fmt, tool["name"] if tool else row["tool"]
        )
    except export.ExportError as exc:
        flash(str(exc), "err")
        return redirect(url_for("account.job", public_id=public_id))

    response = make_response(data)
    response.headers["Content-Type"] = mimetype
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Content-Length"] = str(len(data))
    # The document contains the user's own commercial or personal material.
    # It must never sit in a shared cache.
    response.headers["Cache-Control"] = "private, no-store"
    return response

"""Sofia — admin panel. Separate auth, separate session type, every action audited."""

from __future__ import annotations

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   url_for)

from app.auth_service import (AuthError, admin_required, audit,
                              authenticate_admin, client_ip, login_admin,
                              logout_admin, rate_limited)
from app.credits import CreditError, grant
from app.db import query_all, query_one

bp = Blueprint("admin", __name__)


@bp.route("/", methods=["GET", "POST"])
def login():
    if g.current_admin:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        if rate_limited(f"adminlogin:{client_ip()}", limit=5, window_seconds=900):
            flash("Too many attempts.", "err")
            return render_template("admin/login.html")
        try:
            admin = authenticate_admin(
                request.form.get("email", ""), request.form.get("password", "")
            )
        except AuthError as exc:
            flash(str(exc), "err")
            return render_template("admin/login.html")

        login_admin(admin["id"])
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    logout_admin()
    return redirect(url_for("admin.login"))


@bp.route("/dashboard")
@admin_required
def dashboard():
    metrics = {
        "users": (query_one("SELECT COUNT(*) c FROM users") or {}).get("c", 0),
        "jobs_today": (query_one(
            "SELECT COUNT(*) c FROM jobs WHERE created_at >= CURDATE()"
        ) or {}).get("c", 0),
        "jobs_failed": (query_one(
            "SELECT COUNT(*) c FROM jobs WHERE status IN ('failed','refunded') "
            "AND created_at >= NOW() - INTERVAL 1 DAY"
        ) or {}).get("c", 0),
        "cost_30d": (query_one(
            "SELECT COALESCE(SUM(cost_usd),0) c FROM jobs "
            "WHERE created_at >= NOW() - INTERVAL 30 DAY"
        ) or {}).get("c", 0),
        "stale_rulesets": (query_one(
            "SELECT COUNT(*) c FROM rulesets WHERE status='verified' "
            "AND (verified_on IS NULL OR verified_on < CURDATE() - INTERVAL 365 DAY)"
        ) or {}).get("c", 0),
    }

    top_tools = query_all(
        "SELECT tool, COUNT(*) runs, "
        "SUM(status IN ('failed','refunded')) failures, "
        "SUM(credits_charged) credits "
        "FROM jobs WHERE created_at >= NOW() - INTERVAL 30 DAY "
        "GROUP BY tool ORDER BY runs DESC LIMIT 15"
    )

    return render_template("admin/dashboard.html", m=metrics,
                           top_tools=top_tools, active="dashboard")


@bp.route("/users")
@admin_required
def users():
    q = (request.args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        rows = query_all(
            "SELECT id, email, full_name, credits, plan, status, created_at FROM users "
            "WHERE email LIKE %s OR full_name LIKE %s ORDER BY created_at DESC LIMIT 100",
            (like, like),
        )
    else:
        rows = query_all(
            "SELECT id, email, full_name, credits, plan, status, created_at FROM users "
            "ORDER BY created_at DESC LIMIT 100"
        )
    return render_template("admin/users.html", users=rows, q=q, active="users")


@bp.route("/users/grant", methods=["POST"])
@admin_required
def grant_credits():
    try:
        user_id = int(request.form.get("user_id", 0))
        amount = int(request.form.get("amount", 0))
    except (TypeError, ValueError):
        flash("Invalid input.", "err")
        return redirect(url_for("admin.users"))

    try:
        new_balance = grant(user_id, amount, reason="admin_grant",
                            reference=f"by:{g.current_admin['email']}")
    except CreditError as exc:
        flash(str(exc), "err")
        return redirect(url_for("admin.users"))

    audit("credits.grant", "user", user_id, {"amount": amount, "balance": new_balance})
    flash(f"Adjusted by {amount:+d}. New balance: {new_balance}.", "ok")
    return redirect(url_for("admin.users"))


@bp.route("/jobs")
@admin_required
def jobs():
    rows = query_all(
        "SELECT j.created_at, j.tool, j.status, j.model, j.tokens_in, j.tokens_out, "
        "j.cost_usd, j.error_code, u.email "
        "FROM jobs j LEFT JOIN users u ON u.id = j.user_id "
        "ORDER BY j.created_at DESC LIMIT 200"
    )
    return render_template("admin/jobs.html", jobs=rows, active="jobs")


@bp.route("/rulesets")
@admin_required
def rulesets():
    rows = query_all(
        "SELECT ruleset_id, version, jurisdiction, effective_from, effective_to, "
        "status, verified_on, verified_by FROM rulesets "
        "ORDER BY jurisdiction, ruleset_id, version DESC"
    )
    return render_template("admin/rulesets.html", rulesets=rows, active="rulesets")

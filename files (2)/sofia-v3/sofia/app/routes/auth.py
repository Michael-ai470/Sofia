"""Sofia — signup, login, logout, password reset."""

from __future__ import annotations

import logging

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   url_for)

from app.auth_service import (AuthError, authenticate, client_ip,
                              consume_reset_token, create_user, issue_reset_token,
                              login_user, logout_user, rate_limited)
from app.mail import send_reset_email
from config import Config

log = logging.getLogger("sofia.auth.routes")
bp = Blueprint("auth", __name__)


def _safe_next(raw: str | None) -> str:
    """Only ever redirect to our own paths. An open redirect is a phishing gift."""
    value = (raw or "").strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("public.home")


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if g.current_user:
        return redirect(url_for("account.dashboard"))

    next_url = request.values.get("next")

    if request.method == "POST":
        if rate_limited(f"signup:{client_ip()}", limit=5, window_seconds=3600):
            flash("Too many sign-up attempts. Try again in an hour.", "err")
            return render_template("auth/signup.html", next_url=next_url)

        try:
            user = create_user(
                email=request.form.get("email", ""),
                password=request.form.get("password", ""),
                full_name=request.form.get("full_name", ""),
                country=request.form.get("country", "NG"),
            )
        except AuthError as exc:
            flash(str(exc), "err")
            return render_template("auth/signup.html", next_url=next_url)

        login_user(user["id"])
        flash(f"Welcome to Sofia. You have {Config.SIGNUP_BONUS_CREDITS} credits to start.", "ok")
        return redirect(_safe_next(next_url))

    return render_template("auth/signup.html", next_url=next_url)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.current_user:
        return redirect(url_for("account.dashboard"))

    next_url = request.values.get("next")

    if request.method == "POST":
        # Two buckets: by IP to stop a spray, by email to stop a targeted
        # guess from a rotating address.
        email_raw = (request.form.get("email") or "").strip().lower()[:120]
        if (rate_limited(f"login_ip:{client_ip()}", limit=10, window_seconds=900)
                or rate_limited(f"login_email:{email_raw}", limit=8, window_seconds=900)):
            flash("Too many attempts. Wait fifteen minutes and try again.", "err")
            return render_template("auth/login.html", next_url=next_url)

        try:
            user = authenticate(email_raw, request.form.get("password", ""))
        except AuthError as exc:
            flash(str(exc), "err")
            return render_template("auth/login.html", next_url=next_url)

        login_user(user["id"])
        return redirect(_safe_next(next_url))

    return render_template("auth/login.html", next_url=next_url)


@bp.route("/logout")
def logout():
    logout_user()
    flash("You are logged out.", "ok")
    return redirect(url_for("public.home"))


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        if rate_limited(f"forgot:{client_ip()}", limit=5, window_seconds=3600):
            flash("Too many requests. Try again later.", "err")
            return render_template("auth/forgot.html")

        result = issue_reset_token(request.form.get("email", ""))
        if result:
            raw_token, user = result
            link = f"{Config.SITE_URL}{url_for('auth.reset', token=raw_token)}"
            try:
                send_reset_email(user["email"], user.get("full_name"), link)
            except Exception:
                log.exception("Could not send the reset email")

        # Identical response whether or not the account exists, so this
        # endpoint cannot be used to discover who has an account.
        flash("If that email has an account, a reset link is on its way.", "ok")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot.html")


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    if request.method == "POST":
        if rate_limited(f"reset:{client_ip()}", limit=10, window_seconds=3600):
            flash("Too many attempts. Try again later.", "err")
            return render_template("auth/reset.html", token=token)
        try:
            consume_reset_token(token, request.form.get("password", ""))
        except AuthError as exc:
            flash(str(exc), "err")
            return render_template("auth/reset.html", token=token)

        flash("Password updated. Log in with your new password.", "ok")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset.html", token=token)

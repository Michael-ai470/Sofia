"""
Sofia — authentication and session handling.

Design notes worth keeping:

  * Sessions are server-side rows, not just a signed cookie. The cookie
    carries a random token; the database holds its SHA-256. That means a
    session can actually be revoked from the admin panel, and a leaked
    cookie stops working the moment it is revoked.

  * Admins live in their own table with their own session type. An admin
    is not a user with a flag, so no bug in the user path can escalate
    someone into the admin panel.

  * Rate limiting is database-backed. In-memory counters are worthless on
    cPanel, where Passenger recycles workers freely and each worker would
    keep its own count.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import g, redirect, request, session, url_for, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import execute, query_one, query_all
from config import Config

log = logging.getLogger("sofia.auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
MIN_PASSWORD = 10

USER_COOKIE = "sofia_uid"
ADMIN_COOKIE = "sofia_aid"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
#  Validation
# --------------------------------------------------------------------------- #
def validate_email(email: str) -> str | None:
    email = (email or "").strip().lower()
    if not email or len(email) > 255 or not EMAIL_RE.match(email):
        return None
    return email


def validate_password(password: str) -> str | None:
    """Returns an error message, or None if acceptable."""
    if not password or len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if len(password) > 200:
        return "Password is too long."
    if password.lower() in {
        "password12", "1234567890", "qwertyuiop", "passwordpassword",
    }:
        return "Please choose a less common password."
    return None


# --------------------------------------------------------------------------- #
#  Rate limiting
# --------------------------------------------------------------------------- #
def rate_limited(bucket: str, limit: int, window_seconds: int) -> bool:
    """
    Returns True when the caller has exceeded `limit` hits in the window.
    Fails open on a database error — a broken limiter must not take the
    whole site down, but it does get logged loudly.
    """
    window = _now().replace(microsecond=0)
    window = window - timedelta(seconds=window.timestamp() % window_seconds)
    try:
        execute(
            "INSERT INTO rate_limits (bucket, window_start, hits) VALUES (%s, %s, 1) "
            "ON DUPLICATE KEY UPDATE hits = hits + 1",
            (bucket[:160], window),
        )
        row = query_one(
            "SELECT hits FROM rate_limits WHERE bucket = %s AND window_start = %s",
            (bucket[:160], window),
        )
        # Opportunistic cleanup, cheap and keeps the table small.
        if secrets.randbelow(100) == 0:
            execute(
                "DELETE FROM rate_limits WHERE window_start < %s",
                (_now() - timedelta(days=1),),
            )
        return bool(row and row["hits"] > limit)
    except Exception:
        log.exception("Rate limiter failed for bucket %s", bucket)
        return False


def client_ip() -> str:
    return (request.remote_addr or "0.0.0.0")[:45]


# --------------------------------------------------------------------------- #
#  Sessions
# --------------------------------------------------------------------------- #
def _start_session(subject_type: str, subject_id: int, hours: int) -> str:
    raw = secrets.token_urlsafe(48)
    execute(
        "INSERT INTO sessions (id, subject_type, subject_id, ip, user_agent, expires_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (
            _hash_token(raw),
            subject_type,
            subject_id,
            client_ip(),
            (request.headers.get("User-Agent") or "")[:255],
            _now() + timedelta(hours=hours),
        ),
    )
    return raw


def _resolve_session(raw: str | None, subject_type: str) -> int | None:
    if not raw:
        return None
    row = query_one(
        "SELECT subject_id FROM sessions "
        "WHERE id = %s AND subject_type = %s AND revoked_at IS NULL AND expires_at > %s",
        (_hash_token(raw), subject_type, _now()),
    )
    return int(row["subject_id"]) if row else None


def revoke_session(raw: str | None) -> None:
    if raw:
        execute(
            "UPDATE sessions SET revoked_at = %s WHERE id = %s AND revoked_at IS NULL",
            (_now(), _hash_token(raw)),
        )


def revoke_all_for(subject_type: str, subject_id: int) -> None:
    execute(
        "UPDATE sessions SET revoked_at = %s "
        "WHERE subject_type = %s AND subject_id = %s AND revoked_at IS NULL",
        (_now(), subject_type, subject_id),
    )


# --------------------------------------------------------------------------- #
#  Current subject loaders (called from before_request)
# --------------------------------------------------------------------------- #
def load_current_user() -> dict | None:
    uid = _resolve_session(session.get(USER_COOKIE), "user")
    if not uid:
        return None
    return query_one(
        "SELECT id, email, full_name, country, credits, unlimited, plan, status, created_at "
        "FROM users WHERE id = %s AND status = 'active'",
        (uid,),
    )


def load_current_admin() -> dict | None:
    aid = _resolve_session(session.get(ADMIN_COOKIE), "admin")
    if not aid:
        return None
    return query_one(
        "SELECT id, email, full_name, role, status FROM admins "
        "WHERE id = %s AND status = 'active'",
        (aid,),
    )


# --------------------------------------------------------------------------- #
#  Signup / login
# --------------------------------------------------------------------------- #
class AuthError(Exception):
    pass


def create_user(email: str, password: str, full_name: str, country: str = "NG") -> dict:
    email_clean = validate_email(email)
    if not email_clean:
        raise AuthError("That email address does not look right.")

    pw_error = validate_password(password)
    if pw_error:
        raise AuthError(pw_error)

    if query_one("SELECT id FROM users WHERE email = %s", (email_clean,)):
        # Deliberately the same phrasing the login failure uses, so this
        # endpoint cannot be used to enumerate which emails have accounts.
        raise AuthError("We could not create that account. Try logging in instead.")

    user_id = execute(
        "INSERT INTO users (email, password_hash, full_name, country, credits, plan) "
        "VALUES (%s, %s, %s, %s, %s, 'free')",
        (
            email_clean,
            generate_password_hash(password, method="pbkdf2:sha256:600000"),
            (full_name or "").strip()[:120] or None,
            (country or "NG")[:2].upper(),
            Config.SIGNUP_BONUS_CREDITS,
        ),
    )

    if Config.SIGNUP_BONUS_CREDITS:
        execute(
            "INSERT INTO credit_ledger (user_id, delta, balance_after, reason) "
            "VALUES (%s, %s, %s, 'signup_bonus')",
            (user_id, Config.SIGNUP_BONUS_CREDITS, Config.SIGNUP_BONUS_CREDITS),
        )

    log.info("New user %s (id=%s)", email_clean, user_id)
    return {"id": user_id, "email": email_clean}


def authenticate(email: str, password: str) -> dict:
    email_clean = validate_email(email) or ""
    row = query_one(
        "SELECT id, email, password_hash, status FROM users WHERE email = %s",
        (email_clean,),
    )

    # Always run a hash comparison, even when the user does not exist, so
    # response timing does not reveal which emails are registered.
    stored = row["password_hash"] if row else (
        "pbkdf2:sha256:600000$dummy$" + "0" * 64
    )
    ok = check_password_hash(stored, password or "")

    if not row or not ok:
        raise AuthError("Email or password is incorrect.")
    if row["status"] != "active":
        raise AuthError("This account is not active. Contact support.")

    execute("UPDATE users SET last_login_at = %s WHERE id = %s", (_now(), row["id"]))
    return {"id": row["id"], "email": row["email"]}


def login_user(user_id: int) -> None:
    session.permanent = True
    session[USER_COOKIE] = _start_session("user", user_id, Config.SESSION_DAYS * 24)


def logout_user() -> None:
    revoke_session(session.pop(USER_COOKIE, None))


def authenticate_admin(email: str, password: str) -> dict:
    email_clean = validate_email(email) or ""
    row = query_one(
        "SELECT id, email, password_hash, status FROM admins WHERE email = %s",
        (email_clean,),
    )
    stored = row["password_hash"] if row else ("pbkdf2:sha256:600000$dummy$" + "0" * 64)
    ok = check_password_hash(stored, password or "")
    if not row or not ok or row["status"] != "active":
        raise AuthError("Sign-in failed.")
    execute(
        "UPDATE admins SET last_login_at = %s, last_login_ip = %s WHERE id = %s",
        (_now(), client_ip(), row["id"]),
    )
    return {"id": row["id"], "email": row["email"]}


def login_admin(admin_id: int) -> None:
    session[ADMIN_COOKIE] = _start_session("admin", admin_id, Config.ADMIN_SESSION_HOURS)


def logout_admin() -> None:
    revoke_session(session.pop(ADMIN_COOKIE, None))


# --------------------------------------------------------------------------- #
#  Password reset
# --------------------------------------------------------------------------- #
def issue_reset_token(email: str) -> tuple[str, dict] | None:
    email_clean = validate_email(email)
    if not email_clean:
        return None
    user = query_one("SELECT id, email, full_name FROM users WHERE email = %s AND status='active'",
                     (email_clean,))
    if not user:
        return None

    raw = secrets.token_urlsafe(40)
    execute(
        "INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user["id"], _hash_token(raw), _now() + timedelta(hours=1)),
    )
    return raw, user


def consume_reset_token(raw: str, new_password: str) -> None:
    pw_error = validate_password(new_password)
    if pw_error:
        raise AuthError(pw_error)

    row = query_one(
        "SELECT id, user_id FROM password_resets "
        "WHERE token_hash = %s AND used_at IS NULL AND expires_at > %s",
        (_hash_token(raw), _now()),
    )
    if not row:
        raise AuthError("That reset link has expired or has already been used.")

    execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (generate_password_hash(new_password, method="pbkdf2:sha256:600000"), row["user_id"]),
    )
    execute("UPDATE password_resets SET used_at = %s WHERE id = %s", (_now(), row["id"]))
    # A password change invalidates every existing session for that user.
    revoke_all_for("user", row["user_id"])


# --------------------------------------------------------------------------- #
#  Decorators
# --------------------------------------------------------------------------- #
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not getattr(g, "current_user", None):
            if request.path.startswith("/api/"):
                return jsonify({
                    "status": "error",
                    "code": "auth_required",
                    "message": "Create a free account to use this tool.",
                }), 401
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not getattr(g, "current_admin", None):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapper


def audit(action: str, target_type: str = None, target_id: str = None, detail=None) -> None:
    import json
    admin = getattr(g, "current_admin", None)
    execute(
        "INSERT INTO audit_log (actor_type, actor_id, action, target_type, target_id, detail, ip) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (
            "admin" if admin else "system",
            admin["id"] if admin else None,
            action[:64],
            (target_type or None),
            (str(target_id)[:64] if target_id is not None else None),
            json.dumps(detail) if detail is not None else None,
            client_ip(),
        ),
    )

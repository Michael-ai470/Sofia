"""
Sofia — application factory.

Boots loudly. If the config is unsafe or the database is unreachable, the
process refuses to start rather than serving a site that looks fine and
fails on every write.
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
from datetime import datetime, timezone

from flask import Flask, g, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

import config as config_module
from config import Config


def _configure_logging() -> None:
    level = logging.DEBUG if Config.DEBUG else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # mysql-connector is chatty at DEBUG and leaks query text into logs
    logging.getLogger("mysql.connector").setLevel(logging.WARNING)


def create_app() -> Flask:
    _configure_logging()
    log = logging.getLogger("sofia")

    problems = config_module.validate()
    if problems:
        message = "Sofia cannot start:\n  - " + "\n  - ".join(problems)
        if Config.ENV == "production":
            raise SystemExit(message)
        log.warning(message)

    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY or secrets.token_hex(32)

    # Behind Passenger/nginx on cPanel. Without this, request.remote_addr is
    # the proxy for every visitor, which silently breaks rate limiting by IP
    # and makes every abuse control useless.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.permanent_session_lifetime = __import__("datetime").timedelta(
        days=Config.SESSION_DAYS
    )

    # -- database ---------------------------------------------------------
    from app.db import init_db
    try:
        init_db()
    except RuntimeError as exc:
        if Config.ENV == "production":
            raise SystemExit(f"Sofia cannot start: {exc}") from exc
        log.error("Database check failed: %s", exc)

    # -- blueprints -------------------------------------------------------
    from app.routes.public import bp as public_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.account import bp as account_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.api import bp as api_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(account_bp, url_prefix="/account")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")

    from app.routes.webhooks import bp as webhooks_bp
    app.register_blueprint(webhooks_bp, url_prefix="/webhooks")

    _register_hooks(app)
    _register_context(app)
    _register_errors(app)

    log.info("Sofia ready (env=%s, debug=%s)", Config.ENV, Config.DEBUG)
    return app


# --------------------------------------------------------------------------- #
#  Request hooks
# --------------------------------------------------------------------------- #
def _register_hooks(app: Flask) -> None:
    from app.auth_service import load_current_user, load_current_admin

    @app.before_request
    def _bootstrap():
        g.current_user = load_current_user()
        g.current_admin = load_current_admin()

        # CSRF: double-submit token in the session, checked on every unsafe
        # method. Skipped for /api routes, which carry it in a header.
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)

        # Gateways have no session and no CSRF token. Webhooks are instead
        # authenticated by HMAC signature inside the handler, which is a
        # stronger check than CSRF, not a weaker one.
        if request.path.startswith("/webhooks/"):
            return

        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = (
                request.form.get("csrf_token")
                or request.headers.get("X-CSRF-Token")
                or ""
            )
            if not secrets.compare_digest(sent, session.get("csrf_token", "")):
                from flask import abort
                abort(400, description="Your session expired. Reload the page and try again.")

    @app.after_request
    def _headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self' https://checkout.paystack.com",
        )
        if Config.ENV == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


# --------------------------------------------------------------------------- #
#  Template globals
# --------------------------------------------------------------------------- #
def _register_context(app: Flask) -> None:
    from app import catalog

    # Cache-buster for CSS/JS. Uses the app's own mtime so a redeploy
    # changes it without anyone remembering to bump a version string.
    try:
        asset_version = str(int(os.path.getmtime(
            os.path.join(os.path.dirname(__file__), "static", "css", "sofia.css")
        )))
    except OSError:
        asset_version = "1"

    nav_groups = catalog.grouped_for_nav()

    @app.context_processor
    def _inject():
        from flask import session as flask_session
        return {
            "site_name": Config.SITE_NAME,
            "site_url": Config.SITE_URL,
            "current_year": datetime.now(timezone.utc).year,
            "current_user": getattr(g, "current_user", None),
            "current_admin": getattr(g, "current_admin", None),
            "csrf_token": flask_session.get("csrf_token", ""),
            "asset_version": asset_version,
            "nav_groups": nav_groups,
            "categories": catalog.CATEGORIES,
            "icons": catalog.ICONS,
            "signup_bonus": Config.SIGNUP_BONUS_CREDITS,
        }


# --------------------------------------------------------------------------- #
#  Errors
# --------------------------------------------------------------------------- #
def _register_errors(app: Flask) -> None:
    log = logging.getLogger("sofia.error")

    @app.errorhandler(404)
    def _404(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def _413(_e):
        from flask import jsonify
        msg = f"That file is larger than the {Config.MAX_UPLOAD_MB} MB limit."
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": msg}), 413
        return render_template("errors/500.html", error_id=None), 413

    @app.errorhandler(Exception)
    def _500(exc):
        from werkzeug.exceptions import HTTPException

        # A 4xx is the client's problem and already carries a usable message.
        # Re-raising here does NOT fall through to Flask's default handling —
        # Flask treats the raise as a new unhandled error and turns a tidy 400
        # into a 500, so an expired CSRF token used to surface as "something
        # went wrong on our side". Return the exception instead; Werkzeug
        # renders it as its own response.
        if isinstance(exc, HTTPException) and exc.code and exc.code < 500:
            if request.path.startswith("/api/"):
                from flask import jsonify
                return jsonify({
                    "status": "error",
                    "code": "bad_request" if exc.code == 400 else "http_error",
                    "message": exc.description or "That request could not be processed.",
                }), exc.code
            return exc

        error_id = secrets.token_hex(6)
        log.exception("Unhandled error [%s] on %s", error_id, request.path)

        if request.path.startswith("/api/"):
            from flask import jsonify
            return jsonify({
                "status": "error",
                "message": "Something went wrong on our side. Nothing was charged.",
                "errorId": error_id,
            }), 500

        return render_template("errors/500.html", error_id=error_id), 500

"""
Sofia — configuration.

Everything comes from the environment. Nothing secret has a default.
The production guard at the bottom refuses to boot on an unsafe config
rather than running quietly wrong, which is how the last deployment
turned a missing variable into a silent 500.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    """
    Minimal .env loader. cPanel's Python app manager sets env vars through
    its UI, but a plain .env keeps local dev and shared-host deploys the
    same. Deliberately dependency-free.
    """
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    # -- environment ------------------------------------------------------
    ENV = os.environ.get("SOFIA_ENV", "development").strip()
    DEBUG = _bool("SOFIA_DEBUG", False)
    SITE_NAME = os.environ.get("SOFIA_SITE_NAME", "Sofia")
    SITE_URL = os.environ.get("SOFIA_SITE_URL", "http://localhost:5000").rstrip("/")

    # -- secrets ----------------------------------------------------------
    SECRET_KEY = os.environ.get("SOFIA_SECRET_KEY", "")

    # -- database ---------------------------------------------------------
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = _int("DB_PORT", 3306)
    DB_NAME = os.environ.get("DB_NAME", "")
    DB_USER = os.environ.get("DB_USER", "")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_POOL_SIZE = _int("DB_POOL_SIZE", 5)

    # -- AI providers -----------------------------------------------------
    # Routing lives in app/ai/providers.py and is driven entirely by env, so
    # switching writer or scorer is one setting, not an edit to every engine.
    #
    #   SOFIA_ROLE_SCORING=deepseek:deepseek-v4-flash
    #   SOFIA_ROLE_WRITING=moonshot:kimi-k2.6
    #   SOFIA_ROLE_REASONING=deepseek:deepseek-v4-pro
    #   SOFIA_ROLE_FALLBACK=anthropic:claude-sonnet-4-6
    KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

    AI_TIMEOUT = _int("SOFIA_AI_TIMEOUT", _int("KIMI_TIMEOUT", 180))
    KIMI_TIMEOUT = AI_TIMEOUT                      # legacy name, same value

    # -- money ------------------------------------------------------------
    # One rate, one place. Every naira figure shown to a user or an admin is
    # derived from this, so a rate move is a single env change rather than a
    # hunt through templates.
    USD_NGN = _int("SOFIA_USD_NGN", 1580)

    # Credit costs per tool live in app/catalog.py. Package definitions and
    # gateway fees live in app/pricing.py. Neither belongs in this file.

    # -- uploads ----------------------------------------------------------
    MAX_UPLOAD_MB = _int("SOFIA_MAX_UPLOAD_MB", 8)
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    ALLOWED_UPLOAD_EXT = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".md"}

    # -- sessions ---------------------------------------------------------
    SESSION_COOKIE_NAME = "sofia_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = ENV == "production"
    SESSION_DAYS = _int("SOFIA_SESSION_DAYS", 30)
    ADMIN_SESSION_HOURS = _int("SOFIA_ADMIN_SESSION_HOURS", 8)

    # -- credits ----------------------------------------------------------
    ENFORCE_CREDITS = _bool("SOFIA_ENFORCE_CREDITS", True)
    SIGNUP_BONUS_CREDITS = _int("SOFIA_SIGNUP_BONUS", 3)

    # -- background jobs ----------------------------------------------------
    # Tool runs happen off the request thread so Passenger cannot time out
    # mid-generation. Keep WORKER_THREADS at or below DB_POOL_SIZE: a worker
    # borrows a connection to write its result, and starving the pool turns a
    # slow job into a failed one.
    WORKER_THREADS = _int("SOFIA_WORKER_THREADS", 4)
    # A job still 'running' after this long is presumed dead and refunded by
    # the sweeper. Must exceed KIMI_TIMEOUT with room for retries.
    JOB_STALE_MINUTES = _int("SOFIA_JOB_STALE_MINUTES", 15)

    # Credit packages moved to app/pricing.py — see PACKAGES there.

    # -- payments ---------------------------------------------------------
    # Two gateways: Monnify for Nigerian users (1% capped at ₦1,000, no flat
    # fee), Paystack for international cards. Routing is by user country and
    # lives in app/pricing.py.
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    MONNIFY_API_KEY = os.environ.get("MONNIFY_API_KEY", "")
    MONNIFY_SECRET_KEY = os.environ.get("MONNIFY_SECRET_KEY", "")
    MONNIFY_CONTRACT_CODE = os.environ.get("MONNIFY_CONTRACT_CODE", "")
    MONNIFY_BASE_URL = os.environ.get(
        "MONNIFY_BASE_URL", "https://sandbox.monnify.com")

    # -- mail -------------------------------------------------------------
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "no-reply@sofia.ng")

    # -- payments ---------------------------------------------------------
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")


def validate(cfg=Config) -> list[str]:
    """
    Returns a list of fatal problems. Empty list means safe to boot.
    Called by the app factory; in production a non-empty list stops the
    process instead of letting it serve broken pages.
    """
    problems: list[str] = []

    if not cfg.SECRET_KEY or len(cfg.SECRET_KEY) < 32:
        problems.append(
            "SOFIA_SECRET_KEY is missing or shorter than 32 chars. "
            "Generate one with: python -c \"import secrets;print(secrets.token_hex(32))\""
        )
    if not cfg.DB_NAME or not cfg.DB_USER:
        problems.append("DB_NAME and DB_USER must be set.")

    if cfg.ENV == "production":
        if cfg.DEBUG:
            problems.append("SOFIA_DEBUG=1 is not permitted in production.")
        if not cfg.KIMI_API_KEY:
            problems.append("KIMI_API_KEY is not set; every AI tool would fail.")
        if cfg.SITE_URL.startswith("http://"):
            problems.append("SOFIA_SITE_URL must be https in production.")

    return problems

"""
Sofia — AI provider registry and role routing.

The migration brief's central instruction: one place decides which provider
handles which kind of work, controlled by environment variables. Providers
are never hard-coded into engine code.

Roles, not models
-----------------
Engines ask for a *role* — "scoring", "writing", "reasoning" — and this
module resolves it to a provider and model. Changing the writer from Kimi to
DeepSeek is one env var, not an edit to seven engine functions.

    SOFIA_ROLE_SCORING=deepseek:deepseek-v4-flash
    SOFIA_ROLE_WRITING=moonshot:kimi-k2.6
    SOFIA_ROLE_REASONING=deepseek:deepseek-v4-pro
    SOFIA_ROLE_FALLBACK=anthropic:claude-sonnet-4-6

Transports
----------
Moonshot and DeepSeek are both OpenAI-compatible, so they share one
transport and differ only by base URL and key. Anthropic uses its own
message format, so it gets its own. Both are hidden behind `call()`.

Caching carries across all three: every provider here bills a repeated
system prefix at a large discount, which is why the prompt architecture
puts everything stable in the system message and everything variable in
the user message. That design does not change with the provider.
"""

from __future__ import annotations

import logging
import os

from config import Config

log = logging.getLogger("sofia.ai")


class AIError(Exception):
    """Raised for anything the caller should surface as a failed job."""

    def __init__(self, message: str, code: str = "ai_error"):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- #
#  Rates — USD per 1M tokens
# --------------------------------------------------------------------------- #
# Sourced from the migration brief (verified June 2026) and the Moonshot
# console (August 2026). These drive the cost figures in the admin panel and
# the user's usage dashboard. They are reporting, not billing — if a provider
# changes price, fix it here and the dashboards follow.
#
# `cached` is the rate for input tokens served from the provider's prompt
# cache. It is the single biggest lever in Sofia's unit economics.
RATES = {
    # Moonshot
    "kimi-k2.5":  {"in": 0.60, "out": 3.00,  "cached": 0.07},
    "kimi-k2.6":  {"in": 0.60, "out": 2.50,  "cached": 0.10},
    "kimi-k3":    {"in": 3.00, "out": 15.00, "cached": 0.30},
    # DeepSeek
    "deepseek-v4-flash": {"in": 0.14, "out": 0.28, "cached": 0.014},
    "deepseek-v4-pro":   {"in": 1.74, "out": 3.48, "cached": 0.17},
    # Anthropic — fallback only
    "claude-haiku-4-5":  {"in": 1.00, "out": 5.00,  "cached": 0.10},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00, "cached": 0.30},
}


# --------------------------------------------------------------------------- #
#  Providers
# --------------------------------------------------------------------------- #
PROVIDERS = {
    "moonshot": {
        "label": "Moonshot (Kimi)",
        "transport": "openai",
        "base_url": os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1"),
        "key_env": "KIMI_API_KEY",
    },
    "deepseek": {
        "label": "DeepSeek",
        "transport": "openai",
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "key_env": "DEEPSEEK_API_KEY",
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "transport": "anthropic",
        "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
        "key_env": "ANTHROPIC_API_KEY",
    },
}

_clients: dict[str, object] = {}


def _spec(value: str, default: str) -> tuple[str, str]:
    """Parse 'provider:model'. Falls back to the default on anything odd."""
    raw = (value or default).strip()
    if ":" not in raw:
        raw = default
    provider, _, model = raw.partition(":")
    if provider not in PROVIDERS:
        log.warning("Unknown provider %r in role config; using %s", provider, default)
        provider, _, model = default.partition(":")
    return provider, model


ROLES = {
    "scoring":   _spec(os.environ.get("SOFIA_ROLE_SCORING"),   "moonshot:kimi-k2.5"),
    "writing":   _spec(os.environ.get("SOFIA_ROLE_WRITING"),   "moonshot:kimi-k2.6"),
    "reasoning": _spec(os.environ.get("SOFIA_ROLE_REASONING"), "moonshot:kimi-k3"),
}

FALLBACK = _spec(os.environ.get("SOFIA_ROLE_FALLBACK"), "anthropic:claude-sonnet-4-6")

# The fallback is only worth having if it is a *different* provider. Falling
# back from Kimi to Kimi during a Moonshot outage achieves nothing.
FALLBACK_ENABLED = os.environ.get("SOFIA_AI_FALLBACK", "1") not in ("0", "false", "no")


def resolve(role: str) -> tuple[str, str]:
    if role not in ROLES:
        raise AIError(f"Unknown model role {role!r}.", code="bad_role")
    return ROLES[role]


def api_key(provider: str) -> str:
    return os.environ.get(PROVIDERS[provider]["key_env"], "")


def configured(provider: str) -> bool:
    return bool(api_key(provider))


def client(provider: str):
    """Lazily build and cache a client for the provider."""
    if provider in _clients:
        return _clients[provider]

    spec = PROVIDERS[provider]
    key = api_key(provider)
    if not key:
        raise AIError(
            f"{spec['label']} is not configured — set {spec['key_env']}.",
            code="no_api_key",
        )

    if spec["transport"] == "openai":
        from openai import OpenAI
        built = OpenAI(
            api_key=key,
            base_url=spec["base_url"],
            timeout=Config.AI_TIMEOUT,
            max_retries=0,           # retries and backoff are handled upstream
        )
    else:
        try:
            import anthropic
        except ImportError as exc:
            raise AIError(
                "The anthropic package is not installed, so the Claude "
                "fallback is unavailable.",
                code="no_fallback",
            ) from exc
        built = anthropic.Anthropic(
            api_key=key, timeout=Config.AI_TIMEOUT, max_retries=0
        )

    _clients[provider] = built
    return built


def estimate_cost(model: str, tokens_in: int, tokens_out: int, cached: int = 0) -> float:
    rate = RATES.get(model)
    if not rate:
        return 0.0
    fresh_in = max(0, (tokens_in or 0) - (cached or 0))
    return round(
        (fresh_in / 1_000_000) * rate["in"]
        + ((cached or 0) / 1_000_000) * rate["cached"]
        + ((tokens_out or 0) / 1_000_000) * rate["out"],
        6,
    )


def describe() -> dict:
    """Current routing, for the admin panel and `manage.py check-ai`."""
    return {
        "roles": {
            role: {
                "provider": provider,
                "model": model,
                "configured": configured(provider),
                "rates": RATES.get(model),
            }
            for role, (provider, model) in ROLES.items()
        },
        "fallback": {
            "provider": FALLBACK[0],
            "model": FALLBACK[1],
            "enabled": FALLBACK_ENABLED,
            "configured": configured(FALLBACK[0]),
        },
    }

"""
Sofia — the AI call layer.

Engines call `complete(role="writing", ...)`. This module resolves the role
to a provider, makes the call, checks the answer is usable, and — if it is
not — retries on the fallback provider so a user never sees a failure caused
by one vendor having a bad day.

Kept at module name `kimi` because that is what the engines import, but it
is no longer Moonshot-specific. The routing table lives in `providers.py`.

Why there is a quality gate
---------------------------
The migration brief is explicit that the savings only hold if quality holds,
and names the check that matters most: Sofia must never emit "estimate",
"approximately" or "roughly" in front of a figure. That rule is not
cosmetic — it is the visible edge of the Evidence Tiering Protocol, and a
model that breaks it produces a document that misrepresents how solid its
numbers are.

A response is therefore rejected, and retried on the fallback, when it is
empty, truncated, unparseable in the requested shape, or hedges a figure.
Cheap by default, correct when it matters.
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.ai.providers import (AIError, FALLBACK, FALLBACK_ENABLED, PROVIDERS,
                              RATES, client, configured, estimate_cost, resolve)
from config import Config

log = logging.getLogger("sofia.ai")

# All hedge words, for reporting.
_HEDGE = re.compile(
    r"\b(estimated?|est\.|approximately|approx\.|roughly|around|circa|ballpark)\b",
    re.IGNORECASE,
)

# A hedge is only a defect when it is quantitative. "Roughly speaking" in
# prose is harmless; "roughly ₦4m" is exactly what we are banning.
# Up to two short connecting words are allowed between the hedge and the
# figure, so "estimated at $50,000" and "roughly in the region of ₦4m" are
# both caught, while a hedge in unrelated prose two sentences away is not.
_HEDGED_FIGURE = re.compile(
    r"\b(estimated?|est\.|approximately|approx\.|roughly|around|circa)\b"
    r"(?:\s+\w{1,5}){0,3}\s*\S{0,3}[\d₦$€£]",
    re.IGNORECASE,
)


class QualityRejection(Exception):
    """Raised internally when a response fails a gate. Never reaches the user."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --------------------------------------------------------------------------- #
#  Quality gates
# --------------------------------------------------------------------------- #
def check_text(text: str, *, min_chars: int = 40) -> None:
    if not text or not text.strip():
        raise QualityRejection("empty response")
    if len(text.strip()) < min_chars:
        raise QualityRejection(f"response too short ({len(text.strip())} chars)")

    hedged = _HEDGED_FIGURE.search(text)
    if hedged:
        raise QualityRejection(f"hedged figure: {hedged.group(0)!r}")

    if text.count("```") % 2 == 1:
        raise QualityRejection("unclosed code fence — likely truncated")


def hedge_hits(text: str) -> list[str]:
    """Every hedge word present. Used by the admin quality report."""
    return sorted({m.group(0).lower() for m in _HEDGE.finditer(text or "")})


# --------------------------------------------------------------------------- #
#  Transports
# --------------------------------------------------------------------------- #
def _call_openai(provider, model, system, user, temperature, max_tokens):
    response = client(provider).chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    usage = response.usage

    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0
    else:
        # Moonshot reports the cache hit under its own key on some versions.
        cached = getattr(usage, "cached_tokens", 0) or 0

    return (choice.message.content or ""), {
        "tokens_in": getattr(usage, "prompt_tokens", 0) or 0,
        "tokens_out": getattr(usage, "completion_tokens", 0) or 0,
        "tokens_cached": cached,
        "finish_reason": getattr(choice, "finish_reason", None),
    }


def _call_anthropic(provider, model, system, user, temperature, max_tokens):
    response = client(provider).messages.create(
        model=model,
        system=[{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = "".join(
        block.text for block in response.content
        if getattr(block, "type", "") == "text"
    )
    usage = response.usage
    return text, {
        "tokens_in": getattr(usage, "input_tokens", 0) or 0,
        "tokens_out": getattr(usage, "output_tokens", 0) or 0,
        "tokens_cached": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "finish_reason": getattr(response, "stop_reason", None),
    }


_TRANSPORTS = {"openai": _call_openai, "anthropic": _call_anthropic}


def _attempt(provider, model, system, user, temperature, max_tokens, attempts):
    """One provider, with backoff on transient errors. Raises AIError."""
    from openai import APIError, APITimeoutError, RateLimitError

    transport = _TRANSPORTS[PROVIDERS[provider]["transport"]]
    last: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return transport(provider, model, system, user, temperature, max_tokens)

        except RateLimitError as exc:
            last = exc
            if attempt == attempts:
                raise AIError("The AI service is busy.", code="rate_limited") from exc
            time.sleep(min(2 ** attempt, 8))

        except APITimeoutError as exc:
            last = exc
            if attempt == attempts:
                raise AIError("The AI service timed out.", code="timeout") from exc
            time.sleep(1.5 * attempt)

        except APIError as exc:
            last = exc
            status = getattr(exc, "status_code", None)
            if status and 400 <= status < 500 and status != 429:
                raise AIError("The AI service rejected the request.",
                              code="bad_request") from exc
            if attempt == attempts:
                raise AIError("The AI service is unavailable.",
                              code="upstream") from exc
            time.sleep(1.5 * attempt)

        except AIError:
            raise                                     # config errors: do not retry

        except Exception as exc:                      # transport-agnostic
            last = exc
            if attempt == attempts:
                raise AIError("The AI service failed.", code="upstream") from exc
            time.sleep(1.0 * attempt)

    raise AIError("The AI service failed.", code="upstream") from last


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #
def complete(
    *,
    system: str,
    user: str,
    role: str = "writing",
    model: str | None = None,
    temperature: float = 0.6,
    max_tokens: int = 4000,
    attempts: int = 3,
    gate: bool = True,
) -> tuple[str, dict]:
    """
    Returns (text, usage).

    `system` must be the stable prefix. Nothing request-specific goes in it,
    or the provider's prompt cache stops hitting and input cost rises roughly
    tenfold.
    """
    provider, routed_model = resolve(role)
    model = model or routed_model
    started = time.monotonic()
    reason = None

    try:
        text, raw = _attempt(provider, model, system, user,
                             temperature, max_tokens, attempts)
        if gate:
            check_text(text)
        used_provider, used_model, fell_back = provider, model, False

    except (AIError, QualityRejection) as first_error:
        reason = (getattr(first_error, "reason", None)
                  or getattr(first_error, "code", "error"))

        usable_fallback = (
            FALLBACK_ENABLED
            and configured(FALLBACK[0])
            and (FALLBACK[0], FALLBACK[1]) != (provider, model)
        )
        if not usable_fallback:
            if isinstance(first_error, QualityRejection):
                raise AIError(
                    "The generated document did not pass our quality checks.",
                    code="quality_gate",
                ) from first_error
            raise

        log.warning("Role %s on %s:%s failed (%s) — falling back to %s:%s",
                    role, provider, model, reason, FALLBACK[0], FALLBACK[1])

        text, raw = _attempt(FALLBACK[0], FALLBACK[1], system, user,
                             temperature, max_tokens, attempts=2)
        if gate:
            # If the fallback also fails the gate, the prompt is at fault
            # rather than the provider. Failing the job is correct — it
            # refunds the user instead of handing them a hedged document.
            try:
                check_text(text)
            except QualityRejection as exc:
                raise AIError(
                    "The generated document did not pass our quality checks.",
                    code="quality_gate",
                ) from exc
        used_provider, used_model, fell_back = FALLBACK[0], FALLBACK[1], True

    usage = {
        "provider": used_provider,
        "model": used_model,
        "role": role,
        "fell_back": fell_back,
        "fallback_reason": reason if fell_back else None,
        "duration_ms": int((time.monotonic() - started) * 1000),
        **raw,
    }
    usage["cost_usd"] = estimate_cost(
        used_model, usage["tokens_in"], usage["tokens_out"], usage["tokens_cached"]
    )
    return text, usage


def complete_json(
    *,
    system: str,
    user: str,
    role: str = "scoring",
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4000,
    required_keys: tuple[str, ...] = (),
) -> tuple[dict, dict]:
    """
    Machine mode. Returns (data, usage).

    Parsed defensively: providers differ in how enthusiastically they wrap
    JSON in prose or fences, and a silently missing key fails later and
    further away than a parse error does.
    """
    text, usage = complete(
        system=system, user=user, role=role, model=model,
        temperature=temperature, max_tokens=max_tokens, gate=False,
    )

    data = _parse_json(text)
    shape_ok = data is not None and (
        not required_keys or all(k in data for k in required_keys)
    )

    if not shape_ok:
        log.warning("JSON shape failure on %s; retrying on fallback",
                    usage.get("model"))

        if FALLBACK_ENABLED and configured(FALLBACK[0]):
            data2, usage2 = _retry_json(system, user, max_tokens)
            if data2 is not None:
                data = data2
            usage["fell_back"] = True
            usage["fallback_reason"] = "json_shape"
            for key in ("tokens_in", "tokens_out", "tokens_cached"):
                usage[key] = (usage.get(key) or 0) + (usage2.get(key) or 0)
            usage["cost_usd"] = round(
                (usage.get("cost_usd") or 0) + (usage2.get("cost_usd") or 0), 6
            )

    if data is None:
        raise AIError("The AI returned an unreadable response.", code="bad_json")
    return data, usage


def _retry_json(system: str, user: str, max_tokens: int) -> tuple[dict | None, dict]:
    text, usage = complete(
        system=system,
        user=user + "\n\nReturn ONLY the JSON object. No prose, no code fences.",
        role="scoring", model=FALLBACK[1],
        temperature=0.0, max_tokens=max_tokens, gate=False,
    )
    return _parse_json(text), usage


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned,
                         flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None

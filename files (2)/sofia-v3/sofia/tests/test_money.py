"""Pricing arithmetic, gateway routing, payment idempotency, and the quality gate."""
import hashlib, hmac, json, pytest

from app import pricing, payments, usage
from app.ai import kimi, providers
from app.credits import balance
from app.db import execute, query_one


# ------------------------------------------------------------------ pricing --
def test_every_package_matches_the_financial_analysis():
    expected = {                       # id: (credits, price kobo, strike kobo)
        "starter":       (50,   250_000,   480_000),
        "pro":           (200,  450_000, 1_000_000),
        "business-500":  (500, 1_000_000, 1_800_000),
        "business-1000": (1000, 2_000_000, 3_500_000),
    }
    for pkg in pricing.PACKAGES:
        credits, amount, strike = expected[pkg["id"]]
        assert (pkg["credits"], pkg["amount_minor"], pkg["strike_minor"]) == \
               (credits, amount, strike), pkg["id"]


def test_per_credit_rate_falls_as_packages_grow():
    rates = [pricing.per_credit_minor(p) for p in pricing.PACKAGES]
    assert rates == sorted(rates, reverse=True), "a bigger pack must never cost more per credit"


def test_monnify_beats_paystack_on_every_local_price_point():
    """
    The whole reason for the dual gateway. The analysis puts the saving at
    ₦113-₦200 per sale; assert the direction and the order of magnitude
    rather than exact kobo, which move with rounding.
    """
    for pkg in pricing.PACKAGES:
        local = pricing.gateway_fee(pkg["amount_minor"], "monnify")
        card = int(pkg["amount_minor"] * 0.015) + 10_000   # Paystack local
        saving_naira = (card - local) / 100
        assert 100 <= saving_naira <= 220, (pkg["id"], saving_naira)


def test_monnify_fee_is_capped():
    assert pricing.gateway_fee(50_000_000, "monnify") == 100_000   # ₦1,000 cap


def test_gateway_routing():
    assert pricing.gateway_for("NG") == "monnify"
    assert pricing.gateway_for("Nigeria") == "monnify"
    assert pricing.gateway_for("GB") == "paystack"
    assert pricing.gateway_for(None) == "paystack"      # safe default


def test_fees_are_integers():
    for pkg in pricing.PACKAGES:
        for gw in ("monnify", "paystack"):
            assert isinstance(pricing.gateway_fee(pkg["amount_minor"], gw), int)


def test_margin_is_healthy_at_measured_kimi_cost():
    """
    At Kimi's rates the analysis's cost-per-credit collapses. Every package
    should clear 60% margin — versus 27-49% on Claude pricing.
    """
    for pkg in pricing.PACKAGES:
        m = pricing.margin(pkg, ai_cost_usd_per_credit=0.0020, gateway="monnify")
        assert m["margin_pct"] > 60, (pkg["id"], m)
        assert m["net_minor"] > 0


# ----------------------------------------------------------------- payments --
def _pending(user, package_id="pro", reference="sofia_test_ref"):
    pkg = pricing.package(package_id)
    execute(
        "INSERT INTO payments (user_id, provider, provider_ref, package_id, credits, "
        "amount_minor, currency, status) VALUES (%s,'paystack',%s,%s,%s,%s,'NGN','initiated')",
        (user["id"], reference, package_id, pkg["credits"], pkg["amount_minor"]),
    )
    return reference, pkg


def _signed(body: dict, secret: str) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    return raw, hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()


def test_webhook_grants_credits_once(user, monkeypatch):
    monkeypatch.setattr("config.Config.PAYSTACK_SECRET_KEY", "sk_test_secret")
    execute("UPDATE users SET credits = 0 WHERE id = %s", (user["id"],))
    reference, pkg = _pending(user)

    raw, sig = _signed({"event": "charge.success",
                        "data": {"reference": reference,
                                 "amount": pkg["amount_minor"]}}, "sk_test_secret")

    assert payments.paystack_webhook(raw, sig) is True
    assert balance(user["id"]) == pkg["credits"]

    # Gateways retry. The retry must be a no-op, not a second grant.
    assert payments.paystack_webhook(raw, sig) is False
    assert balance(user["id"]) == pkg["credits"]


def test_webhook_rejects_bad_signature(user, monkeypatch):
    monkeypatch.setattr("config.Config.PAYSTACK_SECRET_KEY", "sk_test_secret")
    execute("UPDATE users SET credits = 0 WHERE id = %s", (user["id"],))
    reference, pkg = _pending(user)
    raw, _ = _signed({"event": "charge.success",
                      "data": {"reference": reference,
                               "amount": pkg["amount_minor"]}}, "sk_test_secret")

    with pytest.raises(payments.PaymentError) as exc:
        payments.paystack_webhook(raw, "deadbeef")
    assert exc.value.code == "bad_signature"
    assert balance(user["id"]) == 0


def test_webhook_rejects_amount_mismatch(user, monkeypatch):
    """A client that can propose the price can propose one kobo."""
    monkeypatch.setattr("config.Config.PAYSTACK_SECRET_KEY", "sk_test_secret")
    execute("UPDATE users SET credits = 0 WHERE id = %s", (user["id"],))
    reference, _ = _pending(user)
    raw, sig = _signed({"event": "charge.success",
                        "data": {"reference": reference, "amount": 100}},
                       "sk_test_secret")

    assert payments.paystack_webhook(raw, sig) is False
    assert balance(user["id"]) == 0
    assert query_one("SELECT status FROM payments WHERE provider_ref=%s",
                     (reference,))["status"] == "mismatch"


def test_webhook_ignores_other_events(user, monkeypatch):
    monkeypatch.setattr("config.Config.PAYSTACK_SECRET_KEY", "sk_test_secret")
    reference, _ = _pending(user)
    raw, sig = _signed({"event": "charge.failed",
                        "data": {"reference": reference}}, "sk_test_secret")
    assert payments.paystack_webhook(raw, sig) is False


def test_monnify_webhook_grants(user, monkeypatch):
    monkeypatch.setattr("config.Config.MONNIFY_SECRET_KEY", "mk_test_secret")
    execute("UPDATE users SET credits = 0 WHERE id = %s", (user["id"],))
    reference, pkg = _pending(user, "starter", "sofia_mon_ref")

    raw, sig = _signed({"eventType": "SUCCESSFUL_TRANSACTION",
                        "eventData": {"paymentReference": reference,
                                      "amountPaid": pkg["amount_minor"] / 100}},
                       "mk_test_secret")
    assert payments.monnify_webhook(raw, sig) is True
    assert balance(user["id"]) == pkg["credits"]


def test_webhook_endpoint_is_csrf_exempt(client, monkeypatch):
    """A gateway has no session and no token; HMAC is the auth instead."""
    monkeypatch.setattr("config.Config.PAYSTACK_SECRET_KEY", "sk_test_secret")
    raw, sig = _signed({"event": "charge.success",
                        "data": {"reference": "nope", "amount": 1}}, "sk_test_secret")
    r = client.post("/webhooks/paystack", data=raw,
                    headers={"X-Paystack-Signature": sig,
                             "Content-Type": "application/json"})
    assert r.status_code == 200          # not 400 — CSRF did not block it


# ------------------------------------------------------- routing / quality --
def test_roles_resolve_to_a_provider_and_model():
    for role in ("scoring", "writing", "reasoning"):
        provider, model = providers.resolve(role)
        assert provider in providers.PROVIDERS
        assert model


def test_unknown_provider_falls_back_to_default():
    assert providers._spec("nonsense:x", "moonshot:kimi-k2.6") == ("moonshot", "kimi-k2.6")
    assert providers._spec("", "moonshot:kimi-k2.6") == ("moonshot", "kimi-k2.6")


def test_deepseek_flash_is_far_cheaper_than_sonnet():
    flash = providers.estimate_cost("deepseek-v4-flash", 2500, 1000)
    sonnet = providers.estimate_cost("claude-sonnet-4-6", 2500, 1000)
    assert sonnet / flash > 30


def test_cache_hits_cut_input_cost():
    cold = providers.estimate_cost("kimi-k2.6", 10_000, 1000, cached=0)
    warm = providers.estimate_cost("kimi-k2.6", 10_000, 1000, cached=9_000)
    assert warm < cold


def test_quality_gate_rejects_hedged_figures():
    for bad in ["Revenue was approximately ₦4,000,000 last year.",
                "We serve roughly 1,200 farms across the region today.",
                "Costs are estimated at $50,000 for the first phase."]:
        with pytest.raises(kimi.QualityRejection):
            kimi.check_text(bad)


def test_quality_gate_allows_hedges_that_are_not_figures():
    kimi.check_text("Roughly speaking, the strategy holds. " * 3)


def test_quality_gate_rejects_empty_and_truncated():
    with pytest.raises(kimi.QualityRejection):
        kimi.check_text("")
    with pytest.raises(kimi.QualityRejection):
        kimi.check_text("x" * 200 + "\n```python\nunclosed")


def test_quality_gate_passes_clean_output():
    kimi.check_text("Revenue was ₦4,000,000 in FY2025, verified against the "
                    "audited accounts filed in March 2026.")


def test_json_parser_survives_fences_and_prose():
    assert kimi._parse_json('```json\n{"a":1}\n```') == {"a": 1}
    assert kimi._parse_json('Here you go: {"a": 1} — hope that helps') == {"a": 1}
    assert kimi._parse_json("not json at all") is None


# -------------------------------------------------------------- dashboard --
def test_usage_dashboard_shape(user):
    data = usage.dashboard(user["id"], days=30)
    assert set(data) == {"summary", "daily", "by_tool", "by_engine", "ledger"}
    assert len(data["daily"]) == 30              # gap-filled, no holes
    assert all("date" in d and "credits" in d for d in data["daily"])


def test_usage_page_renders(client, user):
    r = client.post("/auth/login", data={
        "email": "test@sofia.ng", "password": "Str0ngPassw0rd!",
        "csrf_token": _login_csrf(client)}, follow_redirects=True)
    assert r.status_code == 200
    page = client.get("/account/usage")
    assert page.status_code == 200
    assert b"Credit usage" in page.data


def _login_csrf(client):
    client.get("/auth/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")

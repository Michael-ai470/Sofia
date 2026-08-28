"""
Sofia — payments. Monnify for Nigeria, Paystack for everyone else.

Three rules, each learned from someone else's incident report:

1. **Credits are granted by the webhook, not the browser redirect.**
   A user who closes the tab after paying must still get what they bought.
   The redirect is a convenience for the user; the webhook is the record.

2. **Webhooks are idempotent.** Both gateways retry. The `payments` table
   has a unique key on `reference`, and crediting is guarded by a status
   transition that only one caller can win. A retry is a no-op, not a
   second grant.

3. **Signatures are verified before anything is read.** An unverified
   credit-granting endpoint is a free-credits API. Both checks are
   constant-time.

The amount is re-checked against our own package definition on verification.
Never trust a returned amount — a client that can propose the price can
propose one kobo.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from app import pricing
from app.credits import grant
from app.db import connection, execute, query_one
from config import Config

log = logging.getLogger("sofia.payments")


class PaymentError(Exception):
    def __init__(self, message: str, code: str = "payment_error"):
        super().__init__(message)
        self.code = code


def _post(url: str, payload: dict, headers: dict, timeout: int = 25) -> dict:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", **headers,
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        log.error("Gateway %s returned %s: %s", url, exc.code, detail)
        raise PaymentError("The payment provider rejected the request.",
                           code="gateway_error") from exc
    except Exception as exc:
        log.error("Gateway %s unreachable: %s", url, exc)
        raise PaymentError("Could not reach the payment provider.",
                           code="gateway_unreachable") from exc


def _get(url: str, headers: dict, timeout: int = 25) -> dict:
    request = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception as exc:
        log.error("Gateway %s unreachable: %s", url, exc)
        raise PaymentError("Could not reach the payment provider.",
                           code="gateway_unreachable") from exc


def new_reference() -> str:
    return f"sofia_{secrets.token_urlsafe(18)}"


# --------------------------------------------------------------------------- #
#  Initiating
# --------------------------------------------------------------------------- #
def initiate(user: dict, package_id: str, callback_url: str) -> dict:
    """
    Create a pending payment and return the URL to send the user to.

    The row is written before the gateway is called. If the gateway call
    fails we have an abandoned pending row, which is harmless; the reverse
    order risks a paid transaction with nothing on our side to match it to.
    """
    pkg = pricing.package(package_id)
    if not pkg:
        raise PaymentError("That package does not exist.", code="bad_package")

    gateway = pricing.gateway_for(user.get("country"))
    reference = new_reference()

    execute(
        "INSERT INTO payments (user_id, provider, provider_ref, package_id, "
        "credits, amount_minor, currency, status) "
        "VALUES (%s,%s,%s,%s,%s,%s,'NGN','initiated')",
        (user["id"], gateway, reference, package_id,
         pkg["credits"], pkg["amount_minor"]),
    )

    if gateway == "monnify":
        checkout = _monnify_init(user, pkg, reference, callback_url)
    else:
        checkout = _paystack_init(user, pkg, reference, callback_url)

    log.info("Payment %s initiated for user %s via %s (%s)",
             reference, user["id"], gateway, pricing.naira(pkg["amount_minor"]))
    return {"reference": reference, "gateway": gateway, "checkout_url": checkout}


def _paystack_init(user, pkg, reference, callback_url) -> str:
    if not Config.PAYSTACK_SECRET_KEY:
        raise PaymentError("Card payments are not configured.", code="not_configured")

    data = _post(
        "https://api.paystack.co/transaction/initialize",
        {
            "email": user["email"],
            "amount": pkg["amount_minor"],
            "currency": "NGN",
            "reference": reference,
            "callback_url": callback_url,
            "metadata": {"user_id": user["id"], "package_id": pkg["id"],
                         "credits": pkg["credits"]},
        },
        {"Authorization": f"Bearer {Config.PAYSTACK_SECRET_KEY}"},
    )
    if not data.get("status"):
        raise PaymentError(data.get("message") or "Could not start the payment.")
    return data["data"]["authorization_url"]


def _monnify_token() -> str:
    if not (Config.MONNIFY_API_KEY and Config.MONNIFY_SECRET_KEY):
        raise PaymentError("Bank transfer is not configured.", code="not_configured")
    basic = base64.b64encode(
        f"{Config.MONNIFY_API_KEY}:{Config.MONNIFY_SECRET_KEY}".encode()
    ).decode()
    data = _post(f"{Config.MONNIFY_BASE_URL}/api/v1/auth/login", {},
                 {"Authorization": f"Basic {basic}"})
    if not data.get("requestSuccessful"):
        raise PaymentError("Could not authenticate with the payment provider.")
    return data["responseBody"]["accessToken"]


def _monnify_init(user, pkg, reference, callback_url) -> str:
    token = _monnify_token()
    data = _post(
        f"{Config.MONNIFY_BASE_URL}/api/v1/merchant/transactions/init-transaction",
        {
            "amount": pkg["amount_minor"] / 100,      # Monnify wants major units
            "customerName": user.get("full_name") or user["email"],
            "customerEmail": user["email"],
            "paymentReference": reference,
            "paymentDescription": f"Sofia {pkg['label']} — {pkg['credits']} credits",
            "currencyCode": "NGN",
            "contractCode": Config.MONNIFY_CONTRACT_CODE,
            "redirectUrl": callback_url,
            "paymentMethods": ["ACCOUNT_TRANSFER", "CARD", "USSD"],
        },
        {"Authorization": f"Bearer {token}"},
    )
    if not data.get("requestSuccessful"):
        raise PaymentError(data.get("responseMessage") or "Could not start the payment.")
    return data["responseBody"]["checkoutUrl"]


# --------------------------------------------------------------------------- #
#  Crediting — the one place credits are granted from a payment
# --------------------------------------------------------------------------- #
def _settle(reference: str, amount_minor: int, gateway: str) -> bool:
    """
    Mark paid and grant credits, exactly once.

    Returns True if this call was the one that credited the account, False if
    it had already been settled. Both are success from the caller's point of
    view — a duplicate webhook is not an error.
    """
    row = query_one(
        "SELECT id, user_id, package_id, credits, amount_minor, status "
        "FROM payments WHERE provider_ref = %s", (reference,)
    )
    if not row:
        log.warning("Webhook for unknown reference %s", reference)
        return False

    if row["status"] == "successful":
        return False                                    # already settled

    # Never trust the amount the gateway echoes back — compare with what we
    # recorded when we created the intent.
    if int(amount_minor) != int(row["amount_minor"]):
        log.error("Amount mismatch on %s: gateway said %s, we expected %s",
                  reference, amount_minor, row["amount_minor"])
        execute("UPDATE payments SET status='mismatch' WHERE id=%s", (row["id"],))
        return False

    # Claim it. Only one concurrent caller can move pending -> paid.
    with connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE payments SET status='successful', provider=%s, "
                "settled_at=NOW() WHERE id=%s AND status='initiated'",
                (gateway, row["id"]),
            )
            claimed = cur.rowcount == 1
        finally:
            cur.close()

    if not claimed:
        return False

    grant(row["user_id"], row["credits"],
          reason=f"purchase:{row['package_id']}", reference=reference)
    log.info("Payment %s settled — %d credits to user %s",
             reference, row["credits"], row["user_id"])
    return True


# --------------------------------------------------------------------------- #
#  Webhooks
# --------------------------------------------------------------------------- #
def paystack_webhook(raw_body: bytes, signature: str) -> bool:
    if not Config.PAYSTACK_SECRET_KEY:
        raise PaymentError("Not configured.", code="not_configured")

    expected = hmac.new(Config.PAYSTACK_SECRET_KEY.encode(),
                        raw_body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise PaymentError("Invalid signature.", code="bad_signature")

    event = json.loads(raw_body.decode())
    if event.get("event") != "charge.success":
        return False

    data = event.get("data") or {}
    return _settle(data.get("reference", ""), data.get("amount", 0), "paystack")


def monnify_webhook(raw_body: bytes, signature: str) -> bool:
    if not Config.MONNIFY_SECRET_KEY:
        raise PaymentError("Not configured.", code="not_configured")

    expected = hmac.new(Config.MONNIFY_SECRET_KEY.encode(),
                        raw_body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise PaymentError("Invalid signature.", code="bad_signature")

    event = json.loads(raw_body.decode())
    data = event.get("eventData") or {}
    if event.get("eventType") != "SUCCESSFUL_TRANSACTION":
        return False

    amount_minor = int(round(float(data.get("amountPaid", 0)) * 100))
    return _settle(data.get("paymentReference", ""), amount_minor, "monnify")


# --------------------------------------------------------------------------- #
#  Redirect verification
# --------------------------------------------------------------------------- #
def verify(reference: str) -> dict:
    """
    Called when the user lands back on the site.

    This does not replace the webhook — it makes the page truthful for a user
    who is watching. If the webhook has already landed, this reads the settled
    row. If it has not, it asks the gateway directly and settles, so a slow
    webhook does not leave someone staring at "pending" after they have paid.
    """
    row = query_one(
        "SELECT provider_ref, provider, status, credits, package_id, amount_minor "
        "FROM payments WHERE provider_ref = %s", (reference,)
    )
    if not row:
        raise PaymentError("We have no record of that payment.", code="not_found")

    if row["status"] == "successful":
        return {"status": "paid", "credits": row["credits"],
                "package_id": row["package_id"]}

    try:
        if row["provider"] == "paystack":
            data = _get(f"https://api.paystack.co/transaction/verify/{reference}",
                        {"Authorization": f"Bearer {Config.PAYSTACK_SECRET_KEY}"})
            body = data.get("data") or {}
            if body.get("status") == "success":
                _settle(reference, body.get("amount", 0), "paystack")
        else:
            token = _monnify_token()
            data = _get(
                f"{Config.MONNIFY_BASE_URL}/api/v2/transactions/"
                f"{urllib.parse.quote(reference, safe='')}",
                {"Authorization": f"Bearer {token}"},
            )
            body = data.get("responseBody") or {}
            if body.get("paymentStatus") == "PAID":
                _settle(reference,
                        int(round(float(body.get("amountPaid", 0)) * 100)),
                        "monnify")
    except PaymentError:
        # The gateway being unreachable does not mean the payment failed.
        # Leave it pending; the webhook is the backstop.
        log.warning("Could not verify %s with the gateway; leaving pending",
                    reference)

    fresh = query_one("SELECT status, credits, package_id FROM payments "
                      "WHERE provider_ref = %s", (reference,))
    return {
        "status": "paid" if fresh["status"] == "successful" else fresh["status"],
        "credits": fresh["credits"],
        "package_id": fresh["package_id"],
    }

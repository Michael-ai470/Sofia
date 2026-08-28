"""
Sofia — payment gateway webhooks.

These are the only endpoints that grant credits from a payment. They are
exempt from CSRF (a gateway has no session and no token) and are instead
protected by HMAC signature verification, which is stronger.

Both handlers return 200 for anything they successfully processed, including
events they chose to ignore. Gateways retry on non-200, and retrying an event
we have deliberately skipped achieves nothing but noise. A 400 is reserved
for a bad signature, which is the one case worth shouting about.
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from app import payments

log = logging.getLogger("sofia.webhooks")

bp = Blueprint("webhooks", __name__)


@bp.route("/paystack", methods=["POST"])
def paystack():
    try:
        credited = payments.paystack_webhook(
            request.get_data(), request.headers.get("X-Paystack-Signature", "")
        )
    except payments.PaymentError as exc:
        if exc.code == "bad_signature":
            log.warning("Rejected Paystack webhook: bad signature from %s",
                        request.remote_addr)
            return jsonify({"status": "rejected"}), 400
        log.error("Paystack webhook error: %s", exc)
        return jsonify({"status": "error"}), 200
    except Exception:
        # Never 500 at a gateway. It will retry the same broken event for
        # hours and bury the log while it does.
        log.exception("Unhandled Paystack webhook failure")
        return jsonify({"status": "error"}), 200

    return jsonify({"status": "credited" if credited else "ignored"}), 200


@bp.route("/monnify", methods=["POST"])
def monnify():
    try:
        credited = payments.monnify_webhook(
            request.get_data(), request.headers.get("monnify-signature", "")
        )
    except payments.PaymentError as exc:
        if exc.code == "bad_signature":
            log.warning("Rejected Monnify webhook: bad signature from %s",
                        request.remote_addr)
            return jsonify({"status": "rejected"}), 400
        log.error("Monnify webhook error: %s", exc)
        return jsonify({"status": "error"}), 200
    except Exception:
        log.exception("Unhandled Monnify webhook failure")
        return jsonify({"status": "error"}), 200

    return jsonify({"status": "credited" if credited else "ignored"}), 200

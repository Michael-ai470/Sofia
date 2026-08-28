"""
Sofia — the tool execution API.

One endpoint starts every tool; a second reports on it.

    POST /api/run/<slug>   validate -> charge -> enqueue -> 202
    GET  /api/job/<id>     running | success | error

The model call happens on a worker thread. Passenger closes a request long
before a long document finishes generating, so anything that waits inline
fails on exactly the tools worth the most credits.

Charging happens in the request, before the handoff, so the user learns
immediately whether they could afford the run. Refunds happen in the worker
and in the sweeper, and both are idempotent.
"""

from __future__ import annotations

import json
import logging

from flask import Blueprint, g, jsonify, request

from flask import session

from app import catalog, engines, worker
from app.auth_service import client_ip, rate_limited
from app.credits import CreditError, open_job
from app.db import query_one
from app.extract import ExtractError, from_upload
from config import Config

# Anonymous users have no user_id to authorise a poll against, so the job's
# public_id is kept in their session. Bounded, because a session cookie that
# grows without limit eventually stops being sent.
_ANON_JOBS_KEY = "anon_jobs"
_ANON_JOBS_MAX = 20

log = logging.getLogger("sofia.api")
bp = Blueprint("api", __name__)


def _fail(message: str, status: int = 400, code: str = "bad_request", **extra):
    return jsonify({"status": "error", "code": code, "message": message, **extra}), status


def _collect_inputs(tool: dict) -> dict:
    """
    Build the input dict from the multipart form.

    For file_or_text fields the file wins when present, otherwise the pasted
    text is used. Extraction happens here so a bad upload fails before any
    credit is charged.
    """
    values: dict[str, str] = {}

    for field in tool.get("inputs", []):
        key = field["key"]
        ftype = field.get("type")

        if ftype == "multifile":
            uploads = [f for f in request.files.getlist(key) if f and f.filename]
            if not uploads and field.get("required"):
                raise ExtractError(f"{field['label']} is required.")
            texts = []
            for index, upload in enumerate(uploads[:20], start=1):
                texts.append(f"--- Document {index}: {upload.filename} ---\n"
                             + from_upload(upload))
            values[key] = "\n\n".join(texts)

        elif ftype == "file_or_text":
            upload = request.files.get(key)
            if upload and upload.filename:
                values[key] = from_upload(upload)
            else:
                pasted = (request.form.get(f"{key}_text") or "").strip()
                if not pasted and field.get("required"):
                    raise ExtractError(
                        f"{field['label']} is required — upload a file or paste the text."
                    )
                values[key] = pasted

        else:
            value = (request.form.get(key) or "").strip()
            if not value and field.get("required"):
                raise ExtractError(f"{field['label']} is required.")
            values[key] = value

    return values


@bp.route("/run/<slug>", methods=["POST"])
def run(slug):
    tool = catalog.get(slug)
    if not tool:
        return _fail("No such tool.", 404, "not_found")
    if tool["status"] != "live":
        return _fail(f"{tool['name']} is not available yet.", 409, "not_live")

    user = g.current_user

    # Anonymous users get a tighter limit than signed-in ones. The free
    # analysis tool is the obvious target for someone scraping the API.
    bucket = f"run:{user['id']}" if user else f"run_anon:{client_ip()}"
    limit = 40 if user else 5
    if rate_limited(bucket, limit=limit, window_seconds=3600):
        return _fail(
            "You have run a lot of tools in the last hour. Try again shortly."
            if user else
            "Free runs are limited. Create an account to keep going.",
            429, "rate_limited",
        )

    # ---- validate and extract, BEFORE charging --------------------------
    try:
        inputs = _collect_inputs(tool)
    except ExtractError as exc:
        return _fail(str(exc), 400, "bad_input")

    # ---- charge ---------------------------------------------------------
    # Still synchronous, and deliberately so. The user must know before they
    # leave this request whether they could afford the run.
    try:
        job = open_job(
            user, tool, client_ip(),
            inputs_summary={k: len(v or "") for k, v in inputs.items()},
        )
    except CreditError as exc:
        return _fail(str(exc), exc.status, "insufficient_credits")

    # ---- hand off -------------------------------------------------------
    # The model call runs off this thread. A twelve-section business plan can
    # take minutes, and Passenger will not hold a request open that long.
    if user is None:
        owned = session.get(_ANON_JOBS_KEY, [])
        owned.append(job["public_id"])
        session[_ANON_JOBS_KEY] = owned[-_ANON_JOBS_MAX:]

    worker.submit(job, tool, inputs)

    return jsonify({
        "status": "running",
        "jobId": job["public_id"],
        "creditsCharged": job["credits_charged"],
        "pollUrl": f"/api/job/{job['public_id']}",
    }), 202


def _may_view(row: dict) -> bool:
    """A job is readable by its owner, or by the browser that started it."""
    if row["user_id"] is not None:
        return bool(g.current_user) and g.current_user["id"] == row["user_id"]
    return row["public_id"] in session.get(_ANON_JOBS_KEY, [])


@bp.route("/job/<public_id>")
def job_status(public_id):
    """
    Poll a running job.

    Returns 200 in every normal case, including failure — the HTTP status
    describes the poll, not the job. A client that has to distinguish "the
    poll failed" from "the job failed" is a client that will show the wrong
    message at some point.
    """
    row = query_one(
        "SELECT public_id, user_id, tool, status, credits_charged, output_json, "
        "error_code, error_id FROM jobs WHERE public_id = %s",
        (public_id,),
    )
    if not row or not _may_view(row):
        return _fail("No such job.", 404, "not_found")

    if row["status"] in ("pending", "running"):
        return jsonify({"status": "running", "jobId": public_id})

    if row["status"] in ("failed", "refunded"):
        refunded = row["status"] == "refunded"
        return jsonify({
            "status": "error",
            "jobId": public_id,
            "code": row["error_code"] or "failed",
            "message": _MESSAGES.get(
                row["error_code"],
                "That run did not complete." + (
                    " Your credits have been returned." if refunded else ""
                ),
            ),
            "errorId": row["error_id"],
            "refunded": refunded,
        })

    output = row["output_json"]
    if isinstance(output, (str, bytes)):
        output = json.loads(output)
    payload = dict(output or {})
    if payload.get("kind") == "document" and payload.get("markdown"):
        payload["html"] = engines.render_markdown(payload["markdown"])

    from app.credits import balance
    return jsonify({
        "status": "success",
        "jobId": public_id,
        "creditsCharged": row["credits_charged"],
        "creditsRemaining": balance(g.current_user["id"]) if g.current_user else None,
        "downloads": _download_links(public_id, payload),
        "result": payload,
    })


def _download_links(public_id: str, payload: dict) -> list[dict]:
    """Export formats offered for this result. Empty for non-document output."""
    if payload.get("kind") != "document" or not payload.get("markdown"):
        return []
    return [
        {"format": "pdf",  "label": "Download PDF",
         "url": f"/account/job/{public_id}/download.pdf"},
        {"format": "docx", "label": "Download Word",
         "url": f"/account/job/{public_id}/download.docx"},
    ]


_MESSAGES = {
    "no_api_key": "The AI service is not configured. Contact support.",
    "timeout": "That took longer than expected and was stopped. "
               "Your credits have been returned — please try again.",
    "rate_limited": "The AI service is busy. Your credits have been returned.",
    "stalled": "That run was interrupted and your credits have been returned.",
    "internal": "Something went wrong and your credits were returned.",
}


@bp.route("/me")
def me():
    if not g.current_user:
        return jsonify({"authenticated": False})
    return jsonify({
        "authenticated": True,
        "email": g.current_user["email"],
        "credits": g.current_user["credits"],
        "plan": g.current_user["plan"],
    })

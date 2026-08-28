"""
End-to-end through HTTP: POST returns 202, polling reports running then
success, and the finished job downloads as PDF and Word.

The Kimi call is stubbed — api.moonshot.ai is not reachable from CI and the
point here is the plumbing, not the model.
"""
import io, json, time, zipfile, threading
import pytest

from app import engines, worker
from app.db import execute, query_one
from app.credits import balance


@pytest.fixture
def logged_in(client, user):
    execute("UPDATE users SET credits = 50 WHERE id = %s", (user["id"],))
    r = client.post("/auth/login", data={
        "email": "test@sofia.ng", "password": "Str0ngPassw0rd!",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert r.status_code == 200
    return user


_PLAN_FIELDS = {
    "business_name": "Acme Farms",
    "industry": "Agritech",
    "country": "Nigeria",
    "stage": "Revenue-generating",
    "funding_amount": "50,000,000",
    "use_of_funds": "Working capital and hiring",
    "description": "We supply inputs and offtake services to smallholder farms.",
}


def _csrf(client):
    client.get("/auth/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")


def _stub_engine(monkeypatch, delay=0.0, markdown="# Plan\n\nBody text.\n"):
    def fake_run(tool, inputs):
        if delay:
            time.sleep(delay)
        return ({"kind": "document", "title": "Growth Plan", "markdown": markdown},
                {"model": "kimi-k2.6", "tokens_in": 100, "tokens_out": 200,
                 "tokens_cached": 80, "cost_usd": 0.001, "duration_ms": 10})
    monkeypatch.setattr(engines, "run", fake_run)


def _wait(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/job/{job_id}").get_json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("job never finished")


# ------------------------------------------------------------------ enqueue --
def test_run_returns_202_immediately(client, logged_in, monkeypatch):
    _stub_engine(monkeypatch, delay=1.5)
    token = _csrf(client)

    started = time.time()
    r = client.post("/api/run/business-plan",
                    data={"csrf_token": token, **_PLAN_FIELDS},
                    headers={"X-CSRF-Token": token})
    elapsed = time.time() - started

    assert r.status_code == 202, r.get_json()
    body = r.get_json()
    assert body["status"] == "running" and body["jobId"]
    # The point of the whole change: the request returns long before the work
    assert elapsed < 1.0, f"request blocked for {elapsed:.2f}s"

    assert _wait(client, body["jobId"])["status"] == "success"


def test_poll_reports_success_and_charges_once(client, logged_in, monkeypatch):
    _stub_engine(monkeypatch)
    token = _csrf(client)
    r = client.post("/api/run/business-plan",
                    data={"csrf_token": token, **_PLAN_FIELDS},
                    headers={"X-CSRF-Token": token})
    body = _wait(client, r.get_json()["jobId"])

    assert body["status"] == "success"
    assert body["result"]["markdown"].startswith("# Plan")
    assert "<h2>Plan</h2>" in body["result"]["html"]
    from app import catalog
    cost = catalog.get("business-plan")["credits"]
    assert balance(logged_in["id"]) == 50 - cost   # charged exactly once
    assert {d["format"] for d in body["downloads"]} == {"pdf", "docx"}


def test_engine_failure_refunds_and_reports(client, logged_in, monkeypatch):
    def boom(tool, inputs):
        raise engines.EngineError("Sector is required.", code="missing_input")
    monkeypatch.setattr(engines, "run", boom)

    token = _csrf(client)
    r = client.post("/api/run/business-plan",
                    data={"csrf_token": token, **_PLAN_FIELDS},
                    headers={"X-CSRF-Token": token})
    body = _wait(client, r.get_json()["jobId"])

    assert body["status"] == "error"
    assert body["refunded"] is True
    assert balance(logged_in["id"]) == 50          # fully returned


# -------------------------------------------------------------- ownership --
def test_another_user_cannot_poll_your_job(client, logged_in, monkeypatch, app):
    _stub_engine(monkeypatch)
    token = _csrf(client)
    job_id = client.post("/api/run/business-plan",
                         data={"csrf_token": token, **_PLAN_FIELDS},
                         headers={"X-CSRF-Token": token}).get_json()["jobId"]
    _wait(client, job_id)

    stranger = app.test_client()
    assert stranger.get(f"/api/job/{job_id}").status_code == 404
    assert stranger.get(f"/account/job/{job_id}/download.pdf").status_code == 404


def test_csrf_required(client, logged_in):
    r = client.post("/api/run/business-plan", data=dict(_PLAN_FIELDS))
    assert r.status_code in (400, 403)


# --------------------------------------------------------------- download --
def test_downloads_are_valid_files(client, logged_in, monkeypatch):
    _stub_engine(monkeypatch, markdown="# Growth Plan\n\n| A | B |\n|---|---|\n| 1 | 2 |\n")
    token = _csrf(client)
    job_id = client.post("/api/run/business-plan",
                         data={"csrf_token": token, **_PLAN_FIELDS},
                         headers={"X-CSRF-Token": token}).get_json()["jobId"]
    _wait(client, job_id)

    pdf = client.get(f"/account/job/{job_id}/download.pdf")
    assert pdf.status_code == 200
    assert pdf.data[:5] == b"%PDF-"
    assert "attachment" in pdf.headers["Content-Disposition"]
    assert pdf.headers["Cache-Control"] == "private, no-store"

    docx = client.get(f"/account/job/{job_id}/download.docx")
    assert docx.status_code == 200
    with zipfile.ZipFile(io.BytesIO(docx.data)) as z:
        assert z.testzip() is None


def test_anonymous_free_run_owns_its_own_job(client, monkeypatch):
    """No account, but the browser that started it may still poll and download."""
    monkeypatch.setattr(engines, "run", lambda t, i: (
        {"kind": "document", "title": "CV review", "markdown": "# Review\n\nGood."},
        {"model": "kimi-k2.5"}))
    token = _csrf(client)
    r = client.post("/api/run/cv-analysis",
                    data={"csrf_token": token, "cv_text": "Experienced engineer. " * 30},
                    headers={"X-CSRF-Token": token})
    assert r.status_code == 202
    body = _wait(client, r.get_json()["jobId"])
    assert body["status"] == "success"
    assert client.get(f"/account/job/{body['jobId']}/download.pdf").status_code == 200

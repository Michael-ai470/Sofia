"""Test fixtures — runs against a real MySQL, not a mock."""
import os, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "SOFIA_ENV": "development", "SOFIA_DEBUG": "0",
    "SOFIA_SECRET_KEY": "t" * 64,
    "DB_HOST": "127.0.0.1", "DB_PORT": "3306", "DB_NAME": "sofia_test",
    "DB_USER": "sofia", "DB_PASSWORD": "sofia", "DB_POOL_SIZE": "10",
    "KIMI_API_KEY": "test-key", "SOFIA_ENFORCE_CREDITS": "1",
    "SOFIA_SIGNUP_BONUS": "5", "SOFIA_JOB_STALE_MINUTES": "15",
})

import pytest
from app import create_app
from app.db import execute, query_one


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(autouse=True)
def clean():
    for table in ("credit_ledger", "jobs", "sessions", "password_resets",
                  "rate_limits", "audit_log", "users"):
        execute(f"DELETE FROM {table}")
    yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user():
    from app.auth_service import create_user
    u = create_user(email="test@sofia.ng", password="Str0ngPassw0rd!",
                    full_name="Test User", country="NG")
    return query_one("SELECT * FROM users WHERE id = %s", (u["id"],))

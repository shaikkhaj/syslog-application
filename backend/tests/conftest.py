"""Shared test fixtures.

Environment variables are set BEFORE any application import so that the
settings/engine used by the app point at a throwaway SQLite database and
the network listeners stay disabled during tests.
"""

import os
import pathlib
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="syslog_platform_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR.replace(chr(92), '/')}/test.db"
os.environ["SYSLOG_LISTENERS_ENABLED"] = "false"
# Intentionally unreachable so the health check exercises the error path.
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """Boot the full application (DB init + pipeline) and yield a test client."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_ready():
    """Ensure tables exist and the event type catalog is seeded (idempotent)."""
    from app.db.init_db import init_db
    from app.syslog.event_types import resolver

    init_db()
    resolver.invalidate()
    return True


@pytest.fixture()
def db_session(db_ready):
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session

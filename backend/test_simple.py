import os
import sys
import tempfile

# Set env BEFORE importing app
_TMP_DIR = tempfile.mkdtemp(prefix="syslog_platform_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR.replace(chr(92), '/')}/test.db"
os.environ["SYSLOG_LISTENERS_ENABLED"] = "false"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
os.environ["LOG_LEVEL"] = "WARNING"

print("Step 1: env set", flush=True)

from fastapi.testclient import TestClient
print("Step 2: TestClient imported", flush=True)

from app.main import app
print("Step 3: app imported", flush=True)

print("Step 4: Creating TestClient...", flush=True)
with TestClient(app) as client:
    print("Step 5: TestClient created, making request...", flush=True)
    response = client.get("/api/v1/health")
    print(f"Step 6: Status: {response.status_code}", flush=True)
    print(f"Step 7: Body: {response.json()}", flush=True)
print("Done!", flush=True)
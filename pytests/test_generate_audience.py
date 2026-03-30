import os
# Ensure test-mode bypasses external LLMs and heavy daemons before importing app
os.environ.setdefault("ANNASEO_TESTING", "1")

import sys, pathlib
# Ensure project root is on sys.path so `from main import app` works under pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app
from jobqueue.connection import pipeline_queue

client = TestClient(app)


def register_and_get_token(email="smoke@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "name": "Smoke", "password": "pass"})
    if r.status_code == 400 and isinstance(r.json(), dict) and r.json().get("detail") == "Already registered":
        # Already registered from previous runs — fall back to login
        r2 = client.post("/api/auth/login", data={"username": email, "password": "pass"})
        assert r2.status_code == 200, r2.text
        return r2.json().get("access_token")

    assert r.status_code == 200, r.text
    return r.json().get("access_token")


@app.get("/_pytest_force_error")
def _pytest_force_error():
    raise RuntimeError("forced global exception path")


def test_global_exception_handler_code():
    r = client.get("/_pytest_force_error")
    assert r.status_code == 500, r.text
    body = r.json()
    assert body.get("code") == "INTERNAL_SERVER_ERROR"
    assert body.get("error") is True
    assert body.get("path") == "/_pytest_force_error"


def test_health_endpoint_content():
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "database" in data
    assert "queue_ready" in data
    assert "redis" in data
    assert "memory" in data


def test_ki_run_queue_unavailable():
    # In local test mode with no redis, pipeline_queue should be unavailable and route should fail fast.
    if pipeline_queue is None:
        resp = client.post("/api/ki/proj_x/run", json={"execution_mode": "multi_step"})
        assert resp.status_code in (401, 503), resp.text
        if resp.status_code == 503:
            assert "Queue unavailable" in resp.json().get("detail", "")
    else:
        # If queue is available, we can at least ensure API path responds and does not crash.
        resp = client.post("/api/ki/proj_x/run", json={"execution_mode": "multi_step"})
        assert resp.status_code in (200, 401, 422, 503)


def test_generate_audience_flow():
    token = register_and_get_token()
    headers = {"Authorization": f"Bearer {token}"}

    proj = {"name": "Test Project", "industry": "general", "seed_keywords": ["widget", "gadget"]}
    r = client.post("/api/projects", json=proj, headers=headers)
    assert r.status_code == 200, r.text
    pid = r.json().get("project_id")

    r = client.post(f"/api/strategy/{pid}/generate-audience", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "personas" in data and "products" in data
    assert isinstance(data["personas"], list)
    assert isinstance(data["products"], list)

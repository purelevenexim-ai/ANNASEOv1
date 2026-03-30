import os, sys, pathlib, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app, get_db

client = TestClient(app)


def register_token(email, name="User"):
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": "pass"})
    if r.status_code == 400 and r.json().get("detail") == "Already registered":
        r2 = client.post("/api/auth/login", data={"username": email, "password": "pass"})
        assert r2.status_code == 200, r2.text
        return r2.json()["access_token"]
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_project_list_returns_object():
    token = register_token("jobtracker-user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    project = {"name": "Tracker Test", "industry": "education", "seed_keywords": ["course content"], "description": "test"}
    r = client.post("/api/projects", json=project, headers=headers)
    assert r.status_code == 200
    project_id = r.json().get("project_id")

    r = client.get("/api/projects", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert "projects" in body
    assert any(p.get("project_id") == project_id for p in body["projects"])


def test_strategy_job_create_and_status():
    token = register_token("jobtracker-strategy@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    project = {"name": "Strategy Job", "industry": "education", "seed_keywords": ["learning plan"], "description": "test"}
    r = client.post("/api/projects", json=project, headers=headers)
    assert r.status_code == 200
    project_id = r.json().get("project_id")

    payload = {"pillar": "online education", "language": "english", "region": "india", "max_retries": 1, "execution_mode": "multi_step"}
    r = client.post(f"/api/strategy/{project_id}/jobs/create", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("job_id")
    job_id = data["job_id"]

    r = client.get(f"/api/strategy/{project_id}/jobs/{job_id}", headers=headers)
    assert r.status_code == 200, r.text
    status = r.json().get("status")
    assert status in ["queued", "running", "completed", "failed", "partial_success"]


def test_job_tracker_lock_acquire_release():
    from services import job_tracker
    db = get_db()
    job_id = f"test_lock_{int(time.time()*1000)}"
    project_id = "proj_test_lock"
    job_tracker.create_strategy_job(db, job_id, project_id, job_type="generic", input_payload={"foo": "bar"})

    assert job_tracker.acquire_job_lock(db, job_id) is True
    assert job_tracker.acquire_job_lock(db, job_id) is False
    job = job_tracker.get_strategy_job(db, job_id)
    assert job["is_locked"] is True

    job_tracker.release_job_lock(db, job_id)
    job = job_tracker.get_strategy_job(db, job_id)
    assert job["is_locked"] is False

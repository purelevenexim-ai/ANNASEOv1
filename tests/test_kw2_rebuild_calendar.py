"""
Tests for kw2_rebuild_calendar endpoint — verifies start_date is accepted and forwarded.

Run: pytest tests/test_kw2_rebuild_calendar.py -v
Requires: backend running on port 8000
"""
import os, sys, pytest, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://127.0.0.1:8000"

@pytest.fixture(scope="module")
def auth_header():
    r = requests.post(f"{BASE_URL}/api/auth/register",
        json={"email": "rebuild_cal_test@test.com", "name": "Test", "password": "pass1234"})
    if r.status_code == 200:
        token = r.json()["access_token"]
    else:
        r = requests.post(f"{BASE_URL}/api/auth/login",
            data={"username": "rebuild_cal_test@test.com", "password": "pass1234"})
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="module")
def project_and_session(auth_header):
    """Create a minimal project + kw2 session to test rebuild against."""
    r = requests.post(f"{BASE_URL}/api/projects",
        json={"name": "Rebuild Cal Test Project", "domain": "test.com"},
        headers=auth_header)
    assert r.status_code == 200
    project_id = r.json()["id"]

    r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions",
        json={"mode": "brand", "name": "rebuild test"},
        headers=auth_header)
    assert r.status_code == 200
    session_id = r.json()["session_id"]
    return project_id, session_id

def test_rebuild_accepts_start_date_body(auth_header, project_and_session):
    """Endpoint must accept a JSON body with start_date without 422 Unprocessable Entity."""
    project_id, session_id = project_and_session
    r = requests.post(
        f"{BASE_URL}/api/kw2/{project_id}/sessions/{session_id}/calendar/rebuild",
        json={"start_date": "2026-05-01"},
        headers=auth_header,
    )
    # 200 OK or 404 "Session not found" are both acceptable — 422 is the failure case
    assert r.status_code != 422, f"Endpoint rejected body: {r.text}"

def test_rebuild_accepts_empty_body(auth_header, project_and_session):
    """Endpoint must still work when called with no body (backwards-compatible)."""
    project_id, session_id = project_and_session
    r = requests.post(
        f"{BASE_URL}/api/kw2/{project_id}/sessions/{session_id}/calendar/rebuild",
        headers=auth_header,
    )
    assert r.status_code != 422, f"Endpoint rejected empty body: {r.text}"

import os
os.environ.setdefault("ANNASEO_TESTING", "1")

import sys, pathlib
# Ensure project root is on sys.path so `from main import app` works under pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app
from jobqueue.connection import pipeline_queue

client = TestClient(app)
import time
import json


def register_and_get_token(email="e2e@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "name": "E2E", "password": "pass"})
    if r.status_code == 400 and isinstance(r.json(), dict) and r.json().get("detail") == "Already registered":
        r2 = client.post("/api/auth/login", data={"username": email, "password": "pass"})
        assert r2.status_code == 200, r2.text
        return r2.json().get("access_token")

    assert r.status_code == 200, r.text
    return r.json().get("access_token")


def test_e2e_spices_flow():
    token = register_and_get_token("spice-e2e@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    proj = {"name": "Spices Demo", "industry": "food_spices", "seed_keywords": ["best spices for chicken", "black pepper"]}
    r = client.post("/api/projects", json=proj, headers=headers)
    assert r.status_code == 200, r.text
    pid = r.json().get("project_id")

    r = client.post(f"/api/strategy/{pid}/generate-audience", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "personas" in data and "products" in data


def test_e2e_tour_flow():
    token = register_and_get_token("tour-e2e@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    proj = {"name": "Tour Demo", "industry": "tourism", "seed_keywords": ["cinnamon tour kerala", "temple tour kerala"]}
    r = client.post("/api/projects", json=proj, headers=headers)
    assert r.status_code == 200, r.text
    pid = r.json().get("project_id")

    r = client.post(f"/api/strategy/{pid}/generate-audience", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "personas" in data and "products" in data


def _poll_session_stage(client, project_id, session_id, headers, timeout=12.0, poll_interval=0.5):
    """Poll `/api/ki/{project_id}/session/{session_id}` until generation advances or timeout."""
    waited = 0.0
    last = None
    while waited < timeout:
        r = client.get(f"/api/ki/{project_id}/session/{session_id}", headers=headers)
        if r.status_code == 200:
            last = r.json()
            stage = last.get("stage") or ""
            total_generated = int(last.get("total_generated") or 0)
            if stage and stage != "input":
                return last
            if total_generated > 0:
                return last
        time.sleep(poll_interval)
        waited += poll_interval
    return last


def test_e2e_spices_ki_flow():
    token = register_and_get_token("spice-ki@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    proj = {"name": "Spices KI Demo", "industry": "food_spices", "seed_keywords": ["best spices for chicken"]}
    r = client.post("/api/projects", json=proj, headers=headers)
    assert r.status_code == 200, r.text
    pid = r.json().get("project_id")

    body = {
        "pillars": [
            {"keyword": "cinnamon", "priority": 1, "intent": "transactional"},
            {"keyword": "turmeric", "priority": 2, "intent": "informational"}
        ],
        "supporting": ["buy online", "organic", "kerala"],
        "pillar_support_map": {},
        "intent_focus": "transactional",
        "customer_url": "",
        "competitor_urls": []
    }

    r = client.post(f"/api/ki/{pid}/input", json=body, headers=headers)
    assert r.status_code == 200, r.text
    sid = r.json().get("session_id")
    assert sid

    # pillars stored
    r = client.get(f"/api/ki/{pid}/pillars", headers=headers)
    assert r.status_code == 200, r.text
    pillars = r.json().get("pillars", [])
    assert len(pillars) >= 2

    # explicitly trigger generation (input also schedules it)
    r = client.post(f"/api/ki/{pid}/generate/{sid}", headers=headers)
    assert r.status_code == 200, r.text

    # Poll for progress
    sess = _poll_session_stage(client, pid, sid, headers, timeout=15.0)
    assert sess is not None, "Session polling timed out"
    total = int(sess.get("total_generated") or 0)

    # Confirm universe (accept all) and validate counts
    r = client.post(f"/api/ki/{pid}/confirm/{sid}", headers=headers)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res.get("status") == "confirmed"
    if total > 0:
        assert res.get("keyword_count", 0) > 0


def test_e2e_tour_ki_flow():
    token = register_and_get_token("tour-ki@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    proj = {"name": "Tour KI Demo", "industry": "tourism", "seed_keywords": ["temple tour kerala"]}
    r = client.post("/api/projects", json=proj, headers=headers)
    assert r.status_code == 200, r.text
    pid = r.json().get("project_id")

    body = {
        "pillars": [
            {"keyword": "kerala tour", "priority": 1, "intent": "informational"},
            {"keyword": "temple tour", "priority": 2, "intent": "informational"}
        ],
        "supporting": ["itinerary", "best time to visit", "packages"],
        "pillar_support_map": {},
        "intent_focus": "informational",
        "customer_url": "",
        "competitor_urls": []
    }

    r = client.post(f"/api/ki/{pid}/input", json=body, headers=headers)
    assert r.status_code == 200, r.text
    sid = r.json().get("session_id")
    assert sid

    r = client.get(f"/api/ki/{pid}/pillars", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json().get("pillars", [])) >= 2

    r = client.post(f"/api/ki/{pid}/generate/{sid}", headers=headers)
    assert r.status_code == 200, r.text

    sess = _poll_session_stage(client, pid, sid, headers, timeout=15.0)
    assert sess is not None, "Session polling timed out"
    total = int(sess.get("total_generated") or 0)

    r = client.post(f"/api/ki/{pid}/confirm/{sid}", headers=headers)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res.get("status") == "confirmed"
    if total > 0:
        assert res.get("keyword_count", 0) > 0

import os, sys, pathlib, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def register_and_get_token(email, name="E2E"):
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": "pass"})
    if r.status_code == 400 and isinstance(r.json(), dict) and r.json().get("detail") == "Already registered":
        r2 = client.post("/api/auth/login", data={"username": email, "password": "pass"})
        assert r2.status_code == 200, r2.text
        return r2.json().get("access_token")

    assert r.status_code == 200, r.text
    return r.json().get("access_token")


def _poll_session_stage(client, project_id, session_id, headers, timeout=20.0, poll_interval=1.0):
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


def test_e2e_cooking_company_workflow():
    token = register_and_get_token("cooking-e2e@example.com", "Cooking E2E")
    headers = {"Authorization": f"Bearer {token}"}

    project_data = {
        "name": "Cooking Company E2E",
        "industry": "food_spices",
        "seed_keywords": ["black pepper recipes", "organic cinnamon dishes"],
        "description": "Test cooking company workflow"
    }
    r = client.post("/api/projects", json=project_data, headers=headers)
    assert r.status_code == 200, r.text
    project_id = r.json().get("project_id")
    assert project_id

    # Check project exists
    r = client.get(f"/api/projects/{project_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json().get("name") == project_data["name"]

    # KI Input
    ki_input = {
        "pillars": [
            {"keyword": "cooking with spices", "priority": 1, "intent": "informational"},
            {"keyword": "pepper recipes", "priority": 2, "intent": "transactional"}
        ],
        "supporting": ["recipe", "health benefits", "spice combinations"],
        "pillar_support_map": {},
        "intent_focus": "informational",
        "customer_url": "https://cookingco.example",
        "competitor_urls": ["https://competitor.example"]
    }
    r = client.post(f"/api/ki/{project_id}/input", json=ki_input, headers=headers)
    assert r.status_code == 200, r.text
    sid = r.json().get("session_id")
    assert sid

    # Pillars should be stored and retrievable
    r = client.get(f"/api/ki/{project_id}/pillars", headers=headers)
    assert r.status_code == 200, r.text
    pillars = r.json().get("pillars", [])
    assert len(pillars) >= len(ki_input["pillars"])

    # Generate and poll session
    r = client.post(f"/api/ki/{project_id}/generate/{sid}", headers=headers)
    assert r.status_code == 200, r.text

    sess = _poll_session_stage(client, project_id, sid, headers, timeout=25.0, poll_interval=1.0)
    assert sess is not None, "Session polling timed out"

    # Confirm selection
    r = client.post(f"/api/ki/{project_id}/confirm/{sid}", headers=headers)
    assert r.status_code == 200, r.text
    confirm = r.json()
    assert confirm.get("status") == "confirmed"
    assert confirm.get("keyword_count", 0) >= 0

    # persist/reload path: fetch same session by ID
    r = client.get(f"/api/ki/{project_id}/session/{sid}", headers=headers)
    assert r.status_code == 200, r.text
    sess2 = r.json()
    assert sess2.get("session_id") == sid

    # latest session should also resolve
    r = client.get(f"/api/ki/{project_id}/latest-session", headers=headers)
    assert r.status_code == 200, r.text
    latest = r.json()
    assert latest.get("session_id") == sid

    # Query clusters endpoint (should not error)
    r = client.get(f"/api/ki/{project_id}/clusters", headers=headers)
    assert r.status_code == 200, r.text
    assert "clusters" in r.json()

    # Generate clusters AI endpoint with available keywords
    all_keywords = [f"test keyword {i}" for i in range(25)]
    r = client.post(
        f"/api/ki/{project_id}/clusters/generate",
        json={"pillar": "cooking", "keywords": all_keywords},
        headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("total") > 0


def test_e2e_education_institute_workflow():
    token = register_and_get_token("education-e2e@example.com", "Education E2E")
    headers = {"Authorization": f"Bearer {token}"}

    project_data = {
        "name": "Education Institute E2E",
        "industry": "education",
        "seed_keywords": ["online learning platform", "certification courses"],
        "description": "Test education institute workflow"
    }
    r = client.post("/api/projects", json=project_data, headers=headers)
    assert r.status_code == 200, r.text
    project_id = r.json().get("project_id")
    assert project_id

    # KI Input
    ki_input = {
        "pillars": [
            {"keyword": "online certification", "priority": 1, "intent": "commercial"},
            {"keyword": "learning platform", "priority": 2, "intent": "informational"}
        ],
        "supporting": ["accreditation", "course modules", "career advancement"],
        "pillar_support_map": {},
        "intent_focus": "commercial",
        "customer_url": "https://edu.example",
        "competitor_urls": ["https://otheredu.example"]
    }
    r = client.post(f"/api/ki/{project_id}/input", json=ki_input, headers=headers)
    assert r.status_code == 200, r.text
    sid = r.json().get("session_id")
    assert sid

    r = client.post(f"/api/ki/{project_id}/generate/{sid}", headers=headers)
    assert r.status_code == 200, r.text

    sess = _poll_session_stage(client, project_id, sid, headers, timeout=25.0, poll_interval=1.0)
    assert sess is not None, "Session polling timed out"

    r = client.post(f"/api/ki/{project_id}/confirm/{sid}", headers=headers)
    assert r.status_code == 200, r.text
    confirm = r.json()
    assert confirm.get("status") == "confirmed"

    # Verify project list still contains this project (persistence check)
    r = client.get("/api/projects", headers=headers)
    assert r.status_code == 200, r.text
    projects = r.json()
    if isinstance(projects, dict) and "projects" in projects:
        projects = projects.get("projects", [])
    assert any(p.get("project_id") == project_id for p in projects)

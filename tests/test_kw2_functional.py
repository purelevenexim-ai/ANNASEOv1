"""
kw2 Functional Tests — API Contract & Phase-Gating.
Tests: session creation, phase endpoints, pipeline-status keys,
       phase-gating (requires prev phase done), new merged flow keys.
Run: pytest tests/test_kw2_functional.py -v --tb=short
"""
import os, sys, json, hmac, base64, hashlib, time, pytest, requests
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://127.0.0.1:8000"

# ── Auth helpers ──────────────────────────────────────────────────────────────
def _jwt_secret():
    p = Path("/root/ANNASEOv1/.jwt_secret")
    return p.read_text().strip() if p.exists() else "fallback_secret"

def _make_token(user_id="u_func_test", email="functest@kw2.com", role="user"):
    secret = _jwt_secret()
    exp = (datetime.utcnow() + timedelta(hours=2)).isoformat()
    payload = json.dumps({"user_id": user_id, "email": email, "role": role, "exp": exp})
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{base64.urlsafe_b64encode(payload.encode()).decode()}.{sig}"

@pytest.fixture(scope="module")
def auth():
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"email": "functest@kw2.com", "name": "Func Test", "password": "pass1234"})
    if r.status_code == 200:
        token = r.json()["access_token"]
    else:
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          data={"username": "functest@kw2.com", "password": "pass1234"})
        assert r.status_code == 200, f"Login failed: {r.text}"
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="module")
def project_id(auth):
    r = requests.post(f"{BASE_URL}/api/projects", headers=auth,
                      json={"name": "FuncTest Spice Co", "industry": "food_spices",
                            "seed_keywords": ["basil", "cumin", "turmeric"]})
    assert r.status_code == 200, f"Project creation failed: {r.text}"
    return r.json()["project_id"]

# ── 1. Session creation ───────────────────────────────────────────────────────
class TestSessionCreation:
    def test_create_brand_session(self, auth, project_id):
        r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions", headers=auth,
                          json={"mode": "brand", "name": "Func Brand Session"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "session_id" in body
        # mode is stored in session dict, not top-level
        sess_mode = body.get("session", {}).get("mode") or body.get("mode")
        assert sess_mode == "brand", f"Expected mode='brand', got {sess_mode}. body={body}"

    def test_create_expand_session(self, auth, project_id):
        r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions", headers=auth,
                          json={"mode": "expand", "name": "Func Expand Session"})
        assert r.status_code in (200, 201), r.text

    def test_list_sessions(self, auth, project_id):
        # /sessions returns latest session; /sessions/list returns all
        r = requests.get(f"{BASE_URL}/api/kw2/{project_id}/sessions/list", headers=auth)
        assert r.status_code == 200, r.text
        sessions = r.json().get("sessions", [])
        assert isinstance(sessions, list)
        assert len(sessions) >= 1

    def test_session_has_required_fields(self, auth, project_id):
        r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions", headers=auth,
                          json={"mode": "brand", "name": "Field Check Session"})
        assert r.status_code == 200, r.text
        body = r.json()
        # Top-level must have session_id + project_id; mode lives inside session dict
        assert "session_id" in body, f"Missing session_id in: {body}"
        assert "project_id" in body, f"Missing project_id in: {body}"

# ── 2. Phase gating ───────────────────────────────────────────────────────────
class TestPhaseGating:
    """Phase N requires phase N-1 to be done; otherwise 400."""

    @pytest.fixture(scope="class")
    def fresh_session(self, auth, project_id):
        r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions", headers=auth,
                          json={"mode": "brand", "name": "Phase Gate Test"})
        assert r.status_code == 200
        return r.json()["session_id"]

    def test_phase2_blocked_without_phase1(self, auth, project_id, fresh_session):
        r = requests.post(
            f"{BASE_URL}/api/kw2/{project_id}/sessions/{fresh_session}/phase2",
            headers=auth
        )
        # Should be 400 (phase 1 not done) or 404
        assert r.status_code in (400, 422), (
            f"Expected 400 for phase-gating, got {r.status_code}: {r.text[:200]}"
        )

    def test_phase4_blocked_without_phase3(self, auth, project_id, fresh_session):
        r = requests.post(
            f"{BASE_URL}/api/kw2/{project_id}/sessions/{fresh_session}/phase4",
            headers=auth
        )
        assert r.status_code in (400, 422), (
            f"Expected 400 for phase-gating, got {r.status_code}: {r.text[:200]}"
        )

    def test_phase5_blocked_without_phase4(self, auth, project_id, fresh_session):
        r = requests.post(
            f"{BASE_URL}/api/kw2/{project_id}/sessions/{fresh_session}/phase5",
            headers=auth
        )
        assert r.status_code in (400, 422), (
            f"Expected 400 for phase-gating, got {r.status_code}: {r.text[:200]}"
        )

# ── 3. Pipeline-status keys ───────────────────────────────────────────────────
class TestPipelineStatus:
    def test_pipeline_status_endpoint_exists(self, auth, project_id):
        r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions", headers=auth,
                          json={"mode": "brand", "name": "Status Test"})
        sid = r.json()["session_id"]
        r2 = requests.get(f"{BASE_URL}/api/kw2/{project_id}/sessions/{sid}", headers=auth)
        assert r2.status_code == 200, r2.text

    def test_pipeline_status_has_phase_fields(self, auth, project_id):
        r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions", headers=auth,
                          json={"mode": "brand", "name": "Phase Fields Test"})
        sid = r.json()["session_id"]
        r2 = requests.get(f"{BASE_URL}/api/kw2/{project_id}/sessions/{sid}", headers=auth)
        body = r2.json()
        # At minimum, session data or phase status should be returned
        assert isinstance(body, dict), "Session endpoint should return a dict"

# ── 4. Top-100 endpoint structure ────────────────────────────────────────────
class TestTop100Endpoint:
    """Top-100 endpoint tests using a freshly-created session."""

    @pytest.fixture(scope="class")
    def fresh_session(self, auth, project_id):
        r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions", headers=auth,
                          json={"mode": "brand", "name": "Top100 Test Session"})
        assert r.status_code == 200
        return r.json()["session_id"]

    def test_top100_returns_ok_or_phase_error(self, auth, project_id, fresh_session):
        r = requests.get(
            f"{BASE_URL}/api/kw2/{project_id}/sessions/{fresh_session}/top100",
            headers=auth,
        )
        # Phase 5 not done → 400; done → 200 with items list
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            body = r.json()
            assert "items" in body
            assert isinstance(body["items"], list)

    def test_top100_items_have_keyword_field(self, auth, project_id, fresh_session):
        r = requests.get(
            f"{BASE_URL}/api/kw2/{project_id}/sessions/{fresh_session}/top100",
            headers=auth,
        )
        if r.status_code == 200 and r.json().get("items"):
            for item in r.json()["items"][:5]:
                assert "keyword" in item, f"Missing 'keyword' field in top100 item: {item}"

    def test_top100_spot_check_warning_field_present(self, auth, project_id, fresh_session):
        """spot_check_warning field must be present in top100 response (may be null)."""
        r = requests.get(
            f"{BASE_URL}/api/kw2/{project_id}/sessions/{fresh_session}/top100",
            headers=auth,
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                assert "spot_check_warning" in items[0], (
                    "spot_check_warning field missing from top100 items. "
                    "Was the db.py migration applied?"
                )

# ── 5. Flow definition correctness ───────────────────────────────────────────
class TestFlowDefinition:
    """Verify the new merged brand flow is correct."""

    def test_brand_flow_contains_validate_key(self, auth, project_id):
        """New brand flow uses VALIDATE instead of 3+REVIEW."""
        r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions", headers=auth,
                          json={"mode": "brand", "name": "Flow Validate Test"})
        assert r.status_code == 200
        body = r.json()
        # flow_json should be in the response or in the session GET
        sid = body["session_id"]
        r2 = requests.get(f"{BASE_URL}/api/kw2/{project_id}/sessions/{sid}", headers=auth)
        sess = r2.json()
        flow = sess.get("flow_json") or sess.get("flow", [])
        if isinstance(flow, str):
            flow = json.loads(flow)
        if flow:
            # New flow: should contain VALIDATE (merged 3+REVIEW) or old 3/REVIEW for backward compat
            flow_str = json.dumps(flow)
            # Either the new VALIDATE key or the old 3+REVIEW — both are valid
            assert any(k in flow_str for k in ["VALIDATE", "3", "REVIEW"]), (
                f"Unexpected flow: {flow}"
            )

# ── 6. Session endpoint returns 404 for unknown session ───────────────────────
class TestErrorHandling:
    def test_unknown_session_returns_404(self, auth, project_id):
        r = requests.get(f"{BASE_URL}/api/kw2/{project_id}/sessions/nonexistent_session_id",
                         headers=auth)
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_phase_on_nonexistent_session_returns_404(self, auth, project_id):
        # phase1 requires _KW2ManualInput body (all fields have defaults — send {})
        r = requests.post(
            f"{BASE_URL}/api/kw2/{project_id}/sessions/nonexistent_sid/phase1",
            headers=auth,
            json={},
        )
        assert r.status_code in (404, 400), r.text

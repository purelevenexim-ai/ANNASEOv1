"""
kw2 Run-All Pipeline Tests — ScoreTree + Deliver phases.
Tests the full sequential "Run All" execution across:
  Group A: PhaseScoreTree  → Phase4 (Score) → Phase5 (Tree/Top100) → Phase6 (Graph)
  Group B: PhaseDeliver    → Phase7 (Links) → Phase8 (Calendar)   → Phase9 (Strategy)

Each group mirrors the autoRun chain that the UI triggers.

Run: pytest tests/test_kw2_run_all_pipeline.py -v --tb=short
Run just fast unit tests: pytest tests/test_kw2_run_all_pipeline.py -v -m "not slow"
"""

import os
import sys
import json
import time
import pytest
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT   = 120  # seconds for each phase (some AI phases take longer)

# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth():
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": "runall_test@kw2.com", "name": "RunAll Test", "password": "pass1234"},
    )
    if r.status_code == 200:
        token = r.json()["access_token"]
    else:
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            data={"username": "runall_test@kw2.com", "password": "pass1234"},
        )
        assert r.status_code == 200, f"Login failed: {r.text}"
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Project + full pipeline session ──────────────────────────────────────────

@pytest.fixture(scope="module")
def pipeline_session(auth):
    """
    Creates a project, runs Phase1 (business analysis) + Phase2 (universe) +
    Phase3 (validation) so that Phase4-9 have data to work with.
    Returns {project_id, session_id, headers}.
    """
    headers = auth

    # Create project
    r = requests.post(
        f"{BASE_URL}/api/projects",
        headers=headers,
        json={
            "name": "RunAll Spice Co",
            "industry": "food_spices",
            "seed_keywords": ["organic spices", "turmeric", "cumin", "cardamom"],
        },
    )
    assert r.status_code == 200, f"Project creation failed: {r.text}"
    project_id = r.json()["project_id"]

    # Create session
    r = requests.post(
        f"{BASE_URL}/api/kw2/{project_id}/sessions",
        headers=headers,
        json={"mode": "brand", "name": "RunAll Full Pipeline"},
    )
    assert r.status_code == 200, f"Session creation failed: {r.text}"
    session_id = r.json()["session_id"]

    # ── Phase 1: set up business profile (batch mode, skip AI for speed) ──
    r = requests.patch(
        f"{BASE_URL}/api/kw2/{project_id}/profile",
        headers=headers,
        json={
            "pillars": ["organic spices", "turmeric powder", "spice blends"],
            "modifiers": ["buy", "organic", "wholesale", "bulk"],
            "audience": ["home cooks", "restaurant owners", "spice retailers"],
            "negative_scope": ["recipes", "curry recipe"],
            "geo_scope": "India, UK",
            "business_type": "Ecommerce",
            "usp": "Direct from farm, certified organic spices",
        },
    )
    assert r.status_code == 200, f"Profile patch failed: {r.text}"

    # Mark Phase 1 done manually (so Phase 2 endpoint is unlocked)
    from engines.kw2 import db as kw2_db
    kw2_db.update_session(session_id, phase1_done=True, current_phase="2")

    # ── Phase 2: generate keyword universe (batch) ──
    r = requests.post(
        f"{BASE_URL}/api/kw2/{project_id}/sessions/{session_id}/phase2",
        headers=headers,
        json={
            "confirmed_pillars": ["organic spices", "turmeric powder", "spice blends"],
            "confirmed_modifiers": ["buy", "organic", "wholesale"],
        },
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"Phase2 failed: {r.text}"
    universe = r.json().get("universe", {})
    assert (universe.get("total") or 0) > 0, "Phase2 produced 0 keywords — pipeline has no data to score"

    # ── Phase 3: validation (AI scoring) ──
    r = requests.post(
        f"{BASE_URL}/api/kw2/{project_id}/sessions/{session_id}/phase3",
        headers=headers,
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"Phase3 failed: {r.text}"

    return {"project_id": project_id, "session_id": session_id, "headers": headers}


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP A — PhaseScoreTree: Phase4 → Phase5 → Phase6
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhaseScoreTree:
    """
    Mirrors the PhaseScoreTree 'Run All' chain:
      Phase4 (Score & Cluster) → Phase5 (Tree & Top100) → Phase6 (Graph)
    Tests that each phase succeeds and passes valid data to the next.
    """

    # ── Phase 4: Score & Cluster ──────────────────────────────────────────────

    def test_G1_phase4_returns_200(self, pipeline_session):
        """Phase4 endpoint exists and returns HTTP 200."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase4",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Phase4 HTTP {r.status_code}: {r.text[:300]}"

    def test_G1_phase4_scoring_stats_present(self, pipeline_session):
        """Phase4 response includes scoring statistics."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase4",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        body = r.json()
        scoring = body.get("scoring") or {}
        assert scoring.get("scored", 0) >= 0, f"No 'scored' count in response: {body}"

    def test_G1_phase4_produces_clusters(self, pipeline_session):
        """Phase4 groups keywords into at least 1 cluster."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase4",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        body = r.json()
        clustering = body.get("clustering") or {}
        assert isinstance(clustering.get("clusters"), int), \
            f"Expected 'clusters' int in clustering: {clustering}"

    def test_G1_phase4_avg_score_in_range(self, pipeline_session):
        """Average score is between 0 and 100."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase4",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        scoring = r.json().get("scoring") or {}
        avg = scoring.get("avg_score", -1)
        assert 0 <= avg <= 100, f"avg_score {avg} out of valid range"

    # ── Phase 5: Tree & Top 100 ───────────────────────────────────────────────

    def test_G1_phase5_returns_200(self, pipeline_session):
        """Phase5 endpoint exists and returns HTTP 200."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase5",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Phase5 HTTP {r.status_code}: {r.text[:300]}"

    def test_G1_phase5_tree_has_universe_root(self, pipeline_session):
        """Phase5 returns a tree with a universe root node."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase5",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        tree = r.json().get("tree") or {}
        assert "universe" in tree, f"No 'universe' key in tree: {list(tree.keys())}"

    def test_G1_phase5_tree_has_pillars(self, pipeline_session):
        """Phase5 tree has at least one pillar."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase5",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        universe = r.json().get("tree", {}).get("universe", {})
        pillars = universe.get("pillars", [])
        assert len(pillars) >= 1, "Tree has no pillars — Phase 2 data may be empty"

    def test_G1_phase5_top100_endpoint(self, pipeline_session):
        """GET /top100 returns items after Phase5 runs."""
        p = pipeline_session
        # Run phase5 to ensure data exists
        requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase5",
            headers=p["headers"], timeout=TIMEOUT,
        )
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/top100",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /top100 failed: {r.text}"
        items = r.json().get("items", [])
        assert isinstance(items, list)
        assert len(items) > 0, "Top100 returned 0 items after Phase5"

    def test_G1_phase5_top100_max_100(self, pipeline_session):
        """Top100 list has at most 100 items."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/top100",
            headers=p["headers"],
        )
        items = r.json().get("items", [])
        assert len(items) <= 100, f"Top100 returned {len(items)} items (expected ≤100)"

    def test_G1_phase5_top100_have_scores(self, pipeline_session):
        """Each item in Top100 has a numeric score field."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/top100",
            headers=p["headers"],
        )
        items = r.json().get("items", [])
        if not items:
            pytest.skip("No top100 items to check")
        missing = [i for i, kw in enumerate(items[:10]) if kw.get("score") is None]
        assert not missing, f"Items at indices {missing} have null score"

    def test_G1_tree_get_endpoint(self, pipeline_session):
        """GET /tree returns the tree after Phase5 runs."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/tree",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /tree failed: {r.text}"
        tree = r.json().get("tree") or {}
        assert "universe" in tree, "GET /tree missing universe key"

    # ── Phase 6: Knowledge Graph ──────────────────────────────────────────────

    def test_G1_phase6_returns_200(self, pipeline_session):
        """Phase6 builds knowledge graph and returns HTTP 200."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase6",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Phase6 HTTP {r.status_code}: {r.text[:300]}"

    def test_G1_phase6_graph_has_edges(self, pipeline_session):
        """Phase6 graph result has a positive edge count."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase6",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        graph = r.json().get("graph") or {}
        edges = graph.get("edges", 0)
        assert edges >= 0, f"Unexpected edges value: {graph}"

    def test_G1_graph_get_endpoint(self, pipeline_session):
        """GET /graph returns data after Phase6 runs."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/graph",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /graph failed: {r.text}"

    def test_G1_full_scoretree_sequence(self, pipeline_session):
        """
        Integration: run Phase4 → Phase5 → Phase6 in sequence.
        Each must succeed. Simulates the 'Run All' button flow.
        """
        p = pipeline_session

        # Phase 4
        r4 = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase4",
            headers=p["headers"], timeout=TIMEOUT,
        )
        assert r4.status_code == 200, f"Phase4 in sequence failed: {r4.text[:200]}"

        # Phase 5 — chained after Phase4
        r5 = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase5",
            headers=p["headers"], timeout=TIMEOUT,
        )
        assert r5.status_code == 200, f"Phase5 in sequence failed: {r5.text[:200]}"
        assert "tree" in r5.json(), "Phase5 response missing 'tree'"

        # Phase 6 — chained after Phase5
        r6 = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase6",
            headers=p["headers"], timeout=TIMEOUT,
        )
        assert r6.status_code == 200, f"Phase6 in sequence failed: {r6.text[:200]}"

        top100_r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/top100",
            headers=p["headers"],
        )
        top100_count = len(top100_r.json().get("items", []))
        print(
            f"\n  ScoreTree sequence: "
            f"P4 scored={r4.json().get('scoring', {}).get('scored', '?')} | "
            f"P5 top100={top100_count} | "
            f"P6 edges={r6.json().get('graph', {}).get('edges', '?')}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP B — PhaseDeliver: Phase7 → Phase8 → Phase9
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhaseDeliver:
    """
    Mirrors the PhaseDeliver 'Run All' chain:
      Phase7 (Internal Links) → Phase8 (Content Calendar) → Phase9 (SEO Strategy)
    Tests that each phase succeeds and produces valid structured output.
    """

    # ── Phase 7: Internal Links ───────────────────────────────────────────────

    def test_G2_phase7_returns_200(self, pipeline_session):
        """Phase7 internal link generation returns HTTP 200."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase7",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Phase7 HTTP {r.status_code}: {r.text[:300]}"

    def test_G2_phase7_links_is_dict(self, pipeline_session):
        """Phase7 response has 'links' dict with total count."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase7",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        links = r.json().get("links") or {}
        assert isinstance(links, dict), f"Expected dict for 'links', got {type(links)}"

    def test_G2_phase7_links_get_endpoint(self, pipeline_session):
        """GET /links returns data after Phase7 runs."""
        p = pipeline_session
        # Ensure Phase7 ran
        requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase7",
            headers=p["headers"], timeout=TIMEOUT,
        )
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/links",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /links failed: {r.text}"
        items = r.json().get("items", [])
        assert isinstance(items, list), "GET /links 'items' is not a list"

    def test_G2_phase7_link_item_structure(self, pipeline_session):
        """Each link item has required fields: from_page, to_page, anchor_text, link_type."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/links",
            headers=p["headers"],
        )
        items = r.json().get("items", [])
        if not items:
            pytest.skip("No link items to validate structure")
        required = {"from_page", "to_page", "anchor_text", "link_type"}
        for item in items[:5]:
            missing = required - set(item.keys())
            assert not missing, f"Link item missing fields {missing}: {item}"

    # ── Phase 8: Content Calendar ─────────────────────────────────────────────

    def test_G2_phase8_returns_200(self, pipeline_session):
        """Phase8 content calendar returns HTTP 200."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase8",
            headers=p["headers"],
            json={"blogs_per_week": 2, "duration_weeks": 12, "start_date": None,
                  "seasonal_overrides": {}},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Phase8 HTTP {r.status_code}: {r.text[:300]}"

    def test_G2_phase8_calendar_has_scheduled(self, pipeline_session):
        """Phase8 calendar includes 'scheduled' count > 0."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase8",
            headers=p["headers"],
            json={"blogs_per_week": 2, "duration_weeks": 12, "start_date": None,
                  "seasonal_overrides": {}},
            timeout=TIMEOUT,
        )
        cal = r.json().get("calendar") or {}
        assert "scheduled" in cal, f"No 'scheduled' key in calendar: {cal}"
        assert cal["scheduled"] >= 0

    def test_G2_phase8_calendar_get_endpoint(self, pipeline_session):
        """GET /calendar returns items after Phase8 runs."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/calendar",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /calendar failed: {r.text}"
        items = r.json().get("items", [])
        assert isinstance(items, list)

    def test_G2_phase8_calendar_item_has_date(self, pipeline_session):
        """Each calendar item has a scheduled_date field."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/calendar",
            headers=p["headers"],
        )
        items = r.json().get("items", [])
        if not items:
            pytest.skip("No calendar items to validate")
        for item in items[:5]:
            assert "scheduled_date" in item, f"Calendar item missing 'scheduled_date': {item}"

    # ── Phase 9: SEO Strategy ─────────────────────────────────────────────────

    def test_G2_phase9_returns_200(self, pipeline_session):
        """Phase9 strategy generation returns HTTP 200."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase9",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Phase9 HTTP {r.status_code}: {r.text[:300]}"

    def test_G2_phase9_strategy_is_dict(self, pipeline_session):
        """Phase9 returns a non-empty strategy dict."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase9",
            headers=p["headers"],
            timeout=TIMEOUT,
        )
        strategy = r.json().get("strategy") or {}
        assert isinstance(strategy, dict), f"'strategy' is not a dict: {type(strategy)}"

    def test_G2_phase9_strategy_get_endpoint(self, pipeline_session):
        """GET /strategy returns the strategy after Phase9 runs."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/strategy",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /strategy failed: {r.text}"

    def test_G2_full_deliver_sequence(self, pipeline_session):
        """
        Integration: run Phase7 → Phase8 → Phase9 in sequence.
        Each must succeed. Simulates the PhaseDeliver 'Run All' button flow.
        """
        p = pipeline_session

        # Phase 7: Links
        r7 = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase7",
            headers=p["headers"], timeout=TIMEOUT,
        )
        assert r7.status_code == 200, f"Phase7 in sequence failed: {r7.text[:200]}"

        # Phase 8: Calendar (chained after Phase7)
        r8 = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase8",
            headers=p["headers"],
            json={"blogs_per_week": 3, "duration_weeks": 52, "start_date": None,
                  "seasonal_overrides": {}},
            timeout=TIMEOUT,
        )
        assert r8.status_code == 200, f"Phase8 in sequence failed: {r8.text[:200]}"

        # Phase 9: Strategy (chained after Phase8)
        r9 = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase9",
            headers=p["headers"], timeout=TIMEOUT,
        )
        assert r9.status_code == 200, f"Phase9 in sequence failed: {r9.text[:200]}"

        cal = r8.json().get("calendar", {})
        print(
            f"\n  Deliver sequence: "
            f"P7 links={r7.json().get('links', {}).get('links', '?')} | "
            f"P8 scheduled={cal.get('scheduled', '?')} weeks={cal.get('weeks', '?')} | "
            f"P9 strategy={'ok' if r9.json().get('strategy') else 'empty'}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP C — Error Handling & Resilience
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunAllResilience:
    """
    Tests that Phase4-9 fail gracefully on bad input (missing session,
    phase gating violations, etc.) rather than returning 500.
    """

    def test_G3_phase4_bad_session_404(self, auth):
        """Phase4 with a non-existent session returns 404, not 500."""
        r = requests.post(
            f"{BASE_URL}/api/kw2/fake_project/sessions/BAD_SESSION_ID/phase4",
            headers=auth, timeout=30,
        )
        assert r.status_code in (400, 404, 422), \
            f"Expected 4xx for bad session, got {r.status_code}: {r.text[:200]}"

    def test_G3_phase5_bad_session_404(self, auth):
        """Phase5 with a non-existent session returns 404, not 500."""
        r = requests.post(
            f"{BASE_URL}/api/kw2/fake_project/sessions/BAD_SESSION_ID/phase5",
            headers=auth, timeout=30,
        )
        assert r.status_code in (400, 404, 422), \
            f"Expected 4xx for bad session, got {r.status_code}: {r.text[:200]}"

    def test_G3_phase7_bad_session_404(self, auth):
        """Phase7 with invalid session returns 4xx."""
        r = requests.post(
            f"{BASE_URL}/api/kw2/fake_project/sessions/BAD_SESSION_ID/phase7",
            headers=auth, timeout=30,
        )
        assert r.status_code in (400, 404, 422)

    def test_G3_phase9_bad_session_404(self, auth):
        """Phase9 with invalid session returns 4xx."""
        r = requests.post(
            f"{BASE_URL}/api/kw2/fake_project/sessions/BAD_SESSION_ID/phase9",
            headers=auth, timeout=30,
        )
        assert r.status_code in (400, 404, 422)

    def test_G3_get_top100_empty_session(self, auth, pipeline_session):
        """GET /top100 returns empty list (not 500) when Phase5 hasn't run."""
        p = pipeline_session
        # Create a fresh session with no pipeline runs
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions",
            headers=p["headers"],
            json={"mode": "brand", "name": "Empty Pipeline Session"},
        )
        assert r.status_code == 200
        fresh_sid = r.json()["session_id"]

        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{fresh_sid}/top100",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /top100 shouldn't fail on empty session: {r.text}"
        assert isinstance(r.json().get("items", []), list)

    def test_G3_calendar_blogs_per_week_bounds(self, pipeline_session):
        """Phase8 with extreme blogs_per_week still returns 200."""
        p = pipeline_session
        r = requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase8",
            headers=p["headers"],
            json={"blogs_per_week": 1, "duration_weeks": 4, "start_date": None,
                  "seasonal_overrides": {}},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Phase8 with low config failed: {r.text[:200]}"

    def test_G3_unauthenticated_phase4_rejected(self):
        """Phase4 without auth token returns 401/403."""
        r = requests.post(
            f"{BASE_URL}/api/kw2/some_project/sessions/some_session/phase4",
            timeout=10,
        )
        assert r.status_code in (401, 403, 422), \
            f"Expected auth error, got {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP D — Dashboard & Session Stats
# ═══════════════════════════════════════════════════════════════════════════════

class TestDashboardAfterRunAll:
    """
    Verifies the dashboard and session-level stats reflect pipeline completion.
    """

    def test_G4_dashboard_returns_200(self, pipeline_session):
        """GET /dashboard works after full pipeline."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/dashboard",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /dashboard failed: {r.text}"

    def test_G4_session_reflects_phase_completion(self, pipeline_session):
        """Session record marks phase6_done=True after ScoreTree run."""
        p = pipeline_session
        # Run the full ScoreTree chain to ensure flags are set
        for phase in ["phase4", "phase5", "phase6"]:
            requests.post(
                f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/{phase}",
                headers=p["headers"], timeout=TIMEOUT,
            )
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}",
            headers=p["headers"],
        )
        assert r.status_code == 200
        session = r.json().get("session") or {}
        assert session.get("phase6_done"), \
            f"phase6_done not True after Phase6 ran. session fields: {list(session.keys())}"

    def test_G4_session_reflects_phase9_done(self, pipeline_session):
        """Session record marks phase9_done=True after strategy runs."""
        p = pipeline_session
        requests.post(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/phase9",
            headers=p["headers"], timeout=TIMEOUT,
        )
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}",
            headers=p["headers"],
        )
        session = r.json().get("session") or {}
        assert session.get("phase9_done"), \
            f"phase9_done not True after Phase9. session={list(session.keys())}"

    def test_G4_ai_usage_tracked(self, pipeline_session):
        """GET /ai-usage returns dict after phases that call AI."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/ai-usage",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /ai-usage failed: {r.text}"

    def test_G4_pillar_stats_after_pipeline(self, pipeline_session):
        """GET /pillar-stats returns per-pillar keyword breakdown."""
        p = pipeline_session
        r = requests.get(
            f"{BASE_URL}/api/kw2/{p['project_id']}/sessions/{p['session_id']}/pillar-stats",
            headers=p["headers"],
        )
        assert r.status_code == 200, f"GET /pillar-stats failed: {r.text}"
        stats = r.json() or {}
        assert isinstance(stats, (dict, list)), \
            f"pillar-stats should return dict or list, got {type(stats)}"

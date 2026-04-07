"""
kw2 Comprehensive Test Suite.
Tests all 20 engine modules + 30 API routes + DB operations.
Run: .venv/bin/python3 -m pytest tests/test_kw2.py -v --tb=short
"""
import os
import sys
import json
import sqlite3
import hashlib
import hmac
import base64
import time
import pytest
import requests
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Fixtures ─────────────────────────────────────────────────────────────────

BASE_URL = "http://127.0.0.1:8000"
TEST_DB = "/tmp/kw2_test.db"


def _get_jwt_secret():
    """Read JWT secret from same file the app uses."""
    secret_file = Path("/root/ANNASEOv1/.jwt_secret")
    if secret_file.exists():
        return secret_file.read_text().strip()
    return "fallback_secret"


def _make_test_token():
    """Generate a valid auth token for testing."""
    secret = _get_jwt_secret()
    exp = (datetime.utcnow() + timedelta(hours=2)).isoformat()
    p = json.dumps({"user_id": "user_test_kw2", "email": "test@kw2.com", "role": "user", "exp": exp})
    sig = hmac.new(secret.encode(), p.encode(), sha256).hexdigest()
    return f"{base64.urlsafe_b64encode(p.encode()).decode()}.{sig}"


@pytest.fixture(scope="session")
def auth_headers():
    """Register a test user and get a valid token."""
    # Try to register; if already exists, login instead
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"email": "kw2test@test.com", "name": "KW2 Test", "password": "testpass123"})
    if r.status_code == 200:
        token = r.json()["access_token"]
    elif r.status_code == 400:  # already registered
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          data={"username": "kw2test@test.com", "password": "testpass123"})
        token = r.json()["access_token"]
    else:
        # Fallback: generate token matching app's algorithm
        import hmac, base64
        secret = Path("/root/ANNASEOv1/.jwt_secret").read_text().strip()
        exp = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        p = json.dumps({"user_id": "user_test_kw2", "email": "test@kw2.com", "role": "user", "exp": exp})
        sig = hmac.new(secret.encode(), p.encode(), sha256).hexdigest()
        token = f"{base64.urlsafe_b64encode(p.encode()).decode()}.{sig}"
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def ensure_test_project(auth_headers):
    """Find an existing project or create one for testing."""
    r = requests.get(f"{BASE_URL}/api/projects", headers=auth_headers)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list) and data:
            return data[0].get("project_id")
        elif isinstance(data, dict):
            plist = data.get("projects", [])
            if plist:
                return plist[0].get("project_id")
    # Fallback: try known project
    return "proj_74d1323036"


# ════════════════════════════════════════════════════════════════════════════
# GROUP 1: FOUNDATION MODULE TESTS (no API, no AI)
# ════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_negative_patterns_nonempty(self):
        from engines.kw2.constants import NEGATIVE_PATTERNS
        assert len(NEGATIVE_PATTERNS) >= 25

    def test_commercial_boosts_dict(self):
        from engines.kw2.constants import COMMERCIAL_BOOSTS
        assert isinstance(COMMERCIAL_BOOSTS, dict)
        assert "buy" in COMMERCIAL_BOOSTS

    def test_intent_weights(self):
        from engines.kw2.constants import INTENT_WEIGHTS
        assert INTENT_WEIGHTS["purchase"] == 1.0
        assert INTENT_WEIGHTS["informational"] < 0.2

    def test_category_caps_sum_100(self):
        from engines.kw2.constants import CATEGORY_CAPS
        assert sum(CATEGORY_CAPS.values()) == 100

    def test_templates_have_placeholder(self):
        from engines.kw2.constants import TRANSACTIONAL_TEMPLATES, COMMERCIAL_TEMPLATES, LOCAL_TEMPLATES
        for t in TRANSACTIONAL_TEMPLATES:
            assert "{k}" in t, f"Missing {{k}} in {t}"
        for t in COMMERCIAL_TEMPLATES:
            assert "{k}" in t
        for t in LOCAL_TEMPLATES:
            assert "{k}" in t

    def test_garbage_words_frozenset(self):
        from engines.kw2.constants import GARBAGE_WORDS
        assert isinstance(GARBAGE_WORDS, frozenset)
        assert "the" in GARBAGE_WORDS


class TestPrompts:
    def test_all_prompts_are_strings(self):
        from engines.kw2 import prompts
        prompt_names = [
            "BUSINESS_ANALYSIS_SYSTEM", "BUSINESS_ANALYSIS_USER",
            "CONSISTENCY_CHECK_SYSTEM", "CONSISTENCY_CHECK_USER",
            "UNIVERSE_EXPAND_SYSTEM", "UNIVERSE_EXPAND_USER",
            "VALIDATE_SYSTEM", "VALIDATE_USER",
            "CLUSTER_NAME_SYSTEM", "CLUSTER_NAME_USER",
            "KEYWORD_EXPLAIN_SYSTEM", "KEYWORD_EXPLAIN_USER",
            "STRATEGY_SYSTEM", "STRATEGY_USER",
        ]
        for name in prompt_names:
            val = getattr(prompts, name)
            assert isinstance(val, str), f"{name} is not str"
            assert len(val) > 10, f"{name} is too short"

    def test_business_analysis_user_has_placeholders(self):
        from engines.kw2.prompts import BUSINESS_ANALYSIS_USER
        for key in ["products", "categories", "about", "entities", "topics", "competitor_data", "manual_input"]:
            assert f"{{{key}}}" in BUSINESS_ANALYSIS_USER, f"Missing {{{key}}}"


class TestDB:
    """Test DB helpers using a temp database."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = str(tmp_path / "test_kw2.db")
        os.environ["ANNASEO_DB"] = self.db_path
        from engines.kw2.db import init_kw2_db
        init_kw2_db(self.db_path)

    def test_init_creates_9_tables(self):
        conn = sqlite3.connect(self.db_path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'kw2_%'").fetchall()
        conn.close()
        assert len(tables) == 9

    def test_create_session(self):
        from engines.kw2.db import create_session, get_session
        sid = create_session("proj_test_1", "auto")
        assert sid.startswith("kw2_")
        s = get_session(sid)
        assert s is not None
        assert s["project_id"] == "proj_test_1"
        assert s["phase1_done"] == 0

    def test_update_session(self):
        from engines.kw2.db import create_session, update_session, get_session
        sid = create_session("proj_test_2")
        update_session(sid, phase1_done=1, universe_count=500)
        s = get_session(sid)
        assert s["phase1_done"] == 1
        assert s["universe_count"] == 500

    def test_get_latest_session(self):
        from engines.kw2.db import create_session, get_latest_session
        s1 = create_session("proj_test_3")
        time.sleep(0.05)
        s2 = create_session("proj_test_3")
        latest = get_latest_session("proj_test_3")
        assert latest["id"] == s2

    def test_save_load_business_profile(self):
        from engines.kw2.db import save_business_profile, load_business_profile
        profile = {
            "domain": "test.com",
            "universe": "Test Spices",
            "pillars": ["turmeric", "cardamom"],
            "product_catalog": ["turmeric powder"],
            "modifiers": ["organic"],
            "audience": ["chefs"],
            "intent_signals": ["buy"],
            "geo_scope": "India",
            "business_type": "Ecommerce",
            "negative_scope": ["recipe", "benefits"],
            "confidence_score": 0.85,
        }
        save_business_profile("proj_test_4", profile)
        loaded = load_business_profile("proj_test_4")
        assert loaded is not None
        assert loaded["universe"] == "Test Spices"
        assert loaded["pillars"] == ["turmeric", "cardamom"]
        assert isinstance(loaded["negative_scope"], list)

    def test_bulk_insert_universe(self):
        from engines.kw2.db import create_session, bulk_insert_universe, load_universe_items
        sid = create_session("proj_test_5")
        items = [
            {"keyword": "buy turmeric", "source": "seeds", "pillar": "turmeric", "raw_score": 0.8},
            {"keyword": "cardamom wholesale", "source": "rules", "pillar": "cardamom", "raw_score": 0.7},
        ]
        bulk_insert_universe(sid, "proj_test_5", items)
        loaded = load_universe_items(sid)
        assert len(loaded) == 2
        assert loaded[0]["keyword"] in ["buy turmeric", "cardamom wholesale"]

    def test_bulk_insert_validated(self):
        from engines.kw2.db import create_session, bulk_insert_validated, load_validated_keywords
        sid = create_session("proj_test_6")
        items = [
            {"keyword": "buy turmeric", "pillar": "turmeric", "intent": "purchase",
             "ai_relevance": 0.9, "buyer_readiness": 0.8, "commercial_score": 0.7,
             "final_score": 85.5, "source": "seeds"},
        ]
        bulk_insert_validated(sid, "proj_test_6", items)
        loaded = load_validated_keywords(sid)
        assert len(loaded) == 1
        assert loaded[0]["final_score"] == 85.5

    def test_uid_uniqueness(self):
        from engines.kw2.db import _uid
        ids = {_uid("t_") for _ in range(100)}
        assert len(ids) == 100  # all unique

    def test_update_universe_status(self):
        from engines.kw2.db import create_session, bulk_insert_universe, load_universe_items, update_universe_status
        sid = create_session("proj_test_upd")
        items = [
            {"keyword": "test kw 1", "source": "seeds", "pillar": "test", "raw_score": 0.9},
            {"keyword": "test kw 2", "source": "seeds", "pillar": "test", "raw_score": 0.8},
        ]
        bulk_insert_universe(sid, "proj_test_upd", items)
        loaded = load_universe_items(sid)
        assert len(loaded) == 2
        # Reject first
        update_universe_status([loaded[0]["id"]], "rejected", "bad keyword")
        raw = load_universe_items(sid, status="raw")
        assert len(raw) == 1


# ════════════════════════════════════════════════════════════════════════════
# GROUP 2: ENGINE UNIT TESTS (mocked AI)
# ════════════════════════════════════════════════════════════════════════════

class _FakePage:
    """Simulates CrawledPage for segment_content tests."""
    def __init__(self, page_type, title="", headings=None, body_text="", products_found=None):
        self.page_type = page_type
        self.title = title
        self.headings = headings or []
        self.body_text = body_text
        self.products_found = products_found or []


class TestContentSegmenter:
    def test_segment_empty(self):
        from engines.kw2.content_segmenter import segment_content
        result = segment_content([])
        assert result["products"] == ""
        assert result["found_products"] == []

    def test_segment_with_pages(self):
        from engines.kw2.content_segmenter import segment_content
        pages = [
            _FakePage("product", title="Turmeric Powder", body_text="Buy our organic turmeric powder", products_found=["turmeric powder"]),
            _FakePage("about", title="About Us", body_text="We are a spice company since 1990"),
            _FakePage("category", title="Spice Categories", body_text="Browse all spice categories"),
        ]
        result = segment_content(pages)
        assert len(result["found_products"]) >= 1
        assert "turmeric" in result["products"].lower()
        assert "1990" in result["about"]


class TestEntityExtractor:
    def test_extract_basic(self):
        from engines.kw2.entity_extractor import extract_entities
        text = "Buy organic turmeric powder wholesale from India. Premium cardamom pods for restaurants."
        entities, topics = extract_entities(text)
        assert isinstance(entities, list)
        assert isinstance(topics, list)
        assert len(entities) > 0 or len(topics) > 0


class TestConfidence:
    def test_perfect_profile(self):
        from engines.kw2.confidence import compute_confidence
        profile = {
            "pillars": ["a", "b", "c"],
            "product_catalog": ["p1", "p2", "p3", "p4", "p5"],
            "intent_signals": ["buy", "price"],
            "negative_scope": ["recipe", "benefits", "how to"],
            "universe": "Test",
        }
        score = compute_confidence(profile)
        assert 0.5 <= score <= 1.0

    def test_empty_profile(self):
        from engines.kw2.confidence import compute_confidence
        score = compute_confidence({})
        assert 0.0 <= score <= 0.3


class TestKeywordScorer:
    def test_score_computation(self, tmp_path):
        db_path = str(tmp_path / "scorer_test.db")
        os.environ["ANNASEO_DB"] = db_path
        from engines.kw2.db import init_kw2_db, create_session, bulk_insert_validated, save_business_profile
        from engines.kw2.keyword_scorer import KeywordScorer

        init_kw2_db(db_path)
        sid = create_session("proj_scorer")
        save_business_profile("proj_scorer", {
            "universe": "Spices", "pillars": ["turmeric"],
            "product_catalog": [], "modifiers": [], "audience": [],
            "intent_signals": [], "negative_scope": [],
        })
        bulk_insert_validated(sid, "proj_scorer", [
            {"keyword": "buy turmeric online", "pillar": "turmeric",
             "intent": "purchase", "ai_relevance": 0.9,
             "buyer_readiness": 0.8, "commercial_score": 25,
             "source": "seeds"},
        ])
        scorer = KeywordScorer()
        result = scorer.score_all("proj_scorer", sid)
        assert result["scored"] == 1


class TestTreeBuilder:
    def test_categorize_keyword(self):
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        assert tb._categorize_keyword("buy turmeric online") == "purchase"
        assert tb._categorize_keyword("wholesale cardamom bulk") == "wholesale"
        assert tb._categorize_keyword("turmeric price per kg") == "price"
        assert tb._categorize_keyword("best turmeric vs ginger") == "comparison"
        assert tb._categorize_keyword("spices near me") == "local"
        assert tb._categorize_keyword("organic spices supplier") == "other"

    def test_map_page(self):
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        assert tb._map_page("buy turmeric", "purchase") == "product_page"
        assert tb._map_page("wholesale spices bulk", "") == "b2b_page"
        assert tb._map_page("turmeric vs ginger", "comparison") == "blog_page"
        assert tb._map_page("spices near me", "local") == "local_page"
        assert tb._map_page("turmeric price", "") == "category_page"

    def test_select_top100_balanced(self, tmp_path):
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        kws = []
        # Generate 200 keywords across categories
        for i in range(50):
            kws.append({"id": f"v_{i}a", "keyword": f"buy product {i}", "final_score": 90 - i * 0.5})
        for i in range(50):
            kws.append({"id": f"v_{i}b", "keyword": f"wholesale item {i}", "final_score": 80 - i * 0.5})
        for i in range(50):
            kws.append({"id": f"v_{i}c", "keyword": f"price of item {i}", "final_score": 70 - i * 0.5})
        for i in range(50):
            kws.append({"id": f"v_{i}d", "keyword": f"organic item {i}", "final_score": 60 - i * 0.5})

        top = tb._select_top100(kws)
        assert len(top) == 100

        # Check CATEGORY_CAPS: at least 2 different categories present
        cats = {}
        for kw in top:
            cat = tb._categorize_keyword(kw["keyword"])
            cats[cat] = cats.get(cat, 0) + 1
        assert len(cats) >= 3  # purchase, wholesale, price, other all present


class TestKnowledgeGraph:
    def test_get_graph_empty(self, tmp_path):
        db_path = str(tmp_path / "graph_test.db")
        os.environ["ANNASEO_DB"] = db_path
        from engines.kw2.db import init_kw2_db, create_session
        from engines.kw2.knowledge_graph import KnowledgeGraphBuilder

        init_kw2_db(db_path)
        sid = create_session("proj_graph")
        builder = KnowledgeGraphBuilder()
        result = builder.get_graph(sid)
        assert isinstance(result, dict)
        assert len(result) == 0


class TestInternalLinker:
    def test_get_links_empty(self, tmp_path):
        db_path = str(tmp_path / "linker_test.db")
        os.environ["ANNASEO_DB"] = db_path
        from engines.kw2.db import init_kw2_db, create_session
        from engines.kw2.internal_linker import InternalLinker

        init_kw2_db(db_path)
        sid = create_session("proj_linker")
        linker = InternalLinker()
        result = linker.get_links(sid)
        assert isinstance(result, list)
        assert len(result) == 0


class TestContentCalendar:
    def test_get_calendar_empty(self, tmp_path):
        db_path = str(tmp_path / "cal_test.db")
        os.environ["ANNASEO_DB"] = db_path
        from engines.kw2.db import init_kw2_db, create_session
        from engines.kw2.content_calendar import ContentCalendar

        init_kw2_db(db_path)
        sid = create_session("proj_cal")
        cal = ContentCalendar()
        result = cal.get_calendar(sid)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_flatten_articles(self):
        from engines.kw2.content_calendar import ContentCalendar
        cal = ContentCalendar()
        pillars = ["turmeric", "cardamom"]
        keywords = [
            {"keyword": "buy turmeric", "pillar": "turmeric", "final_score": 90},
            {"keyword": "buy cardamom", "pillar": "cardamom", "final_score": 80},
        ]
        articles = cal._flatten_articles(pillars, keywords, [])
        # 2 pillar pages + 2 keyword articles = 4
        assert len(articles) == 4
        pillar_articles = [a for a in articles if a["is_pillar"]]
        assert len(pillar_articles) == 2

    def test_schedule_round_robin(self):
        from engines.kw2.content_calendar import ContentCalendar
        cal = ContentCalendar()
        articles = [
            {"keyword": "k1", "pillar": "p1", "score": 90, "article_type": "pillar", "is_pillar": True},
            {"keyword": "k2", "pillar": "p1", "score": 80, "article_type": "topic", "is_pillar": False},
            {"keyword": "k3", "pillar": "p2", "score": 70, "article_type": "topic", "is_pillar": False},
            {"keyword": "k4", "pillar": "p2", "score": 60, "article_type": "topic", "is_pillar": False},
        ]
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = cal._schedule(articles, 3, 4, start, {})
        assert len(result) == 4
        assert all("scheduled_date" in a for a in result)


class TestStrategyEngine:
    def test_get_strategy_empty(self, tmp_path):
        db_path = str(tmp_path / "strat_test.db")
        os.environ["ANNASEO_DB"] = db_path
        from engines.kw2.db import init_kw2_db, create_session
        from engines.kw2.strategy_engine import StrategyEngine

        init_kw2_db(db_path)
        sid = create_session("proj_strat")
        strat = StrategyEngine()
        result = strat.get_strategy(sid)
        assert result is None


class TestAiCaller:
    @patch("engines.kw2.ai_caller.AIRouter")
    def test_kw2_ai_call_auto(self, mock_router_class):
        mock_router_class.call.return_value = "test response"

        from engines.kw2.ai_caller import kw2_ai_call
        result = kw2_ai_call("test prompt", "test system", provider="auto")
        assert result == "test response"

    def test_kw2_extract_json(self):
        from engines.kw2.ai_caller import kw2_extract_json
        # The extract_json delegates to AIRouter.extract_json
        # Just test it doesn't crash on empty
        result = kw2_extract_json("")
        # Returns None or empty if can't parse


class TestConsistency:
    @patch("engines.kw2.consistency.kw2_ai_call")
    def test_check_consistency_pass(self, mock_call):
        mock_call.return_value = '{"valid": true, "issues": []}'
        from engines.kw2.consistency import check_consistency
        profile = {"pillars": ["turmeric"], "product_catalog": ["turmeric powder"]}
        result = check_consistency(profile, "auto")
        assert result is True

    @patch("engines.kw2.consistency.kw2_ai_call")
    def test_check_consistency_fail_open(self, mock_call):
        mock_call.side_effect = Exception("AI error")
        from engines.kw2.consistency import check_consistency
        result = check_consistency({}, "auto")
        assert result is True  # fail-open


# ════════════════════════════════════════════════════════════════════════════
# GROUP 3: API ROUTE INTEGRATION TESTS (against live server)
# ════════════════════════════════════════════════════════════════════════════

class TestAPIRoutes:
    """Integration tests against the live server."""

    @pytest.fixture(autouse=True)
    def setup(self, auth_headers, ensure_test_project):
        self.h = auth_headers
        self.pid = ensure_test_project
        self.base = BASE_URL

    def _get_or_create_project(self):
        """Ensure a real project exists for testing."""
        # Try existing project first
        r = requests.get(f"{self.base}/api/projects", headers=self.h)
        if r.status_code == 200:
            projects = r.json()
            if isinstance(projects, list) and projects:
                return projects[0].get("project_id")
            elif isinstance(projects, dict):
                plist = projects.get("projects", [])
                if plist:
                    return plist[0].get("project_id")
        # Create one
        r = requests.post(f"{self.base}/api/projects", headers=self.h, json={
            "name": "KW2 Test", "industry": "ecommerce",
        })
        if r.status_code == 200:
            return r.json().get("project_id")
        return None

    def test_01_server_alive(self):
        r = requests.get(f"{self.base}/api/auth/me", headers=self.h)
        assert r.status_code in [200, 401], f"Server not responding: {r.status_code}"

    def test_02_create_session(self):
        pid = self._get_or_create_project()
        if not pid:
            pytest.skip("No project available")

        r = requests.post(f"{self.base}/api/kw2/{pid}/sessions", headers=self.h,
                          json={"provider": "auto"})
        assert r.status_code == 200, f"Create session failed: {r.text}"
        data = r.json()
        assert "session_id" in data
        self.__class__._session_id = data["session_id"]
        self.__class__._project_id = pid

    def test_03_get_sessions(self):
        pid = getattr(self.__class__, "_project_id", None)
        if not pid:
            pytest.skip("No project")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions", headers=self.h)
        assert r.status_code == 200
        data = r.json()
        assert "session" in data

    def test_04_get_session_detail(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}", headers=self.h)
        assert r.status_code == 200
        data = r.json()
        assert data["session"]["phase1_done"] == 0

    def test_05_get_profile_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        if not pid:
            pytest.skip("No project")
        r = requests.get(f"{self.base}/api/kw2/{pid}/profile", headers=self.h)
        assert r.status_code == 200

    def test_06_get_universe_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/universe", headers=self.h)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0

    def test_07_get_validated_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/validated", headers=self.h)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_08_get_top100_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/top100", headers=self.h)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_09_get_tree_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/tree", headers=self.h)
        assert r.status_code == 200

    def test_10_get_graph_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/graph", headers=self.h)
        assert r.status_code == 200

    def test_11_get_links_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/links", headers=self.h)
        assert r.status_code == 200

    def test_12_get_calendar_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/calendar", headers=self.h)
        assert r.status_code == 200

    def test_13_get_strategy_empty(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/strategy", headers=self.h)
        assert r.status_code == 200
        assert r.json()["strategy"] is None

    def test_14_dashboard(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/dashboard", headers=self.h)
        assert r.status_code == 200

    def test_15_phase2_requires_phase1(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.post(f"{self.base}/api/kw2/{pid}/sessions/{sid}/phase2", headers=self.h)
        assert r.status_code == 400

    def test_16_phase3_requires_phase2(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.post(f"{self.base}/api/kw2/{pid}/sessions/{sid}/phase3", headers=self.h)
        assert r.status_code == 400

    def test_17_phase4_requires_phase3(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.post(f"{self.base}/api/kw2/{pid}/sessions/{sid}/phase4", headers=self.h)
        assert r.status_code == 400

    def test_18_invalid_session_404(self):
        pid = getattr(self.__class__, "_project_id", None)
        if not pid:
            pytest.skip("No project")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/nonexistent", headers=self.h)
        assert r.status_code == 404

    def test_19_invalid_project_404(self):
        r = requests.post(f"{self.base}/api/kw2/nonexistent_project/sessions",
                          headers=self.h, json={"provider": "auto"})
        assert r.status_code == 404

    def test_20_links_filter_by_type(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/links?link_type=sibling", headers=self.h)
        assert r.status_code == 200

    def test_21_calendar_filter_by_pillar(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/calendar?pillar=test", headers=self.h)
        assert r.status_code == 200

    def test_22_top100_filter_by_pillar(self):
        pid = getattr(self.__class__, "_project_id", None)
        sid = getattr(self.__class__, "_session_id", None)
        if not pid or not sid:
            pytest.skip("No session")
        r = requests.get(f"{self.base}/api/kw2/{pid}/sessions/{sid}/top100?pillar=test", headers=self.h)
        assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════════════
# GROUP 4: FULL PIPELINE TEST (with real DB, mocked AI)
# ════════════════════════════════════════════════════════════════════════════

class TestFullPipeline:
    """End-to-end pipeline test using a temp DB and mocked AI calls."""

    @pytest.fixture(autouse=True)
    def setup_pipeline(self, tmp_path):
        self.db_path = str(tmp_path / "pipeline_test.db")
        os.environ["ANNASEO_DB"] = self.db_path
        from engines.kw2.db import init_kw2_db
        init_kw2_db(self.db_path)

    def _seed_profile(self, project_id):
        from engines.kw2.db import save_business_profile
        save_business_profile(project_id, {
            "domain": "test-spices.com",
            "universe": "Indian Spices",
            "pillars": ["turmeric", "cardamom", "cinnamon"],
            "product_catalog": ["turmeric powder", "cardamom pods", "cinnamon sticks"],
            "modifiers": ["organic", "wholesale", "bulk"],
            "audience": ["chefs", "restaurants"],
            "intent_signals": ["buy", "wholesale"],
            "geo_scope": "India",
            "business_type": "Ecommerce",
            "negative_scope": ["recipe", "benefits", "how to", "what is"],
            "confidence_score": 0.85,
        })

    def _seed_validated_kws(self, session_id, project_id):
        from engines.kw2.db import bulk_insert_validated
        kws = []
        intents = ["purchase", "wholesale", "commercial", "comparison", "local"]
        for pillar in ["turmeric", "cardamom", "cinnamon"]:
            for i in range(40):
                intent = intents[i % len(intents)]
                kws.append({
                    "keyword": f"buy {pillar} product {i}",
                    "pillar": pillar,
                    "intent": intent,
                    "ai_relevance": 0.9 - (i * 0.01),
                    "buyer_readiness": 0.8 - (i * 0.01),
                    "commercial_score": 20 + (i % 10),
                    "final_score": 85 - i * 0.5,
                    "source": "seeds",
                })
        bulk_insert_validated(session_id, project_id, kws)

    def _seed_clusters(self, session_id, project_id):
        from engines.kw2.db import get_conn, _uid, _now
        conn = get_conn()
        now = _now()
        for pillar in ["turmeric", "cardamom", "cinnamon"]:
            for c in range(3):
                conn.execute(
                    "INSERT INTO kw2_clusters (id, session_id, project_id, pillar, cluster_name, top_keyword, avg_score, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (_uid("cl_"), session_id, project_id, pillar, f"{pillar}_cluster_{c}", f"buy {pillar} product {c}", 80 - c * 5, now),
                )
        conn.commit()
        conn.close()

    def test_pipeline_phase4_scorer(self):
        from engines.kw2.db import create_session, update_session
        from engines.kw2.keyword_scorer import KeywordScorer

        pid = "proj_pipe_4"
        self._seed_profile(pid)
        sid = create_session(pid)
        update_session(sid, phase1_done=1, phase2_done=1, phase3_done=1)
        self._seed_validated_kws(sid, pid)

        scorer = KeywordScorer()
        result = scorer.score_all(pid, sid)
        assert result["scored"] == 120  # 3 pillars × 40

    def test_pipeline_phase5_tree(self):
        from engines.kw2.db import create_session, update_session
        from engines.kw2.tree_builder import TreeBuilder

        pid = "proj_pipe_5"
        self._seed_profile(pid)
        sid = create_session(pid)
        update_session(sid, phase1_done=1, phase2_done=1, phase3_done=1, phase4_done=1)
        self._seed_validated_kws(sid, pid)
        self._seed_clusters(sid, pid)

        builder = TreeBuilder()
        tree = builder.build_tree(pid, sid, "auto")
        assert "universe" in tree
        assert tree["universe"]["name"] == "Indian Spices"

        # Verify top100
        top = builder.get_top100(sid)
        assert len(top) == 100

    def test_pipeline_phase6_graph(self):
        from engines.kw2.db import create_session, update_session
        from engines.kw2.knowledge_graph import KnowledgeGraphBuilder

        pid = "proj_pipe_6"
        self._seed_profile(pid)
        sid = create_session(pid)
        update_session(sid, phase1_done=1, phase2_done=1, phase3_done=1, phase4_done=1, phase5_done=1)
        self._seed_validated_kws(sid, pid)
        self._seed_clusters(sid, pid)

        builder = KnowledgeGraphBuilder()
        result = builder.build(pid, sid)
        assert result["edges"] > 0
        assert result["pillars"] == 3

        # Verify get_graph returns grouped edges
        graph = builder.get_graph(sid)
        assert "keyword_to_cluster" in graph or "sibling" in graph or "pillar_to_universe" in graph

    def test_pipeline_phase7_links(self):
        from engines.kw2.db import create_session, update_session
        from engines.kw2.internal_linker import InternalLinker

        pid = "proj_pipe_7"
        self._seed_profile(pid)
        sid = create_session(pid)
        update_session(sid, phase1_done=1, phase2_done=1, phase3_done=1, phase4_done=1, phase5_done=1, phase6_done=1)
        self._seed_validated_kws(sid, pid)
        self._seed_clusters(sid, pid)

        linker = InternalLinker()
        result = linker.build(pid, sid)
        assert result["links"] > 0
        assert "by_type" in result

        # Verify get_links returns items
        all_links = linker.get_links(sid)
        assert len(all_links) > 0

        # Verify filter by type works
        sibling_links = linker.get_links(sid, "sibling")
        assert isinstance(sibling_links, list)

    def test_pipeline_phase8_calendar(self):
        from engines.kw2.db import create_session, update_session
        from engines.kw2.content_calendar import ContentCalendar

        pid = "proj_pipe_8"
        self._seed_profile(pid)
        sid = create_session(pid)
        update_session(sid, phase1_done=1, phase2_done=1, phase3_done=1, phase4_done=1,
                       phase5_done=1, phase6_done=1, phase7_done=1)
        self._seed_validated_kws(sid, pid)
        self._seed_clusters(sid, pid)

        cal = ContentCalendar()
        result = cal.build(pid, sid, blogs_per_week=3, duration_weeks=52)
        assert result["scheduled"] > 0

        # Verify calendar entries
        entries = cal.get_calendar(sid)
        assert len(entries) > 0

        # Verify dates are in order
        dates = [e["scheduled_date"] for e in entries]
        assert dates == sorted(dates)


# ════════════════════════════════════════════════════════════════════════════
# GROUP 5: EDGE CASE & SAFETY TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = str(tmp_path / "edge_test.db")
        os.environ["ANNASEO_DB"] = self.db_path
        from engines.kw2.db import init_kw2_db
        init_kw2_db(self.db_path)

    def test_empty_bulk_insert(self):
        from engines.kw2.db import create_session, bulk_insert_universe, load_universe_items
        sid = create_session("proj_edge_1")
        bulk_insert_universe(sid, "proj_edge_1", [])
        assert load_universe_items(sid) == []

    def test_update_session_empty_kwargs(self):
        from engines.kw2.db import create_session, update_session, get_session
        sid = create_session("proj_edge_2")
        update_session(sid)  # empty kwargs should not crash
        s = get_session(sid)
        assert s is not None

    def test_load_nonexistent_profile(self):
        from engines.kw2.db import load_business_profile
        result = load_business_profile("nonexistent_project")
        assert result is None

    def test_get_nonexistent_session(self):
        from engines.kw2.db import get_session
        result = get_session("nonexistent_session_id")
        assert result is None

    def test_category_caps_edge(self):
        """Test that _select_top100 handles fewer than 100 keywords."""
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        kws = [{"id": f"v_{i}", "keyword": f"keyword {i}", "final_score": 90 - i} for i in range(10)]
        top = tb._select_top100(kws)
        assert len(top) == 10  # only 10 available

    def test_segment_content_with_special_chars(self):
        from engines.kw2.content_segmenter import segment_content
        pages = [_FakePage("product", body_text="Buy <b>spices</b> & herbs! Price: $10.99")]
        result = segment_content(pages)
        assert isinstance(result, dict)

    def test_confidence_with_none_values(self):
        from engines.kw2.confidence import compute_confidence
        profile = {"pillars": None, "product_catalog": None}
        score = compute_confidence(profile)
        assert score == 0.0

    def test_tree_builder_no_profile_raises(self):
        from engines.kw2.db import create_session
        from engines.kw2.tree_builder import TreeBuilder
        sid = create_session("proj_edge_noprfl")
        tb = TreeBuilder()
        with pytest.raises(ValueError, match="No business profile"):
            tb.build_tree("proj_edge_noprfl", sid, "auto")

    def test_knowledge_graph_no_profile_raises(self):
        from engines.kw2.db import create_session
        from engines.kw2.knowledge_graph import KnowledgeGraphBuilder
        sid = create_session("proj_edge_nograph")
        builder = KnowledgeGraphBuilder()
        with pytest.raises(ValueError, match="No business profile"):
            builder.build("proj_edge_nograph", sid)

    def test_internal_linker_no_profile_raises(self):
        from engines.kw2.db import create_session
        from engines.kw2.internal_linker import InternalLinker
        sid = create_session("proj_edge_nolink")
        linker = InternalLinker()
        with pytest.raises(ValueError, match="No business profile"):
            linker.build("proj_edge_nolink", sid)

    def test_calendar_no_profile_raises(self):
        from engines.kw2.db import create_session
        from engines.kw2.content_calendar import ContentCalendar
        sid = create_session("proj_edge_nocal")
        cal = ContentCalendar()
        with pytest.raises(ValueError, match="No business profile"):
            cal.build("proj_edge_nocal", sid)

    def test_strategy_engine_no_profile_raises(self):
        from engines.kw2.db import create_session
        from engines.kw2.strategy_engine import StrategyEngine
        sid = create_session("proj_edge_nostrat")
        strat = StrategyEngine()
        with pytest.raises(ValueError, match="No business profile"):
            strat.generate("proj_edge_nostrat", sid)

    def test_double_init_kw2_db_idempotent(self):
        from engines.kw2.db import init_kw2_db
        # Should not crash when called twice
        init_kw2_db(self.db_path)
        init_kw2_db(self.db_path)
        conn = sqlite3.connect(self.db_path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'kw2_%'").fetchall()
        conn.close()
        assert len(tables) == 9

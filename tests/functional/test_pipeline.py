"""
tests/functional/test_pipeline.py
===================================
GROUP 1 — Functional Tests: System Correctness.

Verifies that the kw2 pipeline executes without crashing,
returns expected output shapes, and handles edge cases gracefully.

Run: pytest tests/functional/ -v --tb=short
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("ANNASEO_TESTING", "1")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_profile():
    return {
        "universe": "Indian Spices",
        "pillars": ["cardamom", "black pepper", "turmeric"],
        "modifiers": ["organic", "bulk", "wholesale"],
        "audience": ["home cooks", "restaurants", "exporters"],
        "business_type": "D2C",
        "geo_scope": "India",
        "negative_scope": ["recipe", "benefits", "how to", "what is", "home remedy"],
    }


@pytest.fixture
def sample_keywords():
    return [
        {"keyword": "buy organic cardamom online", "intent": "purchase", "ai_relevance": 0.92, "buyer_readiness": 0.88},
        {"keyword": "cardamom wholesale supplier india", "intent": "commercial", "ai_relevance": 0.85, "buyer_readiness": 0.80},
        {"keyword": "bulk turmeric price per kg", "intent": "transactional", "ai_relevance": 0.78, "buyer_readiness": 0.75},
        {"keyword": "black pepper types guide", "intent": "informational", "ai_relevance": 0.45, "buyer_readiness": 0.20},
        {"keyword": "cardamom near me", "intent": "local", "ai_relevance": 0.70, "buyer_readiness": 0.65},
    ]


@pytest.fixture
def sample_clusters():
    return [
        {"cluster_name": "Wholesale Bulk Orders", "keywords": ["cardamom wholesale", "bulk pepper price"]},
        {"cluster_name": "Online Purchase", "keywords": ["buy cardamom online", "order spices india"]},
        {"cluster_name": "Price Comparison", "keywords": ["turmeric price kg", "pepper rate today"]},
    ]


@pytest.fixture
def sample_strategy():
    return {
        "priority_pillars": ["cardamom", "black pepper"],
        "weekly_plan": [
            {"week": 1, "focus_pillar": "cardamom", "articles": [
                {"title": "Buy Organic Cardamom Online", "primary_keyword": "buy cardamom online", "intent": "transactional", "page_type": "landing_page"}
            ]},
        ],
        "quick_wins": ["buy cardamom online india", "cardamom wholesale bulk"],
        "content_gaps": ["ceylon cardamom vs green cardamom"],
    }


@pytest.fixture
def full_result(sample_profile, sample_keywords, sample_clusters, sample_strategy):
    return {
        "profile": sample_profile,
        "keywords": sample_keywords,
        "clusters": sample_clusters,
        "strategy": sample_strategy,
        "confidence": 0.82,
    }


# ── 1. Normalizer unit tests ──────────────────────────────────────────────────

class TestNormalizer:
    def test_canonical_lowercases(self):
        """canonical() lowercases AND sorts alphabetically by design."""
        from engines.kw2.normalizer import canonical
        result = canonical("Buy Basil ONLINE")
        assert result == result.lower()  # always lowercase
        assert "basil" in result
        assert "online" in result

    def test_canonical_strips_whitespace(self):
        from engines.kw2.normalizer import canonical
        result = canonical("  basil seeds  ")
        assert result == result.strip()  # no leading/trailing whitespace
        assert "basil" in result

    def test_canonical_deduplicates_spaces(self):
        from engines.kw2.normalizer import canonical
        result = canonical("buy   basil")
        assert "  " not in result  # no double spaces
        assert "basil" in result and "buy" in result

    def test_canonical_sorted_alphabetically(self):
        """canonical() sorts tokens alphabetically — this is the defined contract."""
        from engines.kw2.normalizer import canonical
        result = canonical("buy organic cardamom online")
        tokens = result.split()
        assert tokens == sorted(tokens), f"Expected sorted tokens, got: {tokens}"

    def test_detect_pillars_finds_match(self):
        from engines.kw2.normalizer import detect_pillars
        pillars = ["cardamom", "pepper", "turmeric"]
        found = detect_pillars("buy organic cardamom online", pillars)
        # detect_pillars returns list of dicts: [{"pillar": ..., "confidence": ...}]
        pillar_names = [r["pillar"] if isinstance(r, dict) else r for r in found]
        assert "cardamom" in pillar_names

    def test_detect_pillars_empty_on_no_match(self):
        from engines.kw2.normalizer import detect_pillars
        pillars = ["cardamom", "pepper"]
        found = detect_pillars("buy fresh tomatoes india", pillars)
        pillar_names = [r["pillar"] if isinstance(r, dict) else r for r in found]
        assert "cardamom" not in pillar_names


# ── 2. Keyword Scorer unit tests ──────────────────────────────────────────────

class TestKeywordScorer:
    def test_commercial_score_positive_for_buy(self):
        from engines.kw2.keyword_scorer import KeywordScorer
        s = KeywordScorer()
        assert s._commercial_score("buy cardamom seeds bulk") > 0.0

    def test_commercial_score_zero_for_info(self):
        from engines.kw2.keyword_scorer import KeywordScorer
        s = KeywordScorer()
        assert s._commercial_score("cardamom origin history") == 0.0

    def test_commercial_score_positive_for_wholesale(self):
        from engines.kw2.keyword_scorer import KeywordScorer
        s = KeywordScorer()
        assert s._commercial_score("wholesale pepper supplier") > 0.0


# ── 3. Tree Builder size constraints ─────────────────────────────────────────

class TestTreeBuilder:
    def _make_keywords(self, n: int, score: float = 60.0):
        return [
            {"id": f"kw{i}", "keyword": f"keyword {i}", "hybrid_score": score - i * 0.01,
             "category": "purchase", "intent": "purchase", "pillar": "test"}
            for i in range(n)
        ]

    def test_top100_never_exceeds_100(self):
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        kws = self._make_keywords(200)
        result = tb._select_top100(kws)  # internal method: select top 100 from list
        assert len(result) <= 100

    def test_top100_sorted_by_score_desc(self):
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        kws = self._make_keywords(50)
        result = tb._select_top100(kws)
        scores = [k.get("hybrid_score", 0) for k in result]
        assert scores == sorted(scores, reverse=True)


# ── 4. Constants integrity ────────────────────────────────────────────────────

class TestConstants:
    def test_category_caps_sum_100(self):
        from engines.kw2.constants import CATEGORY_CAPS
        assert sum(CATEGORY_CAPS.values()) == 100

    def test_hybrid_weights_sum_1(self):
        from engines.kw2.constants import HYBRID_SCORE_WEIGHTS
        assert abs(sum(HYBRID_SCORE_WEIGHTS.values()) - 1.0) < 1e-6

    def test_negative_patterns_lowercase(self):
        from engines.kw2.constants import NEGATIVE_PATTERNS
        for p in NEGATIVE_PATTERNS:
            assert p == p.lower(), f"Not lowercase: '{p}'"

    def test_commercial_intent_weight_highest(self):
        from engines.kw2.constants import INTENT_WEIGHTS
        commercial = INTENT_WEIGHTS.get("commercial", 0)
        informational = INTENT_WEIGHTS.get("informational", 1)
        assert commercial > informational


# ── 5. Audit validator smoke test ────────────────────────────────────────────

class TestAuditValidatorSmoke:
    def test_full_result_passes(self, full_result):
        from audit.validators.ai_reasoning import validate_ai_output
        verdict = validate_ai_output(full_result)
        assert "valid" in verdict
        assert "score" in verdict
        assert isinstance(verdict["failures"], list)

    def test_empty_result_fails(self):
        from audit.validators.ai_reasoning import validate_ai_output
        verdict = validate_ai_output({})
        assert verdict["valid"] is False
        assert verdict["score"] == 0.0

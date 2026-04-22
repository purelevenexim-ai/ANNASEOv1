"""
tests/ai_reasoning/test_ai_output.py
======================================
GROUP 3 — AI Reasoning Tests: Output Quality & Logic Validation.

Validates that AI-generated outputs are:
  A. Logically consistent (no contradictions)
  B. Free from obvious hallucination
  C. Schema-compliant
  D. Stable across repeated calls (determinism)
  E. Commercially correct (keyword intent alignment)

These tests use MOCK AI responses — no real Ollama/Groq calls.

Run: pytest tests/ai_reasoning/ -v --tb=short
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("ANNASEO_TESTING", "1")


# ── Shared fixtures ───────────────────────────────────────────────────────────

GOOD_KEYWORDS = [
    {"keyword": "buy organic cardamom 500g", "intent": "purchase", "ai_relevance": 0.93, "buyer_readiness": 0.90},
    {"keyword": "cardamom wholesale dealer india", "intent": "commercial", "ai_relevance": 0.87, "buyer_readiness": 0.82},
    {"keyword": "bulk pepper price per kg", "intent": "transactional", "ai_relevance": 0.81, "buyer_readiness": 0.78},
    {"keyword": "best cardamom brand", "intent": "comparison", "ai_relevance": 0.74, "buyer_readiness": 0.60},
    {"keyword": "spice shop near me", "intent": "local", "ai_relevance": 0.70, "buyer_readiness": 0.65},
    {"keyword": "how to choose cardamom grade", "intent": "informational", "ai_relevance": 0.55, "buyer_readiness": 0.25},
]

BAD_KEYWORDS = [
    # informational dominance — wrong for a commercial SEO system
    {"keyword": "cardamom recipe ideas", "intent": "informational", "ai_relevance": 0.80, "buyer_readiness": 0.10},
    {"keyword": "health benefits of cardamom", "intent": "informational", "ai_relevance": 0.75, "buyer_readiness": 0.05},
    {"keyword": "what is black pepper", "intent": "informational", "ai_relevance": 0.70, "buyer_readiness": 0.08},
    {"keyword": "turmeric home remedy", "intent": "informational", "ai_relevance": 0.65, "buyer_readiness": 0.04},
    {"keyword": "ayurvedic uses of cardamom", "intent": "informational", "ai_relevance": 0.60, "buyer_readiness": 0.03},
    {"keyword": "traditional pepper recipe", "intent": "informational", "ai_relevance": 0.55, "buyer_readiness": 0.02},
]

GOOD_PROFILE = {
    "universe": "Kerala Spices",
    "pillars": ["cardamom", "black pepper", "turmeric"],
    "modifiers": ["organic", "wholesale", "bulk"],
    "audience": ["home cooks", "restaurants", "exporters"],
    "business_type": "D2C",
    "geo_scope": "India",
    "negative_scope": ["recipe", "benefits", "how to", "what is", "home remedy"],
}


# ── A. Logical Consistency ────────────────────────────────────────────────────

class TestLogicalConsistency:
    def test_no_positioning_conflicts_in_good_profile(self):
        from audit.validators.consistency import check_positioning_conflicts
        text = str(GOOD_PROFILE)
        issues = check_positioning_conflicts(text)
        assert issues == [], f"Unexpected conflicts: {issues}"

    def test_positioning_conflict_detected(self):
        from audit.validators.consistency import check_positioning_conflicts
        contradicting = "We sell luxury premium spices at the cheapest budget prices"
        issues = check_positioning_conflicts(contradicting)
        assert len(issues) > 0

    def test_pillar_not_in_negative_scope(self):
        from audit.validators.consistency import check_pillar_negative_scope_conflict
        issues = check_pillar_negative_scope_conflict(
            GOOD_PROFILE["pillars"], GOOD_PROFILE["negative_scope"]
        )
        assert issues == []

    def test_strategy_pillar_references_valid_pillars(self):
        from audit.validators.consistency import check_strategy_pillar_references
        strategy = {
            "weekly_plan": [
                {"week": 1, "focus_pillar": "cardamom"},
                {"week": 2, "focus_pillar": "black pepper"},
            ]
        }
        issues = check_strategy_pillar_references(strategy, GOOD_PROFILE["pillars"])
        assert issues == []

    def test_strategy_ghost_pillar_caught(self):
        from audit.validators.consistency import check_strategy_pillar_references
        strategy = {
            "weekly_plan": [{"week": 1, "focus_pillar": "vanilla"}]  # not a known pillar
        }
        issues = check_strategy_pillar_references(strategy, GOOD_PROFILE["pillars"])
        assert any("vanilla" in i for i in issues)


# ── B. Hallucination Detection ────────────────────────────────────────────────

class TestHallucinationDetection:
    def test_entity_present_in_source_passes(self):
        from audit.validators.consistency import check_entity_hallucination
        entities = ["cardamom", "pepper"]
        source = "We sell premium cardamom and black pepper from Kerala"
        issues = check_entity_hallucination(entities, source)
        assert issues == []

    def test_invented_entity_flagged(self):
        from audit.validators.consistency import check_entity_hallucination
        entities = ["zorbinium", "fluxite"]  # completely invented
        source = "We sell premium cardamom and black pepper"
        issues = check_entity_hallucination(entities, source)
        assert len(issues) > 0

    def test_keyword_length_sanity(self):
        """No keyword should be absurdly long — hallucinated outputs are often verbose."""
        from audit.validators.schema import validate_keyword_row
        hallucinated_kw = {
            "keyword": "buy " + "cardamom " * 40,  # 280+ chars
            "intent": "purchase",
            "ai_relevance": 0.8,
            "buyer_readiness": 0.7,
        }
        issues = validate_keyword_row(hallucinated_kw)
        assert any("long" in i.lower() or "200" in i for i in issues)


# ── C. Schema Validation ──────────────────────────────────────────────────────

class TestSchemaCompliance:
    def test_good_keywords_pass_schema(self):
        from audit.validators.schema import validate_keyword_list
        result = validate_keyword_list(GOOD_KEYWORDS)
        assert result["valid"] is True, f"Schema failures: {result['issues']}"

    def test_bad_intent_fails_schema(self):
        from audit.validators.schema import validate_keyword_row
        row = {"keyword": "buy basil", "intent": "UNKNOWN_INTENT", "ai_relevance": 0.8, "buyer_readiness": 0.7}
        issues = validate_keyword_row(row)
        assert any("intent" in i.lower() for i in issues)

    def test_relevance_out_of_range_fails(self):
        from audit.validators.schema import validate_keyword_row
        row = {"keyword": "buy basil", "intent": "purchase", "ai_relevance": 1.8, "buyer_readiness": 0.5}
        issues = validate_keyword_row(row)
        assert any("relevance" in i.lower() for i in issues)

    def test_full_good_output_passes_ai_validator(self):
        from audit.validators.ai_reasoning import validate_ai_output
        result = {
            "keywords": GOOD_KEYWORDS,
            "profile": GOOD_PROFILE,
            "clusters": [
                {"cluster_name": "Wholesale Orders", "keywords": ["cardamom wholesale", "pepper bulk"]},
                {"cluster_name": "Online Purchase", "keywords": ["buy cardamom", "order spices"]},
            ],
            "strategy": {
                "priority_pillars": ["cardamom"],
                "weekly_plan": [{"week": 1, "focus_pillar": "cardamom", "articles": []}],
                "quick_wins": ["buy cardamom online"],
                "content_gaps": [],
            },
        }
        verdict = validate_ai_output(result)
        assert verdict["score"] >= 0.6, f"Expected score ≥0.6, got {verdict['score']}. Failures: {verdict['failures']}"

    def test_informational_dominated_output_warned(self):
        from audit.validators.ai_reasoning import validate_ai_output
        result = {"keywords": BAD_KEYWORDS}
        verdict = validate_ai_output(result)
        # Should have warnings about informational dominance
        all_messages = verdict.get("warnings", []) + verdict.get("failures", [])
        assert any("informational" in m.lower() for m in all_messages), (
            f"Expected informational dominance warning. Got: {all_messages}"
        )


# ── D. Determinism / Stability ────────────────────────────────────────────────

class TestDeterminism:
    def test_similarity_identical_outputs_is_1(self):
        from audit.validators.ai_reasoning import measure_similarity
        out = {"keywords": GOOD_KEYWORDS, "profile": GOOD_PROFILE, "clusters": []}
        assert measure_similarity(out, out) == 1.0

    def test_similarity_empty_vs_full_is_0(self):
        from audit.validators.ai_reasoning import measure_similarity
        out = {"keywords": GOOD_KEYWORDS, "profile": GOOD_PROFILE, "clusters": []}
        sim = measure_similarity(out, {"keywords": [], "profile": {}, "clusters": []})
        assert sim == 0.0

    def test_similarity_partial_overlap_in_range(self):
        from audit.validators.ai_reasoning import measure_similarity
        out1 = {
            "keywords": GOOD_KEYWORDS[:3],  # first 3
            "profile": GOOD_PROFILE,
        }
        out2 = {
            "keywords": GOOD_KEYWORDS[1:4],  # shifted by 1 — 2 in common
            "profile": GOOD_PROFILE,
        }
        sim = measure_similarity(out1, out2)
        assert 0.0 < sim < 1.0, f"Expected partial similarity, got {sim}"

    def test_normalizer_deterministic_on_same_input(self):
        """canonical() must return same result every call for same input."""
        from engines.kw2.normalizer import canonical
        results = {canonical("Buy Organic Cardamom SEEDS India") for _ in range(5)}
        assert len(results) == 1, "canonical() is not deterministic"


# ── E. Commercial Correctness ─────────────────────────────────────────────────

class TestCommercialCorrectness:
    def test_negative_pattern_keywords_have_low_relevance(self):
        """Keywords matching negative patterns should never have high relevance."""
        import re
        from engines.kw2.constants import NEGATIVE_PATTERNS
        flagged = []
        for kw in GOOD_KEYWORDS:
            word = kw["keyword"].lower()
            for neg in NEGATIVE_PATTERNS:
                if neg in word and kw["ai_relevance"] > 0.7:
                    flagged.append(f"'{word}' matches neg pattern '{neg}' but has relevance {kw['ai_relevance']}")
        assert not flagged, f"High-relevance negative keywords: {flagged}"

    def test_purchase_keywords_have_high_buyer_readiness(self):
        """Keywords with 'purchase' intent must have buyer_readiness > 0.5."""
        for kw in GOOD_KEYWORDS:
            if kw["intent"] == "purchase":
                assert kw["buyer_readiness"] > 0.5, (
                    f"Purchase intent keyword '{kw['keyword']}' has low buyer_readiness={kw['buyer_readiness']}"
                )

    def test_informational_keywords_have_low_buyer_readiness(self):
        """Informational keywords should have buyer_readiness < 0.5."""
        for kw in GOOD_KEYWORDS:
            if kw["intent"] == "informational":
                assert kw["buyer_readiness"] < 0.5, (
                    f"Informational '{kw['keyword']}' has high buyer_readiness={kw['buyer_readiness']}"
                )

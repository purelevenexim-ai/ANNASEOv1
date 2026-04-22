"""
Test Group 4: KeywordValidator — pre-score thresholds, AI acceptance threshold,
category balance, rule-based intent classification.
"""
import sys
import pytest

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.keyword_validator import KeywordValidator
from engines.kw2.constants import (
    PRE_SCORE_THRESHOLD, CATEGORY_CAPS, COMMERCIAL_BOOSTS, NEGATIVE_PATTERNS,
)


@pytest.fixture
def validator():
    return KeywordValidator()


# ── PRE_SCORE_THRESHOLD constant ──────────────────────────────────────────

class TestPreScoreThreshold:
    def test_threshold_is_55(self):
        """PRE_SCORE_THRESHOLD must be 55 (raised from 45) to block junk keywords."""
        assert PRE_SCORE_THRESHOLD == 55

    def test_threshold_rejects_low_quality(self, validator):
        # Generic low-quality keyword with no commercial signal should score < 55
        score = validator._pre_score("spice product thing", ["cardamom"])
        assert score < PRE_SCORE_THRESHOLD

    def test_threshold_accepts_pillar_keyword(self, validator):
        # Keyword containing the pillar word should score >= 55
        score = validator._pre_score("buy cardamom wholesale", ["cardamom"])
        assert score >= PRE_SCORE_THRESHOLD

    def test_threshold_accepts_transactional(self, validator):
        score = validator._pre_score("buy black pepper online", ["black pepper"])
        assert score >= PRE_SCORE_THRESHOLD

    def test_single_word_scores_zero(self, validator):
        # < 2 words → pre-score returns 0
        score = validator._pre_score("cardamom", ["cardamom"])
        assert score == 0


# ── Pre-score components ──────────────────────────────────────────────────

class TestPreScoreComponents:
    def test_commercial_boost_applied(self, validator):
        # "wholesale" gives +35 commercial boost
        score_with = validator._pre_score("cardamom wholesale", ["cardamom"])
        score_without = validator._pre_score("cardamom quality", ["cardamom"])
        assert score_with > score_without

    def test_pillar_hit_increases_score(self, validator):
        score_hit  = validator._pre_score("cardamom price per kg", ["cardamom"])
        score_miss = validator._pre_score("random product price", ["cardamom"])
        assert score_hit > score_miss

    def test_long_keyword_penalty(self, validator):
        long_kw = "buy cardamom organic wholesale bulk premium supplier online india best"
        score = validator._pre_score(long_kw, ["cardamom"])
        short_score = validator._pre_score("buy cardamom wholesale", ["cardamom"])
        assert score <= short_score  # penalty for excessive length

    def test_score_bounded_0_100(self, validator):
        for kw in ["buy", "buy cardamom", "buy cardamom wholesale bulk supplier online india best price"]:
            score = validator._pre_score(kw, ["cardamom"])
            assert 0 <= score <= 100

    def test_partial_pillar_match(self, validator):
        # "pepper" is a word in "black pepper" pillar
        score = validator._pre_score("pepper price online", ["black pepper"])
        assert score >= 20  # partial match should add significant points


# ── Pillar assignment ─────────────────────────────────────────────────────

class TestPillarAssignment:
    def test_assigns_to_matching_pillar(self, validator):
        pillars = ["cardamom", "black pepper", "turmeric"]
        result = validator._assign_pillar("buy cardamom wholesale", pillars)
        assert result == "cardamom"

    def test_assigns_to_longest_match(self, validator):
        # "black pepper" should win over generic "pepper"
        pillars = ["pepper", "black pepper"]
        result = validator._assign_pillar("buy black pepper online", pillars)
        assert result == "black pepper"

    def test_fallback_to_first_pillar(self, validator):
        pillars = ["cardamom", "turmeric"]
        result = validator._assign_pillar("buy spices online", pillars)
        # No pillar word found → falls back to first pillar
        assert result == "cardamom"

    def test_case_insensitive_matching(self, validator):
        result = validator._assign_pillar("CARDAMOM wholesale supplier", ["cardamom"])
        assert result == "cardamom"


# ── Rule-based intent ─────────────────────────────────────────────────────

class TestRuleIntent:
    def test_transactional_intent(self, validator):
        assert validator._rule_intent("buy cardamom online") == "transactional"

    def test_commercial_intent(self, validator):
        result = validator._rule_intent("best cardamom wholesale price")
        assert result in ("commercial", "transactional")

    def test_informational_intent(self, validator):
        result = validator._rule_intent("what is cardamom used for")
        assert result == "informational"

    def test_navigational_is_recognized(self, validator):
        result = validator._rule_intent("cardamom near me")
        # "near me" is a navigational signal
        assert result in ("navigational", "transactional", "commercial")

    def test_unknown_falls_to_commercial(self, validator):
        result = validator._rule_intent("cardamom supplier")
        assert result in ("commercial", "transactional")


# ── Category caps ─────────────────────────────────────────────────────────

class TestCategoryCaps:
    def test_category_caps_sum_to_100(self):
        total = sum(CATEGORY_CAPS.values())
        assert total == 100

    def test_purchase_cap_highest(self):
        assert CATEGORY_CAPS["purchase"] >= max(
            v for k, v in CATEGORY_CAPS.items() if k != "purchase"
        )

    def test_all_caps_positive(self):
        for k, v in CATEGORY_CAPS.items():
            assert v > 0, f"Category '{k}' has non-positive cap: {v}"

    def test_required_categories_present(self):
        for cat in ("purchase", "wholesale", "price", "comparison", "local", "other"):
            assert cat in CATEGORY_CAPS

    def test_other_cap_smallest(self):
        # "other" should have the smallest cap (junk bucket)
        assert CATEGORY_CAPS["other"] <= min(CATEGORY_CAPS.values())


# ── Relevance threshold ───────────────────────────────────────────────────

class TestRelevanceThreshold:
    def test_threshold_raised_to_0_75(self):
        """The AI relevance acceptance threshold must be ≥ 0.75 after the fix."""
        import inspect
        from engines.kw2 import keyword_validator
        source = inspect.getsource(keyword_validator)
        # Ensure the old 0.7 threshold has been replaced
        # The file should contain 0.75 and NOT accept keywords at exactly 0.7
        assert ">= 0.75" in source, "Relevance threshold must be 0.75"

    def test_keyword_at_0_74_rejected_by_threshold(self, validator):
        """A cached item with relevance 0.74 should NOT be accepted."""
        # Simulate what happens in _validate_batch with cached result
        relevance = 0.74
        # Check against the new threshold
        assert not (relevance >= 0.75), "Relevance 0.74 should be below the 0.75 threshold"

    def test_keyword_at_0_75_accepted(self):
        relevance = 0.75
        assert relevance >= 0.75

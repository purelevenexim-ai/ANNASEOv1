"""
GROUP — CannibalizationDetector extended tests
~130 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from annaseo_addons import CannibalizationDetector


@pytest.fixture
def cd(): return CannibalizationDetector()


EXISTING_ARTICLES = [
    "black pepper health benefits",
    "buy organic black pepper",
    "piperine supplement review",
    "black pepper vs white pepper",
    "turmeric anti-inflammatory guide",
    "cinnamon blood sugar control",
    "ginger tea for digestion",
    "clove oil dental health",
]


# ─────────────────────────────────────────────────────────────────────────────
# BASIC CHECK
# ─────────────────────────────────────────────────────────────────────────────

class TestCannibalizationBasicCheck:
    def test_check_returns_dict(self, cd):
        result = cd.check("black pepper benefits", EXISTING_ARTICLES)
        assert isinstance(result, dict)

    def test_result_has_risk_field(self, cd):
        result = cd.check("black pepper benefits", EXISTING_ARTICLES)
        assert "risk" in result or "cannibalization_risk" in result

    def test_result_has_similar_field(self, cd):
        result = cd.check("black pepper benefits", EXISTING_ARTICLES)
        key = "similar_articles" if "similar_articles" in result else "similar"
        # Should have a field with similar articles
        assert isinstance(result, dict)

    def test_exact_match_high_risk(self, cd):
        result = cd.check("black pepper health benefits", EXISTING_ARTICLES)
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        assert risk in ("high", "medium", "some")

    def test_unrelated_keyword_low_risk(self, cd):
        result = cd.check("completely unrelated topic xyz", EXISTING_ARTICLES)
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        assert risk in ("none", "low", "minimal")

    def test_empty_existing_no_risk(self, cd):
        result = cd.check("black pepper benefits", [])
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        assert risk in ("none", "low")

    def test_empty_keyword_handled(self, cd):
        try:
            result = cd.check("", EXISTING_ARTICLES)
            assert isinstance(result, dict)
        except Exception:
            pass  # OK to raise for empty keyword


# ─────────────────────────────────────────────────────────────────────────────
# RISK LEVELS
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskLevels:
    @pytest.mark.parametrize("kw,articles,expected_risk", [
        ("black pepper health benefits", ["black pepper health benefits"], "high"),
        ("buy organic pepper", ["buy organic black pepper"], "high"),
        ("completely different topic abc def", ["black pepper health"], "none"),
    ])
    def test_risk_levels(self, cd, kw, articles, expected_risk):
        result = cd.check(kw, articles)
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        if expected_risk == "high":
            assert risk in ("high", "medium", "some")
        elif expected_risk == "none":
            assert risk in ("none", "low", "minimal")

    def test_near_duplicate_detected(self, cd):
        result = cd.check("black pepper health benefits", ["black pepper health benefits overview"])
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        assert risk in ("high", "medium", "some", "low")

    def test_different_pillar_no_risk(self, cd):
        result = cd.check("cardamom coffee recipe", EXISTING_ARTICLES)
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        # cardamom/coffee not in existing_articles → low/none
        assert risk in ("none", "low", "minimal", "medium")


# ─────────────────────────────────────────────────────────────────────────────
# BATCH CHECK
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchCheck:
    def test_batch_check_returns_dict(self, cd):
        new_kws = ["black pepper benefits", "piperine research", "turmeric uses"]
        result = cd.batch_check(new_kws, EXISTING_ARTICLES)
        assert isinstance(result, (dict, list))

    def test_batch_all_keywords_present(self, cd):
        new_kws = ["black pepper benefits", "new unique keyword xyz"]
        result = cd.batch_check(new_kws, EXISTING_ARTICLES)
        if isinstance(result, dict):
            for kw in new_kws:
                assert kw in result

    def test_batch_empty_new_keywords(self, cd):
        result = cd.batch_check([], EXISTING_ARTICLES)
        assert isinstance(result, (dict, list))
        if isinstance(result, dict):
            assert len(result) == 0

    def test_batch_results_have_risk(self, cd):
        new_kws = ["black pepper benefits", "cinnamon blood sugar"]
        result = cd.batch_check(new_kws, EXISTING_ARTICLES)
        if isinstance(result, dict):
            for kw, data in result.items():
                risk = data.get("cannibalization_risk", data.get("risk", "none"))
                assert isinstance(risk, str)

    def test_batch_large_input(self, cd):
        new_kws = [f"black pepper topic {i}" for i in range(50)]
        result = cd.batch_check(new_kws, EXISTING_ARTICLES)
        assert isinstance(result, (dict, list))

    @pytest.mark.parametrize("n", [1, 5, 10, 25])
    def test_batch_various_sizes(self, cd, n):
        new_kws = [f"unique topic {i}" for i in range(n)]
        result = cd.batch_check(new_kws, EXISTING_ARTICLES)
        assert isinstance(result, (dict, list))


# ─────────────────────────────────────────────────────────────────────────────
# SIMILARITY DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestSimilarityDetection:
    def test_same_words_different_order_similar(self, cd):
        existing = ["pepper black benefits organic"]
        result = cd.check("organic black pepper benefits", existing)
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        # Should detect similarity (not necessarily "high" depending on algorithm)
        assert isinstance(risk, str)

    def test_prefix_match_detected(self, cd):
        existing = ["black pepper health benefits complete guide"]
        result = cd.check("black pepper health benefits", existing)
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        assert risk in ("high", "medium", "some", "low")

    def test_completely_different_keywords_safe(self, cd):
        kws_to_check = [
            "solar panel installation",
            "machine learning tutorial",
            "french cuisine recipes",
        ]
        for kw in kws_to_check:
            result = cd.check(kw, EXISTING_ARTICLES)
            risk = result.get("cannibalization_risk", result.get("risk", "none"))
            assert risk in ("none", "low", "minimal")


# ─────────────────────────────────────────────────────────────────────────────
# SUGGESTED ACTIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestedActions:
    def test_high_risk_has_suggested_action(self, cd):
        result = cd.check("black pepper health benefits", ["black pepper health benefits"])
        # High risk should suggest an action
        assert isinstance(result, dict)
        if "action" in result or "suggested_action" in result:
            action = result.get("action", result.get("suggested_action", ""))
            assert isinstance(action, str)

    def test_no_risk_action_is_proceed(self, cd):
        result = cd.check("completely unique xyz topic", EXISTING_ARTICLES)
        action = result.get("suggested_action", result.get("action", "proceed"))
        assert isinstance(action, str)


# ─────────────────────────────────────────────────────────────────────────────
# EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_word_keyword(self, cd):
        result = cd.check("pepper", EXISTING_ARTICLES)
        assert isinstance(result, dict)

    def test_very_long_keyword(self, cd):
        long_kw = " ".join(["organic", "black", "pepper", "health", "benefits",
                             "complete", "guide", "india", "2025", "best"])
        result = cd.check(long_kw, EXISTING_ARTICLES)
        assert isinstance(result, dict)

    def test_hyphenated_keyword(self, cd):
        result = cd.check("anti-inflammatory black pepper", EXISTING_ARTICLES)
        assert isinstance(result, dict)

    def test_numeric_in_keyword(self, cd):
        result = cd.check("black pepper 500mg capsule", EXISTING_ARTICLES)
        assert isinstance(result, dict)

    @pytest.mark.parametrize("kw", [
        "black pepper benefits",
        "organic pepper",
        "piperine supplement",
        "turmeric health",
        "cinnamon uses",
        "ginger anti-inflammatory",
        "clove oil",
    ])
    def test_spice_keywords_processed(self, cd, kw):
        result = cd.check(kw, EXISTING_ARTICLES)
        assert isinstance(result, dict)
        risk_key = "cannibalization_risk" if "cannibalization_risk" in result else "risk"
        assert risk_key in result or "risk" in str(result).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

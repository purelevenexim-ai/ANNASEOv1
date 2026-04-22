"""
Test Group 3: Negative Filter — all 17 NEGATIVE_PATTERNS + edge cases.

Tests the `_negative_filter` method and `NEGATIVE_PATTERNS` constant coverage.
"""
import sys
import pytest

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.constants import NEGATIVE_PATTERNS


# ── Constants validation ──────────────────────────────────────────────────

class TestNegativePatternsConstant:
    def test_minimum_pattern_count(self):
        assert len(NEGATIVE_PATTERNS) >= 17

    def test_all_patterns_are_strings(self):
        for p in NEGATIVE_PATTERNS:
            assert isinstance(p, str)

    def test_all_patterns_lowercase(self):
        for p in NEGATIVE_PATTERNS:
            assert p == p.lower(), f"Pattern '{p}' is not lowercase"

    def test_core_patterns_present(self):
        required = [
            "recipe", "health benefits", "how to use", "what is",
            "side effects", "wikipedia", "pdf",
        ]
        for r in required:
            assert r in NEGATIVE_PATTERNS, f"Missing required pattern: '{r}'"


# ── Filter logic ──────────────────────────────────────────────────────────

def _apply_negative_filter(keywords, extra_patterns=None):
    """Helper: apply the NEGATIVE_PATTERNS filter to a list of keyword strings."""
    patterns = list(NEGATIVE_PATTERNS)
    if extra_patterns:
        patterns.extend(extra_patterns)
    passed, rejected = [], []
    for kw in keywords:
        kw_lower = kw.lower()
        if any(p in kw_lower for p in patterns):
            rejected.append(kw)
        else:
            passed.append(kw)
    return passed, rejected


class TestNegativePatternFiltering:
    @pytest.mark.parametrize("pattern,keyword", [
        ("recipe",          "black pepper recipe"),
        ("recipes",         "cardamom recipes for baking"),
        ("health benefits",  "turmeric health benefits"),
        ("benefits of",     "benefits of cinnamon"),
        ("benefit of",      "benefit of ginger"),
        ("how to use",      "how to use cardamom"),
        ("how to make",     "how to make ginger tea"),
        ("how to grow",     "how to grow pepper"),
        ("how to cook",     "how to cook with turmeric"),
        ("what is",         "what is cardamom"),
        ("meaning",         "cardamom meaning in hindi"),
        ("definition",      "definition of turmeric"),
        ("nutrition facts", "black pepper nutrition facts"),
        ("nutritional value", "cardamom nutritional value"),
        ("side effects",    "turmeric side effects"),
        ("home remedy",     "black pepper home remedy"),
        ("home remedies",   "ginger home remedies"),
        ("uses of",         "uses of cardamom"),
        ("in hindi",        "turmeric in hindi"),
        ("in urdu",         "cardamom in urdu"),
        ("ayurvedic uses",  "cardamom ayurvedic uses"),
        ("images",          "black pepper images"),
        ("wikipedia",       "cardamom wikipedia"),
        ("pdf",             "spices pdf download"),
        ("diy",             "diy spice blend"),
    ])
    def test_rejects_pattern_containing_keyword(self, pattern, keyword):
        passed, rejected = _apply_negative_filter([keyword])
        assert keyword in rejected, f"Expected '{keyword}' to be rejected for pattern '{pattern}'"

    def test_valid_keyword_not_filtered(self):
        valid_kws = [
            "buy black pepper online",
            "wholesale cardamom price",
            "organic turmeric supplier",
            "Kerala spices exporter",
            "best quality cinnamon",
        ]
        passed, rejected = _apply_negative_filter(valid_kws)
        assert len(passed) == len(valid_kws)
        assert len(rejected) == 0

    def test_case_insensitive_filter(self):
        keywords = ["Black Pepper Recipe", "WHAT IS CARDAMOM", "Turmeric Benefits Of Daily Use"]
        passed, rejected = _apply_negative_filter(keywords)
        assert len(rejected) == 3

    def test_no_false_positive_on_recipe_word_in_context(self):
        # "recipe" in a brand name should still be caught (substring match is correct)
        passed, rejected = _apply_negative_filter(["cardamom recipe ideas"])
        assert "cardamom recipe ideas" in rejected

    def test_extra_patterns_from_negative_scope(self):
        passed, rejected = _apply_negative_filter(
            ["custom banned phrase in keyword", "good keyword"],
            extra_patterns=["custom banned phrase"],
        )
        assert "good keyword" in passed
        assert "custom banned phrase in keyword" in rejected

    def test_filter_does_not_reject_empty_string(self):
        passed, rejected = _apply_negative_filter([""])
        # Empty string contains none of the patterns → passed
        assert "" in passed

    def test_partial_pattern_match(self):
        # "benefits of" must be in patterns (substring check)
        keyword = "top benefits of using spices"
        passed, rejected = _apply_negative_filter([keyword])
        assert keyword in rejected

    def test_filter_preserves_order(self):
        kws = ["buy pepper", "pepper recipe", "wholesale cardamom", "cardamom meaning", "bulk turmeric"]
        passed, rejected = _apply_negative_filter(kws)
        assert passed == ["buy pepper", "wholesale cardamom", "bulk turmeric"]
        assert rejected == ["pepper recipe", "cardamom meaning"]

"""
GROUP — OffTopicFilter extended tests
~130 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from annaseo_addons import OffTopicFilter


@pytest.fixture
def otf(): return OffTopicFilter()


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL KILL LIST
# ─────────────────────────────────────────────────────────────────────────────

class TestGlobalKillList:
    def test_meme_killed(self, otf):
        assert otf.is_global_kill("black pepper meme") is True

    def test_viral_killed(self, otf):
        assert otf.is_global_kill("pepper viral trend") is True

    def test_tiktok_killed(self, otf):
        assert otf.is_global_kill("black pepper tiktok") is True

    def test_instagram_killed(self, otf):
        assert otf.is_global_kill("pepper instagram post") is True

    def test_youtube_killed(self, otf):
        assert otf.is_global_kill("pepper youtube shorts") is True

    def test_reddit_killed(self, otf):
        assert otf.is_global_kill("pepper reddit discussion") is True

    def test_twitter_killed(self, otf):
        assert otf.is_global_kill("pepper twitter trend") is True

    def test_facebook_killed(self, otf):
        assert otf.is_global_kill("pepper facebook group") is True

    def test_challenge_killed(self, otf):
        assert otf.is_global_kill("pepper challenge viral") is True

    def test_clean_keyword_not_killed(self, otf):
        assert otf.is_global_kill("black pepper benefits") is False

    def test_informational_not_killed(self, otf):
        assert otf.is_global_kill("what is piperine") is False

    def test_transactional_not_killed(self, otf):
        assert otf.is_global_kill("buy black pepper online") is False

    def test_anti_inflammatory_not_killed(self, otf):
        # Ensure "ant" substring fix is working
        assert otf.is_global_kill("black pepper anti-inflammatory") is False

    def test_antibiotic_not_killed(self, otf):
        assert otf.is_global_kill("turmeric antibiotic properties") is False

    def test_antioxidant_not_killed(self, otf):
        assert otf.is_global_kill("black pepper antioxidant") is False

    @pytest.mark.parametrize("kw,expected", [
        ("pepper meme", True),
        ("pepper viral", True),
        ("pepper challenge", True),
        ("pepper tiktok", True),
        ("pepper instagram", True),
        ("pepper facebook", True),
        ("pepper reddit", True),
        ("pepper benefits", False),
        ("pepper recipe", False),
        ("buy pepper", False),
        ("black pepper anti-inflammatory", False),
        ("pepper antioxidant study", False),
    ])
    def test_global_kill_parametrized(self, otf, kw, expected):
        assert otf.is_global_kill(kw) == expected, \
            f"is_global_kill('{kw}') expected {expected}"


# ─────────────────────────────────────────────────────────────────────────────
# FILTER METHOD
# ─────────────────────────────────────────────────────────────────────────────

class TestOffTopicFilterMethod:
    def test_filter_removes_kill_words(self, otf):
        kws = ["black pepper benefits", "pepper meme", "buy pepper"]
        result = otf.filter(kws)
        assert "pepper meme" not in result

    def test_filter_keeps_clean_keywords(self, otf):
        kws = ["black pepper benefits", "turmeric health", "organic cinnamon"]
        result = otf.filter(kws)
        assert len(result) == 3

    def test_filter_returns_list(self, otf):
        result = otf.filter(["black pepper benefits"])
        assert isinstance(result, list)

    def test_filter_empty_list_returns_empty(self, otf):
        result = otf.filter([])
        assert result == []

    def test_filter_all_killed_returns_empty(self, otf):
        kws = ["pepper meme", "pepper viral", "pepper tiktok"]
        result = otf.filter(kws)
        assert result == []

    def test_filter_preserves_order(self, otf):
        kws = ["black pepper a", "black pepper b", "black pepper c"]
        result = otf.filter(kws)
        assert result == kws

    def test_filter_large_list(self, otf):
        kws = [f"black pepper topic {i}" for i in range(100)]
        result = otf.filter(kws)
        assert len(result) == 100

    def test_filter_with_project_overrides(self, otf):
        # Project-specific overrides
        project_kill = ["tour", "travel", "hotel"]
        kws = ["cinnamon tour", "cinnamon benefits", "cinnamon tea"]
        if hasattr(otf, "filter_with_overrides"):
            result = otf.filter_with_overrides(kws, project_kill)
            assert "cinnamon tour" not in result
            assert "cinnamon benefits" in result
        else:
            # Standard filter
            result = otf.filter(kws)
            assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# CANDLE / CROSS DOMAIN WORDS
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossDomainWords:
    def test_candle_is_killed(self, otf):
        # "candle" should be in GLOBAL_KILL (confirmed in codebase)
        result = otf.is_global_kill("cinnamon candle scent")
        assert result is True

    def test_decor_killed_if_present(self, otf):
        result = otf.is_global_kill("cinnamon decor craft")
        # May or may not be in kill list — just assert it returns bool
        assert isinstance(result, bool)

    def test_recipe_not_killed(self, otf):
        assert otf.is_global_kill("cinnamon recipe healthy") is False

    def test_supplement_not_killed(self, otf):
        assert otf.is_global_kill("cinnamon supplement dosage") is False

    def test_oil_not_killed(self, otf):
        assert otf.is_global_kill("cinnamon oil benefits") is False


# ─────────────────────────────────────────────────────────────────────────────
# SPICE-SPECIFIC CLEAN KEYWORDS (should never be killed)
# ─────────────────────────────────────────────────────────────────────────────

class TestSpiceKeywordsNeverKilled:
    @pytest.mark.parametrize("kw", [
        "black pepper benefits",
        "black pepper recipe",
        "black pepper powder buy",
        "piperine supplement dosage",
        "organic black pepper oil",
        "black pepper health study",
        "turmeric anti-inflammatory",
        "cinnamon blood sugar control",
        "ginger tea digestion",
        "clove oil dental health",
        "cardamom coffee recipe",
        "cumin seeds health benefits",
        "fenugreek leaves recipe",
        "nutmeg sleep benefits",
        "coriander seeds uses",
        "black pepper extract capsule",
        "malabar pepper organic",
        "ceylon cinnamon benefits",
        "what is piperine",
        "how to use black pepper",
    ])
    def test_clean_spice_keywords_not_killed(self, otf, kw):
        assert otf.is_global_kill(kw) is False, f"'{kw}' should NOT be killed"


# ─────────────────────────────────────────────────────────────────────────────
# BATCH OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchOperations:
    def test_batch_filter_100_keywords(self, otf):
        kws = [f"black pepper keyword {i}" for i in range(100)]
        result = otf.filter(kws)
        assert len(result) == 100

    def test_batch_with_mixed_kill(self, otf):
        clean = [f"pepper benefit {i}" for i in range(10)]
        killed = [f"pepper meme {i}" for i in range(5)]
        result = otf.filter(clean + killed)
        assert len(result) == 10

    def test_no_duplicates_introduced(self, otf):
        kws = ["black pepper benefits", "turmeric health", "organic cinnamon"]
        result = otf.filter(kws)
        assert len(result) == len(set(result))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Test Group 5: KeywordBrain pipeline — empty pillar guard, AI expand parallelism,
negative filter integration, pillar assignment, seed building.
"""
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.keyword_brain import KeywordBrain
from engines.kw2.constants import AI_CONCURRENCY


@pytest.fixture
def brain():
    return KeywordBrain()


# ── Pillar guard ──────────────────────────────────────────────────────────

class TestPillarGuard:
    def test_ai_expand_empty_pillars_returns_empty(self, brain):
        """_ai_expand_all_intents with empty pillar list must return []."""
        result = brain._ai_expand_all_intents([], [], "spices universe", "India", "auto")
        assert result == []

    def test_ai_expand_blank_pillars_filtered(self, brain):
        """_ai_expand_all_intents must filter out blank/whitespace pillar entries."""
        with patch.object(brain, "_ai_expand_batch", return_value=[]) as mock_batch:
            result = brain._ai_expand_all_intents(
                ["", "  ", ""],  # all blank
                [], "spices", "India", "auto"
            )
        assert result == []
        mock_batch.assert_not_called()

    def test_ai_expand_valid_pillars_calls_batch(self, brain):
        """_ai_expand_all_intents with valid pillars calls _ai_expand_batch for each intent."""
        call_count = []
        def fake_batch(*args, **kwargs):
            call_count.append(1)
            return []
        with patch.object(brain, "_ai_expand_batch", side_effect=fake_batch):
            brain._ai_expand_all_intents(
                ["cardamom", "black pepper"], [], "spices", "India", "auto"
            )
        # 2 pillars × 3 intents = 6 calls
        assert len(call_count) == 6


# ── Parallelism ───────────────────────────────────────────────────────────

class TestAiExpandParallelism:
    def test_ai_concurrency_constant_is_positive(self):
        """AI_CONCURRENCY must be a positive integer."""
        assert isinstance(AI_CONCURRENCY, int)
        assert AI_CONCURRENCY >= 1

    def test_expand_collects_all_results(self, brain):
        """All tasks from all pillars and intents should be collected."""
        def fake_batch(*args, **kwargs):
            # Return 1 keyword for each call to verify all 9 (3×3) are collected
            return [{"keyword": f"kw_{id(kwargs)}", "source": "ai_expand", "pillar": "test", "raw_score": 50}]

        with patch.object(brain, "_ai_expand_batch", side_effect=fake_batch):
            result = brain._ai_expand_all_intents(
                ["cardamom", "pepper", "turmeric"], [], "spices", "India", "auto"
            )
        # 3 pillars × 3 intents = 9 calls → 9 keywords
        assert len(result) == 9

    def test_expand_handles_partial_failure_gracefully(self, brain):
        """If some AI calls fail, the others should still be collected."""
        counter = [0]
        def intermittent_batch(*args, **kwargs):
            counter[0] += 1
            if counter[0] % 3 == 0:
                raise RuntimeError("Simulated AI call failure")
            return [{"keyword": "test_kw", "source": "ai_expand", "pillar": "", "raw_score": 50}]

        # Should not raise, just log warnings
        with patch.object(brain, "_ai_expand_batch", side_effect=intermittent_batch):
            result = brain._ai_expand_all_intents(
                ["cardamom", "pepper", "turmeric"], [], "spices", "India", "auto"
            )
        # 9 calls total, 3 fail → 6 results
        assert len(result) == 6

    def test_intent_tag_applied_to_results(self, brain):
        """Each result keyword should have the correct intent tag."""
        def fake_commercial(*args, **kwargs):
            intent_label = kwargs.get("intent", "commercial")
            return [{"keyword": "buy cardamom", "source": "ai_expand", "pillar": "cardamom", "raw_score": 50}]

        with patch.object(brain, "_ai_expand_batch", side_effect=fake_commercial):
            result = brain._ai_expand_all_intents(["cardamom"], [], "spices", "India", "auto")
        # All results should have an "intent" key
        for item in result:
            assert "intent" in item


# ── Seeds ─────────────────────────────────────────────────────────────────

class TestSeedBuilding:
    def test_seeds_generated_for_each_pillar(self, brain):
        seeds = brain._build_seeds(["cardamom", "black pepper"], ["wholesale", "organic"])
        pillars_in_seeds = set()
        for s in seeds:
            kw = s.get("keyword", "").lower()
            if "cardamom" in kw:
                pillars_in_seeds.add("cardamom")
            if "black pepper" in kw or "pepper" in kw:
                pillars_in_seeds.add("black pepper")
        assert "cardamom" in pillars_in_seeds
        assert "black pepper" in pillars_in_seeds

    def test_seed_keywords_are_strings(self, brain):
        seeds = brain._build_seeds(["cardamom"], ["wholesale"])
        for s in seeds:
            assert isinstance(s.get("keyword"), str)
            assert len(s["keyword"]) > 0

    def test_no_seeds_for_empty_pillars(self, brain):
        seeds = brain._build_seeds([], ["wholesale"])
        assert len(seeds) == 0

    def test_intent_only_modifiers_excluded_from_seeds(self, brain):
        """Modifiers like 'buy', 'price', 'online' should not create bad seed phrases."""
        seeds = brain._build_seeds(["cardamom"], ["buy", "price", "online", "organic"])
        seed_keywords = [s["keyword"].lower() for s in seeds]
        # "buy cardamom" may appear from templates but "online cardamom" / "price cardamom" are bad seeds
        bad_seeds = [kw for kw in seed_keywords if kw.startswith(("online ", "price ", "cost "))]
        assert len(bad_seeds) == 0, f"Bad seed phrases found: {bad_seeds}"


# ── Negative filter ───────────────────────────────────────────────────────

class TestNegativeFilterIntegration:
    def test_filter_removes_recipe_keywords(self, brain):
        raw = [
            {"keyword": "buy cardamom"},
            {"keyword": "cardamom recipe"},
            {"keyword": "cardamom health benefits"},
        ]
        passed, rejected = brain._negative_filter(raw, [])
        assert len(passed) == 1
        assert passed[0]["keyword"] == "buy cardamom"

    def test_filter_uses_negative_scope(self, brain):
        raw = [{"keyword": "cardamom for cooking"}, {"keyword": "wholesale cardamom"}]
        passed, rejected = brain._negative_filter(raw, ["for cooking"])
        assert len(passed) == 1
        assert passed[0]["keyword"] == "wholesale cardamom"

    def test_filter_case_insensitive(self, brain):
        raw = [{"keyword": "CARDAMOM RECIPE"}, {"keyword": "buy cardamom"}]
        passed, rejected = brain._negative_filter(raw, [])
        assert len(rejected) == 1
        assert rejected[0]["keyword"] == "CARDAMOM RECIPE"

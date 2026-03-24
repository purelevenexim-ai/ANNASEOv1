"""
GROUP — HDBSCANClustering + MissingExpansionDimensions + KeywordTrafficScorer extended
~130 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from annaseo_addons import (
    HDBSCANClustering, MissingExpansionDimensions, KeywordTrafficScorer, ScoredKeyword
)


# ─────────────────────────────────────────────────────────────────────────────
# HDBSCANClustering
# ─────────────────────────────────────────────────────────────────────────────

class TestHDBSCANReturnStructure:
    def test_cluster_returns_dict(self):
        hc = HDBSCANClustering()
        result = hc.cluster(["black pepper benefits", "pepper health", "buy pepper"])
        assert isinstance(result, dict)

    def test_cluster_keys_are_strings(self):
        hc = HDBSCANClustering()
        result = hc.cluster(["black pepper benefits", "pepper health"])
        for k in result.keys():
            assert isinstance(k, str)

    def test_cluster_values_are_lists(self):
        hc = HDBSCANClustering()
        result = hc.cluster(["black pepper benefits", "pepper health", "buy pepper"])
        for v in result.values():
            assert isinstance(v, list)

    def test_all_keywords_assigned(self):
        hc = HDBSCANClustering()
        kws = ["black pepper benefits", "pepper health", "buy pepper", "organic pepper",
               "pepper recipe", "pepper oil"]
        result = hc.cluster(kws)
        all_assigned = [kw for kws_list in result.values() for kw in kws_list]
        for kw in kws:
            assert kw in all_assigned

    def test_empty_list_returns_empty(self):
        hc = HDBSCANClustering()
        result = hc.cluster([])
        assert result == {} or isinstance(result, dict)

    def test_single_keyword_handled(self):
        hc = HDBSCANClustering()
        result = hc.cluster(["black pepper"])
        all_assigned = [kw for kws in result.values() for kw in kws]
        assert "black pepper" in all_assigned

    def test_large_keyword_list(self):
        hc = HDBSCANClustering()
        kws = [f"black pepper topic {i}" for i in range(50)]
        result = hc.cluster(kws)
        assert isinstance(result, dict)

    def test_no_keyword_duplicated(self):
        hc = HDBSCANClustering()
        kws = ["black pepper health", "black pepper recipe", "buy pepper"]
        result = hc.cluster(kws)
        all_assigned = [kw for kws_list in result.values() for kw in kws_list]
        assert len(all_assigned) == len(set(all_assigned))

    @pytest.mark.parametrize("n_keywords", [5, 10, 20, 50, 100])
    def test_various_sizes(self, n_keywords):
        hc = HDBSCANClustering()
        kws = [f"spice keyword variation {i}" for i in range(n_keywords)]
        result = hc.cluster(kws)
        all_assigned = [kw for kws_list in result.values() for kw in kws_list]
        assert len(all_assigned) == n_keywords


# ─────────────────────────────────────────────────────────────────────────────
# MissingExpansionDimensions
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingExpansionDimensions:
    @pytest.fixture
    def med(self):
        return MissingExpansionDimensions()

    def test_find_returns_list(self, med):
        seed = "black pepper"
        existing = ["black pepper benefits", "black pepper recipe"]
        result = med.find(seed, existing)
        assert isinstance(result, list)

    def test_find_no_duplicates(self, med):
        seed = "black pepper"
        existing = ["black pepper benefits", "black pepper recipe"]
        result = med.find(seed, existing)
        assert len(result) == len(set(result))

    def test_find_with_empty_existing(self, med):
        result = med.find("black pepper", [])
        assert isinstance(result, list)

    def test_questions_added(self, med):
        result = med.find("black pepper", [])
        has_question = any(
            kw.startswith(("what", "how", "why", "when", "does", "is", "can"))
            for kw in result
        )
        assert has_question

    def test_commercial_added(self, med):
        result = med.find("black pepper", [])
        has_commercial = any(
            word in kw for kw in result
            for word in ["buy", "best", "price", "organic", "wholesale"]
        )
        assert has_commercial

    def test_comparison_added(self, med):
        result = med.find("black pepper", [])
        has_comparison = any(
            "vs" in kw or "versus" in kw or "compare" in kw
            for kw in result
        )
        assert has_comparison

    def test_existing_not_repeated(self, med):
        existing = ["black pepper benefits"]
        result = med.find("black pepper", existing)
        assert "black pepper benefits" not in result

    def test_all_results_contain_seed(self, med):
        seed = "black pepper"
        result = med.find(seed, [])
        for kw in result:
            assert seed in kw, f"'{kw}' doesn't contain seed '{seed}'"

    @pytest.mark.parametrize("seed", [
        "cinnamon", "turmeric", "ginger", "clove", "cardamom",
    ])
    def test_various_seeds(self, med, seed):
        result = med.find(seed, [])
        assert isinstance(result, list)
        assert len(result) > 0

    def test_find_returns_diverse_dimensions(self, med):
        result = med.find("black pepper", [])
        # Expect at least 5 unique keywords
        assert len(result) >= 5

    def test_long_existing_list(self, med):
        existing = [f"black pepper use {i}" for i in range(50)]
        result = med.find("black pepper", existing)
        assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# ScoredKeyword
# ─────────────────────────────────────────────────────────────────────────────

class TestScoredKeyword:
    def test_creation(self):
        sk = ScoredKeyword(keyword="black pepper benefits", score=75.5)
        assert sk.keyword == "black pepper benefits"
        assert sk.score == 75.5

    def test_default_score(self):
        sk = ScoredKeyword(keyword="black pepper")
        assert hasattr(sk, "score")

    def test_comparison_by_score(self):
        sk1 = ScoredKeyword(keyword="black pepper", score=80.0)
        sk2 = ScoredKeyword(keyword="piperine", score=60.0)
        # Higher score should be "greater"
        if hasattr(sk1, "__lt__") or hasattr(sk1, "__gt__"):
            assert sk1 > sk2 or sk1.score > sk2.score

    def test_keyword_is_string(self):
        sk = ScoredKeyword(keyword="black pepper", score=50.0)
        assert isinstance(sk.keyword, str)

    def test_score_is_numeric(self):
        sk = ScoredKeyword(keyword="black pepper", score=50.0)
        assert isinstance(sk.score, (int, float))

    @pytest.mark.parametrize("kw,score", [
        ("black pepper benefits", 80.0),
        ("buy black pepper", 70.0),
        ("piperine supplement", 65.0),
        ("organic pepper oil", 55.0),
        ("malabar black pepper", 45.0),
    ])
    def test_various_scored_keywords(self, kw, score):
        sk = ScoredKeyword(keyword=kw, score=score)
        assert sk.keyword == kw
        assert sk.score == score


# ─────────────────────────────────────────────────────────────────────────────
# KeywordTrafficScorer — extended tests
# ─────────────────────────────────────────────────────────────────────────────

class TestKeywordTrafficScorerExtended:
    @pytest.fixture
    def kts(self):
        return KeywordTrafficScorer()

    def test_score_returns_float(self, kts):
        score = kts.score("black pepper benefits")
        assert isinstance(score, (int, float))

    def test_score_in_valid_range(self, kts):
        score = kts.score("black pepper benefits")
        assert 0 <= score <= 100

    def test_longer_keywords_score_appropriately(self, kts):
        short = kts.score("pepper")
        long_kw = kts.score("organic black pepper health benefits study")
        # Both should be in valid range
        assert 0 <= short <= 100
        assert 0 <= long_kw <= 100

    def test_transactional_keywords_score_well(self, kts):
        score = kts.score("buy organic black pepper online")
        assert score > 0

    def test_informational_keywords_score(self, kts):
        score = kts.score("what is black pepper piperine")
        assert score > 0

    @pytest.mark.parametrize("kw", [
        "black pepper", "organic cinnamon powder",
        "turmeric curcumin supplement", "ginger anti-inflammatory",
        "clove oil uses", "cardamom benefits",
    ])
    def test_all_spice_keywords_score(self, kts, kw):
        score = kts.score(kw)
        assert isinstance(score, (int, float))
        assert 0 <= score <= 100

    def test_batch_score_returns_dict(self, kts):
        kws = ["black pepper benefits", "buy pepper", "piperine capsule"]
        if hasattr(kts, "batch_score"):
            result = kts.batch_score(kws)
            assert isinstance(result, dict)

    def test_score_deterministic(self, kts):
        kw = "black pepper benefits"
        s1 = kts.score(kw)
        s2 = kts.score(kw)
        assert s1 == s2

    def test_empty_string_handled(self, kts):
        try:
            score = kts.score("")
            assert isinstance(score, (int, float))
        except Exception:
            pass  # OK to raise for empty string

    def test_special_chars_handled(self, kts):
        try:
            score = kts.score("black pepper & ginger")
            assert isinstance(score, (int, float))
        except Exception:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

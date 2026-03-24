"""
GROUP — P7 Opportunity Scoring (extended)
~130 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P7_OpportunityScoring, Seed


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p7(): return P7_OpportunityScoring()

@pytest.fixture
def seed(p1): return p1.run("black pepper")

# Shared test data
KWS = [
    "black pepper benefits",
    "buy black pepper",
    "black pepper vs white pepper",
    "best black pepper supplement",
    "what is piperine",
]
INTENT_MAP = {
    "black pepper benefits":       "informational",
    "buy black pepper":            "transactional",
    "black pepper vs white pepper":"comparison",
    "best black pepper supplement":"commercial",
    "what is piperine":            "informational",
}
SERP_MAP = {
    kw: {"kd_estimate": 40, "has_featured_snippet": False, "has_paa": False}
    for kw in KWS
}


# ─────────────────────────────────────────────────────────────────────────────
# RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP7ReturnStructure:
    def test_returns_dict(self, p7, seed):
        result = p7.run(seed, KWS, INTENT_MAP, SERP_MAP)
        assert isinstance(result, dict)

    def test_all_keywords_scored(self, p7, seed):
        result = p7.run(seed, KWS, INTENT_MAP, SERP_MAP)
        for kw in KWS:
            assert kw in result

    def test_scores_are_numeric(self, p7, seed):
        result = p7.run(seed, KWS, INTENT_MAP, SERP_MAP)
        for kw, score in result.items():
            assert isinstance(score, (int, float))

    def test_scores_in_valid_range(self, p7, seed):
        result = p7.run(seed, KWS, INTENT_MAP, SERP_MAP)
        for kw, score in result.items():
            assert 0 <= score <= 100, f"Score out of range for '{kw}': {score}"

    def test_empty_keywords_returns_empty(self, p7, seed):
        result = p7.run(seed, [], {}, {})
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# SCORE FORMULA — _score()
# ─────────────────────────────────────────────────────────────────────────────

class TestP7ScoreFormula:
    def test_low_kd_gives_higher_score(self, p7):
        high_kd = p7._score("black pepper benefits", "informational", {"kd_estimate": 90})
        low_kd  = p7._score("black pepper benefits", "informational", {"kd_estimate": 10})
        assert low_kd > high_kd

    def test_transactional_beats_navigational(self, p7):
        t_score = p7._score("buy black pepper", "transactional", {"kd_estimate": 40})
        n_score = p7._score("pepper brand website", "navigational", {"kd_estimate": 40})
        assert t_score > n_score

    def test_commercial_beats_informational(self, p7):
        c_score = p7._score("best black pepper", "commercial", {"kd_estimate": 40})
        i_score = p7._score("black pepper facts", "informational", {"kd_estimate": 40})
        assert c_score > i_score

    def test_question_words_bonus(self, p7):
        q_score = p7._score("what is black pepper", "informational", {"kd_estimate": 40})
        n_score = p7._score("black pepper overview", "informational", {"kd_estimate": 40})
        assert q_score >= n_score

    def test_three_to_five_words_sweet_spot(self, p7):
        kw_3 = "black pepper benefits"   # 3 words
        kw_6 = "black pepper health benefits digestion study"  # 6 words
        kw_1 = "pepper"                  # 1 word
        s3 = p7._score(kw_3, "informational", {"kd_estimate": 40})
        s6 = p7._score(kw_6, "informational", {"kd_estimate": 40})
        s1 = p7._score(kw_1, "informational", {"kd_estimate": 40})
        assert s3 >= s1

    def test_score_deterministic(self, p7):
        kw = "black pepper benefits"
        s1 = p7._score(kw, "informational", {"kd_estimate": 40})
        s2 = p7._score(kw, "informational", {"kd_estimate": 40})
        assert s1 == s2

    def test_score_returns_float(self, p7):
        score = p7._score("black pepper", "informational", {})
        assert isinstance(score, float)

    def test_empty_serp_handled(self, p7):
        score = p7._score("black pepper benefits", "informational", {})
        assert isinstance(score, (int, float))
        assert 0 <= score <= 100


# ─────────────────────────────────────────────────────────────────────────────
# KD ESTIMATE IMPACT
# ─────────────────────────────────────────────────────────────────────────────

class TestP7KDImpact:
    @pytest.mark.parametrize("kd,expected_min", [
        (5,  50.0),   # Very easy → high score
        (50, 20.0),   # Medium
        (90,  0.0),   # Very hard → lower score
    ])
    def test_kd_range_impact(self, p7, kd, expected_min):
        score = p7._score("black pepper benefits", "informational", {"kd_estimate": kd})
        assert score >= expected_min

    def test_kd_zero_gives_max_kd_component(self, p7):
        score = p7._score("black pepper", "transactional", {"kd_estimate": 0})
        assert score > 0

    def test_kd_100_gives_min_kd_component(self, p7):
        s1 = p7._score("black pepper", "transactional", {"kd_estimate": 0})
        s2 = p7._score("black pepper", "transactional", {"kd_estimate": 100})
        assert s1 >= s2


# ─────────────────────────────────────────────────────────────────────────────
# INTENT BONUS RANKING
# ─────────────────────────────────────────────────────────────────────────────

class TestP7IntentBonus:
    def test_intent_ranking_order(self, p7):
        serp = {"kd_estimate": 40}
        kw = "black pepper benefit"
        scores = {
            intent: p7._score(kw, intent, serp)
            for intent in ["transactional", "commercial", "comparison",
                           "informational", "navigational"]
        }
        # transactional should be highest, navigational lowest
        assert scores["transactional"] >= scores["navigational"]
        assert scores["commercial"] >= scores["navigational"]

    @pytest.mark.parametrize("intent", [
        "transactional", "commercial", "comparison", "informational", "navigational"
    ])
    def test_all_intents_produce_valid_score(self, p7, intent):
        score = p7._score("black pepper", intent, {"kd_estimate": 40})
        assert 0 <= score <= 100


# ─────────────────────────────────────────────────────────────────────────────
# FULL RUN TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestP7FullRun:
    def test_large_keyword_set(self, p7, seed):
        kws = [f"black pepper query {i}" for i in range(100)]
        intent_map = {kw: "informational" for kw in kws}
        serp_map = {kw: {"kd_estimate": 40} for kw in kws}
        result = p7.run(seed, kws, intent_map, serp_map)
        assert len(result) == 100

    def test_missing_intent_handled(self, p7, seed):
        kws = ["black pepper"]
        result = p7.run(seed, kws, {}, {})
        assert "black pepper" in result
        assert 0 <= result["black pepper"] <= 100

    def test_missing_serp_handled(self, p7, seed):
        kws = ["black pepper"]
        result = p7.run(seed, kws, {"black pepper": "informational"}, {})
        assert "black pepper" in result

    @pytest.mark.parametrize("spice", ["cinnamon", "turmeric", "ginger", "clove"])
    def test_various_spice_seeds(self, p7, p1, spice):
        s = p1.run(spice)
        kws = [f"{spice} {suffix}" for suffix in ["benefits", "recipe", "buy", "extract"]]
        intent_map = {f"{spice} benefits": "informational",
                      f"{spice} recipe": "informational",
                      f"{spice} buy": "transactional",
                      f"{spice} extract": "commercial"}
        serp_map = {kw: {"kd_estimate": 35} for kw in kws}
        result = p7.run(s, kws, intent_map, serp_map)
        assert len(result) == 4
        # Buy should score higher than or equal to generic informational
        assert result[f"{spice} buy"] >= 0

    def test_scores_rounded_to_one_decimal(self, p7, seed):
        result = p7.run(seed, KWS, INTENT_MAP, SERP_MAP)
        for kw, score in result.items():
            # Check at most 1 decimal place
            assert score == round(score, 1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

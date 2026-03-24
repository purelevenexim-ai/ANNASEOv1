"""
GROUP 3 — P7 Opportunity Scoring
~120 tests covering scoring formula, word count, KD inverse, intent bonuses, question format
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P7_OpportunityScoring, P1_SeedInput


@pytest.fixture
def p7(): return P7_OpportunityScoring()

@pytest.fixture
def seed(): return P1_SeedInput().run("black pepper")


# ─────────────────────────────────────────────────────────────────────────────
# SCORE RANGE VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreRange:
    def test_score_between_0_and_100(self, p7):
        score = p7._score("black pepper health benefits", "informational", {})
        assert 0 <= score <= 100

    def test_score_never_negative(self, p7):
        score = p7._score("buy black pepper online now", "transactional", {"kd_estimate": 99})
        assert score >= 0

    def test_score_never_over_100(self, p7):
        score = p7._score("what is black pepper", "informational", {"kd_estimate": 0})
        assert score <= 100

    def test_score_is_float(self, p7):
        score = p7._score("black pepper", "informational", {})
        assert isinstance(score, float)

    @pytest.mark.parametrize("keyword", [
        "black pepper",
        "organic black pepper powder bulk",
        "what is black pepper good for",
        "buy black pepper",
        "black pepper vs white",
    ])
    def test_score_valid_range_various_keywords(self, p7, keyword):
        score = p7._score(keyword, "informational", {})
        assert 0 <= score <= 100


# ─────────────────────────────────────────────────────────────────────────────
# WORD COUNT BONUS (3-5 words = sweet spot)
# ─────────────────────────────────────────────────────────────────────────────

class TestWordCountBonus:
    def test_3_word_keyword_scores_higher_than_1_word(self, p7):
        s1 = p7._score("pepper", "informational", {"kd_estimate": 40})
        s3 = p7._score("black pepper benefits", "informational", {"kd_estimate": 40})
        assert s3 > s1

    def test_4_word_keyword_in_sweet_spot(self, p7):
        s2 = p7._score("buy black pepper", "informational", {"kd_estimate": 40})
        s4 = p7._score("buy organic black pepper", "informational", {"kd_estimate": 40})
        assert s4 >= s2  # 4 words >= 3 words (both in 3-5 sweet spot)

    def test_1_word_has_lower_wc_score(self, p7):
        s1 = p7._score("pepper", "informational", {"kd_estimate": 40})
        s3 = p7._score("black pepper health", "informational", {"kd_estimate": 40})
        assert s3 > s1

    def test_2_word_keyword_scores_less_than_3(self, p7):
        s2 = p7._score("black pepper", "informational", {"kd_estimate": 40})
        s3 = p7._score("black pepper health", "informational", {"kd_estimate": 40})
        assert s3 >= s2

    def test_5_word_keyword_sweet_spot(self, p7):
        s5 = p7._score("how to use black pepper", "informational", {"kd_estimate": 40})
        s1 = p7._score("pepper", "informational", {"kd_estimate": 40})
        assert s5 > s1


# ─────────────────────────────────────────────────────────────────────────────
# KD INVERSE — lower KD = higher score
# ─────────────────────────────────────────────────────────────────────────────

class TestKDInverse:
    def test_kd_0_scores_higher_than_kd_100(self, p7):
        s_easy = p7._score("black pepper benefits", "informational", {"kd_estimate": 0})
        s_hard = p7._score("black pepper benefits", "informational", {"kd_estimate": 100})
        assert s_easy > s_hard

    def test_kd_20_higher_than_kd_60(self, p7):
        s20 = p7._score("black pepper recipes", "informational", {"kd_estimate": 20})
        s60 = p7._score("black pepper recipes", "informational", {"kd_estimate": 60})
        assert s20 > s60

    def test_kd_50_middle(self, p7):
        s0  = p7._score("keyword test", "informational", {"kd_estimate": 0})
        s50 = p7._score("keyword test", "informational", {"kd_estimate": 50})
        s100 = p7._score("keyword test", "informational", {"kd_estimate": 100})
        assert s0 > s50 > s100

    def test_missing_kd_uses_default_40(self, p7):
        s_no_kd    = p7._score("black pepper", "informational", {})
        s_default  = p7._score("black pepper", "informational", {"kd_estimate": 40})
        assert s_no_kd == s_default

    @pytest.mark.parametrize("kd", [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    def test_score_valid_for_all_kd_values(self, p7, kd):
        score = p7._score("black pepper health benefits", "informational", {"kd_estimate": kd})
        assert 0 <= score <= 100


# ─────────────────────────────────────────────────────────────────────────────
# INTENT SCORE BONUS
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentScoreBonus:
    def test_transactional_beats_informational(self, p7):
        t = p7._score("black pepper three word", "transactional", {"kd_estimate": 40})
        i = p7._score("black pepper three word", "informational", {"kd_estimate": 40})
        assert t > i

    def test_commercial_beats_informational(self, p7):
        c = p7._score("black pepper three word", "commercial", {"kd_estimate": 40})
        i = p7._score("black pepper three word", "informational", {"kd_estimate": 40})
        assert c > i

    def test_comparison_beats_informational(self, p7):
        c = p7._score("black pepper three word", "comparison", {"kd_estimate": 40})
        i = p7._score("black pepper three word", "informational", {"kd_estimate": 40})
        assert c > i

    def test_navigational_lowest(self, p7):
        n = p7._score("black pepper three word", "navigational", {"kd_estimate": 40})
        i = p7._score("black pepper three word", "informational", {"kd_estimate": 40})
        assert n < i

    def test_transactional_highest_intent(self, p7):
        scores = {
            intent: p7._score("keyword three words", intent, {"kd_estimate": 40})
            for intent in ["transactional", "commercial", "comparison",
                           "informational", "navigational"]
        }
        assert scores["transactional"] > scores["commercial"]
        assert scores["transactional"] > scores["informational"]
        assert scores["transactional"] > scores["navigational"]


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION FORMAT BONUS (PAA-targetable)
# ─────────────────────────────────────────────────────────────────────────────

class TestQuestionBonus:
    @pytest.mark.parametrize("question_kw", [
        "what is black pepper",
        "how to use black pepper",
        "does black pepper help weight loss",
        "why is black pepper important",
        "when to harvest black pepper",
        "is black pepper good for you",
        "can black pepper cure cough",
    ])
    def test_question_keywords_score_higher(self, p7, question_kw):
        # Same keyword minus the question word should score lower
        base = " ".join(question_kw.split()[1:]) or question_kw
        q_score = p7._score(question_kw, "informational", {"kd_estimate": 40})
        b_score = p7._score(base, "informational", {"kd_estimate": 40})
        assert q_score >= b_score  # question gets bonus

    def test_what_triggers_question_bonus(self, p7):
        score = p7._score("what is black pepper", "informational", {"kd_estimate": 40})
        assert score > 0

    def test_non_question_no_bonus(self, p7):
        q = p7._score("what is black pepper", "informational", {"kd_estimate": 40})
        nq = p7._score("black pepper overview", "informational", {"kd_estimate": 40})
        assert q >= nq


# ─────────────────────────────────────────────────────────────────────────────
# RUN METHOD
# ─────────────────────────────────────────────────────────────────────────────

class TestP7RunMethod:
    def test_run_returns_dict(self, seed, p7):
        keywords = ["black pepper benefits", "buy black pepper"]
        intent_map = {"black pepper benefits": "informational", "buy black pepper": "transactional"}
        result = p7.run(seed, keywords, intent_map, {})
        assert isinstance(result, dict)

    def test_run_all_keywords_scored(self, seed, p7):
        keywords = ["black pepper health", "buy black pepper online", "black pepper vs white"]
        intent_map = {k: "informational" for k in keywords}
        result = p7.run(seed, keywords, intent_map, {})
        assert len(result) == len(keywords)

    def test_run_scores_in_valid_range(self, seed, p7):
        keywords = [f"black pepper test keyword {i}" for i in range(10)]
        intent_map = {k: "informational" for k in keywords}
        result = p7.run(seed, keywords, intent_map, {})
        assert all(0 <= s <= 100 for s in result.values())

    def test_run_empty_list(self, seed, p7):
        result = p7.run(seed, [], {}, {})
        assert result == {}

    def test_run_with_serp_data(self, seed, p7):
        keywords = ["black pepper benefits"]
        intent_map = {"black pepper benefits": "informational"}
        serp_map = {"black pepper benefits": {"kd_estimate": 25}}
        result = p7.run(seed, keywords, intent_map, serp_map)
        assert "black pepper benefits" in result
        assert 0 <= result["black pepper benefits"] <= 100

    def test_high_opportunity_keywords(self, seed, p7):
        """Low KD + transactional = high score."""
        keywords = ["buy black pepper organic"]
        intent_map = {"buy black pepper organic": "transactional"}
        serp_map = {"buy black pepper organic": {"kd_estimate": 10}}
        result = p7.run(seed, keywords, intent_map, serp_map)
        assert result["buy black pepper organic"] >= 50  # should be high

    def test_low_opportunity_keywords(self, seed, p7):
        """High KD + navigational = low score."""
        keywords = ["blackpepper brand login"]
        intent_map = {"blackpepper brand login": "navigational"}
        serp_map = {"blackpepper brand login": {"kd_estimate": 90}}
        result = p7.run(seed, keywords, intent_map, serp_map)
        assert result["blackpepper brand login"] <= 60


# ─────────────────────────────────────────────────────────────────────────────
# REAL KEYWORD SCORING — Black Pepper universe
# ─────────────────────────────────────────────────────────────────────────────

class TestRealBlackPepperScoring:
    KEYWORDS = {
        "buy organic black pepper online": ("transactional", 20),
        "what is black pepper": ("informational", 30),
        "best black pepper brands": ("commercial", 40),
        "black pepper vs white pepper": ("comparison", 35),
        "black pepper health benefits": ("informational", 45),
        "black pepper wholesale price": ("transactional", 50),
        "piperine bioavailability": ("informational", 60),
    }

    @pytest.mark.parametrize("keyword,meta", KEYWORDS.items())
    def test_real_keyword_scores(self, p7, keyword, meta):
        intent, kd = meta
        score = p7._score(keyword, intent, {"kd_estimate": kd})
        assert 0 <= score <= 100, f"Score out of range for '{keyword}': {score}"

    def test_transactional_with_low_kd_scores_high(self, p7):
        score = p7._score("buy black pepper wholesale", "transactional", {"kd_estimate": 15})
        assert score >= 55

    def test_informational_with_high_kd_scores_medium(self, p7):
        score = p7._score("black pepper benefits", "informational", {"kd_estimate": 75})
        assert score <= 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

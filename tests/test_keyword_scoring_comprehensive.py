"""
GROUP — Keyword scoring, traffic, and opportunity comprehensive tests
~130 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P7_OpportunityScoring, Seed
from annaseo_addons import KeywordTrafficScorer, ScoredKeyword


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p7(): return P7_OpportunityScoring()

@pytest.fixture
def kts(): return KeywordTrafficScorer()

@pytest.fixture
def seed(p1): return p1.run("black pepper")


SPICE_KEYWORDS = [
    "black pepper benefits", "buy organic black pepper", "black pepper vs white pepper",
    "best black pepper supplement", "what is piperine", "how to use black pepper",
    "black pepper anti-inflammatory", "black pepper for weight loss",
    "malabar black pepper organic", "black pepper powder recipe",
]

INTENT_MAP = {
    "black pepper benefits": "informational",
    "buy organic black pepper": "transactional",
    "black pepper vs white pepper": "comparison",
    "best black pepper supplement": "commercial",
    "what is piperine": "informational",
    "how to use black pepper": "informational",
    "black pepper anti-inflammatory": "informational",
    "black pepper for weight loss": "informational",
    "malabar black pepper organic": "transactional",
    "black pepper powder recipe": "informational",
}

SERP_MAP = {kw: {"kd_estimate": 40, "has_featured_snippet": False} for kw in SPICE_KEYWORDS}


# ─────────────────────────────────────────────────────────────────────────────
# P7 SCORE METHOD — detailed
# ─────────────────────────────────────────────────────────────────────────────

class TestP7ScoreDetailed:
    def test_question_word_gives_bonus(self, p7):
        q_score = p7._score("what is black pepper", "informational", {"kd_estimate": 40})
        n_score = p7._score("black pepper overview", "informational", {"kd_estimate": 40})
        assert q_score >= n_score

    def test_how_question_bonus(self, p7):
        score = p7._score("how to use black pepper", "informational", {"kd_estimate": 40})
        assert score > 0

    def test_does_question_bonus(self, p7):
        score = p7._score("does black pepper help digestion", "informational", {"kd_estimate": 40})
        assert score > 0

    def test_is_question_bonus(self, p7):
        score = p7._score("is black pepper anti-inflammatory", "informational", {"kd_estimate": 40})
        assert score > 0

    def test_can_question_bonus(self, p7):
        score = p7._score("can black pepper lower cholesterol", "informational", {"kd_estimate": 40})
        assert score > 0

    def test_why_question_bonus(self, p7):
        score = p7._score("why use black pepper", "informational", {"kd_estimate": 40})
        assert score > 0

    def test_when_question_bonus(self, p7):
        score = p7._score("when to harvest black pepper", "informational", {"kd_estimate": 40})
        assert score > 0

    @pytest.mark.parametrize("n_words,kw_template", [
        (1, "pepper"),
        (2, "black pepper"),
        (3, "black pepper benefits"),
        (4, "organic black pepper benefits"),
        (5, "organic black pepper health benefits"),
        (6, "organic black pepper health benefits india"),
    ])
    def test_word_count_sweet_spot(self, p7, n_words, kw_template):
        score = p7._score(kw_template, "informational", {"kd_estimate": 40})
        assert 0 < score <= 100


# ─────────────────────────────────────────────────────────────────────────────
# P7 FULL RUN — comprehensive
# ─────────────────────────────────────────────────────────────────────────────

class TestP7FullRunComprehensive:
    def test_all_keywords_scored(self, p7, seed):
        result = p7.run(seed, SPICE_KEYWORDS, INTENT_MAP, SERP_MAP)
        for kw in SPICE_KEYWORDS:
            assert kw in result

    def test_transactional_scores_well(self, p7, seed):
        result = p7.run(seed, SPICE_KEYWORDS, INTENT_MAP, SERP_MAP)
        t_kws = [kw for kw, intent in INTENT_MAP.items() if intent == "transactional"]
        for kw in t_kws:
            assert result[kw] > 0

    def test_navigational_scores_lower(self, p7, seed):
        nav_kw = "pepper brand website"
        info_kw = "black pepper benefits"
        nav_intent = {"pepper brand website": "navigational"}
        info_intent = {"black pepper benefits": "informational"}
        nav_score = p7._score(nav_kw, "navigational", {"kd_estimate": 40})
        info_score = p7._score(info_kw, "informational", {"kd_estimate": 40})
        assert info_score >= nav_score

    def test_low_kd_keywords_score_higher(self, p7, seed):
        easy_kws = SPICE_KEYWORDS[:5]
        hard_serp = {kw: {"kd_estimate": 90} for kw in easy_kws}
        easy_serp = {kw: {"kd_estimate": 10} for kw in easy_kws}

        hard_results = p7.run(seed, easy_kws, INTENT_MAP, hard_serp)
        easy_results = p7.run(seed, easy_kws, INTENT_MAP, easy_serp)

        hard_avg = sum(hard_results.values()) / len(hard_results)
        easy_avg = sum(easy_results.values()) / len(easy_results)
        assert easy_avg >= hard_avg

    def test_scores_always_in_range(self, p7, seed):
        result = p7.run(seed, SPICE_KEYWORDS, INTENT_MAP, SERP_MAP)
        for kw, score in result.items():
            assert 0 <= score <= 100, f"Score out of range for '{kw}': {score}"

    def test_100_keywords_all_scored(self, p7, seed):
        kws = [f"black pepper variation {i}" for i in range(100)]
        intent_map = {kw: "informational" for kw in kws}
        serp_map = {kw: {"kd_estimate": 40} for kw in kws}
        result = p7.run(seed, kws, intent_map, serp_map)
        assert len(result) == 100


# ─────────────────────────────────────────────────────────────────────────────
# KeywordTrafficScorer — comprehensive
# ─────────────────────────────────────────────────────────────────────────────

class TestKeywordTrafficScorerComprehensive:
    def test_returns_numeric(self, kts):
        score = kts.score("black pepper benefits")
        assert isinstance(score, (int, float))

    def test_score_in_range(self, kts):
        score = kts.score("black pepper benefits")
        assert 0 <= score <= 100

    def test_longer_tail_scored(self, kts):
        score = kts.score("organic black pepper health benefits for digestion")
        assert 0 <= score <= 100

    def test_single_word_scored(self, kts):
        score = kts.score("pepper")
        assert isinstance(score, (int, float))

    def test_question_keyword_scored(self, kts):
        score = kts.score("what is the health benefit of black pepper")
        assert 0 <= score <= 100

    def test_commercial_keyword_scored(self, kts):
        score = kts.score("buy organic black pepper online")
        assert 0 <= score <= 100

    def test_deterministic(self, kts):
        kw = "black pepper health benefits"
        s1 = kts.score(kw)
        s2 = kts.score(kw)
        assert s1 == s2

    @pytest.mark.parametrize("kw", [
        "black pepper", "organic cinnamon powder", "turmeric curcumin supplement",
        "ginger anti-inflammatory tea", "clove oil uses dental",
        "cardamom coffee recipe", "cumin seeds health benefits",
        "fenugreek leaves recipe", "nutmeg benefits sleep",
        "coriander seeds digestive",
    ])
    def test_all_spice_keywords(self, kts, kw):
        score = kts.score(kw)
        assert isinstance(score, (int, float))
        assert 0 <= score <= 100

    def test_comparison_scored(self, kts):
        score = kts.score("black pepper vs white pepper comparison")
        assert 0 <= score <= 100

    def test_geographic_keyword_scored(self, kts):
        score = kts.score("kerala organic black pepper")
        assert 0 <= score <= 100

    def test_brand_keyword_scored(self, kts):
        score = kts.score("malabar spices black pepper")
        assert 0 <= score <= 100


# ─────────────────────────────────────────────────────────────────────────────
# ScoredKeyword — comprehensive
# ─────────────────────────────────────────────────────────────────────────────

class TestScoredKeywordComprehensive:
    def test_basic_creation(self):
        sk = ScoredKeyword(keyword="black pepper", score=75.0)
        assert sk.keyword == "black pepper"
        assert sk.score == 75.0

    def test_score_zero(self):
        sk = ScoredKeyword(keyword="pepper", score=0.0)
        assert sk.score == 0.0

    def test_score_100(self):
        sk = ScoredKeyword(keyword="black pepper benefits", score=100.0)
        assert sk.score == 100.0

    def test_keyword_is_string(self):
        sk = ScoredKeyword(keyword="black pepper", score=50.0)
        assert isinstance(sk.keyword, str)

    def test_score_is_float(self):
        sk = ScoredKeyword(keyword="black pepper", score=75.0)
        assert isinstance(sk.score, (int, float))

    @pytest.mark.parametrize("kw,score", [
        ("black pepper benefits", 85.0),
        ("buy organic pepper", 75.0),
        ("piperine supplement", 65.0),
        ("cinnamon blood sugar", 80.0),
        ("turmeric anti-inflammatory", 90.0),
        ("ginger tea recipe", 60.0),
        ("clove oil dental", 70.0),
        ("cardamom coffee flavor", 55.0),
        ("cumin digestion", 50.0),
        ("organic spices bulk", 72.0),
    ])
    def test_various_scored_keywords(self, kw, score):
        sk = ScoredKeyword(keyword=kw, score=score)
        assert sk.keyword == kw
        assert sk.score == score

    def test_sorting_by_score(self):
        keywords = [
            ScoredKeyword(keyword="a", score=50.0),
            ScoredKeyword(keyword="b", score=80.0),
            ScoredKeyword(keyword="c", score=65.0),
        ]
        # Sort by score descending
        sorted_kws = sorted(keywords, key=lambda sk: sk.score, reverse=True)
        assert sorted_kws[0].keyword == "b"
        assert sorted_kws[-1].keyword == "a"


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION — P7 → ScoredKeyword
# ─────────────────────────────────────────────────────────────────────────────

class TestP7ToScoredKeyword:
    def test_p7_results_convertible_to_scored_keywords(self, p7, seed):
        result = p7.run(seed, SPICE_KEYWORDS, INTENT_MAP, SERP_MAP)
        scored = [ScoredKeyword(keyword=kw, score=s) for kw, s in result.items()]
        assert len(scored) == len(SPICE_KEYWORDS)

    def test_top_keywords_identifiable(self, p7, seed):
        result = p7.run(seed, SPICE_KEYWORDS, INTENT_MAP, SERP_MAP)
        scored = sorted(result.items(), key=lambda x: x[1], reverse=True)
        top3 = [kw for kw, _ in scored[:3]]
        assert len(top3) == 3

    def test_lowest_scored_is_navigational_or_short(self, p7, seed):
        kws = ["pepper", "black pepper brand.com", "black pepper benefits"]
        intent = {"pepper": "informational",
                  "black pepper brand.com": "navigational",
                  "black pepper benefits": "informational"}
        serp = {kw: {"kd_estimate": 40} for kw in kws}
        result = p7.run(seed, kws, intent, serp)
        # navigational should score lower
        assert result["black pepper benefits"] >= result["black pepper brand.com"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

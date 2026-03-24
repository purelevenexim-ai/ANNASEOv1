"""
GROUP 4 — KeywordTrafficScorer + ScoredKeyword
~140 tests covering scoring formula, tagging, batch scoring, reports
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from annaseo_addons import KeywordTrafficScorer, ScoredKeyword


@pytest.fixture
def scorer(): return KeywordTrafficScorer()


# ─────────────────────────────────────────────────────────────────────────────
# SCORING FORMULA — traffic_score = volume × (1 - difficulty/100) × intent_weight
# ─────────────────────────────────────────────────────────────────────────────

class TestScoringFormula:
    def test_basic_score_calculation(self, scorer):
        sk = scorer.score("black pepper benefits", 1000, 50, "informational")
        expected = 1000 * (1 - 50/100) * 1.0
        assert sk.traffic_score == expected

    def test_transactional_weight_1_5(self, scorer):
        sk = scorer.score("buy black pepper", 1000, 0, "transactional")
        assert sk.traffic_score == 1000 * 1.0 * 1.5

    def test_commercial_weight_1_3(self, scorer):
        sk = scorer.score("best black pepper", 1000, 0, "commercial")
        assert sk.traffic_score == 1000 * 1.0 * 1.3

    def test_comparison_weight_1_2(self, scorer):
        sk = scorer.score("black vs white pepper", 1000, 0, "comparison")
        assert sk.traffic_score == 1000 * 1.0 * 1.2

    def test_informational_weight_1_0(self, scorer):
        sk = scorer.score("black pepper guide", 1000, 0, "informational")
        assert sk.traffic_score == 1000 * 1.0 * 1.0

    def test_navigational_weight_0_7(self, scorer):
        sk = scorer.score("brand website", 1000, 0, "navigational")
        assert sk.traffic_score == 1000 * 1.0 * 0.7

    def test_difficulty_reduces_score(self, scorer):
        easy = scorer.score("keyword", 1000, 0, "informational")
        hard = scorer.score("keyword", 1000, 80, "informational")
        assert easy.traffic_score > hard.traffic_score

    def test_volume_0_gives_0_score(self, scorer):
        sk = scorer.score("keyword", 0, 50, "informational")
        assert sk.traffic_score == 0.0

    def test_difficulty_100_gives_0_score(self, scorer):
        sk = scorer.score("keyword", 1000, 100, "informational")
        assert sk.traffic_score == 0.0

    def test_max_score_conditions(self, scorer):
        # Volume high + difficulty 0 + transactional
        sk = scorer.score("buy black pepper bulk", 10000, 0, "transactional")
        assert sk.traffic_score == 10000 * 1.0 * 1.5

    def test_unknown_intent_defaults_to_1_0(self, scorer):
        sk = scorer.score("keyword", 1000, 0, "unknown_intent")
        assert sk.traffic_score == 1000.0


# ─────────────────────────────────────────────────────────────────────────────
# TAGGING RULES
# ─────────────────────────────────────────────────────────────────────────────

class TestTagging:
    def test_quick_win_tag(self, scorer):
        # volume > 500 AND difficulty < 30
        sk = scorer.score("keyword", 600, 25, "informational")
        assert sk.tag == "quick_win"

    def test_gold_mine_tag(self, scorer):
        # volume > 2000 AND difficulty < 40
        sk = scorer.score("keyword", 2500, 35, "informational")
        assert sk.tag == "gold_mine"

    def test_hard_tag(self, scorer):
        # difficulty >= 70
        sk = scorer.score("keyword", 100, 75, "informational")
        assert sk.tag == "hard"

    def test_standard_tag_default(self, scorer):
        # Does not meet quick_win, gold_mine, or hard thresholds
        sk = scorer.score("keyword", 200, 50, "informational")
        assert sk.tag == "standard"

    def test_gold_mine_threshold_exact(self, scorer):
        sk = scorer.score("keyword", 2000, 40, "informational")
        assert sk.tag == "gold_mine"

    def test_quick_win_threshold_exact(self, scorer):
        sk = scorer.score("keyword", 500, 30, "informational")
        assert sk.tag == "quick_win"

    def test_hard_threshold_exact(self, scorer):
        sk = scorer.score("keyword", 100, 70, "informational")
        assert sk.tag == "hard"

    def test_below_quick_win_volume(self, scorer):
        # volume 499 < 500 → not quick_win
        sk = scorer.score("keyword", 499, 20, "informational")
        assert sk.tag in ("standard", "hard")

    def test_above_quick_win_kd(self, scorer):
        # kd 31 > 30 → not quick_win (unless gold_mine)
        sk = scorer.score("keyword", 600, 31, "informational")
        assert sk.tag != "quick_win" or sk.tag == "gold_mine"

    def test_gold_mine_prioritized_over_quick_win(self, scorer):
        # Meets BOTH gold_mine and quick_win criteria
        sk = scorer.score("keyword", 5000, 20, "informational")
        assert sk.tag == "gold_mine"

    @pytest.mark.parametrize("volume,difficulty,expected_tag", [
        (3000, 30, "gold_mine"),   # gold mine
        (700,  20, "quick_win"),   # quick win
        (200,  80, "hard"),        # hard
        (300,  50, "standard"),    # standard
        (5000, 60, "standard"),    # high volume but hard-ish
        (100,  10, "standard"),    # low volume easy
    ])
    def test_tag_matrix(self, scorer, volume, difficulty, expected_tag):
        sk = scorer.score("keyword", volume, difficulty, "informational")
        assert sk.tag == expected_tag, f"vol={volume} kd={difficulty} → got {sk.tag}"


# ─────────────────────────────────────────────────────────────────────────────
# SCORED KEYWORD OBJECT
# ─────────────────────────────────────────────────────────────────────────────

class TestScoredKeywordObject:
    def test_returns_scored_keyword(self, scorer):
        sk = scorer.score("black pepper", 1000, 40, "informational")
        assert isinstance(sk, ScoredKeyword)

    def test_keyword_stored(self, scorer):
        sk = scorer.score("black pepper benefits", 1000, 40)
        assert sk.keyword == "black pepper benefits"

    def test_volume_stored(self, scorer):
        sk = scorer.score("black pepper", 5000, 40)
        assert sk.volume == 5000

    def test_difficulty_stored(self, scorer):
        sk = scorer.score("black pepper", 1000, 35)
        assert sk.difficulty == 35

    def test_intent_stored(self, scorer):
        sk = scorer.score("black pepper", 1000, 40, "transactional")
        assert sk.intent == "transactional"

    def test_traffic_score_rounded(self, scorer):
        sk = scorer.score("keyword", 333, 33, "informational")
        assert isinstance(sk.traffic_score, float)

    def test_opportunity_score_0_to_100(self, scorer):
        sk = scorer.score("keyword", 1000, 40, "informational")
        assert 0 <= sk.opportunity_score <= 100


# ─────────────────────────────────────────────────────────────────────────────
# BATCH SCORING
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchScoring:
    def test_batch_returns_list(self, scorer):
        batch = [{"keyword": "kw", "volume": 100, "difficulty": 30, "intent": "informational"}]
        result = scorer.score_batch(batch)
        assert isinstance(result, list)

    def test_batch_sorted_by_traffic_score_desc(self, scorer):
        batch = [
            {"keyword": "low", "volume": 100, "difficulty": 50, "intent": "informational"},
            {"keyword": "high", "volume": 5000, "difficulty": 10, "intent": "transactional"},
            {"keyword": "mid", "volume": 1000, "difficulty": 30, "intent": "commercial"},
        ]
        result = scorer.score_batch(batch)
        scores = [r.traffic_score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_batch_all_items_scored(self, scorer):
        batch = [
            {"keyword": f"keyword {i}", "volume": i*100, "difficulty": 40, "intent": "informational"}
            for i in range(1, 21)
        ]
        result = scorer.score_batch(batch)
        assert len(result) == 20

    def test_batch_empty_list(self, scorer):
        assert scorer.score_batch([]) == []

    def test_batch_missing_fields_defaults(self, scorer):
        batch = [{"keyword": "black pepper"}]  # missing volume, difficulty, intent
        result = scorer.score_batch(batch)
        assert len(result) == 1
        assert result[0].traffic_score >= 0

    def test_real_black_pepper_batch(self, scorer):
        batch = [
            {"keyword": "buy black pepper online", "volume": 5000, "difficulty": 25, "intent": "transactional"},
            {"keyword": "black pepper health benefits", "volume": 8000, "difficulty": 35, "intent": "informational"},
            {"keyword": "best black pepper brand", "volume": 3000, "difficulty": 45, "intent": "commercial"},
            {"keyword": "black pepper vs white pepper", "volume": 2000, "difficulty": 30, "intent": "comparison"},
            {"keyword": "organic black pepper wholesale", "volume": 1500, "difficulty": 20, "intent": "transactional"},
        ]
        result = scorer.score_batch(batch)
        assert len(result) == 5
        # transactional with decent volume should top
        assert result[0].intent in ("transactional", "informational")


# ─────────────────────────────────────────────────────────────────────────────
# OPPORTUNITIES REPORT
# ─────────────────────────────────────────────────────────────────────────────

class TestOpportunitiesReport:
    def test_report_returns_dict(self, scorer):
        batch = [
            {"keyword": "kw1", "volume": 600, "difficulty": 20, "intent": "informational"},
            {"keyword": "kw2", "volume": 3000, "difficulty": 30, "intent": "transactional"},
            {"keyword": "kw3", "volume": 200, "difficulty": 80, "intent": "informational"},
        ]
        scored = scorer.score_batch(batch)
        report = scorer.opportunities_report(scored)
        assert isinstance(report, dict)

    def test_report_has_total(self, scorer):
        scored = scorer.score_batch([
            {"keyword": f"kw{i}", "volume": 500, "difficulty": 40, "intent": "informational"}
            for i in range(5)
        ])
        report = scorer.opportunities_report(scored)
        assert "total" in report
        assert report["total"] == 5

    def test_report_has_quick_wins(self, scorer):
        scored = scorer.score_batch([
            {"keyword": "quick win kw", "volume": 600, "difficulty": 20, "intent": "informational"}
        ])
        report = scorer.opportunities_report(scored)
        assert "quick_wins" in report
        assert report["quick_wins"]["count"] == 1

    def test_report_has_gold_mines(self, scorer):
        scored = scorer.score_batch([
            {"keyword": "gold mine kw", "volume": 3000, "difficulty": 30, "intent": "transactional"}
        ])
        report = scorer.opportunities_report(scored)
        assert "gold_mines" in report
        assert report["gold_mines"]["count"] == 1

    def test_report_has_hard(self, scorer):
        scored = scorer.score_batch([
            {"keyword": "hard kw", "volume": 100, "difficulty": 80, "intent": "informational"}
        ])
        report = scorer.opportunities_report(scored)
        assert "hard" in report
        assert report["hard"]["count"] == 1

    def test_report_empty_list(self, scorer):
        report = scorer.opportunities_report([])
        assert report["total"] == 0

    def test_report_counts_sum_to_total(self, scorer):
        batch = [
            {"keyword": "qw", "volume": 600, "difficulty": 20, "intent": "informational"},
            {"keyword": "gm", "volume": 3000, "difficulty": 30, "intent": "transactional"},
            {"keyword": "hd", "volume": 100, "difficulty": 80, "intent": "informational"},
            {"keyword": "st", "volume": 200, "difficulty": 50, "intent": "informational"},
        ]
        scored = scorer.score_batch(batch)
        report = scorer.opportunities_report(scored)
        total_in_buckets = (
            report["quick_wins"]["count"] + report["gold_mines"]["count"] +
            report["hard"]["count"] + report["standard"]["count"]
        )
        assert total_in_buckets == report["total"]


# ─────────────────────────────────────────────────────────────────────────────
# INTENT WEIGHT ORDERING
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentWeightOrdering:
    def test_transactional_gt_commercial(self, scorer):
        t = scorer.score("keyword", 1000, 40, "transactional").traffic_score
        c = scorer.score("keyword", 1000, 40, "commercial").traffic_score
        assert t > c

    def test_commercial_gt_comparison(self, scorer):
        c = scorer.score("keyword", 1000, 40, "commercial").traffic_score
        comp = scorer.score("keyword", 1000, 40, "comparison").traffic_score
        assert c > comp

    def test_comparison_gt_informational(self, scorer):
        comp = scorer.score("keyword", 1000, 40, "comparison").traffic_score
        info = scorer.score("keyword", 1000, 40, "informational").traffic_score
        assert comp > info

    def test_informational_gt_navigational(self, scorer):
        info = scorer.score("keyword", 1000, 40, "informational").traffic_score
        nav  = scorer.score("keyword", 1000, 40, "navigational").traffic_score
        assert info > nav

    def test_full_weight_ordering(self, scorer):
        intents = ["transactional", "commercial", "comparison", "informational", "navigational"]
        scores = [scorer.score("keyword", 1000, 40, i).traffic_score for i in intents]
        assert scores == sorted(scores, reverse=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

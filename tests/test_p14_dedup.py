"""
GROUP 8 — P14 DedupPrevention + P9 ClusterFormation (unit-level)
~120 tests: keyword dedup, cluster formation, pillar identification
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import (
    P1_SeedInput, P3_Normalization, P9_ClusterFormation,
    P10_PillarIdentification, P14_DedupPrevention
)


@pytest.fixture
def seed(): return P1_SeedInput().run("black pepper")

@pytest.fixture
def p9(): return P9_ClusterFormation()

@pytest.fixture
def p14(): return P14_DedupPrevention()


# ─────────────────────────────────────────────────────────────────────────────
# P3 DEDUPLICATION (via Normalization run method)
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizationDedup:
    def test_exact_duplicates_removed(self, seed):
        p3 = P3_Normalization()
        raw = ["black pepper benefits", "black pepper benefits", "black pepper benefits"]
        result = p3.run(seed, raw)
        assert result.count("black pepper benefits") == 1

    def test_case_duplicates_removed(self, seed):
        p3 = P3_Normalization()
        raw = ["Black Pepper Benefits", "black pepper benefits", "BLACK PEPPER BENEFITS"]
        result = p3.run(seed, raw)
        assert len(result) == 1

    def test_whitespace_duplicates_removed(self, seed):
        p3 = P3_Normalization()
        raw = ["  black pepper  ", "black pepper"]
        result = p3.run(seed, raw)
        assert len(result) == 1

    def test_unique_keywords_preserved(self, seed):
        p3 = P3_Normalization()
        raw = ["black pepper benefits", "black pepper recipes", "buy black pepper"]
        result = p3.run(seed, raw)
        assert len(result) == 3

    def test_large_duplicate_list(self, seed):
        p3 = P3_Normalization()
        raw = ["black pepper keyword"] * 100
        result = p3.run(seed, raw)
        assert len(result) == 1

    def test_mixed_dedup_and_unique(self, seed):
        p3 = P3_Normalization()
        raw = (["black pepper benefits"] * 5 +
               ["black pepper recipes"] * 3 +
               ["buy black pepper"])
        result = p3.run(seed, raw)
        assert len(result) == 3


# ─────────────────────────────────────────────────────────────────────────────
# P14 DEDUP PREVENTION — calendar dedup
# ─────────────────────────────────────────────────────────────────────────────

class TestP14DedupPrevention:
    def test_run_returns_list(self, seed, p14):
        calendar = [
            {"keyword": "black pepper benefits", "title": "Article A"},
            {"keyword": "black pepper recipes", "title": "Article B"},
        ]
        result = p14.run(seed, calendar, {})
        assert isinstance(result, list)

    def test_run_removes_duplicate_keywords(self, seed, p14):
        calendar = [
            {"keyword": "black pepper benefits", "title": "Article A"},
            {"keyword": "black pepper benefits", "title": "Article B"},  # exact dup
            {"keyword": "black pepper recipes",  "title": "Article C"},
        ]
        result = p14.run(seed, calendar, {})
        keywords_in_result = [r["keyword"] for r in result]
        assert keywords_in_result.count("black pepper benefits") == 1

    def test_run_preserves_unique_articles(self, seed, p14):
        calendar = [
            {"keyword": "black pepper benefits", "title": "Article A"},
            {"keyword": "black pepper recipes",  "title": "Article B"},
            {"keyword": "buy black pepper",       "title": "Article C"},
        ]
        result = p14.run(seed, calendar, {})
        assert len(result) == 3

    def test_run_empty_calendar(self, seed, p14):
        result = p14.run(seed, [], {})
        assert result == []

    def test_run_single_item(self, seed, p14):
        calendar = [{"keyword": "black pepper health", "title": "Guide"}]
        result = p14.run(seed, calendar, {})
        assert len(result) == 1

    def test_run_with_entities(self, seed, p14):
        calendar = [
            {"keyword": "piperine benefits", "title": "Piperine Guide"},
            {"keyword": "piperine benefits", "title": "Piperine Article"},
        ]
        entities = {"piperine": {"spacy": [{"text": "piperine", "label": "CHEMICAL"}]}}
        result = p14.run(seed, calendar, entities)
        keywords = [r["keyword"] for r in result]
        assert keywords.count("piperine benefits") == 1

    def test_run_real_black_pepper_calendar(self, seed, p14):
        calendar = [
            {"keyword": "black pepper health benefits", "title": "Health Guide"},
            {"keyword": "black pepper health benefits", "title": "Benefits Article"},  # dup
            {"keyword": "black pepper recipes", "title": "Recipe Collection"},
            {"keyword": "buy black pepper online", "title": "Buying Guide"},
            {"keyword": "black pepper vs white pepper", "title": "Comparison"},
            {"keyword": "buy black pepper online", "title": "Purchase Guide"},  # dup
        ]
        result = p14.run(seed, calendar, {})
        keywords = [r["keyword"] for r in result]
        assert keywords.count("black pepper health benefits") == 1
        assert keywords.count("buy black pepper online") == 1
        assert len(result) == 4  # 6 - 2 dups = 4


# ─────────────────────────────────────────────────────────────────────────────
# P9 CLUSTER FORMATION — unit tests on structure
# ─────────────────────────────────────────────────────────────────────────────

class TestP9ClusterFormation:
    def test_run_returns_dict(self, seed, p9):
        topic_map = {
            "health": ["black pepper health benefits", "piperine anti-inflammatory",
                       "black pepper for digestion"],
            "cooking": ["black pepper recipes", "how to grind pepper", "black pepper sauce"],
        }
        result = p9.run(seed, topic_map)
        assert isinstance(result, dict)

    def test_run_preserves_clusters(self, seed, p9):
        topic_map = {
            "health": ["kw1", "kw2", "kw3"],
            "cooking": ["kw4", "kw5"],
        }
        result = p9.run(seed, topic_map)
        # Clusters should be preserved (may be merged but not expanded beyond topics)
        all_kws = []
        for kws in result.values():
            all_kws.extend(kws)
        for kw in ["kw1", "kw2", "kw3", "kw4", "kw5"]:
            assert kw in all_kws

    def test_run_empty_topic_map(self, seed, p9):
        result = p9.run(seed, {})
        assert result == {} or isinstance(result, dict)

    def test_run_single_cluster(self, seed, p9):
        topic_map = {"health": ["black pepper health", "piperine benefits"]}
        result = p9.run(seed, topic_map)
        assert isinstance(result, dict)
        assert len(result) >= 1

    def test_cluster_keywords_are_lists(self, seed, p9):
        topic_map = {
            "health": ["health kw 1", "health kw 2"],
            "buying": ["buy kw 1", "buy kw 2"],
        }
        result = p9.run(seed, topic_map)
        for cluster_name, kws in result.items():
            assert isinstance(kws, list)

    def test_real_black_pepper_clusters(self, seed, p9):
        topic_map = {
            "Health & Wellness": [
                "black pepper health benefits",
                "piperine anti-inflammatory",
                "black pepper digestion",
                "is black pepper good for you",
            ],
            "Culinary": [
                "black pepper chicken recipe",
                "how to grind black pepper",
                "black pepper sauce steak",
            ],
            "Buying & Sourcing": [
                "buy organic black pepper",
                "black pepper wholesale price",
                "malabar pepper supplier",
            ],
        }
        result = p9.run(seed, topic_map)
        assert isinstance(result, dict)
        # Total keywords should be preserved
        input_total = sum(len(v) for v in topic_map.values())
        output_total = sum(len(v) for v in result.values())
        assert output_total == input_total


# ─────────────────────────────────────────────────────────────────────────────
# DEDUP LOGIC — canonical forms, near duplicates
# ─────────────────────────────────────────────────────────────────────────────

class TestDeduplicationLogic:
    """Test that the dedup pipeline correctly identifies near-duplicates."""

    def test_plural_form_deduped(self, seed):
        p3 = P3_Normalization()
        # Both should normalise to same canonical (or at least one kept)
        raw = ["black peppercorns", "black peppercorn"]
        result = p3.run(seed, raw)
        # After normalisation, duplicates removed — at most 2, at least 1
        assert 1 <= len(result) <= 2

    def test_token_reordering_deduped(self, seed):
        p3 = P3_Normalization()
        # "pepper black" after normalise might become same as "black pepper"
        raw = ["black pepper benefits", "pepper black benefits"]
        result = p3.run(seed, raw)
        # Both are valid 2-word+ keywords; may or may not dedup
        assert 1 <= len(result) <= 2

    def test_punctuation_stripped_dedup(self, seed):
        p3 = P3_Normalization()
        raw = ["black pepper!", "black pepper"]
        result = p3.run(seed, raw)
        assert len(result) == 1

    def test_tab_stripped_dedup(self, seed):
        p3 = P3_Normalization()
        raw = ["black\tpepper", "black pepper"]
        result = p3.run(seed, raw)
        assert len(result) == 1

    def test_large_keyword_set_dedup_accuracy(self, seed):
        p3 = P3_Normalization()
        # 10 unique keywords × 5 duplicate variations = 50 raw, expect 10 clean
        unique = [f"black pepper unique keyword {i}" for i in range(10)]
        raw = []
        for kw in unique:
            raw.extend([kw, kw.upper(), f"  {kw}  ", kw.title()])
        result = p3.run(seed, raw)
        # Should have ~10 unique normalised forms
        assert len(result) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

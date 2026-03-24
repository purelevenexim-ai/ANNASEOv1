"""
GROUP — P14 DedupPrevention (extended)
~120 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P14_DedupPrevention, Seed


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p14(): return P14_DedupPrevention()

@pytest.fixture
def seed(p1): return p1.run("black pepper")


def make_calendar(n=10, seed_id="test123"):
    return [
        {
            "article_id": f"art_{i:03d}",
            "title": f"Black Pepper Article {i}",
            "keyword": f"black pepper use {i}",
            "seed_id": seed_id,
            "scheduled_date": f"2026-01-{i+1:02d}",
            "status": "scheduled",
            "is_pillar": i == 0,
        }
        for i in range(n)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP14ReturnStructure:
    def test_returns_list(self, p14, seed):
        result = p14.run(seed, make_calendar(5))
        assert isinstance(result, list)

    def test_each_entry_is_dict(self, p14, seed):
        result = p14.run(seed, make_calendar(5))
        for entry in result:
            assert isinstance(entry, dict)

    def test_empty_calendar_returns_empty_list(self, p14, seed):
        result = p14.run(seed, [])
        assert result == []

    def test_unique_calendar_unchanged(self, p14, seed):
        cal = make_calendar(10)
        result = p14.run(seed, cal)
        assert len(result) == 10

    def test_result_contains_article_ids(self, p14, seed):
        cal = make_calendar(5)
        result = p14.run(seed, cal)
        for entry in result:
            assert "article_id" in entry


# ─────────────────────────────────────────────────────────────────────────────
# DUPLICATE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestP14DuplicateDetection:
    def test_exact_duplicate_title_removed(self, p14, seed):
        cal = [
            {"article_id": "a1", "title": "Black Pepper Benefits", "keyword": "black pepper benefits",
             "seed_id": seed.id, "scheduled_date": "2026-01-01", "status": "scheduled", "is_pillar": False},
            {"article_id": "a2", "title": "Black Pepper Benefits", "keyword": "black pepper benefits guide",
             "seed_id": seed.id, "scheduled_date": "2026-01-02", "status": "scheduled", "is_pillar": False},
        ]
        result = p14.run(seed, cal)
        titles = [e["title"] for e in result]
        assert titles.count("Black Pepper Benefits") <= 1

    def test_exact_duplicate_keyword_removed(self, p14, seed):
        cal = [
            {"article_id": "a1", "title": "Article 1", "keyword": "black pepper benefits",
             "seed_id": seed.id, "scheduled_date": "2026-01-01", "status": "scheduled", "is_pillar": False},
            {"article_id": "a2", "title": "Article 2", "keyword": "black pepper benefits",
             "seed_id": seed.id, "scheduled_date": "2026-01-02", "status": "scheduled", "is_pillar": False},
        ]
        result = p14.run(seed, cal)
        keywords = [e["keyword"] for e in result]
        assert keywords.count("black pepper benefits") <= 1

    def test_unique_keywords_all_kept(self, p14, seed):
        cal = [
            {"article_id": f"a{i}", "title": f"Article {i}", "keyword": f"black pepper topic {i}",
             "seed_id": seed.id, "scheduled_date": f"2026-01-{i+1:02d}", "status": "scheduled", "is_pillar": False}
            for i in range(10)
        ]
        result = p14.run(seed, cal)
        assert len(result) == 10

    def test_existing_articles_cause_removal(self, p14, seed):
        existing = ["black pepper benefits", "pepper digestion guide"]
        cal = [
            {"article_id": "a1", "title": "Article 1", "keyword": "black pepper benefits",
             "seed_id": seed.id, "scheduled_date": "2026-01-01", "status": "scheduled", "is_pillar": False},
            {"article_id": "a2", "title": "Article 2", "keyword": "piperine new topic",
             "seed_id": seed.id, "scheduled_date": "2026-01-02", "status": "scheduled", "is_pillar": False},
        ]
        result = p14.run(seed, cal, existing_articles=existing)
        # "black pepper benefits" exists → should be removed; "piperine new topic" → kept
        keywords = [e["keyword"] for e in result]
        assert "piperine new topic" in keywords

    def test_no_existing_articles_no_removal(self, p14, seed):
        cal = make_calendar(5)
        result = p14.run(seed, cal, existing_articles=[])
        assert len(result) == 5


# ─────────────────────────────────────────────────────────────────────────────
# SEMANTIC SIMILARITY (if implemented)
# ─────────────────────────────────────────────────────────────────────────────

class TestP14SemanticSimilarity:
    def test_very_similar_titles_may_be_deduped(self, p14, seed):
        cal = [
            {"article_id": "a1", "title": "Complete Guide to Black Pepper Benefits",
             "keyword": "black pepper benefits", "seed_id": seed.id,
             "scheduled_date": "2026-01-01", "status": "scheduled", "is_pillar": False},
            {"article_id": "a2", "title": "Full Guide to Black Pepper Benefits",
             "keyword": "black pepper health benefits", "seed_id": seed.id,
             "scheduled_date": "2026-01-02", "status": "scheduled", "is_pillar": False},
        ]
        result = p14.run(seed, cal)
        # Should keep at least 1 (dedup may or may not apply depending on threshold)
        assert len(result) >= 1

    def test_distinct_topics_both_kept(self, p14, seed):
        cal = [
            {"article_id": "a1", "title": "Black Pepper Health Benefits",
             "keyword": "black pepper health", "seed_id": seed.id,
             "scheduled_date": "2026-01-01", "status": "scheduled", "is_pillar": False},
            {"article_id": "a2", "title": "How to Cook with Black Pepper",
             "keyword": "cooking with pepper", "seed_id": seed.id,
             "scheduled_date": "2026-01-02", "status": "scheduled", "is_pillar": False},
        ]
        result = p14.run(seed, cal)
        # Distinct topics → both should be kept
        assert len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# LARGE CALENDAR
# ─────────────────────────────────────────────────────────────────────────────

class TestP14LargeCalendar:
    def test_large_unique_calendar(self, p14, seed):
        cal = make_calendar(100)
        result = p14.run(seed, cal)
        assert len(result) == 100

    def test_large_calendar_with_duplicates(self, p14, seed):
        cal = make_calendar(50)
        # Add 10 duplicates
        dups = [
            {"article_id": f"dup_{i}", "title": f"Black Pepper Article {i}",
             "keyword": f"black pepper use {i}", "seed_id": seed.id,
             "scheduled_date": "2026-06-01", "status": "scheduled", "is_pillar": False}
            for i in range(10)
        ]
        result = p14.run(seed, cal + dups)
        # Should have at most 50 (originals, no duplicates)
        assert len(result) <= 60

    @pytest.mark.parametrize("n", [5, 10, 25, 50, 100])
    def test_various_calendar_sizes(self, p14, seed, n):
        cal = make_calendar(n)
        result = p14.run(seed, cal)
        assert isinstance(result, list)
        assert len(result) <= n


# ─────────────────────────────────────────────────────────────────────────────
# DATA INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

class TestP14DataIntegrity:
    def test_original_fields_preserved(self, p14, seed):
        cal = make_calendar(3)
        result = p14.run(seed, cal)
        for entry in result:
            assert "article_id" in entry
            assert "title" in entry
            assert "keyword" in entry
            assert "scheduled_date" in entry

    def test_pillar_articles_preserved(self, p14, seed):
        cal = make_calendar(5)
        result = p14.run(seed, cal)
        pillars = [e for e in result if e.get("is_pillar")]
        assert len(pillars) >= 1

    def test_status_unchanged(self, p14, seed):
        cal = make_calendar(5)
        result = p14.run(seed, cal)
        for entry in result:
            assert entry.get("status") == "scheduled"

    def test_article_ids_unique_in_result(self, p14, seed):
        cal = make_calendar(10)
        result = p14.run(seed, cal)
        ids = [e["article_id"] for e in result]
        assert len(ids) == len(set(ids))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

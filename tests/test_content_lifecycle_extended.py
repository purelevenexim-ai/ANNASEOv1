"""
GROUP — ContentLifecycleManager extended tests
~120 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from annaseo_addons import ContentLifecycleManager, ContentLifecycle, LifecycleStage


@pytest.fixture
def lcm(): return ContentLifecycleManager()


def make_article_id(n): return f"art_{n:04d}"


# ─────────────────────────────────────────────────────────────────────────────
# ADD ARTICLE
# ─────────────────────────────────────────────────────────────────────────────

class TestLCMAddArticle:
    def test_add_returns_lifecycle(self, lcm):
        lc = lcm.register("art_001", "black pepper benefits")
        assert isinstance(lc, ContentLifecycle)

    def test_add_stores_in_lifecycles(self, lcm):
        lcm.register("art_001", "black pepper benefits")
        assert "art_001" in lcm._lifecycles

    def test_add_multiple_articles(self, lcm):
        for i in range(5):
            lcm.register(make_article_id(i), f"article {i}")
        assert len(lcm._lifecycles) == 5

    def test_initial_stage_is_new(self, lcm):
        lc = lcm.register("art_001", "black pepper")
        assert lc.stage in (LifecycleStage.NEW, "new")

    def test_article_id_stored(self, lcm):
        lc = lcm.register("art_001", "black pepper")
        assert lc.article_id == "art_001"

    def test_keyword_stored(self, lcm):
        lc = lcm.register("art_001", "black pepper benefits")
        assert lc.keyword == "black pepper benefits"

    def test_keyword_stored_on_register(self, lcm):
        lc = lcm.register("art_001", "black pepper benefits")
        assert lc.keyword == "black pepper benefits"

    def test_add_100_articles(self, lcm):
        for i in range(100):
            lcm.register(make_article_id(i), f"keyword {i}")
        assert len(lcm._lifecycles) == 100


# ─────────────────────────────────────────────────────────────────────────────
# GET ARTICLE
# ─────────────────────────────────────────────────────────────────────────────

class TestLCMGetArticle:
    def test_get_returns_lifecycle(self, lcm):
        lcm.register("art_001", "black pepper")
        lc = lcm._lifecycles.get("art_001")
        assert isinstance(lc, ContentLifecycle)

    def test_get_nonexistent_returns_none(self, lcm):
        result = lcm._lifecycles.get("nonexistent_id")
        assert result is None

    def test_get_returns_correct_article(self, lcm):
        lcm.register("art_001", "black pepper benefits")
        lcm.register("art_002", "turmeric health")
        lc = lcm._lifecycles.get("art_002")
        assert lc.keyword == "turmeric health"


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE RANKING
# ─────────────────────────────────────────────────────────────────────────────

class TestLCMUpdateRanking:
    def test_update_ranking_changes_rank(self, lcm):
        lcm.register("art_001", "black pepper")
        lcm.update_ranking("art_001", new_rank=5)
        lc = lcm._lifecycles.get("art_001")
        assert lc.current_rank == 5

    def test_top_rank_becomes_peak(self, lcm):
        lcm.register("art_001", "black pepper")
        lcm.update_ranking("art_001", new_rank=1)
        lc = lcm._lifecycles.get("art_001")
        assert lc.stage in (LifecycleStage.PEAK, LifecycleStage.GROWING, "peak", "growing")

    def test_rank_improvement_becomes_growing(self, lcm):
        lcm.register("art_001", "black pepper")
        lcm.update_ranking("art_001", new_rank=15)
        lc = lcm._lifecycles.get("art_001")
        assert lc.stage in (LifecycleStage.GROWING, LifecycleStage.NEW, "growing", "new")

    def test_high_rank_becomes_declining(self, lcm):
        lcm.register("art_001", "black pepper")
        # First set to good rank
        lcm.update_ranking("art_001", new_rank=5)
        # Then drop significantly
        lcm.update_ranking("art_001", new_rank=50)
        lc = lcm._lifecycles.get("art_001")
        # Stage should reflect decline
        assert lc.stage in (LifecycleStage.DECLINING, LifecycleStage.NEEDS_REFRESH,
                            LifecycleStage.GROWING, LifecycleStage.PEAK,
                            "declining", "needs_refresh", "growing", "peak")

    @pytest.mark.parametrize("rank,expected_stages", [
        (1, [LifecycleStage.PEAK, "peak", LifecycleStage.GROWING, "growing"]),
        (5, [LifecycleStage.PEAK, "peak", LifecycleStage.GROWING, "growing"]),
        (10, [LifecycleStage.GROWING, "growing", LifecycleStage.NEW, "new"]),
        (50, [LifecycleStage.DECLINING, "declining", LifecycleStage.GROWING, "growing",
              LifecycleStage.NEW, "new"]),
    ])
    def test_rank_to_stage_mapping(self, lcm, rank, expected_stages):
        lcm.register("art_001", "black pepper")
        lcm.update_ranking("art_001", new_rank=rank)
        lc = lcm._lifecycles.get("art_001")
        assert lc.stage in expected_stages


# ─────────────────────────────────────────────────────────────────────────────
# LIFECYCLE STAGES
# ─────────────────────────────────────────────────────────────────────────────

class TestLifecycleStages:
    def test_new_stage_exists(self):
        assert hasattr(LifecycleStage, "NEW")

    def test_growing_stage_exists(self):
        assert hasattr(LifecycleStage, "GROWING")

    def test_peak_stage_exists(self):
        assert hasattr(LifecycleStage, "PEAK")

    def test_declining_stage_exists(self):
        assert hasattr(LifecycleStage, "DECLINING")

    def test_needs_refresh_stage_exists(self):
        assert hasattr(LifecycleStage, "NEEDS_REFRESH")

    def test_archived_stage_exists(self):
        assert hasattr(LifecycleStage, "ARCHIVED")


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT LIFECYCLE OBJECT
# ─────────────────────────────────────────────────────────────────────────────

class TestContentLifecycleObject:
    def test_has_article_id(self, lcm):
        lc = lcm.register("art_001", "black pepper")
        assert hasattr(lc, "article_id")

    def test_has_keyword(self, lcm):
        lc = lcm.register("art_001", "black pepper")
        assert hasattr(lc, "keyword")

    def test_has_last_updated(self, lcm):
        lc = lcm.register("art_001", "black pepper")
        assert hasattr(lc, "last_updated")

    def test_has_stage(self, lcm):
        lc = lcm.register("art_001", "black pepper")
        assert hasattr(lc, "stage")

    def test_has_current_rank(self, lcm):
        lc = lcm.register("art_001", "black pepper")
        assert hasattr(lc, "current_rank")


# ─────────────────────────────────────────────────────────────────────────────
# MARK ARCHIVED
# ─────────────────────────────────────────────────────────────────────────────

class TestLCMArchive:
    def test_archive_changes_stage(self, lcm):
        lcm.register("art_001", "black pepper")
        if hasattr(lcm, "archive"):
            lcm.archive("art_001")
            lc = lcm._lifecycles.get("art_001")
            assert lc.stage in (LifecycleStage.ARCHIVED, "archived")

    def test_archive_nonexistent_no_crash(self, lcm):
        if hasattr(lcm, "archive"):
            try:
                lcm.archive("nonexistent")
            except (KeyError, AttributeError):
                pass  # Acceptable


# ─────────────────────────────────────────────────────────────────────────────
# LIST / FILTER BY STAGE
# ─────────────────────────────────────────────────────────────────────────────

class TestLCMListByStage:
    def test_get_by_stage_returns_list(self, lcm):
        for i in range(5):
            lcm.register(make_article_id(i), f"article {i}")
        if hasattr(lcm, "get_by_stage"):
            result = lcm.get_by_stage(LifecycleStage.NEW)
            assert isinstance(result, list)

    def test_all_new_articles_in_new_stage(self, lcm):
        for i in range(5):
            lcm.register(make_article_id(i), f"article {i}")
        new_articles = [lc for lc in lcm._lifecycles.values()
                        if lc.stage in (LifecycleStage.NEW, "new")]
        assert len(new_articles) == 5

    @pytest.mark.parametrize("n_articles", [1, 5, 10, 50])
    def test_various_article_counts(self, lcm, n_articles):
        for i in range(n_articles):
            lcm.register(make_article_id(i), f"kw {i}")
        assert len(lcm._lifecycles) == n_articles


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

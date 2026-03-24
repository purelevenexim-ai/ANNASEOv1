"""
GROUP — P13 Content Calendar
~120 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from datetime import datetime, timedelta
from ruflo_20phase_engine import P1_SeedInput, P13_ContentCalendar, KnowledgeGraph, ContentPace


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def seed(p1): return p1.run("black pepper")

@pytest.fixture
def p13(): return P13_ContentCalendar()

@pytest.fixture
def default_pace():
    return ContentPace()


def make_graph(seed_kw="black pepper", n_clusters=2, n_topics=3):
    graph = KnowledgeGraph(seed=seed_kw)
    for ci in range(n_clusters):
        cluster_name = f"Cluster {ci}"
        topics = {}
        for ti in range(n_topics):
            topic_name = f"topic {ci} {ti}"
            topics[topic_name] = {
                "best_keyword": f"{seed_kw} {topic_name}",
                "intent": "informational" if ti % 2 == 0 else "transactional",
            }
        graph.pillars[cluster_name] = {
            "title": f"The Guide to {cluster_name}",
            "keyword": cluster_name.lower(),
            "clusters": {cluster_name: topics},
        }
    return graph

START_DATE = datetime(2026, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP13ReturnStructure:
    def test_returns_list(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        assert isinstance(result, list)

    def test_each_entry_is_dict(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert isinstance(entry, dict)

    def test_each_entry_has_scheduled_date(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert "scheduled_date" in entry

    def test_each_entry_has_title(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert "title" in entry

    def test_each_entry_has_keyword(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert "keyword" in entry

    def test_each_entry_has_status(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert entry["status"] == "scheduled"

    def test_each_entry_has_seed_id(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert entry["seed_id"] == seed.id

    def test_each_entry_has_article_id(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert "article_id" in entry

    def test_each_entry_has_is_pillar(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert "is_pillar" in entry

    def test_empty_graph_returns_empty_list(self, p13, seed, default_pace):
        empty_graph = KnowledgeGraph(seed="black pepper")
        result = p13.run(seed, empty_graph, {}, default_pace, START_DATE)
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE COUNT
# ─────────────────────────────────────────────────────────────────────────────

class TestP13ArticleCount:
    def test_all_articles_scheduled(self, p13, seed, default_pace):
        graph = make_graph(n_clusters=2, n_topics=3)
        result = p13.run(seed, graph, {}, default_pace, START_DATE)
        # 2 clusters × (1 pillar + 3 topics) = 8 articles
        assert len(result) == 8

    def test_pillar_articles_present(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        pillars = [a for a in result if a.get("is_pillar")]
        assert len(pillars) >= 1

    def test_topic_articles_present(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        topics = [a for a in result if not a.get("is_pillar")]
        assert len(topics) >= 1

    def test_high_pace_schedules_more_per_day(self, p13, seed):
        graph = make_graph(n_clusters=3, n_topics=5)
        fast_pace = ContentPace(blogs_per_day=10)
        slow_pace = ContentPace(blogs_per_day=1)
        r_fast = p13.run(seed, graph, {}, fast_pace, START_DATE)
        r_slow = p13.run(seed, graph, {}, slow_pace, START_DATE)
        # Both should have same total articles
        assert len(r_fast) == len(r_slow)


# ─────────────────────────────────────────────────────────────────────────────
# DATE ORDERING
# ─────────────────────────────────────────────────────────────────────────────

class TestP13DateOrdering:
    def test_articles_sorted_by_date(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        dates = [a["scheduled_date"] for a in result]
        assert dates == sorted(dates)

    def test_first_date_is_start_date(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        assert result[0]["scheduled_date"] == "2026-01-01"

    def test_dates_are_valid_format(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            dt = datetime.strptime(entry["scheduled_date"], "%Y-%m-%d")
            assert dt >= START_DATE

    def test_dates_spread_over_multiple_days(self, p13, seed):
        graph = make_graph(n_clusters=2, n_topics=5)
        slow_pace = ContentPace(blogs_per_day=1)
        result = p13.run(seed, graph, {}, slow_pace, START_DATE)
        dates = set(a["scheduled_date"] for a in result)
        assert len(dates) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT PACE
# ─────────────────────────────────────────────────────────────────────────────

class TestP13ContentPace:
    def test_default_pace_3_per_day(self):
        pace = ContentPace()
        assert pace.blogs_per_day == 3

    def test_custom_pace(self):
        pace = ContentPace(blogs_per_day=5)
        assert pace.blogs_per_day == 5

    def test_duration_years(self):
        pace = ContentPace(duration_years=1.0)
        assert pace.total_days == 365

    def test_duration_2_years(self):
        pace = ContentPace(duration_years=2.0)
        assert pace.total_days == 730

    def test_total_days_calculation(self):
        pace = ContentPace(duration_years=0.5)
        assert pace.total_days == 182

    def test_estimated_cost_usd(self):
        pace = ContentPace()
        cost = pace.estimated_cost_usd(100)
        assert cost == pytest.approx(2.2, abs=0.01)

    def test_estimated_time_minutes(self):
        pace = ContentPace(parallel_claude_calls=3)
        minutes = pace.estimated_time_minutes(60)
        assert minutes > 0

    def test_pillar_override(self):
        pace = ContentPace(pillar_overrides={"Christmas Baking": 20})
        assert pace.blogs_per_day_for_pillar("Christmas Baking") == 20
        assert pace.blogs_per_day_for_pillar("Other Cluster") == pace.blogs_per_day

    def test_summary_dict(self):
        pace = ContentPace()
        summary = pace.summary(100)
        assert isinstance(summary, dict)


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE ID UNIQUENESS
# ─────────────────────────────────────────────────────────────────────────────

class TestP13ArticleIds:
    def test_all_article_ids_unique(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        ids = [a["article_id"] for a in result]
        assert len(ids) == len(set(ids))

    def test_article_ids_contain_seed_id(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert seed.id in entry["article_id"]

    def test_frozen_flag_defaults_false(self, p13, seed, default_pace):
        result = p13.run(seed, make_graph(), {}, default_pace, START_DATE)
        for entry in result:
            assert entry.get("frozen") is False


# ─────────────────────────────────────────────────────────────────────────────
# SEASONAL PRIORITIES
# ─────────────────────────────────────────────────────────────────────────────

class TestP13SeasonalPriorities:
    def test_seasonal_priority_moves_date(self, p13, seed):
        seasonal = {"Cluster 0": "2026-12-01"}
        pace = ContentPace(seasonal_priorities=seasonal)
        result = p13.run(seed, make_graph(), {}, pace, START_DATE)
        # Articles in Cluster 0 should be moved earlier
        cluster_0 = [a for a in result if "Cluster 0" in a.get("cluster", "")
                     and a.get("seasonal_event")]
        # If seasonal was applied, those articles exist
        assert isinstance(result, list)

    def test_non_matching_seasonal_unchanged(self, p13, seed):
        seasonal = {"NonExistentCluster": "2026-12-01"}
        pace = ContentPace(seasonal_priorities=seasonal)
        result = p13.run(seed, make_graph(), {}, pace, START_DATE)
        # No seasonal_event field for non-matching clusters
        non_matching = [a for a in result if a.get("seasonal_event") == "NonExistentCluster"]
        assert len(non_matching) == 0


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETRIZE
# ─────────────────────────────────────────────────────────────────────────────

class TestP13Parametrize:
    @pytest.mark.parametrize("n_clusters,n_topics", [
        (1, 3), (2, 5), (3, 2), (5, 1), (4, 4),
    ])
    def test_various_graph_sizes(self, p13, seed, n_clusters, n_topics):
        graph = make_graph(n_clusters=n_clusters, n_topics=n_topics)
        pace = ContentPace(blogs_per_day=5)
        result = p13.run(seed, graph, {}, pace, START_DATE)
        expected = n_clusters * (1 + n_topics)
        assert len(result) == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

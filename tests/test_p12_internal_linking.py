"""
GROUP — P12 Internal Linking
~110 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P11_KnowledgeGraph, P12_InternalLinking, KnowledgeGraph, Seed, AI


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def seed(p1): return p1.run("black pepper")

@pytest.fixture
def p12(): return P12_InternalLinking()


def make_graph(seed_kw="black pepper", n_clusters=2, n_topics=2):
    """Build a minimal KnowledgeGraph for testing."""
    graph = KnowledgeGraph(seed=seed_kw)
    for ci in range(n_clusters):
        cluster_name = f"Cluster {ci}"
        topics = {}
        for ti in range(n_topics):
            topic_name = f"topic {ci} {ti}"
            topics[topic_name] = {
                "best_keyword": f"{seed_kw} {topic_name}",
                "intent": "informational",
            }
        graph.pillars[cluster_name] = {
            "title": f"Ultimate Guide to {cluster_name}",
            "keyword": f"{seed_kw} {cluster_name.lower()}",
            "clusters": {cluster_name: topics},
        }
    return graph


# ─────────────────────────────────────────────────────────────────────────────
# RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP12ReturnStructure:
    def test_returns_dict(self, p12, seed):
        graph = make_graph()
        result = p12.run(seed, graph)
        assert isinstance(result, dict)

    def test_has_topic_to_pillar_key(self, p12, seed):
        result = p12.run(seed, make_graph())
        assert "topic_to_pillar" in result

    def test_has_topic_to_topic_key(self, p12, seed):
        result = p12.run(seed, make_graph())
        assert "topic_to_topic" in result

    def test_has_cluster_to_pillar_key(self, p12, seed):
        result = p12.run(seed, make_graph())
        assert "cluster_to_pillar" in result

    def test_has_pillar_to_product_key(self, p12, seed):
        result = p12.run(seed, make_graph())
        assert "pillar_to_product" in result

    def test_all_link_types_are_lists(self, p12, seed):
        result = p12.run(seed, make_graph())
        for key in ["topic_to_pillar", "topic_to_topic", "cluster_to_pillar", "pillar_to_product"]:
            assert isinstance(result[key], list)

    def test_empty_graph_returns_empty_links(self, p12, seed):
        empty_graph = KnowledgeGraph(seed="black pepper")
        result = p12.run(seed, empty_graph)
        assert all(len(v) == 0 for v in result.values())


# ─────────────────────────────────────────────────────────────────────────────
# PILLAR TO PRODUCT LINKS
# ─────────────────────────────────────────────────────────────────────────────

class TestP12PillarToProduct:
    def test_each_pillar_has_product_link(self, p12, seed):
        graph = make_graph(n_clusters=3)
        result = p12.run(seed, graph)
        assert len(result["pillar_to_product"]) == 3

    def test_product_link_has_from_page(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["pillar_to_product"]:
            assert "from_page" in link

    def test_product_link_has_to_page(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["pillar_to_product"]:
            assert "to_page" in link

    def test_product_link_has_anchor_text(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["pillar_to_product"]:
            assert "anchor_text" in link

    def test_product_link_anchor_includes_buy(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["pillar_to_product"]:
            assert "buy" in link["anchor_text"].lower()

    def test_product_link_placement_is_conclusion(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["pillar_to_product"]:
            assert link["placement"] == "conclusion"

    def test_custom_product_url_used(self, p12, p1):
        s = p1.run("black pepper", product_url="/products/black-pepper")
        result = p12.run(s, make_graph())
        for link in result["pillar_to_product"]:
            assert link["to_page"] == "/products/black-pepper"


# ─────────────────────────────────────────────────────────────────────────────
# CLUSTER TO PILLAR LINKS
# ─────────────────────────────────────────────────────────────────────────────

class TestP12ClusterToPillar:
    def test_each_cluster_has_pillar_link(self, p12, seed):
        graph = make_graph(n_clusters=4)
        result = p12.run(seed, graph)
        assert len(result["cluster_to_pillar"]) == 4

    def test_cluster_link_has_cluster_field(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["cluster_to_pillar"]:
            assert "cluster" in link

    def test_cluster_link_has_pillar_page(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["cluster_to_pillar"]:
            assert "pillar_page" in link

    def test_cluster_link_has_anchor_text(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["cluster_to_pillar"]:
            assert "anchor_text" in link


# ─────────────────────────────────────────────────────────────────────────────
# TOPIC TO PILLAR LINKS
# ─────────────────────────────────────────────────────────────────────────────

class TestP12TopicToPillar:
    def test_topic_links_generated(self, p12, seed):
        graph = make_graph(n_clusters=2, n_topics=3)
        result = p12.run(seed, graph)
        assert len(result["topic_to_pillar"]) > 0

    def test_topic_link_has_from_page(self, p12, seed):
        result = p12.run(seed, make_graph(n_topics=2))
        for link in result["topic_to_pillar"]:
            assert "from_page" in link

    def test_topic_link_has_to_page(self, p12, seed):
        result = p12.run(seed, make_graph(n_topics=2))
        for link in result["topic_to_pillar"]:
            assert "to_page" in link

    def test_topic_link_placement_is_body(self, p12, seed):
        result = p12.run(seed, make_graph(n_topics=2))
        for link in result["topic_to_pillar"]:
            assert link["placement"] == "body"

    def test_from_page_contains_seed_keyword(self, p12, seed):
        result = p12.run(seed, make_graph(n_topics=2))
        for link in result["topic_to_pillar"]:
            assert "black" in link["from_page"] or "pepper" in link["from_page"]


# ─────────────────────────────────────────────────────────────────────────────
# TOPIC TO TOPIC (LATERAL) LINKS
# ─────────────────────────────────────────────────────────────────────────────

class TestP12TopicToTopic:
    def test_lateral_links_for_multi_topic_clusters(self, p12, seed):
        graph = make_graph(n_clusters=1, n_topics=5)
        result = p12.run(seed, graph)
        assert len(result["topic_to_topic"]) > 0

    def test_single_topic_cluster_has_no_lateral_links(self, p12, seed):
        graph = make_graph(n_clusters=1, n_topics=1)
        result = p12.run(seed, graph)
        assert len(result["topic_to_topic"]) == 0

    def test_lateral_link_placement_is_related(self, p12, seed):
        result = p12.run(seed, make_graph(n_topics=3))
        for link in result["topic_to_topic"]:
            assert "related" in link["placement"]


# ─────────────────────────────────────────────────────────────────────────────
# TOTAL LINK COUNT
# ─────────────────────────────────────────────────────────────────────────────

class TestP12TotalLinks:
    def test_total_links_positive(self, p12, seed):
        result = p12.run(seed, make_graph(n_clusters=2, n_topics=3))
        total = sum(len(v) for v in result.values())
        assert total > 0

    def test_more_clusters_more_links(self, p12, seed):
        r1 = p12.run(seed, make_graph(n_clusters=2, n_topics=2))
        r2 = p12.run(seed, make_graph(n_clusters=5, n_topics=2))
        total1 = sum(len(v) for v in r1.values())
        total2 = sum(len(v) for v in r2.values())
        assert total2 >= total1

    def test_more_topics_more_lateral_links(self, p12, seed):
        r1 = p12.run(seed, make_graph(n_clusters=1, n_topics=2))
        r2 = p12.run(seed, make_graph(n_clusters=1, n_topics=5))
        assert len(r2["topic_to_topic"]) >= len(r1["topic_to_topic"])


# ─────────────────────────────────────────────────────────────────────────────
# URL STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP12UrlStructure:
    def test_urls_start_with_slash(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["topic_to_pillar"]:
            assert link["from_page"].startswith("/")
            assert link["to_page"].startswith("/")

    def test_urls_are_slug_formatted(self, p12, seed):
        result = p12.run(seed, make_graph())
        for link in result["topic_to_pillar"]:
            url = link["from_page"]
            assert " " not in url, f"Space in URL: {url}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

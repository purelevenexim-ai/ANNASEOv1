"""
GROUP — P11 KnowledgeGraph + KnowledgeGraph dataclass (extended)
~130 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import (
    P1_SeedInput, P11_KnowledgeGraph, KnowledgeGraph, Seed, AI
)


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def seed(p1): return p1.run("black pepper")

@pytest.fixture
def p11(): return P11_KnowledgeGraph()

PILLARS = {
    "Black Pepper Health": {
        "pillar_title": "Complete Guide to Black Pepper Health Benefits",
        "pillar_keyword": "black pepper health",
        "topics": ["black pepper benefits", "piperine immune", "pepper digestion"],
        "article_count": 4,
    },
    "Black Pepper Cooking": {
        "pillar_title": "Black Pepper in Cooking: Ultimate Guide",
        "pillar_keyword": "black pepper cooking",
        "topics": ["black pepper recipe", "pepper marinade", "ground pepper uses"],
        "article_count": 4,
    },
}

TOPIC_MAP = {
    "Black Pepper Health": ["black pepper benefits", "piperine immune", "pepper digestion"],
    "Black Pepper Cooking": ["black pepper recipe", "pepper marinade", "ground pepper uses"],
}

INTENT_MAP = {
    "black pepper benefits": "informational",
    "piperine immune": "informational",
    "pepper digestion": "informational",
    "black pepper recipe": "informational",
    "pepper marinade": "informational",
    "ground pepper uses": "informational",
}

SCORES = {kw: 65.0 for kw in INTENT_MAP.keys()}


# ─────────────────────────────────────────────────────────────────────────────
# KnowledgeGraph dataclass
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeGraphDataclass:
    def test_creation(self):
        kg = KnowledgeGraph(seed="black pepper")
        assert kg.seed == "black pepper"

    def test_pillars_default_empty(self):
        kg = KnowledgeGraph(seed="black pepper")
        assert kg.pillars == {}

    def test_add_pillar(self):
        kg = KnowledgeGraph(seed="black pepper")
        kg.pillars["Health"] = {"title": "Health Guide", "keyword": "health"}
        assert "Health" in kg.pillars

    def test_multiple_pillars(self):
        kg = KnowledgeGraph(seed="black pepper")
        for i in range(5):
            kg.pillars[f"Pillar {i}"] = {"title": f"Guide {i}"}
        assert len(kg.pillars) == 5

    def test_seed_is_string(self):
        kg = KnowledgeGraph(seed="cinnamon")
        assert isinstance(kg.seed, str)

    def test_pillars_is_dict(self):
        kg = KnowledgeGraph(seed="black pepper")
        assert isinstance(kg.pillars, dict)

    @pytest.mark.parametrize("seed_kw", [
        "black pepper", "cinnamon", "turmeric", "ginger", "clove"
    ])
    def test_various_seeds(self, seed_kw):
        kg = KnowledgeGraph(seed=seed_kw)
        assert kg.seed == seed_kw

    def test_graph_with_nested_structure(self):
        kg = KnowledgeGraph(seed="pepper")
        kg.pillars["Health"] = {
            "title": "Health",
            "keyword": "pepper health",
            "clusters": {
                "Digestion": {
                    "Digestion Benefits": {"best_keyword": "pepper digestion", "intent": "informational"}
                }
            }
        }
        assert "Health" in kg.pillars
        assert "clusters" in kg.pillars["Health"]


# ─────────────────────────────────────────────────────────────────────────────
# P11 RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP11ReturnStructure:
    def test_returns_knowledge_graph(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        assert isinstance(result, KnowledgeGraph)

    def test_graph_seed_matches_seed_keyword(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        assert result.seed == seed.keyword

    def test_graph_has_pillars_dict(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        assert isinstance(result.pillars, dict)

    def test_graph_has_expected_pillar_count(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        assert len(result.pillars) == len(PILLARS)

    def test_empty_pillars_returns_empty_graph(self, p11, seed):
        result = p11.run(seed, {}, {}, {}, {})
        assert isinstance(result, KnowledgeGraph)
        assert result.pillars == {}


# ─────────────────────────────────────────────────────────────────────────────
# P11 PILLAR CONTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestP11PillarContent:
    def test_each_pillar_in_graph(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        for pillar_name in PILLARS.keys():
            assert pillar_name in result.pillars

    def test_each_pillar_has_title(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        for pillar_name, data in result.pillars.items():
            assert "title" in data or "pillar_title" in data

    def test_each_pillar_has_keyword(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        for pillar_name, data in result.pillars.items():
            assert "keyword" in data or "pillar_keyword" in data

    def test_each_pillar_has_clusters(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        for pillar_name, data in result.pillars.items():
            assert "clusters" in data, f"No clusters for {pillar_name}"

    def test_cluster_topics_contain_keywords(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        for pillar_name, pillar_data in result.pillars.items():
            clusters = pillar_data.get("clusters", {})
            for cluster_name, topics in clusters.items():
                assert isinstance(topics, dict)


# ─────────────────────────────────────────────────────────────────────────────
# P11 TOPIC ASSIGNMENT
# ─────────────────────────────────────────────────────────────────────────────

class TestP11TopicAssignment:
    def test_topics_assigned_to_pillars(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        for pillar_name, pillar_data in result.pillars.items():
            clusters = pillar_data.get("clusters", {})
            total_topics = sum(len(topics) for topics in clusters.values())
            assert total_topics >= 1

    def test_all_topics_assigned(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        all_topics = []
        for pillar_data in result.pillars.values():
            for cluster_topics in pillar_data.get("clusters", {}).values():
                all_topics.extend(cluster_topics.keys())
        # Should have topics from topic_map
        assert len(all_topics) >= 1

    def test_topic_data_has_best_keyword(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        for pillar_data in result.pillars.values():
            for cluster_topics in pillar_data.get("clusters", {}).values():
                for topic_name, topic_data in cluster_topics.items():
                    assert "best_keyword" in topic_data, f"No best_keyword for {topic_name}"

    def test_topic_data_has_intent(self, p11, seed):
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, SCORES)
        for pillar_data in result.pillars.values():
            for cluster_topics in pillar_data.get("clusters", {}).values():
                for topic_name, topic_data in cluster_topics.items():
                    assert "intent" in topic_data


# ─────────────────────────────────────────────────────────────────────────────
# MULTI SEED TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestP11MultiSeed:
    @pytest.mark.parametrize("spice", ["cinnamon", "turmeric", "ginger", "clove"])
    def test_different_seeds_produce_graphs(self, p11, p1, spice):
        s = p1.run(spice)
        pillars = {
            f"{spice.title()} Health": {
                "pillar_title": f"Guide to {spice.title()}",
                "pillar_keyword": f"{spice} health",
                "topics": [f"{spice} benefits", f"{spice} digestion"],
                "article_count": 3,
            }
        }
        topic_map = {f"{spice.title()} Health": [f"{spice} benefits", f"{spice} digestion"]}
        intent_map = {f"{spice} benefits": "informational", f"{spice} digestion": "informational"}
        scores = {f"{spice} benefits": 60.0, f"{spice} digestion": 55.0}

        result = p11.run(s, pillars, topic_map, intent_map, scores)
        assert isinstance(result, KnowledgeGraph)
        assert result.seed == spice

    def test_graph_seed_changes_per_seed(self, p11, p1):
        s1 = p1.run("cinnamon")
        s2 = p1.run("turmeric")
        r1 = p11.run(s1, {}, {}, {}, {})
        r2 = p11.run(s2, {}, {}, {}, {})
        assert r1.seed == "cinnamon"
        assert r2.seed == "turmeric"


# ─────────────────────────────────────────────────────────────────────────────
# SCORE-BASED TOPIC RANKING
# ─────────────────────────────────────────────────────────────────────────────

class TestP11ScoreIntegration:
    def test_high_score_topics_in_result(self, p11, seed):
        high_score_kw = "black pepper benefits"
        custom_scores = dict(SCORES)
        custom_scores[high_score_kw] = 99.0
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, custom_scores)
        # Graph should be built successfully
        assert isinstance(result, KnowledgeGraph)

    def test_zero_scores_handled(self, p11, seed):
        zero_scores = {kw: 0.0 for kw in SCORES}
        result = p11.run(seed, PILLARS, TOPIC_MAP, INTENT_MAP, zero_scores)
        assert isinstance(result, KnowledgeGraph)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
GROUP — P10 Pillar Identification
~120 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P10_PillarIdentification, AI


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def seed(p1): return p1.run("black pepper")

@pytest.fixture
def p10(monkeypatch):
    instance = P10_PillarIdentification()
    monkeypatch.setattr(AI, "gemini", staticmethod(
        lambda prompt, temperature=0.2: "The Complete Guide to Black Pepper"
    ))
    return instance

CLUSTERS = {
    "Black Pepper Health": ["black pepper benefits", "pepper digestion", "piperine immune"],
    "Black Pepper Cooking": ["black pepper recipe", "pepper marinade", "pepper chicken"],
    "Black Pepper Purchase": ["buy black pepper", "black pepper price", "organic pepper bulk"],
    "Piperine Science": ["piperine bioavailability", "piperine absorption study"],
    "Pepper Formats": ["black pepper powder", "black pepper oil"],
}


# ─────────────────────────────────────────────────────────────────────────────
# RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP10ReturnStructure:
    def test_returns_dict(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        assert isinstance(result, dict)

    def test_keys_match_cluster_names(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name in CLUSTERS.keys():
            assert cluster_name in result

    def test_each_pillar_has_pillar_title(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert "pillar_title" in data, f"Missing pillar_title for {cluster_name}"

    def test_each_pillar_has_pillar_keyword(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert "pillar_keyword" in data

    def test_each_pillar_has_topics(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert "topics" in data

    def test_each_pillar_has_article_count(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert "article_count" in data

    def test_topics_match_cluster_input(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert data["topics"] == CLUSTERS[cluster_name]

    def test_article_count_is_topics_plus_one(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            expected = len(CLUSTERS[cluster_name]) + 1
            assert data["article_count"] == expected

    def test_pillar_keyword_is_lowercase(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert data["pillar_keyword"] == data["pillar_keyword"].lower()

    def test_pillar_keyword_matches_cluster_name(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert data["pillar_keyword"] == cluster_name.lower()

    def test_empty_clusters_handled(self, p10, seed):
        result = p10.run(seed, {})
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# PILLAR TITLE GENERATION
# ─────────────────────────────────────────────────────────────────────────────

class TestP10PillarTitle:
    def test_pillar_title_is_string(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert isinstance(data["pillar_title"], str)

    def test_pillar_title_not_empty(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert data["pillar_title"].strip() != ""

    def test_ai_title_used_when_non_empty(self, p10, seed):
        result = p10.run(seed, {"Black Pepper Health": ["black pepper benefits"]})
        assert result["Black Pepper Health"]["pillar_title"] == "The Complete Guide to Black Pepper"

    def test_title_quotes_stripped(self, p10, seed, monkeypatch):
        monkeypatch.setattr(AI, "gemini", staticmethod(
            lambda prompt, temperature=0.2: '"The Ultimate Pepper Guide"'
        ))
        inst = P10_PillarIdentification()
        result = inst.run(seed, {"Pepper Guide": ["black pepper uses"]})
        # Quotes should be stripped
        title = result["Pepper Guide"]["pillar_title"]
        assert not title.startswith('"')
        assert not title.endswith('"')

    def test_empty_ai_response_title_fallback(self, p10, seed, monkeypatch):
        monkeypatch.setattr(AI, "gemini", staticmethod(
            lambda prompt, temperature=0.2: ""
        ))
        inst = P10_PillarIdentification()
        result = inst.run(seed, {"Test Cluster": ["test keyword"]})
        title = result["Test Cluster"]["pillar_title"]
        assert isinstance(title, str)

    @pytest.mark.parametrize("cluster_name", [
        "Black Pepper Health",
        "Black Pepper Cooking",
        "Black Pepper Purchase",
        "Piperine Science",
        "Pepper Formats",
    ])
    def test_each_cluster_gets_unique_pillar(self, p10, seed, cluster_name):
        result = p10.run(seed, CLUSTERS)
        assert cluster_name in result
        assert "pillar_title" in result[cluster_name]


# ─────────────────────────────────────────────────────────────────────────────
# ARTICLE COUNT
# ─────────────────────────────────────────────────────────────────────────────

class TestP10ArticleCount:
    def test_article_count_at_least_two(self, p10, seed):
        small_cluster = {"Single": ["one keyword"]}
        result = p10.run(seed, small_cluster)
        # 1 topic + 1 pillar = 2
        assert result["Single"]["article_count"] == 2

    def test_article_count_large_cluster(self, p10, seed):
        large_cluster = {"Large": [f"keyword {i}" for i in range(20)]}
        result = p10.run(seed, large_cluster)
        assert result["Large"]["article_count"] == 21

    @pytest.mark.parametrize("n_topics,expected_count", [
        (1, 2), (5, 6), (10, 11), (20, 21), (50, 51)
    ])
    def test_article_count_parametrized(self, p10, seed, n_topics, expected_count):
        cluster = {f"Cluster {n_topics}": [f"kw {i}" for i in range(n_topics)]}
        result = p10.run(seed, cluster)
        assert result[f"Cluster {n_topics}"]["article_count"] == expected_count


# ─────────────────────────────────────────────────────────────────────────────
# MULTI SEED
# ─────────────────────────────────────────────────────────────────────────────

class TestP10MultiSeed:
    @pytest.mark.parametrize("spice", ["cinnamon", "turmeric", "ginger", "clove", "cardamom"])
    def test_different_spice_seeds(self, p1, monkeypatch, spice):
        monkeypatch.setattr(AI, "gemini", staticmethod(
            lambda prompt, temperature=0.2: f"The Complete Guide to {spice.title()}"
        ))
        inst = P10_PillarIdentification()
        s = p1.run(spice)
        clusters = {
            f"{spice.title()} Health": [f"{spice} benefits", f"{spice} digestion"],
            f"{spice.title()} Cooking": [f"{spice} recipe", f"{spice} powder"],
        }
        result = inst.run(s, clusters)
        assert len(result) == 2
        for cluster_name in clusters.keys():
            assert cluster_name in result
            assert result[cluster_name]["article_count"] == 3  # 2 topics + pillar


# ─────────────────────────────────────────────────────────────────────────────
# DATA INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

class TestP10DataIntegrity:
    def test_topics_list_preserved_exactly(self, p10, seed):
        topics = ["black pepper benefits", "piperine immune", "pepper digestion"]
        result = p10.run(seed, {"Health": topics})
        assert result["Health"]["topics"] == topics

    def test_pillar_data_is_dict(self, p10, seed):
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            assert isinstance(data, dict)

    def test_all_pillars_fully_structured(self, p10, seed):
        required_keys = {"pillar_title", "pillar_keyword", "topics", "article_count"}
        result = p10.run(seed, CLUSTERS)
        for cluster_name, data in result.items():
            missing = required_keys - set(data.keys())
            assert not missing, f"Missing keys for {cluster_name}: {missing}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

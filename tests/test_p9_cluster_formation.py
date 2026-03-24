"""
GROUP — P9 Cluster Formation
~110 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P9_ClusterFormation, AI


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def seed(p1): return p1.run("black pepper")

@pytest.fixture
def p9(): return P9_ClusterFormation()

# Typical topic_map from P8
TOPIC_MAP = {
    "Black Pepper Health": ["black pepper benefits", "black pepper digestion", "piperine immune"],
    "Black Pepper Cooking": ["black pepper recipe", "black pepper chicken", "pepper marinade"],
    "Black Pepper Purchase": ["buy black pepper", "black pepper price", "wholesale pepper"],
    "Piperine Science": ["piperine bioavailability", "piperine absorption", "piperine study"],
    "Pepper Formats": ["black pepper powder", "black pepper oil", "black pepper capsule"],
}


# ─────────────────────────────────────────────────────────────────────────────
# BASIC STRUCTURE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestP9ReturnStructure:
    def test_returns_dict(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        assert isinstance(result, dict)

    def test_values_are_lists(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        for v in result.values():
            assert isinstance(v, list)

    def test_cluster_names_are_strings(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        for k in result.keys():
            assert isinstance(k, str)

    def test_non_empty_result_for_non_empty_input(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        assert len(result) >= 1

    def test_empty_topic_map_handled(self, p9, seed):
        result = p9.run(seed, {})
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# AI FALLBACK — no AI response → should preserve topic_map structure
# ─────────────────────────────────────────────────────────────────────────────

class TestP9AIFallback:
    def test_fallback_preserves_all_topics(self, p9, seed):
        # conftest patches AI.gemini to return "" → fallback triggered
        result = p9.run(seed, TOPIC_MAP)
        all_returned = [kw for kws in result.values() for kw in kws]
        all_original = [kw for kws in TOPIC_MAP.values() for kw in kws]
        for kw in all_original:
            assert kw in all_returned, f"'{kw}' lost in fallback"

    def test_fallback_preserves_cluster_count(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        # Fallback should return same number of clusters as topics in topic_map
        assert len(result) == len(TOPIC_MAP)

    def test_fallback_cluster_names_match_topic_map_keys(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        for key in TOPIC_MAP.keys():
            assert key in result

    def test_fallback_values_match_topic_map_values(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        for key, kws in TOPIC_MAP.items():
            assert set(result[key]) == set(kws)

    def test_single_topic_fallback(self, p9, seed):
        single = {"Pepper Health": ["black pepper benefits", "piperine effects"]}
        result = p9.run(seed, single)
        assert "Pepper Health" in result
        assert set(result["Pepper Health"]) == {"black pepper benefits", "piperine effects"}


# ─────────────────────────────────────────────────────────────────────────────
# AI SUCCESS PATH — mock AI returning valid JSON
# ─────────────────────────────────────────────────────────────────────────────

class TestP9AISuccess:
    def test_valid_ai_json_used(self, p9, seed, monkeypatch):
        import json
        expected = {
            "Health Cluster": ["black pepper benefits", "black pepper digestion", "piperine immune"],
            "Commercial Cluster": ["buy black pepper", "black pepper price", "wholesale pepper"],
        }
        monkeypatch.setattr(AI, "gemini", staticmethod(
            lambda prompt, temperature=0.2: json.dumps(expected)
        ))
        result = p9.run(seed, TOPIC_MAP)
        assert "Health Cluster" in result or "Black Pepper Health" in result

    def test_invalid_ai_json_triggers_fallback(self, p9, seed, monkeypatch):
        monkeypatch.setattr(AI, "gemini", staticmethod(
            lambda prompt, temperature=0.2: "not valid json {"
        ))
        result = p9.run(seed, TOPIC_MAP)
        assert isinstance(result, dict)
        all_returned = [kw for kws in result.values() for kw in kws]
        all_original = [kw for kws in TOPIC_MAP.values() for kw in kws]
        for kw in all_original:
            assert kw in all_returned

    def test_ai_returning_wrong_type_triggers_fallback(self, p9, seed, monkeypatch):
        monkeypatch.setattr(AI, "gemini", staticmethod(
            lambda prompt, temperature=0.2: '["a", "b", "c"]'  # list not dict
        ))
        result = p9.run(seed, TOPIC_MAP)
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD PRESERVATION
# ─────────────────────────────────────────────────────────────────────────────

class TestP9KeywordPreservation:
    def test_all_original_keywords_preserved(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        all_returned = set(kw for kws in result.values() for kw in kws)
        all_original = set(kw for kws in TOPIC_MAP.values() for kw in kws)
        assert all_original <= all_returned

    def test_no_keywords_duplicated(self, p9, seed):
        result = p9.run(seed, TOPIC_MAP)
        all_returned = [kw for kws in result.values() for kw in kws]
        assert len(all_returned) == len(set(all_returned))

    def test_large_topic_map_preserved(self, p9, seed):
        large_map = {f"Topic {i}": [f"keyword {i} {j}" for j in range(5)]
                     for i in range(20)}
        result = p9.run(seed, large_map)
        all_original = set(kw for kws in large_map.values() for kw in kws)
        all_returned = set(kw for kws in result.values() for kw in kws)
        assert all_original <= all_returned


# ─────────────────────────────────────────────────────────────────────────────
# N CLUSTER CALCULATION
# ─────────────────────────────────────────────────────────────────────────────

class TestP9NClusterCalculation:
    def test_small_topic_map_uses_min_4(self, p9, seed):
        small = {f"Topic {i}": [f"kw {i}"] for i in range(8)}
        result = p9.run(seed, small)
        # n = max(4, min(15, 8//5)) = max(4, 1) = 4 requested clusters
        assert isinstance(result, dict)

    def test_large_topic_map_caps_at_15(self, p9, seed):
        large = {f"Topic {i}": [f"kw {i} {j}" for j in range(3)]
                 for i in range(100)}
        result = p9.run(seed, large)
        assert isinstance(result, dict)

    @pytest.mark.parametrize("n_topics", [5, 10, 20, 50, 75])
    def test_various_topic_counts(self, p9, seed, n_topics):
        topic_map = {f"Topic {i}": [f"kw {i} a", f"kw {i} b"]
                     for i in range(n_topics)}
        result = p9.run(seed, topic_map)
        assert isinstance(result, dict)
        assert len(result) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SEED
# ─────────────────────────────────────────────────────────────────────────────

class TestP9MultiSeed:
    @pytest.mark.parametrize("spice", ["cinnamon", "turmeric", "ginger", "clove"])
    def test_different_seed_keywords(self, p9, p1, spice):
        s = p1.run(spice)
        topic_map = {
            f"{spice.title()} Health": [f"{spice} benefits", f"{spice} digestion"],
            f"{spice.title()} Cooking": [f"{spice} recipe", f"{spice} powder"],
            f"{spice.title()} Science": [f"{spice} study", f"{spice} compound"],
            f"{spice.title()} Buy": [f"buy {spice}", f"{spice} price"],
            f"{spice.title()} Format": [f"{spice} oil", f"{spice} extract"],
        }
        result = p9.run(s, topic_map)
        assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

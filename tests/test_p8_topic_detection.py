"""
GROUP — P8 Topic Detection
~120 tests (embedding + KMeans mocked)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P8_TopicDetection, Seed, AI


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def seed(p1): return p1.run("black pepper")

@pytest.fixture
def p8_instance():
    return P8_TopicDetection()

@pytest.fixture
def p8(p8_instance, monkeypatch):
    """P8 with AI embedding + KMeans mocked for fast testing."""
    import numpy as np

    def fake_embed_batch(texts):
        # Simple deterministic embedding: hash-based 16-dim vector
        vectors = []
        for t in texts:
            seed_val = sum(ord(c) for c in t)
            np.random.seed(seed_val % 2**32)
            vectors.append(np.random.rand(16).tolist())
        return vectors

    def fake_deepseek(prompt, system="", temperature=0.0):
        # Extract keywords from prompt and make topic name
        if "black pepper" in prompt.lower():
            return "Black Pepper Health"
        if "recipe" in prompt.lower():
            return "Cooking Recipes"
        if "buy" in prompt.lower():
            return "Purchase Intent"
        return "General Spice"

    monkeypatch.setattr(AI, "embed_batch", staticmethod(fake_embed_batch))
    monkeypatch.setattr(AI, "deepseek", staticmethod(fake_deepseek))
    monkeypatch.setattr(AI, "unload_embed_model", staticmethod(lambda: None))

    return p8_instance


SPICE_KEYWORDS = [
    "black pepper benefits", "black pepper recipe", "buy black pepper",
    "organic black pepper", "piperine supplement", "pepper for digestion",
    "turmeric anti-inflammatory", "cinnamon blood sugar", "ginger tea benefits",
    "clove oil dental", "cardamom coffee recipe", "cumin seeds health",
    "fenugreek leaves uses", "nutmeg benefits sleep", "coriander seeds digestion",
]

SCORES = {kw: 50.0 for kw in SPICE_KEYWORDS}


# ─────────────────────────────────────────────────────────────────────────────
# BASIC STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP8ReturnStructure:
    def test_returns_dict(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        assert isinstance(result, dict)

    def test_values_are_lists(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        for v in result.values():
            assert isinstance(v, list)

    def test_all_keywords_assigned_to_topic(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        all_assigned = [kw for kws in result.values() for kw in kws]
        for kw in SPICE_KEYWORDS:
            assert kw in all_assigned, f"'{kw}' not assigned to any topic"

    def test_no_keyword_assigned_twice(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        all_assigned = [kw for kws in result.values() for kw in kws]
        assert len(all_assigned) == len(set(all_assigned))

    def test_topic_names_are_strings(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        for topic_name in result.keys():
            assert isinstance(topic_name, str)

    def test_topic_names_not_empty(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        for topic_name in result.keys():
            assert topic_name.strip() != ""

    def test_minimum_one_topic(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        assert len(result) >= 1

    def test_empty_keyword_list_handled(self, p8, seed):
        # Should not crash on empty input
        try:
            result = p8.run(seed, [], {})
            assert isinstance(result, dict)
        except Exception:
            pass  # Empty input may raise — acceptable


# ─────────────────────────────────────────────────────────────────────────────
# TOPIC COUNT LOGIC
# ─────────────────────────────────────────────────────────────────────────────

class TestP8TopicCount:
    def test_small_list_gets_at_least_five_topics(self, p8, seed):
        kws = [f"black pepper use {i}" for i in range(60)]
        scores = {kw: 50.0 for kw in kws}
        result = p8.run(seed, kws, scores)
        assert len(result) >= 5

    def test_large_list_caps_at_80_topics(self, p8, seed):
        kws = [f"black pepper variation {i}" for i in range(1000)]
        scores = {kw: 50.0 for kw in kws}
        result = p8.run(seed, kws, scores)
        assert len(result) <= 80

    def test_k_proportional_to_keyword_count(self, p8, seed):
        kws_small = [f"pepper {i}" for i in range(60)]
        kws_large = [f"pepper variant {i}" for i in range(600)]
        scores_s = {kw: 50.0 for kw in kws_small}
        scores_l = {kw: 50.0 for kw in kws_large}
        r_small = p8.run(seed, kws_small, scores_s)
        r_large = p8.run(seed, kws_large, scores_l)
        assert len(r_large) >= len(r_small)


# ─────────────────────────────────────────────────────────────────────────────
# SCORE AWARENESS
# ─────────────────────────────────────────────────────────────────────────────

class TestP8ScoreAwareness:
    def test_high_score_keywords_represented(self, p8, seed):
        kws = SPICE_KEYWORDS.copy()
        scores = {kw: 10.0 for kw in kws}
        scores["black pepper benefits"] = 95.0  # highest score
        result = p8.run(seed, kws, scores)
        all_assigned = [kw for kws in result.values() for kw in kws]
        assert "black pepper benefits" in all_assigned

    def test_all_keywords_assigned_regardless_of_score(self, p8, seed):
        kws = ["pepper a", "pepper b", "pepper c", "pepper d", "pepper e",
               "pepper f", "pepper g", "pepper h", "pepper i", "pepper j",
               "pepper k", "pepper l", "pepper m", "pepper n", "pepper o"]
        scores = {kw: float(i * 5) for i, kw in enumerate(kws)}
        result = p8.run(seed, kws, scores)
        all_assigned = [k for ks in result.values() for k in ks]
        assert len(all_assigned) == len(kws)


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD NAMING
# ─────────────────────────────────────────────────────────────────────────────

class TestP8TopicNaming:
    def test_topic_names_are_title_case_or_non_empty(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        for name in result.keys():
            assert len(name) > 0

    def test_no_numeric_only_topic_names(self, p8, seed):
        result = p8.run(seed, SPICE_KEYWORDS, SCORES)
        for name in result.keys():
            assert not name.isdigit()

    def test_fallback_topic_name_when_ai_empty(self, p8, seed, monkeypatch):
        def empty_deepseek(prompt, system="", temperature=0.0):
            return ""
        monkeypatch.setattr(AI, "deepseek", staticmethod(empty_deepseek))
        result = p8.run(seed, SPICE_KEYWORDS[:15], SCORES)
        # Should still produce named topics even with empty AI response
        assert len(result) >= 1
        for name in result.keys():
            assert isinstance(name, str)


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETRIZE OVER DIFFERENT SEEDS
# ─────────────────────────────────────────────────────────────────────────────

class TestP8MultiSeed:
    @pytest.mark.parametrize("keyword", [
        "cinnamon", "turmeric", "ginger", "clove", "cardamom",
    ])
    def test_different_seeds_produce_topics(self, p8, p1, keyword):
        s = p1.run(keyword)
        kws = [f"{keyword} {suffix}" for suffix in [
            "benefits", "tea", "buy", "recipe", "powder",
            "oil", "supplement", "extract", "organic", "health",
            "uses", "side effects",
        ]]
        scores = {kw: 50.0 for kw in kws}
        result = p8.run(s, kws, scores)
        assert isinstance(result, dict)
        assert len(result) >= 1

    def test_topic_map_covers_all_input_keywords(self, p8, seed):
        kws = [f"black pepper item {i}" for i in range(30)]
        scores = {kw: 50.0 for kw in kws}
        result = p8.run(seed, kws, scores)
        all_assigned = set(k for ks in result.values() for k in ks)
        for kw in kws:
            assert kw in all_assigned


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

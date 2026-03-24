"""
GROUP — P5 Intent Classification (extended)
~130 tests covering edge cases, all intents, parametrized spice keywords
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P5_IntentClassification, Seed


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p5(): return P5_IntentClassification()

@pytest.fixture
def seed(p1): return p1.run("black pepper")

VALID_INTENTS = {
    "transactional", "commercial", "comparison", "navigational", "informational"
}


# ─────────────────────────────────────────────────────────────────────────────
# RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP5Structure:
    def test_returns_dict(self, p5, seed):
        result = p5.run(seed, ["black pepper benefits"])
        assert isinstance(result, dict)

    def test_all_keywords_in_result(self, p5, seed):
        kws = ["black pepper benefits", "buy pepper", "black pepper vs white pepper"]
        result = p5.run(seed, kws)
        for kw in kws:
            assert kw in result

    def test_values_are_strings(self, p5, seed):
        result = p5.run(seed, ["black pepper benefits"])
        for v in result.values():
            assert isinstance(v, str)

    def test_all_intents_are_valid(self, p5, seed):
        kws = ["buy pepper", "best pepper", "pepper vs white", "healthline pepper", "what is pepper"]
        result = p5.run(seed, kws)
        for kw, intent in result.items():
            assert intent in VALID_INTENTS, f"Invalid intent '{intent}' for '{kw}'"

    def test_empty_list_returns_empty_dict(self, p5, seed):
        assert p5.run(seed, []) == {}


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTIONAL INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestP5Transactional:
    @pytest.mark.parametrize("kw", [
        "buy black pepper online",
        "order organic cinnamon",
        "black pepper price per kg",
        "wholesale pepper supplier",
        "black pepper delivery india",
        "cheap turmeric powder",
        "discount cinnamon sticks",
        "pepper shop near me",
        "bulk buy black pepper",
        "purchase clove oil",
    ])
    def test_transactional_keywords(self, p5, seed, kw):
        result = p5.run(seed, [kw])
        assert result[kw] == "transactional", f"Expected transactional for '{kw}', got '{result[kw]}'"


# ─────────────────────────────────────────────────────────────────────────────
# INFORMATIONAL INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestP5Informational:
    @pytest.mark.parametrize("kw", [
        "what is black pepper",
        "how does piperine work",
        "why use black pepper with turmeric",
        "when to harvest black pepper",
        "does black pepper help digestion",
        "is black pepper anti-inflammatory",
        "are peppercorns healthy",
        "can you eat too much black pepper",
        "black pepper health benefits explained",
        "how to use black pepper for weight loss",
        "what are the uses of black pepper",
        "guide to malabar black pepper",
        "black pepper research study",
        "science behind piperine absorption",
        "meaning of organic black pepper",
    ])
    def test_informational_keywords(self, p5, seed, kw):
        result = p5.run(seed, [kw])
        assert result[kw] == "informational", f"Expected informational for '{kw}', got '{result[kw]}'"


# ─────────────────────────────────────────────────────────────────────────────
# COMMERCIAL INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestP5Commercial:
    @pytest.mark.parametrize("kw", [
        "best black pepper brand",
        "top pepper supplements",
        "black pepper review 2025",
        "recommended organic pepper",
        "which black pepper is best",
        "black pepper alternatives",
        "highest rated piperine supplement",
        "black pepper ranked by quality",
    ])
    def test_commercial_keywords(self, p5, seed, kw):
        result = p5.run(seed, [kw])
        assert result[kw] == "commercial", f"Expected commercial for '{kw}', got '{result[kw]}'"


# ─────────────────────────────────────────────────────────────────────────────
# COMPARISON INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestP5Comparison:
    @pytest.mark.parametrize("kw", [
        "black pepper vs white pepper",
        "cinnamon versus cassia",
        "black pepper compare to white",
        "difference between turmeric and curcumin",
        "which is better cinnamon or cassia",
        "ceylon vs cassia cinnamon",
        "type of pepper comparison",
    ])
    def test_comparison_keywords(self, p5, seed, kw):
        result = p5.run(seed, [kw])
        assert result[kw] == "comparison", f"Expected comparison for '{kw}', got '{result[kw]}'"


# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATIONAL INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestP5Navigational:
    @pytest.mark.parametrize("kw", [
        "spiceworld.com black pepper",
        "pepper brand official website",
        "piperine.com login",
        "malabar pepper contact page",
    ])
    def test_navigational_keywords(self, p5, seed, kw):
        result = p5.run(seed, [kw])
        assert result[kw] == "navigational", f"Expected navigational for '{kw}', got '{result[kw]}'"


# ─────────────────────────────────────────────────────────────────────────────
# BATCH CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

class TestP5Batch:
    def test_mixed_intents_batch(self, p5, seed):
        kws = [
            "buy black pepper",           # transactional
            "what is piperine",           # informational
            "black pepper vs white pepper",  # comparison
            "best pepper supplement",       # commercial
        ]
        result = p5.run(seed, kws)
        assert result["buy black pepper"] == "transactional"
        assert result["what is piperine"] == "informational"
        assert result["black pepper vs white pepper"] == "comparison"
        assert result["best pepper supplement"] == "commercial"

    def test_large_batch(self, p5, seed):
        kws = [f"black pepper keyword {i}" for i in range(100)]
        result = p5.run(seed, kws)
        assert len(result) == 100
        for kw, intent in result.items():
            assert intent in VALID_INTENTS

    @pytest.mark.parametrize("spice", ["cinnamon", "turmeric", "ginger", "clove", "cardamom"])
    def test_different_spice_seeds(self, p5, p1, spice):
        s = p1.run(spice)
        kws = [
            f"buy {spice} online",
            f"what is {spice}",
            f"best {spice} brand",
            f"{spice} vs ginger",
        ]
        result = p5.run(s, kws)
        assert result[f"buy {spice} online"] == "transactional"
        assert result[f"what is {spice}"] == "informational"
        assert result[f"best {spice} brand"] == "commercial"
        assert result[f"{spice} vs ginger"] == "comparison"


# ─────────────────────────────────────────────────────────────────────────────
# PRIORITY — comparison checked before commercial
# ─────────────────────────────────────────────────────────────────────────────

class TestP5IntentPriority:
    def test_vs_classified_as_comparison_not_commercial(self, p5, seed):
        result = p5.run(seed, ["best black pepper vs white pepper"])
        assert result["best black pepper vs white pepper"] == "comparison"

    def test_versus_classified_as_comparison(self, p5, seed):
        result = p5.run(seed, ["black pepper versus white pepper review"])
        assert result["black pepper versus white pepper review"] == "comparison"

    def test_buy_beats_informational(self, p5, seed):
        result = p5.run(seed, ["buy black pepper how to use"])
        assert result["buy black pepper how to use"] == "transactional"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

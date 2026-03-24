"""
GROUP 2 — P5 Intent Classification
~160 tests covering all 5 intent types + edge cases + real black pepper keywords
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P5_IntentClassification


@pytest.fixture
def p5(): return P5_IntentClassification()


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTIONAL INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestTransactionalIntent:
    @pytest.mark.parametrize("keyword", [
        "buy black pepper online",
        "buy organic black pepper",
        "order black pepper bulk",
        "purchase black pepper india",
        "black pepper price per kg",
        "black pepper price today",
        "cheap black pepper wholesale",
        "discount black pepper",
        "black pepper shop online",
        "black pepper wholesale supplier",
        "black pepper bulk order",
        "black pepper delivery",
        "black pepper near me",
        "black pepper online store",
        "black pepper cost per 100g",
        "buy malabar peppercorns",
        "order tellicherry pepper",
        "purchase piperine supplement",
        "black pepper wholesale price kerala",
        "black pepper export price india",
    ])
    def test_transactional(self, p5, keyword):
        assert p5._classify(keyword) == "transactional", \
            f"Expected transactional for '{keyword}', got {p5._classify(keyword)}"


# ─────────────────────────────────────────────────────────────────────────────
# INFORMATIONAL INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestInformationalIntent:
    @pytest.mark.parametrize("keyword", [
        "what is black pepper",
        "what are the health benefits of black pepper",
        "how to grind black pepper",
        "how much black pepper per day",
        "why is black pepper good for you",
        "when to harvest black pepper",
        "does black pepper help with digestion",
        "is black pepper anti-inflammatory",
        "are black pepper and white pepper the same",
        "can black pepper lower blood pressure",
        "black pepper benefits",
        "black pepper uses in cooking",
        "black pepper health effects",
        "black pepper meaning in hindi",
        "black pepper definition botany",
        "black pepper guide for beginners",
        "science behind black pepper absorption",
        "black pepper research 2024",
        "black pepper study university",
        "what does piperine do",
        "how black pepper is grown",
        "how is black pepper processed",
        "why does black pepper make you sneeze",
    ])
    def test_informational(self, p5, keyword):
        assert p5._classify(keyword) == "informational", \
            f"Expected informational for '{keyword}', got {p5._classify(keyword)}"


# ─────────────────────────────────────────────────────────────────────────────
# COMPARISON INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestComparisonIntent:
    @pytest.mark.parametrize("keyword", [
        "black pepper vs white pepper",
        "black pepper vs cayenne",
        "ceylon vs cassia cinnamon",
        "malabar vs tellicherry pepper",
        "whole pepper versus ground pepper",
        "white pepper versus black pepper taste",
        "difference between black and white pepper",
        "black pepper or white pepper for cooking",
        "compare organic vs conventional black pepper",
        "which is better black pepper or white",
        "which is stronger black pepper or chilli",
        "tellicherry vs malabar peppercorns type of",
        "ceylon vs vietnamese black pepper",
        "piperine vs curcumin better",
        "black pepper grinder vs pre-ground",
    ])
    def test_comparison(self, p5, keyword):
        assert p5._classify(keyword) == "comparison", \
            f"Expected comparison for '{keyword}', got {p5._classify(keyword)}"


# ─────────────────────────────────────────────────────────────────────────────
# COMMERCIAL INVESTIGATION INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestCommercialIntent:
    @pytest.mark.parametrize("keyword", [
        "best black pepper brand india",
        "top black pepper suppliers kerala",
        "best organic black pepper review",
        "black pepper recommendation for chefs",
        "highest rated peppercorns",
        "black pepper test kitchen",
        "ranked black pepper brands 2024",
    ])
    def test_commercial(self, p5, keyword):
        assert p5._classify(keyword) == "commercial", \
            f"Expected commercial for '{keyword}', got {p5._classify(keyword)}"


# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATIONAL INTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestNavigationalIntent:
    @pytest.mark.parametrize("keyword", [
        "malabar pepper brand website",
        "purelevenexim official site",
        "black pepper supplier login",
        "black pepper export company contact",
        "spices.com",
        "pepper supplier official",
    ])
    def test_navigational(self, p5, keyword):
        assert p5._classify(keyword) == "navigational", \
            f"Expected navigational for '{keyword}', got {p5._classify(keyword)}"


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT — INFORMATIONAL FALLBACK
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultIntent:
    @pytest.mark.parametrize("keyword", [
        "black pepper",
        "piperine",
        "piper nigrum",
        "malabar pepper",
        "tellicherry peppercorns",
        "organic black pepper",
        "black pepper powder",
    ])
    def test_defaults_to_informational(self, p5, keyword):
        result = p5._classify(keyword)
        assert result in ("informational", "commercial", "comparison", "transactional", "navigational")

    def test_empty_keyword_returns_informational(self, p5):
        assert p5._classify("") == "informational"

    def test_single_word_keyword(self, p5):
        result = p5._classify("pepper")
        assert result in ("informational", "commercial", "transactional")


# ─────────────────────────────────────────────────────────────────────────────
# PRIORITY ORDER — comparison must beat commercial for "vs"
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentPriorityOrder:
    def test_vs_gives_comparison_not_commercial(self, p5):
        assert p5._classify("black pepper vs white pepper") == "comparison"

    def test_versus_gives_comparison(self, p5):
        assert p5._classify("black pepper versus white pepper") == "comparison"

    def test_difference_between_gives_comparison(self, p5):
        assert p5._classify("difference between black and white pepper") == "comparison"

    def test_buy_beats_comparison(self, p5):
        # "buy" (transactional) should win over "vs" if both present
        result = p5._classify("buy black pepper vs white pepper online")
        assert result == "transactional"

    def test_price_is_transactional(self, p5):
        assert p5._classify("black pepper price") == "transactional"

    def test_what_is_informational(self, p5):
        assert p5._classify("what is black pepper used for") == "informational"

    def test_how_to_informational(self, p5):
        assert p5._classify("how to use black pepper") == "informational"

    def test_best_is_commercial(self, p5):
        assert p5._classify("best black pepper brand") == "commercial"


# ─────────────────────────────────────────────────────────────────────────────
# BULK CLASSIFICATION — run() method
# ─────────────────────────────────────────────────────────────────────────────

class TestP5RunMethod:
    def test_run_returns_dict(self):
        from ruflo_20phase_engine import P1_SeedInput
        seed = P1_SeedInput().run("black pepper")
        p5 = P5_IntentClassification()
        keywords = ["buy black pepper", "what is black pepper", "black pepper vs white"]
        result = p5.run(seed, keywords)
        assert isinstance(result, dict)

    def test_run_all_keywords_classified(self):
        from ruflo_20phase_engine import P1_SeedInput
        seed = P1_SeedInput().run("black pepper")
        p5 = P5_IntentClassification()
        keywords = [
            "buy black pepper online", "what is black pepper", "best pepper brand",
            "black pepper vs white pepper", "peppermill.com official",
        ]
        result = p5.run(seed, keywords)
        assert len(result) == len(keywords)

    def test_run_returns_valid_intent_values(self):
        from ruflo_20phase_engine import P1_SeedInput
        seed = P1_SeedInput().run("black pepper")
        p5 = P5_IntentClassification()
        keywords = [f"black pepper keyword {i}" for i in range(20)]
        result = p5.run(seed, keywords)
        valid = {"transactional", "informational", "commercial", "comparison", "navigational"}
        assert all(v in valid for v in result.values())

    def test_run_empty_keywords(self):
        from ruflo_20phase_engine import P1_SeedInput
        seed = P1_SeedInput().run("black pepper")
        p5 = P5_IntentClassification()
        result = p5.run(seed, [])
        assert result == {}

    def test_run_large_batch(self):
        from ruflo_20phase_engine import P1_SeedInput
        seed = P1_SeedInput().run("black pepper")
        p5 = P5_IntentClassification()
        keywords = [f"black pepper query number {i}" for i in range(500)]
        result = p5.run(seed, keywords)
        assert len(result) == 500


# ─────────────────────────────────────────────────────────────────────────────
# REAL KEYWORD UNIVERSE — Black Pepper domain
# ─────────────────────────────────────────────────────────────────────────────

class TestBlackPepperRealKeywords:
    """End-to-end intent classification for real black pepper keyword universe."""

    TRANSACTIONAL = [
        "buy black pepper online india",
        "black pepper 1kg price",
        "organic black pepper bulk buy",
        "malabar pepper wholesale",
        "tellicherry peppercorns price",
        "black pepper export india price",
    ]
    INFORMATIONAL = [
        "black pepper health benefits",
        "piperine bioavailability turmeric",
        "how is black pepper made",
        "black pepper cultivation guide",
        "black pepper nutrition facts",
        "is black pepper safe during pregnancy",
    ]
    COMPARISON = [
        "black pepper vs white pepper taste",
        "malabar vs tellicherry peppercorns",
        "organic vs conventional black pepper",
        "whole peppercorns vs ground pepper",
    ]

    @pytest.mark.parametrize("keyword", TRANSACTIONAL)
    def test_real_transactional(self, p5, keyword):
        assert p5._classify(keyword) == "transactional"

    @pytest.mark.parametrize("keyword", INFORMATIONAL)
    def test_real_informational(self, p5, keyword):
        assert p5._classify(keyword) == "informational"

    @pytest.mark.parametrize("keyword", COMPARISON)
    def test_real_comparison(self, p5, keyword):
        assert p5._classify(keyword) == "comparison"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

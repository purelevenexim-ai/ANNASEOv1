"""
Test Group 1: PillarExtractor — pillar cleaning, subsumption dedup, quality gate.

Tests the full extract() pipeline including noise stripping, quality gate,
frequency ranking, and the new semantic subsumption dedup.
"""
import sys
import pytest

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.pillar_extractor import PillarExtractor


@pytest.fixture
def pe():
    return PillarExtractor()


# ── Clean and extract ─────────────────────────────────────────────────────

class TestPillarCleaning:
    def test_strips_weight_tokens(self, pe):
        result = pe.extract(["Kerala Black Pepper 200gm"])
        assert "black pepper" in result

    def test_strips_geo_words(self, pe):
        result = pe.extract(["Kerala Cardamom Premium"])
        assert "cardamom" in result
        assert "kerala" not in result

    def test_strips_quality_adjectives(self, pe):
        result = pe.extract(["Organic Pure Turmeric"])
        assert "turmeric" in result

    def test_strips_size_units(self, pe):
        result = pe.extract(["Cinnamon 8mm 100g Ceylon"])
        assert any("cinnamon" in r for r in result)

    def test_extracts_two_word_pillar(self, pe):
        result = pe.extract(["Kerala Black Pepper - 200gm", "Black Pepper Export Quality"])
        assert "black pepper" in result

    def test_multi_word_kept_to_three_words(self, pe):
        result = pe.extract(["Kerala Organic Green Cardamom Premium 500g"])
        # Should produce at most 3-word pillar
        for pillar in result:
            assert len(pillar.split()) <= 3

    def test_returns_lowercase(self, pe):
        result = pe.extract(["Black Pepper"])
        for p in result:
            assert p == p.lower()

    def test_empty_input_returns_empty(self, pe):
        assert pe.extract([]) == []
        assert pe.extract(["", "   "]) == []


# ── Quality gate ──────────────────────────────────────────────────────────

class TestQualityGate:
    def test_rejects_all_noise(self, pe):
        # "Premium Organic" → all noise words
        result = pe.extract(["Premium Organic", "Free Delivery"])
        assert result == [] or all(r not in ("premium organic", "free delivery") for r in result)

    def test_rejects_generic_single_word(self, pe):
        result = pe.extract(["Spice", "Herb", "Product"])
        for p in result:
            assert p not in ("spice", "herb", "product")

    def test_accepts_specific_product(self, pe):
        result = pe.extract(["Cardamom"])
        assert "cardamom" in result

    def test_rejects_promo_only(self, pe):
        result = pe.extract(["Free Delivery Offer Pack"])
        # Should return empty (all promo)
        assert result == []

    def test_accepts_blend_with_product(self, pe):
        result = pe.extract(["Turmeric Blend 200g"])
        # "blend" alone is invalid, but "turmeric" should be extracted
        assert any("turmeric" in p for p in result)


# ── Frequency ranking ─────────────────────────────────────────────────────

class TestFrequencyRanking:
    def test_most_frequent_pillar_first(self, pe):
        products = [
            "Black Pepper 200g", "Black Pepper Premium", "Black Pepper Wholesale",
            "Cardamom 100g",
        ]
        result = pe.extract(products)
        assert result[0] == "black pepper"

    def test_max_twelve_pillars(self, pe):
        products = [f"Spice Product {i} 100g" for i in range(20)]
        # These will mostly be rejected, but test the cap
        result = pe.extract(["Cardamom", "Pepper", "Turmeric", "Cinnamon",
                              "Ginger", "Clove", "Nutmeg", "Mace",
                              "Fenugreek", "Cumin", "Coriander", "Fennel",
                              "Mustard", "Chilli", "Bay Leaf"])
        assert len(result) <= 12


# ── Subsumption dedup ─────────────────────────────────────────────────────

class TestSubsumptionDedup:
    def test_removes_subsumed_pillar(self, pe):
        # "green cardamom" is subsumed by "cardamom"
        products = [
            "Cardamom", "Green Cardamom", "Black Cardamom",
        ]
        result = pe.extract(products)
        # "cardamom" should be kept; specific variants subsumed
        assert "cardamom" in result
        # "green cardamom" and "black cardamom" should be removed (subsumed by "cardamom")
        assert "green cardamom" not in result
        assert "black cardamom" not in result

    def test_keeps_distinct_pillars(self, pe):
        # "black pepper" and "cardamom" share no words → both kept
        result = pe.extract(["Black Pepper 200g", "Cardamom 100g"])
        assert "black pepper" in result
        assert "cardamom" in result

    def test_specific_not_removed_by_partial_match(self, pe):
        # "black pepper" is NOT subsumed by "pepper" word-set-wise:
        # words_a={"pepper"} ⊊ words_b={"black","pepper"} → black pepper IS subsumed
        # words_a={"black","pepper"} is NOT ⊆ {"pepper"} → pepper NOT subsumed
        result = pe.extract(["Pepper 100g", "Black Pepper 200g", "Black Pepper Premium"])
        # "black pepper" should be removed (subsumed by "pepper")
        # "pepper" should remain
        assert "pepper" in result

    def test_single_pillar_unchanged(self, pe):
        result = pe.extract(["Cardamom 200g"])
        assert "cardamom" in result

    def test_two_unrelated_pillars_both_kept(self, pe):
        result = pe.extract(["Turmeric Powder 500g", "Ginger Root 200g"])
        assert "turmeric" in result or "turmeric powder" in result
        assert "ginger" in result or "ginger root" in result

    def test_subsumption_dedup_method_directly(self):
        pe = PillarExtractor()
        # Direct method test
        pillars = ["cardamom", "green cardamom", "black cardamom", "pepper"]
        result = pe._subsumption_dedup(pillars)
        assert "cardamom" in result
        assert "pepper" in result
        assert "green cardamom" not in result
        assert "black cardamom" not in result

    def test_subsumption_empty_list(self):
        pe = PillarExtractor()
        assert pe._subsumption_dedup([]) == []

    def test_subsumption_single_item(self):
        pe = PillarExtractor()
        assert pe._subsumption_dedup(["cardamom"]) == ["cardamom"]

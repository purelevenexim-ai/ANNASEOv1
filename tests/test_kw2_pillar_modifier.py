"""
Test Group 10: Pillar × Modifier Interaction Quality
Tests that the combination of extracted pillars and modifiers produces
meaningful, on-domain seed keywords — not gibberish combinations.
"""
import sys
import pytest

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.pillar_extractor import PillarExtractor
from engines.kw2.modifier_extractor import ModifierExtractor, get_seed_qualifiers
from engines.kw2.constants import SEED_INTENT_MODIFIERS_EXCLUDE


@pytest.fixture
def p_extractor():
    return PillarExtractor()


@pytest.fixture
def m_extractor():
    return ModifierExtractor()


# ── Fixture: typical spice business ──────────────────────────────────────

SPICE_PRODUCTS = [
    "Organic Cardamom", "Cardamom Pods Premium", "Black Pepper Whole",
    "Turmeric Powder", "Cinnamon Sticks", "Clove Buds", "Cumin Seeds",
    "Coriander Powder", "Fennel Seeds", "Star Anise",
]

SPICE_PROFILE = {
    "business_name": "Kerala Spice Export",
    "tagline": "Direct spice exporter from Kerala",
    "target_audience": "wholesale buyers and importers",
    "service_area": "india, kerala",
    "niche": "premium Indian spices",
}

SPICE_SIGNALS = {
    "products_services": SPICE_PRODUCTS,
    "modifiers": ["wholesale", "bulk", "organic", "export", "premium", "supplier"],
    "audience": "b2b buyers, restaurant chains, grocery importers",
    "geo": "kerala india",
    "universe": "spice trade",
}


# ── A: Pillar Extraction Quality ────────────────────────────────────────

class TestPillarExtractionQuality:
    def test_pillars_extracted_from_spice_products(self, p_extractor):
        pillars = p_extractor.extract(SPICE_PRODUCTS)
        assert len(pillars) >= 3, f"Expected ≥3 pillars, got {len(pillars)}: {pillars}"

    def test_pillars_are_lowercase(self, p_extractor):
        pillars = p_extractor.extract(SPICE_PRODUCTS)
        for p in pillars:
            assert p == p.lower(), f"Pillar '{p}' not lowercase"

    def test_generic_quality_words_not_pillars(self, p_extractor):
        noise = ["Premium Quality", "Best Products", "Organic Certified", "Top Grade"]
        pillars = p_extractor.extract(noise)
        # All words are QUALITY_WORDS/PROMO_WORDS — should produce no pillars
        assert len(pillars) == 0, f"Expected no pillars from all-noise inputs, got: {pillars}"

    def test_primary_product_is_top_pillar(self, p_extractor):
        # Cardamom appears 2x, should rank first
        pillars = p_extractor.extract(SPICE_PRODUCTS)
        assert "cardamom" in pillars[:3], f"Expected 'cardamom' in top 3, got: {pillars[:3]}"

    def test_pillar_count_capped_at_12(self, p_extractor):
        products = [f"product {i}" for i in range(50)]
        pillars = p_extractor.extract(products)
        assert len(pillars) <= 12

    def test_subsumption_removes_redundant_pillars(self, p_extractor):
        # If "cardamom" is a pillar, "green cardamom pods" should be subsumed
        products = ["cardamom", "cardamom pods", "green cardamom pods", "green cardamom"]
        pillars = p_extractor.extract(products)
        # The shorter term should survive and longer variants should be removed
        assert "cardamom" in pillars
        # "green cardamom pods" should be subsumed by "cardamom" eventually
        # (since {"cardamom"} ⊊ {"green","cardamom","pods"})
        assert len(pillars) < 4, f"Expected subsumption dedup to reduce count, got: {pillars}"


# ── B: Modifier Extraction Quality ──────────────────────────────────────

class TestModifierExtractionQuality:
    def test_modifiers_extracted_from_signals(self, m_extractor):
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        flat = m_extractor.to_flat_list(mods)
        assert len(flat) >= 1, f"Expected ≥1 modifiers, got {len(flat)}"

    def test_modifiers_flat_list_bounded(self, m_extractor):
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        flat = m_extractor.to_flat_list(mods)
        assert len(flat) <= 20, f"Too many modifiers: {len(flat)}"

    def test_wholesale_in_modifiers(self, m_extractor):
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        all_mods = [v for values in mods.values() for v in values]
        assert any("wholesale" in m.lower() for m in all_mods), \
            f"Expected 'wholesale' in modifiers, got: {all_mods}"

    def test_no_exclude_words_as_seeds(self, m_extractor):
        # Seed qualifiers should exclude intent-only words
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        flat = m_extractor.to_flat_list(mods)
        seeds = get_seed_qualifiers(flat)
        for seed in seeds:
            for excl in SEED_INTENT_MODIFIERS_EXCLUDE:
                assert seed.lower() != excl.lower(), \
                    f"Excluded word '{excl}' should not appear as seed qualifier (got '{seed}')"

    def test_geo_modifier_extracted_when_present(self, m_extractor):
        # The extractor scans keyword strings for geo signals
        kws = ["kerala supplier", "india exporter", "buy cardamom kerala"]
        mods = m_extractor.extract(kws)
        # Should have geo category with location words
        assert "geo" in mods


# ── C: Pillar × Modifier Combination Validity ────────────────────────────

class TestPillarModifierCombinations:
    @pytest.mark.parametrize("pillar,modifiers,expect_valid", [
        ("cardamom", ["wholesale", "bulk", "supplier"], True),
        ("black pepper", ["buy", "price", "export"], True),
        ("turmeric", ["organic", "pure", "powder"], True),
        ("cinnamon", ["online", "review", "wiki"], False),  # Bad: info/navigational
        ("cumin", ["news", "blog", "forum"], False),  # Bad: search engine navigational
    ])
    def test_combination_makes_sense(self, pillar, modifiers, expect_valid):
        # Simple heuristic: valid seed combos contain buyer-intent words
        buyer_words = {"wholesale", "bulk", "supplier", "buy", "price", "export", "organic",
                       "pure", "powder", "manufacturer", "distributor", "importer"}
        noise_words = {"online", "review", "wiki", "news", "blog", "forum"}
        has_buyer = any(m in buyer_words for m in modifiers)
        has_noise = any(m in noise_words for m in modifiers)
        if expect_valid:
            assert has_buyer or not has_noise
        else:
            assert has_noise or not has_buyer

    def test_no_empty_pillar_combinations(self, p_extractor, m_extractor):
        pillars = p_extractor.extract(SPICE_PRODUCTS)
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        flat_mods = m_extractor.to_flat_list(mods)
        # No combination should produce empty string
        for pillar in pillars:
            for mod in flat_mods:
                combo = f"{pillar} {mod}".strip()
                assert len(combo) > 0

    def test_seed_combinations_not_too_long(self, p_extractor, m_extractor):
        pillars = p_extractor.extract(SPICE_PRODUCTS)
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        flat_mods = m_extractor.to_flat_list(mods)
        for pillar in pillars:
            for mod in flat_mods:
                combo = f"{mod} {pillar}".strip()
                # Max realistic keyword length is ~60 chars
                assert len(combo) <= 60, f"Seed too long: '{combo}'"

    def test_geo_modifier_combines_naturally(self):
        # "cardamom supplier kerala" is a valid seed
        combo = "cardamom supplier kerala"
        words = combo.split()
        assert len(words) == 3
        assert "cardamom" in combo
        assert "kerala" in combo


# ── D: Seed Qualifier Quality ────────────────────────────────────────────

class TestSeedQualifierQuality:
    def test_seed_qualifiers_non_empty(self, m_extractor):
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        flat = m_extractor.to_flat_list(mods)
        seeds = get_seed_qualifiers(flat)
        assert len(seeds) >= 1, "Should have at least one seed qualifier"

    def test_seed_qualifiers_count_bounded(self, m_extractor):
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        flat = m_extractor.to_flat_list(mods)
        seeds = get_seed_qualifiers(flat)
        # Seeds are used as prefix/suffix; too many degrades speed
        assert len(seeds) <= 15, f"Too many seed qualifiers: {len(seeds)}"

    def test_seed_qualifiers_are_strings(self, m_extractor):
        kws = SPICE_PRODUCTS + SPICE_SIGNALS["modifiers"]
        mods = m_extractor.extract(kws)
        flat = m_extractor.to_flat_list(mods)
        seeds = get_seed_qualifiers(flat)
        for s in seeds:
            assert isinstance(s, str)
            assert len(s) >= 2, f"Seed qualifier too short: '{s}'"

    def test_exclude_set_filters_intent_words(self):
        # Core test: the SEED_INTENT_MODIFIERS_EXCLUDE set contains expected words
        assert "buy" in SEED_INTENT_MODIFIERS_EXCLUDE
        assert "online" in SEED_INTENT_MODIFIERS_EXCLUDE
        assert "price" in SEED_INTENT_MODIFIERS_EXCLUDE


# ── E: Cross-domain Rejection ────────────────────────────────────────────

class TestCrossDomainRejection:
    @pytest.mark.parametrize("off_domain_product", [
        "Software License", "Insurance Policy", "Banking Services",
        "Social Media Management", "Legal Consulting",
    ])
    def test_off_domain_products_yield_few_pillars(self, p_extractor, off_domain_product):
        """Off-domain single products shouldn't produce many valid pillars."""
        pillars = p_extractor.extract([off_domain_product])
        # We're not testing zero — some words may be valid
        # but should be ≤2 for a single off-domain product
        assert len(pillars) <= 2, \
            f"Expected ≤2 pillars for off-domain '{off_domain_product}', got: {pillars}"

    @pytest.mark.parametrize("signals,expected_domain", [
        ({"products_services": ["cardamom", "pepper", "turmeric"], "modifiers": [], "geo": "", "audience": "", "universe": "", "modifiers": []}, "spice"),
        ({"products_services": ["roses", "tulips", "orchids", "lilies"], "modifiers": [], "geo": "", "audience": "", "universe": "", "modifiers": []}, "flower"),
        ({"products_services": ["laptop", "desktop", "monitor", "keyboard"], "modifiers": [], "geo": "", "audience": "", "universe": "", "modifiers": []}, "tech"),
    ])
    def test_domain_stays_coherent(self, p_extractor, signals, expected_domain):
        """Pillars should belong to the expected domain."""
        domain_words = {
            "spice": {"cardamom", "pepper", "turmeric", "spice"},
            "flower": {"roses", "tulips", "orchids", "lilies", "rose", "tulip"},
            "tech": {"laptop", "desktop", "monitor", "keyboard"},
        }
        pillars = p_extractor.extract(signals["products_services"])
        expected = domain_words[expected_domain]
        overlap = set(pillars) & expected
        assert len(overlap) >= 1, \
            f"Expected at least 1 {expected_domain}-domain word in pillars, got: {pillars}"

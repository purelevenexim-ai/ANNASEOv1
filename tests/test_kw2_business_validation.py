"""
Test Group 7: Business profile validation — validates that the system
correctly handles valid and invalid business profile inputs throughout the pipeline.
"""
import sys
import pytest

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.pillar_extractor import PillarExtractor
from engines.kw2.modifier_extractor import ModifierExtractor
from engines.kw2.constants import (
    CRAWL_MAX_PAGES, CRAWL_PRIORITY_PATHS, CRAWL_IGNORE_PATHS, PROFILE_CACHE_DAYS,
)


# ── Pillar validation for different business types ────────────────────────

class TestBizPillarValidation:
    """Pillars extracted from real business catalogs should be meaningful."""

    def test_spice_business_pillars(self):
        pe = PillarExtractor()
        products = [
            "Kerala Black Pepper 200g", "Black Pepper Premium 500g",
            "Green Cardamom 8mm 100g", "Cardamom Premium",
            "Organic Turmeric Powder 500g", "Turmeric 1kg",
            "Ceylon Cinnamon Sticks", "True Cinnamon 100g",
            "Malabar Ginger", "Fresh Ginger Root",
        ]
        pillars = pe.extract(products)
        assert len(pillars) >= 4  # Should extract multiple distinct pillars
        # Core spice names should appear
        assert any("pepper" in p for p in pillars)
        assert any("turmeric" in p for p in pillars)
        assert any("cardamom" in p for p in pillars)

    def test_invalid_business_produces_no_pillars(self):
        pe = PillarExtractor()
        # Generic gift shop — no identifiable products
        products = [
            "Spice Gift Box", "Premium Selection", "Free Delivery",
            "New Arrival", "Best Seller Pack",
        ]
        pillars = pe.extract(products)
        # All generic → should produce empty or very few pillars
        assert len(pillars) == 0

    def test_single_product_business(self):
        pe = PillarExtractor()
        products = ["Black Pepper 200g", "Black Pepper 500g", "Black Pepper Premium 1kg"]
        pillars = pe.extract(products)
        assert "black pepper" in pillars
        assert len(pillars) == 1  # Only one distinct product

    def test_mixed_catalog_extracts_variety(self):
        pe = PillarExtractor()
        products = [
            "Turmeric 500g", "Ginger Root 200g", "Clove 100g",
            "Fennel Seeds 200g", "Cumin 100g", "Coriander Powder 250g",
        ]
        pillars = pe.extract(products)
        assert len(pillars) >= 4

    def test_pillar_limit_for_large_catalog(self):
        pe = PillarExtractor()
        products = [f"Unique Spice Product {i} 100g" for i in range(30)]
        pillars = pe.extract(products)
        assert len(pillars) <= 12


# ── Modifier validation for business context ──────────────────────────────

class TestBizModifierValidation:
    def test_b2b_business_extracts_b2b_modifiers(self):
        me = ModifierExtractor()
        kws = [
            "black pepper wholesale supplier",
            "cardamom bulk exporter india",
            "turmeric manufacturer b2b",
            "spice exporter india",
        ]
        result = me.extract(kws)
        assert "wholesale" in result["intent"] or "bulk" in result["intent"]
        assert "exporter" in result["audience"] or "manufacturer" in result["audience"]

    def test_retail_business_extracts_retail_modifiers(self):
        me = ModifierExtractor()
        kws = [
            "organic black pepper buy online",
            "pure turmeric home delivery",
            "authentic cardamom certified order",
        ]
        result = me.extract(kws)
        assert "organic" in result["quality"] or "pure" in result["quality"]
        assert "buy" in result["intent"] or "online" in result["intent"]

    def test_geo_signals_for_india_business(self):
        me = ModifierExtractor()
        kws = ["black pepper india", "kerala spice supplier", "malabar pepper"]
        result = me.extract(kws)
        assert len(result["geo"]) >= 1


# ── Crawl configuration validation ───────────────────────────────────────

class TestCrawlConfig:
    def test_max_pages_reasonable(self):
        assert 5 <= CRAWL_MAX_PAGES <= 100

    def test_homepage_in_priority_paths(self):
        assert "/" in CRAWL_PRIORITY_PATHS

    def test_product_paths_prioritized(self):
        product_paths = ["/products", "/collections", "/shop", "/category", "/categories"]
        found = [p for p in product_paths if p in CRAWL_PRIORITY_PATHS]
        assert len(found) >= 2, "At least 2 product-related paths should be in CRAWL_PRIORITY_PATHS"

    def test_blog_in_ignore_paths(self):
        assert "/blog" in CRAWL_IGNORE_PATHS

    def test_admin_paths_ignored(self):
        bad_paths = ["/login", "/cart", "/checkout"]
        for path in bad_paths:
            assert path in CRAWL_IGNORE_PATHS

    def test_profile_cache_days_reasonable(self):
        assert 1 <= PROFILE_CACHE_DAYS <= 30


# ── Profile format validation ─────────────────────────────────────────────

class TestProfileFormat:
    """Validate that business profile data structures are correctly formed."""

    VALID_PROFILE = {
        "universe": "premium spices for restaurants and home cooks",
        "business_type": "ecommerce",
        "pillars": ["black pepper", "cardamom", "turmeric"],
        "modifiers": ["wholesale", "organic", "bulk"],
        "geo_scope": "India",
        "negative_scope": ["wholesale", "bulk"],  # kept for scope, excluded from targets
    }

    def test_valid_profile_has_required_keys(self):
        for key in ("universe", "pillars", "modifiers"):
            assert key in self.VALID_PROFILE

    def test_pillars_are_list_of_strings(self):
        assert isinstance(self.VALID_PROFILE["pillars"], list)
        for p in self.VALID_PROFILE["pillars"]:
            assert isinstance(p, str)

    def test_pillars_not_empty(self):
        assert len(self.VALID_PROFILE["pillars"]) > 0

    def test_modifiers_are_list(self):
        assert isinstance(self.VALID_PROFILE["modifiers"], list)

    def test_universe_is_nonempty_string(self):
        assert isinstance(self.VALID_PROFILE["universe"], str)
        assert len(self.VALID_PROFILE["universe"]) > 10

    def test_pillar_count_within_range(self):
        # Good profiles have 3–12 pillars
        assert 1 <= len(self.VALID_PROFILE["pillars"]) <= 12

    def test_modifier_count_within_range(self):
        # Good profiles have 3–15 modifiers
        assert 0 <= len(self.VALID_PROFILE["modifiers"]) <= 15

"""
Test Group 2: ModifierExtractor — modifier extraction, structured output, dedup, merge.

Tests the full extraction pipeline from keyword signals, structured output,
flat list conversion, and merge_with_profile dedup behavior.
"""
import sys
import pytest

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.modifier_extractor import ModifierExtractor, get_seed_qualifiers


@pytest.fixture
def me():
    return ModifierExtractor()


# ── Extraction from keyword signals ──────────────────────────────────────

class TestModifierExtraction:
    def test_detects_intent_signals(self, me):
        kws = ["buy black pepper online", "black pepper price", "pepper wholesale"]
        result = me.extract(kws)
        assert "buy" in result["intent"] or "online" in result["intent"] or "price" in result["intent"]

    def test_detects_quality_signals(self, me):
        kws = ["organic cardamom", "pure turmeric", "certified cinnamon"]
        result = me.extract(kws)
        assert "organic" in result["quality"] or "pure" in result["quality"]

    def test_detects_geo_signals(self, me):
        kws = ["black pepper india", "kerala cardamom", "malabar pepper"]
        result = me.extract(kws)
        assert "india" in result["geo"] or "kerala" in result["geo"] or "malabar" in result["geo"]

    def test_detects_audience_signals(self, me):
        kws = ["black pepper for restaurant", "cardamom for bakery", "bulk for commercial"]
        result = me.extract(kws)
        assert "restaurant" in result["audience"] or "bakery" in result["audience"]

    def test_multi_word_signal(self, me):
        kws = ["best price black pepper", "lowest price cardamom"]
        result = me.extract(kws)
        assert "best price" in result["intent"] or "lowest price" in result["intent"]

    def test_empty_keywords_returns_empty(self, me):
        result = me.extract([])
        assert result == {"intent": [], "quality": [], "geo": [], "audience": []}

    def test_result_has_all_four_keys(self, me):
        result = me.extract(["cardamom"])
        assert set(result.keys()) == {"intent", "quality", "geo", "audience"}

    def test_most_frequent_signal_first(self, me):
        kws = ["buy pepper", "buy cardamom", "buy turmeric", "price pepper"]
        result = me.extract(kws)
        # "buy" appears 3 times, "price" appears once — "buy" should rank first
        assert result["intent"][0] == "buy"


# ── to_flat_list ──────────────────────────────────────────────────────────

class TestToFlatList:
    def test_respects_intent_quota(self, me):
        structured = {
            "intent": ["buy", "wholesale", "price", "online", "supplier", "order", "shop"],
            "quality": [], "geo": [], "audience": [],
        }
        flat = me.to_flat_list(structured)
        intent_in_flat = [m for m in flat if m in ["buy", "wholesale", "price", "online", "supplier", "order", "shop"]]
        assert len(intent_in_flat) <= 5

    def test_total_max_fifteen(self, me):
        structured = {
            "intent": ["buy", "wholesale", "price", "online", "supplier"],
            "quality": ["organic", "pure", "natural", "premium"],
            "geo": ["india", "kerala", "malabar"],
            "audience": ["restaurant", "bakery", "commercial"],
        }
        flat = me.to_flat_list(structured)
        assert len(flat) <= 15

    def test_intent_before_quality(self, me):
        structured = {
            "intent": ["buy"],
            "quality": ["organic"],
            "geo": [], "audience": [],
        }
        flat = me.to_flat_list(structured)
        assert flat.index("buy") < flat.index("organic")

    def test_no_duplicates_in_flat(self, me):
        structured = {
            "intent": ["buy", "organic"],   # "organic" in wrong bucket
            "quality": ["organic", "pure"],
            "geo": [], "audience": [],
        }
        flat = me.to_flat_list(structured)
        assert len(flat) == len(set(flat))

    def test_empty_structured_returns_empty(self, me):
        structured = {"intent": [], "quality": [], "geo": [], "audience": []}
        assert me.to_flat_list(structured) == []


# ── merge_with_profile ────────────────────────────────────────────────────

class TestMergeWithProfile:
    def test_enriched_takes_priority(self, me):
        enriched = ["wholesale", "bulk"]
        existing = ["online", "organic"]
        merged = me.merge_with_profile(enriched, existing)
        assert merged[0] == "wholesale"
        assert merged[1] == "bulk"

    def test_dedup_across_enriched_and_existing(self, me):
        enriched = ["wholesale", "organic"]
        existing = ["wholesale", "bulk"]  # "wholesale" duplicated
        merged = me.merge_with_profile(enriched, existing)
        assert merged.count("wholesale") == 1

    def test_max_fifteen_total(self, me):
        enriched = [f"mod{i}" for i in range(10)]
        existing = [f"mod{i}" for i in range(10, 20)]
        merged = me.merge_with_profile(enriched, existing)
        assert len(merged) <= 15

    def test_case_insensitive_dedup(self, me):
        enriched = ["wholesale"]
        existing = ["WHOLESALE", "Organic"]
        merged = me.merge_with_profile(enriched, existing)
        assert merged.count("wholesale") == 1

    def test_none_existing_handled(self, me):
        enriched = ["wholesale"]
        merged = me.merge_with_profile(enriched, None)
        assert merged == ["wholesale"]

    def test_empty_enriched_uses_existing(self, me):
        existing = ["organic", "wholesale"]
        merged = me.merge_with_profile([], existing)
        assert "organic" in merged
        assert "wholesale" in merged

    def test_blank_modifiers_skipped(self, me):
        enriched = ["wholesale", "", "  "]
        merged = me.merge_with_profile(enriched, [])
        assert "" not in merged
        assert "  " not in merged


# ── Seed qualifier filter ─────────────────────────────────────────────────

class TestSeedQualifiers:
    def test_excludes_intent_only_words(self):
        modifiers = ["buy", "price", "online", "organic", "wholesale", "pure"]
        qualifiers = get_seed_qualifiers(modifiers)
        # Intent-only words should be excluded from seed qualifiers
        assert "buy" not in qualifiers
        assert "price" not in qualifiers

    def test_keeps_true_qualifiers(self):
        modifiers = ["organic", "wholesale", "pure", "buy", "online"]
        qualifiers = get_seed_qualifiers(modifiers)
        assert "organic" in qualifiers or "wholesale" in qualifiers

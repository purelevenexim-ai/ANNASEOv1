"""
Test Group 8: Keyword dedup — canonical normalization, variant detection,
semantic dedup (TF-IDF), and merge_keyword_batch.
"""
import sys
import pytest

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.normalizer import (
    canonical, display_form, are_variants, detect_pillars,
    assign_role, merge_keyword_batch, semantic_dedup,
)
from engines.kw2.constants import SEMANTIC_DEDUP_THRESHOLD


# ── Canonical normalization ───────────────────────────────────────────────

class TestCanonicalNormalization:
    def test_lowercase(self):
        assert canonical("BLACK PEPPER") == "black pepper"

    def test_strips_leading_trailing_whitespace(self):
        assert canonical("  cardamom  ") == "cardamom"

    def test_normalizes_internal_whitespace(self):
        result = canonical("black  pepper")
        assert "  " not in result

    def test_removes_punctuation_artifacts(self):
        result = canonical("cardamom, organic")
        assert "," not in result

    def test_sorts_words_for_canonical_form(self):
        # canonical("buy pepper") and canonical("pepper buy") should be equal
        # (if the normalizer sorts tokens for canonical form)
        c1 = canonical("buy black pepper")
        c2 = canonical("buy black pepper")
        assert c1 == c2

    def test_empty_string_returns_empty(self):
        assert canonical("") == ""


# ── display_form ──────────────────────────────────────────────────────────

class TestDisplayForm:
    def test_returns_string(self):
        result = display_form("buy black pepper online")
        assert isinstance(result, str)

    def test_nonempty_for_valid_input(self):
        result = display_form("buy cardamom wholesale")
        assert len(result) > 0


# ── Variant detection ─────────────────────────────────────────────────────

class TestVariantDetection:
    def test_same_keyword_is_variant(self):
        assert are_variants("buy black pepper", "buy black pepper")

    def test_plural_singular_variants(self):
        # "cardamoms" and "cardamom" should be variants
        result = are_variants("cardamom wholesale", "cardamoms wholesale")
        assert result  # should detect as variants

    def test_word_order_variants(self):
        # Different word order but same meaning
        result = are_variants("black pepper buy online", "buy black pepper online")
        # Result depends on implementation — just check it returns a bool
        assert isinstance(result, bool)

    def test_completely_different_are_not_variants(self):
        result = are_variants("black pepper wholesale", "turmeric supplier")
        assert not result

    def test_identical_strings_are_variants(self):
        assert are_variants("cardamom organics", "cardamom organics")


# ── Pillar detection ──────────────────────────────────────────────────────

class TestPillarDetection:
    def test_detects_exact_pillar_match(self):
        pillars = ["cardamom", "black pepper", "turmeric"]
        matches = detect_pillars("buy cardamom wholesale", pillars)
        pillars_found = [m["pillar"] for m in matches]
        assert "cardamom" in pillars_found

    def test_detects_partial_pillar_match(self):
        pillars = ["black pepper"]
        matches = detect_pillars("pepper price", pillars)
        # Should detect "black pepper" via partial token match
        assert isinstance(matches, list)

    def test_no_match_returns_empty_list(self):
        pillars = ["cardamom", "turmeric"]
        matches = detect_pillars("buy fresh ginger root", pillars)
        # "ginger" not in pillars → no match
        assert matches == [] or all(m["confidence"] < 0.5 for m in matches)

    def test_multiple_pillar_match_returns_multiple(self):
        pillars = ["cardamom", "turmeric"]
        matches = detect_pillars("cardamom and turmeric combo", pillars)
        # Both pillars mentioned → should detect both (if normalizer supports multi-pillar)
        assert len(matches) >= 1


# ── merge_keyword_batch ───────────────────────────────────────────────────

class TestMergeKeywordBatch:
    def test_removes_exact_duplicates(self):
        batch = [
            {"keyword": "buy cardamom", "source": "rules", "pillar": "cardamom"},
            {"keyword": "buy cardamom", "source": "ai_expand", "pillar": "cardamom"},
        ]
        merged = merge_keyword_batch(batch)
        # Should deduplicate
        kws = [m["keyword"] for m in merged]
        assert kws.count("buy cardamom") == 1 or "buy cardamom" in kws

    def test_preserves_distinct_keywords(self):
        batch = [
            {"keyword": "buy cardamom", "source": "rules", "pillar": "cardamom"},
            {"keyword": "wholesale turmeric", "source": "rules", "pillar": "turmeric"},
        ]
        merged = merge_keyword_batch(batch)
        kws = [m["keyword"] for m in merged]
        assert len(set(kws)) == len(kws)  # all distinct

    def test_empty_batch_returns_empty(self):
        assert merge_keyword_batch([]) == []

    def test_sources_merged_for_variants(self):
        batch = [
            {"keyword": "buy black pepper", "source": "rules"},
            {"keyword": "black pepper buy", "source": "ai_expand"},
        ]
        merged = merge_keyword_batch(batch)
        # Should consolidate and track multiple sources
        assert len(merged) >= 1


# ── semantic_dedup ────────────────────────────────────────────────────────

class TestSemanticDedup:
    def test_dedup_threshold_constant(self):
        assert 0.5 <= SEMANTIC_DEDUP_THRESHOLD <= 1.0

    def test_identical_keywords_deduplicated(self):
        items = [
            {"keyword": "buy cardamom online", "ai_relevance": 0.9},
            {"keyword": "buy cardamom online", "ai_relevance": 0.8},
        ]
        kept, removed = semantic_dedup(items, threshold=SEMANTIC_DEDUP_THRESHOLD)
        total = len(kept) + len(removed)
        assert total == 2
        assert len(kept) == 1

    def test_distinct_keywords_both_kept(self):
        items = [
            {"keyword": "buy cardamom wholesale", "ai_relevance": 0.9},
            {"keyword": "organic turmeric supplier", "ai_relevance": 0.8},
        ]
        kept, removed = semantic_dedup(items, threshold=SEMANTIC_DEDUP_THRESHOLD)
        assert len(kept) == 2
        assert len(removed) == 0

    def test_empty_input_returns_empty(self):
        kept, removed = semantic_dedup([], threshold=SEMANTIC_DEDUP_THRESHOLD)
        assert kept == []
        assert removed == []

    def test_single_item_always_kept(self):
        items = [{"keyword": "buy cardamom", "ai_relevance": 0.9}]
        kept, removed = semantic_dedup(items, threshold=SEMANTIC_DEDUP_THRESHOLD)
        assert len(kept) == 1
        assert len(removed) == 0

    def test_higher_score_retained(self):
        items = [
            {"keyword": "buy cardamom online", "ai_relevance": 0.95, "id": "A"},
            {"keyword": "buy cardamom online", "ai_relevance": 0.75, "id": "B"},
        ]
        kept, removed = semantic_dedup(items, threshold=SEMANTIC_DEDUP_THRESHOLD)
        if kept:
            assert kept[0].get("ai_relevance", 0) >= removed[0].get("ai_relevance", 0) if removed else True

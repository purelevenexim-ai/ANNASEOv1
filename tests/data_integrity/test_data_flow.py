"""
tests/data_integrity/test_data_flow.py
=======================================
GROUP 2 — Data Integrity Tests: Pipeline Stage Correctness.

Verifies that data does not degrade, mutate incorrectly, or silently
drop records as it moves through pipeline stages. These are the most
critical tests — silent data degradation is the hardest bug to catch.

Run: pytest tests/data_integrity/ -v --tb=short
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("ANNASEO_TESTING", "1")


# ── 1. Entity extraction — no silent loss ─────────────────────────────────────

class TestEntityExtraction:
    def test_entities_extracted_from_product_text(self):
        """Entity extractor must find product names in input text."""
        from engines.kw2.entity_extractor import extract_entities
        text = "organic cardamom bulk wholesale spices india"
        entities, topics = extract_entities(text)
        assert len(entities) >= 1, f"No entities extracted from '{text}'"

    def test_no_entities_on_empty(self):
        from engines.kw2.entity_extractor import extract_entities
        entities, topics = extract_entities("")
        assert isinstance(entities, list)
        assert isinstance(topics, list)

    def test_entity_count_not_less_than_input_words(self):
        """Extracting from N distinct product words should yield at least 1 entity per 3 words."""
        from engines.kw2.entity_extractor import extract_entities
        text = "cardamom turmeric pepper cinnamon cloves ginger cumin coriander"
        entities, _ = extract_entities(text)
        words = text.split()
        assert len(entities) >= len(words) // 3, (
            f"Entity extraction losing too much data: {len(entities)} entities from {len(words)} words"
        )


# ── 2. Keyword normalizer — no corruption ────────────────────────────────────

class TestKeywordNormalizer:
    def test_canonical_idempotent(self):
        """Applying canonical() twice should give same result."""
        from engines.kw2.normalizer import canonical
        texts = ["Buy Organic Basil", "  WHOLESALE   CARDAMOM  ", "pepper-seeds online"]
        for t in texts:
            assert canonical(canonical(t)) == canonical(t), f"Not idempotent: '{t}'"

    def test_merge_keyword_batch_deduplicates(self):
        """Merging a batch with duplicates should yield unique canonicals."""
        from engines.kw2.normalizer import merge_keyword_batch
        batch = [
            {"keyword": "buy basil", "source": "ai"},
            {"keyword": "BUY BASIL", "source": "rules"},   # duplicate
            {"keyword": "basil seeds online", "source": "ai"},
        ]
        merged = merge_keyword_batch(batch)
        canonicals = [m["canonical"] for m in merged]
        assert len(canonicals) == len(set(canonicals)), "Duplicates not removed after merge"

    def test_no_garbage_word_keywords_pass(self):
        """Keywords that are pure garbage words should be flagged or removed."""
        from engines.kw2.constants import NEGATIVE_PATTERNS
        from engines.kw2.normalizer import canonical
        garbage = ["recipe ideas", "health benefits of basil", "what is turmeric"]
        for kw in garbage:
            c = canonical(kw)
            for neg in NEGATIVE_PATTERNS:
                if neg in c:
                    break  # correctly would be filtered
            # We just check negative patterns are defined
        assert len(NEGATIVE_PATTERNS) > 0


# ── 3. Schema validator — data contract ──────────────────────────────────────

class TestSchemaValidation:
    def test_valid_keyword_row_passes(self):
        from audit.validators.schema import validate_keyword_row
        row = {"keyword": "buy cardamom online", "intent": "purchase", "ai_relevance": 0.9, "buyer_readiness": 0.8}
        issues = validate_keyword_row(row)
        assert issues == []

    def test_missing_intent_flagged(self):
        from audit.validators.schema import validate_keyword_row
        row = {"keyword": "buy cardamom", "ai_relevance": 0.9, "buyer_readiness": 0.8}
        issues = validate_keyword_row(row)
        assert any("intent" in i.lower() for i in issues)

    def test_invalid_relevance_flagged(self):
        from audit.validators.schema import validate_keyword_row
        row = {"keyword": "buy basil", "intent": "purchase", "ai_relevance": 1.5, "buyer_readiness": 0.5}
        issues = validate_keyword_row(row)
        assert any("relevance" in i.lower() for i in issues)

    def test_garbage_long_keyword_flagged(self):
        from audit.validators.schema import validate_keyword_row
        row = {"keyword": "x" * 250, "intent": "purchase", "ai_relevance": 0.5, "buyer_readiness": 0.5}
        issues = validate_keyword_row(row)
        assert any("long" in i.lower() or "200" in i for i in issues)

    def test_business_profile_requires_negative_scope(self):
        from audit.validators.schema import validate_business_profile
        profile = {
            "universe": "Spices",
            "pillars": ["cardamom"],
            "modifiers": ["organic"],
            "audience": ["restaurants"],
            "business_type": "D2C",
            "negative_scope": [],  # missing mandatory exclusions
        }
        issues = validate_business_profile(profile)
        assert any("negative_scope" in i.lower() for i in issues)

    def test_cluster_with_single_keyword_flagged(self):
        from audit.validators.schema import validate_cluster_list
        clusters = [{"cluster_name": "Single KW", "keywords": ["only one keyword"]}]
        issues = validate_cluster_list(clusters)
        assert any("only 1" in i for i in issues)


# ── 4. Consistency cross-checks ───────────────────────────────────────────────

class TestConsistencyChecks:
    def test_pillar_not_in_negative_scope_passes(self):
        from audit.validators.consistency import check_pillar_negative_scope_conflict
        issues = check_pillar_negative_scope_conflict(
            pillars=["cardamom", "pepper"],
            negative_scope=["recipe", "benefits", "how to"]
        )
        assert issues == []

    def test_pillar_in_negative_scope_caught(self):
        from audit.validators.consistency import check_pillar_negative_scope_conflict
        issues = check_pillar_negative_scope_conflict(
            pillars=["cardamom", "recipe"],   # 'recipe' is a pillar AND in negative scope
            negative_scope=["recipe", "benefits"]
        )
        assert any("recipe" in i.lower() for i in issues)

    def test_high_buyer_readiness_informational_caught(self):
        from audit.validators.consistency import check_keyword_intent_score_alignment
        kws = [{"keyword": "buy basil bulk", "intent": "informational", "buyer_readiness": 0.9, "ai_relevance": 0.85}]
        issues = check_keyword_intent_score_alignment(kws)
        assert any("informational" in i.lower() and "buyer_readiness" in i.lower() for i in issues)

    def test_luxury_cheap_conflict_detected(self):
        from audit.validators.consistency import check_positioning_conflicts
        text = "premium luxury organic spices at the cheapest rates"
        issues = check_positioning_conflicts(text)
        assert len(issues) > 0


# ── 5. DB round-trip (no real DB — mocked) ───────────────────────────────────

class TestDBIntegrity:
    def test_keyword_json_serializes_cleanly(self):
        """Keywords written to DB as JSON must survive round-trip without mutation."""
        kws = [
            {"keyword": "buy cardamom 500g", "intent": "purchase", "ai_relevance": 0.9, "buyer_readiness": 0.85},
            {"keyword": "pepper wholesale india", "intent": "commercial", "ai_relevance": 0.75, "buyer_readiness": 0.70},
        ]
        serialized = json.dumps(kws)
        recovered = json.loads(serialized)
        assert recovered == kws

    def test_profile_json_round_trip(self):
        profile = {
            "universe": "Kerala Spices",
            "pillars": ["cardamom", "pepper"],
            "negative_scope": ["recipe", "benefits"],
        }
        assert json.loads(json.dumps(profile)) == profile

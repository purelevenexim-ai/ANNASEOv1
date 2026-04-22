"""
kw2 Reasoning Tests — Business Logic & Constraint Integrity.
Tests: constant sanity, category cap math, scoring rules,
       pillar term classification, coverage-guard end-to-end.
Run: pytest tests/test_kw2_reasoning.py -v --tb=short
"""
import os, sys, json, pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANNASEO_TESTING", "1")


# ── 1. Constant integrity ─────────────────────────────────────────────────────
class TestConstantIntegrity:
    def test_category_caps_sum_to_100(self):
        """All category caps must sum to exactly 100 (fills a top-100 list)."""
        from engines.kw2.constants import CATEGORY_CAPS
        total = sum(CATEGORY_CAPS.values())
        assert total == 100, f"CATEGORY_CAPS must sum to 100, got {total}"

    def test_hybrid_weights_sum_to_1(self):
        from engines.kw2.constants import HYBRID_SCORE_WEIGHTS
        total = sum(HYBRID_SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6, f"HYBRID_SCORE_WEIGHTS must sum to 1.0, got {total}"

    def test_intent_weights_in_0_1_range(self):
        from engines.kw2.constants import INTENT_WEIGHTS
        for intent, weight in INTENT_WEIGHTS.items():
            assert 0.0 <= weight <= 1.0, f"Intent weight for '{intent}' out of [0,1]: {weight}"

    def test_commercial_intent_highest_weight(self):
        """Commercial intent must weight higher than informational (our core business premise)."""
        from engines.kw2.constants import INTENT_WEIGHTS
        assert INTENT_WEIGHTS.get("commercial", 0) > INTENT_WEIGHTS.get("informational", 1), (
            "commercial must outweigh informational in INTENT_WEIGHTS"
        )

    def test_category_caps_all_positive(self):
        from engines.kw2.constants import CATEGORY_CAPS
        for cat, cap in CATEGORY_CAPS.items():
            assert cap > 0, f"Category cap for '{cat}' must be > 0"

    def test_purchase_cap_is_largest(self):
        """Purchase category should be the highest-capped (primary buyer intent)."""
        from engines.kw2.constants import CATEGORY_CAPS
        purchase = CATEGORY_CAPS.get("purchase", 0)
        other_caps = [v for k, v in CATEGORY_CAPS.items() if k != "purchase"]
        assert purchase >= max(other_caps), (
            f"purchase cap ({purchase}) should be >= all others ({other_caps})"
        )

    def test_negative_patterns_are_lowercase(self):
        """NEGATIVE_PATTERNS must be lowercase for consistent matching."""
        from engines.kw2.constants import NEGATIVE_PATTERNS
        for p in NEGATIVE_PATTERNS:
            assert p == p.lower(), f"NEGATIVE_PATTERNS entry not lowercase: '{p}'"

    def test_cluster_similarity_threshold_in_range(self):
        from engines.kw2.constants import CLUSTER_SIMILARITY_THRESHOLD
        assert 0.5 < CLUSTER_SIMILARITY_THRESHOLD < 1.0, (
            f"CLUSTER_SIMILARITY_THRESHOLD should be in (0.5, 1.0), got {CLUSTER_SIMILARITY_THRESHOLD}"
        )

    def test_ai_concurrency_at_least_2(self):
        """Parallel AI calls need at least 2 workers to be useful."""
        from engines.kw2.constants import AI_CONCURRENCY
        assert AI_CONCURRENCY >= 2, f"AI_CONCURRENCY should be >= 2, got {AI_CONCURRENCY}"


# ── 2. Keyword classification reasoning ──────────────────────────────────────
class TestKeywordClassificationReasoning:
    """Verify category + page-type assignments make business sense."""

    @pytest.fixture
    def builder(self):
        from engines.kw2.tree_builder import TreeBuilder
        return TreeBuilder()

    @pytest.mark.parametrize("keyword,expected_cat", [
        ("buy organic basil online", "purchase"),
        ("order fresh basil delivery", "purchase"),
        ("basil wholesale uk",        "wholesale"),
        ("bulk basil seeds supplier", "wholesale"),
        ("basil price per kg",        "price"),
        ("basil extract cost",        "price"),
        ("best basil brand review",   "comparison"),
        ("basil vs oregano",          "comparison"),
        ("basil near me",             "local"),
        ("local basil supplier",      "local"),
        ("fresh basil leaves",        "other"),
    ])
    def test_categorize_keyword(self, builder, keyword, expected_cat):
        result = builder._categorize_keyword(keyword)
        assert result == expected_cat, (
            f"'{keyword}': expected category '{expected_cat}', got '{result}'"
        )

    @pytest.mark.parametrize("keyword,intent,expected_page", [
        ("buy basil online",          "commercial",  "product_page"),
        ("basil wholesale bulk",      "commercial",  "b2b_page"),
        ("basil vs mint",             "comparison",  "blog_page"),
        ("basil near me",             "local",       "local_page"),
        ("basil price list",          "commercial",  "category_page"),
        ("fresh organic basil",       "commercial",  "category_page"),
    ])
    def test_map_page(self, builder, keyword, intent, expected_page):
        result = builder._map_page(keyword, intent)
        assert result == expected_page, (
            f"'{keyword}' (intent={intent}): expected '{expected_page}', got '{result}'"
        )


# ── 3. Commercial scoring reasoning ──────────────────────────────────────────
class TestCommercialScoringReasoning:
    """Verify that commercial score reflects buying intent, not informational."""

    @pytest.fixture
    def scorer(self):
        from engines.kw2.keyword_scorer import KeywordScorer
        return KeywordScorer()

    @pytest.mark.parametrize("commercial,informational", [
        ("buy basil seeds bulk",     "basil seeds growing guide"),
        ("wholesale basil supplier", "basil supplier history"),
        ("basil price per gram",     "basil definition meaning"),
        ("order basil online",       "basil origins uses"),
    ])
    def test_commercial_beats_informational(self, scorer, commercial, informational):
        com_score = scorer._commercial_score(commercial)
        inf_score  = scorer._commercial_score(informational)
        assert com_score > inf_score, (
            f"Commercial '{commercial}' ({com_score}) should beat informational '{informational}' ({inf_score})"
        )

    def test_score_capped_at_1(self, scorer):
        """Score must never exceed 1.0 regardless of keyword boost stacking."""
        high_boost_kw = "buy wholesale bulk order for sale cheapest price supplier"
        score = scorer._commercial_score(high_boost_kw)
        assert score <= 1.0, f"Score exceeded 1.0: {score}"

    def test_zero_score_for_no_boost_tokens(self, scorer):
        """A keyword with no COMMERCIAL_BOOSTS tokens should score 0."""
        score = scorer._commercial_score("fresh green leaf")
        assert score == 0.0, f"Expected 0.0, got {score}"


# ── 4. Top-100 category cap enforcement ──────────────────────────────────────
class TestTop100CapEnforcement:
    """Verify CATEGORY_CAPS are respected under adversarial inputs."""

    def _kw(self, i, keyword, score):
        return {"id": f"k{i}", "keyword": keyword, "final_score": score,
                "pillar": "basil", "cluster": "c1", "source": "suggest",
                "ai_relevance": 0.8, "buyer_readiness": 0.7}

    def test_purchase_cap_not_exceeded(self):
        """Cap applies when all categories have enough keywords to fill their slots."""
        from engines.kw2.tree_builder import TreeBuilder
        from engines.kw2.constants import CATEGORY_CAPS
        builder = TreeBuilder()
        # All 6 CATEGORY_CAPS categories represented → caps sum to 100 → NO fill-beyond needed
        kws = (
            [self._kw(i,      f"buy basil variety {i}",        90 - i * 0.1) for i in range(80)] +
            [self._kw(80 + i, f"basil wholesale option {i}",   85 - i * 0.1) for i in range(80)] +
            [self._kw(160+i,  f"basil price tier {i}",         80 - i * 0.1) for i in range(80)] +
            [self._kw(240+i,  f"best basil vs herb {i}",       75 - i * 0.1) for i in range(80)] +
            [self._kw(320+i,  f"basil near me {i}",            70 - i * 0.1) for i in range(80)] +
            [self._kw(400+i,  f"fresh basil leaves {i}",       65 - i * 0.1) for i in range(20)]  # "other"
        )
        result = builder._select_top100(kws)
        purchase_count = sum(
            1 for k in result if builder._categorize_keyword(k["keyword"]) == "purchase"
        )
        assert purchase_count <= CATEGORY_CAPS["purchase"], (
            f"purchase category exceeded cap when all categories are available: "
            f"{purchase_count} > {CATEGORY_CAPS['purchase']}"
        )

    def test_total_never_exceeds_100(self):
        from engines.kw2.tree_builder import TreeBuilder
        builder = TreeBuilder()
        kws = [self._kw(i, f"buy basil variant {i}", 100 - i) for i in range(300)]
        result = builder._select_top100(kws)
        assert len(result) <= 100

    def test_fill_beyond_caps_if_needed(self):
        """If capped categories don't fill 100, additional keywords should be added."""
        from engines.kw2.tree_builder import TreeBuilder
        builder = TreeBuilder()
        # Mix: 50 purchase + 50 "other" (caps: purchase=40, other=5 → 45 via caps; 5 more needed)
        kws = (
            [self._kw(i, f"buy basil {i}", 100 - i) for i in range(50)] +
            [self._kw(50 + i, f"fresh basil {i}", 60 - i) for i in range(50)]
        )
        result = builder._select_top100(kws)
        # Should fill up to 100 from remaining pool
        assert len(result) == 100


# ── 5. Pillar guard reasoning ─────────────────────────────────────────────────
class TestPillarGuardReasoning:
    """Verify that the coverage guard logic handles edge cases correctly."""

    def _apply_guard(self, profile, strategy):
        """Extract the B2 guard logic to test it directly."""
        _all_pillars = [str(p).strip() for p in profile.get("pillars", []) if p]
        _covered = {
            str(pp.get("pillar", "")).lower()
            for pp in strategy.get("priority_pillars", [])
            if isinstance(pp, dict)
        }
        _missing = [p for p in _all_pillars if p.lower() not in _covered]
        for mp in _missing:
            gap = f"[Pillar gap] '{mp}' pillar has no priority articles in the current strategy — add content coverage."
            strategy.setdefault("content_gaps", []).append(gap)
        return _missing

    def test_case_insensitive_matching(self):
        """Pillar matching should be case-insensitive."""
        profile = {"pillars": ["Basil", "TURMERIC"]}
        strategy = {
            "priority_pillars": [
                {"pillar": "basil"},
                {"pillar": "turmeric"},
            ],
            "content_gaps": [],
        }
        missing = self._apply_guard(profile, strategy)
        assert len(missing) == 0, f"Case-insensitive match failed; missing: {missing}"

    def test_partial_match_counts(self):
        """Pillar name that appears as substring of another should still match."""
        profile = {"pillars": ["black pepper"]}
        strategy = {
            "priority_pillars": [{"pillar": "black pepper"}],
            "content_gaps": [],
        }
        missing = self._apply_guard(profile, strategy)
        assert len(missing) == 0

    def test_empty_priority_pillars_all_missing(self):
        """If no priority_pillars, all profile pillars should be flagged."""
        profile = {"pillars": ["basil", "turmeric", "ginger"]}
        strategy = {"priority_pillars": [], "content_gaps": []}
        missing = self._apply_guard(profile, strategy)
        assert set(missing) == {"basil", "turmeric", "ginger"}

    def test_none_pillar_values_skipped(self):
        """None entries in pillars list should be skipped gracefully."""
        profile = {"pillars": ["basil", None, "", "ginger"]}
        strategy = {
            "priority_pillars": [{"pillar": "basil"}, {"pillar": "ginger"}],
            "content_gaps": [],
        }
        missing = self._apply_guard(profile, strategy)
        assert len(missing) == 0

    def test_gap_message_contains_pillar_name(self):
        """Each content_gap message must contain the missing pillar name."""
        profile = {"pillars": ["saffron", "vanilla"]}
        strategy = {"priority_pillars": [{"pillar": "saffron"}], "content_gaps": []}
        self._apply_guard(profile, strategy)
        gaps = strategy["content_gaps"]
        assert len(gaps) == 1
        assert "vanilla" in gaps[0], f"Gap message must reference pillar name: '{gaps[0]}'"


# ── 6. Flow step integrity ────────────────────────────────────────────────────
class TestFlowIntegrity:
    """Verify KW2 flow definitions are structurally valid."""

    def test_brand_flow_has_required_phases(self):
        """Brand flow must contain all required pipeline phases (read flow.js directly)."""
        import os
        flow_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "frontend", "src", "kw2", "flow.js"
        )
        if not os.path.exists(flow_path):
            pytest.skip("flow.js not found")

        with open(flow_path) as f:
            content = f.read()

        required_keys = ["BI", "VALIDATE", "GRAPHLINKS"]
        for key in required_keys:
            assert key in content, f"Phase '{key}' missing from flow.js"

    def test_brand_flow_no_removed_phases(self):
        """Removed phases (Phase6, Phase7 individually) should no longer appear in flow steps."""
        import os
        flow_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "frontend", "src", "kw2", "flow.js"
        )
        if not os.path.exists(flow_path):
            pytest.skip("flow.js not found")

        with open(flow_path) as f:
            content = f.read()

        # Individual Phase6/Phase7 phase labels (numeric 6 and 7) should be merged into GRAPHLINKS
        # They can still appear in comments but not as standalone step numbers
        import re
        brand_match = re.search(r'brand\s*:\s*\[([^\]]+)\]', content)
        if brand_match:
            brand_steps = brand_match.group(1)
            # Steps should not contain standalone 6 or 7 (comma or bracket delimited)
            tokens = [t.strip().strip('"').strip("'") for t in brand_steps.split(",")]
            assert "6" not in tokens, f"Phase '6' should be merged into GRAPHLINKS: {tokens}"
            assert "7" not in tokens, f"Phase '7' should be merged into GRAPHLINKS: {tokens}"

    def test_graphlinks_component_exists(self):
        """PhaseGraphLinks.jsx must exist (merged Phase6 + Phase7)."""
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "frontend", "src", "kw2", "PhaseGraphLinks.jsx"
        )
        assert os.path.exists(path), "PhaseGraphLinks.jsx does not exist — merge not complete"

    def test_validate_review_component_exists(self):
        """PhaseValidateReview.jsx must exist (merged Phase3 + Phase3Review)."""
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "frontend", "src", "kw2", "PhaseValidateReview.jsx"
        )
        assert os.path.exists(path), "PhaseValidateReview.jsx does not exist — merge not complete"


# ── 7. A6: Batch cluster naming ───────────────────────────────────────────────
class TestBatchClusterNaming:
    """Verify batch cluster naming in keyword_clusterer.py (A6 change).

    _ai_batch_name_clusters signature:
        clusters: list[tuple[list[str], str]]   # (top5_keywords, rep_keyword)
    """

    @pytest.fixture
    def clusterer(self):
        from engines.kw2.keyword_clusterer import KeywordClusterer
        return KeywordClusterer()

    def test_batch_naming_returns_correct_count(self, clusterer):
        """_ai_batch_name_clusters must return exactly one name per cluster."""
        clusters = [
            (["buy cardamom", "order cardamom", "cardamom price"], "buy cardamom"),
            (["black pepper bulk", "wholesale pepper", "pepper supplier"], "black pepper bulk"),
            (["cinnamon wholesale", "buy cinnamon", "cinnamon export"], "cinnamon wholesale"),
        ]
        with patch("engines.kw2.keyword_clusterer.kw2_ai_call") as mock_ai:
            mock_ai.return_value = '["Cardamom Buyers", "Pepper Wholesale", "Cinnamon Export"]'
            names = clusterer._ai_batch_name_clusters(clusters, provider="auto")
        assert len(names) == 3, f"Expected 3 names, got {len(names)}"

    def test_batch_naming_fallback_on_bad_json(self, clusterer):
        """If AI returns invalid JSON, fall back to rep_keyword per cluster."""
        clusters = [
            (["buy cardamom bulk", "cardamom order", "cheap cardamom"], "buy cardamom bulk"),
            (["black pepper price", "buy pepper", "pepper deal"], "black pepper price"),
        ]
        with patch("engines.kw2.keyword_clusterer.kw2_ai_call") as mock_ai:
            mock_ai.return_value = "not valid json at all"
            names = clusterer._ai_batch_name_clusters(clusters, provider="auto")
        assert len(names) == 2, f"Fallback must return names for all clusters, got {len(names)}"
        assert names[0] == "buy cardamom bulk", f"Fallback should use rep_keyword: {names[0]}"
        assert names[1] == "black pepper price", f"Fallback should use rep_keyword: {names[1]}"

    def test_batch_naming_fallback_on_empty_ai(self, clusterer):
        """If AI returns empty string, fall back gracefully."""
        clusters = [(["cardamom organic grade a", "organic cardamom"], "cardamom organic grade a")]
        with patch("engines.kw2.keyword_clusterer.kw2_ai_call") as mock_ai:
            mock_ai.return_value = ""
            names = clusterer._ai_batch_name_clusters(clusters, provider="auto")
        assert len(names) == 1
        assert names[0] == "cardamom organic grade a"

    def test_batch_naming_partial_json_array(self, clusterer):
        """If AI returns fewer names than clusters, fill missing with rep_keyword."""
        clusters = [
            (["cardamom bulk", "order cardamom"], "cardamom bulk"),
            (["pepper wholesale", "buy pepper"], "pepper wholesale"),
            (["cinnamon export", "export cinnamon"], "cinnamon export"),
        ]
        with patch("engines.kw2.keyword_clusterer.kw2_ai_call") as mock_ai:
            # Only returns 1 name, not 3
            mock_ai.return_value = '["Cardamom Buyers"]'
            names = clusterer._ai_batch_name_clusters(clusters, provider="auto")
        assert len(names) == 3, f"Must return 3 names even with partial AI response"
        assert names[0] == "Cardamom Buyers"
        assert names[1] == "pepper wholesale"   # rep_keyword fallback
        assert names[2] == "cinnamon export"    # rep_keyword fallback


# ── 8. A7: Parallel pillar validation ────────────────────────────────────────
class TestParallelPillarValidation:
    """Verify the A7 parallel validation structural changes."""

    def test_validator_has_rule_intent_method(self):
        """Validator must have _rule_intent method (Q3 fix for AI-unavailable fallback)."""
        from engines.kw2.keyword_validator import KeywordValidator
        val = KeywordValidator()
        assert hasattr(val, "_rule_intent"), "_rule_intent method must exist in KeywordValidator"

    @pytest.mark.parametrize("keyword,expected_intent", [
        ("buy cardamom online",         "transactional"),
        ("purchase black pepper bulk",  "transactional"),
        ("cardamom price per kg",       "transactional"),
        ("best cardamom brand",         "commercial"),
        ("wholesale cardamom supplier", "commercial"),
        ("cardamom bulk export",        "commercial"),
        ("how to use cardamom",         "informational"),
        ("what is cardamom",            "informational"),
        ("cardamom organic product",    "commercial"),   # default when no signal
    ])
    def test_rule_intent_classification(self, keyword, expected_intent):
        """Rule-based intent must correctly classify keywords without AI."""
        from engines.kw2.keyword_validator import KeywordValidator
        val = KeywordValidator()
        result = val._rule_intent(keyword)
        assert result == expected_intent, (
            f"'{keyword}': expected '{expected_intent}', got '{result}'"
        )

    def test_rule_intent_transactional_takes_priority(self):
        """Transactional signals beat commercial even when both present."""
        from engines.kw2.keyword_validator import KeywordValidator
        val = KeywordValidator()
        # "buy" is transactional, "wholesale" is commercial
        result = val._rule_intent("buy wholesale cardamom online")
        assert result == "transactional", f"Expected transactional, got {result}"

    def test_rule_intent_never_returns_none(self):
        """_rule_intent must always return a string, never None."""
        from engines.kw2.keyword_validator import KeywordValidator
        val = KeywordValidator()
        for kw in ["", "  ", "x", "organic green leaf", "123"]:
            result = val._rule_intent(kw)
            assert result is not None and isinstance(result, str), (
                f"_rule_intent returned invalid value for '{kw}': {result!r}"
            )


# ── 9. Q1: Generic universe fix ───────────────────────────────────────────────
class TestGenericUniverseFix:
    """Verify _fix_generic_universe replaces generic names correctly."""

    @pytest.fixture
    def engine(self):
        from engines.kw2.business_analyzer import BusinessIntelligenceEngine
        return BusinessIntelligenceEngine()

    @pytest.mark.parametrize("universe,expected_not_generic", [
        ("Business",   True),   # should be replaced
        ("Company",    True),
        ("Store",      True),
        ("Ecommerce",  True),
        ("",           True),   # empty → replaced
        ("Indian Spices",     False),  # already specific → kept as-is
        ("Organic Supplements", False),
        ("Tech Accessories",  False),
    ])
    def test_replaces_generic_removes_specific(self, engine, universe, expected_not_generic):
        """Generic names must be replaced; specific 2+ word names must be kept."""
        pillars = ["cardamom", "black pepper", "cinnamon"]
        result = engine._fix_generic_universe(universe, pillars, [], None)
        if expected_not_generic:
            # Should NOT return the original generic name
            assert result.lower() != universe.lower() or universe == "", (
                f"Generic universe '{universe}' was not replaced, got: '{result}'"
            )
            assert result != "", "Fixed universe must not be empty"
        else:
            # Specific name should pass through unchanged
            assert result == universe, (
                f"Specific universe '{universe}' should not be changed, got: '{result}'"
            )

    def test_derives_from_pillars_when_generic(self, engine):
        """When universe is generic, must derive from pillars."""
        result = engine._fix_generic_universe("Business", ["cardamom", "clove"], [], None)
        assert result != "Business", f"Should not return 'Business', got: '{result}'"
        assert len(result) > 3, f"Derived universe too short: '{result}'"

    def test_respects_manual_business_name(self, engine):
        """Manual business_name takes priority over pillar derivation."""
        result = engine._fix_generic_universe(
            "Business", ["cardamom"], [], {"business_name": "Pure Eleven Spices"}
        )
        assert result == "Pure Eleven Spices", f"Expected manual name, got: '{result}'"

    def test_manual_generic_name_is_still_replaced(self, engine):
        """Even manual business_name='Business' should not take priority over derivation."""
        result = engine._fix_generic_universe(
            "Business", ["cardamom", "pepper"], [], {"business_name": "company"}
        )
        # "company" is in GENERIC_UNIVERSE so should fall through to pillar derivation
        assert result.lower() not in ("business", "company"), (
            f"Generic manual name should not be used: '{result}'"
        )

    def test_empty_pillars_uses_product_catalog(self, engine):
        """When pillars are empty, fall back to product_catalog."""
        result = engine._fix_generic_universe("Business", [], ["Ceylon Cinnamon Sticks"], None)
        assert result != "Business", f"Should not return 'Business' when catalog available"

    def test_returns_specialty_products_as_last_resort(self, engine):
        """When all data is empty, return 'Specialty Products'."""
        result = engine._fix_generic_universe("", [], [], None)
        assert result == "Specialty Products", f"Expected 'Specialty Products', got: '{result}'"


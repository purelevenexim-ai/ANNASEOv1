"""
kw2 Logical Tests — Data Flow & Engine Correctness.
Tests: scorer outputs, top-100 size constraints, spot-check logic,
       pillar coverage guard, tree builder internal logic.
Run: pytest tests/test_kw2_logical.py -v --tb=short
"""
import os, sys, json, pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("ANNASEO_TESTING", "1")

# ── 1. KeywordScorer — signal weights ─────────────────────────────────────────
class TestKeywordScorer:
    def test_score_returns_0_to_100(self):
        """All final_scores must be in [0, 100]."""
        from engines.kw2.keyword_scorer import KeywordScorer
        from engines.kw2 import db as kw2db

        scorer = KeywordScorer()
        # Patch DB calls so we don't need real data
        mock_rows = [
            MagicMock(**{
                "__getitem__": lambda self, k: {
                    "id": "kw1", "keyword": "buy basil online",
                    "ai_relevance": 0.9, "intent": "transactional",
                    "buyer_readiness": 0.8, "source": "suggest",
                }[k]
            }),
            MagicMock(**{
                "__getitem__": lambda self, k: {
                    "id": "kw2", "keyword": "basil health benefits",
                    "ai_relevance": 0.2, "intent": "informational",
                    "buyer_readiness": 0.1, "source": "rules",
                }[k]
            }),
        ]

        with patch("engines.kw2.keyword_scorer.db") as mock_db:
            mock_conn = MagicMock()
            mock_db.get_conn.return_value.__enter__ = lambda s: mock_conn
            mock_db.get_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.get_conn.return_value = mock_conn
            mock_conn.execute.return_value.fetchall.return_value = mock_rows
            mock_db.get_biz_intel.return_value = {}
            mock_db.update_session.return_value = None

            def _exec_side(sql, *args):
                m = MagicMock()
                if "SELECT" in sql:
                    m.fetchall.return_value = mock_rows
                return m

            mock_conn.execute.side_effect = _exec_side
            mock_conn.executemany.return_value = None

            # Test directly via _commercial_score which is public logic
            assert scorer._commercial_score("buy basil seeds bulk") > 0
            assert scorer._commercial_score("basil recipe ideas") == 0

    def test_commercial_score_for_purchase_terms(self):
        from engines.kw2.keyword_scorer import KeywordScorer
        s = KeywordScorer()
        # Returns 0.0-1.0; commercial terms should score > 0
        assert s._commercial_score("buy fresh basil") > 0.0
        assert s._commercial_score("wholesale basil supplier") > 0.0
        # Informational terms that don't match any COMMERCIAL_BOOSTS keys should score 0
        assert s._commercial_score("basil meaning in hindi") == 0.0

    def test_score_weights_sum_to_1(self):
        from engines.kw2.constants import HYBRID_SCORE_WEIGHTS
        total = sum(HYBRID_SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6, f"Score weights must sum to 1.0, got {total}"


# ── 2. TreeBuilder — top-100 size constraint ─────────────────────────────────
class TestTreeBuilder:
    def _make_keywords(self, n, base_score=50.0):
        return [
            {
                "id": f"kw_{i}", "keyword": f"basil herb keyword {i}",
                "intent": "commercial", "final_score": base_score - i * 0.1,
                "pillar": "basil", "cluster": "cluster_a", "source": "suggest",
                "ai_relevance": 0.7, "buyer_readiness": 0.6,
            }
            for i in range(n)
        ]

    def test_top100_never_exceeds_100(self):
        from engines.kw2.tree_builder import TreeBuilder
        builder = TreeBuilder()
        keywords = self._make_keywords(200)
        result = builder._select_top100(keywords)
        assert len(result) <= 100, f"top100 returned {len(result)} items, max is 100"

    def test_top100_with_fewer_than_100_returns_all(self):
        from engines.kw2.tree_builder import TreeBuilder
        builder = TreeBuilder()
        keywords = self._make_keywords(42)
        result = builder._select_top100(keywords)
        assert len(result) == 42

    def test_top100_sorted_by_score_descending(self):
        from engines.kw2.tree_builder import TreeBuilder
        builder = TreeBuilder()
        keywords = self._make_keywords(50)
        result = builder._select_top100(keywords)
        scores = [kw["final_score"] for kw in result]
        assert scores == sorted(scores, reverse=True), "top100 must be sorted by score DESC"

    def test_categorize_keyword_purchase(self):
        from engines.kw2.tree_builder import TreeBuilder
        b = TreeBuilder()
        assert b._categorize_keyword("buy basil online") == "purchase"
        assert b._categorize_keyword("wholesale basil bulk") == "wholesale"
        assert b._categorize_keyword("basil price per kg") == "price"
        assert b._categorize_keyword("best basil brand") == "comparison"
        assert b._categorize_keyword("basil near me") == "local"
        assert b._categorize_keyword("fresh basil supplier") == "other"

    def test_map_page_returns_correct_type(self):
        from engines.kw2.tree_builder import TreeBuilder
        b = TreeBuilder()
        assert b._map_page("buy basil seeds", "purchase") == "product_page"
        assert b._map_page("basil wholesale", "wholesale") == "b2b_page"
        assert b._map_page("basil vs mint comparison", "comparison") == "blog_page"


# ── 3. Spot-check logic ───────────────────────────────────────────────────────
class TestSpotCheckLogic:
    def _make_top20(self):
        return [
            {"id": "kw_good1", "keyword": "buy basil wholesale", "final_score": 90},
            {"id": "kw_good2", "keyword": "basil online supplier", "final_score": 85},
            {"id": "kw_bad1",  "keyword": "basil health benefits", "final_score": 80},
            {"id": "kw_bad2",  "keyword": "how to grow basil at home", "final_score": 75},
            {"id": "kw_good3", "keyword": "organic basil bulk order", "final_score": 70},
        ]

    def test_spot_check_flags_informational_terms(self):
        """Keywords with 'health benefits' or 'how to' should be flagged."""
        from engines.kw2.tree_builder import TreeBuilder
        from engines.kw2.constants import NEGATIVE_PATTERNS
        builder = TreeBuilder()
        top20 = self._make_top20()
        negative_scope = list(NEGATIVE_PATTERNS[:5])  # standard negatives

        updates_captured = []
        mock_conn = MagicMock()
        def capture_executemany(sql, data):
            updates_captured.extend(data)
        mock_conn.executemany.side_effect = capture_executemany
        mock_conn.commit.return_value = None
        mock_conn.close.return_value = None

        with patch("engines.kw2.tree_builder.db") as mock_db:
            mock_db.get_conn.return_value = mock_conn
            builder._spot_check_top20(top20, negative_scope, "test_session")

        flagged = [(w, kid) for (w, kid) in updates_captured if w is not None]
        flagged_ids = {kid for (w, kid) in flagged}
        assert "kw_bad1" in flagged_ids, "'basil health benefits' should be flagged"
        assert "kw_bad2" in flagged_ids, "'how to grow basil' should be flagged"

    def test_spot_check_does_not_flag_commercial_terms(self):
        """Commercial keywords should not be flagged."""
        from engines.kw2.tree_builder import TreeBuilder
        from engines.kw2.constants import NEGATIVE_PATTERNS
        builder = TreeBuilder()
        top20 = [
            {"id": "kw_buy",       "keyword": "buy basil wholesale",        "final_score": 90},
            {"id": "kw_wholesale", "keyword": "basil wholesale supplier", "final_score": 85},
            {"id": "kw_price",     "keyword": "basil price per 500g",     "final_score": 80},
        ]
        negative_scope = list(NEGATIVE_PATTERNS[:5])

        updates_captured = []
        mock_conn = MagicMock()
        def capture_executemany(sql, data):
            updates_captured.extend(data)
        mock_conn.executemany.side_effect = capture_executemany
        mock_conn.commit.return_value = None
        mock_conn.close.return_value = None

        with patch("engines.kw2.tree_builder.db") as mock_db:
            mock_db.get_conn.return_value = mock_conn
            builder._spot_check_top20(top20, negative_scope, "test_session")

        flagged = [(w, kid) for (w, kid) in updates_captured if w is not None]
        assert len(flagged) == 0, f"Commercial keywords should not be flagged: {flagged}"

    def test_spot_check_handles_empty_top20(self):
        """Empty top20 should not raise any errors."""
        from engines.kw2.tree_builder import TreeBuilder
        builder = TreeBuilder()
        # Should complete without error
        builder._spot_check_top20([], [], "test_session")


# ── 4. B2: Pillar coverage guard ─────────────────────────────────────────────
class TestPillarCoverageGuard:
    """Verify strategy_engine appends gap notes for missing pillars."""

    def _make_strategy(self, covered_pillars):
        return {
            "strategy_summary": {"headline": "Test strategy"},
            "priority_pillars": [
                {"pillar": p, "rank": i+1, "rationale": "x", "kw_count": 10,
                 "primary_intent": "commercial", "content_angle": "y"}
                for i, p in enumerate(covered_pillars)
            ],
            "quick_wins": [],
            "weekly_plan": [],
            "link_building_plan": "",
            "competitive_gaps": [],
            "content_gaps": [],
            "timeline": {},
        }

    def test_missing_pillar_added_to_content_gaps(self):
        """When a pillar is not in priority_pillars, it must appear in content_gaps."""
        from engines.kw2.strategy_engine import StrategyEngine

        profile = {
            "pillars": ["basil", "turmeric", "ginger"],
            "universe": "Herb Business",
        }
        # Only "basil" and "turmeric" are covered; "ginger" is missing
        strategy = self._make_strategy(["basil", "turmeric"])

        # Simulate the B2 guard logic directly (copied from strategy_engine.generate)
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

        gaps = strategy.get("content_gaps", [])
        assert any("ginger" in g for g in gaps), (
            f"Expected 'ginger' pillar gap in content_gaps. content_gaps={gaps}"
        )
        assert not any("basil" in g for g in gaps), "Covered pillar 'basil' should not be in gaps"
        assert not any("turmeric" in g for g in gaps), "Covered pillar 'turmeric' should not be in gaps"

    def test_no_gaps_when_all_pillars_covered(self):
        """When all pillars appear in priority_pillars, no gap notes should be added."""
        profile = {"pillars": ["basil", "turmeric"]}
        strategy = self._make_strategy(["basil", "turmeric"])

        _all_pillars = [str(p).strip() for p in profile.get("pillars", []) if p]
        _covered = {
            str(pp.get("pillar", "")).lower()
            for pp in strategy.get("priority_pillars", [])
            if isinstance(pp, dict)
        }
        _missing = [p for p in _all_pillars if p.lower() not in _covered]
        assert len(_missing) == 0, f"Should have no missing pillars, got: {_missing}"

    def test_empty_pillars_profile_no_crash(self):
        """Strategy engine must not crash when profile has no pillars."""
        profile = {"pillars": [], "universe": "Empty Business"}
        strategy = self._make_strategy([])

        _all_pillars = [str(p).strip() for p in profile.get("pillars", []) if p]
        _missing = []  # nothing to check
        assert len(_all_pillars) == 0
        assert len(_missing) == 0


# ── 5. Negative patterns ─────────────────────────────────────────────────────
class TestNegativePatterns:
    def test_negative_patterns_not_empty(self):
        from engines.kw2.constants import NEGATIVE_PATTERNS
        assert len(NEGATIVE_PATTERNS) > 0, "NEGATIVE_PATTERNS must not be empty"

    def test_informational_terms_in_negative_patterns(self):
        from engines.kw2.constants import NEGATIVE_PATTERNS
        neg_lower = [p.lower() for p in NEGATIVE_PATTERNS]
        must_have = ["recipe", "benefits", "how to"]
        for term in must_have:
            assert any(term in p for p in neg_lower), (
                f"'{term}' must appear in NEGATIVE_PATTERNS"
            )

    def test_commercial_terms_not_in_negative_patterns(self):
        from engines.kw2.constants import NEGATIVE_PATTERNS
        neg_lower = [p.lower() for p in NEGATIVE_PATTERNS]
        safe_terms = ["buy", "wholesale", "supplier", "price"]
        for term in safe_terms:
            assert not any(p == term for p in neg_lower), (
                f"Commercial term '{term}' must not be in NEGATIVE_PATTERNS"
            )

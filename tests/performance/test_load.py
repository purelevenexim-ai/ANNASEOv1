"""
tests/performance/test_load.py
================================
ADVANCED — Performance Tests: Speed & Memory Constraints.

Validates that key pipeline components complete within acceptable time budgets.
Does NOT make real AI calls — pure CPU/memory tests on rule-based components.

Thresholds (configurable via env vars):
  AUDIT_NORMALIZER_MAX_MS  = 500ms for 1000 keywords
  AUDIT_SCORER_MAX_MS      = 200ms per keyword batch
  AUDIT_TREE_MAX_MS        = 100ms for top-100 build

Run: pytest tests/performance/ -v --tb=short
"""
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("ANNASEO_TESTING", "1")

_NORMALIZER_MAX_MS = int(os.getenv("AUDIT_NORMALIZER_MAX_MS", "500"))
_SCORER_MAX_MS = int(os.getenv("AUDIT_SCORER_MAX_MS", "200"))
_TREE_MAX_MS = int(os.getenv("AUDIT_TREE_MAX_MS", "100"))


def _elapsed_ms(fn, *args, **kwargs) -> float:
    t = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t) * 1000


# ── Normalizer throughput ─────────────────────────────────────────────────────

class TestNormalizerPerformance:
    def _make_batch(self, n: int) -> list[dict]:
        return [
            {"keyword": f"buy organic cardamom seeds batch {i}", "source": "ai"}
            for i in range(n)
        ]

    def test_canonical_1000_keywords_under_500ms(self):
        from engines.kw2.normalizer import canonical
        keywords = [f"buy organic spice variant {i}" for i in range(1000)]
        elapsed = _elapsed_ms(lambda: [canonical(k) for k in keywords])
        assert elapsed < _NORMALIZER_MAX_MS, (
            f"canonical() for 1000 keywords took {elapsed:.0f}ms > {_NORMALIZER_MAX_MS}ms"
        )

    def test_merge_batch_100_keywords_under_200ms(self):
        from engines.kw2.normalizer import merge_keyword_batch
        batch = self._make_batch(100)
        elapsed = _elapsed_ms(merge_keyword_batch, batch)
        assert elapsed < 200, (
            f"merge_keyword_batch(100) took {elapsed:.0f}ms — too slow"
        )


# ── Tree builder throughput ───────────────────────────────────────────────────

class TestTreeBuilderPerformance:
    def _make_keywords(self, n: int) -> list[dict]:
        return [
            {
                "id": f"kw{i}", "keyword": f"keyword variant {i}",
                "hybrid_score": 100.0 - i * 0.1, "category": "purchase",
                "intent": "purchase", "pillar": "cardamom",
            }
            for i in range(n)
        ]

    def test_top100_from_500_under_100ms(self):
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        kws = self._make_keywords(500)
        elapsed = _elapsed_ms(tb._select_top100, kws)
        assert elapsed < _TREE_MAX_MS, (
            f"_select_top100(500 keywords) took {elapsed:.0f}ms > {_TREE_MAX_MS}ms"
        )

    def test_top100_from_5000_under_500ms(self):
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        kws = self._make_keywords(5000)
        elapsed = _elapsed_ms(tb._select_top100, kws)
        assert elapsed < 500, (
            f"_select_top100(5000 keywords) took {elapsed:.0f}ms — acceptable max is 500ms"
        )


# ── Audit validator throughput ────────────────────────────────────────────────

class TestAuditValidatorPerformance:
    def _make_keyword_list(self, n: int) -> list[dict]:
        intents = ["purchase", "commercial", "informational", "local", "comparison"]
        return [
            {
                "keyword": f"buy spice variant {i} online",
                "intent": intents[i % len(intents)],
                "ai_relevance": 0.7 + (i % 3) * 0.1,
                "buyer_readiness": 0.6 + (i % 4) * 0.1,
            }
            for i in range(n)
        ]

    def test_schema_validate_1000_kws_under_500ms(self):
        from audit.validators.schema import validate_keyword_list
        kws = self._make_keyword_list(1000)
        elapsed = _elapsed_ms(validate_keyword_list, kws)
        assert elapsed < 500, (
            f"validate_keyword_list(1000) took {elapsed:.0f}ms"
        )

    def test_full_ai_validate_100_kws_under_300ms(self):
        from audit.validators.ai_reasoning import validate_ai_output
        result = {"keywords": self._make_keyword_list(100)}
        elapsed = _elapsed_ms(validate_ai_output, result)
        assert elapsed < 300, (
            f"validate_ai_output(100 kws) took {elapsed:.0f}ms"
        )


# ── Regression diff throughput ────────────────────────────────────────────────

class TestRegressionDiffPerformance:
    def _make_output(self, n: int) -> dict:
        return {
            "keywords": [{"keyword": f"test keyword {i}", "intent": "purchase", "ai_relevance": 0.8, "buyer_readiness": 0.7} for i in range(n)],
            "profile": {"universe": "Test", "pillars": ["product_a", "product_b"]},
        }

    def test_compare_1000_kw_outputs_under_200ms(self):
        from audit.regression.diff import compare_outputs
        out1 = self._make_output(1000)
        out2 = self._make_output(950)  # slightly different
        elapsed = _elapsed_ms(compare_outputs, out1, out2)
        assert elapsed < 200, (
            f"compare_outputs(1000 kws) took {elapsed:.0f}ms"
        )

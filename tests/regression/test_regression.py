"""
tests/regression/test_regression.py
=====================================
GROUP 4 — Regression Tests: Stability Over Time.

Compares current pipeline output against saved golden baselines.
On first run, saves baselines automatically.
On subsequent runs, alerts if output has drifted significantly.

Threshold: similarity_score >= 0.85 = stable, < 0.75 = critical drift

Run: pytest tests/regression/ -v --tb=short
Run with baseline refresh: pytest tests/regression/ -v -k "refresh" --capture=no
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("ANNASEO_TESTING", "1")

_DRIFT_WARN = 0.85
_DRIFT_CRITICAL = 0.75


# ── Golden output fixtures ────────────────────────────────────────────────────
# These represent what the system SHOULD produce for stable test cases.
# They serve as the reference point for regression.

GOLDEN_SPICE_OUTPUT = {
    "profile": {
        "universe": "Indian Spices",
        "pillars": ["cardamom", "black pepper", "turmeric"],
        "modifiers": ["organic", "wholesale", "bulk"],
        "audience": ["restaurants", "home cooks"],
        "business_type": "D2C",
        "geo_scope": "India",
        "negative_scope": ["recipe", "benefits", "how to", "what is"],
    },
    "keywords": [
        {"keyword": "buy organic cardamom online", "intent": "purchase", "ai_relevance": 0.92, "buyer_readiness": 0.88},
        {"keyword": "cardamom wholesale supplier india", "intent": "commercial", "ai_relevance": 0.85, "buyer_readiness": 0.80},
        {"keyword": "bulk turmeric price per kg", "intent": "transactional", "ai_relevance": 0.78, "buyer_readiness": 0.75},
        {"keyword": "black pepper near me", "intent": "local", "ai_relevance": 0.70, "buyer_readiness": 0.65},
    ],
    "clusters": [
        {"cluster_name": "Wholesale Bulk Orders", "keywords": ["cardamom wholesale", "bulk pepper price"]},
        {"cluster_name": "Online Purchase", "keywords": ["buy cardamom online", "order spices india"]},
    ],
    "confidence": 0.82,
}


# ── 1. Store tests ────────────────────────────────────────────────────────────

class TestRegressionStore:
    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        from audit.regression import store
        monkeypatch.setattr(store, "_BASELINE_DIR", tmp_path / "baselines")

        store.save_baseline("test_case_1", {"keywords": ["buy basil"], "confidence": 0.8})
        loaded = store.load_baseline("test_case_1")
        assert "keywords" in loaded

    def test_load_nonexistent_returns_empty(self, tmp_path, monkeypatch):
        from audit.regression import store
        monkeypatch.setattr(store, "_BASELINE_DIR", tmp_path / "baselines")

        result = store.load_baseline("nonexistent_case_xyz")
        assert result == {}

    def test_overwrite_protection(self, tmp_path, monkeypatch):
        from audit.regression import store
        monkeypatch.setattr(store, "_BASELINE_DIR", tmp_path / "baselines")

        store.save_baseline("protected_case", {"data": 1})
        with pytest.raises(FileExistsError):
            store.save_baseline("protected_case", {"data": 2})  # no overwrite=True

    def test_overwrite_with_flag(self, tmp_path, monkeypatch):
        from audit.regression import store
        monkeypatch.setattr(store, "_BASELINE_DIR", tmp_path / "baselines")

        store.save_baseline("overwrite_case", {"data": 1})
        store.save_baseline("overwrite_case", {"data": 2}, overwrite=True)
        loaded = store.load_baseline("overwrite_case")
        assert loaded["data"] == 2

    def test_list_baselines(self, tmp_path, monkeypatch):
        from audit.regression import store
        monkeypatch.setattr(store, "_BASELINE_DIR", tmp_path / "baselines")

        store.save_baseline("case_a", {"data": "a"})
        store.save_baseline("case_b", {"data": "b"})
        cases = store.list_baselines()
        assert "case_a" in cases
        assert "case_b" in cases


# ── 2. Diff / compare tests ───────────────────────────────────────────────────

class TestRegressionDiff:
    def test_identical_outputs_score_1(self):
        from audit.regression.diff import compare_outputs
        assert compare_outputs(GOLDEN_SPICE_OUTPUT, GOLDEN_SPICE_OUTPUT) == 1.0

    def test_empty_baseline_score_1(self):
        from audit.regression.diff import compare_outputs
        # No baseline = first run = perfect score (not a regression)
        assert compare_outputs(GOLDEN_SPICE_OUTPUT, {}) == 1.0

    def test_completely_different_output_low_score(self):
        from audit.regression.diff import compare_outputs
        different = {
            "profile": {"universe": "Fashion", "pillars": ["shoes", "bags"], "pillars": ["bags"]},
            "keywords": [{"keyword": "buy shoes online", "intent": "purchase", "ai_relevance": 0.9, "buyer_readiness": 0.8}],
        }
        score = compare_outputs(different, GOLDEN_SPICE_OUTPUT)
        assert score < 0.5, f"Expected low score for unrelated output, got {score}"

    def test_partial_overlap_score_in_range(self):
        from audit.regression.diff import compare_outputs
        partial = {
            "profile": GOLDEN_SPICE_OUTPUT["profile"],  # same profile
            "keywords": GOLDEN_SPICE_OUTPUT["keywords"][:2],  # only half the keywords
        }
        score = compare_outputs(partial, GOLDEN_SPICE_OUTPUT)
        assert 0.0 < score < 1.0

    def test_diff_report_severity_labels(self):
        from audit.regression.diff import diff_report

        # Identical → ok
        rep = diff_report(GOLDEN_SPICE_OUTPUT, GOLDEN_SPICE_OUTPUT)
        assert rep["severity"] == "ok"

        # Completely different → critical
        empty = {"keywords": [], "profile": {}, "clusters": [], "confidence": 0.0}
        rep = diff_report(empty, GOLDEN_SPICE_OUTPUT)
        assert rep["severity"] in ("warn", "critical")

    def test_diff_report_tracks_removed_keywords(self):
        from audit.regression.diff import diff_report
        reduced = {**GOLDEN_SPICE_OUTPUT, "keywords": GOLDEN_SPICE_OUTPUT["keywords"][:1]}
        rep = diff_report(reduced, GOLDEN_SPICE_OUTPUT)
        assert len(rep["removed_keywords"]) >= 1

    def test_diff_report_tracks_new_keywords(self):
        from audit.regression.diff import diff_report
        extra_kw = {"keyword": "new exotic spice online", "intent": "purchase", "ai_relevance": 0.9, "buyer_readiness": 0.8}
        expanded = {**GOLDEN_SPICE_OUTPUT, "keywords": GOLDEN_SPICE_OUTPUT["keywords"] + [extra_kw]}
        rep = diff_report(expanded, GOLDEN_SPICE_OUTPUT)
        assert "new exotic spice online" in rep["new_keywords"]


# ── 3. Stability assertion ────────────────────────────────────────────────────

class TestRegressionStability:
    """
    These tests verify the CURRENT output of key pipeline components
    against known-good values. If they fail, something in the pipeline
    changed that affects output quality.
    """

    def test_constants_version_stability(self):
        """Core constants must not change without a deliberate version bump."""
        from engines.kw2.constants import CATEGORY_CAPS, HYBRID_SCORE_WEIGHTS
        assert sum(CATEGORY_CAPS.values()) == 100
        assert abs(sum(HYBRID_SCORE_WEIGHTS.values()) - 1.0) < 1e-6

    def test_canonical_output_stable(self):
        """canonical() must produce same output for same inputs across versions.
        canonical() sorts tokens alphabetically — this is the defined contract."""
        from engines.kw2.normalizer import canonical
        # Run same input multiple times — must be identical each time
        inputs = ["Buy Organic Cardamom ONLINE", "  BLACK  PEPPER  ", "turmeric powder"]
        for inp in inputs:
            results = [canonical(inp) for _ in range(3)]
            assert len(set(results)) == 1, f"canonical({inp!r}) is not deterministic: {results}"
            # Tokens must always be sorted alphabetically
            tokens = results[0].split()
            assert tokens == sorted(tokens), f"canonical({inp!r}) tokens not sorted: {tokens}"

    def test_negative_patterns_still_present(self):
        """Critical negative patterns must always be in constants."""
        from engines.kw2.constants import NEGATIVE_PATTERNS
        # Check at least one recipe and one how-to variant is present
        has_recipe = any("recipe" in p for p in NEGATIVE_PATTERNS)
        has_howto = any("how to" in p for p in NEGATIVE_PATTERNS)
        has_benefits = any("benefit" in p for p in NEGATIVE_PATTERNS)
        has_whatis = any("what is" in p or "what are" in p for p in NEGATIVE_PATTERNS)
        assert has_recipe, "No 'recipe' pattern in NEGATIVE_PATTERNS"
        assert has_howto, "No 'how to' pattern in NEGATIVE_PATTERNS"
        assert has_benefits, "No 'benefits' pattern in NEGATIVE_PATTERNS"
        assert has_whatis, "No 'what is' pattern in NEGATIVE_PATTERNS"

    def test_purchase_intent_weight_unchanged(self):
        """purchase intent must always be highest priority."""
        from engines.kw2.constants import CATEGORY_CAPS, INTENT_WEIGHTS
        purchase_cap = CATEGORY_CAPS.get("purchase", 0)
        other_caps = [v for k, v in CATEGORY_CAPS.items() if k != "purchase"]
        assert purchase_cap >= max(other_caps), "purchase cap was lowered below another category"

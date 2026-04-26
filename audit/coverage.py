"""
audit/coverage.py
==================
Audit score computation and test coverage tracking.

Combines:
  - Functional check (did pipeline produce output?)
  - AI quality score (from validators/ai_reasoning.py)
  - Regression stability (from regression/diff.py)
  - Confidence signal (pipeline's own confidence field)
  - LLM judge score (optional — requires Ollama)

Weights:
  functional   30%
  ai_quality   30%
  regression   20%
  confidence   20%

Usage:
    from audit.coverage import compute_audit_score
    report = compute_audit_score(result, ai_verdict, regression_score)
"""
from __future__ import annotations
from typing import Any


# ── Audit dimension weights ───────────────────────────────────────────────────
_WEIGHTS = {
    "functional": 0.30,
    "ai_quality": 0.30,
    "regression": 0.20,
    "confidence": 0.20,
}

# Test coverage manifest — update as new tests are added
# Format: {group: count_of_tests}
_TEST_MANIFEST: dict[str, int] = {
    "functional": 0,       # updated by test runner
    "data_integrity": 0,
    "ai_reasoning": 0,
    "regression": 0,
    "human_validation": 0,
    "performance": 0,
    "chaos": 0,
}


def compute_audit_score(
    result: dict[str, Any],
    ai_verdict: dict[str, Any],
    regression_score: float,
    llm_judge_score: float | None = None,
) -> dict[str, Any]:
    """
    Compute the composite audit score for a single pipeline run.

    Args:
        result:           Raw pipeline output dict
        ai_verdict:       Output of validate_ai_output()
        regression_score: Output of compare_outputs() — float 0..1
        llm_judge_score:  Optional LLM judge final_score / 10 — float 0..1

    Returns:
        {
          "final_score": float,        # 0..1
          "grade": str,                # A/B/C/D/F
          "breakdown": dict,
          "passed": bool,
          "recommendations": list[str],
        }
    """
    breakdown: dict[str, float] = {}

    # 1. Functional: did we get output at all?
    has_output = bool(
        result.get("keywords") or result.get("clusters") or result.get("strategy")
    )
    breakdown["functional"] = 1.0 if has_output else 0.0

    # 2. AI quality (0..1 from ai_verdict score)
    breakdown["ai_quality"] = float(ai_verdict.get("score", 0.0))

    # 3. Regression stability
    breakdown["regression"] = float(regression_score)

    # 4. Pipeline's own confidence signal (0..1 or 0..100 normalised)
    raw_conf = result.get("confidence", 0.5)
    if isinstance(raw_conf, (int, float)):
        conf = float(raw_conf)
        if conf > 1.0:
            conf = conf / 100.0  # normalise 0-100 → 0-1
        breakdown["confidence"] = min(max(conf, 0.0), 1.0)
    else:
        breakdown["confidence"] = 0.5

    # 5. Optional LLM judge override (blends into ai_quality)
    if llm_judge_score is not None:
        judge_norm = min(max(float(llm_judge_score) / 10.0, 0.0), 1.0)
        # Blend: 60% rule-based ai_quality, 40% LLM judge
        breakdown["ai_quality"] = round(
            0.60 * breakdown["ai_quality"] + 0.40 * judge_norm, 3
        )

    # Weighted final score
    final = sum(_WEIGHTS[k] * breakdown.get(k, 0.0) for k in _WEIGHTS)
    final = round(final, 3)

    grade = _grade(final)
    passed = final >= 0.70  # 70% composite = production-safe

    recommendations = _recommend(breakdown, ai_verdict)

    return {
        "final_score": final,
        "grade": grade,
        "passed": passed,
        "breakdown": breakdown,
        "weights": _WEIGHTS,
        "recommendations": recommendations,
    }


def _grade(score: float) -> str:
    if score >= 0.90:
        return "A"
    if score >= 0.80:
        return "B"
    if score >= 0.70:
        return "C"
    if score >= 0.55:
        return "D"
    return "F"


def _recommend(breakdown: dict, ai_verdict: dict) -> list[str]:
    recs: list[str] = []
    if breakdown.get("functional", 1.0) < 1.0:
        recs.append("Pipeline produced no output — check crawl and extraction stages")
    if breakdown.get("ai_quality", 1.0) < 0.7:
        recs.append("AI quality is low — review keyword validation and schema issues")
    if breakdown.get("regression", 1.0) < 0.85:
        recs.append("Regression score < 0.85 — inspect keyword/pillar drift since last baseline")
    if breakdown.get("confidence", 1.0) < 0.5:
        recs.append("Pipeline confidence is low — check data source quality and crawl depth")
    for failure in (ai_verdict.get("failures") or [])[:3]:
        recs.append(f"Fix: {failure}")
    return recs


def compute_test_coverage(test_results: dict[str, int]) -> dict[str, Any]:
    """
    Given a {group: tests_passed} dict, compute coverage vs manifest.
    """
    total_planned = sum(_TEST_MANIFEST.values()) or 1
    total_run = sum(test_results.values())
    return {
        "coverage_ratio": round(total_run / total_planned, 2),
        "by_group": {
            grp: {
                "planned": _TEST_MANIFEST.get(grp, 0),
                "run": test_results.get(grp, 0),
            }
            for grp in _TEST_MANIFEST
        },
    }

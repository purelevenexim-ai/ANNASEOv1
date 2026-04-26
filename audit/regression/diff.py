"""
audit/regression/diff.py
=========================
Compare a current pipeline output against a saved baseline.

Score 0.0 = completely different, 1.0 = identical.

Three comparison dimensions:
  1. Keyword set similarity (Jaccard)
  2. Pillar set similarity
  3. Confidence proximity (if present)

Additional diagnostics:
  - New keywords added since baseline
  - Keywords that disappeared
  - Pillar drift
"""
from __future__ import annotations
from typing import Any


def compare_outputs(current: dict[str, Any], baseline: dict[str, Any]) -> float:
    """
    Fast similarity score between current and baseline output.
    Returns float in [0.0, 1.0]. A score < 0.85 should trigger investigation.
    """
    if not baseline:
        return 1.0  # No baseline yet → first run is always "perfect"

    scores: list[float] = []

    # ── Keyword set (Jaccard) ─────────────────────────────────────────────────
    kw_curr = {k.get("keyword", "").lower() for k in (current.get("keywords") or [])}
    kw_base = {k.get("keyword", "").lower() for k in (baseline.get("keywords") or [])}
    if kw_curr or kw_base:
        scores.append(len(kw_curr & kw_base) / max(len(kw_curr | kw_base), 1))

    # ── Pillar set (Jaccard) ──────────────────────────────────────────────────
    curr_prof = current.get("profile") or current.get("business_profile") or {}
    base_prof = baseline.get("profile") or baseline.get("business_profile") or {}
    p_curr = set(curr_prof.get("pillars", []))
    p_base = set(base_prof.get("pillars", []))
    if p_curr or p_base:
        scores.append(len(p_curr & p_base) / max(len(p_curr | p_base), 1))

    # ── Confidence proximity ──────────────────────────────────────────────────
    c_curr = current.get("confidence")
    c_base = baseline.get("confidence")
    if c_curr is not None and c_base is not None:
        delta = abs(float(c_curr) - float(c_base))
        scores.append(max(0.0, 1.0 - delta / 0.5))  # 0.5+ drift → 0

    # ── Cluster name overlap ──────────────────────────────────────────────────
    cl_curr = {c.get("cluster_name", "").lower() for c in (current.get("clusters") or [])}
    cl_base = {c.get("cluster_name", "").lower() for c in (baseline.get("clusters") or [])}
    if cl_curr or cl_base:
        scores.append(len(cl_curr & cl_base) / max(len(cl_curr | cl_base), 1))

    return round(sum(scores) / max(len(scores), 1), 3)


def diff_report(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """
    Detailed regression diff report between current and baseline.
    """
    score = compare_outputs(current, baseline)

    kw_curr = {k.get("keyword", "").lower() for k in (current.get("keywords") or [])}
    kw_base = {k.get("keyword", "").lower() for k in (baseline.get("keywords") or [])}
    new_kws = sorted(kw_curr - kw_base)
    removed_kws = sorted(kw_base - kw_curr)

    curr_prof = current.get("profile") or current.get("business_profile") or {}
    base_prof = baseline.get("profile") or baseline.get("business_profile") or {}
    p_curr = set(curr_prof.get("pillars", []))
    p_base = set(base_prof.get("pillars", []))
    new_pillars = sorted(p_curr - p_base)
    removed_pillars = sorted(p_base - p_curr)

    kw_count_change = len(kw_curr) - len(kw_base)
    severity = "ok" if score >= 0.9 else ("warn" if score >= 0.75 else "critical")

    return {
        "similarity_score": score,
        "severity": severity,
        "keyword_count": {"current": len(kw_curr), "baseline": len(kw_base), "delta": kw_count_change},
        "new_keywords": new_kws[:20],
        "removed_keywords": removed_kws[:20],
        "new_pillars": new_pillars,
        "removed_pillars": removed_pillars,
        "confidence_current": current.get("confidence"),
        "confidence_baseline": baseline.get("confidence"),
        "recommendation": (
            "✅ Stable" if severity == "ok" else
            "⚠️ Minor drift — review new/removed keywords" if severity == "warn" else
            "🔴 CRITICAL drift — investigate pipeline changes before shipping"
        ),
    }

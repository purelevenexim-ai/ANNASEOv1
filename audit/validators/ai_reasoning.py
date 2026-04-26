"""
audit/validators/ai_reasoning.py
=================================
Top-level AI output quality gate.

Combines schema + consistency checks into a single score dict.
Also provides a simple similarity metric for determinism testing.

Usage:
    from audit.validators.ai_reasoning import validate_ai_output, measure_similarity
    score = validate_ai_output(result)
    similarity = measure_similarity(out1, out2)
"""
from __future__ import annotations
import re
from typing import Any

from audit.validators.schema import (
    validate_keyword_list,
    validate_business_profile,
    validate_cluster_list,
    validate_strategy,
)
from audit.validators.consistency import run_all_consistency_checks


def validate_ai_output(result: dict[str, Any], source_text: str = "") -> dict[str, Any]:
    """
    Full AI output validation gate.

    Input `result` should be the merged output from a kw2 session or pipeline run,
    containing any/all of: keywords, profile, clusters, strategy.

    Returns:
        {
          "valid": bool,
          "score": float (0.0-1.0),
          "failures": list[str],
          "warnings": list[str],
          "schema": {...},
          "consistency": {...},
        }
    """
    failures: list[str] = []
    warnings: list[str] = []
    checks_run = 0
    checks_passed = 0

    schema_results: dict[str, Any] = {}
    consistency_result: dict[str, Any] = {}

    # ── 1. Empty output gate ──────────────────────────────────────────────────
    keywords = result.get("keywords") or result.get("top_keywords") or []
    _profile_raw = result.get("profile") or result.get("business_profile") or {}
    profile = _profile_raw if isinstance(_profile_raw, dict) else {}
    _clusters_raw = result.get("clusters") or []
    clusters = _clusters_raw if isinstance(_clusters_raw, list) else []
    _strategy_raw = result.get("strategy") or {}
    strategy = _strategy_raw if isinstance(_strategy_raw, dict) else {}
    if not isinstance(keywords, list):
        keywords = []

    if not keywords and not profile and not clusters and not strategy:
        return {
            "valid": False,
            "score": 0.0,
            "failures": ["Output is completely empty — no keywords, profile, clusters, or strategy"],
            "warnings": [],
            "schema": {},
            "consistency": {},
        }

    # ── 2. Schema validation ──────────────────────────────────────────────────
    if keywords:
        kw_schema = validate_keyword_list(keywords)
        schema_results["keywords"] = kw_schema
        checks_run += 1
        if kw_schema["valid"]:
            checks_passed += 1
        else:
            failures += [f"[schema/keywords] {i}" for i in kw_schema["issues"][:5]]

    if profile:
        prof_issues = validate_business_profile(profile)
        schema_results["profile"] = {"valid": not prof_issues, "issues": prof_issues}
        checks_run += 1
        if not prof_issues:
            checks_passed += 1
        else:
            failures += [f"[schema/profile] {i}" for i in prof_issues]

    if clusters:
        cl_issues = validate_cluster_list(clusters)
        schema_results["clusters"] = {"valid": not cl_issues, "issues": cl_issues}
        checks_run += 1
        if not cl_issues:
            checks_passed += 1
        else:
            warnings += [f"[schema/clusters] {i}" for i in cl_issues]

    if strategy:
        st_issues = validate_strategy(strategy)
        schema_results["strategy"] = {"valid": not st_issues, "issues": st_issues}
        checks_run += 1
        if not st_issues:
            checks_passed += 1
        else:
            warnings += [f"[schema/strategy] {i}" for i in st_issues]

    # ── 3. Consistency checks ─────────────────────────────────────────────────
    if profile or keywords or strategy:
        consistency_result = run_all_consistency_checks(
            profile=profile,
            keywords=keywords,
            strategy=strategy,
            source_text=source_text,
        )
        checks_run += 1
        if consistency_result["valid"]:
            checks_passed += 1
        else:
            failures += [f"[consistency] {i}" for i in consistency_result.get("positioning_conflicts", [])]
            failures += [f"[consistency] {i}" for i in consistency_result.get("pillar_negative_scope_conflicts", [])]
            warnings += [f"[consistency] {i}" for i in consistency_result.get("intent_score_mismatches", [])]
            warnings += [f"[consistency] {i}" for i in consistency_result.get("hallucination_candidates", [])]

    # ── 4. Keyword health checks ──────────────────────────────────────────────
    if keywords:
        checks_run += 1
        informational_ratio = sum(
            1 for k in keywords if k.get("intent") == "informational"
        ) / max(len(keywords), 1)
        if informational_ratio > 0.5:
            warnings.append(
                f"[health] {informational_ratio:.0%} of keywords are informational — "
                "expected majority to be commercial/transactional for an SEO keyword set"
            )
            checks_passed += 0.5  # partial credit
        else:
            checks_passed += 1

        # Check for suspiciously short keyword list
        if len(keywords) < 10:
            warnings.append(f"[health] Only {len(keywords)} keywords — very sparse output")

    # ── 5. Score ──────────────────────────────────────────────────────────────
    score = round(checks_passed / max(checks_run, 1), 2)
    valid = len(failures) == 0

    return {
        "valid": valid,
        "score": score,
        "checks_run": checks_run,
        "checks_passed": checks_passed,
        "failures": failures,
        "warnings": warnings,
        "schema": schema_results,
        "consistency": consistency_result,
    }


def measure_similarity(out1: dict, out2: dict) -> float:
    """
    Measure similarity between two pipeline outputs (0.0–1.0).
    Used for determinism/stability testing.

    Compares:
    - keyword set overlap (Jaccard)
    - pillar set overlap
    - cluster name overlap
    """
    scores: list[float] = []

    # Keyword Jaccard
    kw1 = {k.get("keyword", "").lower() for k in (out1.get("keywords") or [])}
    kw2 = {k.get("keyword", "").lower() for k in (out2.get("keywords") or [])}
    if kw1 or kw2:
        jaccard = len(kw1 & kw2) / max(len(kw1 | kw2), 1)
        scores.append(jaccard)

    # Pillar overlap
    p1 = set((out1.get("profile") or {}).get("pillars", []))
    p2 = set((out2.get("profile") or {}).get("pillars", []))
    if p1 or p2:
        scores.append(len(p1 & p2) / max(len(p1 | p2), 1))

    # Cluster name overlap
    c1 = {c.get("cluster_name", "").lower() for c in (out1.get("clusters") or [])}
    c2 = {c.get("cluster_name", "").lower() for c in (out2.get("clusters") or [])}
    if c1 or c2:
        scores.append(len(c1 & c2) / max(len(c1 | c2), 1))

    return round(sum(scores) / max(len(scores), 1), 3)

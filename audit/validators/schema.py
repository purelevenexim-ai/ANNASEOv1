"""
audit/validators/schema.py
==========================
JSON schema validation for every key kw2 output type.

Usage:
    from audit.validators.schema import validate_keyword_row, validate_business_profile
    issues = validate_keyword_row({"keyword": "buy basil", "intent": "purchase", ...})
"""
from __future__ import annotations
from typing import Any


# ── Expected field specs per output type ─────────────────────────────────────

_KW_REQUIRED = {"keyword", "intent", "ai_relevance", "buyer_readiness"}
_KW_INTENT_VALUES = {
    "purchase", "transactional", "commercial", "comparison",
    "local", "informational", "navigational",
}
_PROFILE_REQUIRED = {"universe", "pillars", "modifiers", "audience", "business_type"}
_CLUSTER_REQUIRED = {"cluster_name", "keywords"}
_STRATEGY_REQUIRED = {"priority_pillars", "weekly_plan", "quick_wins"}


def validate_keyword_row(row: dict[str, Any]) -> list[str]:
    """Validate a single keyword dict. Returns list of issue strings (empty = valid)."""
    issues: list[str] = []

    for f in _KW_REQUIRED:
        if f not in row:
            issues.append(f"Missing required field: '{f}'")

    kw = row.get("keyword", "")
    if not isinstance(kw, str) or not kw.strip():
        issues.append("'keyword' must be a non-empty string")
    elif len(kw) > 200:
        issues.append(f"'keyword' too long ({len(kw)} chars) — likely garbage")

    intent = row.get("intent", "")
    if intent not in _KW_INTENT_VALUES:
        issues.append(f"Invalid intent '{intent}' — must be one of {_KW_INTENT_VALUES}")

    rel = row.get("ai_relevance")
    if rel is not None and not (0.0 <= float(rel) <= 1.0):
        issues.append(f"'ai_relevance' out of [0,1]: {rel}")

    br = row.get("buyer_readiness")
    if br is not None and not (0.0 <= float(br) <= 1.0):
        issues.append(f"'buyer_readiness' out of [0,1]: {br}")

    return issues


def validate_keyword_list(keywords: list[dict]) -> dict[str, Any]:
    """Validate a full keyword list. Returns summary dict."""
    if not isinstance(keywords, list):
        return {"valid": False, "issues": ["keywords is not a list"], "invalid_count": 0}

    all_issues: list[str] = []
    invalid_count = 0

    for i, row in enumerate(keywords):
        row_issues = validate_keyword_row(row)
        if row_issues:
            invalid_count += 1
            for iss in row_issues:
                all_issues.append(f"[kw#{i}] {iss}")

    return {
        "valid": invalid_count == 0,
        "total": len(keywords),
        "invalid_count": invalid_count,
        "issues": all_issues[:50],  # cap to avoid noise
    }


def validate_business_profile(profile: dict[str, Any]) -> list[str]:
    """Validate a business profile dict."""
    issues: list[str] = []

    if not isinstance(profile, dict):
        return [f"profile must be a dict, got {type(profile).__name__}"]

    for f in _PROFILE_REQUIRED:
        if f not in profile:
            issues.append(f"Missing required field: '{f}'")

    pillars = profile.get("pillars", [])
    if not isinstance(pillars, list) or len(pillars) == 0:
        issues.append("'pillars' must be a non-empty list")
    elif len(pillars) > 20:
        issues.append(f"'pillars' has {len(pillars)} entries — suspiciously large (max 20)")

    neg_scope = profile.get("negative_scope", [])
    must_exclude = {"recipe", "benefits", "how to", "what is"}
    missing_neg = must_exclude - set(neg_scope)
    if missing_neg:
        issues.append(f"'negative_scope' is missing mandatory exclusions: {missing_neg}")

    return issues


def validate_cluster_list(clusters: list[dict]) -> list[str]:
    """Validate cluster list structure."""
    issues: list[str] = []
    if not isinstance(clusters, list):
        issues.append("clusters is not a list")
        return issues
    for i, c in enumerate(clusters):
        for f in _CLUSTER_REQUIRED:
            if f not in c:
                issues.append(f"[cluster#{i}] Missing '{f}'")
        kws = c.get("keywords", [])
        if len(kws) < 2:
            issues.append(f"[cluster#{i}] '{c.get('cluster_name','?')}' has only {len(kws)} keyword(s)")
    return issues


def validate_strategy(strategy: dict) -> list[str]:
    """Validate strategy output."""
    issues: list[str] = []
    for f in _STRATEGY_REQUIRED:
        if f not in strategy:
            issues.append(f"Missing required strategy field: '{f}'")
    weekly = strategy.get("weekly_plan", [])
    if not isinstance(weekly, list) or len(weekly) == 0:
        issues.append("'weekly_plan' is empty or missing")
    return issues

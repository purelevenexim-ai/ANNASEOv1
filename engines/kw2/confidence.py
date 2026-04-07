"""
kw2 Phase 1 helper — compute confidence score for a business profile.
"""


def compute_confidence(profile: dict) -> float:
    """
    5-factor weighted confidence score for a business profile.

    Returns float 0.0 - 1.0 (rounded to 2 decimals).
    """
    score = 0.0

    pillars = profile.get("pillars") or []
    if isinstance(pillars, str):
        pillars = []
    if len(pillars) >= 3:
        score += 0.25

    catalog = profile.get("product_catalog") or []
    if isinstance(catalog, str):
        catalog = []
    if len(catalog) >= 5:
        score += 0.25

    signals = profile.get("intent_signals") or []
    if isinstance(signals, str):
        signals = []
    if signals:
        score += 0.20

    neg = profile.get("negative_scope") or []
    if isinstance(neg, str):
        neg = []
    if neg:
        score += 0.15

    universe = profile.get("universe") or ""
    if universe and pillars:
        score += 0.15

    return round(min(score, 1.0), 2)

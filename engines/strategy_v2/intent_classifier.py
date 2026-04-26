"""
Strategy V2 — Rule-based intent classifier.
No AI call — fast, deterministic.
"""
import re


_COMPARISON_PATTERNS = [
    r"\bvs\.?\b", r"\bversus\b", r"\bcompare\b", r"\bcomparison\b",
    r"\bdifference between\b", r"\bwhich is better\b",
]
_TRANSACTIONAL_PATTERNS = [
    r"\bbuy\b", r"\border\b", r"\bdiscount\b", r"\bcoupon\b",
    r"\bpromo\b", r"\bdeal\b", r"\bshop\b", r"\bpurchase\b",
]
_COMMERCIAL_PATTERNS = [
    r"\bprice\b", r"\bcost\b", r"\bcheap\b", r"\baffordable\b",
    r"\bbest\b", r"\btop\b", r"\breview\b", r"\brating\b",
    r"\brecommend\b", r"\bworth it\b",
]


def classify_intent(keyword: str) -> str:
    """
    Classify keyword search intent.

    Returns: "comparison" | "transactional" | "commercial" | "informational"
    """
    kw = keyword.lower().strip()

    for pat in _COMPARISON_PATTERNS:
        if re.search(pat, kw):
            return "comparison"

    for pat in _TRANSACTIONAL_PATTERNS:
        if re.search(pat, kw):
            return "transactional"

    for pat in _COMMERCIAL_PATTERNS:
        if re.search(pat, kw):
            return "commercial"

    return "informational"

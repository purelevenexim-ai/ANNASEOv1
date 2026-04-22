"""
GSC Engine — Keyword Processor
Handles: pillar matching, synonym expansion, intent classification, scoring.
Runs 100% locally — no external API calls.

Upgraded in Phase 1 to accept ProjectConfig — the AI-generated project
intelligence object that drives smarter filtering and classification.
"""
import re
import logging
from collections import defaultdict
from typing import Union

from .gsc_ai_config import ProjectConfig

log = logging.getLogger(__name__)

# ─── Synonyms ─────────────────────────────────────────────────────────────────

SYNONYMS: dict[str, list[str]] = {
    "cardamom":  ["elaichi", "elachi", "cardamon", "elacha"],
    "turmeric":  ["haldi", "curcumin", "haridra"],
    "pepper":    ["kali mirch", "black pepper", "peppercorn"],
    "clove":     ["lavang", "laung", "syzygium"],
    "cinnamon":  ["dalchini", "darchini"],
    "ginger":    ["adrak", "adraka", "zingiber"],
    "saffron":   ["kesar", "zafran", "crocus"],
    "fennel":    ["saunf", "aniseed", "foeniculum"],
    "cumin":     ["jeera", "jira", "cuminum"],
    "coriander": ["dhania", "dhaniya", "cilantro"],
    "fenugreek": ["methi", "trigonella"],
    "mustard":   ["sarson", "rai"],
    "nutmeg":    ["jaiphal", "myristica"],
    "mace":      ["javitri", "blade mace"],
}

# ─── Intent signals ───────────────────────────────────────────────────────────

_PURCHASE = {"buy", "price", "order", "wholesale", "bulk", "supplier", "purchase",
             "shop", "cost", "rate", "per kg", "price list", "minimum order"}
_WHOLESALE = {"wholesale", "bulk", "b2b", "export", "distributor", "trader", "importer",
              "exporter", "freight", "container", "consignment", "per tonne", "per quintal"}
_COMMERCIAL = {"best", "review", "compare", "vs", "alternatives", "recommended",
               "top", "quality", "grade", "organic", "certified"}
_INFO = {"benefits", "uses", "how", "what", "guide", "recipe", "nutrition", "side effect",
         "health", "ayurvedic", "history", "origin", "difference", "types", "varieties"}
_NAV = {"login", "account", "contact", "address", "website", "official", "near me", "location"}


def classify_intent(keyword: str, config: ProjectConfig | None = None) -> str:
    kw = keyword.lower()
    words = set(re.findall(r"\b\w+\b", kw))

    # Config-driven signals get priority (user-defined business terms)
    if config and config.purchase_set:
        for sig in config.purchase_set:
            if sig in kw:
                return "purchase"

    # Check wholesale first (more specific than purchase)
    if _WHOLESALE & words or any(p in kw for p in _WHOLESALE):
        return "wholesale"
    if _PURCHASE & words or any(p in kw for p in _PURCHASE):
        return "purchase"
    if _NAV & words:
        return "navigational"
    if _COMMERCIAL & words:
        return "commercial"
    if _INFO & words:
        return "informational"
    return "informational"


# ─── Core term extraction (strip product-specific noise) ─────────────────────

_GEO = {"kerala", "assam", "gujarat", "rajasthan", "india", "bangalore", "delhi", "mumbai"}
_QUAL = {"organic", "pure", "premium", "natural", "raw", "dried", "whole", "ground", "powder"}
_SIZE = re.compile(r"\b(\d+\s*(?:gm|g|kg|ml|l|gram|kilogram|liter))\b", re.I)
_PROMO = {"free delivery", "free shipping", "best price", "lowest price", "discount", "offer", "sale"}


def _extract_core_term(pillar: str) -> str:
    """Strip weight/geo/promo/quality noise to get the product core."""
    s = pillar.lower()
    s = _SIZE.sub("", s)
    for w in _GEO | _QUAL:
        s = re.sub(rf"\b{re.escape(w)}\b", "", s)
    for p in _PROMO:
        s = s.replace(p, "")
    return " ".join(s.split()).strip()


# ─── Pillar Matching ──────────────────────────────────────────────────────────

def _get_all_terms(pillar: str, config: ProjectConfig | None = None) -> list[str]:
    """Return pillar + core term + built-in synonyms + config synonyms."""
    terms = [pillar.lower(), _extract_core_term(pillar)]
    # Built-in synonym table
    for base, synonyms in SYNONYMS.items():
        if base in pillar.lower() or base in terms[1]:
            terms.extend(synonyms)
    # Config (AI-generated) synonym table
    if config:
        config_syns = config.get_synonyms_for(pillar)
        terms.extend(config_syns)
    # deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def detect_pillar(keyword: str, pillars: list[str],
                  config: ProjectConfig | None = None) -> str | None:
    """
    Assign a keyword to a pillar using 3-tier matching:
    1. Exact substring (full pillar name in keyword)
    2. Core term substring (stripped pillar in keyword)
    3. Word overlap (>40% shared words)
    Uses config.synonyms on top of built-in SYNONYMS when available.
    Returns pillar name or None.
    """
    kw_lower = keyword.lower()
    kw_words = set(re.findall(r"\b\w+\b", kw_lower))

    best_pillar = None
    best_overlap = 0.0

    for pillar in pillars:
        terms = _get_all_terms(pillar, config)

        # Tier 1 & 2: substring match
        for term in terms:
            if term and term in kw_lower:
                return pillar

        # Tier 3: word overlap
        for term in terms:
            if not term:
                continue
            term_words = set(re.findall(r"\b\w+\b", term))
            if not term_words:
                continue
            overlap = len(kw_words & term_words) / len(term_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_pillar = pillar

    if best_overlap >= 0.4:
        return best_pillar
    return None


# ─── Scoring ──────────────────────────────────────────────────────────────────

INTENT_BOOST = {
    "purchase": 5,
    "wholesale": 4,
    "commercial": 2,
    "informational": 1,
    "navigational": 0,
}


def score_keyword(kw: dict) -> dict:
    """
    Compute composite score for a keyword.
    score = source_score + impression_score + click_score + intent_boost + opportunity_score
    """
    impressions = kw.get("impressions", 0)
    clicks = kw.get("clicks", 0)
    position = kw.get("position", 0.0)
    intent = kw.get("intent", "informational")

    source_score = 5  # GSC = +5 (user input would be +10)
    impression_score = min(impressions * 0.005, 30)   # capped at 30
    click_score = min(clicks * 0.05, 20)               # capped at 20
    intent_boost = INTENT_BOOST.get(intent, 0)

    # Opportunity: high impressions but poor rank (11-50)
    opportunity_score = 0
    if position > 10 and impressions > 200:
        opportunity_score = min(impressions * 0.002, 15)
    elif position > 20 and impressions > 500:
        opportunity_score = min(impressions * 0.003, 20)

    total = source_score + impression_score + click_score + intent_boost + opportunity_score

    return {
        **kw,
        "score": round(total, 2),
        "source_score": source_score,
        "impression_score": round(impression_score, 2),
        "click_score": round(click_score, 2),
        "intent_boost": intent_boost,
        "opportunity_score": round(opportunity_score, 2),
    }


# ─── Main Processing ─────────────────────────────────────────────────────────

def detect_angle(keyword: str, config: ProjectConfig | None = None) -> str:
    """
    Detect the supporting content angle for a keyword using config.supporting_angles.
    Returns the matched angle name or 'general'.
    """
    if not config or not config.supporting_set:
        # Fall back to built-in INFO signals
        kw = keyword.lower()
        for sig in _INFO:
            if sig in kw:
                return sig
        return "general"
    kw = keyword.lower()
    for angle in config.supporting_angles:
        if angle.lower() in kw:
            return angle
    return "general"


def process_keywords(
    raw_keywords: list[dict],
    config: Union[ProjectConfig, list[str]],
) -> list[dict]:
    """
    Full processing pipeline:
    1. Match each keyword to a pillar
    2. Classify intent (config-driven signals first)
    3. Detect supporting angle
    4. Score
    5. Mark top 100 per pillar

    config: ProjectConfig (preferred) or list[str] of pillar names (backward compat).
    Returns: list of scored+classified keywords, sorted by score desc.
    """
    # Backward compatibility: accept bare pillar list
    if isinstance(config, list):
        config = ProjectConfig.from_pillars(config)

    pillars = config.pillars
    log.info(f"[GSC Processor] Processing {len(raw_keywords)} keywords across {len(pillars)} pillars")

    # Step 1+2+3+4: Match, classify, detect angle, score
    processed = []
    unmatched = 0
    for kw in raw_keywords:
        keyword = kw.get("keyword", "").strip()
        if not keyword:
            continue

        pillar = detect_pillar(keyword, pillars, config)
        if not pillar:
            unmatched += 1
            continue

        intent = classify_intent(keyword, config)
        angle  = detect_angle(keyword, config)
        scored = score_keyword({
            "keyword":     keyword,
            "pillar":      pillar,
            "intent":      intent,
            "angle":       angle,
            "clicks":      kw.get("clicks", 0),
            "impressions": kw.get("impressions", 0),
            "ctr":         kw.get("ctr", 0),
            "position":    kw.get("position", 0),
        })
        processed.append(scored)

    log.info(f"[GSC Processor] Matched: {len(processed)}, Unmatched: {unmatched}")

    # Step 4: Mark top 100 per pillar
    per_pillar: dict[str, list[dict]] = defaultdict(list)
    for kw in processed:
        per_pillar[kw["pillar"]].append(kw)

    for pil, kws in per_pillar.items():
        sorted_kws = sorted(kws, key=lambda x: x["score"], reverse=True)
        for i, kw in enumerate(sorted_kws):
            kw["top100"] = i < 100

    # Flatten and sort globally by score
    result = sorted(processed, key=lambda x: x["score"], reverse=True)
    return result


def build_tree(processed: list[dict]) -> dict:
    """
    Build tree structure from processed keywords:
    Universe → Pillar → Intent Group → Keyword
    """
    pillar_map: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for kw in processed:
        pillar_map[kw["pillar"]][kw["intent"]].append(kw)

    pillars = []
    for pillar_name, intent_groups in pillar_map.items():
        groups = []
        for intent, kws in intent_groups.items():
            kws_sorted = sorted(kws, key=lambda x: x["score"], reverse=True)
            groups.append({
                "name": intent.title(),
                "type": "intent_group",
                "intent": intent,
                "count": len(kws_sorted),
                "keywords": kws_sorted,
            })
        groups.sort(key=lambda g: INTENT_BOOST.get(g["intent"], 0), reverse=True)

        total_kws = sum(g["count"] for g in groups)
        top100_count = sum(1 for kw in processed if kw["pillar"] == pillar_name and kw.get("top100"))
        pillars.append({
            "name": pillar_name,
            "type": "pillar",
            "total": total_kws,
            "top100": top100_count,
            "groups": groups,
        })

    pillars.sort(key=lambda p: p["total"], reverse=True)
    return {
        "universe": {
            "name": "GSC Keyword Universe",
            "type": "universe",
            "total": len(processed),
            "pillars": pillars,
        }
    }

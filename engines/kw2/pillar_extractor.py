"""
kw2 — PillarExtractor

Converts raw product catalog names into clean, search-quality pillar keywords.

The core principle: pillars are SEARCH ENTITIES, not inventory labels.

    "Kerala Black Pepper - 200gm"           → "black pepper"
    "Aromatic True Cinnamon (Ceylon)"        → "cinnamon ceylon"
    "Premium Cassia Cinnamon 100g"           → "cassia cinnamon"
    "Kerala Cardamom 8mm - Free Delivery"    → "cardamom"
    "Organic Turmeric Powder - 500gm"        → "turmeric powder"
    "Spice Gift Box"                         → REJECTED (no product word)
    "Premium Organic"                        → REJECTED (adjectives only)

Usage:
    from engines.kw2.pillar_extractor import PillarExtractor
    pillars = PillarExtractor().extract(product_catalog)
"""
import re
import logging
from collections import Counter

log = logging.getLogger("kw2.pillar_extractor")

# ── Noise word sets (sourced from intelligent_crawl_engine._GEO_WORDS + _QUALITY_WORDS) ─

GEO_WORDS = {
    "kerala", "india", "indian", "srilanka", "sri", "lanka", "karnataka",
    "tamilnadu", "assam", "darjeeling", "nilgiri", "wayanad", "idukki",
    "coorg", "ooty", "mysore", "malabar", "adimali", "south", "north",
    "chinese", "vietnam", "vietnamese", "indonesian", "indonesia",
}

QUALITY_WORDS = {
    "organic", "pure", "natural", "fresh", "best", "top", "finest",
    "authentic", "raw", "whole", "ground", "powder", "paste", "extract",
    "oil", "seeds", "leaves", "bark", "dried", "handpicked", "selected",
    "premium", "wild", "cold", "pressed", "certified", "aromatic",
    "fruit", "bulb", "root", "flower", "pod", "herb", "spice", "grade",
    "bold", "extra", "medium", "small", "large", "true", "quality",
}

PROMO_WORDS = {
    "free", "delivery", "shipping", "offer", "sale", "pack", "combo",
    "set", "kit", "deal", "discount", "new", "special", "limited",
    "edition", "sample", "trial", "tester", "testers", "clearance",
    "gift", "box", "selection", "arrival", "seller",
}

# Matches size tokens like "200gm", "8mm", "1kg", "500ml", "100g", "2pcs"
_SIZE_PAT = re.compile(
    r'^\d+\s*(mm|cm|g|gm|grams?|kg|ml|l|oz|lbs?|pcs?|pieces?|units?)$', re.I
)

# All noise (union)
_ALL_NOISE = GEO_WORDS | QUALITY_WORDS | PROMO_WORDS | {
    "in", "of", "the", "and", "for", "with", "from", "per", "a", "an",
    "gm", "gms", "g", "kg", "ml", "mm", "cm", "oz", "lbs",
}

# Generic terms that are never valid stand-alone pillars.
# A "pillar" must be a specific product, not a category abstraction.
_INVALID_SINGLE_PILLARS = frozenset({
    "spice", "spices", "herb", "herbs", "product", "products", "item", "items",
    "goods", "ingredient", "ingredients", "supplement", "supplements",
    "food", "foods", "drink", "tea", "oil", "oils", "extract", "extracts",
    "blend", "blends", "mix", "mixes", "kit", "kits", "pack", "packs",
    "thing", "stuff", "material", "materials", "commodity", "commodities",
})


class PillarExtractor:
    """
    Extract clean search entities (pillars) from a list of raw product names.

    Products are typically messy inventory labels with geo, size, quality noise.
    This class strips that noise and returns clean 1–3 word search terms.
    """

    def extract(self, products: list[str]) -> list[str]:
        """
        Convert a raw product catalog into clean, ranked pillar keywords.

        - Cleans each product name (strips geo/size/quality noise)
        - Applies quality gate: rejects pillars that are all noise or purely generic
        - Enforces 1–3 word limit (over-specified names aren't good pillars)
        - Ranks by frequency (same entity appearing in many variants = high signal)
        - Returns deduplicated list, sorted by frequency, max 12

        Args:
            products: list of raw product names from site crawl or manual input

        Returns:
            list of clean pillar strings (lowercase, 1–3 words, deduped)
        """
        if not products:
            return []

        # Clean each product → core term
        cleaned = []
        for p in products:
            core = self._clean(p)
            if core and self._is_valid_pillar(core):
                cleaned.append(core)
            elif core:
                log.debug("[PillarExtractor] Quality-rejected: '%s' → '%s'", p, core)

        if not cleaned:
            log.warning("[PillarExtractor] All products rejected by quality gate — returning empty")
            return []

        # Rank by frequency: "black pepper" from 5 variants → score 5
        ranked = self._rank_by_frequency(cleaned)

        # Semantic dedup: remove pillars that are fully subsumed by a shorter pillar.
        # "green cardamom" is subsumed by "cardamom" → remove it.
        deduped = self._subsumption_dedup(ranked)

        log.info(
            f"[PillarExtractor] {len(products)} products → {len(deduped)} pillars "
            f"(before dedup: {len(ranked)}): {deduped[:5]}..."
        )
        return deduped[:12]

    def _is_valid_pillar(self, term: str) -> bool:
        """
        Quality gate: return True if `term` is a valid product pillar.

        A valid pillar must:
        1. Have at least one word that is NOT a noise/quality/geo adjective.
           e.g. "premium organic" → all noise → invalid
           e.g. "cardamom" → has product word → valid
        2. Not be a single generic abstraction (spice, herb, product, goods…).
           e.g. "spice" alone → invalid (too generic to target)
           e.g. "black pepper" → valid specific product
        3. Be at least 3 characters after cleaning.
        """
        words = term.lower().split()
        if not words or len(term) < 3:
            return False

        # Check 1: reject if ALL words are noise (only adjectives / geo / promo)
        non_noise = [w for w in words if w not in _ALL_NOISE]
        if not non_noise:
            log.debug("[PillarExtractor] Rejected '%s': all words are noise", term)
            return False

        # Check 2: reject single-word generic abstractions
        if len(words) == 1 and words[0] in _INVALID_SINGLE_PILLARS:
            log.debug("[PillarExtractor] Rejected '%s': generic single-word pillar", term)
            return False

        return True

    def _clean(self, text: str) -> str:
        """
        Strip noise from a product name and return the core search entity.

        Strips: sizes (200gm, 8mm), promo phrases (free delivery, offer),
        geo words (kerala, india, malabar), quality adjectives (organic, premium, aromatic),
        separators and brackets.

        Returns lowercase string. Falls back to original lowercased if result < 3 chars.
        """
        s = text

        # Remove size/weight tokens in context: "200gm", "100g", "1kg", "8mm"
        s = re.sub(r'\b\d+\s*(gm|g|kg|ml|l|mm|cm|oz|lbs?|pcs?|pieces?|units?|grams?)\b', '', s, flags=re.IGNORECASE)

        # Remove standalone numeric tokens
        s = re.sub(r'\b\d+\b', '', s)

        # Remove promo phrases
        s = re.sub(r'\b(free\s*delivery|free\s*ship\w*|offer|discount|sale\s*price)\b', '', s, flags=re.IGNORECASE)

        # Replace separators and brackets with spaces
        s = re.sub(r'[-–—&,\(\)\[\]/|]+', ' ', s)

        # Tokenize and filter noise
        tokens = s.split()
        kept = []
        for tok in tokens:
            tok_lower = tok.lower()
            # Skip size tokens
            if _SIZE_PAT.match(tok):
                continue
            # Skip all noise words
            if tok_lower in _ALL_NOISE:
                continue
            # Skip single-char tokens
            if len(tok) <= 1:
                continue
            kept.append(tok_lower)

        if not kept:
            # Fallback: return original lowercased, collapsed
            fallback = re.sub(r'[^a-z0-9\s]', ' ', text.lower())
            fallback = re.sub(r'\s+', ' ', fallback).strip()
            return fallback if len(fallback) > 2 else ""

        result = " ".join(kept)
        result = re.sub(r'\s+', ' ', result).strip()

        # Enforce 1–3 word limit: take first 3 meaningful words
        words = result.split()
        if len(words) > 3:
            result = " ".join(words[:3])

        return result if len(result) > 2 else ""

    def _rank_by_frequency(self, cleaned: list[str]) -> list[str]:
        """
        Rank cleaned pillar terms by frequency across the product list.

        Terms appearing in more products are more likely to be core pillars.
        E.g. if "black pepper" appears from 5 product variants, it ranks above
        "cardamom" which appeared from 2.

        Returns deduplicated list, most frequent first.
        """
        counts = Counter(cleaned)
        return [term for term, _count in counts.most_common()]

    def _subsumption_dedup(self, pillars: list[str]) -> list[str]:
        """
        Remove pillars whose every word is already covered by a shorter (more general) pillar.

        Examples:
            ["cardamom", "green cardamom", "black cardamom"]
                → "green cardamom" and "black cardamom" are subsumed by "cardamom"
                → result: ["cardamom"]

            ["black pepper", "pepper", "black pepper powder"]
                → "black pepper powder" subsumed by "black pepper"
                → "black pepper" subsumed by "pepper" (all words of "pepper" ∈ "black pepper")
                → result: ["pepper", "black pepper"]  ← kept because "black pepper" is more specific

        The rule: pillar B is subsumed by pillar A if:
          - A ≠ B
          - every word in A also appears in B (A is a strict subset of B's words)
          - len(A.words) < len(B.words)   (A is shorter / more general)

        This preserves specific pillars like "black pepper" even when "pepper" exists,
        because "black pepper" adds signal. It only removes overly-specific variants
        that add no useful search differentiation over the base term.
        """
        if len(pillars) <= 1:
            return pillars

        keep = []
        pillar_wordsets = [(p, set(p.split())) for p in pillars]

        for i, (pillar_b, words_b) in enumerate(pillar_wordsets):
            subsumed = False
            for j, (pillar_a, words_a) in enumerate(pillar_wordsets):
                if i == j:
                    continue
                # B is subsumed by A if: A's words ⊆ B's words AND A is strictly shorter
                if words_a < words_b:   # strict subset (A has fewer unique words, all in B)
                    subsumed = True
                    log.debug(
                        "[PillarExtractor] Subsumption: '%s' subsumed by '%s'",
                        pillar_b, pillar_a,
                    )
                    break
            if not subsumed:
                keep.append(pillar_b)

        return keep

"""
kw2 normalizer — Canonical keyword normalization, variant tracking, semantic dedup.

The Normalization Engine provides:
1. canonical() — normalize keyword to fingerprint form
2. are_variants() — check if two keywords are variants of each other
3. merge_variants() — merge a batch of keywords, tracking variants
4. semantic_dedup() — TF-IDF cosine-based near-dedup within a keyword list
"""
import re
import logging
from collections import defaultdict

log = logging.getLogger("kw2.normalizer")

# ── Inflection rules (lightweight, no external deps) ────────────────────────

_PLURAL_RULES = [
    (re.compile(r"(s|x|z|ch|sh)es$", re.I), r"\1"),
    (re.compile(r"ies$", re.I), "y"),
    (re.compile(r"ves$", re.I), "f"),
    (re.compile(r"([^s])s$", re.I), r"\1"),
]

# Lightweight verb stemming (gerund/participle → base)
_STEM_RULES = [
    # buying → buy, selling → sell (doubling consonant: running→run, shipping→ship)
    (re.compile(r"^(.+)([^aeiou])\2ing$", re.I), r"\1\2"),
    # making → make, pricing → price (drop e + ing)
    (re.compile(r"^(.{2,})ting$", re.I), r"\1te"),
    (re.compile(r"^(.{2,})cing$", re.I), r"\1ce"),
    (re.compile(r"^(.{2,})sing$", re.I), r"\1se"),
    (re.compile(r"^(.{2,})ving$", re.I), r"\1ve"),
    (re.compile(r"^(.{2,})zing$", re.I), r"\1ze"),
    # buying → buy, playing → play
    (re.compile(r"^(.{2,})ying$", re.I), r"\1y"),
    # general -ing: ordering→order, comparing→compare
    (re.compile(r"^(.{3,})ing$", re.I), r"\1"),
]

_ARTICLES = frozenset({"a", "an", "the"})

_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "in", "to", "for", "and", "or", "is", "it",
    "by", "on", "at", "with", "from", "as", "are", "was", "be", "its",
})


def _singularize(word: str) -> str:
    """Best-effort singularize a single word."""
    w = word.lower()
    # Don't singularize short words or known exceptions
    if len(w) <= 3 or w.endswith("ss") or w in {"this", "bus", "plus", "gas", "is"}:
        return w
    for pattern, repl in _PLURAL_RULES:
        result, n = pattern.subn(repl, w)
        if n:
            return result
    return w


def _stem(word: str) -> str:
    """Best-effort stem: singularize + verb base form."""
    w = _singularize(word)
    if len(w) <= 3:
        return w
    # Try verb stemming on the (possibly already singularized) word
    for pattern, repl in _STEM_RULES:
        result, n = pattern.subn(repl, w)
        if n and len(result) >= 2:
            return result
    return w


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase alpha tokens."""
    return re.findall(r"[a-z]+", text.lower())


def canonical(keyword: str) -> str:
    """
    Normalize a keyword to a canonical fingerprint.

    Steps:
    1. Lowercase, strip non-alpha chars (keep spaces between words)
    2. Tokenize into words
    3. Remove articles (a, an, the)
    4. Singularize each word
    5. Sort alphabetically
    6. Join with single space

    Examples:
        canonical("Buy Coconut Oil")      → "buy coconut oil"
        canonical("buying coconut oils")   → "buy coconut oil"
        canonical("the best coconut oil")  → "best coconut oil"
        canonical("coconut oil buy")       → "buy coconut oil"
    """
    tokens = _tokenize(keyword)
    if not tokens:
        return ""
    # Remove articles
    tokens = [t for t in tokens if t not in _ARTICLES]
    if not tokens:
        return ""
    # Singularize + stem
    tokens = [_stem(t) for t in tokens]
    # Sort for order-invariant fingerprint
    tokens.sort()
    return " ".join(tokens)


def display_form(keyword: str) -> str:
    """Clean display form: lowercase, collapse whitespace, strip."""
    text = keyword.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def are_variants(kw1: str, kw2: str) -> bool:
    """Check if two keywords have the same canonical form."""
    return canonical(kw1) == canonical(kw2)


def detect_pillars(keyword: str, pillars: list[str],
                   threshold: float = 0.3) -> list[dict]:
    """
    Match a keyword against ALL pillars, returning list of {pillar, confidence}.

    Matching strategy (3-tier):
    1. Exact substring: pillar appears as substring → confidence 0.9
    2. Core-term match: extracted core term matches → confidence 0.7
    3. Word overlap: Jaccard-like overlap of content words → confidence = ratio

    Returns all matches with confidence >= threshold, sorted by confidence desc.
    """
    kw_lower = keyword.lower()
    kw_tokens = set(_tokenize(keyword)) - _STOP_WORDS
    results = []

    for pillar in pillars:
        p_lower = pillar.lower().strip()
        p_tokens = set(_tokenize(pillar)) - _STOP_WORDS

        # Tier 1: exact substring
        if p_lower in kw_lower or kw_lower in p_lower:
            results.append({"pillar": pillar, "confidence": 0.9})
            continue

        # Tier 2: core term (multi-word pillars — extract the product noun)
        core = _extract_core(p_lower)
        if core and len(core) > 2 and core in kw_lower:
            results.append({"pillar": pillar, "confidence": 0.7})
            continue

        # Tier 3: word overlap
        if p_tokens and kw_tokens:
            overlap = len(p_tokens & kw_tokens)
            denom = min(len(p_tokens), len(kw_tokens))
            if denom > 0:
                ratio = overlap / denom
                if ratio >= threshold:
                    results.append({"pillar": pillar, "confidence": round(ratio, 2)})

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results


def assign_role(keyword: str, pillars: list[str],
                pillar_matches: list[dict]) -> str:
    """
    Determine keyword role:
    - 'pillar' if keyword IS a pillar (canonical match)
    - 'bridge' if matches 2+ pillars with confidence >= 0.5
    - 'supporting' otherwise
    """
    kw_canon = canonical(keyword)
    for p in pillars:
        if canonical(p) == kw_canon:
            return "pillar"
    high_conf = [m for m in pillar_matches if m["confidence"] >= 0.5]
    if len(high_conf) >= 2:
        return "bridge"
    return "supporting"


def _extract_core(pillar: str) -> str:
    """Extract the core product noun from a pillar name, stripping noise."""
    noise = re.compile(
        r"\b(\d+\s*(g|gm|kg|ml|l|mm|cm|oz|lb)s?\b|"
        r"free delivery|discount|offer|premium|organic|natural|"
        r"kerala|indian|india|pure|best|quality)\b",
        re.I,
    )
    result = noise.sub("", pillar).strip()
    result = re.sub(r"\s+", " ", result).strip()
    return result if len(result) >= 3 else pillar


def merge_keyword_batch(keywords: list[dict]) -> list[dict]:
    """
    Merge a batch of keyword dicts by canonical form.

    Input dicts should have at least: keyword, source, pillar (or pillars), raw_score
    Returns merged list where each canonical form appears once with:
    - keyword: the highest-scoring display form
    - canonical: the canonical fingerprint
    - sources: accumulated list of all sources
    - variants: accumulated list of all display forms
    - pillars: union of all pillar assignments
    - raw_score: max score across variants
    """
    buckets: dict[str, dict] = {}

    for kw in keywords:
        text = kw.get("keyword", "").strip()
        if not text:
            continue
        canon = canonical(text)
        if not canon or len(canon) < 3:
            continue

        if canon not in buckets:
            buckets[canon] = {
                "keyword": display_form(text),
                "canonical": canon,
                "sources": [],
                "variants": [],
                "pillars": [],
                "raw_score": 0.0,
                "intent": kw.get("intent", ""),
            }

        entry = buckets[canon]

        # Track variant
        df = display_form(text)
        if df not in entry["variants"]:
            entry["variants"].append(df)

        # Accumulate source
        src = kw.get("source", "")
        if src and src not in entry["sources"]:
            entry["sources"].append(src)

        # Keep highest score + best display form
        score = float(kw.get("raw_score", 0.0))
        if score > entry["raw_score"]:
            entry["raw_score"] = score
            entry["keyword"] = df

        # Union of pillars
        kw_pillars = kw.get("pillars", [])
        if isinstance(kw_pillars, str):
            kw_pillars = [kw_pillars] if kw_pillars else []
        # Also check legacy single-pillar field
        single_pillar = kw.get("pillar", "")
        if single_pillar and single_pillar not in kw_pillars:
            kw_pillars.append(single_pillar)
        for p in kw_pillars:
            if p and p not in entry["pillars"]:
                entry["pillars"].append(p)

        # Keep non-empty intent
        if not entry["intent"] and kw.get("intent"):
            entry["intent"] = kw["intent"]

    return list(buckets.values())


def semantic_dedup(keywords: list[dict], threshold: float = 0.90,
                   score_key: str = "raw_score") -> tuple[list[dict], list[dict]]:
    """
    Remove semantic near-duplicates using TF-IDF cosine similarity.

    Keeps the higher-scored keyword of each pair above the threshold.
    Returns (kept, removed) tuple.
    """
    if len(keywords) <= 1:
        return keywords, []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        log.warning("sklearn not available — skipping semantic dedup")
        return keywords, []

    # Sort by score descending so we keep the better keyword
    sorted_kws = sorted(keywords,
                        key=lambda k: float(k.get(score_key, 0)),
                        reverse=True)

    texts = [kw.get("keyword", "") for kw in sorted_kws]
    if not any(texts):
        return keywords, []

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    try:
        tfidf = vectorizer.fit_transform(texts)
    except ValueError:
        return keywords, []

    sim_matrix = cosine_similarity(tfidf)

    removed_idx: set[int] = set()
    kept = []
    removed = []

    for i, kw in enumerate(sorted_kws):
        if i in removed_idx:
            removed.append(kw)
            continue
        kept.append(kw)
        # Mark all lower-scored near-duplicates
        for j in range(i + 1, len(sorted_kws)):
            if j not in removed_idx and sim_matrix[i, j] >= threshold:
                removed_idx.add(j)

    log.info("semantic_dedup: %d kept, %d removed (threshold=%.2f)",
             len(kept), len(removed), threshold)
    return kept, removed

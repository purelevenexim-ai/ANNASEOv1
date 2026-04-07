"""
kw2 Phase 1 helper — extract entities and topics from text using YAKE + n-gram fallback.
"""
import re
import logging
from collections import Counter

from engines.kw2.constants import GARBAGE_WORDS

log = logging.getLogger("kw2.entity")


def extract_entities(text: str) -> tuple[list[str], list[str]]:
    """
    Hybrid entity/topic extraction: YAKE (if available) + n-gram fallback.

    Returns:
        (entities: list[str], topics: list[str])
        First 25 = entities, next 25 = topics.
    """
    if not text or len(text.strip()) < 20:
        return [], []

    yake_results = _yake_extract(text)
    ngram_results = _ngram_extract(text)

    # Merge: YAKE first, then n-grams not already in YAKE set
    seen = set()
    combined = []
    for kw in yake_results + ngram_results:
        kl = kw.lower().strip()
        if kl not in seen and len(kl) >= 3 and _is_quality(kl):
            seen.add(kl)
            combined.append(kw.strip())
        if len(combined) >= 50:
            break

    entities = combined[:25]
    topics = combined[25:50]
    return entities, topics


def _yake_extract(text: str) -> list[str]:
    """Try YAKE extraction, return empty list on failure."""
    try:
        import yake
        extractor = yake.KeywordExtractor(lan="en", n=3, top=50)
        results = extractor.extract_keywords(text)
        # YAKE returns (keyword, score) — lower score = more important
        return [kw for kw, _score in sorted(results, key=lambda x: x[1])[:50]]
    except Exception as e:
        log.debug(f"YAKE extraction failed, using n-gram fallback: {e}")
        return []


def _ngram_extract(text: str) -> list[str]:
    """Extract n-grams (1-3 words) from text, ranked by frequency."""
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
    # Filter garbage
    words = [w for w in words if w not in GARBAGE_WORDS]

    ngrams = []
    # Unigrams
    ngrams.extend(words)
    # Bigrams
    for i in range(len(words) - 1):
        ngrams.append(f"{words[i]} {words[i+1]}")
    # Trigrams
    for i in range(len(words) - 2):
        ngrams.append(f"{words[i]} {words[i+1]} {words[i+2]}")

    counts = Counter(ngrams)
    return [phrase for phrase, _count in counts.most_common(50)]


def _is_quality(phrase: str) -> bool:
    """Check if a phrase is worth keeping."""
    words = phrase.split()
    if len(words) > 4:
        return False
    # Reject if first or last word is garbage
    if words[0] in GARBAGE_WORDS or words[-1] in GARBAGE_WORDS:
        return False
    # Reject if majority garbage
    garbage_ratio = sum(1 for w in words if w in GARBAGE_WORDS) / len(words)
    return garbage_ratio <= 0.4

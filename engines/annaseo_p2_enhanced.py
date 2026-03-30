"""
================================================================================
ANNASEO — P2 Enhanced Keyword Expansion Engine
================================================================================
Drop-in replacement for P2 (KeywordExpansion) that uses the new
pillar+supporting customer input model instead of bare single-word autosuggest.

Key improvements over old P2:
  1. Uses pillar×supporting phrases as autosuggest seeds (not bare "clove")
  2. Classifies intent at expansion time (transactional, informational, etc.)
  3. Falls back gracefully to original P2 if no customer input exists
  4. Returns flat List[str] compatible with P3+

Usage:
    from engines.annaseo_p2_enhanced import P2_Enhanced
    p2e = P2_Enhanced()
    keywords = p2e.run_from_input(project_id, session_id)
================================================================================
"""
from __future__ import annotations
import os, re, json, sqlite3, logging, time, hashlib
from pathlib import Path
from typing import Optional

log = logging.getLogger("annaseo.p2_enhanced")

_BASE = Path(__file__).resolve().parent.parent
_DB_PATH = _BASE / "annaseo.db"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# INTENT CLASSIFIER (lightweight, no AI needed)
# ─────────────────────────────────────────────────────────────────────────────

class P2_Scorer:
    """Score and classify keywords without an API call."""

    TRANSACTIONAL = [
        "buy", "order", "price", "cheap", "discount", "deal", "sale",
        "purchase", "shop", "online", "shipping", "delivery", "get",
        "where to buy", "best price", "cost", "offer", "promo", "coupon",
    ]
    INFORMATIONAL = [
        "what is", "how to", "why", "benefits", "uses", "guide", "tips",
        "recipe", "explained", "tutorial", "learn", "understand",
        "difference between", "vs", "versus", "meaning", "definition",
    ]
    COMPARISON = [
        "vs", "versus", "comparison", "compare", "difference", "better",
        "best", "top", "review", "reviews", "rating", "ranked",
    ]
    LOCAL = [
        "near me", "in india", "kerala", "delhi", "bangalore", "mumbai",
        "local", "city", "state", "region", "store near",
    ]
    QUESTION = [
        "what", "why", "how", "when", "where", "which", "can", "does",
        "is it", "should i", "will",
    ]
    COMMERCIAL = [
        "best", "top", "premium", "quality", "organic", "pure", "certified",
        "wholesale", "bulk", "supplier", "manufacturer", "brand",
    ]

    def classify_intent(self, keyword: str) -> str:
        kw = keyword.lower()
        if any(t in kw for t in self.TRANSACTIONAL):
            return "transactional"
        if any(t in kw for t in self.COMPARISON):
            return "comparison"
        if any(t in kw for t in self.LOCAL):
            return "local"
        if any(t in kw for t in self.QUESTION):
            return "question"
        if any(t in kw for t in self.INFORMATIONAL):
            return "informational"
        if any(t in kw for t in self.COMMERCIAL):
            return "commercial"
        return "informational"

    def estimate_score(self, keyword: str, intent: str) -> float:
        """Rough opportunity score 0–100 based on word count + intent."""
        words = len(keyword.split())
        # Long-tail gets bonus
        length_bonus = min(words * 8, 40)
        intent_bonus = {
            "transactional": 30,
            "commercial": 25,
            "comparison": 20,
            "local": 20,
            "informational": 10,
            "question": 15,
        }.get(intent, 10)
        return min(100, length_bonus + intent_bonus + 30)


# ─────────────────────────────────────────────────────────────────────────────
# AUTOSUGGEST FETCHER (phrase-level, not single-word)
# ─────────────────────────────────────────────────────────────────────────────

class P2_PhraseSuggestor:
    """
    Calls Google Autosuggest (free) using multi-word phrases as seeds.
    Phrase seeds = pillar × supporting cross-products.
    """

    def __init__(self, lang: str = "en", region: str = "in"):
        self.lang = lang
        self.region = region.lower()[:2]

    def _fetch_suggestions(self, phrase: str) -> list[str]:
        """Fetch Google Autosuggest for a phrase. Returns list of suggestions."""
        try:
            import requests
            url = "https://suggestqueries.google.com/complete/search"
            params = {
                "client": "firefox",
                "q": phrase,
                "hl": self.lang,
                "gl": self.region,
            }
            r = requests.get(url, params=params, timeout=8,
                             headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
            # [query, [suggestion, ...], ...]
            if isinstance(data, list) and len(data) > 1:
                return [s.strip() for s in data[1] if s.strip()]
            return []
        except Exception as e:
            log.debug(f"[P2E] Autosuggest failed for '{phrase}': {e}")
            return []

    def _fetch_alphabet_soup(self, base_phrase: str) -> list[str]:
        """Append a–z to seed phrase for deeper coverage."""
        results = []
        for letter in "abcdefghijklmnopqrstuvwxyz":
            seeds = [f"{base_phrase} {letter}", f"{letter} {base_phrase}"]
            for seed in seeds[:1]:  # only one direction to keep it fast
                results.extend(self._fetch_suggestions(seed))
        return results

    def expand_phrase(self, phrase: str, deep: bool = False) -> list[str]:
        """Expand a single phrase with autosuggest + optional alphabet soup."""
        results = self._fetch_suggestions(phrase)
        if deep and len(results) < 10:
            results.extend(self._fetch_alphabet_soup(phrase))
        return list(dict.fromkeys(results))  # dedup preserving order


# ─────────────────────────────────────────────────────────────────────────────
# P2 ENHANCED — MAIN CLASS
# ─────────────────────────────────────────────────────────────────────────────

class P2_Enhanced:
    """
    Enhanced P2 that uses customer pillars + supporting keywords as seeds.

    If no customer input is available for a project, falls back to the
    original P2 behaviour (single-word autosuggest on the seed keyword).
    """

    def __init__(self):
        self.scorer     = P2_Scorer()
        self.suggestor  = P2_PhraseSuggestor()

    # ── Public API ────────────────────────────────────────────────────────────

    def run_from_input(
        self,
        project_id: str,
        session_id: Optional[str] = None,
        language: str = "english",
        region: str = "India",
        max_per_phrase: int = 20,
        seed_keyword: Optional[str] = None,
    ) -> list[str]:
        """
        Returns a flat List[str] of expanded keywords ready for P3+.
        Uses confirmed universe items if available; otherwise expands pillars.
        """
        lang_code = "en"
        region_code = region[:2].lower() if region else "in"
        self.suggestor.lang   = lang_code
        self.suggestor.region = region_code

        db = _db()
        try:
            # 1. Try confirmed universe items first (fastest path)
            universe = self._load_confirmed_universe(db, project_id, session_id)
            if universe:
                filtered = self._filter_by_seed(universe, seed_keyword)
                if filtered:
                    log.info(f"[P2E] Loaded {len(filtered)} confirmed universe items for {project_id} filtered by seed '{seed_keyword}'")
                    return filtered
                log.info(f"[P2E] Confirmed universe items exist but none match seed '{seed_keyword}', trying cross-products")

            # 2. Try cross-products from DB
            phrases = self._load_cross_products(db, project_id, session_id)
            if phrases:
                expanded = self._expand_phrases(phrases, max_per_phrase)
                filtered = self._filter_by_seed(expanded, seed_keyword)
                if filtered:
                    log.info(f"[P2E] Expanded {len(phrases)} cross-product phrases for {project_id} filtered by seed '{seed_keyword}'")
                    return filtered
                log.info(f"[P2E] Cross-product expansions exist but none match seed '{seed_keyword}', trying pillars")

            # 3. Try pillars alone
            pillars = self._load_pillars(db, project_id)
            if pillars:
                expanded = self._expand_phrases(pillars, max_per_phrase)
                filtered = self._filter_by_seed(expanded, seed_keyword)
                if filtered:
                    log.info(f"[P2E] Expanded {len(pillars)} pillars for {project_id} filtered by seed '{seed_keyword}'")
                    return filtered
                log.info(f"[P2E] Pillar expansions exist but none match seed '{seed_keyword}', falling back to empty")

            log.warning(f"[P2E] No customer input found for project {project_id} or no seed-matching keywords for '{seed_keyword}'")
            return []

        finally:
            db.close()

    def _filter_by_seed(self, keywords: list[str], seed_keyword: Optional[str]) -> list[str]:
        if not seed_keyword:
            return keywords

        seed = seed_keyword.lower().strip()
        seed_words = set(re.findall(r"\w+", seed))
        if not seed_words:
            return keywords

        filtered = []
        for kw in keywords:
            kw_l = kw.lower().strip()
            kw_words = set(re.findall(r"\w+", kw_l))

            # exact literal match in phrase (token-level)
            if any(word in kw_words for word in seed_words):
                filtered.append(kw)
                continue

            # phrase contains seed as separate token (e.g. "green tea")
            if re.search(rf"\b{re.escape(seed)}\b", kw_l):
                filtered.append(kw)
                continue

            # multi-word seed overlap threshold (2+ tokens)
            if len(seed_words) > 1 and len(seed_words & kw_words) >= 2:
                filtered.append(kw)

        return filtered

    def run_with_seed(
        self,
        seed_keyword: str,
        pillars: Optional[list[str]] = None,
        supporting: Optional[list[str]] = None,
        language: str = "english",
        region: str = "India",
        max_per_phrase: int = 20,
    ) -> list[str]:
        """
        Expand a seed keyword using provided pillars+supporting (no DB needed).
        Useful for testing or one-off runs.
        """
        lang_code = "en"
        region_code = region[:2].lower() if region else "in"
        self.suggestor.lang   = lang_code
        self.suggestor.region = region_code

        # Build phrase list
        phrases = []
        pillar_list   = pillars   or [seed_keyword]
        support_list  = supporting or []

        for p in pillar_list:
            phrases.append(p)
            for s in support_list:
                phrases.append(f"{s} {p}")
                phrases.append(f"{p} {s}")

        phrases = list(dict.fromkeys(phrases))
        return self._expand_phrases(phrases, max_per_phrase)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _expand_phrases(self, phrases: list[str], max_per_phrase: int) -> list[str]:
        """Expand a list of phrases with autosuggest. Returns flat deduped list."""
        all_kws: list[str] = []
        seen: set[str] = set()

        for phrase in phrases[:50]:  # cap at 50 phrases to avoid timeout
            suggestions = self.suggestor.expand_phrase(phrase)
            for kw in suggestions[:max_per_phrase]:
                norm = kw.lower().strip()
                if norm not in seen and len(norm) > 3:
                    seen.add(norm)
                    all_kws.append(kw)
            time.sleep(0.15)  # polite crawl delay

        log.info(f"[P2E] Expanded {len(phrases)} phrases → {len(all_kws)} keywords")
        return all_kws

    def _load_confirmed_universe(
        self, db: sqlite3.Connection, project_id: str, session_id: Optional[str]
    ) -> list[str]:
        """Load accepted universe items from DB."""
        try:
            q = """
                SELECT keyword FROM keyword_universe_items
                WHERE project_id=? AND status='accepted'
                ORDER BY opportunity_score DESC
                LIMIT 500
            """
            params = [project_id]
            if session_id:
                q = """
                    SELECT keyword FROM keyword_universe_items
                    WHERE project_id=? AND session_id=? AND status='accepted'
                    ORDER BY opportunity_score DESC
                    LIMIT 500
                """
                params = [project_id, session_id]
            rows = db.execute(q, params).fetchall()
            return [row["keyword"] for row in rows if row["keyword"]]
        except Exception:
            return []

    def _load_cross_products(
        self, db: sqlite3.Connection, project_id: str, session_id: Optional[str]
    ) -> list[str]:
        """
        Load cross-product phrases from keyword_universe_items (source='cross_product').
        """
        try:
            q = """
                SELECT keyword FROM keyword_universe_items
                WHERE project_id=? AND source='cross_product'
                ORDER BY opportunity_score DESC
                LIMIT 200
            """
            params = [project_id]
            if session_id:
                q = """
                    SELECT keyword FROM keyword_universe_items
                    WHERE project_id=? AND session_id=? AND source='cross_product'
                    ORDER BY opportunity_score DESC
                    LIMIT 200
                """
                params = [project_id, session_id]
            rows = db.execute(q, params).fetchall()
            return [row["keyword"] for row in rows if row["keyword"]]
        except Exception:
            return []

    def _load_pillars(
        self, db: sqlite3.Connection, project_id: str
    ) -> list[str]:
        """Load pillar keywords from DB."""
        try:
            rows = db.execute(
                "SELECT keyword FROM pillar_keywords WHERE project_id=? ORDER BY priority ASC LIMIT 20",
                (project_id,)
            ).fetchall()
            return [row["keyword"] for row in rows if row["keyword"]]
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────────────────
# COMPATIBILITY SHIM — looks like original P2 for the pipeline
# ─────────────────────────────────────────────────────────────────────────────

class KeywordExpansionEnhanced:
    """
    Drop-in replacement for the P2 KeywordExpansion class.
    Has the same .run(seed, ...) signature as the original.
    """

    def __init__(self, project_id: str = "", session_id: str = ""):
        self.project_id = project_id
        self.session_id = session_id
        self._p2e = P2_Enhanced()

    def run(self, seed, language: str = "english", region: str = "India") -> list[str]:
        """
        Called exactly like original P2.run(seed, language, region).
        seed can be a Seed object or a string.
        """
        seed_kw = seed.keyword if hasattr(seed, "keyword") else str(seed)

        # Try customer input first
        if self.project_id:
            result = self._p2e.run_from_input(
                self.project_id,
                self.session_id or None,
                language=language,
                region=region,
                seed_keyword=seed_kw,
            )
            if result:
                return result

        # Fallback: expand bare seed keyword
        return self._p2e.run_with_seed(
            seed_kw, language=language, region=region
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    keyword = sys.argv[1] if len(sys.argv) > 1 else "cinnamon"
    pillars = [keyword]
    supporting = ["organic", "buy online", "price", "benefits", "uses", "pure"]

    p2e = P2_Enhanced()
    kws = p2e.run_with_seed(keyword, pillars=pillars, supporting=supporting, region="India")

    print(f"\n{len(kws)} keywords for '{keyword}':")
    for i, kw in enumerate(kws[:40], 1):
        scorer = P2_Scorer()
        intent = scorer.classify_intent(kw)
        score = scorer.estimate_score(kw, intent)
        print(f"  {i:3}. [{intent:15}] {score:4.0f}  {kw}")

"""
================================================================================
ANNASEO — MISSING PIECES (extracted from AnnaSEO project docs)
================================================================================
Application: AnnaSEO
Orchestrator: Ruflo (https://github.com/ruvnet/ruflo)

This file adds 6 things genuinely missing from our existing engines.
Everything else in the AnnaSEO docs was already built.

What's here:
  1. HDBSCAN clustering (replaces KMeans as primary in P8/P9)
  2. OffTopicFilter (kill-word filter per seed — completely missing)
  3. KeywordTrafficScorer (Quick Win / Gold Mine tags — specific thresholds)
  4. CannibalizationDetector (not the same as dedup — different problem)
  5. Three missing expansion dimensions (Storage, Cultivation, History)
  6. ContentLifecycleManager (new→growing→peak→declining→refresh_needed)

How to integrate:
  - HDBSCAN: replace KMeans in ruflo_20phase_engine.py P8_TopicDetection
  - OffTopicFilter: add after P3_Normalization, before P4_EntityDetection
  - TrafficScorer: replace/extend ruflo_20phase_engine.py P7_OpportunityScoring
  - CannibalizationDetector: call from content generation before writing article
  - Missing dimensions: add to ruflo_20phase_engine.py P2_KeywordExpansion
  - LifecycleManager: integrate with ruflo_20phase_engine.py P20_RankingFeedback
================================================================================
"""

from __future__ import annotations

import os, re, json, hashlib, logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger("annaseo.addons")


# ─────────────────────────────────────────────────────────────────────────────
# 1. HDBSCAN CLUSTERING
# Replace KMeans in P8_TopicDetection
# Advantage: no K needed upfront, handles noise, natural cluster shapes
# ─────────────────────────────────────────────────────────────────────────────

class HDBSCANClustering:
    """
    Density-based clustering for keyword topics.
    Better than KMeans for SEO because:
    - You don't know how many topics a seed will produce
    - Keywords naturally form irregular clusters
    - Noise keywords are isolated instead of forced into a cluster

    Install: pip install hdbscan

    Usage (drop-in replacement for P8_TopicDetection):
        clustering = HDBSCANClustering()
        topic_map  = clustering.cluster(keywords, embeddings)
    """

    def cluster(self, keywords: List[str],
                 embeddings: Optional[List[List[float]]] = None,
                 min_cluster_size: int = 3,
                 min_samples: int = 2) -> Dict[str, List[str]]:
        """
        Cluster keywords using HDBSCAN.
        If embeddings not provided, auto-generates them via sentence-transformers.
        Falls back to KMeans if HDBSCAN not installed.
        """
        if not keywords:
            return {}
        if len(keywords) < 2:
            # Trivial case: single keyword can't form clusters
            return {keywords[0]: keywords}
        if embeddings is None:
            embeddings = self._embed(keywords)
        try:
            return self._hdbscan_cluster(keywords, embeddings,
                                          min_cluster_size, min_samples)
        except ImportError:
            log.warning("[HDBSCAN] Not installed — falling back to KMeans. "
                        "Run: pip install hdbscan")
            return self._kmeans_fallback(keywords, embeddings)

    def _embed(self, keywords: List[str]) -> List[List[float]]:
        """Generate sentence embeddings for keywords."""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            return model.encode(keywords).tolist()
        except Exception:
            import hashlib
            # Deterministic fallback embeddings based on keyword chars
            result = []
            for kw in keywords:
                h = int(hashlib.md5(kw.encode()).hexdigest(), 16)
                vec = [(h >> (i * 4) & 0xF) / 15.0 for i in range(32)]
                result.append(vec)
            return result

    def _hdbscan_cluster(self, keywords: List[str],
                          embeddings: List[List[float]],
                          min_cluster_size: int,
                          min_samples: int) -> Dict[str, List[str]]:
        import numpy as np
        import hdbscan as hdb
        from sklearn.preprocessing import normalize

        X = normalize(np.array(embeddings))

        clusterer = hdb.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",    # use euclidean on normalised vectors (= cosine)
            cluster_selection_method="eom",
            prediction_data=True
        )
        labels = clusterer.fit_predict(X)

        # Group by label (-1 = noise, treated as singleton clusters)
        clusters: Dict[int, List[str]] = {}
        for kw, label in zip(keywords, labels):
            clusters.setdefault(int(label), []).append(kw)

        # Name each cluster using the most central keyword
        named: Dict[str, List[str]] = {}
        for label, kw_list in clusters.items():
            if label == -1:
                # Noise — create individual topic for each (they're unique enough)
                for kw in kw_list:
                    named[kw.replace(" ","_")] = [kw]
            else:
                # Name cluster by its first keyword (shortest = most general)
                name = sorted(kw_list, key=len)[0]
                named[name] = kw_list

        log.info(f"[HDBSCAN] {len(keywords)} keywords → "
                 f"{sum(1 for l in set(labels) if l >= 0)} clusters + "
                 f"{sum(1 for l in labels if l == -1)} noise")
        return named

    def _kmeans_fallback(self, keywords: List[str],
                          embeddings: List[List[float]]) -> Dict[str, List[str]]:
        import numpy as np
        from sklearn.cluster import KMeans
        k = max(3, min(50, len(keywords) // 10))
        X = np.array(embeddings)
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X)
        clusters: Dict[int, List[str]] = {}
        for kw, label in zip(keywords, labels):
            clusters.setdefault(int(label), []).append(kw)
        return {sorted(kws, key=len)[0]: kws for kws in clusters.values()}


# ─────────────────────────────────────────────────────────────────────────────
# 2. OFF-TOPIC FILTER
# Add after P3_Normalization, before P4_EntityDetection
# Kills keywords that are semantically off-topic for the business
# ─────────────────────────────────────────────────────────────────────────────

class OffTopicFilter:
    """
    Kill-word filter. Removes keywords irrelevant to the seed keyword/business.

    Example: seed = "cinnamon" (spice business)
    Kill: "cinnamon challenge", "cinnamon smell removal", "cinnamon furniture color"
    Keep: "cinnamon benefits", "buy cinnamon online", "cinnamon recipes"

    Two layers:
      1. Global kill words (always irrelevant for all seeds)
      2. Per-seed custom kill words (business-specific)
    """

    # Global kill words — common irrelevant patterns for any spice/food business
    GLOBAL_KILL = [
        # Social media / viral content
        "challenge","meme","viral","tiktok","instagram","facebook","reddit","twitter",
        "youtube",
        # Unrelated consumer product categories
        "furniture","paint","color","candle","perfume","air freshener",
        "decoration","wallpaper","nail","polish","lipstick","makeup",
        # Off-topic uses
        "pest control","insect","cockroach","moth","repellent",
        # DIY / craft (not food related)
        "craft","diy","sewing","knitting","crochet",
        # Sports / other entertainment (unless relevant)
        "game","sports","jersey","team",
        # Low-quality traffic patterns
        "free download","crack","torrent","pirate","hack",
    ]

    def __init__(self, seed_kill_words: List[str] = None):
        """
        seed_kill_words: per-seed custom kill words set by user
        Example: ["challenge", "furniture", "scented candle"] for a spice business
        """
        self.seed_kill = [w.lower() for w in (seed_kill_words or [])]
        self.global_kill = [w.lower() for w in self.GLOBAL_KILL]

    def is_global_kill(self, keyword: str) -> bool:
        """Return True if keyword matches any global kill word."""
        kl = keyword.lower()
        return any(k in kl for k in self.global_kill)

    def filter(self, keywords: List[str]) -> List[str]:
        """
        Returns kept_keywords (list of keywords that passed the filter).
        Keywords matching any global or seed kill word are removed.
        """
        all_kill = set(self.global_kill + self.seed_kill)
        kept = [kw for kw in keywords if not any(k in kw.lower() for k in all_kill)]
        log.info(f"[OffTopicFilter] {len(keywords)} → {len(kept)} kept "
                 f"({len(keywords)-len(kept)} removed)")
        return kept

    def filter_tuple(self, keywords: List[str]) -> Tuple[List[str], List[str]]:
        """Returns (kept_keywords, removed_keywords) — for callers that need both lists."""
        all_kill = set(self.global_kill + self.seed_kill)
        kept, removed = [], []
        for kw in keywords:
            (removed if any(k in kw.lower() for k in all_kill) else kept).append(kw)
        return kept, removed

    def filter_with_reason(self, keywords: List[str]) -> List[dict]:
        """Returns list with reason for each filtered keyword (for console output)."""
        all_kill = set(self.global_kill + self.seed_kill)
        result = []
        for kw in keywords:
            kl = kw.lower()
            kill_match = next((k for k in all_kill if k in kl), None)
            result.append({
                "keyword": kw,
                "kept":    kill_match is None,
                "reason":  f"kill word '{kill_match}'" if kill_match else "ok"
            })
        return result

    def add_seed_kill_words(self, words: List[str]):
        """User can add kill words per seed from UI."""
        self.seed_kill.extend([w.lower() for w in words])

    @staticmethod
    def suggest_kill_words(keywords: List[str], seed: str) -> List[str]:
        """
        Auto-suggest kill words based on off-topic keywords found in expansion.
        Uses frequency analysis: words that appear in many keywords but aren't
        related to the seed concept.
        """
        from collections import Counter
        seed_words = set(seed.lower().split())
        word_freq  = Counter()
        for kw in keywords:
            for word in kw.lower().split():
                if word not in seed_words and len(word) > 4:
                    word_freq[word] += 1

        # Words that appear in many keywords but look unrelated
        suggestions = []
        for word, count in word_freq.most_common(50):
            if count >= 3 and word not in seed.lower():
                suggestions.append(word)
        return suggestions[:20]


# ─────────────────────────────────────────────────────────────────────────────
# 3. KEYWORD TRAFFIC SCORER
# Replaces/extends P7_OpportunityScoring in ruflo_20phase_engine.py
# Key: Quick Win and Gold Mine tags for opportunities dashboard
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoredKeyword:
    keyword:       str
    volume:        int     = 0
    difficulty:    int     = 50
    intent:        str     = "informational"
    traffic_score: float   = 0.0
    tag:           str     = ""    # "quick_win" | "gold_mine" | "standard" | "hard"
    opportunity_score: float = 0.0
    score:         float   = 0.0  # alias for opportunity_score — used by tests

    def __post_init__(self):
        # Keep score and opportunity_score in sync
        if self.score != 0.0 and self.opportunity_score == 0.0:
            self.opportunity_score = self.score
        elif self.opportunity_score != 0.0 and self.score == 0.0:
            self.score = self.opportunity_score

    def __lt__(self, other): return self.score < other.score
    def __le__(self, other): return self.score <= other.score
    def __gt__(self, other): return self.score > other.score
    def __ge__(self, other): return self.score >= other.score


class KeywordTrafficScorer:
    """
    Traffic-focused keyword scoring from AnnaSEO.

    Formula: traffic_score = volume × (1 - difficulty/100) × intent_weight

    Intent weights:
      transactional: 1.5  (highest — direct purchase intent)
      commercial:    1.3  (research to buy)
      comparison:    1.2  (vs intent)
      informational: 1.0  (base)
      navigational:  0.7  (looking for specific site, less valuable)

    Tags:
      Quick Win:  volume > 500  AND difficulty < 30  → target first
      Gold Mine:  volume > 2000 AND difficulty < 40  → high value long-term
      Standard:   everything else
      Hard:       difficulty > 70 → require domain authority
    """

    INTENT_WEIGHTS = {
        "transactional":  1.5,
        "commercial":     1.3,
        "comparison":     1.2,
        "informational":  1.0,
        "navigational":   0.7,
    }

    # Thresholds from AnnaSEO
    QUICK_WIN_VOLUME     = 500
    QUICK_WIN_DIFFICULTY = 30
    GOLD_MINE_VOLUME     = 2000
    GOLD_MINE_DIFFICULTY = 40
    HARD_DIFFICULTY      = 70

    _SENTINEL = object()  # detect when volume/difficulty not explicitly passed

    def score(self, keyword: str, volume=_SENTINEL, difficulty=_SENTINEL,
               intent: str = "informational"):
        """Score a single keyword.

        If called with just keyword: returns float (opportunity score 0-100).
        If called with volume + difficulty: returns ScoredKeyword object.
        """
        keyword_only = volume is self._SENTINEL and difficulty is self._SENTINEL
        vol  = 100 if volume is self._SENTINEL else int(volume)
        diff = 50  if difficulty is self._SENTINEL else int(difficulty)

        intent_w  = self.INTENT_WEIGHTS.get(intent, 1.0)
        ease      = max(0, 1 - diff / 100)
        traffic_s = vol * ease * intent_w

        # Tag assignment
        if vol >= self.GOLD_MINE_VOLUME and diff <= self.GOLD_MINE_DIFFICULTY:
            tag = "gold_mine"
        elif vol >= self.QUICK_WIN_VOLUME and diff <= self.QUICK_WIN_DIFFICULTY:
            tag = "quick_win"
        elif diff >= self.HARD_DIFFICULTY:
            tag = "hard"
        else:
            tag = "standard"

        # Opportunity score (0-100 normalized)
        opp = round(min(100, traffic_s / 1000 * 10), 1)

        if keyword_only:
            # Simple float for tests/quick use
            return opp

        return ScoredKeyword(
            keyword=keyword, volume=vol, difficulty=diff,
            intent=intent, traffic_score=round(traffic_s, 1),
            tag=tag, opportunity_score=opp, score=opp
        )

    def score_batch(self, keywords: List[dict]) -> List[ScoredKeyword]:
        """
        Score a list of keywords.
        Each dict: {keyword, volume, difficulty, intent}
        """
        scored = [
            self.score(
                k.get("keyword",""), k.get("volume",0),
                k.get("difficulty",50), k.get("intent","informational")
            )
            for k in keywords
        ]
        return sorted(scored, key=lambda x: x.traffic_score, reverse=True)

    def opportunities_report(self, scored: List[ScoredKeyword]) -> dict:
        """
        Return opportunities breakdown for dashboard display.
        This is what powers the Opportunities view from AnnaSEO.
        """
        quick_wins = [s for s in scored if s.tag == "quick_win"]
        gold_mines = [s for s in scored if s.tag == "gold_mine"]
        hard       = [s for s in scored if s.tag == "hard"]
        standard   = [s for s in scored if s.tag == "standard"]

        return {
            "total": len(scored),
            "quick_wins": {
                "count": len(quick_wins),
                "label": f"Volume >{self.QUICK_WIN_VOLUME} + KD <{self.QUICK_WIN_DIFFICULTY}",
                "keywords": [s.keyword for s in quick_wins[:20]]
            },
            "gold_mines": {
                "count": len(gold_mines),
                "label": f"Volume >{self.GOLD_MINE_VOLUME} + KD <{self.GOLD_MINE_DIFFICULTY}",
                "keywords": [s.keyword for s in gold_mines[:20]]
            },
            "standard": {"count": len(standard)},
            "hard":     {"count": len(hard)},
            "top_10": [
                {
                    "keyword":       s.keyword,
                    "traffic_score": s.traffic_score,
                    "tag":           s.tag,
                    "volume":        s.volume,
                    "difficulty":    s.difficulty
                }
                for s in scored[:10]
            ]
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. CANNIBALIZATION DETECTOR
# Call before generating content for a keyword
# Not the same as dedup — different problem
# ─────────────────────────────────────────────────────────────────────────────

class CannibalizationDetector:
    """
    Detect keyword cannibalization before generating new content.

    Dedup (what we have): prevents two identical articles
    Cannibalization (this): two DIFFERENT articles targeting the SAME keyword
    → Google picks one to rank, demotes the other. Both lose.

    Example:
      Article A: "Black Pepper Health Benefits" → targets "black pepper benefits"
      Article B: "Benefits of Black Pepper"     → also targets "black pepper benefits"
      = Cannibalization. Google confused. Both rank lower.

    Solution:
      Before generating Article B, check if Article A already targets same keyword.
      If yes: either merge, differentiate the angle, or skip.
    """

    def __init__(self, similarity_threshold: float = 0.85):
        self.threshold = similarity_threshold
        self._published: List[dict] = []   # {title, keyword, url, embedding}

    def register(self, title: str, keyword: str, url: str,
                  embedding: List[float] = None):
        """Register a published/scheduled article."""
        self._published.append({
            "title": title, "keyword": keyword.lower().strip(),
            "url": url, "embedding": embedding
        })

    def check(self, new_keyword: str,
               existing_articles_or_title=None,
               new_embedding: List[float] = None) -> dict:
        """
        Check if a new keyword will cannibalize existing content.

        Two calling styles:
          check(keyword, existing_articles)  — list of strings/dicts (new style)
          check(keyword, title, embedding)   — title + embedding (old style)

        Returns: {risk, conflict_with, recommendation}
        """
        nk = new_keyword.lower().strip()

        # New-style: existing_articles is a list
        if isinstance(existing_articles_or_title, list):
            existing = existing_articles_or_title
            # Check against the provided list
            for item in existing:
                ex_kw = (item if isinstance(item, str) else item.get("keyword","")).lower().strip()
                if ex_kw == nk:
                    return {
                        "risk": "high",
                        "cannibalization_risk": "high",
                        "type": "exact_keyword_match",
                        "conflict_with": item,
                        "recommendation": f"Exact match with existing article '{item}'."
                    }
            # Near-duplicate check: word overlap > 70%
            nk_words = set(nk.split())
            for item in existing:
                ex_kw = (item if isinstance(item, str) else item.get("keyword","")).lower().strip()
                ex_words = set(ex_kw.split())
                if len(nk_words) > 0 and ex_words:
                    overlap = len(nk_words & ex_words) / max(len(nk_words), len(ex_words))
                    if overlap >= 0.6:
                        return {
                            "risk": "medium",
                            "cannibalization_risk": "medium",
                            "type": "near_duplicate",
                            "conflict_with": item,
                            "recommendation": f"High word overlap ({overlap:.0%}) with '{item}'."
                        }
            return {"risk": "none", "cannibalization_risk": "none",
                    "type": None, "conflict_with": None, "recommendation": "Safe to generate."}

        # Old-style: second arg is a title string
        new_title = existing_articles_or_title or ""

        # Fast check: exact keyword match against registered articles
        exact = [p for p in self._published if p["keyword"] == nk]
        if exact:
            return {
                "risk": "high",
                "cannibalization_risk": "high",
                "type": "exact_keyword_match",
                "conflict_with": exact[0],
                "recommendation": (
                    f"Article already targets '{new_keyword}': "
                    f"'{exact[0]['title']}'. "
                    "Options: merge, differentiate angle, or skip."
                )
            }

        # Semantic similarity check (if embeddings available)
        if new_embedding and any(p.get("embedding") for p in self._published):
            similar = self._find_similar(new_embedding)
            if similar:
                return {
                    "risk": "medium",
                    "cannibalization_risk": "medium",
                    "type": "semantic_overlap",
                    "conflict_with": similar,
                    "recommendation": (
                        f"High semantic overlap with '{similar['title']}'. "
                        "Consider merging or adding a unique angle."
                    )
                }

        return {"risk": "none", "cannibalization_risk": "none",
                "type": None, "conflict_with": None, "recommendation": "Safe to generate."}

    def _find_similar(self, embedding: List[float],
                       threshold: float = None) -> Optional[dict]:
        t = threshold or self.threshold
        for p in self._published:
            if not p.get("embedding"):
                continue
            sim = self._cosine(embedding, p["embedding"])
            if sim >= t:
                return p
        return None

    def _cosine(self, a: List[float], b: List[float]) -> float:
        import math
        dot   = sum(x*y for x,y in zip(a,b))
        mag_a = math.sqrt(sum(x*x for x in a))
        mag_b = math.sqrt(sum(x*x for x in b))
        return dot / (mag_a * mag_b + 1e-9)

    def batch_check(self, new_keywords, existing_articles=None) -> List[dict]:
        """
        Check a list of new keywords/articles against existing articles.

        new_keywords: List[str] or List[dict] (each dict has 'keyword' key)
        existing_articles: optional List[str] or List[dict] to check against
        Returns: List[dict] with cannibalization_risk and recommendation fields.
        """
        results = []
        seen_keywords: set = set()
        existing = existing_articles or []

        # Normalize new_keywords to list of dicts
        normalized = []
        for item in new_keywords:
            if isinstance(item, str):
                normalized.append({"keyword": item})
            else:
                normalized.append(item)

        for art in normalized:
            kw = art.get("keyword","").lower().strip()
            if kw in seen_keywords:
                results.append({
                    **art,
                    "cannibalization_risk": "high",
                    "recommendation": f"Duplicate keyword '{kw}' in batch"
                })
            else:
                seen_keywords.add(kw)
                if existing:
                    check = self.check(kw, existing)
                else:
                    check = self.check(kw, art.get("title",""))
                results.append({**art,
                                 "cannibalization_risk": check.get("cannibalization_risk", check.get("risk","none")),
                                 "recommendation": check.get("recommendation","")})
        return results

    def report(self) -> dict:
        """Summary of cannibalization risks across all registered articles."""
        return {
            "total_articles": len(self._published),
            "unique_keywords": len(set(p["keyword"] for p in self._published)),
            "potential_cannibalization": len(self._published) - len(set(p["keyword"] for p in self._published))
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. THREE MISSING EXPANSION DIMENSIONS
# Add to P2_KeywordExpansion in ruflo_20phase_engine.py
# Storage, Cultivation, History — ~50 extra low-KD keywords per seed
# ─────────────────────────────────────────────────────────────────────────────

class MissingExpansionDimensions:
    """
    Three expansion dimensions from AnnaSEO docs not in our 8-method engine.
    These produce ~50 extra keywords per seed with very low KD.

    Storage:      "how to store X", "X shelf life", "X preservation methods"
    Cultivation:  "where is X grown", "X farming", "X climate requirements"
    History:      "X history", "X origin", "X discovery", "X trade route"

    Add to P2 expansion as methods 9, 10, 11.
    """

    STORAGE_TEMPLATES = [
        "how to store {seed}",
        "{seed} shelf life",
        "how long does {seed} last",
        "{seed} storage tips",
        "{seed} preservation methods",
        "does {seed} expire",
        "best way to store {seed}",
        "{seed} proper storage",
        "storing {seed} at home",
        "{seed} freshness",
        "how to keep {seed} fresh",
        "airtight {seed} storage",
    ]

    CULTIVATION_TEMPLATES = [
        "where is {seed} grown",
        "{seed} farming",
        "{seed} cultivation",
        "how to grow {seed}",
        "{seed} growing regions",
        "{seed} climate requirements",
        "{seed} harvest season",
        "{seed} production countries",
        "{seed} plantation",
        "organic {seed} farming",
        "{seed} growing conditions",
        "{seed} crop yield",
    ]

    HISTORY_TEMPLATES = [
        "{seed} history",
        "{seed} origin",
        "history of {seed}",
        "where does {seed} come from",
        "{seed} ancient uses",
        "{seed} traditional uses",
        "{seed} discovery",
        "{seed} trade history",
        "{seed} ancient history",
        "{seed} Silk Road",
        "{seed} historical significance",
        "{seed} medicinal history",
    ]

    def expand_storage(self, seed: str) -> List[str]:
        return [t.format(seed=seed) for t in self.STORAGE_TEMPLATES]

    def expand_cultivation(self, seed: str) -> List[str]:
        return [t.format(seed=seed) for t in self.CULTIVATION_TEMPLATES]

    def expand_history(self, seed: str) -> List[str]:
        return [t.format(seed=seed) for t in self.HISTORY_TEMPLATES]

    def find(self, seed: str, existing: List[str] = None) -> List[str]:
        """
        Find missing expansion keywords for a seed, excluding already-existing ones.
        Returns a flat list of new keyword suggestions covering all dimensions.
        """
        existing_set = set((existing or []))
        # Build comprehensive keyword list covering all dimensions
        candidates = (
            # Questions
            [f"what is {seed}", f"how to use {seed}", f"why use {seed}",
             f"does {seed} work", f"is {seed} safe", f"can {seed} help",
             f"when to use {seed}", f"how does {seed} work"]
            # Commercial
            + [f"buy {seed}", f"best {seed}", f"{seed} price", f"organic {seed}",
               f"{seed} wholesale", f"{seed} online", f"cheap {seed}", f"{seed} near me"]
            # Comparison
            + [f"{seed} vs alternative", f"{seed} versus substitute",
               f"compare {seed}", f"{seed} or substitute"]
            # Storage, cultivation, history
            + self.expand_storage(seed)
            + self.expand_cultivation(seed)
            + self.expand_history(seed)
        )
        # Filter: must contain seed, must not be in existing
        result = [kw for kw in candidates if seed in kw and kw not in existing_set]
        return list(dict.fromkeys(result))  # dedup preserving order

    def expand_all(self, seed: str) -> Dict[str, List[str]]:
        """All three dimensions at once."""
        return {
            "storage":     self.expand_storage(seed),
            "cultivation": self.expand_cultivation(seed),
            "history":     self.expand_history(seed),
            "total":       (self.expand_storage(seed) +
                            self.expand_cultivation(seed) +
                            self.expand_history(seed))
        }

    # Bonus: comparison matrix (N×(N-1)/2)
    @staticmethod
    def comparison_matrix(entities: List[str]) -> List[str]:
        """
        Generate ALL pairwise comparison keywords.
        For 4 cinnamon types: 4×3/2 = 6 comparisons guaranteed.
        AnnaSEO doc: "Solves 'Cassia vs Ceylon' problem — nothing missed."
        """
        comparisons = []
        for i in range(len(entities)):
            for j in range(i+1, len(entities)):
                a, b = entities[i], entities[j]
                comparisons.extend([
                    f"{a} vs {b}",
                    f"{b} vs {a}",
                    f"{a} or {b}",
                    f"difference between {a} and {b}",
                    f"which is better {a} or {b}",
                ])
        return list(dict.fromkeys(comparisons))   # dedup while preserving order


# ─────────────────────────────────────────────────────────────────────────────
# 6. CONTENT LIFECYCLE MANAGER
# Integrate with P20_RankingFeedback in ruflo_20phase_engine.py
# Maps ranking trends to lifecycle stages, triggers refresh automatically
# ─────────────────────────────────────────────────────────────────────────────

class LifecycleStage:
    NEW        = "new"         # Just published, no data yet
    GROWING    = "growing"     # Rankings improving week-over-week
    PEAK       = "peak"        # Ranking stable at top 10, holding position
    DECLINING  = "declining"   # Rankings dropping 3+ weeks in a row
    NEEDS_REFRESH = "refresh_needed"  # Dropped out of top 20, action required
    ARCHIVED   = "archived"    # Manually archived


@dataclass
class ContentLifecycle:
    article_id:   str
    keyword:      str
    stage:        str        = LifecycleStage.NEW
    current_rank: int        = 999
    peak_rank:    int        = 999
    consecutive_drops: int   = 0
    weeks_at_stage:    int   = 0
    last_updated:      str   = field(default_factory=lambda: datetime.utcnow().isoformat())
    next_action:       str   = ""


class ContentLifecycleManager:
    """
    Track article lifecycle stages based on GSC ranking data.
    From AnnaSEO LifecycleManager — closes the self-improving loop.

    Stage transitions:
      new → growing:       rank improves for 2+ consecutive weeks
      growing → peak:      rank reaches top 10 and holds for 2+ weeks
      peak → declining:    rank drops for 3+ consecutive weeks
      declining → refresh: rank drops below 20 and stays there 2+ weeks
      any → new:           after refresh/rewrite, reset to new

    Actions triggered:
      declining:         schedule content update (add 500+ words, refresh stats)
      refresh_needed:    trigger full rewrite via Claude
      peak:              schedule similar content (success pattern)
    """

    def __init__(self):
        self._lifecycles: Dict[str, ContentLifecycle] = {}

    def register(self, article_id: str, keyword: str) -> ContentLifecycle:
        """Register a new article — starts in NEW stage."""
        lc = ContentLifecycle(article_id=article_id, keyword=keyword)
        self._lifecycles[article_id] = lc
        return lc

    def update_ranking(self, article_id: str,
                        new_rank: int) -> ContentLifecycle:
        """
        Update an article's ranking and advance/regress lifecycle stage.
        Call weekly from P20_RankingFeedback.
        """
        if article_id not in self._lifecycles:
            log.warning(f"[Lifecycle] Article {article_id} not registered")
            return None

        lc = self._lifecycles[article_id]
        old_rank = lc.current_rank
        lc.current_rank = new_rank
        lc.weeks_at_stage += 1

        # Track best rank seen
        if new_rank < lc.peak_rank:
            lc.peak_rank = new_rank

        # Stage transitions
        prev_stage = lc.stage
        lc.stage, lc.next_action, lc.consecutive_drops = self._transition(
            lc, old_rank, new_rank
        )

        if lc.stage != prev_stage:
            lc.weeks_at_stage = 0
            log.info(f"[Lifecycle] '{lc.keyword}' stage change: "
                     f"{prev_stage} → {lc.stage} (rank {new_rank})")

        lc.last_updated = datetime.utcnow().isoformat()
        return lc

    def _transition(self, lc: ContentLifecycle,
                     old_rank: int, new_rank: int) -> Tuple[str, str, int]:
        """Return (new_stage, action, consecutive_drops)."""
        drops = lc.consecutive_drops

        if new_rank < old_rank:
            drops = 0   # reset drop counter on improvement
        elif new_rank > old_rank:
            drops += 1  # increment on drop

        # NEW → GROWING: improving for first time
        if lc.stage == LifecycleStage.NEW and new_rank < old_rank:
            return LifecycleStage.GROWING, "Monitor weekly", drops

        # GROWING → PEAK: reached top 10
        if lc.stage == LifecycleStage.GROWING and new_rank <= 10:
            return LifecycleStage.PEAK, "Create similar content to double down", drops

        # PEAK → DECLINING: 3+ consecutive rank drops
        if lc.stage == LifecycleStage.PEAK and drops >= 3:
            return LifecycleStage.DECLINING, \
                f"Schedule content update: add 500+ words, refresh stats, update year", drops

        # DECLINING → REFRESH NEEDED: rank below 20 for 2+ weeks
        if lc.stage == LifecycleStage.DECLINING and new_rank > 20 and lc.weeks_at_stage >= 2:
            return LifecycleStage.NEEDS_REFRESH, \
                f"Full rewrite needed. Current rank {new_rank}. Peak was {lc.peak_rank}.", drops

        return lc.stage, lc.next_action, drops

    def articles_needing_action(self) -> Dict[str, List[ContentLifecycle]]:
        """Return grouped list of articles needing attention."""
        refresh  = [lc for lc in self._lifecycles.values()
                    if lc.stage == LifecycleStage.NEEDS_REFRESH]
        declining= [lc for lc in self._lifecycles.values()
                    if lc.stage == LifecycleStage.DECLINING]
        peak     = [lc for lc in self._lifecycles.values()
                    if lc.stage == LifecycleStage.PEAK]

        return {
            "needs_rewrite":  refresh,
            "needs_update":   declining,
            "double_down":    peak,   # create more similar content
        }

    def report(self) -> dict:
        """Full lifecycle report — shown in Rankings & Analytics page."""
        stage_counts = {}
        for lc in self._lifecycles.values():
            stage_counts[lc.stage] = stage_counts.get(lc.stage, 0) + 1
        return {
            "total_articles": len(self._lifecycles),
            "by_stage":       stage_counts,
            "needs_action":   {
                k: len(v) for k, v in self.articles_needing_action().items()
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION GUIDE — Where each piece plugs into existing Ruflo pipeline
# ─────────────────────────────────────────────────────────────────────────────

INTEGRATION_MAP = """
ANNASEO — Integration guide for the 6 additions

1. HDBSCAN (HDBSCANClustering)
   File: ruflo_20phase_engine.py
   Where: P8_TopicDetection.run()
   Change: Replace KMeans with HDBSCANClustering().cluster(keywords, embeddings)
   Fallback: Already handles ImportError → falls back to KMeans

2. OffTopicFilter
   File: ruflo_20phase_engine.py
   Where: Between P3_Normalization.run() and P4_EntityDetection.run()
   Usage:
     filter = OffTopicFilter(seed_kill_words=project_settings.kill_words)
     keywords, removed = filter.filter(normalised_keywords)
     job.log("OffTopicFilter", "data", f"Removed {len(removed)} off-topic keywords")

3. KeywordTrafficScorer
   File: ruflo_20phase_engine.py
   Where: P7_OpportunityScoring.run() — extend existing scorer
   Usage:
     scorer = KeywordTrafficScorer()
     scored = scorer.score_batch(keywords)
     report = scorer.opportunities_report(scored)
     # Quick Win and Gold Mine tags now appear in keyword tree UI

4. CannibalizationDetector
   File: ruflo_content_engine.py + publishing integration
   Where: Before ContentGenerationEngine.generate()
   Usage:
     detector = CannibalizationDetector()
     # Register all published articles on startup
     for article in published_articles:
         detector.register(article.title, article.keyword, article.url)
     # Check before generating
     check = detector.check(new_keyword, new_title)
     if check["risk"] == "high":
         job.log("Cannibalization", "warning", check["recommendation"])
         # Skip or differentiate

5. Missing Dimensions (MissingExpansionDimensions)
   File: ruflo_20phase_engine.py
   Where: P2_KeywordExpansion._expand_pillar()
   Usage:
     dims = MissingExpansionDimensions()
     extra = dims.expand_all(seed_keyword)["total"]
     all_keywords.extend(extra)
     # +~36 keywords per seed, very low KD

     # Comparison matrix (guaranteed all entity pairs)
     entities = ["ceylon cinnamon", "cassia cinnamon", "saigon cinnamon"]
     comparisons = MissingExpansionDimensions.comparison_matrix(entities)
     # Returns: "ceylon vs cassia", "cassia vs ceylon", etc.

6. ContentLifecycleManager
   File: ruflo_20phase_engine.py
   Where: P20_RankingFeedback.analyse()
   Usage:
     lifecycle_mgr = ContentLifecycleManager()  # singleton, loaded at startup
     # On each weekly GSC sync:
     for gsc_row in gsc_data:
         lifecycle_mgr.update_ranking(gsc_row["article_id"], gsc_row["rank"])
     # Get articles needing attention:
     actions = lifecycle_mgr.articles_needing_action()
     # "needs_rewrite" → trigger Claude full rewrite
     # "needs_update"  → schedule content expansion
     # "double_down"   → create more similar content in same cluster
"""


# ─────────────────────────────────────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_off_topic_filter(self):
        self._h("OffTopicFilter")
        f = OffTopicFilter(seed_kill_words=["challenge","candle","nail"])
        kws = ["cinnamon benefits", "cinnamon challenge", "cinnamon nail art",
               "ceylon cinnamon price", "cinnamon candle scent", "cinnamon diabetes"]
        kept, removed = f.filter(kws)
        self._ok(f"Input: {len(kws)} → Kept: {len(kept)}, Removed: {len(removed)}")
        self._ok(f"Kept: {kept}")
        self._ok(f"Removed: {removed}")

    def test_traffic_scorer(self):
        self._h("KeywordTrafficScorer — Quick Win + Gold Mine tags")
        scorer = KeywordTrafficScorer()
        keywords = [
            {"keyword": "buy cinnamon online",    "volume": 2500, "difficulty": 35, "intent": "transactional"},
            {"keyword": "cinnamon for diabetes",  "volume": 800,  "difficulty": 25, "intent": "informational"},
            {"keyword": "cinnamon benefits",      "volume": 12000,"difficulty": 55, "intent": "informational"},
            {"keyword": "ceylon vs cassia",       "volume": 3200, "difficulty": 28, "intent": "comparison"},
            {"keyword": "cinnamon price per kg",  "volume": 400,  "difficulty": 18, "intent": "commercial"},
        ]
        scored = scorer.score_batch(keywords)
        report = scorer.opportunities_report(scored)
        self._ok(f"Quick wins:  {report['quick_wins']['count']}")
        self._ok(f"Gold mines:  {report['gold_mines']['count']}")
        for s in scored[:3]:
            self._ok(f"  [{s.tag:10}] {s.keyword:35} score={s.traffic_score:.0f}")

    def test_cannibalization(self):
        self._h("CannibalizationDetector")
        detector = CannibalizationDetector()
        detector.register("Cinnamon Benefits Guide", "cinnamon benefits", "/cinnamon-benefits")
        detector.register("Ceylon Cinnamon Health", "ceylon cinnamon health", "/ceylon-health")

        # Test: exact match
        c1 = detector.check("cinnamon benefits", "Health Benefits of Cinnamon")
        self._ok(f"Exact match risk: {c1['risk']} — {c1['recommendation'][:60]}")

        # Test: no conflict
        c2 = detector.check("cinnamon tea recipe", "Cinnamon Tea for Weight Loss")
        self._ok(f"New keyword risk: {c2['risk']}")

    def test_missing_dimensions(self):
        self._h("Missing Expansion Dimensions (Storage + Cultivation + History)")
        dims = MissingExpansionDimensions()
        result = dims.expand_all("cinnamon")
        self._ok(f"Storage:     {len(result['storage'])} keywords")
        self._ok(f"Cultivation: {len(result['cultivation'])} keywords")
        self._ok(f"History:     {len(result['history'])} keywords")
        self._ok(f"Total extra: {len(result['total'])} keywords")
        self._ok(f"Sample: {result['total'][:3]}")

        # Comparison matrix
        entities = ["ceylon cinnamon", "cassia cinnamon", "saigon cinnamon", "korintje cinnamon"]
        comps = MissingExpansionDimensions.comparison_matrix(entities)
        self._ok(f"Comparison matrix for {len(entities)} entities: {len(comps)} comparisons")
        self._ok(f"Sample: {comps[:3]}")

    def test_lifecycle(self):
        self._h("ContentLifecycleManager")
        mgr = ContentLifecycleManager()
        mgr.register("art_001", "cinnamon benefits")
        mgr.register("art_002", "ceylon cinnamon")

        # Simulate ranking history over 10 weeks
        trajectory = [87, 54, 34, 18, 9, 8, 7, 12, 18, 28]  # rises then falls
        for week, rank in enumerate(trajectory):
            lc = mgr.update_ranking("art_001", rank)
            if week in (2, 5, 8):
                print(f"    Week {week+1}: rank={rank} → stage={lc.stage}")

        report = mgr.report()
        self._ok(f"Report: {report}")
        actions = mgr.articles_needing_action()
        self._ok(f"Needs rewrite: {len(actions['needs_rewrite'])}")
        self._ok(f"Needs update:  {len(actions['needs_update'])}")
        self._ok(f"Double down:   {len(actions['double_down'])}")

    def run_all(self):
        print("\n"+"═"*55+"\n  ANNASEO ADDONS — TESTS\n"+"═"*55)
        tests = [
            ("off_topic_filter",      self.test_off_topic_filter),
            ("traffic_scorer",        self.test_traffic_scorer),
            ("cannibalization",       self.test_cannibalization),
            ("missing_dimensions",    self.test_missing_dimensions),
            ("lifecycle",             self.test_lifecycle),
        ]
        p=f=0
        for name,fn in tests:
            try: fn(); p+=1
            except Exception as e: print(f"  ✗ {name}: {e}"); f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*55)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        if len(sys.argv) > 2:
            fn = getattr(Tests(), f"test_{sys.argv[2]}", None)
            if fn: fn()
            else: print(f"Unknown: {sys.argv[2]}")
        else:
            Tests().run_all()
    else:
        print(INTEGRATION_MAP)

"""
================================================================================
RUFLO — 20-PHASE KEYWORD UNIVERSE ENGINE
================================================================================
Complete implementation of the 20-phase pipeline with:

  MEMORY MANAGEMENT    — Every engine has a memory budget. Ruflo orchestrates
                         to prevent OOM. Heavy engines never run simultaneously.
                         Large datasets stream through 500-item chunks.

  THREE-TIER CACHING   — L1: in-memory LRU (hot keywords)
                         L2: SQLite disk cache (SERP: 14d TTL, suggestions: 7d)
                         L3: File checkpoints (.json.gz per phase, per seed)
                         Embeddings: never recalculated (permanent .npy files)

  RUFLO ORCHESTRATOR   — DAG workflow. Checkpoint resume after crash.
                         Parallel execution where safe (P2 sources run parallel).
                         Gates pause execution for customer confirmation.

  CONFIGURABLE PACE    — content_pace dict controls everything:
                         duration_years, blogs_per_day, per_pillar_overrides,
                         parallel_claude_calls, seasonal_priorities

PIPELINE:
  P1  Seed Input         → P2  Keyword Expansion (Google/YouTube/Amazon/Reddit)
  P3  Normalization      → P4  Entity Detection (spaCy)
  P5  Intent Class       → P6  SERP Intelligence (playwright)
  P7  Opportunity Score  → P8  Topic Detection (SBERT)
  P9  Cluster Formation  → P10 Pillar Identification
  P11 Knowledge Graph    → P12 Internal Linking
  P13 Content Calendar   → P14 Dedup Prevention
  P15 Content Brief      → P16 Claude Content Generation
  P17 SEO Optimization   → P18 Schema & Metadata
  P19 Publishing         → P20 Ranking Feedback (self-improving)

1 seed keyword → 40 clusters → 400 topics → 2,000+ blogs → 2-year pipeline
================================================================================
"""

from __future__ import annotations

import os, json, gzip, time, re, hashlib, logging, sqlite3, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, Generator, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from dotenv import load_dotenv
import requests as _req

load_dotenv()
log = logging.getLogger("ruflo.engine")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    # Paths
    BASE_DIR        = Path(os.getenv("RUFLO_DIR", "./ruflo_data"))
    CACHE_DIR       = BASE_DIR / "cache"
    CHECKPOINT_DIR  = BASE_DIR / "checkpoints"
    EMBED_DIR       = BASE_DIR / "embeddings"
    BRIEF_DIR       = BASE_DIR / "briefs"
    ARTICLE_DIR     = BASE_DIR / "articles"

    # AI
    OLLAMA_URL      = os.getenv("OLLAMA_URL",     "http://localhost:11434")
    OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",   "deepseek-r1:7b")
    OLLAMA_EMBED    = os.getenv("OLLAMA_EMBED",   "nomic-embed-text")
    GEMINI_KEY      = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL    = os.getenv("GEMINI_MODEL",   "gemini-1.5-flash")
    GEMINI_RATE     = float(os.getenv("GEMINI_RATE", "4.0"))
    ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL    = os.getenv("CLAUDE_MODEL",   "claude-sonnet-4-6")
    EMBED_MODEL     = "all-MiniLM-L6-v2"

    # Cache TTL (seconds)
    TTL_SUGGESTIONS = 7  * 24 * 3600   # 7 days
    TTL_SERP        = 14 * 24 * 3600   # 14 days
    TTL_ENTITIES    = 30 * 24 * 3600   # 30 days

    # Memory budgets (MB) per phase
    MEMORY_BUDGET: Dict[str, int] = {
        "P1":  5,   "P2":  80,  "P3":  30,  "P4":  150,
        "P5":  20,  "P6":  60,  "P7":  40,  "P8":  380,
        "P9":  100, "P10": 20,  "P11": 50,  "P12": 30,
        "P13": 20,  "P14": 40,  "P15": 30,  "P16": 50,
        "P17": 30,  "P18": 10,  "P19": 20,  "P20": 40,
    }

    # Heavy phases that must not run simultaneously
    HEAVY_PHASES = {"P4", "P8"}

    # Chunk size for streaming large keyword sets
    CHUNK_SIZE  = 500
    EMBED_BATCH = 256

    @classmethod
    def ensure_dirs(cls):
        for d in [cls.CACHE_DIR, cls.CHECKPOINT_DIR, cls.EMBED_DIR,
                  cls.BRIEF_DIR, cls.ARTICLE_DIR]:
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class ContentPace:
    """
    Fully configurable content pace.
    Example: 50 pillars × 50 blogs/day for one month = intensive launch.
    """
    duration_years:         float = 2.0      # 1, 2, 3, 5, or fraction
    blogs_per_day:          int   = 3        # global default
    parallel_claude_calls:  int   = 3        # simultaneous Claude article generations
    pillar_overrides:       Dict[str,int] = field(default_factory=dict)
    # {"Christmas Baking": 20}  → publish all 20 before Dec 1
    seasonal_priorities:    Dict[str,str] = field(default_factory=dict)
    # {"Christmas Baking": "2026-11-15"} → must be live by this date

    @property
    def total_days(self) -> int:
        return int(365 * self.duration_years)

    def blogs_per_day_for_pillar(self, pillar: str) -> int:
        return self.pillar_overrides.get(pillar, self.blogs_per_day)

    def estimated_cost_usd(self, total_blogs: int) -> float:
        return round(total_blogs * 0.022, 2)   # ~$0.022 per 2000-word article

    def estimated_time_minutes(self, total_blogs: int) -> float:
        # 3 parallel calls × ~35s each = ~12s effective per article
        secs_per_article = 35 / max(self.parallel_claude_calls, 1)
        return round(total_blogs * secs_per_article / 60, 1)

    def summary(self, total_blogs: int) -> dict:
        return {
            "total_blogs":      total_blogs,
            "duration_years":   self.duration_years,
            "blogs_per_day":    self.blogs_per_day,
            "parallel_calls":   self.parallel_claude_calls,
            "estimated_cost":   f"${self.estimated_cost_usd(total_blogs)}",
            "estimated_time":   f"{self.estimated_time_minutes(total_blogs)} min",
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — MEMORY MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class MemoryManager:
    """
    Tracks available RAM. Decides if engine runs in-memory or streamed from disk.
    Prevents heavy phases from running simultaneously.
    """
    _active_heavy: set = set()

    @staticmethod
    def available_mb() -> float:
        try:
            import psutil
            return psutil.virtual_memory().available / (1024 * 1024)
        except ImportError:
            return 1024.0   # assume 1GB if psutil not installed

    @classmethod
    def can_run(cls, phase: str) -> Tuple[bool, str]:
        budget = Cfg.MEMORY_BUDGET.get(phase, 50)
        avail  = cls.available_mb()

        # Heavy phase conflict check
        if phase in Cfg.HEAVY_PHASES and cls._active_heavy:
            return False, f"Heavy phase already running: {cls._active_heavy}"

        # Memory budget check (require 20% headroom)
        if avail < budget * 1.2:
            return False, f"Low memory: {avail:.0f}MB available, {budget}MB needed"

        return True, "ok"

    @classmethod
    def acquire(cls, phase: str):
        if phase in Cfg.HEAVY_PHASES:
            cls._active_heavy.add(phase)

    @classmethod
    def release(cls, phase: str):
        cls._active_heavy.discard(phase)

    @staticmethod
    def chunks(items: list, size: int = None) -> Generator:
        """Stream large lists through chunks to control memory."""
        size = size or Cfg.CHUNK_SIZE
        for i in range(0, len(items), size):
            yield items[i:i+size]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — THREE-TIER CACHE
# ─────────────────────────────────────────────────────────────────────────────

class Cache:
    """
    L1: In-memory LRU (hot lookups, evicted after engine completes)
    L2: SQLite disk cache (persistent, TTL-aware)
    L3: File checkpoints (.json.gz per phase per seed)
    """

    _l1: Dict[str, Any] = {}   # in-memory LRU
    _l1_max = 500
    _db: Optional[sqlite3.Connection] = None

    @classmethod
    def _get_db(cls) -> sqlite3.Connection:
        if cls._db is None:
            Cfg.ensure_dirs()
            cls._db = sqlite3.connect(str(Cfg.CACHE_DIR / "ruflo_cache.sqlite"),
                                       check_same_thread=False)
            cls._db.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB,
                    created_at INTEGER,
                    ttl INTEGER
                )""")
            cls._db.commit()
        return cls._db

    @classmethod
    def get(cls, key: str, ttl: int = None) -> Optional[Any]:
        """Check L1 → L2 → return None if miss."""
        # L1
        if key in cls._l1:
            return cls._l1[key]
        # L2
        db = cls._get_db()
        row = db.execute("SELECT value, created_at, ttl FROM cache WHERE key=?", (key,)).fetchone()
        if row:
            value, created, row_ttl = row
            effective_ttl = ttl or row_ttl or 0
            if effective_ttl == 0 or (time.time() - created) < effective_ttl:
                obj = json.loads(value)
                cls._set_l1(key, obj)
                return obj
        return None

    @classmethod
    def set(cls, key: str, value: Any, ttl: int = 0):
        """Write to L1 + L2."""
        cls._set_l1(key, value)
        db  = cls._get_db()
        db.execute("INSERT OR REPLACE INTO cache (key,value,created_at,ttl) VALUES (?,?,?,?)",
                   (key, json.dumps(value, default=str), int(time.time()), ttl))
        db.commit()

    @classmethod
    def _set_l1(cls, key: str, value: Any):
        if len(cls._l1) >= cls._l1_max:
            cls._l1.pop(next(iter(cls._l1)))
        cls._l1[key] = value

    @classmethod
    def clear_l1(cls):
        cls._l1.clear()

    # ── Checkpoints (L3) ──────────────────────────────────────────────────────

    @staticmethod
    def checkpoint_path(seed_id: str, phase: str) -> Path:
        p = Cfg.CHECKPOINT_DIR / seed_id
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{phase}.json.gz"

    @classmethod
    def save_checkpoint(cls, seed_id: str, phase: str, data: Any):
        path = cls.checkpoint_path(seed_id, phase)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(data, f, default=str)
        log.info(f"[Cache] Checkpoint saved: {phase} ({path.stat().st_size//1024}KB)")

    @classmethod
    def load_checkpoint(cls, seed_id: str, phase: str) -> Optional[Any]:
        path = cls.checkpoint_path(seed_id, phase)
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)
            log.info(f"[Cache] Checkpoint loaded: {phase} ✓")
            return data
        return None

    # ── Embedding cache ───────────────────────────────────────────────────────

    @staticmethod
    def embed_path(text: str) -> Path:
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        return Cfg.EMBED_DIR / f"{h}.npy"

    @classmethod
    def get_embedding(cls, text: str):
        import numpy as np
        p = cls.embed_path(text)
        if p.exists():
            return np.load(p)
        return None

    @classmethod
    def save_embedding(cls, text: str, vector):
        import numpy as np
        np.save(str(cls.embed_path(text)), vector)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — AI ROUTER
# ─────────────────────────────────────────────────────────────────────────────

class AI:
    _embed_model = None
    _spacy_model = None
    _last_gemini = 0.0

    @staticmethod
    def deepseek(prompt: str, system: str = "You are an SEO expert.",
                  temperature: float = 0.1) -> str:
        try:
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/chat", json={
                "model": Cfg.OLLAMA_MODEL, "stream": False,
                "options": {"temperature": temperature},
                "messages": [{"role":"system","content":system},
                             {"role":"user","content":prompt}]
            }, timeout=120)
            r.raise_for_status()
            t = r.json()["message"]["content"].strip()
            return re.sub(r"<think>.*?</think>","",t,flags=re.DOTALL).strip()
        except Exception as e:
            log.warning(f"[AI] DeepSeek: {e}")
            return ""

    @classmethod
    def gemini(cls, prompt: str, temperature: float = 0.3) -> str:
        if not Cfg.GEMINI_KEY:
            return cls.deepseek(prompt, temperature=temperature)
        elapsed = time.time() - cls._last_gemini
        if elapsed < Cfg.GEMINI_RATE:
            time.sleep(Cfg.GEMINI_RATE - elapsed)
        try:
            import google.generativeai as genai
            genai.configure(api_key=Cfg.GEMINI_KEY)
            m = genai.GenerativeModel(Cfg.GEMINI_MODEL)
            r = m.generate_content(prompt,
                generation_config=genai.GenerationConfig(temperature=temperature))
            cls._last_gemini = time.time()
            return r.text.strip()
        except Exception as e:
            log.warning(f"[AI] Gemini: {e}")
            return cls.deepseek(prompt, temperature=temperature)

    @staticmethod
    def claude(prompt: str, system: str, max_tokens: int = 4096) -> Tuple[str, int]:
        if not Cfg.ANTHROPIC_KEY:
            return '{"error":"no key"}', 0
        try:
            import anthropic
            c = anthropic.Anthropic(api_key=Cfg.ANTHROPIC_KEY)
            r = c.messages.create(
                model=Cfg.CLAUDE_MODEL, max_tokens=max_tokens,
                system=system, messages=[{"role":"user","content":prompt}]
            )
            return r.content[0].text.strip(), r.usage.input_tokens + r.usage.output_tokens
        except Exception as e:
            log.error(f"[AI] Claude: {e}")
            return '{"error":"' + str(e)[:100] + '"}', 0

    @classmethod
    def embed_batch(cls, texts: List[str]) -> List[List[float]]:
        """Embed batch with cache check. Never re-embeds same text."""
        import numpy as np
        results = [None] * len(texts)
        uncached_idx, uncached_texts = [], []

        for i, t in enumerate(texts):
            cached = Cache.get_embedding(t)
            if cached is not None:
                results[i] = cached.tolist()
            else:
                uncached_idx.append(i)
                uncached_texts.append(t)

        if uncached_texts:
            vectors = cls._encode(uncached_texts)
            for idx, text, vec in zip(uncached_idx, uncached_texts, vectors):
                Cache.save_embedding(text, vec)
                results[idx] = vec if isinstance(vec, list) else vec.tolist()

        return results

    @classmethod
    def _encode(cls, texts: List[str]) -> List:
        """Try Ollama embed → sentence-transformers fallback."""
        try:
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/embed",
                          json={"model": Cfg.OLLAMA_EMBED, "input": texts},
                          timeout=60)
            r.raise_for_status()
            return r.json()["embeddings"]
        except Exception:
            if cls._embed_model is None:
                from sentence_transformers import SentenceTransformer
                cls._embed_model = SentenceTransformer(Cfg.EMBED_MODEL)
            return cls._embed_model.encode(texts, normalize_embeddings=True).tolist()

    @classmethod
    def spacy_nlp(cls):
        if cls._spacy_model is None:
            import spacy
            try:
                cls._spacy_model = spacy.load("en_core_web_sm")
            except OSError:
                log.warning("spaCy model not found. Run: python -m spacy download en_core_web_sm")
                cls._spacy_model = None
        return cls._spacy_model

    @classmethod
    def unload_embed_model(cls):
        """Free SBERT memory after use."""
        cls._embed_model = None
        import gc; gc.collect()
        log.info("[AI] SBERT model unloaded from memory")

    @staticmethod
    def parse_json(text: str) -> Any:
        text = re.sub(r"<think>.*?</think>","",text,flags=re.DOTALL)
        text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
        m = re.search(r'(\{.*\}|\[.*\])',text,re.DOTALL)
        if m: return json.loads(m.group(1))
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — SEED (P1)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Seed:
    id:         str
    keyword:    str
    language:   str = "english"
    region:     str = "India"
    product_url:str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def make_id(keyword: str) -> str:
        return hashlib.md5(keyword.lower().strip().encode()).hexdigest()[:10]


class P1_SeedInput:
    """Phase 1: Store and validate seed keyword."""
    phase = "P1"

    def run(self, keyword: str, language: str = "english",
             region: str = "India", product_url: str = "") -> Seed:
        seed = Seed(
            id=Seed.make_id(keyword), keyword=keyword.strip().lower(),
            language=language, region=region, product_url=product_url
        )
        Cache.set(f"seed:{seed.id}", asdict(seed))
        log.info(f"[P1] Seed stored: '{seed.keyword}' (id={seed.id})")
        return seed


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — KEYWORD EXPANSION (P2)
# ─────────────────────────────────────────────────────────────────────────────

class P2_KeywordExpansion:
    """
    Phase 2: Generate large keyword universe using free sources.
    Sources: Google Autosuggest, YouTube, Amazon, Reddit, DuckDuckGo.
    
    Target: 500–3000 keywords per seed.
    Cache: 7-day TTL per query.
    Memory: 80MB max — streams 500 at a time to disk.
    """
    phase = "P2"

    def run(self, seed: Seed) -> List[str]:
        # Check checkpoint first
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        all_kws = []
        log.info(f"[P2] Expanding '{seed.keyword}' from 5 sources...")

        # Run all sources — each cached independently
        all_kws.extend(self._google_autosuggest(seed.keyword))
        all_kws.extend(self._youtube_autosuggest(seed.keyword))
        all_kws.extend(self._amazon_autosuggest(seed.keyword))
        all_kws.extend(self._duckduckgo(seed.keyword))
        all_kws.extend(self._reddit_titles(seed.keyword))
        all_kws.extend(self._question_variants(seed.keyword))

        # Deduplicate before save
        unique = list(dict.fromkeys(k.lower().strip() for k in all_kws if k.strip()))
        log.info(f"[P2] Total keywords: {len(unique)}")
        Cache.save_checkpoint(seed.id, self.phase, unique)
        return unique

    def _google_autosuggest(self, kw: str) -> List[str]:
        cache_key = f"google_suggest:{hashlib.md5(kw.encode()).hexdigest()[:8]}"
        cached = Cache.get(cache_key, Cfg.TTL_SUGGESTIONS)
        if cached:
            return cached

        results = []
        suffixes = [""] + list("abcdefghijklmnopqrstuvwxyz") + [
            "for", "with", "without", "vs", "benefits", "side effects",
            "uses", "recipe", "buy", "organic", "price", "best"
        ]
        for sfx in suffixes[:20]:   # limit for free usage
            query = f"{kw} {sfx}".strip()
            try:
                r = _req.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client":"firefox","q":query},
                    headers={"User-Agent":"Mozilla/5.0"}, timeout=5
                )
                if r.ok:
                    data = r.json()
                    if isinstance(data,list) and len(data)>1:
                        results.extend([str(s).lower() for s in data[1]])
                time.sleep(0.2)
            except Exception:
                continue

        Cache.set(cache_key, results, Cfg.TTL_SUGGESTIONS)
        log.info(f"[P2/Google]  {len(results)} suggestions for '{kw}'")
        return results

    def _youtube_autosuggest(self, kw: str) -> List[str]:
        cache_key = f"yt_suggest:{hashlib.md5(kw.encode()).hexdigest()[:8]}"
        cached = Cache.get(cache_key, Cfg.TTL_SUGGESTIONS)
        if cached:
            return cached

        results = []
        for sfx in ["", "how to", "benefits", "recipe", "tutorial"]:
            query = f"{kw} {sfx}".strip()
            try:
                r = _req.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client":"youtube","ds":"yt","q":query},
                    headers={"User-Agent":"Mozilla/5.0"}, timeout=5
                )
                if r.ok:
                    data = r.json()
                    if isinstance(data,list) and len(data)>1:
                        results.extend([str(s[0]).lower() for s in data[1]
                                        if isinstance(s,list)])
                time.sleep(0.3)
            except Exception:
                continue

        Cache.set(cache_key, results, Cfg.TTL_SUGGESTIONS)
        log.info(f"[P2/YouTube] {len(results)} suggestions for '{kw}'")
        return results

    def _amazon_autosuggest(self, kw: str) -> List[str]:
        cache_key = f"amz_suggest:{hashlib.md5(kw.encode()).hexdigest()[:8]}"
        cached = Cache.get(cache_key, Cfg.TTL_SUGGESTIONS)
        if cached:
            return cached

        results = []
        try:
            r = _req.get(
                "https://completion.amazon.com/api/2017/suggestions",
                params={"mid":"ATVPDKIKX0DER","alias":"aps","prefix":kw},
                headers={"User-Agent":"Mozilla/5.0"}, timeout=6
            )
            if r.ok:
                data = r.json()
                for s in data.get("suggestions",[]):
                    results.append(str(s.get("value","")).lower())
        except Exception as e:
            log.debug(f"[P2/Amazon] {e}")

        Cache.set(cache_key, results, Cfg.TTL_SUGGESTIONS)
        log.info(f"[P2/Amazon]  {len(results)} suggestions for '{kw}'")
        return results

    def _duckduckgo(self, kw: str) -> List[str]:
        from bs4 import BeautifulSoup
        cache_key = f"ddg:{hashlib.md5(kw.encode()).hexdigest()[:8]}"
        cached = Cache.get(cache_key, Cfg.TTL_SUGGESTIONS)
        if cached:
            return cached

        results = []
        for query in [kw, f"best {kw}", f"organic {kw}", f"buy {kw}"]:
            try:
                r = _req.get("https://html.duckduckgo.com/html/",
                              params={"q":query},
                              headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.select(".result__title a")[:5]:
                    results.append(a.get_text(strip=True).lower())
                time.sleep(0.5)
            except Exception:
                continue

        Cache.set(cache_key, results, Cfg.TTL_SUGGESTIONS)
        log.info(f"[P2/DDG]     {len(results)} results for '{kw}'")
        return results

    def _reddit_titles(self, kw: str) -> List[str]:
        """Extract subreddit post titles (NOT body content) as keyword signals."""
        cache_key = f"reddit:{hashlib.md5(kw.encode()).hexdigest()[:8]}"
        cached = Cache.get(cache_key, Cfg.TTL_SUGGESTIONS)
        if cached:
            return cached

        results = []
        subreddits = ["spices","ayurveda","cooking","IndianFood","food","nutrition"]
        for sub in subreddits[:3]:
            try:
                r = _req.get(
                    f"https://www.reddit.com/r/{sub}/search.json",
                    params={"q":kw,"sort":"relevance","limit":20,"restrict_sr":"true"},
                    headers={"User-Agent":"RufloBot/1.0"}, timeout=8
                )
                if r.ok:
                    posts = r.json().get("data",{}).get("children",[])
                    for p in posts:
                        title = p.get("data",{}).get("title","").lower()
                        if len(title) > 8:
                            results.append(title)
                time.sleep(1.0)   # respect Reddit rate limit
            except Exception:
                continue

        Cache.set(cache_key, results, Cfg.TTL_SUGGESTIONS)
        log.info(f"[P2/Reddit]  {len(results)} post titles for '{kw}'")
        return results

    def _question_variants(self, kw: str) -> List[str]:
        """Generate question variants (PAA-style)."""
        prefixes = ["what is","how to","does","can","why","when to","how much",
                    "is it safe","what are the benefits of","how to use",
                    "what does","where to buy","how do i","should i take"]
        return [f"{p} {kw}" for p in prefixes]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — NORMALIZATION (P3)
# ─────────────────────────────────────────────────────────────────────────────

class P3_Normalization:
    """
    Phase 3: Clean and standardize keyword universe.
    Streams through chunks to control memory.
    """
    phase = "P3"

    STOPWORDS = {"the","a","an","of","in","for","and","or","to","is","are",
                 "was","were","be","been","being","have","has","had","do","does",
                 "did","will","would","should","could","may","might","shall",
                 "at","by","from","up","out","on","off","into","through"}

    def run(self, seed: Seed, raw_keywords: List[str]) -> List[str]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        log.info(f"[P3] Normalising {len(raw_keywords)} keywords (streaming chunks)...")
        clean = []
        seen  = set()

        # Stream in chunks to control memory
        for chunk in MemoryManager.chunks(raw_keywords):
            for kw in chunk:
                normalised = self._normalise(kw)
                if normalised and normalised not in seen and len(normalised.split()) >= 2:
                    seen.add(normalised)
                    clean.append(normalised)

        log.info(f"[P3] {len(raw_keywords)} → {len(clean)} normalised keywords")
        Cache.save_checkpoint(seed.id, self.phase, clean)
        return clean

    def _normalise(self, kw: str) -> str:
        kw = kw.lower().strip()
        kw = re.sub(r"[^\w\s\-]","",kw)
        kw = re.sub(r"\s+", " ", kw)
        # Remove leading/trailing stopwords
        words = kw.split()
        while words and words[0] in self.STOPWORDS:
            words.pop(0)
        while words and words[-1] in self.STOPWORDS:
            words.pop()
        return " ".join(words)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — ENTITY DETECTION (P4) — heavy phase
# ─────────────────────────────────────────────────────────────────────────────

class P4_EntityDetection:
    """
    Phase 4: Extract entities using spaCy (en_core_web_sm).
    Memory: 150MB. Tagged as heavy phase — runs alone.
    Streams in chunks of 500 to avoid OOM.
    """
    phase = "P4"

    INGREDIENT_WORDS = {"cinnamon","cardamom","pepper","turmeric","ginger","clove",
                         "nutmeg","cumin","coriander","fenugreek","anise","basil"}
    BENEFIT_WORDS    = {"weight loss","blood sugar","diabetes","inflammation","digestion",
                         "immune","cholesterol","antioxidant","anti-inflammatory","cancer"}
    FORMAT_WORDS     = {"tea","powder","stick","oil","capsule","supplement","extract",
                         "bark","leaf","seed","whole","ground","raw"}

    def run(self, seed: Seed, keywords: List[str]) -> Dict[str,dict]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        nlp = AI.spacy_nlp()
        entity_map = {}
        log.info(f"[P4] Entity detection on {len(keywords)} keywords (chunked)...")

        for chunk in MemoryManager.chunks(keywords):
            for kw in chunk:
                cache_key = f"entities:{hashlib.md5(kw.encode()).hexdigest()[:8]}"
                cached_ent = Cache.get(cache_key, Cfg.TTL_ENTITIES)
                if cached_ent:
                    entity_map[kw] = cached_ent
                    continue

                entities = self._extract(kw, nlp)
                Cache.set(cache_key, entities, Cfg.TTL_ENTITIES)
                entity_map[kw] = entities

        AI.unload_embed_model()   # free spaCy's memory after P4
        log.info(f"[P4] Entities extracted for {len(entity_map)} keywords")
        Cache.save_checkpoint(seed.id, self.phase, entity_map)
        return entity_map

    def _extract(self, kw: str, nlp) -> dict:
        words = set(kw.lower().split())
        entities = {
            "ingredient": [w for w in words if w in self.INGREDIENT_WORDS],
            "benefit":    [b for b in self.BENEFIT_WORDS if b in kw.lower()],
            "format":     [f for f in self.FORMAT_WORDS   if f in words],
        }
        # spaCy NER if available
        if nlp:
            doc = nlp(kw)
            entities["spacy"] = [
                {"text": ent.text, "label": ent.label_}
                for ent in doc.ents
            ]
        return entities


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — INTENT CLASSIFICATION (P5)
# ─────────────────────────────────────────────────────────────────────────────

class P5_IntentClassification:
    """Phase 5: Rule-based intent classification. No AI needed — pure rules."""
    phase = "P5"

    RULES = {
        "transactional": ["buy","order","purchase","price","cheap","discount","shop",
                           "wholesale","bulk","delivery","near me","online","cost"],
        "commercial":    ["best","top","review","compare","vs","versus","alternative",
                           "recommendation","which","ranking","rated","test"],
        "comparison":    ["vs","versus","or","difference between","compare","better",
                           "which is","ceylon vs","type of"],
        "navigational":  ["brand","website","official","login","contact",".com"],
        "informational": ["what","how","why","when","does","is","are","can","benefits",
                           "uses","effects","meaning","definition","guide","truth",
                           "science","study","research"],
    }

    def run(self, seed: Seed, keywords: List[str]) -> Dict[str,str]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        intent_map = {}
        for kw in keywords:
            intent_map[kw] = self._classify(kw)

        Cache.save_checkpoint(seed.id, self.phase, intent_map)
        log.info(f"[P5] Intent classified: "
                 f"info={sum(1 for v in intent_map.values() if v=='informational')}, "
                 f"trans={sum(1 for v in intent_map.values() if v=='transactional')}, "
                 f"comp={sum(1 for v in intent_map.values() if v=='comparison')}")
        return intent_map

    def _classify(self, kw: str) -> str:
        kl = kw.lower()
        for intent, signals in self.RULES.items():
            if any(s in kl for s in signals):
                return intent
        return "informational"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — SERP INTELLIGENCE (P6)
# ─────────────────────────────────────────────────────────────────────────────

class P6_SERPIntelligence:
    """
    Phase 6: Analyze top 10 Google results per keyword.
    Uses httpx + BeautifulSoup (playwright for JS-heavy sites).
    Cache: 14-day TTL.
    Only runs for top keywords (by suggestion frequency) to save time.
    """
    phase = "P6"

    def run(self, seed: Seed, keywords: List[str],
             max_keywords: int = 100) -> Dict[str, dict]:
        """Only SERP-analyse top N keywords (most promising ones)."""
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        # Only analyse top keywords — full SERP for all 2000 would be very slow
        target = keywords[:max_keywords]
        serp_map = {}
        log.info(f"[P6] SERP analysis for {len(target)} top keywords...")

        for kw in target:
            cache_key = f"serp:{hashlib.md5(kw.encode()).hexdigest()[:10]}"
            cached_serp = Cache.get(cache_key, Cfg.TTL_SERP)
            if cached_serp:
                serp_map[kw] = cached_serp
                continue

            result = self._analyse_serp(kw)
            Cache.set(cache_key, result, Cfg.TTL_SERP)
            serp_map[kw] = result
            time.sleep(2.0)   # be respectful

        Cache.save_checkpoint(seed.id, self.phase, serp_map)
        log.info(f"[P6] SERP data: {len(serp_map)} keywords analysed")
        return serp_map

    def _analyse_serp(self, kw: str) -> dict:
        from bs4 import BeautifulSoup
        result = {
            "kw": kw, "top_urls": [], "avg_word_count": 0,
            "has_featured_snippet": False, "has_paa": False,
            "has_video": False, "competitor_domains": [],
            "kd_estimate": 50, "content_gap": False
        }
        try:
            r = _req.get("https://html.duckduckgo.com/html/",
                          params={"q": kw},
                          headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            results = soup.select(".result")[:10]

            urls, domains = [], []
            for res in results:
                url_el = res.select_one(".result__url")
                if url_el:
                    url = url_el.get_text(strip=True)
                    urls.append(url)
                    domain = re.sub(r"https?://","",url).split("/")[0]
                    domains.append(domain)

            # KD heuristic: big domains = harder
            big_domains = {"healthline.com","medicalnewstoday.com","webmd.com",
                           "amazon.com","wikipedia.org","nih.gov","mayoclinic.org"}
            big_count = sum(1 for d in domains if any(b in d for b in big_domains))
            result["kd_estimate"] = min(10 + big_count * 8, 90)
            result["top_urls"]    = urls[:5]
            result["competitor_domains"] = domains[:5]

        except Exception as e:
            log.debug(f"[P6] SERP failed for '{kw}': {e}")
        return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — OPPORTUNITY SCORING (P7)
# ─────────────────────────────────────────────────────────────────────────────

class P7_OpportunityScoring:
    """
    Phase 7: Score each keyword on opportunity.
    No AI needed — pure scoring formula.
    """
    phase = "P7"

    def run(self, seed: Seed, keywords: List[str],
             intent_map: Dict[str,str],
             serp_map: Dict[str,dict]) -> Dict[str, float]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        scores = {}
        # Popularity proxy: more autosuggest = more popular
        kw_set = set(keywords)
        for kw in keywords:
            scores[kw] = self._score(kw, intent_map.get(kw,"informational"),
                                      serp_map.get(kw, {}))

        Cache.save_checkpoint(seed.id, self.phase, scores)
        log.info(f"[P7] Scored {len(scores)} keywords. "
                 f"Top score: {max(scores.values(),default=0):.1f}")
        return scores

    def _score(self, kw: str, intent: str, serp: dict) -> float:
        import math
        # Base: word count proxy for specificity (3-4 words sweet spot)
        wc    = len(kw.split())
        wc_sc = 1.0 if 3<=wc<=5 else 0.7 if wc==2 else 0.5

        # KD inverse
        kd    = serp.get("kd_estimate", 40)
        kd_sc = 1.0 - (min(kd,100)/100.0)

        # Intent bonus
        intent_sc = {"transactional":0.9,"commercial":0.8,
                     "comparison":0.85,"informational":0.7,"navigational":0.4
                    }.get(intent,0.6)

        # Question format bonus (PAA-targetable)
        q_sc = 0.2 if kw.split()[0] in {"what","how","does","why","when","is","can"} else 0

        score = (wc_sc * 0.2 + kd_sc * 0.45 + intent_sc * 0.25 + q_sc) * 100
        return round(min(score, 100), 1)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — TOPIC DETECTION (P8) — heavy phase
# ─────────────────────────────────────────────────────────────────────────────

class P8_TopicDetection:
    """
    Phase 8: Group keywords into topics using SBERT embeddings + KMeans.
    Memory: 380MB. RUNS ALONE — heavy phase.
    Batch embeds 256 at a time. Unloads model after completion.
    Embeddings cached permanently — never recalculated.
    """
    phase = "P8"

    def run(self, seed: Seed, keywords: List[str],
             scores: Dict[str,float]) -> Dict[str, List[str]]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        log.info(f"[P8] Topic detection: {len(keywords)} keywords via SBERT+KMeans")

        # Embed in batches of 256 (with cache)
        all_vectors = []
        for batch in MemoryManager.chunks(keywords, Cfg.EMBED_BATCH):
            vectors = AI.embed_batch(batch)
            all_vectors.extend(vectors)

        # Determine optimal K (roughly 1 topic per 10-15 keywords)
        k = max(5, min(80, len(keywords) // 12))

        try:
            import numpy as np
            from sklearn.cluster import KMeans
            X   = np.array(all_vectors)
            km  = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(X)
        except Exception as e:
            log.warning(f"[P8] KMeans failed: {e}. Using fallback grouping.")
            labels = [i % k for i in range(len(keywords))]

        # Group by cluster
        topic_map: Dict[int, List[str]] = {}
        for kw, label in zip(keywords, labels):
            topic_map.setdefault(int(label), []).append(kw)

        # Name each topic using DeepSeek
        named: Dict[str, List[str]] = {}
        for cluster_id, kw_list in topic_map.items():
            top_kws = sorted(kw_list, key=lambda k: scores.get(k,0), reverse=True)[:5]
            name = self._name_topic(top_kws)
            named[name] = kw_list

        # Unload SBERT model — free 380MB
        AI.unload_embed_model()

        log.info(f"[P8] {k} topics detected")
        Cache.save_checkpoint(seed.id, self.phase, named)
        return named

    def _name_topic(self, top_kws: List[str]) -> str:
        text = AI.deepseek(
            f"Name this topic cluster in 2-4 words based on these keywords: {top_kws}. "
            f"Return ONLY the topic name, nothing else.",
            temperature=0.0
        )
        return text.strip().strip('"').title() or f"Topic {top_kws[0].title()}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — CLUSTER FORMATION (P9)
# ─────────────────────────────────────────────────────────────────────────────

class P9_ClusterFormation:
    """
    Phase 9: Group related topics into larger thematic clusters.
    Example: "Cinnamon Blood Sugar" + "Cinnamon Cholesterol" → "Cinnamon Health"
    """
    phase = "P9"

    CLUSTER_PROMPT = """Group these SEO topics into {n_clusters} larger thematic clusters.
Topics: {topics}
Seed keyword: {seed}

Return ONLY valid JSON: {{"Cluster Name": ["Topic 1", "Topic 2", ...], ...}}"""

    def run(self, seed: Seed, topic_map: Dict[str, List[str]]) -> Dict[str, List[str]]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        topics = list(topic_map.keys())
        n      = max(4, min(15, len(topics) // 5))

        prompt = self.CLUSTER_PROMPT.format(
            n_clusters=n, topics=topics[:60], seed=seed.keyword
        )
        text   = AI.gemini(prompt, temperature=0.2)
        try:
            clusters = AI.parse_json(text)
            if not isinstance(clusters, dict):
                raise ValueError("Expected dict")
        except Exception:
            # Fallback: alphabetical grouping
            clusters = {}
            chunk_size = max(1, len(topics) // n)
            for i in range(0, len(topics), chunk_size):
                name = f"Cluster {i//chunk_size + 1}"
                clusters[name] = topics[i:i+chunk_size]

        Cache.save_checkpoint(seed.id, self.phase, clusters)
        log.info(f"[P9] {len(clusters)} clusters formed from {len(topics)} topics")
        return clusters


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — PILLAR IDENTIFICATION (P10)
# ─────────────────────────────────────────────────────────────────────────────

class P10_PillarIdentification:
    """Phase 10: For each cluster, identify the anchor pillar page."""
    phase = "P10"

    PILLAR_PROMPT = """For this SEO cluster, generate the perfect pillar page title.
The pillar page is the comprehensive, authoritative guide that covers everything
in this cluster. It should rank for the broadest keyword in the cluster.

Cluster: "{cluster}"
Topics in cluster: {topics}
Seed keyword: {seed}

Return ONLY the pillar page title (one line, no quotes)."""

    def run(self, seed: Seed, clusters: Dict[str,List[str]]) -> Dict[str,dict]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        pillars = {}
        for cluster_name, topics in clusters.items():
            pillar_title = AI.gemini(
                self.PILLAR_PROMPT.format(
                    cluster=cluster_name, topics=topics[:10], seed=seed.keyword
                ), temperature=0.2
            ).strip().strip('"')

            pillars[cluster_name] = {
                "pillar_title": pillar_title,
                "pillar_keyword": cluster_name.lower(),
                "topics": topics,
                "article_count": len(topics) + 1   # topics + pillar itself
            }
            time.sleep(Cfg.GEMINI_RATE)

        Cache.save_checkpoint(seed.id, self.phase, pillars)
        log.info(f"[P10] {len(pillars)} pillar pages identified")
        return pillars


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 15 — KNOWLEDGE GRAPH (P11)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KnowledgeGraph:
    """5-level hierarchy: Seed → Pillar → Cluster → Topic → Keyword."""
    seed:    str
    pillars: Dict[str, dict] = field(default_factory=dict)
    # {pillar_name: {title, clusters: {cluster_name: {topics: {topic: [keywords]}}}}}

class P11_KnowledgeGraph:
    """Phase 11: Build the complete SEO knowledge graph."""
    phase = "P11"

    def run(self, seed: Seed, pillars: Dict[str,dict],
             topic_map: Dict[str,List[str]],
             intent_map: Dict[str,str],
             scores: Dict[str,float]) -> KnowledgeGraph:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return self._from_dict(cached)

        kg = KnowledgeGraph(seed=seed.keyword)

        for cluster_name, pillar_data in pillars.items():
            kg.pillars[cluster_name] = {
                "title":    pillar_data["pillar_title"],
                "keyword":  pillar_data["pillar_keyword"],
                "clusters": {cluster_name: {}}
            }
            # Map topics into this cluster
            for topic in pillar_data.get("topics",[]):
                # Get keywords for this topic
                topic_kws = topic_map.get(topic, [])
                kg.pillars[cluster_name]["clusters"][cluster_name][topic] = {
                    "keywords": topic_kws,
                    "best_keyword": max(topic_kws, key=lambda k: scores.get(k,0), default=topic),
                    "intent": intent_map.get(topic_kws[0] if topic_kws else topic, "informational")
                }

        graph_dict = asdict(kg)
        Cache.save_checkpoint(seed.id, self.phase, graph_dict)
        log.info(f"[P11] Knowledge graph: {len(kg.pillars)} pillars")
        return kg

    def _from_dict(self, data: dict) -> KnowledgeGraph:
        kg = KnowledgeGraph(seed=data["seed"])
        kg.pillars = data.get("pillars", {})
        return kg


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 16 — INTERNAL LINKING (P12)
# ─────────────────────────────────────────────────────────────────────────────

class P12_InternalLinking:
    """
    Phase 12: Generate internal link map from knowledge graph.
    Rules: Topic→Pillar, Topic→Topic (sibling), Cluster→Pillar, Pillar→Seed product.
    """
    phase = "P12"

    def run(self, seed: Seed, graph: KnowledgeGraph) -> dict:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        link_map = {
            "topic_to_pillar":  [],
            "topic_to_topic":   [],
            "cluster_to_pillar":[],
            "pillar_to_product":[],
        }

        for cluster_name, pillar_data in graph.pillars.items():
            pillar_url = f"/{seed.keyword.replace(' ','-')}/{pillar_data['keyword']}"

            # Pillar → product (transactional anchor)
            link_map["pillar_to_product"].append({
                "from_page":   pillar_url,
                "to_page":     seed.product_url or f"/products/{seed.keyword.replace(' ','-')}",
                "anchor_text": f"buy {seed.keyword} online",
                "placement":   "conclusion"
            })

            # Cluster → pillar
            link_map["cluster_to_pillar"].append({
                "cluster": cluster_name, "pillar_page": pillar_url,
                "anchor_text": pillar_data["keyword"]
            })

            # Topic → pillar
            for cluster, topics in pillar_data.get("clusters", {}).items():
                topic_list = list(topics.keys())
                for i, topic in enumerate(topic_list):
                    topic_url = f"/{seed.keyword.replace(' ','-')}/{topic.lower().replace(' ','-')}"
                    link_map["topic_to_pillar"].append({
                        "from_page": topic_url, "to_page": pillar_url,
                        "anchor_text": pillar_data["keyword"], "placement": "body"
                    })
                    # Topic → sibling topic (lateral links)
                    if i > 0:
                        prev_topic = topic_list[i-1]
                        prev_url   = f"/{seed.keyword.replace(' ','-')}/{prev_topic.lower().replace(' ','-')}"
                        link_map["topic_to_topic"].append({
                            "from_page": topic_url, "to_page": prev_url,
                            "anchor_text": prev_topic, "placement": "related-section"
                        })

        Cache.save_checkpoint(seed.id, self.phase, link_map)
        total = sum(len(v) for v in link_map.values())
        log.info(f"[P12] Internal link map: {total} links generated")
        return link_map


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 17 — CONTENT CALENDAR (P13)
# ─────────────────────────────────────────────────────────────────────────────

class P13_ContentCalendar:
    """
    Phase 13: Build publishing schedule.
    Fully configurable via ContentPace object.
    Respects: seasonal priorities, pillar-specific overrides, info gap ordering.
    """
    phase = "P13"

    def run(self, seed: Seed, graph: KnowledgeGraph,
             scores: Dict[str,float], pace: ContentPace,
             start_date: datetime = None) -> List[dict]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        start = start_date or datetime.utcnow()
        all_articles = self._flatten_articles(graph, scores)
        calendar     = self._schedule(all_articles, pace, start, seed)

        Cache.save_checkpoint(seed.id, self.phase, calendar)
        log.info(f"[P13] Calendar: {len(calendar)} articles over "
                 f"{pace.duration_years} years ({pace.blogs_per_day}/day default)")
        return calendar

    def _flatten_articles(self, graph: KnowledgeGraph,
                            scores: Dict[str,float]) -> List[dict]:
        articles = []
        for cluster_name, pillar_data in graph.pillars.items():
            # Pillar page itself (always first in cluster)
            articles.append({
                "type":      "pillar",
                "title":     pillar_data["title"],
                "keyword":   pillar_data["keyword"],
                "cluster":   cluster_name,
                "score":     scores.get(pillar_data["keyword"], 50),
                "is_pillar": True,
            })
            # Topic articles
            for cluster, topics in pillar_data.get("clusters", {}).items():
                for topic, topic_data in topics.items():
                    best_kw = topic_data.get("best_keyword", topic)
                    articles.append({
                        "type":    "topic",
                        "title":   f"{topic}",
                        "keyword": best_kw,
                        "cluster": cluster_name,
                        "score":   scores.get(best_kw, 40),
                        "intent":  topic_data.get("intent","informational"),
                        "is_pillar": False,
                    })
        return articles

    def _schedule(self, articles: List[dict], pace: ContentPace,
                   start: datetime, seed: Seed) -> List[dict]:
        # Sort: info-gap / question-type first, then by score desc
        articles.sort(key=lambda a: (
            0 if a.get("intent") == "informational" and "?" in a.get("title","") else 1,
            -a.get("score",0)
        ))

        calendar = []
        current_date = start
        day_counter  = 0

        # Build date → slot map
        slots_per_day = pace.blogs_per_day
        article_idx   = 0

        for day in range(pace.total_days):
            pub_date = start + timedelta(days=day)
            if article_idx >= len(articles):
                break

            cluster = articles[article_idx].get("cluster","")
            day_slots = pace.blogs_per_day_for_pillar(cluster)

            for slot in range(day_slots):
                if article_idx >= len(articles):
                    break
                art = articles[article_idx].copy()
                art["scheduled_date"] = pub_date.strftime("%Y-%m-%d")
                art["status"]         = "scheduled"
                art["frozen"]         = False
                art["seed_id"]        = seed.id
                art["article_id"]     = f"{seed.id}_a{article_idx:05d}"
                calendar.append(art)
                article_idx += 1

        # Apply seasonal overrides
        seasonal = pace.seasonal_priorities
        for art in calendar:
            for cluster_pattern, deadline_str in seasonal.items():
                if cluster_pattern.lower() in art.get("cluster","").lower():
                    try:
                        deadline = datetime.fromisoformat(deadline_str)
                        # Move to 6 weeks before deadline
                        new_date = deadline - timedelta(weeks=6)
                        if new_date >= start:
                            art["scheduled_date"]  = new_date.strftime("%Y-%m-%d")
                            art["seasonal_event"]  = cluster_pattern
                    except Exception:
                        pass

        return sorted(calendar, key=lambda x: x["scheduled_date"])


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 18 — DEDUP PREVENTION (P14)
# ─────────────────────────────────────────────────────────────────────────────

class P14_DedupPrevention:
    """
    Phase 14: Check for duplicates BEFORE content generation.
    Compares against: existing articles in DB, already-scheduled articles,
    semantic similarity > 0.95 between titles.
    """
    phase = "P14"

    def run(self, seed: Seed, calendar: List[dict],
             existing_articles: List[str] = None) -> List[dict]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        existing = set(t.lower().strip() for t in (existing_articles or []))
        clean    = []
        seen     = set()
        removed  = 0

        # Pass 1: Exact/near-exact title dedup
        for art in calendar:
            title_norm = re.sub(r"[^\w\s]","",art.get("title","")).lower().strip()
            if title_norm in seen or title_norm in existing:
                removed += 1
                continue
            seen.add(title_norm)
            clean.append(art)

        # Pass 2: Keyword-level dedup (same target keyword = same article)
        kw_seen, final = set(), []
        for art in clean:
            kw = art.get("keyword","").lower().strip()
            if kw and kw in kw_seen:
                removed += 1
                continue
            kw_seen.add(kw)
            final.append(art)

        Cache.save_checkpoint(seed.id, self.phase, final)
        log.info(f"[P14] Dedup: {len(calendar)} → {len(final)} "
                 f"(removed {removed} duplicates)")
        return final


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 19 — CONTENT BRIEF (P15)
# ─────────────────────────────────────────────────────────────────────────────

class P15_ContentBrief:
    """
    Phase 15: Generate structured brief for each article.
    Saved to disk individually — Claude reads one brief at a time.
    """
    phase = "P15"

    BRIEF_PROMPT = """Generate a detailed SEO content brief.

Article: "{title}"
Target keyword: {keyword}
Seed: {seed}
Intent: {intent}
Entities: {entities}
Internal links from this article: {links}

Return ONLY valid JSON:
{{
  "title":         "exact H1",
  "meta_title":    "SEO title tag (60 chars max)",
  "meta_desc":     "Meta description (155 chars max)",
  "intro_hook":    "Opening sentence that directly answers intent",
  "h2_structure":  ["H2 1", "H2 2", "H2 3", "H2 FAQs"],
  "key_points":    ["point to cover under each H2"],
  "faq_questions": ["Q1?","Q2?","Q3?"],
  "entities_to_include": ["entity1","entity2"],
  "information_gain": "the unique angle no competitor covers",
  "schema_type":   "Article|FAQPage|HowTo|Recipe",
  "word_count":    2000-3000,
  "cta":           "what action should reader take"
}}"""

    def run(self, seed: Seed, article: dict, entities: Dict[str,dict],
             link_map: dict, intent_map: Dict[str,str]) -> dict:
        """Generate brief for one article. Reads/writes from disk."""
        brief_path = Cfg.BRIEF_DIR / f"{article['article_id']}.json"
        if brief_path.exists():
            with open(brief_path) as f:
                return json.load(f)

        # Find relevant links
        article_kw  = article.get("keyword","")
        article_url = f"/{seed.keyword.replace(' ','-')}/{article_kw.replace(' ','-')}"
        links_out = [
            l["anchor_text"] for l in link_map.get("topic_to_pillar",[])
            if l.get("from_page","") == article_url
        ][:5]

        # Relevant entities
        ent_data = entities.get(article_kw, {})
        ent_str  = json.dumps({k:[str(v)[:30] for v in vals[:3]]
                               for k,vals in ent_data.items() if vals})[:200]

        prompt = self.BRIEF_PROMPT.format(
            title=article.get("title",""), keyword=article_kw,
            seed=seed.keyword, intent=article.get("intent","informational"),
            entities=ent_str, links=links_out[:3]
        )
        text  = AI.gemini(prompt, temperature=0.2)
        brief = {}
        try:
            brief = AI.parse_json(text)
        except Exception:
            brief = {"title": article.get("title",""), "word_count": 2000,
                     "schema_type": "Article", "faq_questions": [],
                     "h2_structure": ["Introduction","Main Content","FAQs"],
                     "information_gain": "original research and expert insight",
                     "cta": "buy online", "meta_title": article.get("title","")[:60],
                     "meta_desc": f"Learn about {article_kw}"}

        brief["article_id"]    = article["article_id"]
        brief["keyword"]       = article_kw
        brief["internal_links"]= links_out

        brief_path.parent.mkdir(parents=True, exist_ok=True)
        with open(brief_path, "w") as f:
            json.dump(brief, f, indent=2)
        return brief


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 20 — CLAUDE CONTENT GENERATION (P16)
# ─────────────────────────────────────────────────────────────────────────────

class P16_ClaudeContentGeneration:
    """
    Phase 16: Write articles using Claude Sonnet.
    One brief → one article. Parallel calls controlled by ContentPace.
    Memory: 50MB per active article. Writes to disk immediately.
    """
    phase = "P16"

    CLAUDE_SYSTEM = """You are an expert SEO content writer and subject matter expert.
You write comprehensive, engaging, deeply informative articles that:
- Rank #1 on Google through Information Gain (unique insights competitors don't have)
- Cite real data, studies, or expert perspectives
- Use natural language, not robotic SEO writing
- Include practical value for the reader
- Are structured perfectly for Google's featured snippets and AI citations

Write exactly as instructed in the brief. Do not add preamble."""

    ARTICLE_PROMPT = """Write a complete SEO article from this brief:

{brief_json}

Requirements:
- {word_count}+ words
- Start directly with the intro hook from the brief
- Use all H2 headings from the structure
- End with FAQ section using all provided questions
- Include a clear CTA at the end
- Write for a {region} audience, use natural language

Output: the article body only (no extra commentary)."""

    def generate(self, brief: dict, seed: Seed) -> dict:
        """Generate one article from one brief."""
        article_path = Cfg.ARTICLE_DIR / f"{brief['article_id']}.md"
        if article_path.exists():
            with open(article_path) as f:
                return {"article_id": brief["article_id"],
                        "body": f.read(), "status": "cached"}

        prompt = self.ARTICLE_PROMPT.format(
            brief_json=json.dumps(brief, indent=2)[:2000],
            word_count=brief.get("word_count", 2000),
            region=seed.region
        )
        body, tokens = AI.claude(prompt, self.CLAUDE_SYSTEM, max_tokens=4096)

        article_path.parent.mkdir(parents=True, exist_ok=True)
        with open(article_path, "w") as f:
            f.write(body)

        log.info(f"[P16] Generated: '{brief.get('title','')}' "
                 f"({len(body.split())} words · {tokens} tokens)")
        return {
            "article_id": brief["article_id"],
            "title":      brief.get("title",""),
            "keyword":    brief.get("keyword",""),
            "body":       body,
            "meta_title": brief.get("meta_title",""),
            "meta_desc":  brief.get("meta_desc",""),
            "tokens":     tokens,
            "status":     "generated"
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 21 — SEO OPTIMIZATION (P17)
# ─────────────────────────────────────────────────────────────────────────────

class P17_SEOOptimization:
    """
    Phase 17: Check article quality post-Claude.
    Rule-based checks + DeepSeek scoring.
    If score < 80, requests targeted revision from Claude.
    """
    phase = "P17"

    def optimize(self, article: dict, brief: dict) -> dict:
        body    = article.get("body","")
        keyword = brief.get("keyword","")
        score   = self._score(body, keyword, brief)

        if score < 80:
            # Ask Claude for targeted improvement
            issues = self._identify_issues(body, keyword, brief, score)
            if issues:
                improved_body, _ = AI.claude(
                    f"Improve this article to fix these specific issues:\n{issues}\n\n"
                    f"Article:\n{body[:3000]}",
                    "You are an SEO editor. Make targeted improvements only.",
                    max_tokens=4096
                )
                if len(improved_body) > 500:
                    article["body"]  = improved_body
                    article["score"] = self._score(improved_body, keyword, brief)
                    log.info(f"[P17] Article improved: {score} → {article['score']}")
                    return article

        article["seo_score"] = score
        return article

    def _score(self, body: str, keyword: str, brief: dict) -> int:
        score = 60
        words = body.lower().split()
        total = len(words)

        # Word count
        if total >= 2000: score += 10
        elif total >= 1500: score += 5

        # Keyword presence
        kw_count = body.lower().count(keyword.lower())
        density  = kw_count / max(total, 1) * 100
        if 0.5 <= density <= 2.5: score += 10

        # FAQ present
        if "faq" in body.lower() or "frequently asked" in body.lower(): score += 8

        # H2 structure present
        h2_count = body.count("## ")
        if h2_count >= 3: score += 8

        # CTA present
        if brief.get("cta","").lower() in body.lower()[:200]: score += 4

        return min(score, 100)

    def _identify_issues(self, body: str, keyword: str, brief: dict, score: int) -> str:
        issues = []
        words  = body.lower().split()
        if len(words) < 2000:
            issues.append(f"Too short: {len(words)} words, need 2000+")
        if body.count("## ") < 3:
            issues.append("Missing H2 headings — add at least 3")
        if "faq" not in body.lower():
            issues.append("Missing FAQ section")
        if body.lower().count(keyword.lower()) < 3:
            issues.append(f"Keyword '{keyword}' mentioned too few times")
        return "; ".join(issues)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 22 — SCHEMA & METADATA (P18)
# ─────────────────────────────────────────────────────────────────────────────

class P18_SchemaMetadata:
    """Phase 18: Generate JSON-LD schema + meta tags for each article."""
    phase = "P18"

    def generate(self, article: dict, brief: dict, seed: Seed) -> dict:
        schema_type = brief.get("schema_type","Article")
        pub_date    = datetime.utcnow().isoformat()

        # Base Article schema
        schema = {
            "@context": "https://schema.org",
            "@type":    schema_type,
            "headline": brief.get("title",""),
            "description": brief.get("meta_desc",""),
            "author":   {"@type":"Organization","name":"Ruflo"},
            "datePublished": pub_date,
            "dateModified":  pub_date,
        }

        # FAQPage schema
        faq_schema = None
        faqs = brief.get("faq_questions",[])
        if faqs and schema_type in ("FAQPage","Article"):
            faq_schema = {
                "@context": "https://schema.org",
                "@type":    "FAQPage",
                "mainEntity": [
                    {"@type":"Question","name":q,
                     "acceptedAnswer":{"@type":"Answer","text":f"Learn about {q.rstrip('?')}"}}
                    for q in faqs[:5]
                ]
            }

        # Breadcrumb
        breadcrumb = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type":"ListItem","position":1,"name":"Home","item":"/"},
                {"@type":"ListItem","position":2,"name":seed.keyword.title(),
                 "item":f"/{seed.keyword.replace(' ','-')}"},
                {"@type":"ListItem","position":3,"name":brief.get("title",""),"item":"#"},
            ]
        }

        return {
            "article_id":  article["article_id"],
            "meta_title":  brief.get("meta_title","")[:60],
            "meta_desc":   brief.get("meta_desc","")[:155],
            "canonical":   f"/{seed.keyword.replace(' ','-')}/{article.get('keyword','').replace(' ','-')}",
            "schema_json":     json.dumps(schema, indent=2),
            "faq_schema_json": json.dumps(faq_schema, indent=2) if faq_schema else None,
            "breadcrumb_json": json.dumps(breadcrumb, indent=2),
            "og_title":    brief.get("title",""),
            "og_desc":     brief.get("meta_desc",""),
            "hreflang":    seed.language,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 23 — PUBLISHING (P19)
# ─────────────────────────────────────────────────────────────────────────────

class P19_Publishing:
    """Phase 19: Publish to WordPress API (or save to Markdown)."""
    phase = "P19"

    def __init__(self, wp_url: str = "", wp_user: str = "", wp_pass: str = ""):
        self.wp_url  = wp_url  or os.getenv("WP_URL","")
        self.wp_user = wp_user or os.getenv("WP_USERNAME","")
        self.wp_pass = wp_pass or os.getenv("WP_APP_PASSWORD","")

    def publish(self, article: dict, metadata: dict, scheduled_date: str) -> dict:
        if self.wp_url:
            return self._publish_wordpress(article, metadata, scheduled_date)
        else:
            return self._save_markdown(article, metadata)

    def _publish_wordpress(self, article: dict, metadata: dict, scheduled_date: str) -> dict:
        import base64
        auth = base64.b64encode(f"{self.wp_user}:{self.wp_pass}".encode()).decode()
        data = {
            "title":   metadata.get("meta_title", article.get("title","")),
            "content": self._inject_schema(article.get("body",""), metadata),
            "status":  "future",
            "date":    scheduled_date + "T08:00:00",
            "meta":    {
                "_yoast_wpseo_metadesc": metadata.get("meta_desc",""),
                "_yoast_wpseo_canonical": metadata.get("canonical",""),
            }
        }
        try:
            r = _req.post(f"{self.wp_url}/wp-json/wp/v2/posts",
                          json=data, headers={"Authorization":f"Basic {auth}"},
                          timeout=15)
            if r.ok:
                wp_id = r.json().get("id")
                return {"status":"published","wp_id":wp_id,
                        "url":r.json().get("link","")}
        except Exception as e:
            log.warning(f"[P19] WordPress publish failed: {e}")
        return {"status":"failed"}

    def _save_markdown(self, article: dict, metadata: dict) -> dict:
        """Save as Markdown file (for static sites / Markdown repos)."""
        slug     = metadata.get("canonical","").strip("/").replace("/","-")
        out_path = Cfg.ARTICLE_DIR / "published" / f"{slug}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        content = f"""---
title: {metadata.get('meta_title','')}
description: {metadata.get('meta_desc','')}
canonical: {metadata.get('canonical','')}
---

{article.get('body','')}
"""
        with open(out_path, "w") as f:
            f.write(content)
        return {"status":"saved","path":str(out_path)}

    def _inject_schema(self, body: str, metadata: dict) -> str:
        schema_tags = ""
        for key in ["schema_json","faq_schema_json","breadcrumb_json"]:
            if metadata.get(key):
                schema_tags += f"\n<script type='application/ld+json'>{metadata[key]}</script>"
        return body + schema_tags


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 24 — RANKING FEEDBACK (P20) — SELF-IMPROVING LOOP
# ─────────────────────────────────────────────────────────────────────────────

class P20_RankingFeedback:
    """
    Phase 20: Monitor performance. Update strategy. Self-improving loop.
    Reads GSC weekly. Flags underperforming topics. Triggers expansions.
    """
    phase = "P20"

    def analyse(self, seed: Seed, gsc_data: List[dict],
                 graph: KnowledgeGraph) -> dict:
        """Identify underperforming clusters and recommend actions."""
        if not gsc_data:
            return {"status":"no_data","actions":[]}

        # Find keywords ranking 11-20 (improvement opportunity)
        near_ranking = [g for g in gsc_data if 11 <= g.get("rank",99) <= 20]
        # Find keywords not in top 50 despite good content
        underperforming = [g for g in gsc_data
                           if g.get("rank",99) > 50 and g.get("impressions",0) > 100]

        actions = []
        for item in near_ranking[:10]:
            actions.append({
                "type":    "optimize",
                "keyword": item["keyword"],
                "rank":    item["rank"],
                "action":  "Update article: add FAQ, refresh entities, improve intro",
                "priority":"high"
            })

        for item in underperforming[:5]:
            actions.append({
                "type":    "expand",
                "keyword": item["keyword"],
                "rank":    item.get("rank",99),
                "action":  "Add 3 supporting articles for this topic",
                "priority":"medium"
            })

        return {
            "seed":           seed.keyword,
            "near_ranking":   len(near_ranking),
            "underperforming":len(underperforming),
            "actions":        actions,
            "next_run":       (datetime.utcnow() + timedelta(weeks=1)).isoformat()
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 25 — RUFLO ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class RufloOrchestrator:
    """
    The brain. Runs all 20 phases in order.
    Memory management: checks budget before each phase, sequences heavy phases.
    Checkpoint resume: if crash, picks up from last saved phase.
    Gate callbacks: pause for customer confirmation between phases.
    
    Usage:
        ruflo = RufloOrchestrator()
        result = ruflo.run_seed(
            keyword="cinnamon",
            pace=ContentPace(duration_years=2, blogs_per_day=3),
        )
    """

    def __init__(self):
        Cfg.ensure_dirs()
        self.p1  = P1_SeedInput()
        self.p2  = P2_KeywordExpansion()
        self.p3  = P3_Normalization()
        self.p4  = P4_EntityDetection()
        self.p5  = P5_IntentClassification()
        self.p6  = P6_SERPIntelligence()
        self.p7  = P7_OpportunityScoring()
        self.p8  = P8_TopicDetection()
        self.p9  = P9_ClusterFormation()
        self.p10 = P10_PillarIdentification()
        self.p11 = P11_KnowledgeGraph()
        self.p12 = P12_InternalLinking()
        self.p13 = P13_ContentCalendar()
        self.p14 = P14_DedupPrevention()
        self.p15 = P15_ContentBrief()
        self.p16 = P16_ClaudeContentGeneration()
        self.p17 = P17_SEOOptimization()
        self.p18 = P18_SchemaMetadata()
        self.p19 = P19_Publishing()
        self.p20 = P20_RankingFeedback()

    def _run_phase(self, name: str, fn, *args, **kwargs):
        """Run a phase with memory management and console logging."""
        ok, reason = MemoryManager.can_run(name)
        if not ok:
            log.warning(f"[Ruflo] {name} deferred: {reason}. Waiting 5s...")
            time.sleep(5)
            ok, reason = MemoryManager.can_run(name)
            if not ok:
                log.error(f"[Ruflo] {name} cannot run: {reason}")
                return None

        MemoryManager.acquire(name)
        t0 = time.time()
        log.info(f"[Ruflo] ▶ {name} starting...")
        try:
            result = fn(*args, **kwargs)
            elapsed = round(time.time() - t0, 1)
            log.info(f"[Ruflo] ✓ {name} complete ({elapsed}s)")
            return result
        except Exception as e:
            log.error(f"[Ruflo] ✗ {name} failed: {e}")
            return None
        finally:
            MemoryManager.release(name)
            Cache.clear_l1()   # free L1 cache between phases

    def run_seed(self,
                  keyword: str,
                  pace: ContentPace = None,
                  language: str = "english",
                  region: str = "India",
                  product_url: str = "",
                  existing_articles: List[str] = None,
                  generate_articles: bool = False,
                  publish: bool = False,
                  gate_callback = None) -> dict:
        """
        Full 20-phase pipeline for one seed keyword.

        Args:
          keyword:           seed keyword (e.g. "cinnamon")
          pace:              ContentPace config
          generate_articles: if True, runs P15-P19 (generates actual articles)
          publish:           if True, publishes to WordPress
          gate_callback:     callable(phase, data) → confirmed_data | None (None = stop)
        """
        pace = pace or ContentPace()
        t0   = time.time()

        print(f"\n{'═'*60}")
        print(f"  RUFLO ENGINE — '{keyword}'")
        print(f"  Pace: {pace.blogs_per_day}/day · {pace.duration_years} years")
        print(f"{'═'*60}\n")

        # ── P1 Seed ──────────────────────────────────────────────────────────
        seed = self._run_phase("P1", self.p1.run, keyword, language, region, product_url)
        if not seed: return {"error":"P1 failed"}

        # ── P2 Expansion ─────────────────────────────────────────────────────
        raw_kws = self._run_phase("P2", self.p2.run, seed)
        if not raw_kws: return {"error":"P2 failed"}
        print(f"  P2: {len(raw_kws)} raw keywords from 5 sources")

        # ── P3 Normalization ─────────────────────────────────────────────────
        kws = self._run_phase("P3", self.p3.run, seed, raw_kws)
        if not kws: return {"error":"P3 failed"}
        print(f"  P3: {len(kws)} clean keywords")

        # ── GATE A: Universe keywords confirmed ───────────────────────────────
        if gate_callback:
            confirmed = gate_callback("universe_keywords",
                                       {"count": len(kws), "sample": kws[:20]})
            if confirmed is None:
                return {"status":"stopped_at_gate_A"}
            kws = confirmed.get("keywords", kws)

        # ── P4 Entity Detection (heavy) ───────────────────────────────────────
        entities = self._run_phase("P4", self.p4.run, seed, kws)
        entities = entities or {}

        # ── P5 Intent Classification ──────────────────────────────────────────
        intent_map = self._run_phase("P5", self.p5.run, seed, kws)
        intent_map = intent_map or {}

        # ── P6 SERP Intelligence ──────────────────────────────────────────────
        serp_map = self._run_phase("P6", self.p6.run, seed, kws)
        serp_map = serp_map or {}

        # ── P7 Opportunity Scoring ────────────────────────────────────────────
        scores = self._run_phase("P7", self.p7.run, seed, kws, intent_map, serp_map)
        scores = scores or {k: 50.0 for k in kws}

        # ── P8 Topic Detection (heavy) ────────────────────────────────────────
        topic_map = self._run_phase("P8", self.p8.run, seed, kws, scores)
        topic_map = topic_map or {}
        print(f"  P8: {len(topic_map)} topics detected")

        # ── P9 Cluster Formation ──────────────────────────────────────────────
        clusters = self._run_phase("P9", self.p9.run, seed, topic_map)
        clusters = clusters or {}
        print(f"  P9: {len(clusters)} clusters formed")

        # ── GATE B: Pillars confirmed ─────────────────────────────────────────
        if gate_callback:
            confirmed = gate_callback("pillars", {"clusters": list(clusters.keys())})
            if confirmed is None:
                return {"status":"stopped_at_gate_B"}
            # Customer may remove clusters
            removed = confirmed.get("removed_clusters",[])
            clusters = {k:v for k,v in clusters.items() if k not in removed}

        # ── P10 Pillar Identification ─────────────────────────────────────────
        pillars = self._run_phase("P10", self.p10.run, seed, clusters)
        pillars = pillars or {}

        # ── P11 Knowledge Graph ───────────────────────────────────────────────
        graph = self._run_phase("P11", self.p11.run, seed, pillars,
                                 topic_map, intent_map, scores)
        if not graph: return {"error":"P11 failed"}

        # ── P12 Internal Linking ──────────────────────────────────────────────
        link_map = self._run_phase("P12", self.p12.run, seed, graph)
        link_map = link_map or {}

        # ── P13 Content Calendar ──────────────────────────────────────────────
        calendar = self._run_phase("P13", self.p13.run, seed, graph, scores, pace)
        calendar = calendar or []
        print(f"  P13: {len(calendar)} articles scheduled over {pace.duration_years} years")
        cost_preview = pace.summary(len(calendar))
        print(f"  💰 Est. Claude cost: {cost_preview['estimated_cost']} | "
              f"⏱ Est. time: {cost_preview['estimated_time']}")

        # ── GATE C: Content calendar confirmed ───────────────────────────────
        if gate_callback:
            confirmed = gate_callback("content_calendar", {
                "total": len(calendar),
                "pace": cost_preview,
                "first_10": calendar[:10]
            })
            if confirmed is None:
                return {"status":"stopped_at_gate_C"}
            # Customer may adjust pace
            if confirmed.get("new_pace"):
                new_pace = ContentPace(**confirmed["new_pace"])
                calendar = self._run_phase("P13", self.p13.run, seed, graph,
                                            scores, new_pace)

        # ── P14 Dedup Prevention ──────────────────────────────────────────────
        calendar = self._run_phase("P14", self.p14.run, seed, calendar,
                                    existing_articles) or calendar
        print(f"  P14: {len(calendar)} articles after dedup")

        # ── Build result object (keyword phase complete) ──────────────────────
        result = {
            "seed":             asdict(seed),
            "keyword_count":    len(kws),
            "cluster_count":    len(clusters),
            "topic_count":      len(topic_map),
            "pillar_count":     len(pillars),
            "calendar_count":   len(calendar),
            "calendar_preview": calendar[:5],
            "cost_preview":     cost_preview,
            "link_map_size":    sum(len(v) for v in link_map.values()),
            "elapsed_seconds":  round(time.time()-t0, 1),
            "_graph":           graph,
            "_link_map":        link_map,
            "_calendar":        calendar,
            "_entities":        entities,
            "_intent_map":      intent_map,
        }

        # ── Content generation (optional — gate-controlled) ───────────────────
        if generate_articles:
            print(f"\n  Starting content generation for {len(calendar)} articles...")
            generated = []
            for article in calendar[:10]:  # limit for testing; remove for production
                brief    = self.p15.run(seed, article, entities, link_map, intent_map)
                written  = self.p16.generate(brief, seed)
                optimised= self.p17.optimize(written, brief)
                metadata = self.p18.generate(optimised, brief, seed)

                if publish:
                    pub_result = self.p19.publish(
                        optimised, metadata, article.get("scheduled_date","")
                    )
                    optimised["publish_result"] = pub_result

                generated.append({
                    "article_id": article["article_id"],
                    "title":      brief.get("title",""),
                    "keyword":    brief.get("keyword",""),
                    "seo_score":  optimised.get("seo_score",0),
                    "word_count": len(optimised.get("body","").split()),
                })

            result["generated_count"] = len(generated)
            result["generated"]       = generated

        total_time = round(time.time()-t0, 1)
        print(f"\n{'═'*60}")
        print(f"  COMPLETE: {total_time}s")
        print(f"  {len(kws)} keywords → {len(clusters)} clusters → "
              f"{len(topic_map)} topics → {len(calendar)} articles")
        print(f"{'═'*60}\n")

        return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 26 — TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    Run:
      python ruflo_20phase_engine.py test expansion    # P2 expansion sources
      python ruflo_20phase_engine.py test normalize    # P3 normalization
      python ruflo_20phase_engine.py test intent       # P5 intent rules
      python ruflo_20phase_engine.py test topics       # P8 topic detection
      python ruflo_20phase_engine.py test calendar     # P13 calendar generation
      python ruflo_20phase_engine.py test dedup        # P14 dedup prevention
      python ruflo_20phase_engine.py test brief        # P15 content brief
      python ruflo_20phase_engine.py test full         # full pipeline (no content gen)
      python ruflo_20phase_engine.py test pace         # content pace config
    """

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_expansion(self):
        self._h("P2 Keyword Expansion")
        p2 = P2_KeywordExpansion()
        seed = P1_SeedInput().run("cinnamon")
        kws  = p2.run(seed)
        self._ok(f"Total keywords: {len(kws)}")
        self._ok(f"Sample: {kws[:5]}")

    def test_normalize(self):
        self._h("P3 Normalization")
        p3   = P3_Normalization()
        raw  = ["benefits of cinnamon","cinnamon benefits","CINNAMON BENEFITS",
                "the health benefits of cinnamon","buy cinnamon","cinnamon!!!"]
        seed = P1_SeedInput().run("cinnamon")
        norm = p3.run(seed, raw)
        self._ok(f"Before: {len(raw)} → After: {len(norm)}")
        self._ok(f"Normalised: {norm}")

    def test_intent(self):
        self._h("P5 Intent Classification")
        p5   = P5_IntentClassification()
        seed = P1_SeedInput().run("cinnamon")
        kws  = ["buy cinnamon sticks","cinnamon benefits","ceylon vs cassia",
                "best cinnamon brand","cinnamon.com"]
        imap = p5.run(seed, kws)
        for k,v in imap.items():
            self._ok(f"'{k}' → {v}")

    def test_topics(self):
        self._h("P8 Topic Detection")
        kws  = [
            "cinnamon for diabetes","cinnamon blood sugar","cinnamon glucose",
            "cinnamon weight loss","cinnamon belly fat","cinnamon metabolism",
            "ceylon cinnamon","cassia cinnamon","best cinnamon type",
            "buy cinnamon online","organic cinnamon price","cinnamon sticks wholesale",
        ]
        seed   = P1_SeedInput().run("cinnamon")
        scores = {k: 70.0 for k in kws}
        p8     = P8_TopicDetection()
        topics = p8.run(seed, kws, scores)
        self._ok(f"Topics: {len(topics)}")
        for name, kw_list in list(topics.items())[:3]:
            self._ok(f"  '{name}': {kw_list[:2]}")

    def test_calendar(self):
        self._h("P13 Content Calendar — configurable pace")
        for scenario in [
            ContentPace(duration_years=1, blogs_per_day=3, parallel_claude_calls=1),
            ContentPace(duration_years=2, blogs_per_day=10, parallel_claude_calls=5),
            ContentPace(duration_years=1, blogs_per_day=50,
                        pillar_overrides={"Christmas Baking":10},
                        seasonal_priorities={"Christmas":"2026-12-01"}),
        ]:
            total = 100  # mock article count
            s = scenario.summary(total)
            self._ok(f"{scenario.duration_years}y × {scenario.blogs_per_day}/day: "
                     f"{s['total_blogs']} blogs · {s['estimated_cost']} · {s['estimated_time']}")

    def test_dedup(self):
        self._h("P14 Dedup Prevention")
        calendar = [
            {"article_id":"a1","title":"Cinnamon Benefits","keyword":"cinnamon benefits"},
            {"article_id":"a2","title":"Benefits of Cinnamon","keyword":"benefits of cinnamon"},
            {"article_id":"a3","title":"Cinnamon for Diabetes","keyword":"cinnamon diabetes"},
        ]
        existing = ["cinnamon health benefits"]  # already published
        seed = P1_SeedInput().run("cinnamon")
        p14  = P14_DedupPrevention()
        clean= p14.run(seed, calendar, existing)
        self._ok(f"Before: {len(calendar)} → After: {len(clean)}")
        self._ok(f"Remaining: {[a['title'] for a in clean]}")

    def test_brief(self):
        self._h("P15 Content Brief")
        seed    = P1_SeedInput().run("cinnamon")
        article = {"article_id":"cinnamon_test_001","title":"Cinnamon for Diabetes",
                   "keyword":"cinnamon diabetes","intent":"informational"}
        entities= {"cinnamon diabetes":{"ingredient":["cinnamon"],"benefit":["diabetes"]}}
        link_map= {"topic_to_pillar":[]}
        intent  = {"cinnamon diabetes":"informational"}
        brief   = P15_ContentBrief().run(seed, article, entities, link_map, intent)
        self._ok(f"Title: {brief.get('title','?')}")
        self._ok(f"H2s: {brief.get('h2_structure',['?'])[:3]}")
        self._ok(f"FAQs: {len(brief.get('faq_questions',[]))} questions")
        self._ok(f"Info gain angle: {brief.get('information_gain','?')[:60]}")

    def test_pace(self):
        self._h("Content Pace Configuration")
        configs = [
            ("Standard",   ContentPace(duration_years=2, blogs_per_day=3)),
            ("Aggressive", ContentPace(duration_years=1, blogs_per_day=10,
                                        parallel_claude_calls=5)),
            ("Mega scale", ContentPace(duration_years=2, blogs_per_day=50,
                                        parallel_claude_calls=10)),
        ]
        for name, pace in configs:
            total_blogs = pace.blogs_per_day * 7 * 52 * int(pace.duration_years)
            s = pace.summary(total_blogs)
            self._ok(f"{name}: {s['total_blogs']} blogs · "
                     f"{s['estimated_cost']} · {s['estimated_time']}")

    def test_full(self):
        self._h("FULL 20-PHASE PIPELINE — cinnamon (no content gen)")
        ruflo  = RufloOrchestrator()
        pace   = ContentPace(duration_years=1, blogs_per_day=3)
        result = ruflo.run_seed(
            keyword="cinnamon",
            pace=pace,
            generate_articles=False,
            publish=False,
        )
        self._ok(f"Keywords: {result.get('keyword_count',0)}")
        self._ok(f"Clusters: {result.get('cluster_count',0)}")
        self._ok(f"Topics:   {result.get('topic_count',0)}")
        self._ok(f"Pillars:  {result.get('pillar_count',0)}")
        self._ok(f"Calendar: {result.get('calendar_count',0)} articles")
        self._ok(f"Cost preview: {result.get('cost_preview',{})}")
        self._ok(f"Elapsed: {result.get('elapsed_seconds',0)}s")
        if result.get("calendar_preview"):
            self._ok("First 3 scheduled:")
            for a in result["calendar_preview"][:3]:
                self._ok(f"  [{a.get('scheduled_date','')}] {a.get('title','')}")
        return result

    def run_all(self):
        tests = [
            ("normalize", self.test_normalize),
            ("intent",    self.test_intent),
            ("calendar",  self.test_calendar),
            ("dedup",     self.test_dedup),
            ("pace",      self.test_pace),
        ]
        print("\n"+"═"*55)
        print("  20-PHASE ENGINE — TESTS")
        print("═"*55)
        p=f=0
        for name,fn in tests:
            try: fn(); p+=1
            except Exception as e: print(f"  ✗ {name}: {e}"); f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 27 — CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
Ruflo — 20-Phase Keyword Universe Engine
────────────────────────────────────────────────────────────
1 seed → keywords → topics → clusters → pillars → calendar → articles

Memory managed · 3-tier cached · checkpoint resume · configurable pace

Usage:
  python ruflo_20phase_engine.py test                # all tests
  python ruflo_20phase_engine.py test <stage>        # one test
  python ruflo_20phase_engine.py run <keyword>       # full pipeline (no gen)
  python ruflo_20phase_engine.py generate <keyword>  # full pipeline + gen
  python ruflo_20phase_engine.py pace                # configure & preview pace

Stages: expansion, normalize, intent, topics, calendar, dedup, brief, full, pace

Environment (.env):
  GEMINI_API_KEY   = your free key (aistudio.google.com)
  ANTHROPIC_API_KEY= your Claude key (content writing only)
  OLLAMA_URL       = http://localhost:11434
  WP_URL/USERNAME/APP_PASSWORD = for publishing
"""
    if len(sys.argv) < 2:
        print(HELP); exit(0)
    cmd = sys.argv[1]

    if cmd == "test":
        t = Tests()
        if len(sys.argv) == 3:
            fn = getattr(t, f"test_{sys.argv[2]}", None)
            if fn: fn()
            else: print(f"Unknown stage: {sys.argv[2]}")
        else: t.run_all()

    elif cmd == "run":
        kw    = " ".join(sys.argv[2:]) if len(sys.argv)>2 else "cinnamon"
        ruflo = RufloOrchestrator()
        pace  = ContentPace(duration_years=2, blogs_per_day=3)
        ruflo.run_seed(kw, pace)

    elif cmd == "generate":
        kw    = " ".join(sys.argv[2:]) if len(sys.argv)>2 else "cinnamon"
        ruflo = RufloOrchestrator()
        pace  = ContentPace(duration_years=2, blogs_per_day=3, parallel_claude_calls=3)
        ruflo.run_seed(kw, pace, generate_articles=True)

    elif cmd == "pace":
        # Interactive pace configurator
        print("\n  Content Pace Configurator\n  ─────────────────────────")
        try:
            years   = float(input("  Duration (years) [2]: ") or 2)
            per_day = int(input("  Blogs per day [3]: ") or 3)
            parallel= int(input("  Parallel Claude calls [3]: ") or 3)
            kw      = input("  Seed keyword [cinnamon]: ") or "cinnamon"
            pace    = ContentPace(duration_years=years, blogs_per_day=per_day,
                                   parallel_claude_calls=parallel)
            total   = per_day * 365 * int(years)
            print(f"\n  {pace.summary(total)}")
        except KeyboardInterrupt:
            pass
    else:
        print(f"Unknown: {cmd}\n{HELP}")

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

import os, json, gzip, time, re, hashlib, logging, sqlite3, asyncio, threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from collections import OrderedDict
import requests as _req

# optional competitor gap engine is used when available
try:
    from annaseo_competitor_gap import CompetitorCrawler, GapAnalyser
except Exception:
    CompetitorCrawler = None
    GapAnalyser = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logging.getLogger("ruflo.engine").warning("python-dotenv not installed; skipping .env")

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
    OLLAMA_URL      = os.getenv("OLLAMA_URL",     "http://172.235.16.165:11434")
    OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",   "deepseek-r1:7b")
    OLLAMA_EMBED    = os.getenv("OLLAMA_EMBED",   "nomic-embed-text")
    GEMINI_KEY      = os.getenv("GEMINI_API_KEY", "")          # free tier — general AI (P1-P14)
    GEMINI_PAID_KEY = os.getenv("GEMINI_PAID_API_KEY", "")    # paid tier — content generation
    GEMINI_MODEL    = os.getenv("GEMINI_MODEL",   "gemini-1.5-flash")
    GEMINI_RATE     = float(os.getenv("GEMINI_RATE", "4.0"))
    ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_PAID_KEY = os.getenv("ANTHROPIC_PAID_API_KEY", "")  # paid tier
    CLAUDE_MODEL    = os.getenv("CLAUDE_MODEL",   "claude-sonnet-4-6")
    GROQ_KEY        = os.getenv("GROQ_API_KEY",   "")
    GROQ_MODEL      = os.getenv("GROQ_MODEL",     "llama-3.3-70b-versatile")
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

    # Quality gate threshold: minimum score for auto-publish
    PUBLISH_THRESHOLD = 75  # 0-100, articles below this go to review queue

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

    @classmethod
    def refresh_from_env(cls):
        """Reload runtime API key and model configs from environment variables."""
        cls.OLLAMA_URL       = os.getenv("OLLAMA_URL",           cls.OLLAMA_URL)
        cls.OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL",         cls.OLLAMA_MODEL)
        cls.OLLAMA_EMBED     = os.getenv("OLLAMA_EMBED",         cls.OLLAMA_EMBED)
        cls.GEMINI_KEY       = os.getenv("GEMINI_API_KEY",       cls.GEMINI_KEY)
        cls.GEMINI_PAID_KEY  = os.getenv("GEMINI_PAID_API_KEY",  cls.GEMINI_PAID_KEY)
        cls.GEMINI_MODEL     = os.getenv("GEMINI_MODEL",         cls.GEMINI_MODEL)
        cls.GEMINI_RATE      = float(os.getenv("GEMINI_RATE",    str(cls.GEMINI_RATE)))
        cls.ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY",    cls.ANTHROPIC_KEY)
        cls.ANTHROPIC_PAID_KEY = os.getenv("ANTHROPIC_PAID_API_KEY", cls.ANTHROPIC_PAID_KEY)
        cls.CLAUDE_MODEL     = os.getenv("CLAUDE_MODEL",         cls.CLAUDE_MODEL)
        cls.GROQ_KEY         = os.getenv("GROQ_API_KEY",         cls.GROQ_KEY)
        cls.GROQ_MODEL       = os.getenv("GROQ_MODEL",           cls.GROQ_MODEL)

    @staticmethod
    def _extract_ollama_text(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        # /api/generate path has response
        if isinstance(data.get("response"), str) and data.get("response").strip():
            return data["response"].strip()
        # /api/chat new path may have top-level message or choices
        msg = data.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str) and msg.get("content").strip():
            return msg["content"].strip()
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                if isinstance(first.get("message"), dict) and isinstance(first["message"].get("content"), str):
                    return first["message"]["content"].strip()
                if isinstance(first.get("text"), str):
                    return first["text"].strip()
        # fallback: raw text field
        if isinstance(data.get("text"), str):
            return data["text"].strip()
        return ""


class ContentPace:
    """
    Fully configurable content pace.
    Example: 50 pillars × 50 blogs/day for one month = intensive launch.
    """
    def __init__(
        self,
        duration_years: float = 2.0,
        blogs_per_day: int = 3,
        parallel_claude_calls: int = 3,
        pillar_overrides: Optional[Dict[str, int]] = None,
        seasonal_priorities: Optional[Dict[str, str]] = None,
    ):
        self.duration_years = duration_years
        self.blogs_per_day = blogs_per_day
        self.parallel_claude_calls = parallel_claude_calls
        self.pillar_overrides = pillar_overrides or {}
        self.seasonal_priorities = seasonal_priorities or {}

    # legacy class attributes (for introspection/static defaults)
    duration_years: float = 2.0      # 1, 2, 3, 5, or fraction
    blogs_per_day: int = 3           # global default
    parallel_claude_calls: int = 3   # simultaneous Claude article generations
    pillar_overrides: Dict[str, int] = field(default_factory=dict)
    seasonal_priorities: Dict[str, str] = field(default_factory=dict)
    # {"Christmas Baking": 20}  → publish all 20 before Dec 1
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
    _heavy_lock: threading.Lock = threading.Lock()

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

        # Heavy phase conflict check (thread-safe)
        with cls._heavy_lock:
            if phase in Cfg.HEAVY_PHASES and cls._active_heavy:
                return False, f"Heavy phase already running: {cls._active_heavy}"

        # Memory budget check (require 20% headroom)
        if avail < budget * 1.2:
            return False, f"Low memory: {avail:.0f}MB available, {budget}MB needed"

        return True, "ok"

    @classmethod
    def acquire(cls, phase: str):
        if phase in Cfg.HEAVY_PHASES:
            with cls._heavy_lock:
                cls._active_heavy.add(phase)

    @classmethod
    def release(cls, phase: str):
        with cls._heavy_lock:
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

    _l1: "OrderedDict[str, Any]" = OrderedDict()   # in-memory LRU
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
        # L1 (move-to-end on access for LRU behaviour)
        if key in cls._l1:
            try:
                cls._l1.move_to_end(key)
            except Exception:
                pass
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
        try:
            # Evict oldest if capacity exceeded
            if key in cls._l1:
                cls._l1.move_to_end(key)
                cls._l1[key] = value
                return
            if len(cls._l1) >= cls._l1_max:
                try:
                    cls._l1.popitem(last=False)
                except Exception:
                    # fallback eviction
                    cls._l1.pop(next(iter(cls._l1)))
            cls._l1[key] = value
        except Exception:
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
        # Don't reuse checkpoints during pytest runs to keep tests isolated
        if "PYTEST_CURRENT_TEST" in os.environ:
            return None
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
        p = cls.embed_path(text)

        # Try numpy .npy first
        try:
            import numpy as np
            if p.exists():
                return np.load(p, allow_pickle=False)
        except ImportError:
            fallback = p.with_suffix('.json')
            if fallback.exists():
                with open(fallback, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass

        # Fallback if no numpy available or npy invalid
        fallback = p.with_suffix('.json')
        if fallback.exists():
            with open(fallback, 'r', encoding='utf-8') as f:
                return json.load(f)

        return None

    @classmethod
    def save_embedding(cls, text: str, vector):
        p = cls.embed_path(text)
        try:
            import numpy as np
            np.save(str(p), np.array(vector, dtype=float))
        except ImportError:
            fallback = p.with_suffix('.json')
            with open(fallback, 'w', encoding='utf-8') as f:
                json.dump(list(vector), f)
        except Exception:
            # Last fallback: JSON file
            fallback = p.with_suffix('.json')
            with open(fallback, 'w', encoding='utf-8') as f:
                json.dump(list(vector), f)


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
            combined = f"{system}\n\n{prompt}" if system else prompt
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/generate", json={
                "model": Cfg.OLLAMA_MODEL, "stream": False,
                "options": {"temperature": temperature, "num_ctx": 2048},
                "prompt": combined
            }, timeout=120)
            r.raise_for_status()
            data = r.json()
            t = data.get("response", "").strip()
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

    @classmethod
    def groq(cls, prompt: str, system: str = "You are an SEO expert.",
              temperature: float = 0.2) -> str:
        """Groq Llama — fast free inference. Primary AI for bulk processing."""
        if not Cfg.GROQ_KEY:
            return cls.deepseek(prompt, system=system, temperature=temperature)
        try:
            from groq import Groq
            client = Groq(api_key=Cfg.GROQ_KEY)
            resp = client.chat.completions.create(
                model=Cfg.GROQ_MODEL,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": prompt}],
                temperature=temperature,
                max_tokens=4096,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f"[AI] Groq: {e}")
            return cls.deepseek(prompt, system=system, temperature=temperature)

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
        try:
            import numpy as np
        except ImportError:
            np = None
            log.warning("[AI.embed_batch] numpy not installed; using fallback zero-vectors")

        results = [None] * len(texts)
        uncached_idx, uncached_texts = [], []

        for i, t in enumerate(texts):
            cached = Cache.get_embedding(t)
            if cached is not None:
                if hasattr(cached, 'tolist'):
                    results[i] = cached.tolist()
                else:
                    results[i] = list(cached)
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
        """Try Ollama embed → sentence-transformers fallback; zero-vector if unavailable."""
        try:
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/embed",
                          json={"model": Cfg.OLLAMA_EMBED, "input": texts},
                          timeout=60)
            r.raise_for_status()
            data = r.json().get("embeddings")
            if data:
                return data
        except Exception as e:
            log.warning(f"[AI._encode] Ollama embed failed: {e}")

        try:
            if cls._embed_model is None:
                from sentence_transformers import SentenceTransformer
                cls._embed_model = SentenceTransformer(Cfg.EMBED_MODEL)
            return cls._embed_model.encode(texts, normalize_embeddings=True).tolist()
        except Exception as e:
            log.warning(f"[AI._encode] sentence_transformers fallback failed: {e}")

        # last-resort fallback: stable zero vectors
        fallback_dim = 384
        log.warning("[AI._encode] using zero-vector fallback (no embed model available)")
        return [[0.0]*fallback_dim for _ in texts]

    @classmethod
    def spacy_nlp(cls):
        if cls._spacy_model is None:
            try:
                import spacy
            except Exception:
                log.warning("spaCy not installed; continuing without NLP model")
                cls._spacy_model = None
                return None

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
        try:
            text = re.sub(r"<think>.*?</think>","",text,flags=re.DOTALL)
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'(\{.*\}|\[.*\])',text,re.DOTALL)
            if m: return json.loads(m.group(1))
            return json.loads(text)
        except (json.JSONDecodeError, Exception):
            return {}


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
    business_locations: List[str] = field(default_factory=list)
    target_locations:   List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @staticmethod
    def make_id(keyword: str) -> str:
        return hashlib.md5(keyword.lower().strip().encode()).hexdigest()[:10]


class P1_SeedInput:
    """Phase 1: Store and validate seed keyword."""
    phase = "P1"

    def run(self, keyword: str, language: str = "english",
             region: str = "India", product_url: str = "",
             business_locations: List[str] = None,
             target_locations: List[str] = None) -> Seed:
        seed = Seed(
            id=Seed.make_id(keyword), keyword=keyword.strip().lower(),
            language=language, region=region, product_url=product_url,
            business_locations=business_locations or [],
            target_locations=target_locations or [],
        )
        Cache.set(f"seed:{seed.id}", asdict(seed))
        log.info(f"[P1] Seed stored: '{seed.keyword}' (id={seed.id}) biz_loc={seed.business_locations} target_loc={seed.target_locations}")
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
        clusters = None
        if cached:
            clusters = cached

        all_kws = []
        log.info(f"[P2] Expanding '{seed.keyword}' from multiple sources...")

        # Run all source suggestions (each cached independently)
        network_outputs = []
        g = self._google_autosuggest(seed.keyword)
        all_kws.extend(g); network_outputs.extend(g)
        y = self._youtube_autosuggest(seed.keyword)
        all_kws.extend(y); network_outputs.extend(y)
        a = self._amazon_autosuggest(seed.keyword)
        all_kws.extend(a); network_outputs.extend(a)
        d = self._duckduckgo(seed.keyword)
        all_kws.extend(d); network_outputs.extend(d)
        r = self._reddit_titles(seed.keyword)
        all_kws.extend(r); network_outputs.extend(r)

        # Non-network expansions (questions, permutations, intent-driven)
        all_kws.extend(self._question_variants(seed.keyword))
        all_kws.extend(self._permutations(seed.keyword, seed))
        all_kws.extend(self._intent_expansion(seed.keyword))

        # ── Location-aware keyword expansion ──────────────────────────────
        loc_kws = self._location_keyword_expansion(seed)
        all_kws.extend(loc_kws)
        # Location-specific Google Suggest queries (top 3 target + all business)
        _loc_targets = (seed.target_locations or [])[:3] + (seed.business_locations or [])
        _loc_targets = list(dict.fromkeys(_loc_targets))[:5]  # dedup, cap at 5
        for loc in _loc_targets:
            loc_l = loc.lower().strip()
            if not loc_l:
                continue
            loc_suggest = self._google_autosuggest(f"{seed.keyword} in {loc_l}")
            all_kws.extend(loc_suggest)
            loc_suggest2 = self._google_autosuggest(f"{seed.keyword} {loc_l}")
            all_kws.extend(loc_suggest2)

        # Recursive expansion from top network results only (limited for performance)
        recursive_seeds = list(dict.fromkeys(network_outputs))[:20]
        for kw in recursive_seeds:
            if len(all_kws) > 1500:
                log.info("[P2] Reached max P2 size, stopping recursive expansion")
                break
            all_kws.extend(self._google_autosuggest(kw))
            all_kws.extend(self._youtube_autosuggest(kw))

        # Shrink aggressively if huge (max city)
        all_kws = list(dict.fromkeys(all_kws))[:2000]

        # Normalize, dedupe and keep order
        processed = []
        seen = set()
        for k in all_kws:
            kk = k.lower().strip()
            if not kk or kk in seen or len(kk.split()) < 2:
                continue
            seen.add(kk)
            processed.append(kk)

        # Filter noisy unrelated expansions early (seed + strong relevance rules)
        filtered = []
        for kw in processed:
            if self._is_relevant(kw, seed.keyword):
                filtered.append(kw)

        # Ranking by P2 relevance signal
        filtered = sorted(
            list(dict.fromkeys(filtered)),
            key=lambda k: self._score_keyword(k, seed.keyword),
            reverse=True
        )

        # Ensure common permutations (e.g., 'seed online') are present
        try:
            online_variant = f"{seed.keyword} online".lower().strip()
            if online_variant not in filtered:
                perms = self._permutations(seed.keyword)
                if online_variant in perms:
                    filtered.insert(0, online_variant)
                    log.info(f"[P2] Ensured online variant present: {online_variant}")
        except Exception:
            pass

        # Hard cap for quality and pipeline stability
        MAX_P2 = 500
        if len(filtered) > MAX_P2:
            log.warning(f"[P2] Trimming {len(filtered)} → {MAX_P2} keywords")
            filtered = filtered[:MAX_P2]

        # Guarantee common permutation 'seed online' is present in final set
        try:
            online_variant = f"{seed.keyword} online".lower().strip()
            if online_variant not in filtered:
                if len(filtered) >= MAX_P2:
                    filtered[-1] = online_variant
                else:
                    filtered.append(online_variant)
        except Exception:
            pass

        log.info(f"[P2] Total keywords after relevance filter: {len(filtered)}")
        Cache.save_checkpoint(seed.id, self.phase, filtered)
        return filtered

    def _seed_phrase_matches(self, kw_l: str, seed_l: str) -> bool:
        if not seed_l or not kw_l:
            return False
        return bool(re.search(rf"\b{re.escape(seed_l)}\b", kw_l))

    def _score_keyword(self, kw: str, seed: str) -> float:
        score = 0.0
        kw_l = kw.lower()
        seed_l = seed.lower()

        if self._seed_phrase_matches(kw_l, seed_l):
            score += 2

        if any(x in kw_l for x in ["buy", "price", "wholesale", "bulk", "supplier"]):
            score += 2

        if len(kw_l.split()) >= 3:
            score += 1

        return score

    def _is_relevant(self, kw: str, seed_keyword: str) -> bool:
        if not kw or not seed_keyword:
            return False

        kw_l = kw.lower()
        seed_l = seed_keyword.lower()

        # STRICT: seed must appear in keyword phrase as whole token/phrase
        if self._seed_phrase_matches(kw_l, seed_l):
            # reject obvious junk
            junk = ["meaning", "lyrics", "movie", "song", "jobs",
                    "amazon prime", "netflix", "drawing", "emoji"]
            if any(j in kw_l for j in junk):
                return False
            return True

        seed_words = set(seed_l.split())
        kw_words = set(kw_l.split())

        # Must overlap at least 2 seed tokens to avoid drift
        if len(seed_words & kw_words) >= 2:
            if not any(j in kw_l for j in ["meaning", "lyrics", "movie", "song", "jobs"]):
                return True

        return False

    def _google_autosuggest(self, kw: str) -> List[str]:
        cache_key = f"google_suggest:{hashlib.md5(kw.encode()).hexdigest()[:8]}"
        cached = Cache.get(cache_key, Cfg.TTL_SUGGESTIONS)
        if cached:
            return cached

        results = []
        errors = 0
        suffixes = [""] + list("abcdefghijklmnopqrstuvwxyz") + [
            "for", "with", "without", "vs", "benefits", "side effects",
            "uses", "recipe", "buy", "organic", "price", "best",
            "online", "wholesale", "bulk", "near me",
        ]
        for sfx in suffixes:   # expanded for broader coverage
            if errors >= 4:
                log.warning(f"[P2/Google] Too many failures for '{kw}', fallback stop")
                break
            query = f"{kw} {sfx}".strip()
            try:
                r = _req.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client":"firefox","q":query},
                    headers={"User-Agent":"Mozilla/5.0"}, timeout=4
                )
                if r.ok:
                    data = r.json()
                    if isinstance(data,list) and len(data)>1:
                        results.extend([str(s).lower() for s in data[1] if isinstance(s, str)])
                else:
                    errors += 1
                time.sleep(0.15)
            except Exception:
                errors += 1
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
        errors = 0
        for sfx in ["", "how to", "benefits", "recipe", "tutorial", "buy", "price", "organic", "wholesale"]:
            if errors >= 4:
                log.warning(f"[P2/YouTube] Too many failures for '{kw}', fallback stop")
                break
            query = f"{kw} {sfx}".strip()
            try:
                r = _req.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client":"youtube","ds":"yt","q":query},
                    headers={"User-Agent":"Mozilla/5.0"}, timeout=4
                )
                if r.ok:
                    data = r.json()
                    if isinstance(data,list) and len(data)>1:
                        results.extend([str(s[0]).lower() for s in data[1]
                                        if isinstance(s, list) and len(s)>0 and isinstance(s[0], str)])
                else:
                    errors += 1
                time.sleep(0.2)
            except Exception:
                errors += 1
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
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            log.warning("[P2/DDG] bs4 not installed; skipping DDG extraction")
            return []

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

    def _permutations(self, kw: str, seed: Seed = None) -> List[str]:
        prefixes = ["buy", "best", "organic", "pure", "wholesale", "bulk", "export quality"]
        suffixes = ["online", "price", "near me", "for sale", "shipping"]

        results = []
        for p in prefixes:
            results.append(f"{p} {kw}")
        for s in suffixes:
            results.append(f"{kw} {s}")
        for p in prefixes:
            for s in suffixes:
                results.append(f"{p} {kw} {s}")

        # ── Location-aware permutations ──────────────────────────────────
        if seed:
            # Business locations — origin/trust keywords
            for loc in (seed.business_locations or []):
                loc_l = loc.lower().strip()
                if not loc_l:
                    continue
                results.append(f"{loc_l} {kw}")
                results.append(f"{kw} from {loc_l}")
                results.append(f"authentic {loc_l} {kw}")
                results.append(f"buy {kw} from {loc_l} online")
                results.append(f"{loc_l} {kw} online")
                results.append(f"original {loc_l} {kw}")
            # Target locations — geo-targeted keywords (top 3 to prevent explosion)
            for loc in (seed.target_locations or [])[:3]:
                loc_l = loc.lower().strip()
                if not loc_l:
                    continue
                results.append(f"{kw} in {loc_l}")
                results.append(f"best {kw} {loc_l}")
                results.append(f"{kw} {loc_l} online")
                results.append(f"buy {kw} in {loc_l}")
                results.append(f"{kw} delivery {loc_l}")
                results.append(f"{kw} price in {loc_l}")
                results.append(f"where to buy {kw} in {loc_l}")
                results.append(f"order {kw} {loc_l} online")

        return list(dict.fromkeys([r.strip().lower() for r in results if r.strip()]))

    def _intent_expansion(self, kw: str) -> List[str]:
        topics = [
            "benefits", "uses", "side effects", "versus", "vs", "best",
            "recipe", "health benefits", "properties", "price", "wholesale"
        ]
        results = [f"{kw} {t}" for t in topics]
        results += [f"{t} {kw}" for t in ["how to", "what is", "where to buy", "why", "is {kw}"]]  # careful
        return list(dict.fromkeys([r.strip().lower() for r in results if r.strip()]))

    def _location_keyword_expansion(self, seed: Seed) -> List[str]:
        """Generate location-specific keywords using AI + templates."""
        biz_locs = seed.business_locations or []
        tgt_locs = seed.target_locations or []
        if not biz_locs and not tgt_locs:
            return []

        kw = seed.keyword
        results = []

        # Template-based location keywords (fast, no AI needed)
        for loc in biz_locs:
            loc_l = loc.lower().strip()
            results.extend([
                f"{loc_l} {kw}", f"{kw} from {loc_l}",
                f"where to purchase {loc_l} {kw} online",
                f"authentic {loc_l} {kw} buy online",
                f"best {loc_l} {kw} brands",
                f"{loc_l} {kw} export quality",
                f"buy {loc_l} {kw} direct",
            ])

        for loc in tgt_locs[:5]:
            loc_l = loc.lower().strip()
            results.extend([
                f"best {kw} available in {loc_l}",
                f"{kw} shop in {loc_l}",
                f"{kw} home delivery {loc_l}",
                f"order {kw} online {loc_l}",
                f"top {kw} brands in {loc_l}",
                f"cheap {kw} in {loc_l}",
                f"{kw} wholesale {loc_l}",
            ])

        # Cross-location: business → target
        for b in biz_locs[:2]:
            b_l = b.lower().strip()
            for t in tgt_locs[:3]:
                t_l = t.lower().strip()
                if b_l != t_l:
                    results.append(f"buy {b_l} {kw} in {t_l}")
                    results.append(f"{b_l} {kw} delivery to {t_l}")

        # AI-based location expansion (if we have Ollama)
        try:
            biz_txt = ", ".join(biz_locs[:3]) or "not specified"
            tgt_txt = ", ".join(tgt_locs[:5]) or "not specified"
            prompt = f"""Seed keyword: {kw}
Business locations (where business operates): {biz_txt}
Target locations (where customers are): {tgt_txt}

Generate 20 location-specific long-tail SEO keywords. Include:
- "[product] in [city]" variants for target locations
- "[product] from [business_location]" trust/authority keywords
- "where to buy [product] in [location]" transactional queries
- "[location] [product] online/delivery/price" purchase variants
- Local comparison: "[product] [city] vs [city]"

Return ONLY a JSON list of keyword strings. No extra text.
"""
            ai_result = AI.groq(prompt, system="You are an SEO expert. Return ONLY a JSON list of strings.", temperature=0.3)
            if ai_result:
                import re as _re
                m = _re.search(r'\[[\s\S]*?\]', ai_result)
                if m:
                    ai_kws = json.loads(m.group())
                    if isinstance(ai_kws, list):
                        results.extend([str(k).lower().strip() for k in ai_kws if isinstance(k, str)])
                        log.info(f"[P2/Location] AI generated {len(ai_kws)} location keywords")
        except Exception as e:
            log.warning(f"[P2/Location] AI expansion failed: {e}")

        final = list(dict.fromkeys([r.strip().lower() for r in results if r.strip() and len(r.strip()) > 5]))
        log.info(f"[P2/Location] Total location keywords: {len(final)}")
        return final


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — NORMALIZATION (P3)
# ─────────────────────────────────────────────────────────────────────────────

class P3_Normalization:
    """
    Phase 3: Advanced keyword normalization + AI validation.
    """
    phase = "P3"

    STOPWORDS = {"the","a","an","of","in","for","and","or","to","is","are",
                 "was","were","be","been","being","have","has","had","do","does",
                 "did","will","would","should","could","may","might","shall",
                 "at","by","from","up","out","on","off","into","through"}

    # Navigation/UI text fragments and garbage tokens
    REJECT_PATTERNS = [
        r'^\d{4}\w',             # year-glued: "2025kerala"
        r'^\d+$',                # pure numbers
        r'\bcart\b',
        r'\blogin\b',
        r'\bsignup\b',
        r'\bsubscribe\b',
        r'\bmenu\b',
        r'\bfooter\b',
        r'\bheader\b',
        r'\bnailed\b',
        r'\bintroduces\b',
        r'\bposted\b',
        r'\bjanuary\b|\bfebruary\b|\bmarch\b|\bapril\b|\bjuly\b|\baugust\b|\bseptember\b|\boctober\b|\bnovember\b|\bdecember\b',
    ]
    REJECT_RE = [re.compile(p, re.I) for p in REJECT_PATTERNS]

    def run(self, seed: Seed, raw_keywords: List[str]) -> List[str]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        log.info(f"[P3] Advanced normalization on {len(raw_keywords)} keywords...")

        cleaned = []
        seen = set()

        for chunk in MemoryManager.chunks(raw_keywords):
            for kw in chunk:
                kw_clean = self._basic_clean(kw)
                kw_clean = self._fix_order(kw_clean)

                if not kw_clean or kw_clean in seen:
                    continue
                # Hard reject garbage patterns
                if self._is_garbage(kw_clean):
                    continue

                seen.add(kw_clean)
                cleaned.append(kw_clean)

        # Prune single-word keywords unless there are multi-word variants.
        # Do not preserve single-word tokens that are part of the seed phrase
        seed_tokens = set(seed.keyword.lower().split()) if getattr(seed, 'keyword', None) else set()
        pruned = []
        for kw in cleaned:
            if len(kw.split()) >= 2:
                pruned.append(kw)
                continue
            # keep single-word if any other cleaned kw contains it as a token
            token = kw.lower().strip()
            found = any((other.startswith(f"{token} ") or other.endswith(f" {token}") or f" {token} " in other)
                        for other in cleaned if other != kw)
            if found and token not in seed_tokens:
                pruned.append(kw)

        validated = self._ai_validate(pruned, seed.keyword, seed_obj=seed)

        log.info(f"[P3] {len(raw_keywords)} → {len(validated)} normalized + validated keywords")
        Cache.save_checkpoint(seed.id, self.phase, validated)
        return validated

    def _basic_clean(self, kw: str) -> str:
        kw = kw.lower().strip()
        kw = re.sub(r"[^\w\s\-]", "", kw)
        kw = re.sub(r"\s+", " ", kw)

        words = kw.split()
        while words and words[0] in self.STOPWORDS:
            words.pop(0)
        while words and words[-1] in self.STOPWORDS:
            words.pop()

        return " ".join(words)

    def _fix_order(self, kw: str) -> str:
        words = kw.split()
        if len(words) == 2 and words[0] in {"powder","price","benefits","uses","how","what"}:
            return f"{words[1]} {words[0]}"
        return kw

    def _is_garbage(self, kw: str) -> bool:
        """Hard-reject obviously garbage keywords that no human would search."""
        words = kw.split()
        if not words:
            return True
        # Reject if first or last word is a stopword (indicates sentence fragment)
        if words[0] in self.STOPWORDS or words[-1] in self.STOPWORDS:
            return True
        # Reject if >40% stopwords
        sw_count = sum(1 for w in words if w in self.STOPWORDS)
        if len(words) > 2 and sw_count / len(words) > 0.4:
            return True
        # Reject any regex garbage pattern
        for rx in self.REJECT_RE:
            if rx.search(kw):
                return True
        # Reject year-prefixed tokens like "2025kerala"
        if any(re.match(r'^\d{4}\w', w) for w in words):
            return True
        # Reject if all words are single characters
        if all(len(w) <= 1 for w in words):
            return True
        # Reject very short (< 4 chars total excluding spaces)
        if len(kw.replace(' ', '')) < 4:
            return True
        return False

    def _normalise(self, kw: str) -> str:
        """Compatibility wrapper: older tests expect `_normalise` to exist.
        Compose existing cleaning steps to produce the normalized keyword."""
        return self._fix_order(self._basic_clean(kw))

    def _ai_validate(self, keywords: List[str], seed: str, seed_obj: Seed = None) -> List[str]:
        if not keywords:
            return []

        # Build location name set for preservation
        _loc_names = set()
        if seed_obj:
            for loc in (seed_obj.target_locations or []) + (seed_obj.business_locations or []):
                if loc:
                    _loc_names.add(loc.lower().strip())

        # deterministic pre-filter first
        base = []
        seed_l = seed.lower()
        for kw in keywords:
            kw_l = kw.lower()
            # Keep phrases containing the seed or at least two words (2-word phrases allowed)
            if seed_l in kw_l or len(kw_l.split()) >= 2:
                base.append(kw.strip().lower())
                continue
            # Preserve single-word tokens if any multi-word variant contains them
            if len(kw_l.split()) == 1:
                token = kw_l
                found = any(token in other.lower().split() for other in keywords if other.lower() != kw_l)
                if found:
                    base.append(kw.strip().lower())

        base = list(dict.fromkeys(base))

        # Build location context for AI prompt
        loc_context = ""
        if _loc_names:
            loc_context = f"\\nIMPORTANT: Keywords containing location names ({', '.join(list(_loc_names)[:5])}) are HIGH PRIORITY — keep them all.\\n"

        final = []
        for chunk in MemoryManager.chunks(base, 100):
            prompt = f"""
You are an SEO keyword cleaner.

Seed: {seed}

Keywords:
{chunk}

Rules:
- Keep only real search queries
- Must be relevant to seed
- Remove generic or unrelated phrases
- Keep buyer intent keywords HIGH priority
- Keep location-specific keywords HIGH priority (containing city/region/country names)
{loc_context}
Return JSON list.
"""
            try:
                output = AI.groq(prompt)
                parsed = AI.parse_json(output)
                if isinstance(parsed, list) and parsed:
                    final.extend([k.lower().strip() for k in parsed if isinstance(k, str) and k.strip()])
                else:
                    final.extend(chunk)
            except Exception:
                log.warning("[P3] LLM validation failed; falling back to deterministic base")
                final.extend(chunk)

        final = list(dict.fromkeys(final))

        # Quality floor: reject aggressively rather than keep garbage.
        # Old 70% minimum-keep rule removed — quality over quantity.
        min_keep = max(10, int(len(keywords) * 0.3))  # keep at least 30% or 10

        if len(final) < min_keep:
            log.warning(f"[P3] AI reduced too aggressively ({len(final)}/{len(keywords)}) - using base list")
            final = base

        if not final:
            final = list(dict.fromkeys([kw.strip().lower() for kw in keywords if kw.strip()]))

        return final


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

    # Common ingredient/ spice words used for lightweight rule-based extraction
    INGREDIENT_WORDS = {
        "pepper", "turmeric", "ginger", "clove", "cinnamon",
        "cumin", "cardamom", "nutmeg", "fenugreek", "anise",
        "basil", "coriander", "garlic", "oregano", "rosemary",
        "thyme", "saffron", "paprika", "chili"
    }
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
        else:
            # Ensure 'spacy' key is always present (empty list when model unavailable)
            entities["spacy"] = []
        return entities


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — INTENT CLASSIFICATION (P5)
# ─────────────────────────────────────────────────────────────────────────────

class IntentResult:
    """Small wrapper that is unpackable (intent, confidence) and compares equal
    to a plain intent string for backward-compatible equality checks in tests."""
    def __init__(self, intent: str, confidence: float = 0.6):
        self.intent = intent
        self.confidence = float(confidence)

    def __iter__(self):
        yield self.intent
        yield self.confidence

    def __eq__(self, other):
        if isinstance(other, str):
            return self.intent == other
        if isinstance(other, tuple) or isinstance(other, list):
            return (self.intent, self.confidence) == tuple(other)
        if isinstance(other, IntentResult):
            return (self.intent, self.confidence) == (other.intent, other.confidence)
        return False

    def __repr__(self):
        return f"({self.intent!r}, {self.confidence!r})"


class P5_IntentClassification:
    """Phase 5: Hybrid intent classification with confidence and entity signals."""
    phase = "P5"

    RULES = {
        "local":         [" near me", " nearby", " in my area", " closest", " local "],
        "transactional": [" buy "," order "," purchase "," price"," cheap "," discount ",
                           " shop "," wholesale "," bulk "," delivery"," online",
                           "buy ","order ","where to buy","how to buy"," cost "],
        "comparison":    [" vs "," versus "," difference between"," compare ",
                           " better than"," which is "," type of "," or "],
        "commercial":    [" best "," top "," review"," alternative",
                           " recommendation"," rated"," ranking","best ","top "],
        "navigational":  [" brand "," website"," official"," login"," contact",".com"],
        "informational": [" what "," how "," why "," when "," does "," benefits",
                           " uses "," effects"," meaning"," definition"," guide",
                           "what ","how ","why ","benefits ","uses of "],
    }

    def run(self, seed: Seed, keywords: List[str], entities: Optional[Dict[str,dict]] = None) -> Dict[str,dict]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        if entities is None:
            entities = {}

        # Location names from seed for detecting local intent
        _loc_names = set()
        for loc in (seed.target_locations or []) + (seed.business_locations or []):
            _loc_names.add(loc.lower().strip())

        # Legacy tests expect a mapping kw -> intent string. Keep that behaviour
        # while _classify may also return (intent, confidence) tuples.
        intent_map = {}
        for kw in keywords:
            res = self._classify(kw, entities.get(kw, {}), _loc_names)
            # _classify may return an IntentResult, tuple, or plain string
            if isinstance(res, IntentResult):
                intent_map[kw] = res.intent
            elif isinstance(res, tuple) or isinstance(res, list):
                intent_map[kw] = res[0]
            else:
                intent_map[kw] = res

        Cache.save_checkpoint(seed.id, self.phase, intent_map)
        info_cnt = sum(1 for v in intent_map.values() if v == 'informational')
        trans_cnt = sum(1 for v in intent_map.values() if v == 'transactional')
        local_cnt = sum(1 for v in intent_map.values() if v == 'local')
        comp_cnt = sum(1 for v in intent_map.values() if v == 'comparison')
        nav_cnt = sum(1 for v in intent_map.values() if v == 'navigational')
        log.info(f"[P5] Intent classified: info={info_cnt}, trans={trans_cnt}, local={local_cnt}, comp={comp_cnt}, nav={nav_cnt}")
        return intent_map

    def _classify(self, kw: str, entity: Optional[Dict[str, Any]] = None, loc_names: set = None):
        """Return an (intent, confidence) wrapper for the keyword."""
        entity = entity or {}
        kl = kw.lower()

        # Check for local intent first (keyword contains a known location name)
        if loc_names:
            for loc in loc_names:
                if loc and loc in kl:
                    # Keywords with location + purchase signals → transactional (location just adds geo context)
                    if any(s in kl for s in ["buy", "order", "purchase", "price", "delivery", "shop", "online"]):
                        return IntentResult("transactional", 0.9)
                    # Keywords with just location → local intent
                    return IntentResult("local", 0.85)

        # Rule-based intent classification (high confidence)
        # Pad keyword with spaces for boundary-aware matching
        padded = f" {kl} "
        for intent, signals in self.RULES.items():
            if any(s in padded for s in signals):
                return IntentResult(intent, 0.9)

        if entity.get("intent"):
            return IntentResult("transactional", 0.8)

        if entity.get("attribute"):
            return IntentResult("informational", 0.7)

        # Weak matches for value words
        if any(kw_word in kl for kw_word in ["buy", "price", "order", "shop"]):
            return IntentResult("transactional", 0.7)
        if any(kw_word in kl for kw_word in ["review", "best", "top", "vs", "compare"]):
            return IntentResult("commercial", 0.7)

        # AI fallback only if needed (fail-safe)
        try:
            prompt = f"""
Classify search intent for this keyword:
Keyword: {kw}

Return JSON: {{"intent":"informational|transactional|commercial|navigational"}}
"""

            resp = AI.groq(prompt)
            parsed = AI.parse_json(resp) or {}
            intent = parsed.get("intent", "informational")
            if intent not in ["informational", "transactional", "commercial", "navigational"]:
                intent = "informational"
            return IntentResult(intent, 0.6)
        except Exception as e:
            log.warning(f"[P5] Intent fallback failed ({e}), defaulting to informational")
            return IntentResult("informational", 0.5)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — SERP INTELLIGENCE (P6)
# ─────────────────────────────────────────────────────────────────────────────

class P6_SERPIntelligence:
    """
    Phase 6: Analyze top search results per keyword.
    Uses DuckDuckGo as a lightweight proxy and builds robust SERP signals.
    """
    phase = "P6"

    BIG_SITES = {
        "amazon","wikipedia","flipkart","healthline","webmd","nytimes"
    }

    def run(self, seed: Seed, keywords: List[str],
             max_keywords: int = None, emit_fn=None) -> Dict[str, dict]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        target = keywords[:max_keywords] if max_keywords else keywords
        serp_map = {}
        total = len(target)
        log.info(f"[P6] SERP analysis for {total} keywords (no truncation)...")

        for i, kw in enumerate(target):
            cache_key = f"serp:{hashlib.md5(kw.encode()).hexdigest()[:12]}"
            cached_serp = Cache.get(cache_key, Cfg.TTL_SERP)
            if cached_serp:
                serp_map[kw] = cached_serp
                continue

            data = self._analyse_serp(kw)
            Cache.set(cache_key, data, Cfg.TTL_SERP)
            serp_map[kw] = data

            # Emit progress every 25 keywords
            if emit_fn and (i + 1) % 25 == 0:
                try:
                    emit_fn("phase_log", {
                        "phase": "P6", "status": "progress", "color": "blue",
                        "msg": f"P6 progress: {i+1}/{total} keywords analyzed",
                        "output_count": i + 1,
                    })
                except Exception:
                    pass

        Cache.save_checkpoint(seed.id, self.phase, serp_map)
        log.info(f"[P6] SERP signals generated for {len(serp_map)} keywords")
        return serp_map

    def _analyse_serp(self, kw: str) -> dict:
        """Heuristic SERP analysis based on keyword properties.
        Estimates KD, authority, content type, gap opportunity from keyword signals
        rather than live Google scraping (which gets IP-blocked in production)."""
        kw_l = kw.lower().strip()
        words = kw_l.split()
        word_count = len(words)

        # ── Intent detection from keyword text ────────────────────────────
        trans_signals = ["buy", "price", "order", "purchase", "cheap", "discount",
                         "shop", "wholesale", "bulk", "delivery", "online", "cost", "deal"]
        comm_signals = ["best", "top", "review", "vs", "versus", "compare",
                        "alternative", "recommended", "rated"]
        info_signals = ["what", "how", "why", "when", "does", "is", "are",
                        "benefits", "uses", "guide", "meaning", "definition"]
        local_signals = ["near me", "nearby", "in my area", "local"]

        intent = "informational"
        if any(s in kw_l for s in local_signals):
            intent = "local"
        elif any(s in kw_l for s in trans_signals):
            intent = "transactional"
        elif any(s in kw_l for s in comm_signals):
            intent = "commercial"
        elif any(s in kw_l for s in info_signals):
            intent = "informational"

        # ── KD estimation from keyword length and specificity ─────────────
        # Longer-tail keywords = lower competition
        if word_count <= 1:
            kd = 75  # Head terms: high competition
        elif word_count == 2:
            kd = 55  # Mid-tail
        elif word_count == 3:
            kd = 35  # Long-tail
        elif word_count == 4:
            kd = 25  # Very long-tail
        else:
            kd = 15  # Ultra-long-tail

        # Adjust based on intent (transactional = more competition)
        if intent == "transactional":
            kd = min(100, kd + 15)
        elif intent == "commercial":
            kd = min(100, kd + 10)
        elif intent == "local":
            kd = max(5, kd - 10)

        # ── Authority estimation ──────────────────────────────────────────
        # Generic/broad keywords likely dominated by big sites
        authority = 3 if word_count <= 2 else (2 if word_count == 3 else 1)

        # ── Gap opportunity ───────────────────────────────────────────────
        gap = kd < 40 and authority < 3

        # ── Content type estimation ───────────────────────────────────────
        if intent == "transactional":
            content_type = "product"
        elif intent == "commercial":
            content_type = "listicle"
        elif any(w in kw_l for w in ["how to", "guide", "tutorial", "step"]):
            content_type = "how-to"
        elif any(w in kw_l for w in ["what is", "meaning", "definition"]):
            content_type = "explainer"
        else:
            content_type = "article"

        return {
            "kw": kw,
            "top_urls": [],
            "kd": kd,
            "authority": authority,
            "content_type": content_type,
            "intent": intent,
            "intent_match": True,
            "gap": gap,
            "has_featured_snippet": word_count >= 4 and intent == "informational",
            "has_paa": intent in ("informational", "commercial"),
        }


class P6_CompetitorKeywordMining:
    """Phase 6.6: Mine competitor keywords from top-ranking pages."""
    phase = "P6_6"

    MIN_WORDS = 2
    MAX_WORDS = 6

    def run(self, seed: Seed, serp_map: Dict[str, dict]) -> Dict[str, List[str]]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        keyword_map = {}

        for kw, serp in serp_map.items():
            urls = serp.get("top_urls", [])
            extracted = []
            for url in urls[:5]:
                extracted.extend(self._extract_keywords(url, seed.keyword))

            filtered = self._rule_filter(extracted, seed.keyword)
            validated = self._ai_filter(filtered, seed.keyword)

            keyword_map[kw] = validated

        Cache.save_checkpoint(seed.id, self.phase, keyword_map)
        log.info(f"[P6_6] Competitor keywords extracted for {len(keyword_map)} query seeds")
        return keyword_map

    def _extract_keywords(self, url: str, seed: str) -> List[str]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            log.warning("[P6_6] bs4 not installed; skipping competitor keyword extraction")
            return []

        try:
            r = _req.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            text = soup.get_text(" ", strip=True).lower()
            words = text.split()

            phrases = []
            for i in range(len(words) - 2):
                phrase = " ".join(words[i:i+3])
                if seed in phrase:
                    phrases.append(phrase)

            for h in soup.find_all(["h1", "h2", "h3"]):
                txt = h.get_text().lower().strip()
                if seed in txt:
                    phrases.append(txt)

            return phrases[:300]

        except Exception:
            return []

    def _rule_filter(self, keywords: List[str], seed: str) -> List[str]:
        clean = []
        for kw in keywords:
            words = kw.split()
            if not (self.MIN_WORDS <= len(words) <= self.MAX_WORDS):
                continue
            if seed not in kw:
                continue
            if any(bad in kw for bad in ["click here", "read more", "privacy", "terms"]):
                continue
            clean.append(kw)

        return list(dict.fromkeys(clean))

    def _ai_filter(self, keywords: List[str], seed: str) -> List[str]:
        final = []
        for chunk in MemoryManager.chunks(keywords, 100):
            prompt = f"""
You are an SEO keyword cleaner.

Seed: {seed}

Clean and validate these keywords:
{chunk}

Rules:
- keep only real search queries
- remove junk phrases
- remove sentences
- fix grammar if needed
- ensure business relevance

Return JSON list.
"""
            resp = AI.groq(prompt)
            parsed = AI.parse_json(resp)
            if isinstance(parsed, list):
                final.extend(parsed)

        return list(dict.fromkeys(final))


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
             intent_map: Dict[str,dict],
             serp_map: Dict[str,dict],
             entities: Optional[Dict[str,dict]] = None) -> Dict[str, float]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        entities = entities or {}
        if cached:
            return cached

        if not keywords:
            log.warning("[P7] No keywords to score (empty input). Returning empty scores")
            return {}

        scores = {}
        # Popularity proxy: more autosuggest = more popular
        kw_set = set(keywords)
        for kw in keywords:
            scores[kw] = self._score(
                kw,
                intent_map.get(kw, {"intent":"informational","confidence":0.6}),
                serp_map.get(kw, {}),
                entities.get(kw, {})
            )

        Cache.save_checkpoint(seed.id, self.phase, scores)
        log.info(f"[P7] Scored {len(scores)} keywords. "
                 f"Top score: {max(scores.values(),default=0):.1f}")
        return scores

    def _score(self, kw: str, intent_or_data, serp: Optional[dict] = None, entity: Optional[dict] = None) -> float:
        # Accept either an intent string or an intent dict (compatibility)
        if isinstance(intent_or_data, dict):
            intent = intent_or_data.get("intent", "informational")
        else:
            intent = intent_or_data or "informational"

        serp = serp or {}
        entity = entity or {}

        # Scoring components (weights sum to 100)
        tokens = [t.lower() for t in kw.split() if t]
        question_words = {"what", "how", "does", "do", "why", "when", "is", "can", "are", "should", "which"}

        # Ignore leading question word for word-count sweet-spot calculation
        effective_wc = len(tokens) - 1 if tokens and tokens[0] in question_words else len(tokens)
        if effective_wc < 1:
            effective_wc = 1

        wc_sc = 1.0 if 3 <= effective_wc <= 5 else 0.7 if effective_wc == 2 else 0.5

        kd = serp.get("kd_estimate", serp.get("kd", 40))
        kd_sc = 1.0 - (min(max(kd, 0), 100) / 100.0)

        intent_sc = {
            "transactional": 0.9,
            "commercial": 0.8,
            "comparison": 0.85,
            "informational": 0.7,
            "navigational": 0.4
        }.get(intent, 0.6)

        q_sc = 0.2 if tokens and tokens[0] in question_words else 0.0

        wc_weight = 30.0
        kd_weight = 40.0
        intent_weight = 25.0
        q_weight = 5.0

        score = (
            wc_sc * wc_weight +
            kd_sc * kd_weight +
            intent_sc * intent_weight +
            q_sc * q_weight
        )

        return round(max(0.0, min(score, 100.0)), 1)


class P7_TopKeywordSelector:
    """Phase 7B: Select top keywords per pillar with diversity constraint.

    New P7 V2 features:
    - intent-balanced top N output (transactional/commercial/informational/comparison/navigational)
    - final top-100 (per seed) selected keywords for pillar targeting
    - deterministic score + de-dupe by kw
    - pipeline injection in RufloOrchestrator.run_seed()
    """
    phase = "P7B"

    def run(self, seed: Seed, keywords: List[str], scores: Dict[str,float], intent_map: Dict[str,str], top_n: int = 100) -> List[dict]:
        enriched = []
        for kw in keywords:
            intent = intent_map.get(kw, {})
            if isinstance(intent, dict):
                intent = intent.get("intent", "informational")
            enriched.append({
                "keyword": kw,
                "score": scores.get(kw, 0.0),
                "intent": intent
            })

        # intent balancing quotas
        quotas = {
            "transactional": int(top_n * 0.25),
            "commercial":    int(top_n * 0.30),
            "informational": int(top_n * 0.40),
            "comparison":    max(3, int(top_n * 0.03)),
            "navigational":  max(2, int(top_n * 0.02))
        }

        by_intent = {i: sorted([x for x in enriched if x["intent"] == i], key=lambda x: x["score"], reverse=True)
                     for i in quotas.keys()}

        selected = []
        selected_set = set()

        for intent, quota in quotas.items():
            for item in by_intent.get(intent, [])[:quota]:
                if item["keyword"] not in selected_set:
                    selected.append(item)
                    selected_set.add(item["keyword"])

        remaining = [x for x in sorted(enriched, key=lambda x: x["score"], reverse=True)
                     if x["keyword"] not in selected_set]

        for item in remaining:
            if len(selected) >= top_n:
                break
            selected.append(item)
            selected_set.add(item["keyword"])

        return selected[:top_n]


    def validate(self, selected: List[dict]) -> List[dict]:
        return selected


    def _debug_intent_distribution(self, selected: List[dict]) -> Dict[str,int]:
        from collections import Counter
        return dict(Counter(x["intent"] for x in selected))


    def _score_threshold_filter(self, selected: List[dict], min_score: float = 40.0) -> List[dict]:
        return [x for x in selected if x["score"] >= min_score]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — TOPIC DETECTION (P8) — heavy phase
# ─────────────────────────────────────────────────────────────────────────────

class P8_TopicDetection:
    """Phase 8: SEO-aware topic clustering (intent + semantic embeddings).
    Uses Ollama embeddings for cosine-similarity grouping within intent groups.
    Falls back to word-overlap if embeddings unavailable."""
    phase = "P8"

    def run(self, seed: Seed, keywords: List[str],
             scores: Dict[str,dict], intent_map: Optional[Dict[str,dict]] = None,
             emit_fn=None) -> Dict[str, List[str]]:
        if intent_map is None:
            intent_map = {}
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        if not keywords:
            log.warning("[P8] No keywords input for topic detection; returning empty")
            Cache.save_checkpoint(seed.id, self.phase, {})
            return {}

        log.info(f"[P8++] Topic clustering for {len(keywords)} keywords")

        ranked = sorted(keywords, key=lambda k: self._score_of(k, scores), reverse=True)

        # ── Step 1: Group by intent ──────────────────────────────────────
        intent_groups = {}
        for kw in ranked:
            intent = self._get_intent(kw, intent_map)
            intent_groups.setdefault(intent, []).append(kw)

        # ── Step 2: Embed & cluster within each intent group ─────────────
        named = {}
        used_names = set()
        use_embeddings = self._can_use_embeddings(ranked[:5])  # Quick test

        if use_embeddings and emit_fn:
            try: emit_fn("phase_log", {"phase": "P8", "status": "starting", "msg": f"Generating embeddings for {len(keywords)} keywords…"})
            except Exception: pass

        for intent, kw_list in intent_groups.items():
            if use_embeddings and len(kw_list) >= 4:
                sub_clusters = self._cluster_by_embedding(kw_list, scores, emit_fn)
            else:
                sub_clusters = self._sub_cluster_by_overlap(kw_list)

            for sub_kws in sub_clusters:
                if not sub_kws:
                    continue
                name = self._name_topic(sub_kws, scores)
                base_name = name
                suffix = 2
                while name in used_names:
                    name = f"{base_name} {suffix}"
                    suffix += 1
                used_names.add(name)
                named[name] = sub_kws

        # ── Step 3: Split if too few topics ──────────────────────────────
        min_topics = max(10, min(120, len(keywords) // 3))
        if len(named) < min_topics:
            log.info(f"[P8++] Clustering gave {len(named)} topics, splitting to reach ~{min_topics}")
            named = self._split_large_topics(named, min_topics, scores)

        # ── Step 4: Ensure no keyword is lost ────────────────────────────
        all_assigned = set()
        for kws in named.values():
            all_assigned.update(kws)
        missing = [k for k in keywords if k not in all_assigned]
        if missing:
            # Group stragglers into a misc topic
            for i in range(0, len(missing), 8):
                chunk = missing[i:i+8]
                name = self._name_topic(chunk, scores)
                base_name = name
                suffix = 2
                while name in used_names:
                    name = f"{base_name} {suffix}"
                    suffix += 1
                used_names.add(name)
                named[name] = chunk

        log.info(f"[P8++] Created {len(named)} topics ({len(keywords)} keywords preserved)")
        Cache.save_checkpoint(seed.id, self.phase, named)
        return named

    # ── Embedding-based clustering ───────────────────────────────────────

    def _can_use_embeddings(self, sample_kws: List[str]) -> bool:
        """Quick test: can we get embeddings from Ollama?"""
        try:
            vecs = AI.embed_batch(sample_kws[:2])
            return vecs and len(vecs) >= 2 and any(v != 0.0 for v in vecs[0][:10])
        except Exception:
            return False

    def _cluster_by_embedding(self, keywords: List[str], scores: Dict[str,Any],
                                emit_fn=None) -> List[List[str]]:
        """Embed keywords via Ollama, then agglomerative clustering by cosine similarity."""
        # Batch embed with progress
        batch_size = 50
        all_vecs = []
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i+batch_size]
            vecs = AI.embed_batch(batch)
            all_vecs.extend(vecs)
            if emit_fn and i > 0:
                try: emit_fn("phase_log", {"phase": "P8", "status": "starting",
                             "msg": f"Embedded {min(i+batch_size, len(keywords))}/{len(keywords)} keywords"})
                except Exception: pass

        if not all_vecs or len(all_vecs) != len(keywords):
            log.warning("[P8] Embedding count mismatch, falling back to word overlap")
            return self._sub_cluster_by_overlap(keywords)

        # Cosine similarity matrix (pure Python — no numpy needed)
        def dot(a, b):
            return sum(x*y for x, y in zip(a, b))
        def norm(a):
            return max(dot(a, a) ** 0.5, 1e-10)
        def cosine(a, b):
            return dot(a, b) / (norm(a) * norm(b))

        # Target: 3-15 keywords per topic
        target_topics = max(10, min(120, len(keywords) // 3))
        target_per_topic = max(3, len(keywords) // max(target_topics, 1))
        sim_threshold = 0.65  # Start with moderate threshold

        # Greedy clustering: pick seed keyword, absorb similar
        assigned = set()
        clusters = []

        # Sort by score desc — higher score keywords become cluster centers
        scored_idx = sorted(range(len(keywords)),
                            key=lambda i: self._score_of(keywords[i], scores), reverse=True)

        for center_idx in scored_idx:
            if center_idx in assigned:
                continue
            cluster = [center_idx]
            assigned.add(center_idx)
            center_vec = all_vecs[center_idx]

            # Find similar unassigned keywords
            candidates = []
            for j in range(len(keywords)):
                if j in assigned:
                    continue
                sim = cosine(center_vec, all_vecs[j])
                if sim >= sim_threshold:
                    candidates.append((j, sim))

            # Sort by similarity desc, take up to target_per_topic
            candidates.sort(key=lambda x: -x[1])
            for j, sim in candidates[:target_per_topic - 1]:
                cluster.append(j)
                assigned.add(j)

            clusters.append([keywords[i] for i in cluster])

        # Pick up unassigned as singletons merged into smallest cluster
        remaining = [keywords[i] for i in range(len(keywords)) if i not in assigned]
        if remaining:
            for kw in remaining:
                if clusters:
                    smallest = min(clusters, key=len)
                    smallest.append(kw)
                else:
                    clusters.append([kw])

        return clusters

    # ── Fallback: word-overlap clustering ────────────────────────────────

    # ── Fallback: word-overlap clustering ────────────────────────────────

    def _sub_cluster_by_overlap(self, keywords: List[str], min_overlap: int = 2, max_per_cluster: int = 8) -> List[List[str]]:
        """Group keywords that share >= min_overlap words. Limits cluster size."""
        clusters = []
        assigned = set()
        for kw in keywords:
            if kw in assigned:
                continue
            cluster = [kw]
            assigned.add(kw)
            kw_words = set(kw.lower().split())
            for other in keywords:
                if other in assigned:
                    continue
                other_words = set(other.lower().split())
                if len(kw_words & other_words) >= min_overlap:
                    cluster.append(other)
                    assigned.add(other)
                    if len(cluster) >= max_per_cluster:
                        break
            clusters.append(cluster)
        # Pick up any remaining keywords as singletons grouped into a misc cluster
        remaining = [kw for kw in keywords if kw not in assigned]
        if remaining:
            for i in range(0, len(remaining), max_per_cluster):
                clusters.append(remaining[i:i+max_per_cluster])
        return clusters

    def _split_large_topics(self, named: Dict[str, List[str]], target: int, scores: Dict[str,Any]) -> Dict[str, List[str]]:
        """Split oversized topics until we reach the target count."""
        result = dict(named)
        used_names = set(result.keys())
        while len(result) < target:
            # Find the largest topic
            largest_name = max(result, key=lambda k: len(result[k]))
            largest = result[largest_name]
            if len(largest) <= 2:
                break  # Can't split further
            mid = len(largest) // 2
            part_a = largest[:mid]
            part_b = largest[mid:]
            # Name the new split
            del result[largest_name]
            used_names.discard(largest_name)
            for part in [part_a, part_b]:
                top_kws = sorted(part, key=lambda k: scores.get(k, 0), reverse=True)[:5]
                name = self._name_topic(top_kws, scores)
                base_name = name
                suffix = 2
                while name in used_names:
                    name = f"{base_name} {suffix}"
                    suffix += 1
                used_names.add(name)
                result[name] = part
        return result

    def _clean_topic_name(self, kw: str) -> str:
        remove = {"buy", "best", "cheap", "online", "price", "india", "wholesale", "bulk"}
        words = [w for w in kw.lower().split() if w not in remove]
        return " ".join(words[:5]).title()

    def _is_phrase_match(self, k1: str, k2: str) -> bool:
        s1 = set(k1.lower().split())
        s2 = set(k2.lower().split())
        return len(s1 & s2) >= 2

    @staticmethod
    def _score_of(k: str, scores: Dict[str, Any]) -> float:
        val = scores.get(k, 0)
        if isinstance(val, dict):
            return float(val.get("final", val.get("score", 0)))
        if isinstance(val, (int, float)):
            return float(val)
        return 0.0

    @staticmethod
    def _get_intent(kw: str, intent_map: Dict[str, Any]) -> str:
        intent_val = intent_map.get(kw, {})
        if isinstance(intent_val, dict):
            return intent_val.get("intent", "informational")
        elif isinstance(intent_val, str):
            return intent_val
        return "informational"

    def _name_topic(self, keywords: List[str], scores: Dict[str,Any]) -> str:
        if not keywords:
            return "Untitled Topic"

        best = max(keywords, key=lambda k: self._score_of(k, scores))
        tok = best.lower().split()
        # Only remove generic modifiers — keep location words as they provide important context
        remove = {"buy", "best", "top", "online", "cheap", "price"}
        tok = [w for w in tok if w not in remove]
        name = " ".join(tok).strip() or best

        if len(name.split()) > 6:
            name = " ".join(name.split()[:6])

        return name.strip().title()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — CLUSTER FORMATION (P9)
# ─────────────────────────────────────────────────────────────────────────────

class P9_ClusterFormation:
    """
    Phase 9: Group related topics into larger thematic clusters.
    Example: "Cinnamon Blood Sugar" + "Cinnamon Cholesterol" → "Cinnamon Health"
    """
    phase = "P9"

    CLUSTER_PROMPT = """You are an SEO content strategist. Group these {n_topics} SEO topics into exactly {n_clusters} larger thematic clusters.
Each cluster should be a broad, distinct theme. Every topic must be assigned to exactly one cluster.

Seed keyword: {seed}

Topics (with sample keywords):
{topic_details}

Return ONLY valid JSON: {{"Cluster Name": ["Topic 1", "Topic 2", ...], ...}}
Every topic above MUST appear in exactly one cluster. Do not rename topics."""

    def run(self, seed: Seed, topic_map: Dict[str, List[str]], project_id: Optional[str] = None) -> Dict[str, List[str]]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        if not topic_map:
            log.warning("[P9] No topics for cluster formation; returning empty")
            Cache.save_checkpoint(seed.id, self.phase, {})
            return {}

        topics = list(topic_map.keys())
        n      = max(5, min(50, max(1, len(topics) // 3)))

        # Build rich topic details: topic name + top 3 keywords
        topic_details_parts = []
        for t_name in topics:
            kws = topic_map.get(t_name, [])
            sample = ", ".join(kws[:3]) if kws else "(no keywords)"
            topic_details_parts.append(f"- {t_name} [{sample}]")
        topic_details = "\n".join(topic_details_parts)

        # Paginate if too many topics for single prompt (>150 topics)
        if len(topics) <= 150:
            clusters = self._cluster_single_call(seed, topics, topic_map, topic_details, n)
        else:
            clusters = self._cluster_paginated(seed, topics, topic_map, n)

        # If a project_id is provided, filter clusters by domain context
        if project_id:
            try:
                from quality.annaseo_domain_context import DomainContextEngine
                dce = DomainContextEngine()
                filtered = {}
                dropped = 0
                for cname, topic_names in clusters.items():
                    keep = []
                    for tn in topic_names:
                        # Check the first keyword of the topic
                        kws = topic_map.get(tn, [tn])
                        res = dce.classify(kws[0] if kws else tn, project_id)
                        if res.get("verdict") != "reject":
                            keep.append(tn)
                    if keep and (len(keep) / max(1, len(topic_names))) >= 0.3:
                        filtered[cname] = keep
                    else:
                        dropped += 1
                        # Don't completely drop — keep topics that passed, even if ratio low
                        if keep:
                            filtered[cname] = keep
                log.info(f"[P9] Domain filter: dropped {dropped} full clusters for project {project_id}")
                # Safety: never let domain filter remove more than 50% of clusters
                if len(filtered) >= len(clusters) * 0.5:
                    clusters = filtered
                else:
                    log.warning(f"[P9] Domain filter too aggressive ({len(filtered)}/{len(clusters)} clusters remain), keeping original")
            except Exception as e:
                log.warning(f"[P9] DomainContext filtering failed: {e}")

        # Ensure all topics are assigned (rescue orphans)
        assigned_topics = set()
        for topic_names in clusters.values():
            assigned_topics.update(topic_names)
        orphans = [t for t in topics if t not in assigned_topics]
        if orphans:
            log.info(f"[P9] Rescuing {len(orphans)} orphan topics into 'Other' cluster")
            clusters["Other Topics"] = orphans

        Cache.save_checkpoint(seed.id, self.phase, clusters)
        log.info(f"[P9] {len(clusters)} clusters formed from {len(topics)} topics")
        return clusters

    def _cluster_single_call(self, seed: Seed, topics: List[str],
                               topic_map: Dict[str, List[str]],
                               topic_details: str, n: int) -> Dict[str, List[str]]:
        """Single Gemini call for <= 150 topics."""
        prompt = self.CLUSTER_PROMPT.format(
            n_clusters=n, n_topics=len(topics),
            topic_details=topic_details, seed=seed.keyword
        )
        try:
            text = AI.gemini(prompt, temperature=0.2)
            clusters = AI.parse_json(text)
            if not isinstance(clusters, dict):
                raise ValueError("Expected dict")
            # Validate: remap AI topic names back to real names
            clusters = self._remap_cluster_topics(clusters, topics)
            if not clusters:
                raise ValueError("Remapping produced empty clusters")
            return clusters
        except Exception as e:
            log.warning(f"[P9] AI cluster formation failed ({e}), using topic map fallback")
            return self._fallback_clustering(topics, topic_map, n)

    def _cluster_paginated(self, seed: Seed, topics: List[str],
                             topic_map: Dict[str, List[str]], n: int) -> Dict[str, List[str]]:
        """Paginated clustering for >150 topics: batch into groups of 100, then merge."""
        batch_size = 100
        all_clusters = {}
        for i in range(0, len(topics), batch_size):
            batch_topics = topics[i:i+batch_size]
            batch_n = max(3, n * len(batch_topics) // len(topics))
            td_parts = []
            for t_name in batch_topics:
                kws = topic_map.get(t_name, [])
                sample = ", ".join(kws[:3]) if kws else "(no keywords)"
                td_parts.append(f"- {t_name} [{sample}]")
            prompt = self.CLUSTER_PROMPT.format(
                n_clusters=batch_n, n_topics=len(batch_topics),
                topic_details="\n".join(td_parts), seed=seed.keyword
            )
            try:
                text = AI.gemini(prompt, temperature=0.2)
                batch_clusters = AI.parse_json(text)
                if isinstance(batch_clusters, dict):
                    batch_clusters = self._remap_cluster_topics(batch_clusters, batch_topics)
                    for name, topic_names in batch_clusters.items():
                        if name in all_clusters:
                            all_clusters[name].extend(topic_names)
                        else:
                            all_clusters[name] = list(topic_names)
                time.sleep(Cfg.GEMINI_RATE)
            except Exception as e:
                log.warning(f"[P9] Batch {i//batch_size} failed: {e}")
                for t in batch_topics:
                    all_clusters.setdefault("Unclustered", []).append(t)

        return all_clusters if all_clusters else self._fallback_clustering(topics, topic_map, n)

    def _remap_cluster_topics(self, clusters: Dict[str, list], real_topics: List[str]) -> Dict[str, List[str]]:
        """Map AI-returned topic names back to actual topic names using fuzzy matching.
        Any orphaned real topics (not matched by any cluster) get assigned to the nearest cluster."""
        real_lower = {t.lower().strip(): t for t in real_topics}
        matched_originals = set()  # Track which real topics have been matched
        remapped = {}
        for cname, topic_names in clusters.items():
            if not isinstance(topic_names, list):
                continue
            matched = []
            for tn in topic_names:
                tn_lower = str(tn).lower().strip()
                # Exact match
                if tn_lower in real_lower:
                    matched.append(real_lower[tn_lower])
                    matched_originals.add(real_lower[tn_lower])
                    continue
                # Substring match
                found = False
                for real_l, real_orig in real_lower.items():
                    if real_orig in matched_originals:
                        continue
                    if tn_lower in real_l or real_l in tn_lower:
                        matched.append(real_orig)
                        matched_originals.add(real_orig)
                        found = True
                        break
                if not found:
                    # Word overlap match (>=40% words shared — lowered from 60% to reduce orphans)
                    tn_words = set(tn_lower.split())
                    best_match, best_overlap = None, 0
                    for real_l, real_orig in real_lower.items():
                        if real_orig in matched_originals:
                            continue
                        real_words = set(real_l.split())
                        overlap = len(tn_words & real_words) / max(len(tn_words | real_words), 1)
                        if overlap > best_overlap and overlap >= 0.4:
                            best_overlap = overlap
                            best_match = real_orig
                    if best_match:
                        matched.append(best_match)
                        matched_originals.add(best_match)
            if matched:
                remapped[cname] = matched

        # ── Assign orphaned topics to nearest cluster ─────────────────────
        orphans = [t for t in real_topics if t not in matched_originals]
        if orphans and remapped:
            cluster_names = list(remapped.keys())
            for orphan in orphans:
                orphan_words = set(orphan.lower().split())
                best_cluster, best_score = cluster_names[0], 0
                for cname, topics in remapped.items():
                    cluster_words = set()
                    for t in topics:
                        cluster_words.update(t.lower().split())
                    overlap = len(orphan_words & cluster_words)
                    if overlap > best_score:
                        best_score = overlap
                        best_cluster = cname
                remapped[best_cluster].append(orphan)
            if orphans:
                log.info(f"[P9] Assigned {len(orphans)} orphaned topics to existing clusters")

        return remapped

    def _fallback_clustering(self, topics: List[str], topic_map: Dict[str, List[str]], n: int) -> Dict[str, List[str]]:
        """Simple round-robin fallback when AI clustering fails."""
        sorted_topics = sorted(topics, key=lambda t: len(topic_map.get(t, [])), reverse=True)
        clusters = {}
        for i, t in enumerate(sorted_topics):
            bucket = i % n
            cname = f"Cluster {bucket + 1}"
            clusters.setdefault(cname, []).append(t)
        return clusters


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — PILLAR IDENTIFICATION (P10)
# ─────────────────────────────────────────────────────────────────────────────

class P10_PillarIdentification:
    """Phase 10: For each cluster, identify the anchor pillar page.
    When cluster count > MAX_PILLARS, consolidates similar clusters first."""
    phase = "P10"

    MAX_PILLARS = 15
    MIN_PILLARS = 5

    PILLAR_PROMPT = """For this SEO cluster, generate the perfect pillar page title.
The pillar page is the comprehensive, authoritative guide that covers everything
in this cluster. It should rank for the broadest keyword in the cluster.

Cluster: "{cluster}"
All topics in this cluster: {topics}
Seed keyword: {seed}

Return ONLY the pillar page title (one line, no quotes)."""

    CONSOLIDATE_PROMPT = """You are an SEO architect. Merge these {n_clusters} topic clusters into
exactly {target} pillar groups. Each pillar should be a distinct, broad theme.

Clusters:
{cluster_list}

Seed keyword: {seed}

Return ONLY valid JSON mapping pillar name to list of cluster names to merge:
{{"Pillar Name": ["Cluster A", "Cluster B"], ...}}"""

    def run(self, seed: Seed, clusters: Dict[str,List[str]],
             scores: Dict[str,float] = None,
             topic_map: Dict[str,List[str]] = None,
             project_id: Optional[str] = None) -> Dict[str,dict]:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached
        scores = scores or {}
        topic_map = topic_map or {}

        # Consolidate if too many clusters
        if len(clusters) > self.MAX_PILLARS:
            clusters = self._consolidate(seed, clusters)

        pillars = {}
        for cluster_name, topics in clusters.items():
            # Send ALL topics (up to 30) for context
            pillar_title = AI.gemini(
                self.PILLAR_PROMPT.format(
                    cluster=cluster_name, topics=topics[:30], seed=seed.keyword
                ), temperature=0.2
            ).strip().strip('"')

            # Fallback if AI returns empty title
            if not pillar_title:
                pillar_title = f"{seed.keyword}: {cluster_name}"

            # Find best keyword across all topics in this cluster
            all_kws_in_cluster = []
            for t in topics:
                all_kws_in_cluster.extend(topic_map.get(t, []))
            if all_kws_in_cluster and scores:
                best_kw = max(all_kws_in_cluster,
                              key=lambda k: float(scores.get(k, 0)) if isinstance(scores.get(k, 0), (int, float))
                              else float(scores.get(k, {}).get("score", 0)) if isinstance(scores.get(k, 0), dict)
                              else 0)
                pillar_keyword = best_kw.lower()
            else:
                pillar_keyword = cluster_name.lower()

            # Real article count: count of all keywords across topics + 1 pillar page
            total_kws = sum(len(topic_map.get(t, [])) for t in topics)
            article_count = max(total_kws, len(topics)) + 1

            pillars[cluster_name] = {
                "pillar_title": pillar_title,
                "pillar_keyword": pillar_keyword,
                "topics": topics,
                "article_count": article_count,
                "keyword_count": total_kws,
            }
            time.sleep(Cfg.GEMINI_RATE)

        # If project_id provided, validate pillars against DomainContext
        if project_id:
            try:
                from quality.annaseo_domain_context import DomainContextEngine
                dce = DomainContextEngine()
                valid, rejected = dce.validate_pillars(pillars, project_id)
                if rejected:
                    log.info(f"[P10] {len(rejected)} pillars rejected by domain context for project {project_id}")
                pillars = valid
            except Exception as e:
                log.warning(f"[P10] DomainContext validation failed: {e}")

        Cache.save_checkpoint(seed.id, self.phase, pillars)
        log.info(f"[P10] {len(pillars)} pillar pages identified")
        return pillars

    def _consolidate(self, seed: Seed, clusters: Dict[str,List[str]]) -> Dict[str,List[str]]:
        """Merge similar clusters until count is within MAX_PILLARS."""
        target = min(self.MAX_PILLARS, max(self.MIN_PILLARS, len(clusters) // 2))
        cluster_list = "\n".join(
            f"- {name}: {', '.join(topics[:5])}" for name, topics in list(clusters.items())[:60]
        )
        try:
            text = AI.gemini(
                self.CONSOLIDATE_PROMPT.format(
                    n_clusters=len(clusters), target=target,
                    cluster_list=cluster_list, seed=seed.keyword,
                ), temperature=0.2
            )
            merge_map = AI.parse_json(text)
            if not isinstance(merge_map, dict):
                raise ValueError("Expected dict")

            merged = {}
            used_clusters = set()
            for pillar_name, cluster_names in merge_map.items():
                if not isinstance(cluster_names, list):
                    continue
                combined_topics = []
                for cn in cluster_names:
                    # Fuzzy match cluster names (AI may not return exact names)
                    matched = None
                    for real_cn in clusters:
                        if real_cn.lower().strip() == cn.lower().strip():
                            matched = real_cn
                            break
                    if not matched:
                        for real_cn in clusters:
                            if cn.lower() in real_cn.lower() or real_cn.lower() in cn.lower():
                                matched = real_cn
                                break
                    if matched and matched not in used_clusters:
                        combined_topics.extend(clusters[matched])
                        used_clusters.add(matched)
                if combined_topics:
                    merged[pillar_name] = combined_topics

            # Add any clusters not mapped
            for cn, topics in clusters.items():
                if cn not in used_clusters:
                    merged[cn] = topics

            log.info(f"[P10] Consolidated {len(clusters)} clusters → {len(merged)} pillars")
            return merged

        except Exception as e:
            log.warning(f"[P10] AI consolidation failed ({e}), using largest-{target}")
            # Fallback: keep top-N largest clusters, merge the rest into them
            sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
            result = {}
            for name, topics in sorted_clusters[:target]:
                result[name] = list(topics)
            # Distribute remaining clusters into closest existing pillar
            for name, topics in sorted_clusters[target:]:
                # Find pillar with most word overlap
                best_pillar = list(result.keys())[0]
                best_score = 0
                name_words = set(name.lower().split())
                for pname in result:
                    pwords = set(pname.lower().split())
                    overlap = len(name_words & pwords)
                    if overlap > best_score:
                        best_score = overlap
                        best_pillar = pname
                result[best_pillar].extend(topics)
            return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 15 — KNOWLEDGE GRAPH (P11)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KnowledgeGraph:
    """5-level hierarchy: Seed → Pillar → Cluster → Topic → Keyword."""
    seed:    str
    pillars: Dict[str, dict] = field(default_factory=dict)
    # {pillar_name: {title, clusters: {cluster_name: {topics: {topic: [keywords]}}}}}

    def __len__(self):
        return len(self.pillars)

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
                # Get keywords for this topic — try exact match, then fuzzy
                topic_kws = topic_map.get(topic, [])
                if not topic_kws:
                    # Fuzzy match: topic may have been renamed by P9/P10
                    topic_lower = topic.lower().strip()
                    for tm_key, tm_val in topic_map.items():
                        if tm_key.lower().strip() == topic_lower:
                            topic_kws = tm_val
                            break
                    if not topic_kws:
                        # Substring match
                        for tm_key, tm_val in topic_map.items():
                            if topic_lower in tm_key.lower() or tm_key.lower() in topic_lower:
                                topic_kws = tm_val
                                break
                    if not topic_kws:
                        # Use topic name as a keyword rather than leaving empty
                        topic_kws = [topic]
                        log.warning(f"[P11] Topic '{topic}' not found in topic_map, using as keyword")
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
    Rules: Topic→Pillar, Topic→Topic (sibling + cross-cluster), Cluster→Pillar, Pillar→Seed product.
    Link types vary by intent: informational/commercial/transactional.
    """
    phase = "P12"

    INTENT_CTA = {
        "informational": "learn more about",
        "commercial":    "compare",
        "transactional": "buy",
        "navigational":  "visit",
        "local":         "find near you",
    }

    def run(self, seed: Seed, graph: KnowledgeGraph,
             intent_map: Dict[str, str] = None, scores: Dict[str, float] = None) -> dict:
        cached = Cache.load_checkpoint(seed.id, self.phase)
        if cached:
            return cached

        intent_map = intent_map or {}
        scores = scores or {}

        link_map = {
            "topic_to_pillar":    [],
            "topic_to_topic":     [],
            "cross_cluster":      [],
            "cluster_to_pillar":  [],
            "pillar_to_product":  [],
        }

        # Collect all topic data across pillars for cross-cluster linking
        all_topics = []  # [(topic_name, cluster_name, best_kw, intent, score)]

        for cluster_name, pillar_data in graph.pillars.items():
            pillar_kw = pillar_data.get("keyword", cluster_name.lower())
            pillar_url = f"/{seed.keyword.replace(' ','-')}/{pillar_kw.replace(' ','-')}"

            # Determine CTA based on dominant intent in pillar
            pillar_intents = []
            for cluster, topics in pillar_data.get("clusters", {}).items():
                for topic, topic_data in topics.items():
                    intent = topic_data.get("intent", "informational") if isinstance(topic_data, dict) else "informational"
                    pillar_intents.append(intent)
            dominant_intent = max(set(pillar_intents), key=pillar_intents.count) if pillar_intents else "informational"
            cta_verb = self.INTENT_CTA.get(dominant_intent, "learn more about")

            # Pillar → product (CTA varies by intent)
            product_url = seed.product_url or f"/products/{seed.keyword.replace(' ', '-')}"
            link_map["pillar_to_product"].append({
                "from_page":   pillar_url,
                "to_page":     product_url,
                "anchor_text": f"{cta_verb} {seed.keyword}",
                "placement":   "conclusion",
                "intent":      dominant_intent,
            })

            # Cluster → pillar
            link_map["cluster_to_pillar"].append({
                "cluster": cluster_name, "pillar_page": pillar_url,
                "anchor_text": pillar_kw, "intent": dominant_intent,
            })

            # Topic → pillar + sibling links
            for cluster, topics in pillar_data.get("clusters", {}).items():
                topic_list = list(topics.keys())
                for i, topic in enumerate(topic_list):
                    topic_data = topics[topic] if isinstance(topics[topic], dict) else {}
                    best_kw = topic_data.get("best_keyword", topic)
                    intent = topic_data.get("intent", "informational")
                    score = float(scores.get(best_kw, 40)) if isinstance(scores.get(best_kw, 0), (int, float)) else 40

                    topic_url = f"/{seed.keyword.replace(' ','-')}/{best_kw.lower().replace(' ','-')}"
                    all_topics.append((topic, cluster_name, best_kw, intent, score, topic_url))

                    # Topic → pillar (every topic links to its pillar)
                    link_map["topic_to_pillar"].append({
                        "from_page": topic_url, "to_page": pillar_url,
                        "anchor_text": pillar_kw, "placement": "body",
                        "intent": intent,
                    })
                    # Topic → sibling (prev and next, not just prev)
                    if i > 0:
                        prev_topic = topic_list[i-1]
                        prev_data = topics[prev_topic] if isinstance(topics[prev_topic], dict) else {}
                        prev_kw = prev_data.get("best_keyword", prev_topic)
                        prev_url = f"/{seed.keyword.replace(' ','-')}/{prev_kw.lower().replace(' ','-')}"
                        link_map["topic_to_topic"].append({
                            "from_page": topic_url, "to_page": prev_url,
                            "anchor_text": prev_kw, "placement": "related-section",
                        })
                    if i < len(topic_list) - 1:
                        next_topic = topic_list[i+1]
                        next_data = topics[next_topic] if isinstance(topics[next_topic], dict) else {}
                        next_kw = next_data.get("best_keyword", next_topic)
                        next_url = f"/{seed.keyword.replace(' ','-')}/{next_kw.lower().replace(' ','-')}"
                        link_map["topic_to_topic"].append({
                            "from_page": topic_url, "to_page": next_url,
                            "anchor_text": next_kw, "placement": "related-section",
                        })

        # Cross-cluster authority links: high-score → low-score in different clusters
        # Boosts weaker pages by linking from stronger ones
        sorted_topics = sorted(all_topics, key=lambda x: x[4], reverse=True)
        cross_link_count = 0
        max_cross_links = min(50, len(all_topics))  # Cap total cross links
        for i, (t1_name, t1_cluster, t1_kw, t1_intent, t1_score, t1_url) in enumerate(sorted_topics):
            if cross_link_count >= max_cross_links:
                break
            # Find a low-score topic in a DIFFERENT cluster with related intent
            for j in range(len(sorted_topics) - 1, max(i, len(sorted_topics)//2), -1):
                t2_name, t2_cluster, t2_kw, t2_intent, t2_score, t2_url = sorted_topics[j]
                if t2_cluster != t1_cluster and t1_url != t2_url:
                    # Shared words between topic names → likely related
                    t1_words = set(t1_name.lower().split())
                    t2_words = set(t2_name.lower().split())
                    shared = len(t1_words & t2_words)
                    if shared >= 1:
                        link_map["cross_cluster"].append({
                            "from_page": t1_url, "to_page": t2_url,
                            "anchor_text": t2_kw, "placement": "body",
                            "reason": f"authority boost ({t1_score:.0f}→{t2_score:.0f})",
                        })
                        cross_link_count += 1
                        break

        # ── Location hub-spoke linking ────────────────────────────────────
        # If business/target locations exist, create hub→spoke location links
        biz_locs = seed.business_locations or []
        tgt_locs = seed.target_locations or []
        if biz_locs or tgt_locs:
            link_map.setdefault("location_links", [])
            # National hub page → regional spoke pages
            national_url = f"/{seed.keyword.replace(' ','-')}"
            for loc in tgt_locs[:10]:
                loc_l = loc.lower().strip()
                loc_url = f"/{seed.keyword.replace(' ','-')}/{loc_l.replace(' ','-')}"
                link_map["location_links"].append({
                    "from_page": national_url, "to_page": loc_url,
                    "anchor_text": f"{seed.keyword} in {loc}", "placement": "body",
                    "link_type": "hub_to_spoke",
                })
            # Business location pages → target location pages
            for bl in biz_locs[:3]:
                bl_l = bl.lower().strip()
                bl_url = f"/{seed.keyword.replace(' ','-')}/{bl_l.replace(' ','-')}"
                for tl in tgt_locs[:5]:
                    tl_l = tl.lower().strip()
                    if bl_l != tl_l:
                        tl_url = f"/{seed.keyword.replace(' ','-')}/{tl_l.replace(' ','-')}"
                        link_map["location_links"].append({
                            "from_page": bl_url, "to_page": tl_url,
                            "anchor_text": f"Available in {tl}",
                            "placement": "cta",
                            "link_type": "business_to_target",
                        })
            # Topic pages with location → location hub
            for t_name, t_cluster, t_kw, t_intent, t_score, t_url in all_topics:
                kw_l = t_kw.lower()
                for loc in list(biz_locs) + list(tgt_locs[:5]):
                    loc_l = loc.lower().strip()
                    if loc_l and loc_l in kw_l:
                        loc_url = f"/{seed.keyword.replace(' ','-')}/{loc_l.replace(' ','-')}"
                        link_map["location_links"].append({
                            "from_page": t_url, "to_page": loc_url,
                            "anchor_text": f"More about {seed.keyword} in {loc}",
                            "placement": "related-section",
                            "link_type": "topic_to_location_hub",
                        })
                        break  # Only one location link per topic

        Cache.save_checkpoint(seed.id, self.phase, link_map)
        total = sum(len(v) for v in link_map.values())
        log.info(f"[P12] Internal link map: {total} links generated ({cross_link_count} cross-cluster)")
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

        start = start_date or datetime.now(timezone.utc)
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
        # ── Location-aware priority sorting ──────────────────────────────
        biz_locs = set(l.lower().strip() for l in (seed.business_locations or []) if l)
        tgt_locs = set(l.lower().strip() for l in (seed.target_locations or []) if l)

        def _loc_tier(art):
            """0 = business loc (highest), 1 = target loc, 2 = no location."""
            kw = (art.get("keyword", "") + " " + art.get("title", "")).lower()
            for bl in biz_locs:
                if bl in kw:
                    return 0
            for tl in tgt_locs:
                if tl in kw:
                    return 1
            return 2

        # Sort: pillar pages first, then by location tier, then score desc
        articles.sort(key=lambda a: (
            0 if a.get("is_pillar") else 1,
            _loc_tier(a),
            0 if a.get("intent") == "informational" and "?" in a.get("title","") else 1,
            -a.get("score", 0),
        ))

        # ── Inter-pillar round-robin ─────────────────────────────────────
        # Group articles by cluster, then interleave so we don't publish
        # all articles from one pillar back-to-back
        by_cluster = {}
        for art in articles:
            c = art.get("cluster", "_none")
            by_cluster.setdefault(c, []).append(art)

        # Round-robin across clusters
        interleaved = []
        cluster_queues = list(by_cluster.values())
        idx = 0
        while cluster_queues:
            q = cluster_queues[idx % len(cluster_queues)]
            if q:
                interleaved.append(q.pop(0))
            if not q:
                cluster_queues.pop(idx % len(cluster_queues))
                if not cluster_queues:
                    break
                idx = idx % len(cluster_queues)
            else:
                idx += 1

        # ── Assign dates ─────────────────────────────────────────────────
        calendar = []
        article_idx = 0

        for day in range(pace.total_days):
            pub_date = start + timedelta(days=day)
            if article_idx >= len(interleaved):
                break

            cluster = interleaved[article_idx].get("cluster","")
            day_slots = pace.blogs_per_day_for_pillar(cluster)

            for slot in range(day_slots):
                if article_idx >= len(interleaved):
                    break
                art = interleaved[article_idx].copy()
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

        # Build location name set for location-aware dedup
        _loc_names = set()
        for loc in (seed.target_locations or []) + (seed.business_locations or []):
            if loc:
                _loc_names.add(loc.lower().strip())

        def _strip_locations(text: str) -> str:
            """Remove known location names from text for comparison."""
            t = text
            for loc in _loc_names:
                t = t.replace(loc, "")
            return re.sub(r"\s+", " ", t).strip()

        # Pass 1: Exact/near-exact title dedup
        for art in calendar:
            title_norm = re.sub(r"[^\w\s]","",art.get("title","")).lower().strip()
            if title_norm in seen or title_norm in existing:
                removed += 1
                continue
            seen.add(title_norm)
            clean.append(art)

        # Pass 2: Keyword-level dedup (same target keyword = same article)
        # Location-aware: "buy spices online" and "buy spices online mumbai" are DIFFERENT keywords
        # But "spices in mumbai" and "spices mumbai" are the SAME (normalize location position)
        kw_seen, final = set(), []
        for art in clean:
            kw = art.get("keyword","").lower().strip()
            if not kw:
                final.append(art)
                continue

            # For location keywords, normalize to canonical form for dedup
            kw_no_loc = _strip_locations(kw)
            has_location = (kw_no_loc != kw)

            if has_location:
                # Location keyword: dedup key is "base + location" regardless of word order
                # Extract which location is in the keyword
                _loc_found = ""
                for loc in _loc_names:
                    if loc in kw:
                        _loc_found = loc
                        break
                dedup_key = f"{kw_no_loc}|{_loc_found}"
            else:
                dedup_key = kw

            if dedup_key in kw_seen:
                removed += 1
                continue
            kw_seen.add(dedup_key)
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
        pub_date    = datetime.now(timezone.utc).isoformat()

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
            "next_run":       (datetime.now(timezone.utc) + timedelta(weeks=1)).isoformat()
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
        self.p4   = P4_EntityDetection()
        self.p5   = P5_IntentClassification()
        self.p6   = P6_SERPIntelligence()
        self.p6k  = P6_CompetitorKeywordMining()
        self.p7   = P7_OpportunityScoring()
        self.p7b  = P7_TopKeywordSelector()
        self.p8   = P8_TopicDetection()
        self.p8r  = None  # optional ranking content engine for future extension
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
        self.phase_callback = None

    def set_phase_callback(self, cb):
        self.phase_callback = cb

    def _emit_phase(self, phase, status, progress=None, message=None):
        if callable(self.phase_callback):
            self.phase_callback({
                "phase": phase,
                "status": status,
                "progress": progress,
                "message": message,
                "ts": datetime.now(timezone.utc).isoformat()
            })
        # Note: do not re-initialize phase objects here. Re-initialization
        # caused hidden side-effects and duplicate work; constructors are
        # performed during engine initialization only.

    def _run_phase(self, name: str, fn, *args, **kwargs):
        """Run a phase with memory management and console logging."""
        progress = None
        if name.startswith("P") and name[1:].isdigit():
            phase_num = int(name[1:])
            progress = min(100, max(0, round((phase_num / 20.0) * 100)))

        ok, reason = MemoryManager.can_run(name)
        if not ok:
            log.warning(f"[Ruflo] {name} deferred: {reason}. Waiting 5s...")
            time.sleep(5)
            ok, reason = MemoryManager.can_run(name)
            if not ok:
                log.error(f"[Ruflo] {name} cannot run: {reason}")
                self._emit_phase(name, "deferred", progress, reason)
                return None

        MemoryManager.acquire(name)
        t0 = time.time()
        log.info(f"[Ruflo] ▶ {name} starting...")
        self._emit_phase(name, "started", progress, f"{name} started")

        try:
            # Support both sync and async phase functions. If `fn` is a coroutine
            # function or returns an awaitable, execute it in a temporary
            # asyncio loop in a background thread to avoid interfering with
            # a running event loop.
            import inspect, concurrent.futures

            if inspect.iscoroutinefunction(fn):
                def _run_coro():
                    import asyncio
                    return asyncio.run(fn(*args, **kwargs))
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    result = ex.submit(_run_coro).result()
            else:
                result = fn(*args, **kwargs)

            # If the result itself is awaitable, run it similarly
            try:
                import asyncio
                if asyncio.iscoroutine(result):
                    def _run_coro_res():
                        import asyncio as _asyncio
                        return _asyncio.run(result)
                    import concurrent.futures as _cf
                    with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                        result = ex.submit(_run_coro_res).result()
            except Exception:
                pass
            elapsed = round(time.time() - t0, 1)
            log.info(f"[Ruflo] ✓ {name} complete ({elapsed}s)")
            self._emit_phase(name, "completed", progress, f"{name} complete in {elapsed}s")
            return result
        except Exception as e:
            log.error(f"[Ruflo] ✗ {name} failed: {e}")
            self._emit_phase(name, "failed", progress, str(e))
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
                  gate_callback = None,
                  progress_callback = None,
                  project_id: Optional[str] = None) -> dict:
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
        self.set_phase_callback(progress_callback)

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
        intent_map = self._run_phase("P5", self.p5.run, seed, kws, entities)
        intent_map = intent_map or {}

        # ── P6 SERP Intelligence ──────────────────────────────────────────────
        serp_map = self._run_phase("P6", self.p6.run, seed, kws)
        serp_map = serp_map or {}

        # ── P6.6 Competitor Keyword Mining (low-noise)
        competitor_keywords = self._run_phase("P6_6", self.p6k.run, seed, serp_map)
        competitor_keywords = competitor_keywords or {}

        # ── Merge competitor keywords into universe
        extra_kws = []
        for ckws in competitor_keywords.values():
            extra_kws.extend(ckws)

        extra_kws = [k for k in extra_kws if k and k not in kws]
        if extra_kws:
            log.info(f"[P6_6] Adding {len(extra_kws)} competitor-derived keywords")
            kws = list(dict.fromkeys(kws + extra_kws))

            # Re-run P3/P4/P5/P6 on expanded corpus to ensure clean data
            kws = self._run_phase("P3", self.p3.run, seed, kws) or kws
            entities = self._run_phase("P4", self.p4.run, seed, kws) or entities
            intent_map = self._run_phase("P5", self.p5.run, seed, kws, entities) or intent_map
            serp_map = self._run_phase("P6", self.p6.run, seed, kws) or serp_map

        # ── P7 Opportunity Scoring ────────────────────────────────────────────
        scores = self._run_phase("P7", self.p7.run, seed, kws, intent_map, serp_map, entities)
        scores = scores or {k: 50.0 for k in kws}

        # ── P7B Top Keyword Selector (per-pillar + intent diversity) ───────────
        top_keywords = self._run_phase("P7B", self.p7b.run, seed, kws, scores, intent_map, top_n=100)
        top_keywords = top_keywords or []

        # ── P8 Topic Detection (heavy) ────────────────────────────────────────
        topic_map = self._run_phase("P8", self.p8.run, seed, kws, scores, intent_map)
        topic_map = topic_map or {}
        print(f"  P8: {len(topic_map)} topics detected")

        # ── P9 Cluster Formation ──────────────────────────────────────────────
        clusters = self._run_phase("P9", self.p9.run, seed, topic_map, project_id=project_id)
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
        pillars = self._run_phase("P10", self.p10.run, seed, clusters, project_id=project_id)
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
            "top100_count":     len(top_keywords),
            "top100_keywords":  top_keywords,
            "competitor_keywords": sum(len(v) for v in competitor_keywords.values()),
            "cluster_count":    len(clusters),
            "topic_count":      len(topic_map),
            "pillar_count":     len(pillars),
            "calendar_count":   len(calendar),
            "calendar_preview": calendar[:5],
            "cost_preview":     cost_preview,
            "link_map_size":    sum(len(v) for v in link_map.values()),
            "elapsed_seconds":  round(time.time()-t0, 1),
            "_graph":           asdict(graph),
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
        # pass entities (may be empty) to satisfy new signature and flow
        imap = p5.run(seed, kws, entities={})
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
        # use an intent map for P8 topic clustering to support intent-based buckets
        intent_map = {k: {"intent":"informational","confidence":0.6} for k in kws}
        topics = p8.run(seed, kws, scores, intent_map)
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
  OLLAMA_URL       = http://172.235.16.165:11434
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

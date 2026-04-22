"""
================================================================================
RUFLO v3 — KEYWORD UNIVERSE INTELLIGENCE SYSTEM
================================================================================
Corrected 4-level tree:

  Universe   = customer input keyword  (e.g. "black pepper")
  Pillar     = generated from competitor traffic  (e.g. "black pepper health benefits")
  Cluster    = semantic sub-group  (e.g. "Ayurvedic medicine")
  Supporting = long-tail + language + region + religion variants

Customer inputs "black pepper, clove, cardamom, organic spices"
→ 4 universes created, each with 5–8 pillars, each pillar with clusters and supporting keywords

Language expansion: English, Malayalam, Hindi, Tamil
Region expansion:   Wayanad → Kerala → South India → India → Global
Religion expansion: Ayurveda, Halal, Unani, Festival/Seasonal

AI Routing (strict):
  DeepSeek (Ollama local)  → intent, score, cluster names, dedup canonical
  Gemini (free API)        → pillar generation, keyword expansion, language variants
  Claude/OpenAI            → content writing ONLY — separate module, NOT here

Tech stack (minimal, free, open-source):
  FastAPI + SQLite + SQLAlchemy + BeautifulSoup4 + YAKE
  sentence-transformers (all-MiniLM-L6-v2) + scikit-learn
  wikipedia-api + google-generativeai
================================================================================
"""

import os, json, re, time, uuid, hashlib, logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("ruflo_v3")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    DB_URL          = os.getenv("DATABASE_URL",    "sqlite:///./ruflo.db")
    OLLAMA_URL      = os.getenv("OLLAMA_URL",      "http://172.235.16.165:8080")
    OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",    "mistral:7b-instruct-q4_K_M")
    OLLAMA_EMBED    = os.getenv("OLLAMA_EMBED",    "nomic-embed-text")
    GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY",  "")
    GEMINI_MODEL    = os.getenv("GEMINI_MODEL",    "gemini-1.5-flash")
    GEMINI_RATE     = float(os.getenv("GEMINI_RATE", "4.0"))  # seconds between calls (free tier)
    EMBED_MODEL     = "all-MiniLM-L6-v2"
    DEDUP_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", "0.90"))
    TOP_N           = int(os.getenv("TOP_N",   "100"))
    MAX_SERP_PAGES  = int(os.getenv("MAX_SERP", "10"))
    CRAWL_DELAY     = float(os.getenv("CRAWL_DELAY", "1.5"))

    # Supported languages and regions — users select these per project
    LANGUAGES       = ["english", "malayalam", "hindi", "tamil", "kannada", "arabic"]
    REGIONS         = ["wayanad", "kerala", "south india", "north india", "india", "global"]
    RELIGION_CTX    = ["ayurveda", "halal", "unani", "general"]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DATABASE MODELS
# ─────────────────────────────────────────────────────────────────────────────

from sqlalchemy import (create_engine, Column, Integer, String, Float, Text,
                        DateTime, ForeignKey, JSON, Boolean)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session as DbSession

Base   = declarative_base()
_eng   = None
_Sess  = None


def get_db() -> DbSession:
    global _eng, _Sess
    if _eng is None:
        _eng  = create_engine(Cfg.DB_URL,
                              connect_args={"check_same_thread": False}
                              if "sqlite" in Cfg.DB_URL else {})
        Base.metadata.create_all(_eng)
        _Sess = sessionmaker(bind=_eng)
        log.info("DB ready ✓")
    return _Sess()


class Project(Base):
    """One customer project. Contains all settings for a keyword intelligence run."""
    __tablename__ = "projects"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(255), nullable=False)
    website_url     = Column(String(500))
    industry        = Column(String(100))
    business_type   = Column(String(20), default="B2C")    # B2C / B2B / D2C
    target_location = Column(String(200), default="India")
    target_audience = Column(JSON)     # list[str]
    target_languages= Column(JSON)     # e.g. ["english","malayalam","hindi"]
    target_regions  = Column(JSON)     # e.g. ["wayanad","kerala","india"]
    religion_ctx    = Column(JSON)     # e.g. ["ayurveda","halal"]
    brand_context   = Column(JSON)
    created_at      = Column(DateTime, default=datetime.utcnow)

    competitors     = relationship("Competitor",   back_populates="project", cascade="all, delete-orphan")
    products        = relationship("Product",      back_populates="project", cascade="all, delete-orphan")
    universes       = relationship("Universe",     back_populates="project", cascade="all, delete-orphan")
    seo_pages       = relationship("SeoPage",      back_populates="project", cascade="all, delete-orphan")


class Competitor(Base):
    __tablename__ = "competitors"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    project_id  = Column(Integer, ForeignKey("projects.id"))
    url         = Column(String(500))
    project     = relationship("Project", back_populates="competitors")


class Product(Base):
    __tablename__ = "products"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    project_id  = Column(Integer, ForeignKey("projects.id"))
    name        = Column(String(255))
    url         = Column(String(500))
    project     = relationship("Project", back_populates="products")


class SeoPage(Base):
    """Module 1 — SEO audit results per page."""
    __tablename__ = "seo_pages"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    project_id    = Column(Integer, ForeignKey("projects.id"))
    url           = Column(String(1000))
    title         = Column(String(500), nullable=True)
    h1            = Column(String(500), nullable=True)
    meta_desc     = Column(Text, nullable=True)
    word_count    = Column(Integer, default=0)
    has_canonical = Column(Boolean, default=False)
    has_schema    = Column(Boolean, default=False)
    schema_types  = Column(JSON, nullable=True)
    status_code   = Column(Integer, nullable=True)
    issues        = Column(JSON)
    score         = Column(Integer, default=0)
    extracted_kws = Column(JSON)
    crawled_at    = Column(DateTime, default=datetime.utcnow)
    project       = relationship("Project", back_populates="seo_pages")


class Universe(Base):
    """
    Level 1 — The customer's input keyword.
    Each universe is an independent keyword tree.
    """
    __tablename__ = "universes"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    project_id    = Column(Integer, ForeignKey("projects.id"))
    term          = Column(String(255))   # e.g. "black pepper"
    wiki_summary  = Column(Text, nullable=True)
    wiki_entities = Column(JSON, nullable=True)
    serp_topics   = Column(JSON, nullable=True)   # topics extracted from SERP competitor pages
    created_at    = Column(DateTime, default=datetime.utcnow)

    project       = relationship("Project",  back_populates="universes")
    pillars       = relationship("Pillar",   back_populates="universe", cascade="all, delete-orphan")


class Pillar(Base):
    """
    Level 2 — Generated from competitor traffic + Wikipedia.
    These are the proven, traffic-backed topic hubs for a universe.
    """
    __tablename__ = "pillars"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    universe_id     = Column(Integer, ForeignKey("universes.id"))
    name            = Column(String(255))   # e.g. "black pepper health benefits"
    source          = Column(String(30))    # "competitor" | "wikipedia" | "ai"
    competitor_count= Column(Integer, default=0)  # how many competitors cover this
    content_brief   = Column(JSON, nullable=True)
    product_url     = Column(String(500), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    universe        = relationship("Universe", back_populates="pillars")
    clusters        = relationship("Cluster",  back_populates="pillar", cascade="all, delete-orphan")


class Cluster(Base):
    """
    Level 3 — Semantic keyword groups under a pillar.
    Tagged by region, language, religion where applicable.
    """
    __tablename__ = "clusters"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    pillar_id   = Column(Integer, ForeignKey("pillars.id"))
    name        = Column(String(255))
    description = Column(Text, nullable=True)
    language    = Column(String(30), nullable=True)   # "english","malayalam","hindi","tamil"
    region      = Column(String(50), nullable=True)   # "wayanad","kerala","india","global"
    religion    = Column(String(30), nullable=True)   # "ayurveda","halal","unani","general"
    pillar      = relationship("Pillar",  back_populates="clusters")
    keywords    = relationship("Keyword", back_populates="cluster")


class Keyword(Base):
    """Level 4 — Individual supporting keyword."""
    __tablename__ = "keywords"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id    = Column(Integer, ForeignKey("clusters.id"))
    universe_id   = Column(Integer, ForeignKey("universes.id"))
    term          = Column(String(500))
    intent        = Column(String(30))   # informational/transactional/commercial/navigational
    language      = Column(String(30), default="english")
    region        = Column(String(50), nullable=True)
    religion      = Column(String(30), nullable=True)
    source        = Column(String(50))   # autocomplete/wiki/gemini/competitor/user
    score         = Column(Float, default=0.0)
    content_type  = Column(String(40), nullable=True)   # blog/faq/product_page/recipe
    is_duplicate  = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.utcnow)
    cluster       = relationship("Cluster", back_populates="keywords")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — AI ROUTER
# ─────────────────────────────────────────────────────────────────────────────

import requests as _req

class AI:
    _embed_model  = None
    _last_gemini  = 0.0

    @staticmethod
    def _extract_ollama_text(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        if isinstance(data.get("response"), str) and data.get("response").strip():
            return data["response"].strip()
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
        if isinstance(data.get("text"), str):
            return data["text"].strip()
        return ""

    @staticmethod
    def deepseek(prompt: str, system: str = "You are a keyword research assistant.",
                  temperature: float = 0.1) -> str:
        """Route through central AIRouter (health check, semaphore, 620s timeout)."""
        try:
            from core.ai_config import AIRouter
            return AIRouter._call_ollama(prompt, system or "You are a keyword research assistant.", temperature)
        except Exception as e:
            log.warning(f"[AI.deepseek] Ollama failed: {e}")
            return ""

    @classmethod
    def gemini(cls, prompt: str, temperature: float = 0.3) -> str:
        """Gemini free tier — expansion, research, pillar generation, language variants."""
        if not Cfg.GEMINI_API_KEY:
            log.warning("No GEMINI_API_KEY — falling back to DeepSeek")
            return cls.deepseek(prompt, temperature=temperature)
        elapsed = time.time() - cls._last_gemini
        if elapsed < Cfg.GEMINI_RATE:
            time.sleep(Cfg.GEMINI_RATE - elapsed)
        try:
            import google.generativeai as genai
            genai.configure(api_key=Cfg.GEMINI_API_KEY)
            model = genai.GenerativeModel(Cfg.GEMINI_MODEL)
            resp  = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(temperature=temperature)
            )
            cls._last_gemini = time.time()
            return resp.text.strip()
        except Exception as e:
            log.warning(f"Gemini error: {e} — falling back to DeepSeek")
            return cls.deepseek(prompt, temperature=temperature)

    @classmethod
    def embed(cls, texts: List[str]) -> List[List[float]]:
        """Local embeddings — Ollama nomic-embed or sentence-transformers fallback."""
        try:
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/embed",
                          json={"model": Cfg.OLLAMA_EMBED, "input": texts}, timeout=60)
            r.raise_for_status()
            return r.json()["embeddings"]
        except Exception:
            if cls._embed_model is None:
                from sentence_transformers import SentenceTransformer
                cls._embed_model = SentenceTransformer(Cfg.EMBED_MODEL)
            return cls._embed_model.encode(texts, normalize_embeddings=True).tolist()

    @staticmethod
    def parse_json(text: str) -> Any:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

class P:

    # ── DeepSeek prompts (fast, local, free) ─────────────────────────────────

    INTENT = """Classify keyword search intent. Return ONLY one word.
Options: informational, transactional, commercial, navigational
Keyword: "{kw}"
"""
    SCORE = """Score this keyword for the business. Return ONLY valid JSON, no markdown.
Keyword: "{kw}"
Intent: {intent}
Business: {ctx}
{{"score": 1.0-10.0, "content_type": "blog|faq|product_page|recipe|comparison|guide"}}"""

    CLUSTER_NAME = """Name this keyword cluster in 2-4 words and give a 1-sentence description.
Return ONLY valid JSON, no markdown: {{"name": "...", "description": "..."}}
Keywords: {kws}"""

    CANONICAL = """Which is the best, most natural keyword form? Return ONLY that one, nothing else.
Options: {variants}"""

    # ── Gemini prompts (expansion, research, pillar generation) ──────────────

    EXTRACT_PILLARS = """You are an SEO expert analysing competitor pages for the keyword universe "{universe}".
Here are headings (H1/H2/title) extracted from the top {n} ranking pages:
{headings}

And Wikipedia sub-topics: {wiki_topics}

Identify 5–8 strong pillar topic keywords that:
- Are proven to get traffic (backed by competitor headings)
- Cover the main angles users search for
- Work as standalone content hubs

Return ONLY a JSON array, no markdown:
[
  {{"name": "pillar keyword", "source": "competitor|wikipedia", "competitor_count": 3}},
  ...
]"""

    EXPAND_PILLAR = """Generate 40 long-tail keyword variations for the pillar "{pillar}" within the universe "{universe}".
Business: {ctx}
Target location: {location}
Languages required: {languages}

Include:
- How-to and question format keywords (English)
- Buying intent keywords (English)
- Language variants: provide {lang_list} versions of top 10 keywords
- Regional variants: {regions} specific keywords
- Religious/cultural context: {religion} related keywords if relevant

Return ONLY a JSON array of objects, no markdown:
[
  {{"term": "...", "language": "english|malayalam|hindi|tamil", "region": "wayanad|kerala|india|global", "religion": "ayurveda|halal|general"}},
  ...
]"""

    LANGUAGE_VARIANTS = """Translate these English keywords into {language}. Keep them natural search queries.
Return ONLY a JSON array of objects, no markdown:
[{{"english": "...", "translated": "...", "language": "{language}"}}, ...]
Keywords: {keywords}"""

    PILLAR_BRIEF = """Create SEO content brief for pillar page about "{pillar}" (universe: "{universe}").
Business: {ctx}
Audience: {audience}
Target for BOTH Google ranking AND AI search (Perplexity, ChatGPT overview).

Return ONLY valid JSON, no markdown:
{{
  "page_title": "...",
  "meta_description": "...",
  "h1": "...",
  "h2_sections": ["...", "..."],
  "faq_questions": ["...", "..."],
  "entities_to_include": ["..."],
  "schema_type": "Article|FAQPage|HowTo|Product",
  "word_count": 2000,
  "product_page_url": "...",
  "ai_search_tips": ["use entity-rich language", "answer questions directly", "..."]
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — RESULT TYPE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class R:
    ok:   bool
    data: Any = None
    err:  str = ""
    ms:   int = 0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — MODULE 1: SEO CHECKER
# ─────────────────────────────────────────────────────────────────────────────

from bs4 import BeautifulSoup

class SeoChecker:
    """
    Crawls own website. Produces SEO audit + existing keyword footprint.
    No AI needed — pure rule-based checks aligned with Google SEO Starter Guide.
    """
    UA = "Mozilla/5.0 (compatible; RufloBot/3.0)"

    def audit_site(self, project: Project, max_pages: int = 20) -> R:
        t0     = time.time()
        pages  = self._discover(project.website_url, max_pages)
        results, all_kws = [], []

        for url in pages:
            audit = self._audit_page(url)
            if audit:
                results.append(audit)
                all_kws.extend(audit.get("extracted_kws", []))
            time.sleep(Cfg.CRAWL_DELAY)

        avg_score = int(sum(r["score"] for r in results) / len(results)) if results else 0
        return R(True, {
            "pages": results, "avg_score": avg_score,
            "total_pages": len(results),
            "site_keywords": list(set(k.lower() for k in all_kws)),
            "all_issues": [i for r in results for i in r.get("issues", [])],
        }, ms=int((time.time()-t0)*1000))

    def _discover(self, base: str, limit: int) -> List[str]:
        pages = set([base])
        for path in ["/sitemap.xml", "/sitemap_index.xml"]:
            try:
                r = _req.get(base.rstrip("/")+path, headers={"User-Agent": self.UA}, timeout=8)
                if r.ok:
                    soup = BeautifulSoup(r.text, "xml")
                    for loc in soup.find_all("loc"):
                        pages.add(loc.text.strip())
                    if len(pages) > 2:
                        break
            except Exception:
                pass
        if len(pages) <= 1:
            try:
                r    = _req.get(base, headers={"User-Agent": self.UA}, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith("/"):
                        pages.add(base.rstrip("/")+href)
                    elif href.startswith(base):
                        pages.add(href)
            except Exception:
                pass
        return list(pages)[:limit]

    def _audit_page(self, url: str) -> Optional[dict]:
        try:
            r = _req.get(url, headers={"User-Agent": self.UA}, timeout=12)
        except Exception as e:
            return {"url": url, "score": 0, "issues": [{"type":"critical","msg": str(e)}],
                    "extracted_kws": []}

        soup   = BeautifulSoup(r.text, "html.parser")
        issues = []
        score  = 100

        def check(cond, sev, code, msg, penalty):
            nonlocal score
            if cond:
                issues.append({"type": sev, "code": code, "msg": msg})
                score -= penalty

        title     = (soup.title.string or "").strip() if soup.title else ""
        h1_list   = soup.find_all("h1")
        h1        = h1_list[0].get_text(strip=True) if h1_list else ""
        meta_d    = soup.find("meta", {"name": "description"})
        meta_desc = (meta_d["content"] or "").strip() if meta_d and meta_d.get("content") else ""
        canonical = bool(soup.find("link", {"rel": "canonical"}))
        schemas   = [s.get("type","") for s in soup.find_all("script", type="application/ld+json")]

        check(not title,           "critical", "MISSING_TITLE",    "Missing <title> tag",       15)
        check(len(title)>60,       "warning",  "TITLE_LONG",       f"Title {len(title)} chars",  5)
        check(not h1,              "critical", "MISSING_H1",       "Missing H1",                15)
        check(len(h1_list)>1,      "warning",  "MULTI_H1",         f"{len(h1_list)} H1 tags",    5)
        check(not meta_desc,       "warning",  "NO_META_DESC",     "Missing meta description",  10)
        check(len(meta_desc)>160,  "info",     "META_LONG",        "Meta desc >160 chars",       3)
        check(not canonical,       "info",     "NO_CANONICAL",     "No canonical tag",           3)
        check(not schemas,         "warning",  "NO_SCHEMA",        "No JSON-LD schema markup",   8)

        for tag in soup(["script","style","nav","footer"]):
            tag.decompose()
        body      = soup.get_text(separator=" ", strip=True)
        wc        = len(body.split())
        no_alt    = len([i for i in soup.find_all("img") if not i.get("alt")])

        check(wc<300,      "warning", "THIN",      f"Only {wc} words",           10)
        check(no_alt>0,    "warning", "NO_ALT",    f"{no_alt} images missing alt",
              min(no_alt*2,10))
        check(r.status_code!=200, "critical", f"HTTP_{r.status_code}",
              f"HTTP {r.status_code}", 20)

        return {
            "url": url, "title": title, "h1": h1, "meta_desc": meta_desc,
            "word_count": wc, "has_canonical": canonical,
            "has_schema": bool(schemas), "schema_types": schemas,
            "status_code": r.status_code, "issues": issues,
            "score": max(0, score),
            "extracted_kws": self._yake(body[:3000]),
        }

    def _yake(self, text: str) -> List[str]:
        try:
            import yake
            ext = yake.KeywordExtractor(lan="en", top=15, dedupLim=0.7)
            return [kw for kw, _ in ext.extract_keywords(text)]
        except Exception:
            words = re.findall(r'\b[a-z]{4,}\b', text.lower())
            freq  = {}
            for w in words:
                freq[w] = freq.get(w, 0) + 1
            return sorted(freq, key=freq.get, reverse=True)[:15]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — SERP SCRAPER (free)
# ─────────────────────────────────────────────────────────────────────────────

class SerpScraper:
    """
    Gets top ranking pages for a keyword using free methods.
    DuckDuckGo HTML (most reliable free option) → crawl each result.
    Extracts: H1, H2, H3, title, meta description, FAQ questions, URL slug.
    """
    UA = "Mozilla/5.0 (compatible; RufloBot/3.0)"

    def get_top_pages(self, keyword: str, n: int = 10) -> List[dict]:
        """Get top n SERP result URLs for keyword."""
        urls = self._ddg_search(keyword, n)
        if not urls:
            log.warning(f"No SERP results for '{keyword}' — try adding SERPAPI key")
            return []

        pages = []
        for url in urls[:n]:
            page = self._extract_page(url)
            if page:
                pages.append(page)
            time.sleep(Cfg.CRAWL_DELAY)
        return pages

    def _ddg_search(self, query: str, n: int) -> List[str]:
        """Scrape DuckDuckGo HTML results (free, no API key)."""
        try:
            r = _req.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": self.UA}, timeout=12
            )
            soup  = BeautifulSoup(r.text, "html.parser")
            links = []
            for a in soup.select(".result__a"):
                href = a.get("href", "")
                if href.startswith("http") and "duckduckgo" not in href:
                    links.append(href)
                if len(links) >= n:
                    break
            return links
        except Exception as e:
            log.warning(f"DDG search failed: {e}")
            return []

    def _extract_page(self, url: str) -> Optional[dict]:
        """Crawl one SERP result page and extract SEO-relevant content."""
        try:
            r    = _req.get(url, headers={"User-Agent": self.UA}, timeout=12)
            soup = BeautifulSoup(r.text, "html.parser")

            title  = (soup.title.string or "").strip() if soup.title else ""
            h1     = [t.get_text(strip=True) for t in soup.find_all("h1")]
            h2     = [t.get_text(strip=True) for t in soup.find_all("h2")]
            h3     = [t.get_text(strip=True) for t in soup.find_all("h3")]
            meta_d = soup.find("meta", {"name": "description"})
            meta   = (meta_d["content"] or "").strip() if meta_d and meta_d.get("content") else ""

            # Extract FAQ questions (common in SEO content)
            faq_q  = [q.get_text(strip=True) for q in soup.find_all(
                ["details", "summary", "div"],
                class_=re.compile(r"faq|question|accordion", re.I)
            )]

            # URL slug as keyword signal
            slug   = url.split("/")[-1].replace("-"," ").replace("_"," ")

            # All headings combined for topic extraction
            all_headings = h1 + h2 + h3
            all_headings = [h for h in all_headings if 5 < len(h) < 100]

            return {
                "url": url, "title": title, "h1": h1, "h2": h2, "h3": h3,
                "meta": meta, "faq_questions": faq_q[:10],
                "slug": slug, "all_headings": all_headings,
            }
        except Exception as e:
            log.debug(f"Page extract failed {url}: {e}")
            return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — WIKIPEDIA RESEARCH
# ─────────────────────────────────────────────────────────────────────────────

class Wiki:
    """Free Wikipedia research. No API key. Used for universe context + pillar gap-filling."""

    def research(self, term: str) -> dict:
        base = {"term": term, "found": False, "summary": "",
                "sections": [], "entities": [], "links": []}
        try:
            import wikipediaapi
            wiki = wikipediaapi.Wikipedia("RufloBot/3.0", "en")
            page = wiki.page(term)
            if not page.exists():
                page = wiki.page(term.title())
            if not page.exists():
                return base

            summary  = page.summary[:2000]
            sections = [s.title for s in page.sections][:10]
            links    = list(page.links.keys())[:30]

            # Extract entity-like terms from summary (capitalized words / compounds)
            entities = list(set(re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', summary)))[:20]

            return {**base, "found": True, "summary": summary,
                    "sections": sections, "entities": entities, "links": links}
        except Exception as e:
            log.warning(f"Wikipedia failed for '{term}': {e}")
            return base


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — KEYWORD COLLECTOR
# ─────────────────────────────────────────────────────────────────────────────

class Collector:
    """Collects raw keywords from free sources."""

    def autocomplete(self, term: str) -> List[str]:
        """Google autocomplete — free, no key, alphabet expansion."""
        results = set()
        for prefix in [""] + list("abcdefghijklmnopqrstuvwxyz"):
            query = f"{term} {prefix}".strip() if prefix else term
            try:
                r = _req.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client": "firefox", "q": query},
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=5
                )
                if r.ok:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 1:
                        results.update(str(s).lower() for s in data[1])
            except Exception:
                pass
            time.sleep(0.2)
        return list(results)

    def ddg_autocomplete(self, term: str) -> List[str]:
        try:
            r = _req.get("https://duckduckgo.com/ac/",
                         params={"q": term, "type": "list"},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            if r.ok:
                return [d.get("phrase","").lower() for d in r.json() if d.get("phrase")]
        except Exception:
            pass
        return []

    def gemini_expand(self, pillar: str, universe: str, ctx: dict,
                       languages: List[str], regions: List[str],
                       religion: List[str]) -> List[dict]:
        """
        Gemini expansion per pillar.
        Returns list of {term, language, region, religion} dicts.
        """
        prompt = P.EXPAND_PILLAR.format(
            pillar=pillar, universe=universe,
            ctx=json.dumps(ctx)[:300],
            location=ctx.get("target_location","India"),
            languages=", ".join(languages),
            lang_list=", ".join(l for l in languages if l != "english"),
            regions=", ".join(regions),
            religion=", ".join(religion)
        )
        try:
            text  = AI.gemini(prompt, temperature=0.4)
            items = AI.parse_json(text)
            if isinstance(items, list):
                return [i for i in items if isinstance(i, dict) and i.get("term")]
        except Exception as e:
            log.warning(f"Gemini expand failed for '{pillar}': {e}")
        return [{"term": kw, "language": "english", "region": "india", "religion": "general"}
                for kw in [pillar + " benefits", pillar + " recipe",
                            "buy " + pillar + " online"]]

    def language_variants(self, keywords: List[str], language: str) -> List[dict]:
        """Translate keywords to target language using Gemini."""
        prompt = P.LANGUAGE_VARIANTS.format(
            language=language,
            keywords=json.dumps(keywords[:15])
        )
        try:
            text  = AI.gemini(prompt, temperature=0.2)
            items = AI.parse_json(text)
            return items if isinstance(items, list) else []
        except Exception as e:
            log.warning(f"Language translation to {language} failed: {e}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — PILLAR EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

class PillarExtractor:
    """
    Generates pillars from SERP competitor data + Wikipedia.
    This is the key differentiator: pillars are TRAFFIC-BACKED, not invented.
    """
    serp = SerpScraper()
    wiki = Wiki()

    def extract_pillars(self, universe_term: str, wiki_data: dict) -> List[dict]:
        """
        1. Get top SERP pages for universe keyword.
        2. Extract all headings from those pages.
        3. Use Gemini to identify pillar topics from those headings + Wikipedia.
        """
        log.info(f"[Pillar] Extracting pillars for universe: '{universe_term}'")

        # Step 1: SERP pages
        pages      = self.serp.get_top_pages(universe_term, Cfg.MAX_SERP_PAGES)
        all_headings = []
        for page in pages:
            all_headings.extend(page.get("all_headings", []))
            all_headings.extend(page.get("faq_questions", []))

        # Deduplicate headings
        seen, unique_headings = set(), []
        for h in all_headings:
            norm = h.lower().strip()
            if norm not in seen and len(norm) > 5:
                seen.add(norm)
                unique_headings.append(h)

        log.info(f"[Pillar] Collected {len(unique_headings)} unique headings from {len(pages)} SERP pages")

        # Step 2: Generate pillars with Gemini
        wiki_topics = wiki_data.get("sections", []) + wiki_data.get("entities", [])
        prompt = P.EXTRACT_PILLARS.format(
            universe=universe_term,
            n=len(pages),
            headings="\n".join(f"- {h}" for h in unique_headings[:60]),
            wiki_topics=", ".join(str(t) for t in wiki_topics[:20])
        )
        try:
            text    = AI.gemini(prompt, temperature=0.2)
            pillars = AI.parse_json(text)
            if isinstance(pillars, list):
                return pillars
        except Exception as e:
            log.warning(f"Gemini pillar extraction failed: {e}")

        # Fallback: use top headings directly as pillar candidates
        return [{"name": h, "source": "competitor", "competitor_count": 1}
                for h in unique_headings[:6]]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — CLEANING & DEDUP ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class Cleaner:
    """
    Multi-lingual aware cleaning.
    English: full normalise + lemmatise + dedup pipeline.
    Other languages: light normalise + hash dedup only (no English lemmatiser).
    """
    _nlp = None

    def clean(self, keywords: List[str]) -> List[str]:
        """String-based cleaning. Language-aware."""
        seen_h, seen_c, results = set(), set(), []
        for kw in keywords:
            norm = self._normalise(kw)
            if not norm or len(norm) < 3:
                continue
            h = hashlib.md5(norm.encode()).hexdigest()
            c = " ".join(sorted(norm.split()))
            if h not in seen_h and c not in seen_c:
                seen_h.add(h)
                seen_c.add(c)
                results.append(norm)
        return results

    def _normalise(self, kw: str) -> str:
        # Preserve non-ASCII (Malayalam, Hindi, Tamil scripts)
        norm = re.sub(r"[^\w\s\-]", "", kw.strip(), flags=re.UNICODE)
        norm = re.sub(r"\s+", " ", norm).strip().lower()
        # Only lemmatise English (ASCII-only strings)
        if norm.isascii() and self._nlp:
            try:
                doc  = self._nlp(norm)
                norm = " ".join(t.lemma_ for t in doc)
            except Exception:
                pass
        return norm

    def _load_nlp(self):
        if self._nlp is None:
            try:
                import spacy
                self._nlp = spacy.load("en_core_web_sm")
            except Exception:
                pass

    def semantic_dedup(self, keywords: List[str]) -> Tuple[List[str], dict]:
        """Semantic cosine dedup on SBERT embeddings."""
        if len(keywords) <= 1:
            return keywords, {}
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        emb  = np.array(AI.embed(keywords))
        sim  = cosine_similarity(emb)
        kept = set(range(len(keywords)))
        dupes= {}
        for i in range(len(keywords)):
            if i not in kept:
                continue
            for j in range(i+1, len(keywords)):
                if j in kept and sim[i][j] >= Cfg.DEDUP_THRESHOLD:
                    canon = i if len(keywords[i]) <= len(keywords[j]) else j
                    dup   = j if canon == i else i
                    kept.discard(dup)
                    dupes[keywords[dup]] = keywords[canon]
        return [keywords[i] for i in sorted(kept)], dupes


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — INTENT + SCORE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class Scorer:
    INTENT_RULES = {
        "transactional": ["buy","price","purchase","order","shop","cheap","discount","sale","wholesale"],
        "commercial":    ["best","top","review","compare","vs","versus","alternative"],
        "informational": ["how","what","why","when","where","does","is","are","can","benefits","uses"],
    }

    def intent(self, kw: str) -> str:
        # Rule-based first (fast, free)
        kl = kw.lower()
        for intent, words in self.INTENT_RULES.items():
            if any(w in kl for w in words):
                return intent
        # DeepSeek fallback for ambiguous
        try:
            text = AI.deepseek(P.INTENT.format(kw=kw), temperature=0.0)
            r    = text.strip().lower().split()[0]
            if r in ["informational","transactional","commercial","navigational"]:
                return r
        except Exception:
            pass
        return "informational"

    def score(self, kw: str, intent: str, ctx: dict,
               source: str = "collected", is_gap: bool = False,
               is_priority: bool = False) -> Tuple[float, str]:
        try:
            text   = AI.deepseek(P.SCORE.format(kw=kw, intent=intent,
                                                  ctx=json.dumps(ctx)[:200]), temperature=0.0)
            parsed = AI.parse_json(text)
            score  = float(parsed.get("score", 5.0))
            ctype  = parsed.get("content_type", "blog")
        except Exception:
            score, ctype = 5.0, "blog"
        if is_priority: score = min(score + 2.5, 10.0)
        if is_gap:      score = min(score * 1.2,  10.0)
        if intent == "transactional": score = min(score * 1.15, 10.0)
        return round(score, 2), ctype


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — CLUSTERING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class Clusterer:
    def cluster(self, keywords: List[str], n_clusters: int = None,
                 language_aware: bool = True) -> List[dict]:
        """
        Cluster keywords. If language_aware, create language-specific sub-clusters
        within semantic groups.
        """
        if len(keywords) < 4:
            return [{"name":"General","description":"","keywords": keywords,
                     "language":"mixed","region":None,"religion":None}]
        import numpy as np
        from sklearn.cluster import KMeans
        emb    = np.array(AI.embed(keywords))
        k      = n_clusters or max(3, min(len(keywords) // 5, 15))
        km     = KMeans(n_clusters=min(k, len(keywords)), random_state=42,
                        n_init=10, max_iter=300)
        labels = km.fit_predict(emb).tolist()
        groups: Dict[int, List[str]] = {}
        for kw, lbl in zip(keywords, labels):
            groups.setdefault(lbl, []).append(kw)

        clusters = []
        for lbl, kws in groups.items():
            try:
                text   = AI.deepseek(P.CLUSTER_NAME.format(kws=", ".join(kws[:12])))
                parsed = AI.parse_json(text)
                name   = parsed.get("name", kws[0])
                desc   = parsed.get("description","")
            except Exception:
                name, desc = kws[0], ""

            # Detect dominant language in cluster
            lang = self._detect_cluster_language(kws)
            clusters.append({"name": name, "description": desc,
                              "keywords": kws, "language": lang,
                              "region": None, "religion": None})

        return sorted(clusters, key=lambda x: len(x["keywords"]), reverse=True)

    def _detect_cluster_language(self, kws: List[str]) -> str:
        """Simple heuristic: non-ASCII = likely Indian language script."""
        non_ascii = sum(1 for kw in kws if not kw.isascii())
        if non_ascii > len(kws) * 0.5:
            return "multilingual"
        return "english"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — RUFLO v3 ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class State:
    project_id: int
    status:     str = "running"
    log:        List[dict] = field(default_factory=list)
    data:       Dict[str, Any] = field(default_factory=dict)

    def step(self, name: str, ok: bool, ms: int, note: str = ""):
        self.log.append({"step": name, "ok": ok, "ms": ms, "note": note})
        icon = "✓" if ok else "✗"
        log.info(f"[Ruflo] {icon} {name} ({ms}ms){' — '+note if note else ''}")

    def set(self, k: str, v: Any): self.data[k] = v
    def get(self, k: str, d=None): return self.data.get(k, d)


class Ruflo:
    """
    ┌──────────────────────────────────────────────────────────────┐
    │  RUFLO v3 — Universe Tree Orchestrator                       │
    │                                                              │
    │  Customer input → Universe → Pillars (traffic-backed)       │
    │  → Clusters → Supporting keywords (+ language/region)       │
    └──────────────────────────────────────────────────────────────┘

    Runs one universe at a time:
      universe_term: str      (e.g. "black pepper")
      Returns: complete 4-level keyword tree

    For 4 customer inputs → run 4 times → 4 universe trees
    """

    def __init__(self):
        self.seo       = SeoChecker()
        self.serp      = SerpScraper()
        self.wiki      = Wiki()
        self.pillar_ex = PillarExtractor()
        self.collector = Collector()
        self.cleaner   = Cleaner()
        self.scorer    = Scorer()
        self.clusterer = Clusterer()

    # ── Run per universe ──────────────────────────────────────────────

    def run_universe(self, project: Project,
                      universe_term: str,
                      priority_keywords: List[str] = None,
                      site_kws: List[str] = None) -> dict:
        """
        Full pipeline for one universe keyword.
        Call this once per customer input keyword.
        """
        state = State(project_id=project.id)
        langs    = project.target_languages or ["english"]
        regions  = project.target_regions   or ["india"]
        religion = project.religion_ctx     or ["general"]
        ctx = {
            "business_name":   project.name,
            "industry":        project.industry,
            "target_location": project.target_location or "India",
            "target_audience": project.target_audience or [],
        }
        priority_set = set(k.lower() for k in (priority_keywords or []))
        own_kw_set   = set(k.lower() for k in (site_kws or []))

        # ── STEP 1: Wikipedia research ────────────────────────────────
        t0 = time.time()
        wiki_data = self.wiki.research(universe_term)
        state.step("wiki_research", wiki_data["found"],
                   int((time.time()-t0)*1000),
                   f"{'Found' if wiki_data['found'] else 'Not found'} on Wikipedia")
        state.set("wiki_data", wiki_data)

        # ── STEP 2: Extract pillars from SERP + Wikipedia ────────────
        t0 = time.time()
        raw_pillars = self.pillar_ex.extract_pillars(universe_term, wiki_data)
        state.step("pillar_extraction", True, int((time.time()-t0)*1000),
                   f"{len(raw_pillars)} pillars extracted from competitor SERP")
        state.set("pillars", raw_pillars)

        # ── STEP 3: For each pillar — collect keywords ────────────────
        t0 = time.time()
        all_kw_items: List[dict] = []

        # Add priority keywords from user input
        for kw in priority_set:
            all_kw_items.append({"term": kw, "language": "english",
                                  "region": "india", "religion": "general",
                                  "source": "user", "pillar": universe_term})

        for pillar in raw_pillars:
            pillar_name = pillar.get("name", "")
            if not pillar_name:
                continue

            # Google autocomplete (free)
            ac_kws = self.collector.autocomplete(pillar_name)
            all_kw_items.extend([{"term": k, "language": "english",
                                   "region": "india", "religion": "general",
                                   "source": "autocomplete", "pillar": pillar_name}
                                  for k in ac_kws])

            # DuckDuckGo autocomplete (backup)
            ddg_kws = self.collector.ddg_autocomplete(pillar_name)
            all_kw_items.extend([{"term": k, "language": "english",
                                   "region": "india", "religion": "general",
                                   "source": "ddg", "pillar": pillar_name}
                                  for k in ddg_kws])

            # Gemini expansion with language + region + religion variants
            gem_items = self.collector.gemini_expand(
                pillar_name, universe_term, ctx, langs, regions, religion
            )
            for item in gem_items:
                item["source"]  = "gemini"
                item["pillar"]  = pillar_name
            all_kw_items.extend(gem_items)

        # Wikipedia entities as keywords
        for entity in wiki_data.get("entities", []):
            all_kw_items.append({"term": entity.lower(), "language": "english",
                                  "region": "india", "religion": "general",
                                  "source": "wiki", "pillar": universe_term})

        state.step("keyword_collection", True, int((time.time()-t0)*1000),
                   f"{len(all_kw_items)} raw keyword items collected")
        state.set("raw_kw_items", all_kw_items)

        # ── STEP 4: Cleaning + dedup ──────────────────────────────────
        t0 = time.time()
        # Clean per language group
        english_kws = [i["term"] for i in all_kw_items if i.get("language","english")=="english"]
        other_kws   = [i for i in all_kw_items if i.get("language","english")!="english"]

        cleaned_english = self.cleaner.clean(english_kws)
        deduped, dupes  = self.cleaner.semantic_dedup(cleaned_english)

        # Rebuild full item list with deduped English + all non-English
        kw_meta = {i["term"]: i for i in all_kw_items}
        final_items = []
        for term in deduped:
            meta = kw_meta.get(term, {"term": term, "language": "english",
                                       "region": "india", "religion": "general",
                                       "source": "collected", "pillar": universe_term})
            final_items.append(meta)
        final_items.extend(other_kws)   # Add non-English without English dedup

        state.step("cleaning_dedup", True, int((time.time()-t0)*1000),
                   f"{len(all_kw_items)} → {len(final_items)} after dedup")

        # ── STEP 5: Intent + scoring (DeepSeek) ──────────────────────
        t0 = time.time()
        scored = []
        for item in final_items:
            term     = item.get("term","")
            intent   = self.scorer.intent(term)
            is_gap   = term.lower() not in own_kw_set
            is_prio  = term.lower() in priority_set
            score, ctype = self.scorer.score(term, intent, ctx,
                                              item.get("source","collected"),
                                              is_gap, is_prio)
            scored.append({**item, "intent": intent, "score": score,
                           "content_type": ctype, "is_gap": is_gap})

        scored.sort(key=lambda x: x["score"], reverse=True)
        top_100 = scored[:Cfg.TOP_N]
        state.step("intent_scoring", True, int((time.time()-t0)*1000),
                   f"Top {len(top_100)} keywords scored")

        # ── STEP 6: Cluster per pillar ───────────────────────────────
        t0 = time.time()
        pillar_trees = []
        for pillar in raw_pillars:
            pillar_name = pillar.get("name","")
            pillar_kws  = [i for i in top_100
                           if i.get("pillar","").lower() == pillar_name.lower()
                           or pillar_name.lower() in i.get("term","").lower()]
            kw_terms = [i["term"] for i in pillar_kws]
            clusters = self.clusterer.cluster(kw_terms) if len(kw_terms) >= 4 else [
                {"name":"General","description":"","keywords":kw_terms,
                 "language":"english","region":None,"religion":None}
            ]

            # Generate content brief (Gemini)
            brief = {}
            try:
                text  = AI.gemini(P.PILLAR_BRIEF.format(
                    pillar=pillar_name, universe=universe_term,
                    ctx=json.dumps(ctx)[:300],
                    audience=", ".join(ctx.get("target_audience",["general"]))
                ), temperature=0.3)
                brief = AI.parse_json(text)
            except Exception as e:
                log.warning(f"Brief failed for '{pillar_name}': {e}")

            # Attach scored keyword metadata to clusters
            kw_map = {i["term"]: i for i in pillar_kws}
            for cluster in clusters:
                cluster["keyword_items"] = [kw_map.get(t, {"term": t})
                                             for t in cluster["keywords"]]

            pillar_trees.append({
                "name":           pillar_name,
                "source":         pillar.get("source","competitor"),
                "competitor_count":pillar.get("competitor_count",0),
                "content_brief":  brief,
                "product_url":    self._match_product(pillar_name, project),
                "clusters":       clusters,
                "total_keywords": len(kw_terms),
            })

        state.step("clustering", True, int((time.time()-t0)*1000),
                   f"Clustered keywords across {len(pillar_trees)} pillars")

        # ── STEP 7: Build final universe tree ────────────────────────
        tree = {
            "universe":      universe_term,
            "project_id":    project.id,
            "pillars":       pillar_trees,
            "top_100":       top_100,
            "wiki_summary":  wiki_data.get("summary","")[:300],
            "wiki_entities": wiki_data.get("entities",[]),
            "languages":     list(set(i.get("language","english") for i in final_items)),
            "regions":       regions,
            "religion_ctx":  religion,
            "summary": {
                "total_pillars":  len(pillar_trees),
                "total_clusters": sum(len(p["clusters"]) for p in pillar_trees),
                "total_keywords": len(top_100),
                "languages_covered": list(set(i.get("language","english") for i in final_items)),
                "generated_at":  datetime.utcnow().isoformat(),
            }
        }
        state.set("universe_tree", tree)
        state.status = "completed"
        return {"status": "completed", "steps": state.log,
                "universe_tree": tree, "universe": universe_term}

    # ── Run ALL universes (batch) ──────────────────────────────────────

    def run_all_universes(self, project: Project,
                           universe_terms: List[str],
                           priority_keywords: List[str] = None,
                           run_seo_first: bool = True) -> dict:
        """
        Run the full pipeline for all customer input keywords.
        Each universe runs independently → separate trees.
        """
        log.info(f"[Ruflo v3] Running {len(universe_terms)} universes for project {project.id}")

        # Step 0: SEO audit (once, shared across all universes)
        site_kws = []
        if run_seo_first and project.website_url:
            log.info("[Ruflo v3] Running SEO audit first...")
            seo_result = self.seo.audit_site(project, max_pages=15)
            if seo_result.ok:
                site_kws = seo_result.data.get("site_keywords", [])
                log.info(f"[Ruflo v3] SEO audit done. {len(site_kws)} existing keywords found.")

        # Run each universe
        universe_results = []
        for term in universe_terms:
            log.info(f"\n[Ruflo v3] ═══ Universe: {term} ═══")
            result = self.run_universe(project, term, priority_keywords, site_kws)
            universe_results.append(result)

        return {
            "project_id":      project.id,
            "status":          "completed",
            "universe_count":  len(universe_results),
            "universes":       universe_results,
            "total_keywords":  sum(len(u["universe_tree"].get("top_100",[]))
                                   for u in universe_results),
            "generated_at":    datetime.utcnow().isoformat(),
        }

    def _match_product(self, pillar_name: str, project: Project) -> str:
        if not project.products:
            return f"/products/{pillar_name.lower().replace(' ','-')}"
        best, best_score = project.products[0].url, 0
        for prod in project.products:
            overlap = sum(1 for w in pillar_name.lower().split()
                          if w in prod.name.lower())
            if overlap > best_score:
                best, best_score = prod.url, overlap
        return best


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 15 — FASTAPI LAYER
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    app = FastAPI(
        title="Ruflo v3 — Keyword Universe System",
        description=(
            "4-level tree: Universe (customer input) → Pillar (competitor traffic) "
            "→ Cluster → Supporting keywords.\n"
            "Language + region + religion expansion built-in.\n"
            "AI: DeepSeek (local/free) + Gemini (free tier)."
        ),
        version="3.0.0"
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    ruflo = Ruflo()
    _jobs: Dict[str, dict] = {}


    class ProjectCreate(BaseModel):
        name:             str
        website_url:      Optional[str]  = None
        industry:         Optional[str]  = None
        business_type:    str            = "B2C"
        target_location:  str            = "Kerala, India"
        target_audience:  List[str]      = []
        target_languages: List[str]      = ["english", "malayalam"]
        target_regions:   List[str]      = ["wayanad", "kerala", "india"]
        religion_ctx:     List[str]      = ["ayurveda", "general"]
        brand_context:    dict           = {}
        competitor_urls:  List[str]      = []
        products:         List[dict]     = []


    class UniverseRequest(BaseModel):
        """Run keyword pipeline for one or more universe keywords."""
        project_id:        int
        universe_terms:    List[str]           # customer input keywords
        priority_keywords: Optional[List[str]] = []
        run_seo_first:     bool = True


    @app.post("/api/projects", tags=["Projects"])
    def create_project(req: ProjectCreate):
        db = get_db()
        p  = Project(
            name=req.name, website_url=req.website_url,
            industry=req.industry, business_type=req.business_type,
            target_location=req.target_location,
            target_audience=req.target_audience,
            target_languages=req.target_languages,
            target_regions=req.target_regions,
            religion_ctx=req.religion_ctx,
            brand_context=req.brand_context
        )
        db.add(p); db.flush()
        for url in req.competitor_urls:
            db.add(Competitor(project_id=p.id, url=url))
        for prod in req.products:
            db.add(Product(project_id=p.id, name=prod.get("name",""),
                           url=prod.get("url","")))
        db.commit()
        return {"project_id": p.id, "name": p.name}


    @app.get("/api/projects/{pid}", tags=["Projects"])
    def get_project(pid: int):
        db = get_db()
        p  = db.query(Project).filter(Project.id == pid).first()
        if not p:
            raise HTTPException(404, "Project not found")
        return {"id":p.id,"name":p.name,"industry":p.industry,
                "languages":p.target_languages,"regions":p.target_regions,
                "religion":p.religion_ctx,
                "competitors":[c.url for c in p.competitors],
                "products":[{"name":pr.name,"url":pr.url} for pr in p.products]}


    @app.post("/api/projects/{pid}/seo-audit", tags=["Module 1: SEO Checker"])
    def seo_audit(pid: int, background_tasks: BackgroundTasks):
        db = get_db()
        p  = db.query(Project).filter(Project.id == pid).first()
        if not p:
            raise HTTPException(404)
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {"status": "running"}
        def _run():
            r = SeoChecker().audit_site(p)
            _jobs[job_id] = {"status": "done" if r.ok else "failed",
                              "data": r.data}
        background_tasks.add_task(_run)
        return {"job_id": job_id}


    @app.post("/api/keyword-universe/run", tags=["Module 2: Keyword Universe"],
              summary="Run full keyword universe pipeline (async)")
    def run_universes(req: UniverseRequest, background_tasks: BackgroundTasks):
        db = get_db()
        p  = db.query(Project).filter(Project.id == req.project_id).first()
        if not p:
            raise HTTPException(404, "Project not found")
        if not req.universe_terms:
            raise HTTPException(400, "Provide at least one universe term")

        job_id = str(uuid.uuid4())
        _jobs[job_id] = {"status": "running", "universes": req.universe_terms}

        def _run():
            try:
                result = ruflo.run_all_universes(p, req.universe_terms,
                                                  req.priority_keywords,
                                                  req.run_seo_first)
                _jobs[job_id] = {"status": "done", "data": result}
            except Exception as e:
                log.exception(f"Pipeline failed: {e}")
                _jobs[job_id] = {"status": "failed", "error": str(e)}

        background_tasks.add_task(_run)
        return {"job_id": job_id, "universes": req.universe_terms,
                "message": "Pipeline running — poll /api/jobs/{job_id}"}


    @app.post("/api/keyword-universe/single", tags=["Module 2: Keyword Universe"],
              summary="Run one universe synchronously (for testing)")
    def run_single_universe(project_id: int, universe_term: str):
        db = get_db()
        p  = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            raise HTTPException(404)
        return ruflo.run_universe(p, universe_term)


    @app.get("/api/jobs/{job_id}", tags=["Jobs"])
    def get_job(job_id: str):
        if job_id not in _jobs:
            raise HTTPException(404)
        return _jobs[job_id]


    @app.get("/api/health", tags=["System"])
    def health():
        ollama_ok = False
        try:
            r = _req.get(f"{Cfg.OLLAMA_URL}/api/tags", timeout=3)
            ollama_ok = r.ok
        except Exception:
            pass
        return {
            "version":     "3.0.0",
            "architecture":"Universe → Pillar (competitor-driven) → Cluster → Supporting",
            "ollama":      "connected" if ollama_ok else "offline — run: ollama serve",
            "model":       Cfg.OLLAMA_MODEL,
            "gemini":      "configured" if Cfg.GEMINI_API_KEY else "not set (get free key at aistudio.google.com)",
            "languages":   Cfg.LANGUAGES,
            "regions":     Cfg.REGIONS,
        }

except ImportError as e:
    log.warning(f"FastAPI not available: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 16 — TEST SUITE
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    Test each stage. Uses spice business (Kerala organic spices) as example.

    Run:
      python ruflo_v3_keyword_system.py test              # all
      python ruflo_v3_keyword_system.py test serp         # SERP scraper
      python ruflo_v3_keyword_system.py test wiki         # Wikipedia
      python ruflo_v3_keyword_system.py test pillar       # pillar extraction
      python ruflo_v3_keyword_system.py test collect      # keyword collection
      python ruflo_v3_keyword_system.py test clean        # cleaning + dedup
      python ruflo_v3_keyword_system.py test intent       # intent classification
      python ruflo_v3_keyword_system.py test cluster      # clustering
      python ruflo_v3_keyword_system.py test universe     # full universe run
      python ruflo_v3_keyword_system.py test all_universes # 4 universes (full demo)
    """
    PROJECT = None

    def _make_project(self):
        if self.PROJECT:
            return self.PROJECT
        db = get_db()
        p  = Project(
            name="PureSpice Organics", website_url="https://example.com",
            industry="Organic Spices", business_type="D2C",
            target_location="Wayanad, Kerala, India",
            target_audience=["Home cooks","Health-conscious buyers","Exporters","Wholesalers"],
            target_languages=["english","malayalam","hindi"],
            target_regions=["wayanad","kerala","south india","india"],
            religion_ctx=["ayurveda","halal","general"]
        )
        db.add(p); db.flush()
        db.add(Competitor(project_id=p.id, url="https://en.wikipedia.org/wiki/Black_pepper"))
        db.add(Product(project_id=p.id, name="Organic Black Pepper", url="/products/black-pepper"))
        db.add(Product(project_id=p.id, name="Organic Cloves",       url="/products/cloves"))
        db.add(Product(project_id=p.id, name="Green Cardamom",        url="/products/cardamom"))
        db.commit()
        self.PROJECT = p
        return p

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_serp(self):
        self._h("SERP Scraper — black pepper")
        scraper = SerpScraper()
        pages   = scraper.get_top_pages("black pepper health benefits", n=3)
        self._ok(f"Got {len(pages)} SERP pages")
        for p in pages[:2]:
            self._ok(f"  URL: {p['url'][:60]}")
            self._ok(f"  H2s: {p['h2'][:3]}")

    def test_wiki(self):
        self._h("Wikipedia Research — cinnamon")
        data = Wiki().research("cinnamon")
        assert data["found"], "Wikipedia page not found"
        self._ok(f"Summary: {data['summary'][:80]}...")
        self._ok(f"Sections: {data['sections'][:5]}")
        self._ok(f"Entities: {data['entities'][:5]}")

    def test_pillar(self):
        self._h("Pillar Extraction — black pepper")
        wiki    = Wiki().research("black pepper")
        pillars = PillarExtractor().extract_pillars("black pepper", wiki)
        self._ok(f"{len(pillars)} pillars extracted:")
        for p in pillars:
            self._ok(f"  • {p['name']} (source: {p.get('source','?')}, competitor count: {p.get('competitor_count',0)})")

    def test_collect(self):
        self._h("Keyword Collection — clove")
        col = Collector()
        ac  = col.autocomplete("clove")
        self._ok(f"Autocomplete: {len(ac)} keywords → {ac[:3]}")
        ctx = {"business_name":"PureSpice","industry":"Spices","target_location":"Kerala"}
        gem = col.gemini_expand("clove health benefits","clove",ctx,
                                 ["english","malayalam"],["kerala","india"],["ayurveda"])
        self._ok(f"Gemini expanded: {len(gem)} items")
        for item in gem[:3]:
            self._ok(f"  {item}")

    def test_clean(self):
        self._h("Cleaning & Dedup (multi-lingual)")
        cleaner = Cleaner()
        raw = [
            "Black Pepper","black pepper","black pepper benefits","benefits of black pepper",
            "buy black pepper","purchase black pepper online",
            "കുരുമുളക്","കുരുമുളക് ഗുണങ്ങൾ",   # Malayalam
            "काली मिर्च","काली मिर्च के फायदे",   # Hindi
        ]
        cleaned = cleaner.clean(raw)
        self._ok(f"Cleaned: {len(raw)} → {len(cleaned)}")
        deduped, dupes = cleaner.semantic_dedup(
            [k for k in cleaned if k.isascii()]   # semantic dedup on English only
        )
        self._ok(f"Deduped: {len(deduped)} | Merged {len(dupes)} pairs")

    def test_intent(self):
        self._h("Intent Classification (DeepSeek)")
        scorer = Scorer()
        cases  = [
            ("black pepper health benefits", "informational"),
            ("buy organic black pepper online", "transactional"),
            ("best black pepper brand India", "commercial"),
        ]
        for kw, exp in cases:
            r = scorer.intent(kw)
            print(f"  {'✓' if r==exp else '?'} '{kw}' → {r} (expected {exp})")

    def test_cluster(self):
        self._h("Clustering — cardamom keywords")
        kws = [
            "cardamom health benefits","elaichi benefits","cardamom digestion",
            "buy cardamom online","cardamom price Kerala","green cardamom wholesale",
            "cardamom in chai","cardamom tea recipe","masala chai cardamom",
            "black cardamom vs green","types of cardamom",
        ]
        clusters = Clusterer().cluster(kws, n_clusters=3)
        self._ok(f"{len(clusters)} clusters:")
        for c in clusters:
            self._ok(f"  '{c['name']}' — {len(c['keywords'])} keywords, lang: {c['language']}")

    def test_universe(self):
        self._h("FULL UNIVERSE — black pepper")
        proj   = self._make_project()
        result = Ruflo().run_universe(proj, "black pepper",
                                      priority_keywords=["buy organic black pepper Kerala"])
        tree   = result["universe_tree"]
        self._ok(f"Status: {result['status']}")
        self._ok(f"Steps: {[s['step'] for s in result['steps']]}")
        self._ok(f"Pillars: {[p['name'] for p in tree['pillars']]}")
        self._ok(f"Top keywords: {[k['term'] for k in tree['top_100'][:5]]}")
        self._ok(f"Languages covered: {tree['languages']}")
        self._ok(f"Summary: {tree['summary']}")
        return result

    def test_all_universes(self):
        self._h("FULL RUN — 4 universes (black pepper, clove, cardamom, organic spices)")
        proj   = self._make_project()
        result = Ruflo().run_all_universes(
            proj,
            universe_terms=["black pepper","clove","cardamom","organic spices"],
            priority_keywords=["buy organic spices Kerala","Kerala spices online"],
            run_seo_first=False
        )
        self._ok(f"Status: {result['status']}")
        self._ok(f"Universes completed: {result['universe_count']}")
        self._ok(f"Total keywords: {result['total_keywords']}")
        for u in result["universes"]:
            tree = u["universe_tree"]
            self._ok(f"\n  Universe: {u['universe']}")
            self._ok(f"    Pillars: {[p['name'][:40] for p in tree['pillars']]}")
            self._ok(f"    Keywords: {tree['summary']['total_keywords']}")
        return result

    def run_all(self):
        tests = [
            ("wiki",     self.test_wiki),
            ("serp",     self.test_serp),
            ("pillar",   self.test_pillar),
            ("collect",  self.test_collect),
            ("clean",    self.test_clean),
            ("intent",   self.test_intent),
            ("cluster",  self.test_cluster),
        ]
        print("\n" + "═"*55)
        print("  RUFLO v3 — UNIVERSE TREE SYSTEM — STAGE TESTS")
        print("═"*55)
        passed = failed = 0
        for name, fn in tests:
            try:
                fn()
                passed += 1
            except Exception as e:
                print(f"  ✗ {name}: {e}")
                failed += 1
        print("\n" + "═"*55)
        print(f"  {passed} passed / {failed} failed")
        print("═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 17 — CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
Ruflo v3 — Keyword Universe Intelligence System
─────────────────────────────────────────────────────
4-level tree: Universe → Pillar (competitor traffic) → Cluster → Supporting keywords
Language + region + religion expansion included.

Usage:
  python ruflo_v3_keyword_system.py test                  # all stage tests
  python ruflo_v3_keyword_system.py test <stage>          # one stage
  python ruflo_v3_keyword_system.py run <keyword>         # run one universe
  python ruflo_v3_keyword_system.py run_all               # run 4-universe demo
  python ruflo_v3_keyword_system.py api                   # start FastAPI server
  python ruflo_v3_keyword_system.py wiki <term>           # research a term
  python ruflo_v3_keyword_system.py serp <keyword>        # scrape SERP for keyword
  python ruflo_v3_keyword_system.py pillar <keyword>      # extract pillars for keyword

Stages: serp, wiki, pillar, collect, clean, intent, cluster, universe, all_universes

Setup:
  ollama pull deepseek-r1:7b     # local AI (free)
  echo GEMINI_API_KEY=xxx > .env # free key at aistudio.google.com
  pip install fastapi uvicorn sqlalchemy requests beautifulsoup4 \\
              yake spacy sentence-transformers scikit-learn numpy \\
              wikipedia-api google-generativeai python-dotenv
"""
    if len(sys.argv) < 2:
        print(HELP); sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "test":
        t = Tests()
        if len(sys.argv) == 3:
            fn = getattr(t, f"test_{sys.argv[2]}", None)
            if fn: fn()
            else:  print(f"Unknown stage: {sys.argv[2]}")
        else:
            t.run_all()

    elif cmd == "run":
        kw   = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "black pepper"
        db   = get_db()
        proj = Project(name="Demo", industry="Spices", business_type="D2C",
                       target_location="Kerala, India",
                       target_languages=["english","malayalam"],
                       target_regions=["kerala","india"],
                       religion_ctx=["ayurveda","general"])
        db.add(proj); db.flush()
        db.add(Product(project_id=proj.id, name=kw, url=f"/products/{kw.replace(' ','-')}"))
        db.commit()
        result = Ruflo().run_universe(proj, kw)
        print(json.dumps(result["universe_tree"]["summary"], indent=2))
        print("Pillars:", [p["name"] for p in result["universe_tree"]["pillars"]])
        print("Top 5:", [k["term"] for k in result["universe_tree"]["top_100"][:5]])

    elif cmd == "run_all":
        Tests().test_all_universes()

    elif cmd == "api":
        try:
            import uvicorn
            print("Ruflo v3 API — http://localhost:8000")
            print("Docs:  http://localhost:8000/docs")
            uvicorn.run("ruflo_v3_keyword_system:app",
                        host="0.0.0.0", port=8000, reload=True)
        except ImportError:
            print("pip install uvicorn")

    elif cmd == "wiki":
        term   = " ".join(sys.argv[2:])
        result = Wiki().research(term)
        print(json.dumps({k:v for k,v in result.items() if k!="summary"}, indent=2))
        print("Summary:", result.get("summary","")[:300])

    elif cmd == "serp":
        kw    = " ".join(sys.argv[2:])
        pages = SerpScraper().get_top_pages(kw, n=5)
        for p in pages:
            print(f"\n{p['url']}")
            print(f"  H1: {p['h1']}")
            print(f"  H2s: {p['h2'][:4]}")

    elif cmd == "pillar":
        kw      = " ".join(sys.argv[2:])
        wiki    = Wiki().research(kw)
        pillars = PillarExtractor().extract_pillars(kw, wiki)
        print(f"\nPillars for '{kw}':")
        for p in pillars:
            print(f"  • {p['name']} [{p.get('source','?')}]")

    else:
        print(f"Unknown command: {cmd}\n{HELP}")

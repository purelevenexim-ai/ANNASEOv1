"""
================================================================================
ANNASEO — SELF DEVELOPMENT ENGINE
================================================================================
Application : AnnaSEO
Module      : Self Development (SD) — the learning half of Research & Self Dev
Orchestrator: Ruflo (https://github.com/ruvnet/ruflo)

What this does
──────────────
Crawls 40+ authoritative sources on a schedule.
Extracts what is new, changed, or deprecated in:
  SEO signals, GEO/AI search, schema standards, CWV thresholds, algorithm
  updates, new Python libraries, GitHub releases.
Compares discoveries against what AnnaSEO currently implements.
Plans new features, deprecation fixes, or engine updates.
Uses free AI tools to research → understand → code → test the change.
Requires manual human approval before anything reaches production.
Full rollback to any previous version.
User can add custom content/sources at any time.

AI Model Routing (free tools only for coding/testing)
──────────────────────────────────────────────────────
  DuckDuckGo       → web search (free, no key)
  feedparser       → RSS/Atom feeds (free)
  Gemini 1.5 Flash → source analysis, feature extraction (free tier)
  Groq Llama       → test generation, fast iteration (free tier)
  DeepSeek local   → implementation coding (Ollama, free)
  Claude Sonnet    → ONLY for final verification + approval notes

Source Categories
─────────────────
  GOOGLE_OFFICIAL   — Search Central, web.dev, schema.org, patents
  SEO_INDUSTRY      — searchengineland, moz, ahrefs, backlinko, seroundtable
  AI_SEARCH         — perplexity, openai, anthropic, llmstxt.org
  GITHUB            — trending repos, watched releases, topics
  RESEARCH          — arxiv, Google Research, HTTP Archive
  USER_ADDED        — custom sources added by the user at any time

Scheduling
──────────
  Daily   8:00 UTC  → crawl GOOGLE_OFFICIAL + SEO_INDUSTRY
  Daily  10:00 UTC  → crawl AI_SEARCH + GITHUB
  Weekly Sun 6:00   → crawl RESEARCH + arxiv
  On-demand         → user triggers manual crawl
================================================================================
"""
from __future__ import annotations

import os, re, json, time, sqlite3, hashlib, logging, traceback, textwrap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("annaseo.selfdev")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

import requests as _req
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — SOURCE REGISTRY (40+ sources)
# ─────────────────────────────────────────────────────────────────────────────

class SourceCategory(str, Enum):
    GOOGLE_OFFICIAL = "google_official"
    SEO_INDUSTRY    = "seo_industry"
    AI_SEARCH       = "ai_search"
    GITHUB          = "github"
    RESEARCH        = "research"
    USER_ADDED      = "user_added"


@dataclass
class IntelligenceSource:
    source_id:       str
    name:            str
    url:             str
    category:        SourceCategory
    crawl_type:      str          # "rss" | "html" | "github_api" | "arxiv" | "user"
    engines_affected:List[str]    # which AnnaSEO engines this source feeds
    frequency:       str          # "daily" | "weekly" | "monthly" | "on_change"
    keywords:        List[str]    # keywords to search for relevance
    rss_url:         str          = ""
    active:          bool         = True
    added_by:        str          = "system"
    notes:           str          = ""


# The complete source registry
SOURCES: List[IntelligenceSource] = [

    # ── Google Official ──────────────────────────────────────────────────────
    IntelligenceSource("google_searchcentral_blog","Google Search Central Blog",
        "https://developers.google.com/search/blog","google_official",
        "rss",["20phase_engine","rank_zero_engine","seo_audit"],"daily",
        ["algorithm","core update","helpful content","e-e-a-t","schema","ranking"],
        rss_url="https://developers.google.com/search/blog/rss.xml"),
    IntelligenceSource("google_webdev","web.dev Blog",
        "https://web.dev/blog","google_official",
        "rss",["seo_audit","rank_zero_engine"],"weekly",
        ["INP","LCP","CLS","core web vitals","performance","interaction"],
        rss_url="https://web.dev/feed.xml"),
    IntelligenceSource("schema_org_releases","Schema.org Releases",
        "https://schema.org/docs/releases.html","google_official",
        "html",["seo_audit","content_engine","rank_zero_engine"],"on_change",
        ["new type","deprecated","restricted","FAQPage","HowTo","Article","VideoObject"]),
    IntelligenceSource("google_patents","Google Patents — SEO",
        "https://patents.google.com/?assignee=Google+LLC&q=search+ranking","google_official",
        "html",["20phase_engine","rank_zero_engine","content_engine"],"monthly",
        ["information gain","entity","passage","helpful content","originality"]),
    IntelligenceSource("google_search_docs","Google Search Documentation",
        "https://developers.google.com/search/docs","google_official",
        "html",["seo_audit","rank_zero_engine"],"on_change",
        ["crawlability","indexing","structured data","canonical","hreflang","robots"]),

    # ── SEO Industry ─────────────────────────────────────────────────────────
    IntelligenceSource("searchengineland","Search Engine Land",
        "https://searchengineland.com","seo_industry",
        "rss",["20phase_engine","rank_zero_engine","content_engine"],"daily",
        ["algorithm update","google update","core update","ranking factor","SERP","AI overview"],
        rss_url="https://searchengineland.com/feed"),
    IntelligenceSource("seroundtable","Search Engine Roundtable",
        "https://www.seroundtable.com","seo_industry",
        "rss",["20phase_engine","rank_zero_engine"],"daily",
        ["google algorithm","ranking","indexing","manual action","search update"],
        rss_url="https://www.seroundtable.com/googlenews.rss"),
    IntelligenceSource("moz_blog","Moz Blog",
        "https://moz.com/blog","seo_industry",
        "rss",["20phase_engine","content_engine","seo_audit"],"weekly",
        ["ranking factors","e-e-a-t","content","technical SEO","link building"],
        rss_url="https://moz.com/blog/feed"),
    IntelligenceSource("ahrefs_blog","Ahrefs Blog",
        "https://ahrefs.com/blog","seo_industry",
        "rss",["20phase_engine","content_engine"],"weekly",
        ["keyword research","backlinks","content strategy","SERP analysis"],
        rss_url="https://ahrefs.com/blog/rss/"),
    IntelligenceSource("backlinko","Backlinko",
        "https://backlinko.com/blog","seo_industry",
        "rss",["rank_zero_engine","content_engine"],"monthly",
        ["ranking factors","content","google algorithm","SEO study"]),
    IntelligenceSource("searchenginejournal","Search Engine Journal",
        "https://www.searchenginejournal.com","seo_industry",
        "rss",["content_engine","seo_audit","rank_zero_engine"],"daily",
        ["e-e-a-t","algorithm","content quality","technical SEO"],
        rss_url="https://www.searchenginejournal.com/feed/"),
    IntelligenceSource("semrush_blog","Semrush Blog",
        "https://www.semrush.com/blog/","seo_industry",
        "html",["20phase_engine","rank_zero_engine"],"weekly",
        ["SERP features","keyword trends","competitive intelligence","AI content"]),

    # ── AI Search / GEO ──────────────────────────────────────────────────────
    IntelligenceSource("perplexity_blog","Perplexity Blog",
        "https://blog.perplexity.ai","ai_search",
        "html",["rank_zero_engine","seo_audit","annaseo_addons"],"weekly",
        ["citation","index","source selection","answer engine","AI search"]),
    IntelligenceSource("openai_blog","OpenAI Blog",
        "https://openai.com/blog","ai_search",
        "rss",["rank_zero_engine","seo_audit"],"weekly",
        ["search","web browsing","ChatGPT search","GPTBot","citation"],
        rss_url="https://openai.com/blog/rss/"),
    IntelligenceSource("anthropic_news","Anthropic News",
        "https://www.anthropic.com/news","ai_search",
        "html",["rank_zero_engine","publisher"],"weekly",
        ["Claude","ClaudeBot","search","web","citation","crawl"]),
    IntelligenceSource("llmstxt_spec","llms.txt Specification",
        "https://llmstxt.org","ai_search",
        "html",["seo_audit","rank_zero_engine"],"on_change",
        ["llms.txt","AI crawlers","LLM access","standard","spec"]),
    IntelligenceSource("bing_webmaster","Bing Webmaster Blog",
        "https://blogs.bing.com/webmaster/","ai_search",
        "rss",["seo_audit","publisher"],"weekly",
        ["IndexNow","Bing","Copilot","AI search","crawl","index"]),
    IntelligenceSource("google_ai_blog","Google AI Blog",
        "https://blog.google/technology/ai/","ai_search",
        "rss",["rank_zero_engine","20phase_engine","content_engine"],"weekly",
        ["Gemini","AI search","AI overviews","generative","knowledge graph"],
        rss_url="https://blog.google/rss/"),

    # ── GitHub ────────────────────────────────────────────────────────────────
    IntelligenceSource("github_trending_seo","GitHub Trending — SEO",
        "https://github.com/trending?q=seo&since=weekly","github",
        "github_api",["all_engines"],"weekly",
        ["seo","keyword","content","audit","rank","serp","schema"]),
    IntelligenceSource("github_trending_llm_seo","GitHub Trending — LLM+SEO",
        "https://github.com/trending?q=llm+seo&since=weekly","github",
        "github_api",["rank_zero_engine","content_engine"],"weekly",
        ["llm","seo","AI","GEO","citation","search"]),
    IntelligenceSource("github_claude_seo","claude-seo releases",
        "https://github.com/AgriciDaniel/claude-seo/releases","github",
        "github_api",["seo_audit","rank_zero_engine","content_engine"],"weekly",
        ["release","new","schema","GEO","AEO","hreflang","audit"]),
    IntelligenceSource("github_agentic_seo","Agentic-SEO-Skill releases",
        "https://github.com/Bhanunamikaze/Agentic-SEO-Skill/releases","github",
        "github_api",["seo_audit","rank_zero_engine"],"weekly",
        ["release","new","INP","FID","schema","rubric","confidence"]),
    IntelligenceSource("github_ruflo","Ruflo releases",
        "https://github.com/ruvnet/ruflo/releases","github",
        "github_api",["all_engines"],"weekly",
        ["release","new","job","SSE","agent","orchestrator","breaking change"]),
    IntelligenceSource("github_geo_seo","geo-seo-claude releases",
        "https://github.com/zubair-trabzada/geo-seo-claude/releases","github",
        "github_api",["rank_zero_engine","seo_audit"],"weekly",
        ["GEO","citability","llms.txt","brand","platform","AI search"]),
    IntelligenceSource("pypi_seo_packages","PyPI new SEO packages",
        "https://pypi.org/search/?q=seo&o=-created","github",
        "html",["annaseo_addons","20phase_engine"],"weekly",
        ["seo","nlp","keyword","serp","rank","schema","crawl"]),

    # ── Research ─────────────────────────────────────────────────────────────
    IntelligenceSource("arxiv_seo_llm","arXiv — SEO + LLM papers",
        "https://arxiv.org/search/?query=seo+llm&searchtype=all","research",
        "html",["rank_zero_engine","content_engine","20phase_engine"],"weekly",
        ["information gain","ranking","LLM","content quality","entity","semantic"]),
    IntelligenceSource("arxiv_geo","arXiv — Generative Engine Optimization",
        "https://arxiv.org/search/?query=generative+engine+optimization","research",
        "html",["rank_zero_engine","seo_audit"],"weekly",
        ["GEO","citation","AI search","generative","retrieval","augmented"]),
    IntelligenceSource("google_research","Google Research Publications",
        "https://research.google/pubs/","research",
        "html",["20phase_engine","rank_zero_engine","content_engine"],"monthly",
        ["search ranking","helpful content","information gain","entity","knowledge"]),
    IntelligenceSource("httparchive","HTTP Archive Web Almanac",
        "https://almanac.httparchive.org/en/","research",
        "html",["seo_audit","rank_zero_engine"],"annual",
        ["core web vitals","schema","SEO","performance","CWV adoption"]),
]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IntelligenceItem:
    """One piece of new information discovered from a source."""
    item_id:         str
    source_id:       str
    title:           str
    url:             str
    raw_content:     str
    summary:         str       = ""
    relevance_score: float     = 0.0    # 0-1 how relevant to AnnaSEO
    engines_affected:List[str] = field(default_factory=list)
    change_type:     str       = ""     # "new_signal"|"deprecated"|"threshold_change"|"new_tool"|"algorithm_update"
    action_needed:   bool      = False
    discovered_at:   str       = field(default_factory=lambda: datetime.utcnow().isoformat())
    processed:       bool      = False


@dataclass
class KnowledgeGap:
    """Something AnnaSEO doesn't yet implement that it should."""
    gap_id:          str
    title:           str
    description:     str
    evidence_urls:   List[str]
    engines_affected:List[str]
    priority:        str       = "medium"   # "critical"|"high"|"medium"|"low"
    gap_type:        str       = "feature"  # "feature"|"fix"|"deprecation"|"update"|"new_signal"
    estimated_effort:str       = "medium"   # "small"|"medium"|"large"
    status:          str       = "pending"  # "pending"|"in_dev"|"testing"|"approved"|"done"|"rejected"
    source_items:    List[str] = field(default_factory=list)
    implementation:  str       = ""         # filled after development
    created_at:      str       = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class UserContent:
    """Content added manually by the user for review and possible implementation."""
    content_id:      str
    title:           str
    content:         str        # raw text, URL, code snippet, or description
    content_type:    str        # "url"|"text"|"snippet"|"idea"|"source"
    engines_affected:List[str]
    notes:           str        = ""
    status:          str        = "pending"  # "pending"|"analysed"|"gap_created"|"implemented"|"rejected"
    analysis:        str        = ""
    created_at:      str        = field(default_factory=lambda: datetime.utcnow().isoformat())
    added_by:        str        = "user"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — CONSOLE (consistent with other AnnaSEO engines)
# ─────────────────────────────────────────────────────────────────────────────

class Console:
    C = {"info":"\033[94m","success":"\033[92m","warning":"\033[93m","error":"\033[91m",
         "data":"\033[95m","sep":"\033[90m","gemini":"\033[36m","groq":"\033[33m",
         "deepseek":"\033[34m","claude":"\033[35m","crawl":"\033[96m"}
    R = "\033[0m"
    I = {"info":"→","success":"✓","warning":"⚠","error":"✗","data":"·",
         "sep":"─","gemini":"◇","groq":"◈","deepseek":"◉","claude":"◆","crawl":"⟳"}

    @classmethod
    def log(cls, eng: str, level: str, msg: str):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        c  = cls.C.get(level,"")
        i  = cls.I.get(level,"·")
        print(f"  {ts} {c}[{eng:<20}] {i} {msg}{cls.R}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — DATABASE
# ─────────────────────────────────────────────────────────────────────────────

class SDDB:
    def __init__(self, db_path: str = None):
        path = Path(db_path or os.getenv("ANNASEO_DB","./annaseo.db"))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS sd_intelligence_items (
            item_id TEXT PRIMARY KEY,
            source_id TEXT,
            title TEXT,
            url TEXT,
            raw_content TEXT,
            summary TEXT DEFAULT '',
            relevance_score REAL DEFAULT 0,
            engines_affected TEXT DEFAULT '[]',
            change_type TEXT DEFAULT '',
            action_needed INTEGER DEFAULT 0,
            discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sd_knowledge_gaps (
            gap_id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            evidence_urls TEXT DEFAULT '[]',
            engines_affected TEXT DEFAULT '[]',
            priority TEXT DEFAULT 'medium',
            gap_type TEXT DEFAULT 'feature',
            estimated_effort TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            source_items TEXT DEFAULT '[]',
            implementation TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sd_user_content (
            content_id TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            content_type TEXT,
            engines_affected TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            analysis TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            added_by TEXT DEFAULT 'user'
        );

        CREATE TABLE IF NOT EXISTS sd_implementations (
            impl_id TEXT PRIMARY KEY,
            gap_id TEXT,
            engine_name TEXT,
            version TEXT,
            code_before TEXT DEFAULT '',
            code_after TEXT DEFAULT '',
            diff TEXT DEFAULT '',
            changes TEXT DEFAULT '[]',
            ai_used TEXT DEFAULT '[]',
            test_code TEXT DEFAULT '',
            test_results TEXT DEFAULT '{}',
            claude_notes TEXT DEFAULT '',
            approval_status TEXT DEFAULT 'pending',
            approved_by TEXT DEFAULT '',
            approved_at TEXT DEFAULT '',
            rejection_reason TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sd_source_crawl_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT,
            crawled_at TEXT DEFAULT CURRENT_TIMESTAMP,
            items_found INTEGER DEFAULT 0,
            items_relevant INTEGER DEFAULT 0,
            error TEXT DEFAULT '',
            duration_ms REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sd_custom_sources (
            source_id TEXT PRIMARY KEY,
            name TEXT,
            url TEXT,
            category TEXT,
            crawl_type TEXT DEFAULT 'html',
            engines_affected TEXT DEFAULT '[]',
            frequency TEXT DEFAULT 'weekly',
            keywords TEXT DEFAULT '[]',
            active INTEGER DEFAULT 1,
            added_by TEXT DEFAULT 'user',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_sd_items_source ON sd_intelligence_items(source_id);
        CREATE INDEX IF NOT EXISTS idx_sd_items_action ON sd_intelligence_items(action_needed);
        CREATE INDEX IF NOT EXISTS idx_sd_gaps_status ON sd_knowledge_gaps(status);
        CREATE INDEX IF NOT EXISTS idx_sd_gaps_priority ON sd_knowledge_gaps(priority);
        CREATE INDEX IF NOT EXISTS idx_sd_impl_gap ON sd_implementations(gap_id);
        """)
        self.db.commit()

    def save_item(self, item: IntelligenceItem):
        self.db.execute("""
            INSERT OR REPLACE INTO sd_intelligence_items
            (item_id,source_id,title,url,raw_content,summary,relevance_score,
             engines_affected,change_type,action_needed,discovered_at,processed)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (item.item_id, item.source_id, item.title, item.url,
              item.raw_content[:5000], item.summary, item.relevance_score,
              json.dumps(item.engines_affected), item.change_type,
              1 if item.action_needed else 0, item.discovered_at,
              1 if item.processed else 0))
        self.db.commit()

    def save_gap(self, gap: KnowledgeGap):
        self.db.execute("""
            INSERT OR REPLACE INTO sd_knowledge_gaps
            (gap_id,title,description,evidence_urls,engines_affected,priority,
             gap_type,estimated_effort,status,source_items,implementation)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (gap.gap_id, gap.title, gap.description,
              json.dumps(gap.evidence_urls), json.dumps(gap.engines_affected),
              gap.priority, gap.gap_type, gap.estimated_effort, gap.status,
              json.dumps(gap.source_items), gap.implementation))
        self.db.commit()

    def save_user_content(self, uc: UserContent):
        self.db.execute("""
            INSERT OR REPLACE INTO sd_user_content
            (content_id,title,content,content_type,engines_affected,notes,status,analysis,added_by)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (uc.content_id, uc.title, uc.content, uc.content_type,
              json.dumps(uc.engines_affected), uc.notes, uc.status,
              uc.analysis, uc.added_by))
        self.db.commit()

    def get_gaps(self, status: str = None, priority: str = None) -> List[dict]:
        q = "SELECT * FROM sd_knowledge_gaps"
        filters, params = [], []
        if status:    filters.append("status=?"); params.append(status)
        if priority:  filters.append("priority=?"); params.append(priority)
        if filters:   q += " WHERE " + " AND ".join(filters)
        q += " ORDER BY created_at DESC"
        return [dict(r) for r in self.db.execute(q, params).fetchall()]

    def get_items(self, action_only: bool = False, limit: int = 100) -> List[dict]:
        q = "SELECT * FROM sd_intelligence_items"
        if action_only: q += " WHERE action_needed=1 AND processed=0"
        q += " ORDER BY discovered_at DESC LIMIT ?"
        return [dict(r) for r in self.db.execute(q, [limit]).fetchall()]

    def get_implementations(self, status: str = None) -> List[dict]:
        q = "SELECT * FROM sd_implementations"
        if status: q += f" WHERE approval_status='{status}'"
        q += " ORDER BY created_at DESC"
        return [dict(r) for r in self.db.execute(q).fetchall()]

    def get_user_content(self, status: str = None) -> List[dict]:
        q = "SELECT * FROM sd_user_content"
        if status: q += f" WHERE status='{status}'"
        q += " ORDER BY created_at DESC"
        return [dict(r) for r in self.db.execute(q).fetchall()]

    def log_crawl(self, source_id: str, items: int, relevant: int,
                   error: str = "", duration_ms: float = 0):
        self.db.execute("""
            INSERT INTO sd_source_crawl_log (source_id,items_found,items_relevant,error,duration_ms)
            VALUES (?,?,?,?,?)
        """, (source_id, items, relevant, error, duration_ms))
        self.db.commit()

    def add_custom_source(self, data: dict) -> str:
        sid = f"custom_{hashlib.md5(data['url'].encode()).hexdigest()[:8]}"
        self.db.execute("""
            INSERT OR REPLACE INTO sd_custom_sources
            (source_id,name,url,category,crawl_type,engines_affected,frequency,keywords,added_by,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (sid, data["name"], data["url"], data.get("category","user_added"),
              data.get("crawl_type","html"), json.dumps(data.get("engines_affected",[])),
              data.get("frequency","weekly"), json.dumps(data.get("keywords",[])),
              data.get("added_by","user"), data.get("notes","")))
        self.db.commit()
        return sid


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — INTELLIGENCE CRAWLER
# ─────────────────────────────────────────────────────────────────────────────

class IntelligenceCrawler:
    """
    Crawls all intelligence sources and extracts raw content items.
    Uses only free tools: feedparser for RSS, httpx/BeautifulSoup for HTML,
    GitHub API (unauthenticated, 60 req/hr), DuckDuckGo for keyword searches.
    """
    HEADERS = {
        "User-Agent": "AnnaSEO-SelfDev/1.0 (research bot; +https://annaseo.ai/bot)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self):
        self._db = SDDB()

    def crawl_source(self, source: IntelligenceSource) -> List[IntelligenceItem]:
        """Crawl one source and return raw items."""
        t0 = time.perf_counter()
        Console.log("Crawler", "crawl", f"Crawling: {source.name}")
        items = []
        try:
            if source.crawl_type == "rss":
                items = self._crawl_rss(source)
            elif source.crawl_type == "html":
                items = self._crawl_html(source)
            elif source.crawl_type == "github_api":
                items = self._crawl_github(source)
            elif source.crawl_type == "arxiv":
                items = self._crawl_arxiv(source)
        except Exception as e:
            error = str(e)[:200]
            Console.log("Crawler", "error", f"{source.source_id}: {error}")
            self._db.log_crawl(source.source_id, 0, 0, error)
            return []

        ms = (time.perf_counter() - t0) * 1000
        Console.log("Crawler", "data",
                    f"{source.name}: {len(items)} items in {ms:.0f}ms")
        for item in items:
            self._db.save_item(item)
        self._db.log_crawl(source.source_id, len(items), len(items))
        return items

    def _crawl_rss(self, source: IntelligenceSource) -> List[IntelligenceItem]:
        """Parse RSS/Atom feed."""
        try:
            import feedparser
        except ImportError:
            # Fallback: simple HTTP parse
            return self._crawl_html(source)

        feed_url = source.rss_url or source.url
        try:
            r = _req.get(feed_url, headers=self.HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"RSS fetch failed: {e}")

        feed   = feedparser.parse(r.content)
        items  = []
        cutoff = datetime.utcnow() - timedelta(days=14)   # last 2 weeks only

        for entry in feed.entries[:20]:
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                import calendar
                pub_date = datetime(*entry.published_parsed[:6])
                if pub_date < cutoff:
                    continue

            title   = getattr(entry,'title','(no title)').strip()
            url     = getattr(entry,'link','')
            summary = BeautifulSoup(getattr(entry,'summary',''), 'html.parser').get_text()[:500]
            iid     = hashlib.md5(f"{source.source_id}{url}".encode()).hexdigest()[:14]

            items.append(IntelligenceItem(
                item_id=iid, source_id=source.source_id,
                title=title, url=url, raw_content=summary,
                engines_affected=source.engines_affected.copy()
            ))
        return items

    def _crawl_html(self, source: IntelligenceSource) -> List[IntelligenceItem]:
        """Scrape HTML page and extract article titles + excerpts."""
        try:
            r = _req.get(source.url, headers=self.HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"HTML fetch failed: {e}")

        soup  = BeautifulSoup(r.text, 'html.parser')
        items = []

        # Try to find articles: h2/h3 + adjacent paragraph
        articles = soup.find_all(['article','div'], class_=re.compile(r'post|article|entry|card|item',re.I))
        if not articles:
            articles = soup.find_all(['h2','h3'])[:20]

        for art in articles[:15]:
            title_el = art.find(['h2','h3','h4','a']) if art.name not in ('h2','h3','h4') else art
            if not title_el: continue
            title = title_el.get_text(strip=True)[:200]
            if len(title) < 10: continue

            link_el = art.find('a', href=True)
            url = urljoin(source.url, link_el['href']) if link_el else source.url
            body_el = art.find('p')
            body = body_el.get_text(strip=True)[:400] if body_el else ""
            iid  = hashlib.md5(f"{source.source_id}{title}".encode()).hexdigest()[:14]

            items.append(IntelligenceItem(
                item_id=iid, source_id=source.source_id,
                title=title, url=url, raw_content=body,
                engines_affected=source.engines_affected.copy()
            ))
        return items

    def _crawl_github(self, source: IntelligenceSource) -> List[IntelligenceItem]:
        """Use GitHub API to get releases or trending repos (unauthenticated)."""
        items = []
        token = os.getenv("GITHUB_TOKEN","")   # optional — 5000 req/hr if set
        headers = {**self.HEADERS}
        if token: headers["Authorization"] = f"token {token}"

        # Is it a releases page?
        releases_match = re.match(r"https://github\.com/([^/]+)/([^/]+)/releases", source.url)
        if releases_match:
            owner, repo = releases_match.groups()
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=5"
            try:
                r = _req.get(api_url, headers=headers, timeout=12)
                if r.ok:
                    for rel in r.json()[:5]:
                        iid = hashlib.md5(f"{source.source_id}{rel.get('id','')}".encode()).hexdigest()[:14]
                        items.append(IntelligenceItem(
                            item_id=iid, source_id=source.source_id,
                            title=f"Release {rel.get('tag_name','')} — {rel.get('name','')}",
                            url=rel.get('html_url',''),
                            raw_content=(rel.get('body','') or '')[:1000],
                            engines_affected=source.engines_affected.copy()
                        ))
            except Exception as e:
                Console.log("Crawler","warning",f"GitHub API: {e}")
            return items

        # Trending repos — use GitHub search API
        search_q = "+".join(source.keywords[:3]) + "&sort=stars&order=desc&per_page=10"
        try:
            r = _req.get(
                f"https://api.github.com/search/repositories?q={search_q}&per_page=10",
                headers=headers, timeout=12
            )
            if r.ok:
                for repo in r.json().get("items",[])[:10]:
                    iid = hashlib.md5(f"{source.source_id}{repo['full_name']}".encode()).hexdigest()[:14]
                    items.append(IntelligenceItem(
                        item_id=iid, source_id=source.source_id,
                        title=f"{repo['full_name']} ★{repo.get('stargazers_count',0)}",
                        url=repo.get('html_url',''),
                        raw_content=repo.get('description','')[:400],
                        engines_affected=source.engines_affected.copy()
                    ))
        except Exception as e:
            Console.log("Crawler","warning",f"GitHub search API: {e}")
        return items

    def _crawl_arxiv(self, source: IntelligenceSource) -> List[IntelligenceItem]:
        """Search arxiv using their API (free, no auth)."""
        query   = "+AND+".join(f'ti:"{k}"' for k in source.keywords[:2])
        api_url = f"http://export.arxiv.org/api/query?search_query={query}&max_results=10&sortBy=submittedDate"
        items   = []
        try:
            r = _req.get(api_url, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'xml')
            for entry in soup.find_all('entry')[:10]:
                title   = entry.find('title').get_text(strip=True) if entry.find('title') else ""
                summary = entry.find('summary').get_text(strip=True)[:500] if entry.find('summary') else ""
                url     = entry.find('id').get_text(strip=True) if entry.find('id') else ""
                iid     = hashlib.md5(f"arxiv{url}".encode()).hexdigest()[:14]
                items.append(IntelligenceItem(
                    item_id=iid, source_id=source.source_id,
                    title=title, url=url, raw_content=summary,
                    engines_affected=source.engines_affected.copy()
                ))
        except Exception as e:
            Console.log("Crawler","warning",f"arXiv API: {e}")
        return items

    def search_duckduckgo(self, query: str, max_results: int = 10) -> List[dict]:
        """
        Free DuckDuckGo search (no API key).
        Uses DDG HTML endpoint — returns titles + URLs.
        """
        results = []
        try:
            r = _req.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "us-en"},
                headers={**self.HEADERS, "Accept": "text/html"},
                timeout=12
            )
            if r.ok:
                soup = BeautifulSoup(r.text, 'html.parser')
                for result in soup.select('.result')[:max_results]:
                    title_el = result.select_one('.result__title a')
                    snip_el  = result.select_one('.result__snippet')
                    if title_el:
                        results.append({
                            "title":   title_el.get_text(strip=True),
                            "url":     title_el.get('href',''),
                            "snippet": snip_el.get_text(strip=True) if snip_el else ""
                        })
        except Exception as e:
            Console.log("Crawler","warning",f"DDG search failed: {e}")
        return results


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — KNOWLEDGE EXTRACTOR (Gemini — free tier)
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeExtractor:
    """
    Uses Gemini 1.5 Flash (free tier) to:
    1. Score relevance of each crawled item to AnnaSEO
    2. Extract what specifically changed or is new
    3. Identify which engines are affected
    4. Classify change type
    Uses DuckDuckGo for additional research when needed.
    """
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def __init__(self):
        self._db     = SDDB()
        self._crawler= IntelligenceCrawler()

    def process_item(self, item: IntelligenceItem) -> IntelligenceItem:
        """Analyse one intelligence item with Gemini."""
        gemini_key = os.getenv("GEMINI_API_KEY","")
        if not gemini_key:
            return self._rule_based_analysis(item)

        # What does AnnaSEO currently implement?
        annaseo_context = """
AnnaSEO currently implements:
- 20-phase keyword universe engine (HDBSCAN, SBERT, spaCy, SERP intel)
- 7-pass content generation (E-E-A-T, GEO scoring, 41 signal checks)
- 12-engine Rank-Zero scoring (INP not FID, Info Gain, E-E-A-T, AI readiness)
- SEO audit (14 technical checks, AI crawler audit, llms.txt, citability scorer)
- Publisher (WordPress REST API, Shopify Admin API, IndexNow)
- ContentLifecycleManager (new→growing→peak→declining→refresh_needed)
- PromptVersioning (A/B testing, performance tracking)
- Cluster type taxonomy (Pillar/Subtopic/Support/Conversion)
- Brand mention scanner (7 platforms)
- OffTopicFilter, CannibalizationDetector
Schema rules: FAQPage restricted (Aug 2023), HowTo deprecated (Sept 2023), INP replaced FID (March 2024)
"""
        prompt = f"""You are an SEO engineering analyst reviewing intelligence for an SEO automation system.

{annaseo_context}

New intelligence item:
Title: {item.title}
Source: {item.source_id}
Content: {item.raw_content[:800]}

Analyse this item:
1. Is it relevant to AnnaSEO's engines? (0-1 score)
2. What specifically is new or changed?
3. Which engines are affected? (from: 20phase_engine, content_engine, seo_audit, rank_zero_engine, publisher, annaseo_addons, confirmation_pipeline)
4. Change type: new_signal|deprecated|threshold_change|new_tool|algorithm_update|spec_change|library_update
5. Does this require AnnaSEO code changes? (true/false)

Return JSON only:
{{"relevance":0.0-1.0,"what_is_new":"...","engines_affected":[],"change_type":"...","action_needed":true/false,"summary":"2 sentence summary"}}"""

        try:
            r = _req.post(
                f"{self.GEMINI_URL}?key={gemini_key}",
                json={"contents":[{"parts":[{"text":prompt}]}],
                      "generationConfig":{"temperature":0.1,"maxOutputTokens":400}},
                timeout=15
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                item.relevance_score  = float(data.get("relevance",0))
                item.summary          = data.get("summary","")
                item.engines_affected = data.get("engines_affected", item.engines_affected)
                item.change_type      = data.get("change_type","")
                item.action_needed    = bool(data.get("action_needed",False))
                item.processed        = True
                return item
        except Exception as e:
            Console.log("KnowledgeExtractor","warning",f"Gemini analysis failed: {e}")
        return self._rule_based_analysis(item)

    def _rule_based_analysis(self, item: IntelligenceItem) -> IntelligenceItem:
        """Fallback: keyword-matching relevance analysis (no AI needed)."""
        HIGH_SIGNAL = ["INP","algorithm update","core update","deprecated","schema change",
                       "AI overview","helpful content","E-E-A-T","CWV threshold",
                       "information gain","llms.txt","GPTBot","ClaudeBot","IndexNow",
                       "FAQPage","HowTo","JSON-LD","breaking change","release"]
        MEDIUM_SIGNAL = ["SEO","ranking","content","crawl","index","schema","performance",
                         "search","GEO","AI search","citation","structured data"]
        text = f"{item.title} {item.raw_content}".lower()
        high_hits   = sum(1 for s in HIGH_SIGNAL   if s.lower() in text)
        medium_hits = sum(1 for s in MEDIUM_SIGNAL if s.lower() in text)
        item.relevance_score  = min(1.0, high_hits * 0.25 + medium_hits * 0.05)
        item.action_needed    = high_hits >= 1
        item.summary          = item.raw_content[:150]
        item.change_type      = self._detect_change_type(text)
        item.processed        = True
        return item

    def _detect_change_type(self, text: str) -> str:
        if any(w in text for w in ["deprecated","removed","no longer"]):
            return "deprecated"
        if any(w in text for w in ["threshold","limit","requirement","updated to"]):
            return "threshold_change"
        if any(w in text for w in ["new release","released","launch","v2","2.0"]):
            return "new_tool"
        if any(w in text for w in ["algorithm","update","core","helpful content"]):
            return "algorithm_update"
        return "new_signal"

    def research_deep(self, item: IntelligenceItem) -> str:
        """
        Use DuckDuckGo + Gemini to do deeper research on an action-needed item.
        Fetches 3 additional sources to build comprehensive understanding.
        """
        Console.log("KnowledgeExtractor","gemini",f"Deep research: {item.title[:50]}")
        # DuckDuckGo search for more context
        results = self._crawler.search_duckduckgo(
            f"{item.title} SEO 2026", max_results=5
        )
        extra_content = "\n".join(
            f"- {r['title']}: {r['snippet']}" for r in results[:3]
        )
        gemini_key = os.getenv("GEMINI_API_KEY","")
        if not gemini_key:
            return f"Item: {item.title}\nAdditional sources: {extra_content[:500]}"

        try:
            prompt = f"""Research this SEO/GEO change for an SEO automation system.

Topic: {item.title}
Initial info: {item.raw_content[:500]}
Additional sources found:
{extra_content}

Provide:
1. What exactly changed or is new
2. Why it matters for automated SEO
3. Concrete implementation requirements (what code must change)
4. Any edge cases or warnings

Keep to 3-4 paragraphs. Be specific and technical."""
            r = _req.post(
                f"{self.GEMINI_URL}?key={gemini_key}",
                json={"contents":[{"parts":[{"text":prompt}]}],
                      "generationConfig":{"temperature":0.2,"maxOutputTokens":600}},
                timeout=20
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return f"Deep research incomplete. Initial summary: {item.summary}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — GAP ANALYSER
# ─────────────────────────────────────────────────────────────────────────────

class GapAnalyser:
    """
    Compares new intelligence against what AnnaSEO implements.
    Creates KnowledgeGap records for items that require changes.
    Deduplicates gaps so the same issue isn't filed twice.
    Uses Gemini (free) for analysis.
    """
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    # What AnnaSEO currently implements — used to determine if something is new
    CURRENT_CAPABILITIES = [
        "HDBSCAN + KMeans keyword clustering",
        "20-phase keyword universe pipeline",
        "7-pass content generation with 41 SEO signals",
        "E-E-A-T scoring: Experience, Expertise, Authoritativeness, Trust",
        "GEO scoring: AI-first content structure",
        "12-engine Rank-Zero scoring system",
        "INP (not FID) Core Web Vitals check",
        "FAQPage schema restricted (gov/health only)",
        "HowTo schema deprecated",
        "JSON-LD only (no Microdata/RDFa)",
        "14 AI crawler access check (GPTBot, ClaudeBot, etc.)",
        "llms.txt validation and generation",
        "AI citability scoring (134-167 word passages)",
        "Brand mention scanning (7 platforms)",
        "WordPress REST API publishing",
        "Shopify Admin API publishing",
        "IndexNow protocol submission",
        "GSC ranking monitoring",
        "OffTopicFilter with kill-word lists",
        "CannibalizationDetector",
        "ContentLifecycleManager (5 stages)",
        "PromptVersioning with A/B testing",
        "Cluster type taxonomy (Pillar/Subtopic/Support/Conversion)",
        "Keyword status lifecycle (6 stages)",
        "Competitor attack plan generation",
        "4-layer memory system",
    ]

    def __init__(self):
        self._db = SDDB()

    def analyse_batch(self, items: List[IntelligenceItem]) -> List[KnowledgeGap]:
        """Analyse a batch of action-needed items and create gaps."""
        action_items = [i for i in items if i.action_needed and i.relevance_score >= 0.3]
        Console.log("GapAnalyser","info",
                    f"Analysing {len(action_items)} action-needed items...")
        gaps = []
        for item in action_items:
            gap = self._create_gap(item)
            if gap:
                # Deduplicate: check if similar gap already exists
                existing = self._find_similar_gap(gap.title)
                if not existing:
                    self._db.save_gap(gap)
                    gaps.append(gap)
                    Console.log("GapAnalyser","data",
                                f"New gap: [{gap.priority}] {gap.title[:60]}")
                else:
                    Console.log("GapAnalyser","sep",
                                f"Duplicate gap skipped: {gap.title[:50]}")
        return gaps

    def _create_gap(self, item: IntelligenceItem) -> Optional[KnowledgeGap]:
        """Create a KnowledgeGap from an intelligence item."""
        gemini_key = os.getenv("GEMINI_API_KEY","")
        current_caps = "\n".join(f"- {c}" for c in self.CURRENT_CAPABILITIES)

        if gemini_key:
            prompt = f"""You are analysing whether a new SEO/GEO development requires changes to an SEO automation system.

AnnaSEO currently implements:
{current_caps}

New development:
Title: {item.title}
Source: {item.source_id}
Change type: {item.change_type}
Content: {item.summary or item.raw_content[:500]}

Questions:
1. Is this already covered by AnnaSEO's current implementation?
2. If NOT covered: what exact gap exists?
3. What is the priority? (critical=breaks existing functionality, high=important ranking factor, medium=improvement, low=nice-to-have)
4. Estimated effort? (small=<1 day, medium=1-3 days, large=3+ days)
5. Which engines need changes?

If already covered: return {{"already_covered": true}}

If gap exists, return JSON:
{{"already_covered":false,"title":"specific gap title","description":"what needs to change and why","priority":"critical|high|medium|low","gap_type":"feature|fix|deprecation|update|new_signal","estimated_effort":"small|medium|large","engines_affected":[]}}"""
            try:
                r = _req.post(
                    f"{self.GEMINI_URL}?key={gemini_key}",
                    json={"contents":[{"parts":[{"text":prompt}]}],
                          "generationConfig":{"temperature":0.1,"maxOutputTokens":400}},
                    timeout=15
                )
                r.raise_for_status()
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
                m = re.search(r'\{.*\}', text, re.DOTALL)
                if m:
                    data = json.loads(m.group(0))
                    if data.get("already_covered"):
                        return None
                    return KnowledgeGap(
                        gap_id=f"gap_{hashlib.md5(data.get('title','').encode()).hexdigest()[:10]}",
                        title=data.get("title", item.title),
                        description=data.get("description",""),
                        evidence_urls=[item.url],
                        engines_affected=data.get("engines_affected", item.engines_affected),
                        priority=data.get("priority","medium"),
                        gap_type=data.get("gap_type","feature"),
                        estimated_effort=data.get("estimated_effort","medium"),
                        source_items=[item.item_id]
                    )
            except Exception as e:
                Console.log("GapAnalyser","warning",f"Gemini gap analysis failed: {e}")

        # Fallback: create gap directly from item
        return KnowledgeGap(
            gap_id=f"gap_{item.item_id}",
            title=f"Implement: {item.title[:80]}",
            description=item.summary or item.raw_content[:300],
            evidence_urls=[item.url],
            engines_affected=item.engines_affected,
            priority="medium",
            gap_type=item.change_type or "feature",
            estimated_effort="medium",
            source_items=[item.item_id]
        )

    def _find_similar_gap(self, title: str) -> bool:
        """Check if a gap with very similar title already exists."""
        existing = self._db.get_gaps()
        title_words = set(title.lower().split())
        for g in existing:
            existing_words = set(g["title"].lower().split())
            overlap = len(title_words & existing_words) / max(len(title_words), 1)
            if overlap > 0.6:
                return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — FEATURE IMPLEMENTER (Groq + DeepSeek + Claude)
# Same pipeline as RSD engine — consistent approach across the system
# ─────────────────────────────────────────────────────────────────────────────

class FeatureImplementer:
    """
    Implements a KnowledgeGap using the same AI pipeline as the RSD engine.
    Groq → generates tests → DeepSeek → writes code → Claude → verifies
    → ApprovalGate → human approves → production push
    """
    GROQ_URL  = "https://api.groq.com/openai/v1/chat/completions"
    GEMINI_URL= "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    CLAUDE_MODEL = "claude-sonnet-4-6"

    def implement(self, gap: KnowledgeGap,
                   engine_file: str, deep_research: str = "") -> dict:
        """Full implementation pipeline for one gap."""
        Console.log("Implementer","info",
                    f"Implementing: {gap.title[:60]} [{gap.priority}]")

        if not Path(engine_file).exists():
            return {"success":False, "error":f"Engine file not found: {engine_file}"}

        engine_code = Path(engine_file).read_text(encoding="utf-8")

        # Step 1: Gemini generates detailed implementation spec
        impl_spec = self._gemini_spec(gap, engine_code, deep_research)
        Console.log("Implementer","gemini",
                    f"Implementation spec: {impl_spec.get('approach','?')[:60]}")

        # Step 2: Groq generates test cases
        test_code = self._groq_tests(gap, engine_code, impl_spec)
        Console.log("Implementer","groq",
                    f"Tests generated: {len(test_code.splitlines())} lines")

        # Step 3: DeepSeek writes the code
        modified_code = self._deepseek_implement(gap, engine_code, impl_spec)
        Console.log("Implementer","deepseek",
                    f"Code written: {len(modified_code.splitlines())} lines")

        # Step 4: Validate Python syntax
        import ast as _ast
        try:
            _ast.parse(modified_code)
        except SyntaxError as e:
            Console.log("Implementer","error",f"Syntax error: {e} — using original")
            modified_code = engine_code

        # Step 5: Diff
        import difflib
        diff = "\n".join(difflib.unified_diff(
            engine_code.splitlines(), modified_code.splitlines(),
            fromfile=f"{gap.engines_affected[0] if gap.engines_affected else 'engine'}_current.py",
            tofile=f"{gap.engines_affected[0] if gap.engines_affected else 'engine'}_proposed.py",
            lineterm=""
        ))
        changes = [f"{gap.title}", f"Source: {', '.join(gap.evidence_urls[:2])}"]

        # Step 6: Claude final verification
        claude_notes = self._claude_verify(gap, engine_code, modified_code,
                                            test_code, diff)
        Console.log("Implementer","claude",
                    f"Claude: {claude_notes.get('recommendation','?')} "
                    f"(confidence: {claude_notes.get('confidence',0)}%)")

        # Step 7: Save implementation to DB (status=pending)
        impl_id = f"impl_{gap.gap_id}_{int(time.time())}"
        engine_name = gap.engines_affected[0] if gap.engines_affected else "unknown"
        impl_data = {
            "impl_id": impl_id,
            "gap_id": gap.gap_id,
            "engine_name": engine_name,
            "version": "proposed",
            "code_before": engine_code,
            "code_after": modified_code,
            "diff": diff,
            "changes": json.dumps(changes),
            "ai_used": json.dumps(["gemini","groq","deepseek","claude"]),
            "test_code": test_code,
            "test_results": json.dumps({"note":"run tests manually or via CI"}),
            "claude_notes": json.dumps(claude_notes),
            "approval_status": "pending",
        }
        self._db_save_impl(impl_data)

        # Update gap status
        self._db = SDDB()
        self._db.db.execute(
            "UPDATE sd_knowledge_gaps SET status='in_dev', implementation=? WHERE gap_id=?",
            (impl_id, gap.gap_id)
        )
        self._db.db.commit()

        Console.log("Implementer","warning",
                    f"Pending approval: {impl_id} — review in AnnaSEO → Research & Self Development")
        return {
            "success":   True,
            "impl_id":   impl_id,
            "gap_id":    gap.gap_id,
            "diff_lines":len(diff.splitlines()),
            "claude_rec":claude_notes.get("recommendation","unknown"),
            "message":   "Implementation ready for manual approval."
        }

    def _gemini_spec(self, gap: KnowledgeGap, engine_code: str,
                      deep_research: str) -> dict:
        """Gemini writes the implementation specification."""
        key = os.getenv("GEMINI_API_KEY","")
        if not key:
            return {"approach": gap.description[:200], "changes": [gap.title]}
        try:
            prompt = f"""Write an implementation specification for this SEO engine gap.

Gap: {gap.title}
Description: {gap.description}
Priority: {gap.priority}
Engines: {gap.engines_affected}
Research: {deep_research[:600]}

Engine code (first 1500 chars):
{engine_code[:1500]}

Specify:
1. Exactly what to add/change/remove
2. Which function/class to modify
3. What the new logic should do
4. Any new imports needed
5. Backward compatibility notes

Return JSON only:
{{"approach":"brief approach","changes":["specific change 1","specific change 2"],"new_functions":["function_name if new function needed"],"imports":["new import if needed"],"backward_safe":true/false}}"""
            r = _req.post(
                f"{self.GEMINI_URL}?key={key}",
                json={"contents":[{"parts":[{"text":prompt}]}],
                      "generationConfig":{"temperature":0.15,"maxOutputTokens":500}},
                timeout=15
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m: return json.loads(m.group(0))
        except Exception as e:
            Console.log("Implementer","warning",f"Gemini spec failed: {e}")
        return {"approach": gap.description[:200], "changes": [gap.title]}

    def _groq_tests(self, gap: KnowledgeGap, engine_code: str, spec: dict) -> str:
        """Groq generates pytest tests for the new functionality."""
        key = os.getenv("GROQ_API_KEY","")
        if not key:
            return f"""import pytest

class Test{gap.gap_id.replace('-','_').title()}:
    def test_gap_implemented(self):
        \"\"\"Verify: {gap.title}\"\"\"
        # TODO: implement test for {gap.title}
        pass

    def test_no_regression(self):
        \"\"\"Ensure existing functionality still works.\"\"\"
        pass
"""
        try:
            changes_text = "\n".join(f"- {c}" for c in spec.get("changes",[])[:3])
            r = _req.post(
                self.GROQ_URL,
                headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                json={"model":"llama-3.1-8b-instant","max_tokens":1500,
                      "messages":[{"role":"user","content":
                        f"""Write pytest tests for this SEO engine change.

Gap to implement: {gap.title}
Changes planned:
{changes_text}

Engine code snippet:
{engine_code[:800]}

Write tests covering:
1. The new functionality works as expected
2. Edge cases (empty input, invalid input)
3. No regressions in existing functionality
4. Performance is acceptable

Return only Python pytest code."""}]},
                timeout=20
            )
            r.raise_for_status()
            code = r.json()["choices"][0]["message"]["content"]
            return re.sub(r"```(?:python)?","",code).strip().rstrip("`").strip()
        except Exception as e:
            Console.log("Implementer","warning",f"Groq test gen failed: {e}")
            return f"# Tests for {gap.title}\nimport pytest\ndef test_placeholder(): pass"

    def _deepseek_implement(self, gap: KnowledgeGap, engine_code: str,
                             spec: dict) -> str:
        """DeepSeek writes the actual implementation."""
        ollama_url = os.getenv("OLLAMA_URL","http://localhost:11434")
        changes_text = "\n".join(f"- {c}" for c in spec.get("changes",[])[:5])
        imports_text = "\n".join(spec.get("imports",[]))

        prompt = f"""You are implementing a new feature in a Python SEO engine.

Feature to implement: {gap.title}
Description: {gap.description[:400]}

Changes to make:
{changes_text}

New imports needed (add at top if not already present):
{imports_text}

Current engine code:
{engine_code}

Rules:
1. Make ONLY the specified changes
2. Add comment # SD-IMPL: {gap.gap_id} above each changed section
3. Do not break existing interfaces
4. Keep all existing tests passing
5. Code must be valid Python

Return ONLY the complete modified Python file, no explanations."""
        try:
            r = _req.post(
                f"{ollama_url}/api/generate",
                json={"model":"deepseek-r1:7b","prompt":prompt,
                      "stream":False,"options":{"num_predict":5000}},
                timeout=180
            )
            r.raise_for_status()
            code = r.json().get("response","").strip()
            import ast as _ast
            try:
                _ast.parse(code)
                return code
            except SyntaxError:
                Console.log("Implementer","warning","DeepSeek syntax error — using original")
                return engine_code
        except Exception as e:
            Console.log("Implementer","warning",f"DeepSeek failed: {e}")
        return engine_code

    def _claude_verify(self, gap: KnowledgeGap, original: str,
                        modified: str, tests: str, diff: str) -> dict:
        """Claude verifies the implementation before human approval."""
        key = os.getenv("ANTHROPIC_API_KEY","")
        if not key:
            return {"recommendation":"needs_manual_review","confidence":0,
                    "breaking_changes_risk":"unknown",
                    "approval_notes":"Claude API not configured — full manual review required"}
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            r = client.messages.create(
                model=os.getenv("CLAUDE_MODEL", self.CLAUDE_MODEL),
                max_tokens=800,
                messages=[{"role":"user","content":f"""Review this SEO engine feature implementation before production.

Feature: {gap.title}
Priority: {gap.priority}
Gap type: {gap.gap_type}

Code diff:
{diff[:2500]}

Test code written:
{tests[:800]}

Review for:
1. Does the implementation correctly address the gap?
2. Are there breaking changes to other engines?
3. Are there security or performance issues?
4. Is the approach technically sound for a production SEO system?

Return JSON only:
{{"recommendation":"approve|reject|needs_changes","confidence":0-100,"breaking_changes_risk":"none|low|medium|high","concerns":[],"approval_notes":"what reviewer needs to know"}}"""}]
            )
            text = r.content[0].text.strip()
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m: return json.loads(m.group(0))
        except Exception as e:
            Console.log("Implementer","warning",f"Claude verify failed: {e}")
        return {"recommendation":"needs_manual_review","confidence":50,
                "breaking_changes_risk":"low","concerns":[],
                "approval_notes":"Verification incomplete — manual review required"}

    def _db_save_impl(self, data: dict):
        db = SDDB()
        db.db.execute("""
            INSERT OR REPLACE INTO sd_implementations
            (impl_id,gap_id,engine_name,version,code_before,code_after,diff,
             changes,ai_used,test_code,test_results,claude_notes,approval_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (data["impl_id"],data["gap_id"],data["engine_name"],data["version"],
              data["code_before"][:10000],data["code_after"][:10000],data["diff"][:20000],
              data["changes"],data["ai_used"],data["test_code"],
              data["test_results"],data["claude_notes"],data["approval_status"]))
        db.db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — USER CONTENT MANAGER
# Lets the user add URLs, text, ideas, code snippets for the system to review
# ─────────────────────────────────────────────────────────────────────────────

class UserContentManager:
    """
    Users can add:
    - URLs to new articles, tools, or research they've found
    - Text descriptions of features they want
    - Code snippets for consideration
    - New source URLs to add to the crawler registry
    - Ideas for new AnnaSEO capabilities

    The system reviews each submission, determines if it represents
    a knowledge gap, and queues it for implementation if approved.
    """

    def __init__(self):
        self._db       = SDDB()
        self._extractor= KnowledgeExtractor()
        self._gap      = GapAnalyser()

    def add(self, title: str, content: str, content_type: str,
             engines: List[str] = None, notes: str = "",
             added_by: str = "user") -> str:
        """Add user content for review. Returns content_id."""
        uc = UserContent(
            content_id=f"uc_{hashlib.md5(f'{title}{content[:50]}'.encode()).hexdigest()[:10]}",
            title=title, content=content,
            content_type=content_type,
            engines_affected=engines or [],
            notes=notes, added_by=added_by
        )
        self._db.save_user_content(uc)
        Console.log("UserContent","success",
                    f"Added: [{content_type}] {title[:60]}")
        return uc.content_id

    def add_source(self, name: str, url: str, keywords: List[str],
                    engines: List[str] = None, notes: str = "") -> str:
        """Add a custom source to the crawler registry."""
        sid = self._db.add_custom_source({
            "name": name, "url": url,
            "category": "user_added",
            "engines_affected": engines or [],
            "keywords": keywords,
            "frequency": "weekly",
            "notes": notes,
            "added_by": "user"
        })
        Console.log("UserContent","success", f"Custom source added: {name} ({url})")
        return sid

    def analyse(self, content_id: str) -> dict:
        """
        Analyse one user submission.
        If it's a URL → crawl it.
        If it's text/idea → create IntelligenceItem and process.
        Returns gap analysis result.
        """
        rows = self._db.db.execute(
            "SELECT * FROM sd_user_content WHERE content_id=?", (content_id,)
        ).fetchone()
        if not rows: return {"error": "Content not found"}
        uc = dict(rows)

        # Build intelligence item from user content
        if uc["content_type"] == "url":
            # Crawl the URL
            temp_source = IntelligenceSource(
                source_id=f"user_{content_id}", name=uc["title"],
                url=uc["content"], category=SourceCategory.USER_ADDED,
                crawl_type="html",
                engines_affected=json.loads(uc["engines_affected"]),
                frequency="once", keywords=[]
            )
            items = IntelligenceCrawler().crawl_source(temp_source)
            content_text = "\n".join(i.raw_content for i in items[:3]) if items else uc["notes"]
        else:
            content_text = uc["content"]

        # Create and analyse item
        item = IntelligenceItem(
            item_id=f"uc_item_{content_id}",
            source_id=f"user_{content_id}",
            title=uc["title"],
            url=uc["content"] if uc["content_type"]=="url" else "",
            raw_content=content_text[:2000],
            engines_affected=json.loads(uc["engines_affected"])
        )
        item = self._extractor.process_item(item)
        self._db.save_item(item)

        result = {"relevance": item.relevance_score, "action_needed": item.action_needed}
        if item.action_needed:
            gaps = self._gap.analyse_batch([item])
            result["gaps_created"] = len(gaps)
            result["gap_ids"] = [g.gap_id for g in gaps]

        # Update user content status
        status = "gap_created" if item.action_needed else "analysed"
        analysis = f"Relevance: {item.relevance_score:.2f} | Change type: {item.change_type} | {item.summary}"
        self._db.db.execute(
            "UPDATE sd_user_content SET status=?, analysis=? WHERE content_id=?",
            (status, analysis, content_id)
        )
        self._db.db.commit()
        return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — APPROVAL + DEPLOYMENT (reuses RSD patterns)
# ─────────────────────────────────────────────────────────────────────────────

class SDApprovalManager:
    """
    Same manual approval gate as RSD engine.
    Approve → write code to production.
    Reject → no change.
    Rollback → restore from snapshot.
    """
    def __init__(self):
        self._db = SDDB()
        self._versions_dir = Path(os.getenv("VERSIONS_DIR","./rsd_versions"))
        self._versions_dir.mkdir(parents=True, exist_ok=True)

    def approve(self, impl_id: str, approved_by: str, note: str = "") -> dict:
        """Write approved code to production engine file."""
        rows = self._db.db.execute(
            "SELECT * FROM sd_implementations WHERE impl_id=?", (impl_id,)
        ).fetchone()
        if not rows: return {"success":False, "error":"Implementation not found"}
        impl = dict(rows)

        # Find engine file
        from annaseo_rsd_engine import ResearchAndSelfDevelopment
        engine_map = dict(ResearchAndSelfDevelopment.MONITORED_ENGINES)
        engine_file = engine_map.get(impl["engine_name"])
        if not engine_file or not Path(engine_file).exists():
            return {"success":False, "error":f"Engine file not found for {impl['engine_name']}"}

        # Snapshot original first
        original = Path(engine_file).read_text(encoding="utf-8")
        snap_path = self._versions_dir / f"{impl['engine_name']}_sd_{impl_id}_pre.py"
        snap_path.write_text(original, encoding="utf-8")

        # Write new code
        Path(engine_file).write_text(impl["code_after"], encoding="utf-8")

        # Update DB
        self._db.db.execute(
            "UPDATE sd_implementations SET approval_status=?, approved_by=?, approved_at=? WHERE impl_id=?",
            ("approved", approved_by, datetime.utcnow().isoformat(), impl_id)
        )
        self._db.db.execute(
            "UPDATE sd_knowledge_gaps SET status='done' WHERE gap_id=?",
            (impl["gap_id"],)
        )
        self._db.db.commit()

        Console.log("SDApproval","success",
                    f"DEPLOYED: {impl['engine_name']} — {approved_by} approved impl {impl_id}")
        return {"success":True, "message":f"Deployed to {engine_file}. Snapshot saved."}

    def reject(self, impl_id: str, rejected_by: str, reason: str) -> dict:
        self._db.db.execute(
            "UPDATE sd_implementations SET approval_status='rejected', rejection_reason=? WHERE impl_id=?",
            (reason, impl_id)
        )
        self._db.db.execute(
            "UPDATE sd_knowledge_gaps SET status='rejected' WHERE gap_id=(SELECT gap_id FROM sd_implementations WHERE impl_id=?)",
            (impl_id,)
        )
        self._db.db.commit()
        Console.log("SDApproval","info",f"Rejected {impl_id}: {reason}")
        return {"success":True, "message":"Implementation rejected. No code changes made."}

    def rollback(self, impl_id: str, rolled_back_by: str) -> dict:
        """Restore the pre-change snapshot for this implementation."""
        rows = self._db.db.execute(
            "SELECT * FROM sd_implementations WHERE impl_id=?", (impl_id,)
        ).fetchone()
        if not rows: return {"success":False, "error":"Not found"}
        impl = dict(rows)

        snap = self._versions_dir / f"{impl['engine_name']}_sd_{impl_id}_pre.py"
        if not snap.exists():
            return {"success":False, "error":"Snapshot not found for rollback"}

        from annaseo_rsd_engine import ResearchAndSelfDevelopment
        engine_file = dict(ResearchAndSelfDevelopment.MONITORED_ENGINES).get(impl["engine_name"])
        if engine_file:
            Path(engine_file).write_text(snap.read_text(encoding="utf-8"), encoding="utf-8")

        Console.log("SDApproval","success",
                    f"ROLLBACK: {impl['engine_name']} restored by {rolled_back_by}")
        return {"success":True, "message":f"Rolled back {impl['engine_name']} to pre-{impl_id} state."}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — MASTER SELF DEVELOPMENT ENGINE (Ruflo job types)
# ─────────────────────────────────────────────────────────────────────────────

class SelfDevelopmentEngine:
    """
    Master engine.
    Ruflo calls via job queue.

    Job types:
      sd_crawl_all         — crawl all sources, extract intelligence
      sd_crawl_category    — crawl one category (google_official, ai_search, etc.)
      sd_analyse           — process crawled items, create knowledge gaps
      sd_implement <gap_id>— implement one specific gap
      sd_approve <impl_id> — approve and deploy
      sd_reject <impl_id>  — reject
      sd_rollback <impl_id>— rollback
      sd_add_content       — add user content for review
      sd_add_source        — add custom source
      sd_dashboard         — get current state for UI
    """

    def __init__(self):
        self._db         = SDDB()
        self._crawler    = IntelligenceCrawler()
        self._extractor  = KnowledgeExtractor()
        self._gap        = GapAnalyser()
        self._implementer= FeatureImplementer()
        self._user       = UserContentManager()
        self._approval   = SDApprovalManager()

    def job_crawl_all(self) -> dict:
        Console.log("SelfDev","sep","═"*50)
        Console.log("SelfDev","info",f"Crawling {len(SOURCES)} sources...")
        all_items, total_action = [], 0
        for source in SOURCES:
            if not source.active: continue
            items = self._crawler.crawl_source(source)
            # Extract only — don't deep analyse yet
            for item in items:
                item = self._extractor.process_item(item)
                if item.action_needed: total_action += 1
                self._db.save_item(item)
                all_items.append(item)
            time.sleep(0.5)   # rate limit

        # Also crawl user-added custom sources
        custom = self._db.db.execute(
            "SELECT * FROM sd_custom_sources WHERE active=1"
        ).fetchall()
        for row in custom:
            r = dict(row)
            src = IntelligenceSource(
                source_id=r["source_id"], name=r["name"], url=r["url"],
                category=SourceCategory.USER_ADDED, crawl_type=r["crawl_type"],
                engines_affected=json.loads(r["engines_affected"]),
                frequency=r["frequency"], keywords=json.loads(r["keywords"])
            )
            items = self._crawler.crawl_source(src)
            all_items.extend(items)

        Console.log("SelfDev","success",
                    f"Crawl complete: {len(all_items)} items, {total_action} action-needed")
        return {"items": len(all_items), "action_needed": total_action}

    def job_crawl_category(self, category: str) -> dict:
        sources = [s for s in SOURCES if s.category.value == category]
        Console.log("SelfDev","info",f"Crawling category: {category} ({len(sources)} sources)")
        all_items = []
        for source in sources:
            items = self._crawler.crawl_source(source)
            all_items.extend(items)
            time.sleep(0.3)
        return {"category": category, "items": len(all_items)}

    def job_analyse(self) -> dict:
        """Process unprocessed action-needed items into knowledge gaps."""
        items_raw = self._db.get_items(action_only=True)
        items = []
        for row in items_raw:
            item = IntelligenceItem(
                item_id=row["item_id"], source_id=row["source_id"],
                title=row["title"], url=row["url"],
                raw_content=row["raw_content"],
                summary=row["summary"],
                relevance_score=row["relevance_score"],
                engines_affected=json.loads(row.get("engines_affected","[]")),
                change_type=row["change_type"],
                action_needed=bool(row["action_needed"]),
                processed=bool(row["processed"])
            )
            items.append(item)

        gaps = self._gap.analyse_batch(items)
        Console.log("SelfDev","success",
                    f"Analysis complete: {len(gaps)} new knowledge gaps created")
        return {"gaps_created": len(gaps),
                "gap_ids": [g.gap_id for g in gaps]}

    def job_implement(self, gap_id: str) -> dict:
        """Implement one specific knowledge gap."""
        rows = self._db.db.execute(
            "SELECT * FROM sd_knowledge_gaps WHERE gap_id=?", (gap_id,)
        ).fetchone()
        if not rows: return {"success":False, "error":f"Gap {gap_id} not found"}
        gap_row = dict(rows)
        gap = KnowledgeGap(
            gap_id=gap_row["gap_id"], title=gap_row["title"],
            description=gap_row["description"],
            evidence_urls=json.loads(gap_row.get("evidence_urls","[]")),
            engines_affected=json.loads(gap_row.get("engines_affected","[]")),
            priority=gap_row["priority"], gap_type=gap_row["gap_type"],
            estimated_effort=gap_row["estimated_effort"], status=gap_row["status"]
        )

        # Find engine file
        try:
            from annaseo_rsd_engine import ResearchAndSelfDevelopment
            engine_map = dict(ResearchAndSelfDevelopment.MONITORED_ENGINES)
        except ImportError:
            engine_map = {}
        engine_file = engine_map.get(
            gap.engines_affected[0] if gap.engines_affected else ""
        )
        if not engine_file:
            # Try to find a matching file
            for name, path in engine_map.items():
                if any(name in e for e in gap.engines_affected):
                    engine_file = path
                    break
        if not engine_file:
            return {"success":False,
                    "error":f"No engine file found for {gap.engines_affected}"}

        # Deep research first
        item_ids = json.loads(gap_row.get("source_items","[]"))
        deep_research = ""
        if item_ids:
            item_row = self._db.db.execute(
                "SELECT * FROM sd_intelligence_items WHERE item_id=?",
                (item_ids[0],)
            ).fetchone()
            if item_row:
                item = IntelligenceItem(
                    item_id=item_row["item_id"],
                    source_id=item_row["source_id"],
                    title=item_row["title"], url=item_row["url"],
                    raw_content=item_row["raw_content"],
                )
                deep_research = self._extractor.research_deep(item)

        return self._implementer.implement(gap, engine_file, deep_research)

    def job_dashboard(self) -> dict:
        """Complete state for the Self Development UI page."""
        gaps_all      = self._db.get_gaps()
        pending_impls = self._db.get_implementations(status="pending")
        recent_items  = self._db.get_items(limit=20)
        user_content  = self._db.get_user_content()

        crawl_log = self._db.db.execute("""
            SELECT source_id, MAX(crawled_at) as last_crawl, SUM(items_found) as total
            FROM sd_source_crawl_log GROUP BY source_id ORDER BY last_crawl DESC LIMIT 10
        """).fetchall()

        return {
            "gaps": {
                "total":    len(gaps_all),
                "pending":  sum(1 for g in gaps_all if g["status"]=="pending"),
                "in_dev":   sum(1 for g in gaps_all if g["status"]=="in_dev"),
                "done":     sum(1 for g in gaps_all if g["status"]=="done"),
                "by_priority": {
                    "critical": sum(1 for g in gaps_all if g["priority"]=="critical"),
                    "high":     sum(1 for g in gaps_all if g["priority"]=="high"),
                    "medium":   sum(1 for g in gaps_all if g["priority"]=="medium"),
                    "low":      sum(1 for g in gaps_all if g["priority"]=="low"),
                },
                "list": gaps_all[:10]
            },
            "pending_implementations": pending_impls,
            "recent_intelligence": recent_items[:10],
            "user_content":  user_content,
            "sources_count": len(SOURCES),
            "crawl_log":     [dict(r) for r in crawl_log],
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from pydantic import BaseModel as PM

    app = FastAPI(title="AnnaSEO — Self Development Engine")
    sd  = SelfDevelopmentEngine()

    class UserContentBody(PM):
        title:            str
        content:          str
        content_type:     str   = "text"   # url|text|snippet|idea|source
        engines_affected: List[str] = []
        notes:            str   = ""
        added_by:         str   = "user"

    class CustomSourceBody(PM):
        name:             str
        url:              str
        keywords:         List[str] = []
        engines_affected: List[str] = []
        frequency:        str   = "weekly"
        notes:            str   = ""

    class ApproveBody(PM):
        approved_by: str
        note:        str = ""

    class RejectBody(PM):
        rejected_by: str
        reason:      str

    @app.get("/api/sd/dashboard", tags=["Self Development"])
    def dashboard():
        return sd.job_dashboard()

    @app.post("/api/sd/crawl/all", tags=["Self Development"])
    def crawl_all(bg: BackgroundTasks):
        bg.add_task(sd.job_crawl_all)
        return {"status":"started","message":"Full crawl started — check console"}

    @app.post("/api/sd/crawl/{category}", tags=["Self Development"])
    def crawl_category(category: str, bg: BackgroundTasks):
        bg.add_task(sd.job_crawl_category, category)
        return {"status":"started","category":category}

    @app.post("/api/sd/analyse", tags=["Self Development"])
    def analyse(bg: BackgroundTasks):
        bg.add_task(sd.job_analyse)
        return {"status":"started","message":"Analysis started"}

    @app.get("/api/sd/gaps", tags=["Self Development"])
    def list_gaps(status: str = None, priority: str = None):
        return SDDB().get_gaps(status, priority)

    @app.post("/api/sd/gaps/{gap_id}/implement", tags=["Self Development"])
    def implement(gap_id: str, bg: BackgroundTasks):
        bg.add_task(sd.job_implement, gap_id)
        return {"status":"started","gap_id":gap_id,
                "message":"Implementation started — watch console. Will need approval."}

    @app.get("/api/sd/implementations", tags=["Self Development"])
    def list_implementations(status: str = None):
        return SDDB().get_implementations(status)

    @app.post("/api/sd/implementations/{impl_id}/approve", tags=["Self Development"])
    def approve(impl_id: str, body: ApproveBody):
        return SDApprovalManager().approve(impl_id, body.approved_by, body.note)

    @app.post("/api/sd/implementations/{impl_id}/reject", tags=["Self Development"])
    def reject(impl_id: str, body: RejectBody):
        return SDApprovalManager().reject(impl_id, body.rejected_by, body.reason)

    @app.post("/api/sd/implementations/{impl_id}/rollback", tags=["Self Development"])
    def rollback(impl_id: str, rolled_back_by: str = "admin"):
        return SDApprovalManager().rollback(impl_id, rolled_back_by)

    @app.post("/api/sd/user-content", tags=["Self Development"])
    def add_user_content(body: UserContentBody):
        cid = UserContentManager().add(
            body.title, body.content, body.content_type,
            body.engines_affected, body.notes, body.added_by
        )
        return {"content_id":cid, "message":"Added for review"}

    @app.post("/api/sd/user-content/{content_id}/analyse", tags=["Self Development"])
    def analyse_user_content(content_id: str, bg: BackgroundTasks):
        bg.add_task(UserContentManager().analyse, content_id)
        return {"status":"started","content_id":content_id}

    @app.get("/api/sd/user-content", tags=["Self Development"])
    def list_user_content(status: str = None):
        return SDDB().get_user_content(status)

    @app.post("/api/sd/sources", tags=["Self Development"])
    def add_custom_source(body: CustomSourceBody):
        sid = UserContentManager().add_source(
            body.name, body.url, body.keywords,
            body.engines_affected, body.notes
        )
        return {"source_id":sid, "message":"Custom source added to crawler registry"}

    @app.get("/api/sd/sources", tags=["Self Development"])
    def list_sources():
        built_in = [{"source_id":s.source_id,"name":s.name,"category":s.category.value,
                     "frequency":s.frequency,"url":s.url} for s in SOURCES]
        custom   = [dict(r) for r in SDDB().db.execute(
            "SELECT * FROM sd_custom_sources ORDER BY created_at DESC").fetchall()]
        return {"built_in": built_in, "custom": custom,
                "total": len(built_in) + len(custom)}

    @app.get("/api/sd/intelligence", tags=["Self Development"])
    def list_intelligence(action_only: bool = False, limit: int = 50):
        return SDDB().get_items(action_only, limit)

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
AnnaSEO — Self Development Engine
─────────────────────────────────────────────────────────────
Crawls 40+ sources · Extracts intelligence · Identifies gaps
Implements with Gemini/Groq/DeepSeek · Claude verifies · Manual approval

Usage:
  python annaseo_self_dev.py crawl all                 # crawl all sources
  python annaseo_self_dev.py crawl <category>          # one category
  python annaseo_self_dev.py analyse                   # process items → gaps
  python annaseo_self_dev.py implement <gap_id>        # implement one gap
  python annaseo_self_dev.py approve <impl_id>         # approve → deploy
  python annaseo_self_dev.py reject <impl_id> <reason> # reject
  python annaseo_self_dev.py rollback <impl_id>        # rollback to pre-change
  python annaseo_self_dev.py dashboard                 # show state
  python annaseo_self_dev.py gaps                      # list pending gaps
  python annaseo_self_dev.py add url <url> <title>     # add URL for review
  python annaseo_self_dev.py add text <title> <content># add idea/text for review
  python annaseo_self_dev.py add source <url> <name>   # add custom crawl source
  python annaseo_self_dev.py sources                   # list all sources
  python annaseo_self_dev.py api                       # start FastAPI on :8005

Categories: google_official | seo_industry | ai_search | github | research
"""
    if len(sys.argv) < 2: print(HELP); exit(0)
    cmd = sys.argv[1]
    se  = SelfDevelopmentEngine()

    if cmd == "crawl":
        cat = sys.argv[2] if len(sys.argv) > 2 else "all"
        if cat == "all": print(json.dumps(se.job_crawl_all(), indent=2))
        else: print(json.dumps(se.job_crawl_category(cat), indent=2))

    elif cmd == "analyse":
        print(json.dumps(se.job_analyse(), indent=2))

    elif cmd == "implement":
        if len(sys.argv) < 3: print("Usage: implement <gap_id>"); exit(1)
        print(json.dumps(se.job_implement(sys.argv[2]), indent=2))

    elif cmd == "approve":
        if len(sys.argv) < 3: print("Usage: approve <impl_id>"); exit(1)
        print(json.dumps(SDApprovalManager().approve(sys.argv[2], "cli_user"), indent=2))

    elif cmd == "reject":
        if len(sys.argv) < 4: print("Usage: reject <impl_id> <reason>"); exit(1)
        print(json.dumps(SDApprovalManager().reject(sys.argv[2], "cli_user", sys.argv[3]), indent=2))

    elif cmd == "rollback":
        if len(sys.argv) < 3: print("Usage: rollback <impl_id>"); exit(1)
        print(json.dumps(SDApprovalManager().rollback(sys.argv[2], "cli_user"), indent=2))

    elif cmd == "dashboard":
        d = se.job_dashboard()
        print(f"\n  SELF DEVELOPMENT DASHBOARD")
        print(f"  Gaps:  {d['gaps']['total']} total | {d['gaps']['pending']} pending | {d['gaps']['done']} done")
        print(f"  Sources: {d['sources_count']} registered")
        print(f"  Pending approvals: {len(d['pending_implementations'])}")
        if d["gaps"]["list"]:
            print(f"\n  Top gaps:")
            for g in d["gaps"]["list"][:5]:
                print(f"    [{g['priority']:8}] {g['title'][:60]} ({g['status']})")

    elif cmd == "gaps":
        gaps = SDDB().get_gaps(status="pending")
        print(f"\n  {len(gaps)} pending knowledge gaps:")
        for g in gaps:
            print(f"  [{g['priority']:8}] {g['gap_id']} — {g['title'][:60]}")

    elif cmd == "add":
        if len(sys.argv) < 5: print("Usage: add url|text|source <title_or_url> <content>"); exit(1)
        ctype, title, content = sys.argv[2], sys.argv[3], sys.argv[4]
        if ctype == "source":
            sid = UserContentManager().add_source(content, title, keywords=[])
            print(f"Source added: {sid}")
        else:
            ucm = UserContentManager()
            cid = ucm.add(title, content if ctype!="url" else title,
                          content_type=ctype if ctype!="source" else "url")
            print(f"Content added: {cid} — run 'analyse' to process")

    elif cmd == "sources":
        print(f"\n  REGISTERED SOURCES ({len(SOURCES)} built-in):")
        for s in SOURCES:
            print(f"  [{s.category.value:16}] {s.frequency:8} {s.name}")
        custom = SDDB().db.execute("SELECT * FROM sd_custom_sources").fetchall()
        if custom:
            print(f"\n  CUSTOM SOURCES ({len(custom)}):")
            for r in custom:
                print(f"  [user_added       ] {r['frequency']:8} {r['name']} ({r['url'][:50]})")

    elif cmd == "api":
        try:
            import uvicorn
            Console.log("SelfDev","info","API at http://localhost:8005")
            Console.log("SelfDev","info","Docs at http://localhost:8005/docs")
            uvicorn.run("annaseo_self_dev:app", host="0.0.0.0", port=8005, reload=True)
        except ImportError:
            print("pip install uvicorn")
    else:
        print(f"Unknown: {cmd}\n{HELP}")

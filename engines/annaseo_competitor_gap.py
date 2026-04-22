"""
================================================================================
ANNASEO — COMPETITOR KEYWORD GAP ENGINE  (annaseo_competitor_gap.py)
================================================================================
Answers: "What keywords do my competitors rank for that I don't?"

Pipeline
────────
  1. Crawl competitor URLs → extract all on-page keywords + headings
  2. Cross-reference with free search data (DuckDuckGo, Google autosuggest)
  3. Score each gap by traffic × difficulty × your domain's ability to rank
  4. Generate "attack plan": ordered list of articles to write
  5. Domain Context validation: filter out off-domain gaps per project

AI usage (all free)
  Gemini → analyse competitor content, extract keyword intent
  DeepSeek → generate attack plan content briefs
  Claude → final attack plan summary + prioritisation (verification only)

Integration
  Called after P10_PillarIdentification in the keyword pipeline
  Results stored in competitor_gaps table
  Surfaces in Dashboard as "Keyword Opportunities"
================================================================================
"""

from __future__ import annotations

import os, re, json, hashlib, time, logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse, urljoin

import requests as _req
from bs4 import BeautifulSoup

log = logging.getLogger("annaseo.competitor_gap")

def _GEMINI_URL() -> str:
    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompetitorPage:
    url:          str
    domain:       str
    title:        str
    headings:     List[str] = field(default_factory=list)
    keywords:     List[str] = field(default_factory=list)
    word_count:   int = 0
    content_type: str = ""   # "pillar"|"cluster"|"product"|"guide"
    crawled_at:   str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class KeywordGap:
    keyword:          str
    competitor_urls:  List[str]         # competitors ranking for this
    gap_type:         str               # "missing_pillar"|"missing_cluster"|"missing_content"
    traffic_estimate: int = 0
    difficulty:       int = 50          # 0-100
    opportunity_score:float = 0.0       # 0-100: traffic × (1 - difficulty/100)
    intent:           str = "informational"
    content_brief:    dict = field(default_factory=dict)
    priority:         str = "medium"    # "critical"|"high"|"medium"|"low"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — COMPETITOR CRAWLER
# ─────────────────────────────────────────────────────────────────────────────

class CompetitorCrawler:
    HEADERS = {
        "User-Agent": "AnnaSEO-Competitor-Analysis/1.0 (research bot)",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }

    def crawl(self, url: str, max_pages: int = 20) -> List[CompetitorPage]:
        """Crawl a competitor domain: homepage + sitemap + top pages."""
        pages = []
        domain = "{0.scheme}://{0.netloc}".format(urlparse(url))
        log.info(f"[CompGap] Crawling {domain} (max {max_pages} pages)")

        # Try sitemap first
        sitemap_urls = self._parse_sitemap(domain)
        urls_to_crawl = list(dict.fromkeys([url] + sitemap_urls[:max_pages]))[:max_pages]

        for page_url in urls_to_crawl:
            page = self._crawl_page(page_url, domain)
            if page and page.keywords:
                pages.append(page)
            time.sleep(1.0)   # polite rate limit

        log.info(f"[CompGap] Crawled {len(pages)} pages from {domain}")
        return pages

    def _crawl_page(self, url: str, domain: str) -> Optional[CompetitorPage]:
        try:
            r = _req.get(url, headers=self.HEADERS, timeout=12)
            if not r.ok or "text/html" not in r.headers.get("content-type",""):
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.find("title")
            title = title.get_text(strip=True) if title else ""
            # Extract headings
            headings = [h.get_text(strip=True) for tag in ["h1","h2","h3"]
                         for h in soup.find_all(tag)][:30]
            # Extract text body
            for tag in soup(["script","style","nav","footer","header"]):
                tag.decompose()
            text = " ".join(soup.get_text().split())
            words = text.split()
            # Extract keyword phrases (2-4 word n-grams that appear 2+ times)
            keywords = self._extract_keywords(text, title, headings)
            return CompetitorPage(
                url=url, domain=domain, title=title,
                headings=headings, keywords=keywords,
                word_count=len(words)
            )
        except Exception as e:
            log.debug(f"[CompGap] Crawl failed {url}: {e}")
            return None

    def _parse_sitemap(self, domain: str) -> List[str]:
        """Try /sitemap.xml and /sitemap_index.xml."""
        urls = []
        for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap.txt"]:
            try:
                r = _req.get(f"{domain}{path}", headers=self.HEADERS, timeout=8)
                if not r.ok: continue
                if "xml" in r.headers.get("content-type",""):
                    soup = BeautifulSoup(r.text, "xml")
                    urls += [loc.get_text().strip() for loc in soup.find_all("loc")][:50]
                elif "text" in r.headers.get("content-type",""):
                    urls += [u.strip() for u in r.text.splitlines() if u.strip()][:50]
                if urls: break
            except Exception:
                continue
        return [u for u in urls if u.startswith(domain)][:30]

    def _extract_keywords(self, text: str, title: str, headings: List[str]) -> List[str]:
        """Extract 2-4 word keyword phrases that appear 2+ times."""
        import re as _re
        text_lower = (title + " " + " ".join(headings) + " " + text).lower()
        text_lower = _re.sub(r"[^a-z0-9\s]", " ", text_lower)
        words  = text_lower.split()
        counts: Dict[str, int] = {}
        # 2-grams and 3-grams
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i+n])
                if not any(sw in phrase.split() for sw in
                           ["the","is","are","was","were","be","been","have",
                            "had","do","does","did","will","would","could","should"]):
                    counts[phrase] = counts.get(phrase, 0) + 1
        # Return phrases appearing 2+ times, sorted by frequency
        return [k for k, v in sorted(counts.items(), key=lambda x: -x[1]) if v >= 2][:50]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — GAP ANALYSER
# ─────────────────────────────────────────────────────────────────────────────

class GapAnalyser:
    """
    Compare competitor keywords against the project's existing keyword universe.
    Find gaps → score by opportunity → classify type.
    """

    def find_gaps(self, competitor_pages: List[CompetitorPage],
                   project_keywords: List[str],
                   project_id: str,
                   seed: str) -> List[KeywordGap]:
        """
        competitor_pages:  crawled competitor content
        project_keywords:  all keywords in the project's universe (already generated)
        project_id:        for domain context validation
        seed:              seed keyword for context
        """
        # Collect all competitor keywords
        comp_keywords: Dict[str, List[str]] = {}  # keyword → [competitor_urls]
        for page in competitor_pages:
            for kw in page.keywords:
                if kw not in comp_keywords:
                    comp_keywords[kw] = []
                if page.url not in comp_keywords[kw]:
                    comp_keywords[kw].append(page.url)

        # Find keywords in competitor content but NOT in our universe
        our_kws = set(kw.lower() for kw in project_keywords)
        gaps_raw = {kw: urls for kw, urls in comp_keywords.items()
                    if kw not in our_kws and len(urls) >= 1}

        log.info(f"[CompGap] Found {len(gaps_raw)} raw gaps vs {len(our_kws)} our keywords")

        # Domain context filter (project-isolated)
        try:
            from annaseo_domain_context import DomainContextEngine
            dce = DomainContextEngine()
            filtered = {}
            for kw, urls in gaps_raw.items():
                result = dce.classify(kw, project_id)
                if result["verdict"] != "reject":
                    filtered[kw] = urls
            gaps_raw = filtered
            log.info(f"[CompGap] After domain filter: {len(gaps_raw)} gaps")
        except Exception as e:
            log.warning(f"[CompGap] Domain context unavailable: {e}")

        # Score and classify
        gaps = []
        for kw, urls in list(gaps_raw.items())[:100]:   # top 100
            score = self._opportunity_score(kw, len(urls))
            gap   = KeywordGap(
                keyword=kw,
                competitor_urls=urls[:3],
                gap_type=self._classify_gap_type(kw, urls),
                traffic_estimate=self._estimate_traffic(kw, len(urls)),
                difficulty=self._estimate_difficulty(kw, len(urls)),
                opportunity_score=score,
                priority=("critical" if score >= 80 else
                           "high"     if score >= 60 else
                           "medium"   if score >= 40 else "low"),
            )
            gaps.append(gap)

        return sorted(gaps, key=lambda g: -g.opportunity_score)[:50]

    def _opportunity_score(self, kw: str, competitor_count: int) -> float:
        """Higher score = more competitors have it + easier to rank for."""
        word_count = len(kw.split())
        # More specific (longer) = lower difficulty
        specificity_bonus = min(word_count * 8, 25)
        # More competitors covering it = higher traffic potential
        traffic_signal = min(competitor_count * 20, 50)
        # Question keywords tend to be featured snippet opportunities
        question_bonus = 15 if any(kw.startswith(q) for q in
                                    ["how","what","why","when","which","best","is"]) else 0
        return min(100, specificity_bonus + traffic_signal + question_bonus + 10)

    def _estimate_traffic(self, kw: str, competitor_count: int) -> int:
        # Very rough estimate — replace with real volume data if DataForSEO available
        base = competitor_count * 200
        if any(kw.startswith(q) for q in ["how","what","best"]): base *= 2
        return min(base, 10000)

    def _estimate_difficulty(self, kw: str, competitor_count: int) -> int:
        words = len(kw.split())
        if words >= 4: return max(10, 50 - competitor_count * 5)   # long-tail = easier
        if words == 3: return max(20, 55 - competitor_count * 3)
        return max(40, 70 - competitor_count * 2)                   # short = harder

    def _classify_gap_type(self, kw: str, urls: List[str]) -> str:
        words = len(kw.split())
        if words <= 2: return "missing_pillar"
        if words <= 4: return "missing_cluster"
        return "missing_content"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — ATTACK PLAN GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class AttackPlanGenerator:
    """
    Gemini + DeepSeek → generate content briefs for top gap keywords.
    Claude → final attack plan summary.
    """

    def generate(self, gaps: List[KeywordGap], seed: str,
                  project_id: str, project_name: str = "") -> dict:
        log.info(f"[CompGap] Generating attack plan for {len(gaps)} gaps")

        # Step 1: Gemini analyses top 10 gaps
        top_gaps  = gaps[:10]
        gap_analysis = self._gemini_analyse(top_gaps, seed, project_name)

        # Step 2: DeepSeek generates brief for top 5
        briefs = []
        for gap in top_gaps[:5]:
            brief = self._deepseek_brief(gap, seed)
            briefs.append({"keyword": gap.keyword, "brief": brief,
                            "priority": gap.priority,
                            "opportunity": round(gap.opportunity_score, 1)})

        # Step 3: Claude final summary (verification only)
        claude_summary = self._claude_summary(top_gaps, gap_analysis, project_name)

        return {
            "project_id":    project_id,
            "seed":          seed,
            "total_gaps":    len(gaps),
            "quick_wins":    [g.keyword for g in gaps if g.priority == "critical"][:5],
            "high_priority": [g.keyword for g in gaps if g.priority == "high"][:10],
            "all_gaps":      [{"keyword": g.keyword, "type": g.gap_type,
                                "opportunity": round(g.opportunity_score, 1),
                                "priority": g.priority,
                                "competitors": len(g.competitor_urls)}
                               for g in gaps[:30]],
            "content_briefs":  briefs,
            "gemini_analysis": gap_analysis,
            "claude_summary":  claude_summary,
            "generated_at":    datetime.utcnow().isoformat(),
        }

    def _gemini_analyse(self, gaps: List[KeywordGap], seed: str,
                         business: str) -> dict:
        key = os.getenv("GEMINI_API_KEY","")
        if not key:
            return {"patterns": [], "top_opportunity": gaps[0].keyword if gaps else ""}
        gap_text = "\n".join(f"- {g.keyword} (score:{g.opportunity_score:.0f}, "
                              f"type:{g.gap_type}, competitors:{len(g.competitor_urls)})"
                              for g in gaps[:10])
        try:
            r = _req.post(
                f"{_GEMINI_URL()}?key={key}",
                json={"contents":[{"parts":[{"text":
                    f"SEO gap analysis for {business or 'business'} in '{seed}' niche.\n\n"
                    f"Competitor keywords we're missing:\n{gap_text}\n\n"
                    f"Identify: 1) Content patterns in the gaps 2) Top 3 opportunities "
                    f"3) Recommended content type for each gap type\n"
                    f"Return JSON: {{\"patterns\":[...],\"top_3\":[...],\"strategy\":\"...\"}}"}]}],
                    "generationConfig":{"temperature":0.1,"maxOutputTokens":400}},
                timeout=15
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m: return json.loads(m.group(0))
        except Exception as e:
            log.warning(f"[CompGap] Gemini analysis failed: {e}")
        return {"patterns": [], "top_3": [g.keyword for g in gaps[:3]], "strategy": ""}

    def _deepseek_brief(self, gap: KeywordGap, seed: str) -> dict:
        try:
            from core.ai_config import AIRouter
            prompt = (
                f"Write a content brief for this SEO gap keyword: '{gap.keyword}'\n"
                f"Seed business: {seed}\n"
                f"Gap type: {gap.gap_type}\n"
                f"Competitor URLs covering this: {gap.competitor_urls[:2]}\n\n"
                f"Provide: H1 title, 4 H2 headings, 2 FAQ questions, target word count.\n"
                f"Return JSON: {{\"title\":\"...\",\"h2s\":[...],\"faqs\":[...],\"word_count\":0}}"
            )
            text = AIRouter._call_ollama(prompt, "You are an SEO content strategist.", 0.1)
            if text:
                m = re.search(r'\{.*\}', text, re.DOTALL)
                if m: return json.loads(m.group(0))
        except Exception as e:
            log.warning(f"[CompGap] DeepSeek brief failed: {e}")
        return {"title": f"Complete Guide to {gap.keyword}",
                "h2s": [f"What is {gap.keyword}", f"Why it matters",
                         f"How to use {gap.keyword}", "Expert tips"],
                "faqs": [f"What is {gap.keyword}?", f"How does {gap.keyword} work?"],
                "word_count": 1800}

    def _claude_summary(self, gaps: List[KeywordGap], analysis: dict,
                          business: str) -> str:
        key = os.getenv("ANTHROPIC_API_KEY","")
        if not key:
            return f"Found {len(gaps)} keyword gaps. Top opportunity: {gaps[0].keyword if gaps else 'N/A'}."
        try:
            import anthropic
            top_kws = [g.keyword for g in gaps[:5]]
            client  = anthropic.Anthropic(api_key=key)
            r = client.messages.create(
                model=os.getenv("CLAUDE_MODEL","claude-sonnet-4-6"),
                max_tokens=300,
                messages=[{"role":"user","content":
                    f"Summarise this SEO opportunity for {business or 'this business'}.\n"
                    f"Top {len(gaps)} keyword gaps found vs competitors.\n"
                    f"Top gaps: {top_kws}\n"
                    f"Pattern analysis: {analysis.get('strategy','')}\n\n"
                    f"In 2-3 sentences: what is the biggest opportunity and what should be built first?"}]
            )
            return r.content[0].text.strip()
        except Exception as e:
            log.warning(f"[CompGap] Claude summary failed: {e}")
        return f"Found {len(gaps)} gaps. Focus on: {', '.join(g.keyword for g in gaps[:3])}."


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — DATABASE
# ─────────────────────────────────────────────────────────────────────────────

import sqlite3
DB_PATH = Path(os.getenv("ANNASEO_DB","./annaseo.db"))

def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS competitor_domains (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        domain     TEXT NOT NULL,
        notes      TEXT DEFAULT '',
        active     INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS competitor_gaps (
        gap_id     TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        keyword    TEXT NOT NULL,
        gap_type   TEXT DEFAULT 'missing_content',
        opportunity REAL DEFAULT 0,
        priority   TEXT DEFAULT 'medium',
        competitors TEXT DEFAULT '[]',
        content_brief TEXT DEFAULT '{}',
        status     TEXT DEFAULT 'open',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS competitor_attack_plans (
        plan_id    TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        seed       TEXT,
        plan       TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_cgaps_project ON competitor_gaps(project_id);
    CREATE INDEX IF NOT EXISTS idx_cgaps_priority ON competitor_gaps(priority);
    """)
    con.commit()
    return con


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — MASTER ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class CompetitorGapEngine:
    """
    Master engine. Ruflo calls via job queue.
    Job: cge_analyse <project_id> <competitor_urls[]>
    """

    def __init__(self):
        self._crawler  = CompetitorCrawler()
        self._analyser = GapAnalyser()
        self._planner  = AttackPlanGenerator()

    def analyse(self, project_id: str, competitor_urls: List[str],
                 seed: str, project_keywords: List[str] = None,
                 project_name: str = "") -> dict:
        """Full pipeline: crawl → gap → plan → store."""
        con = _db()

        # Save competitor domains
        for url in competitor_urls:
            domain = "{0.netloc}".format(urlparse(url))
            con.execute("INSERT OR IGNORE INTO competitor_domains (project_id,domain) VALUES (?,?)",
                         (project_id, domain))
        con.commit()

        # 1. Crawl
        all_pages = []
        for url in competitor_urls[:5]:   # max 5 competitors
            pages = self._crawler.crawl(url, max_pages=15)
            all_pages.extend(pages)

        if not all_pages:
            return {"error": "No competitor pages crawled", "gaps": []}

        log.info(f"[CompGap] Total pages crawled: {len(all_pages)}")

        # 2. Find gaps
        our_keywords = project_keywords or []
        gaps = self._analyser.find_gaps(all_pages, our_keywords, project_id, seed)

        # 3. Store gaps
        for gap in gaps:
            gid = f"gap_{hashlib.md5(f'{project_id}{gap.keyword}'.encode()).hexdigest()[:10]}"
            con.execute("""
                INSERT OR REPLACE INTO competitor_gaps
                (gap_id,project_id,keyword,gap_type,opportunity,priority,competitors)
                VALUES (?,?,?,?,?,?,?)
            """, (gid, project_id, gap.keyword, gap.gap_type,
                   gap.opportunity_score, gap.priority,
                   json.dumps(gap.competitor_urls)))
        con.commit()

        # 4. Generate attack plan
        plan = self._planner.generate(gaps, seed, project_id, project_name)

        # 5. Store plan
        plan_id = f"plan_{project_id}_{int(time.time())}"
        con.execute("INSERT INTO competitor_attack_plans (plan_id,project_id,seed,plan) VALUES (?,?,?,?)",
                     (plan_id, project_id, seed, json.dumps(plan)))
        con.commit()

        return plan

    def get_gaps(self, project_id: str, priority: str = None) -> List[dict]:
        con = _db()
        q   = "SELECT * FROM competitor_gaps WHERE project_id=?"
        p   = [project_id]
        if priority: q += " AND priority=?"; p.append(priority)
        q += " ORDER BY opportunity DESC"
        return [dict(r) for r in con.execute(q, p).fetchall()]

    def get_attack_plans(self, project_id: str) -> List[dict]:
        con = _db()
        rows = con.execute("SELECT * FROM competitor_attack_plans WHERE project_id=? ORDER BY created_at DESC LIMIT 5",
                            (project_id,)).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks
    from pydantic import BaseModel as PM
    from typing import Optional as Opt

    app = FastAPI(title="AnnaSEO Competitor Gap Engine")
    cge = CompetitorGapEngine()

    class AnalyseBody(PM):
        project_id:        str
        competitor_urls:   List[str]
        seed:              str
        project_keywords:  List[str] = []
        project_name:      str = ""

    @app.post("/api/cge/analyse", tags=["Competitor Gap"])
    def analyse(body: AnalyseBody, bg: BackgroundTasks):
        bg.add_task(cge.analyse, body.project_id, body.competitor_urls,
                     body.seed, body.project_keywords, body.project_name)
        return {"status": "started", "message": "Analysis started. Check /api/cge/gaps for results."}

    @app.post("/api/cge/analyse/sync", tags=["Competitor Gap"])
    def analyse_sync(body: AnalyseBody):
        """Synchronous version — blocks until complete."""
        return cge.analyse(body.project_id, body.competitor_urls,
                            body.seed, body.project_keywords, body.project_name)

    @app.get("/api/cge/gaps/{project_id}", tags=["Competitor Gap"])
    def get_gaps(project_id: str, priority: Opt[str] = None):
        return cge.get_gaps(project_id, priority)

    @app.get("/api/cge/plans/{project_id}", tags=["Competitor Gap"])
    def get_plans(project_id: str):
        return cge.get_attack_plans(project_id)

    @app.get("/api/cge/competitors/{project_id}", tags=["Competitor Gap"])
    def list_competitors(project_id: str):
        return [dict(r) for r in _db().execute(
            "SELECT * FROM competitor_domains WHERE project_id=?", (project_id,)
        ).fetchall()]

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("""
AnnaSEO Competitor Gap Engine
Usage:
  python annaseo_competitor_gap.py analyse <project_id> <seed> <url1> [url2] [url3]
  python annaseo_competitor_gap.py gaps <project_id>
  python annaseo_competitor_gap.py plan <project_id>
  python annaseo_competitor_gap.py demo
"""); exit(0)

    cmd = sys.argv[1]
    cge = CompetitorGapEngine()

    if cmd == "demo":
        print("\n  COMPETITOR GAP ENGINE DEMO")
        print("  " + "─"*50)
        result = cge.analyse(
            project_id="proj_demo",
            competitor_urls=["https://www.spicejungle.com",
                             "https://www.thespicehouse.com"],
            seed="cinnamon",
            project_keywords=["cinnamon benefits","buy cinnamon","ceylon cinnamon"],
            project_name="Demo Spice Store"
        )
        print(f"\n  Total gaps found: {result.get('total_gaps',0)}")
        print(f"  Quick wins: {result.get('quick_wins',[])}")
        print(f"\n  Attack plan summary: {result.get('claude_summary','')}")
        print(f"\n  Top 5 gaps:")
        for g in result.get("all_gaps",[])[:5]:
            print(f"    [{g['priority']:8}] {g['keyword']:<30} opp={g['opportunity']:.0f}")

    elif cmd == "analyse":
        if len(sys.argv) < 5: print("Usage: analyse <project_id> <seed> <url1> [url2]"); exit(1)
        pid, seed = sys.argv[2], sys.argv[3]
        urls = sys.argv[4:]
        print(json.dumps(cge.analyse(pid, urls, seed), indent=2))

    elif cmd == "gaps":
        for g in cge.get_gaps(sys.argv[2] if len(sys.argv)>2 else "proj_demo"):
            print(f"  [{g['priority']:8}] {g['keyword']:<30} opp={g['opportunity']:.0f}")

    elif cmd == "plan":
        plans = cge.get_attack_plans(sys.argv[2] if len(sys.argv)>2 else "proj_demo")
        if plans:
            p = json.loads(plans[0]["plan"])
            print(f"  Summary: {p.get('claude_summary','')}")
            print(f"  Quick wins: {p.get('quick_wins',[])}")

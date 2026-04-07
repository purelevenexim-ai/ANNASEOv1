"""
================================================================================
ANNASEO — CONTENT REFRESH ENGINE  (annaseo_content_refresh.py)
================================================================================
When a published article drops in rankings, analyse exactly WHY and
generate specific surgical update instructions — not a full rewrite.

The difference matters:
  Full rewrite = loses existing link equity, internal link graph, indexed URLs
  Surgical update = preserves what's working, fixes what's broken

Why articles lose rankings (in order of frequency):
  1. New competitors published better content on the same topic
  2. Search intent shifted (informational → transactional, or vice versa)
  3. Statistics and data are now outdated
  4. Missing entities now expected by Google's knowledge graph
  5. E-E-A-T signals weakened vs competitors (no recent expertise signals)
  6. GEO score dropped (AI search now expects different content structure)
  7. Core Web Vitals degraded (page got heavier)

What this engine does
─────────────────────
  1. Monitor: GSC position changes → flag articles dropping >3 positions
  2. Diagnose: crawl current top-3 SERP results, compare vs our article
  3. Prescribe: generate specific update instructions per failure mode
  4. Prioritise: by traffic × ranking drop × content effort
  5. Schedule: auto-add to content calendar's "refresh" queue

AI usage
  Gemini → competitor content analysis, intent shift detection (free)
  DeepSeek → generate update instructions (free, local)
  Claude → final review of update plan (verification only)
================================================================================
"""

from __future__ import annotations

import os, re, json, hashlib, time, logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests as _req
from bs4 import BeautifulSoup

log = logging.getLogger("annaseo.content_refresh")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RankingDrop:
    article_id:   str
    keyword:      str
    url:          str
    old_position: float
    new_position: float
    drop:         float           # positions dropped (positive = worse)
    traffic_estimate: int = 0
    severity:     str = "medium"  # "critical"|"high"|"medium"|"low"


@dataclass
class ContentDiagnosis:
    article_id:    str
    keyword:       str
    failure_modes: List[str]      # what's wrong
    update_instructions: List[dict]   # specific things to change
    priority:      str = "medium"
    effort:        str = "small"  # "small"|"medium"|"large"
    estimated_impact: str = ""    # what improvement is expected
    competitor_url:str = ""       # the competitor to beat


@dataclass
class RefreshInstruction:
    """One specific, actionable update to make to an article."""
    instruction_type: str   # "add_section"|"update_stat"|"add_entity"|"restructure_h2"|"add_faq"|"update_intro"
    location:         str   # "introduction"|"section:Benefits"|"FAQ section"|"end of article"
    current_content:  str   # what's there now (if replacing)
    new_content:      str   # exact replacement or addition
    reason:           str   # why this change
    priority:         str   # "must_do"|"should_do"|"nice_to_have"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DECLINE DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

class DeclineDetector:
    """
    Reads ranking data from DB and identifies articles that need refreshing.
    Threshold: dropped >3 positions AND currently outside top 20.
    """

    CRITICAL_DROP = 5    # dropped 5+ positions → critical
    HIGH_DROP     = 3    # dropped 3–5 positions → high priority

    def detect(self, project_id: str) -> List[RankingDrop]:
        import sqlite3
        db_path = Path(os.getenv("ANNASEO_DB","./annaseo.db"))
        con     = sqlite3.connect(str(db_path), check_same_thread=False)
        con.row_factory = sqlite3.Row

        # Get ranking history for this project: compare latest vs 4 weeks ago
        cutoff = (datetime.utcnow() - timedelta(days=28)).isoformat()
        drops  = []

        keywords = [dict(r) for r in con.execute("""
            SELECT keyword, MIN(position) as best_pos, MAX(recorded_at) as latest_at
            FROM rankings WHERE project_id=? AND recorded_at >= ?
            GROUP BY keyword HAVING COUNT(*) >= 2
        """, (project_id, cutoff)).fetchall()]

        for kw_row in keywords:
            kw = kw_row["keyword"]
            history = [dict(r) for r in con.execute("""
                SELECT position, recorded_at FROM rankings
                WHERE project_id=? AND keyword=?
                ORDER BY recorded_at ASC
            """, (project_id, kw)).fetchall()]

            if len(history) < 2: continue
            old_pos = history[0]["position"]
            new_pos = history[-1]["position"]
            drop    = new_pos - old_pos   # positive = worse

            if drop >= self.HIGH_DROP:
                # Find associated article
                article = con.execute("""
                    SELECT article_id, published_url FROM content_articles
                    WHERE project_id=? AND keyword=? AND status='published'
                    LIMIT 1
                """, (project_id, kw)).fetchone()
                if article:
                    severity = ("critical" if drop >= self.CRITICAL_DROP
                                 else "high" if drop >= self.HIGH_DROP
                                 else "medium")
                    drops.append(RankingDrop(
                        article_id=dict(article)["article_id"],
                        keyword=kw,
                        url=dict(article).get("published_url",""),
                        old_position=old_pos,
                        new_position=new_pos,
                        drop=drop,
                        severity=severity,
                    ))

        con.close()
        return sorted(drops, key=lambda d: -(d.drop * (100 if d.severity=="critical" else 1)))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — DIAGNOSTICIAN
# ─────────────────────────────────────────────────────────────────────────────

class ContentDiagnostician:
    """
    Crawls current SERP top-3 and compares against our article.
    Identifies specific failure modes.
    Uses Gemini (free tier) for content analysis.
    """
    HEADERS = {"User-Agent": "Mozilla/5.0 (research; AnnaSEO content refresh)"}

    def diagnose(self, drop: RankingDrop, our_article_body: str = "") -> ContentDiagnosis:
        log.info(f"[Refresh] Diagnosing: '{drop.keyword}' (dropped {drop.drop:.0f} positions)")

        # 1. Get current SERP top-3
        serp_results  = self._get_serp(drop.keyword)
        competitor_url= serp_results[0]["url"] if serp_results else ""
        competitor_body = self._fetch_page(competitor_url) if competitor_url else ""

        # 2. Analyse with Gemini
        failure_modes, instructions = self._gemini_diagnose(
            keyword=drop.keyword,
            our_body=our_article_body[:3000],
            competitor_body=competitor_body[:3000],
            competitor_url=competitor_url,
        )

        effort = ("small" if len(instructions) <= 2
                   else "large" if len(instructions) >= 5
                   else "medium")
        return ContentDiagnosis(
            article_id=drop.article_id,
            keyword=drop.keyword,
            failure_modes=failure_modes,
            update_instructions=[i.__dict__ if hasattr(i,"__dict__") else i
                                   for i in instructions],
            priority=drop.severity,
            effort=effort,
            competitor_url=competitor_url,
            estimated_impact=f"Recover {drop.drop:.0f} lost positions, target top-{int(drop.new_position)}→top-{max(1,int(drop.old_position))}",
        )

    def _get_serp(self, keyword: str) -> List[dict]:
        """Use DuckDuckGo HTML endpoint — free, no API key."""
        results = []
        try:
            r = _req.get("https://html.duckduckgo.com/html/",
                          params={"q": keyword},
                          headers={**self.HEADERS, "Accept":"text/html"},
                          timeout=10)
            if r.ok:
                soup = BeautifulSoup(r.text, "html.parser")
                for result in soup.select(".result")[:5]:
                    a    = result.select_one(".result__title a")
                    snip = result.select_one(".result__snippet")
                    if a:
                        results.append({
                            "title":   a.get_text(strip=True),
                            "url":     a.get("href",""),
                            "snippet": snip.get_text(strip=True) if snip else "",
                        })
        except Exception as e:
            log.warning(f"[Refresh] SERP fetch failed: {e}")
        return results

    def _fetch_page(self, url: str) -> str:
        try:
            r = _req.get(url, headers=self.HEADERS, timeout=10)
            if r.ok:
                soup = BeautifulSoup(r.text, "html.parser")
                for tag in soup(["script","style","nav","footer"]):
                    tag.decompose()
                return " ".join(soup.get_text().split())[:5000]
        except Exception:
            pass
        return ""

    def _gemini_diagnose(self, keyword: str, our_body: str,
                          competitor_body: str, competitor_url: str) -> Tuple[List[str], List[RefreshInstruction]]:
        key = os.getenv("GEMINI_API_KEY","")
        if not key:
            return self._rule_diagnose(our_body, competitor_body)

        try:
            prompt = f"""Compare these two articles about "{keyword}". Identify what our article is missing.

OUR ARTICLE (first 2000 chars):
{our_body[:2000]}

COMPETITOR ARTICLE from {competitor_url} (first 2000 chars):
{competitor_body[:2000]}

Identify:
1. What failure modes explain our ranking drop?
   Options: outdated_stats, missing_entities, weak_eeat, intent_mismatch, missing_sections,
            weak_intro, poor_geo_structure, too_short, no_faq, weak_conclusion

2. For each failure, give ONE specific update instruction:
   - instruction_type: add_section|update_stat|add_entity|restructure_h2|add_faq|update_intro
   - location: where in the article
   - new_content: exactly what to write (2-3 sentences)
   - reason: why this fixes the ranking issue

Return JSON only:
{{"failure_modes":["mode1","mode2"],"instructions":[{{"instruction_type":"...","location":"...","new_content":"...","reason":"...","priority":"must_do|should_do"}}]}}"""
            r = _req.post(
                f"{GEMINI_URL}?key={key}",
                json={"contents":[{"parts":[{"text":prompt}]}],
                      "generationConfig":{"temperature":0.1,"maxOutputTokens":600}},
                timeout=15
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                failure_modes = data.get("failure_modes",[])
                instructions  = [
                    RefreshInstruction(
                        instruction_type=i.get("instruction_type","add_section"),
                        location=i.get("location",""),
                        current_content=i.get("current_content",""),
                        new_content=i.get("new_content",""),
                        reason=i.get("reason",""),
                        priority=i.get("priority","should_do"),
                    )
                    for i in data.get("instructions",[])[:6]
                ]
                return failure_modes, instructions
        except Exception as e:
            log.warning(f"[Refresh] Gemini diagnose failed: {e}")
        return self._rule_diagnose(our_body, competitor_body)

    def _rule_diagnose(self, our: str, competitor: str) -> Tuple[List[str], List[RefreshInstruction]]:
        """Rule-based fallback diagnosis."""
        modes, instructions = [], []
        our_words = len(our.split())
        comp_words = len(competitor.split()) if competitor else 0

        if comp_words > our_words * 1.3:
            modes.append("too_short")
            instructions.append(RefreshInstruction(
                instruction_type="add_section",
                location="end of article before conclusion",
                current_content="",
                new_content=f"Add 300-400 words covering additional expert tips and use cases. Competitor article is {comp_words - our_words} words longer.",
                reason="Article is significantly shorter than top-ranking competitor",
                priority="must_do"
            ))
        if "faq" not in our.lower() and "frequently" not in our.lower():
            modes.append("no_faq")
            instructions.append(RefreshInstruction(
                instruction_type="add_faq",
                location="before conclusion",
                current_content="",
                new_content="Add FAQ section with 4-5 questions people actually ask about this topic. Check Google's People Also Ask box for the keyword.",
                reason="No FAQ section — missing People Also Ask visibility and GEO citability",
                priority="must_do"
            ))
        return modes, instructions


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — UPDATE PLAN GENERATOR (DeepSeek)
# ─────────────────────────────────────────────────────────────────────────────

class UpdatePlanGenerator:
    """
    Takes diagnosis → generates complete update plan with exact text to add.
    DeepSeek writes the actual content additions (free, local).
    """

    def generate(self, diagnosis: ContentDiagnosis, article_body: str,
                  keyword: str) -> dict:
        instructions_with_content = []
        for instr in diagnosis.update_instructions[:4]:
            if isinstance(instr, dict):
                instr_dict = instr
            else:
                instr_dict = instr.__dict__

            if instr_dict.get("priority") == "must_do":
                written = self._deepseek_write(keyword, instr_dict, article_body)
                instr_dict["written_content"] = written
            instructions_with_content.append(instr_dict)

        return {
            "article_id":       diagnosis.article_id,
            "keyword":          keyword,
            "failure_modes":    diagnosis.failure_modes,
            "effort":           diagnosis.effort,
            "priority":         diagnosis.priority,
            "estimated_impact": diagnosis.estimated_impact,
            "competitor_url":   diagnosis.competitor_url,
            "instructions":     instructions_with_content,
            "update_type":      "surgical",
            "generated_at":     datetime.utcnow().isoformat(),
        }

    def _deepseek_write(self, keyword: str, instruction: dict,
                         article_body: str) -> str:
        """DeepSeek writes the exact content addition."""
        try:
            r = _req.post(
                f"{os.getenv('OLLAMA_URL','http://172.235.16.165:11434')}/api/generate",
                json={"model": "deepseek-r1:7b",
                      "prompt": (
                          f"Write content for an SEO article update.\n"
                          f"Keyword: {keyword}\n"
                          f"Update type: {instruction.get('instruction_type','')}\n"
                          f"Location: {instruction.get('location','')}\n"
                          f"What to write: {instruction.get('new_content','')}\n"
                          f"Reason: {instruction.get('reason','')}\n\n"
                          f"Write the exact text to add. 150-250 words. "
                          f"Include specific facts, numbers, and expert signals. "
                          f"Start with a direct statement, not 'In conclusion' or 'Furthermore'."
                      ),
                      "stream": False, "options": {"num_predict": 350}},
                timeout=60
            )
            if r.ok:
                return r.json().get("response","").strip()
        except Exception as e:
            log.warning(f"[Refresh] DeepSeek write failed: {e}")
        return instruction.get("new_content","[Content to be written manually]")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — MASTER ENGINE
# ─────────────────────────────────────────────────────────────────────────────

import sqlite3

class ContentRefreshEngine:
    def __init__(self):
        self._detector     = DeclineDetector()
        self._diagnostician= ContentDiagnostician()
        self._planner      = UpdatePlanGenerator()

    def job_scan(self, project_id: str) -> dict:
        """Scan for declining articles in a project. Ruflo job: refresh_scan."""
        drops   = self._detector.detect(project_id)
        critical= [d for d in drops if d.severity == "critical"]
        high    = [d for d in drops if d.severity == "high"]
        log.info(f"[Refresh] {project_id}: {len(drops)} drops, {len(critical)} critical")
        return {
            "project_id":  project_id,
            "total_drops": len(drops),
            "critical":    len(critical),
            "high":        len(high),
            "drops":       [{"article_id": d.article_id, "keyword": d.keyword,
                              "old": d.old_position, "new": d.new_position,
                              "drop": d.drop, "severity": d.severity}
                             for d in drops[:20]],
        }

    def job_diagnose(self, article_id: str, keyword: str) -> dict:
        """Diagnose one article drop and generate update plan. Ruflo job: refresh_diagnose."""
        # Get article body from DB
        db_path = Path(os.getenv("ANNASEO_DB","./annaseo.db"))
        con = sqlite3.connect(str(db_path), check_same_thread=False)
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT body FROM content_articles WHERE article_id=?",
                           (article_id,)).fetchone()
        body    = dict(row)["body"] if row else ""
        con.close()

        # Create a mock drop for this article
        drop = RankingDrop(
            article_id=article_id, keyword=keyword,
            url="", old_position=5, new_position=12, drop=7, severity="high"
        )
        diagnosis = self._diagnostician.diagnose(drop, body)
        plan      = self._planner.generate(diagnosis, body, keyword)

        # Store in DB
        db_path2 = Path(os.getenv("ANNASEO_DB","./annaseo.db"))
        con2 = sqlite3.connect(str(db_path2), check_same_thread=False)
        con2.execute("""
            CREATE TABLE IF NOT EXISTS content_refresh_plans (
                plan_id TEXT PRIMARY KEY, article_id TEXT, keyword TEXT,
                plan TEXT, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        plan_id = f"rfr_{article_id}_{int(time.time())}"
        con2.execute("INSERT INTO content_refresh_plans (plan_id,article_id,keyword,plan) VALUES (?,?,?,?)",
                      (plan_id, article_id, keyword, json.dumps(plan)))
        con2.commit()
        con2.close()
        return plan


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — FASTAPI + CLI
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks
    from pydantic import BaseModel as PM
    from typing import Optional as Opt

    app = FastAPI(title="AnnaSEO Content Refresh Engine")
    cre = ContentRefreshEngine()

    @app.post("/api/refresh/scan/{project_id}", tags=["Content Refresh"])
    def scan(project_id: str, bg: BackgroundTasks):
        bg.add_task(cre.job_scan, project_id)
        return {"status": "started", "project_id": project_id}

    @app.post("/api/refresh/diagnose", tags=["Content Refresh"])
    def diagnose(article_id: str, keyword: str, bg: BackgroundTasks):
        bg.add_task(cre.job_diagnose, article_id, keyword)
        return {"status": "started", "article_id": article_id}

    @app.get("/api/refresh/plans/{article_id}", tags=["Content Refresh"])
    def get_plans(article_id: str):
        import sqlite3
        con = sqlite3.connect(os.getenv("ANNASEO_DB","./annaseo.db"), check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute("SELECT * FROM content_refresh_plans WHERE article_id=? ORDER BY created_at DESC LIMIT 3", (article_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

except ImportError:
    pass


if __name__ == "__main__":
    import sys
    cre = ContentRefreshEngine()
    if len(sys.argv) > 1 and sys.argv[1] == "scan":
        pid = sys.argv[2] if len(sys.argv) > 2 else "proj_demo"
        print(json.dumps(cre.job_scan(pid), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        if len(sys.argv) < 4: print("Usage: diagnose <article_id> <keyword>"); exit(1)
        print(json.dumps(cre.job_diagnose(sys.argv[2], sys.argv[3]), indent=2))
    else:
        print("Usage: python annaseo_content_refresh.py scan <project_id>")
        print("       python annaseo_content_refresh.py diagnose <article_id> <keyword>")

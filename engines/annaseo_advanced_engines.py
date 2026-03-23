"""
================================================================================
ANNASEO — ADVANCED ENGINES PACK  (annaseo_advanced_engines.py)
================================================================================
7 remaining engines completing the full system:

  1. EntityAuthorityBuilder     — Knowledge Graph entity strengthening
  2. ProgrammaticSEOBuilder     — template → N unique pages with quality gates
  3. BacklinkOpportunityEngine  — post-publish link building outreach
  4. LocalSEOEngine             — GeoLevel → LocalBusiness schema + NAP consistency
  5. AlgorithmUpdateAssessor    — Google update drops → auto-score all articles
  6. CompetitorMonitorDashboard — ongoing weekly competitor tracking
  7. WhiteLabelConfig           — agency branding for all reports and exports
================================================================================
"""

from __future__ import annotations

import os, re, json, hashlib, time, logging, sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import requests as _req
from bs4 import BeautifulSoup

log = logging.getLogger("annaseo.advanced")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
DB_PATH    = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS entity_profiles (
        entity_id   TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        name        TEXT NOT NULL,
        entity_type TEXT DEFAULT 'Organization',
        same_as     TEXT DEFAULT '[]',
        description TEXT DEFAULT '',
        wikipedia_url TEXT DEFAULT '',
        wikidata_id TEXT DEFAULT '',
        strength_score REAL DEFAULT 0,
        gaps        TEXT DEFAULT '[]',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS programmatic_templates (
        template_id TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        name        TEXT NOT NULL,
        template    TEXT NOT NULL,
        variables   TEXT DEFAULT '[]',
        pages_count INTEGER DEFAULT 0,
        status      TEXT DEFAULT 'draft',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS programmatic_pages (
        page_id     TEXT PRIMARY KEY,
        template_id TEXT NOT NULL,
        project_id  TEXT NOT NULL,
        title       TEXT,
        slug        TEXT,
        content     TEXT,
        variables   TEXT DEFAULT '{}',
        quality_score REAL DEFAULT 0,
        status      TEXT DEFAULT 'draft',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS backlink_opportunities (
        opp_id      TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        article_id  TEXT DEFAULT '',
        keyword     TEXT NOT NULL,
        target_url  TEXT NOT NULL,
        domain      TEXT DEFAULT '',
        opp_type    TEXT DEFAULT 'resource',
        da_estimate INTEGER DEFAULT 0,
        outreach_status TEXT DEFAULT 'pending',
        template    TEXT DEFAULT '',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS local_seo_profiles (
        profile_id  TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        business_name TEXT NOT NULL,
        address     TEXT DEFAULT '',
        city        TEXT DEFAULT '',
        state       TEXT DEFAULT '',
        country     TEXT DEFAULT 'India',
        phone       TEXT DEFAULT '',
        hours       TEXT DEFAULT '{}',
        lat         REAL DEFAULT 0,
        lng         REAL DEFAULT 0,
        geo_level   TEXT DEFAULT 'local',
        nap_issues  TEXT DEFAULT '[]',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS algorithm_updates (
        update_id   TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        date        TEXT NOT NULL,
        type        TEXT DEFAULT 'core',
        signals     TEXT DEFAULT '[]',
        detected_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS algorithm_impact_reports (
        report_id   TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        update_id   TEXT NOT NULL,
        articles_at_risk TEXT DEFAULT '[]',
        articles_safe TEXT DEFAULT '[]',
        recommended_fixes TEXT DEFAULT '[]',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS competitor_snapshots (
        snap_id     TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        domain      TEXT NOT NULL,
        new_pages   TEXT DEFAULT '[]',
        new_keywords TEXT DEFAULT '[]',
        lost_keywords TEXT DEFAULT '[]',
        week_of     TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS white_label_configs (
        config_id   TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        agency_name TEXT DEFAULT 'AnnaSEO',
        agency_logo TEXT DEFAULT '',
        primary_color TEXT DEFAULT '#7F77DD',
        custom_domain TEXT DEFAULT '',
        hide_powered_by INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_prog_pages_template ON programmatic_pages(template_id);
    CREATE INDEX IF NOT EXISTS idx_backlink_project ON backlink_opportunities(project_id);
    CREATE INDEX IF NOT EXISTS idx_algo_project ON algorithm_impact_reports(project_id);
    CREATE INDEX IF NOT EXISTS idx_comp_snap_project ON competitor_snapshots(project_id);
    """)
    con.commit()
    return con


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 1 — ENTITY AUTHORITY BUILDER
# ─────────────────────────────────────────────────────────────────────────────

class EntityAuthorityBuilder:
    """
    Strengthens Knowledge Graph entity associations for a brand.

    AI search engines (and Google) rely heavily on entity graphs.
    If your brand is not an entity in Wikidata/Wikipedia, AI search
    won't cite you as an authority. This engine:

    1. Identifies current entity associations (sameAs schema)
    2. Finds gaps vs competitor entity profiles
    3. Generates entity-strengthening content plan
    4. Creates the correct JSON-LD schema markup
    """

    ENTITY_PLATFORMS = [
        ("Wikipedia", "https://en.wikipedia.org/wiki/{name}"),
        ("Wikidata",  "https://www.wikidata.org/wiki/Special:Search?search={name}"),
        ("LinkedIn",  "https://www.linkedin.com/company/{name_slug}"),
        ("Crunchbase","https://www.crunchbase.com/organization/{name_slug}"),
        ("Google Business", "https://business.google.com"),
    ]

    def build_profile(self, project_id: str, business_name: str,
                       industry: str, description: str = "",
                       website_url: str = "") -> dict:
        """Build entity profile and identify gaps."""
        entity_id = f"ent_{hashlib.md5(f'{project_id}{business_name}'.encode()).hexdigest()[:10]}"

        # Check existing sameAs on the site
        same_as = self._find_same_as(website_url) if website_url else []
        # Find gaps
        gaps = self._find_gaps(business_name, industry, same_as)
        # Calculate strength score
        score = min(100, len(same_as) * 15 + (20 if same_as else 0))

        _db().execute("""
            INSERT OR REPLACE INTO entity_profiles
            (entity_id,project_id,name,entity_type,same_as,description,strength_score,gaps)
            VALUES (?,?,?,?,?,?,?,?)
        """, (entity_id, project_id, business_name,
               "Organization",
               json.dumps(same_as),
               description,
               score,
               json.dumps(gaps)))
        _db().commit()

        schema = self._generate_schema(business_name, description, website_url, same_as, industry)
        return {
            "entity_id":     entity_id,
            "business_name": business_name,
            "same_as_found": same_as,
            "strength_score":score,
            "gaps":          gaps,
            "schema_json":   schema,
            "action_plan":   self._action_plan(gaps, business_name),
        }

    def _find_same_as(self, website_url: str) -> List[str]:
        """Check if the site already has sameAs schema pointing to authority platforms."""
        try:
            r = _req.get(website_url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
            if not r.ok: return []
            soup   = BeautifulSoup(r.text, "html.parser")
            schemas= []
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        urls = data.get("sameAs", [])
                        if isinstance(urls, list): schemas.extend(urls)
                        elif isinstance(urls, str): schemas.append(urls)
                except Exception:
                    pass
            return schemas[:10]
        except Exception:
            return []

    def _find_gaps(self, name: str, industry: str, existing: List[str]) -> List[dict]:
        """Identify missing entity platforms."""
        gaps = []
        existing_lower = " ".join(existing).lower()
        platform_checks = [
            ("Wikipedia",  "wikipedia.org",  "high",   "Create or request a Wikipedia article about your brand"),
            ("Wikidata",   "wikidata.org",   "high",   "Add Wikidata entity with sameAs links"),
            ("LinkedIn",   "linkedin.com",   "medium", "Add LinkedIn company page to sameAs schema"),
            ("Crunchbase", "crunchbase.com", "medium", "Add Crunchbase profile to sameAs schema"),
            ("Google KB",  "google.com/maps","high",   "Verify Google Business Profile with structured data"),
        ]
        for platform, domain, priority, action in platform_checks:
            if domain not in existing_lower:
                gaps.append({"platform": platform, "priority": priority, "action": action})
        return gaps

    def _generate_schema(self, name: str, description: str, url: str,
                           same_as: List[str], industry: str) -> str:
        """Generate Organization JSON-LD with all sameAs links."""
        schema = {
            "@context": "https://schema.org",
            "@type":    "Organization",
            "name":     name,
            "url":      url,
            "description": description,
            "sameAs":   same_as,
        }
        if industry in ("food_spices", "agriculture"):
            schema["@type"] = ["Organization", "FoodEstablishment"]
        elif industry == "healthcare":
            schema["@type"] = ["Organization", "MedicalOrganization"]
        return json.dumps(schema, indent=2)

    def _action_plan(self, gaps: List[dict], name: str) -> List[str]:
        plan = []
        high = [g for g in gaps if g["priority"] == "high"]
        for g in high[:3]:
            plan.append(f"{g['platform']}: {g['action']}")
        plan.append(f"Create author bio pages for all content creators mentioning {name}")
        plan.append("Add sameAs schema to Organization JSON-LD on homepage")
        return plan


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 2 — PROGRAMMATIC SEO BUILDER
# ─────────────────────────────────────────────────────────────────────────────

PROG_SEO_GATES = {"warning": 100, "hard_stop": 500}

# Anti-thin-content rules per template
THIN_CONTENT_CHECKS = [
    ("min_words_per_page", 400,  "Each page must have at least 400 unique words"),
    ("unique_content_pct", 0.40, "At least 40% of content must be unique per page"),
    ("has_h1",             True, "Every page must have an H1 containing the primary variable"),
    ("has_meta_desc",      True, "Every page must have a unique meta description"),
]


class ProgrammaticSEOBuilder:
    """
    Build N unique pages from one template.
    Anti-thin-content gates at 100 and 500 pages.
    Each variable slot must produce genuinely different content.

    Use cases:
      - "Best {spice} in {city}" — location × product pages
      - "{spice} vs {spice2}" — comparison pages
      - "Buy {spice} online in {country}" — market pages
    """

    def create_template(self, project_id: str, name: str,
                          template_html: str, variables: List[dict]) -> str:
        """
        template_html: HTML with {variable} placeholders
        variables: [{name, values: [...], description}]
        Returns template_id.
        """
        tid   = f"tmpl_{project_id}_{hashlib.md5(name.encode()).hexdigest()[:8]}"
        # Count how many pages this template would produce
        count = 1
        for v in variables:
            count *= len(v.get("values", [1]))

        _db().execute("""
            INSERT OR REPLACE INTO programmatic_templates
            (template_id,project_id,name,template,variables,pages_count,status)
            VALUES (?,?,?,?,?,?,?)
        """, (tid, project_id, name, template_html[:50000],
               json.dumps(variables), count,
               "warning" if count >= PROG_SEO_GATES["warning"] else "active"))
        _db().commit()
        log.info(f"[ProgSEO] Template '{name}': {count} pages projected")
        return tid

    def generate_pages(self, template_id: str, max_pages: int = None) -> dict:
        """Generate pages from template with quality gates."""
        con  = _db()
        tmpl = con.execute("SELECT * FROM programmatic_templates WHERE template_id=?",
                            (template_id,)).fetchone()
        if not tmpl:
            return {"error": "Template not found"}
        tmpl = dict(tmpl)

        total = tmpl["pages_count"]
        # Gate checks
        if total >= PROG_SEO_GATES["hard_stop"]:
            return {"error": f"HARD STOP: {total} pages exceeds limit of {PROG_SEO_GATES['hard_stop']}. "
                              "Reduce variable combinations or segment into multiple projects."}
        if total >= PROG_SEO_GATES["warning"]:
            log.warning(f"[ProgSEO] WARNING: {total} pages — approaching thin content risk")

        variables = json.loads(tmpl["variables"])
        template  = tmpl["template"]
        project_id= tmpl["project_id"]

        # Generate all combinations
        combos = self._combinations(variables)
        limit  = min(max_pages or total, PROG_SEO_GATES["hard_stop"])
        pages_created, passed, failed = 0, 0, 0

        for combo in combos[:limit]:
            page_content = template
            for var_name, var_val in combo.items():
                page_content = page_content.replace("{" + var_name + "}", str(var_val))
            slug  = self._to_slug(combo)
            title = self._extract_title(page_content) or f"{list(combo.values())[0]} Guide"
            # Quality check
            score, issues = self._quality_check(page_content, title, combo)
            status = "published" if score >= 70 else "needs_review"
            if score < 50:
                failed += 1
                continue
            pid   = f"pg_{hashlib.md5(f'{template_id}{slug}'.encode()).hexdigest()[:12]}"
            con.execute("""
                INSERT OR IGNORE INTO programmatic_pages
                (page_id,template_id,project_id,title,slug,content,variables,quality_score,status)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (pid, template_id, project_id, title, slug,
                   page_content[:20000], json.dumps(combo), score, status))
            pages_created += 1
            if status == "published": passed += 1
            if pages_created % 50 == 0:
                con.commit()

        con.commit()
        return {
            "template_id":   template_id,
            "pages_created": pages_created,
            "passed_quality":passed,
            "failed_quality":failed,
            "total_projected":total,
            "gate_status":   ("hard_stop" if total >= 500 else
                               "warning"   if total >= 100 else "ok"),
        }

    def _combinations(self, variables: List[dict]) -> List[dict]:
        """Generate all variable combinations."""
        if not variables: return [{}]
        first, rest = variables[0], variables[1:]
        result      = []
        for val in first.get("values", []):
            for sub in self._combinations(rest):
                combo = {first["name"]: val}
                combo.update(sub)
                result.append(combo)
        return result

    def _to_slug(self, combo: dict) -> str:
        slug = "-".join(str(v).lower().replace(" ","-") for v in combo.values())
        return re.sub(r"[^a-z0-9-]", "", slug)[:80]

    def _extract_title(self, content: str) -> str:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.I | re.DOTALL)
        return BeautifulSoup(m.group(1),"html.parser").get_text() if m else ""

    def _quality_check(self, content: str, title: str, combo: dict) -> Tuple[float, List[str]]:
        """Check for thin content."""
        text   = BeautifulSoup(content,"html.parser").get_text()
        words  = len(text.split())
        score  = 100.0
        issues = []
        if words < 400:
            score -= 40; issues.append(f"Only {words} words (min 400)")
        if not title:
            score -= 20; issues.append("Missing H1 title")
        # Check uniqueness via variable density
        var_words = " ".join(str(v) for v in combo.values()).split()
        unique_ratio = len(set(var_words)) / max(len(var_words), 1)
        if unique_ratio < 0.3:
            score -= 15; issues.append("Low content uniqueness")
        return max(0, score), issues


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 3 — BACKLINK OPPORTUNITY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class BacklinkOpportunityEngine:
    """
    After publishing an article, find the top 20 link building opportunities:
    - Sites linking to competitor articles on the same topic (skyscraper)
    - Resource pages in the niche that list external links
    - Journalists/bloggers who've written about the topic
    - Broken links on authority sites (replace with your content)

    All free: DuckDuckGo search + page scraping + Gemini outreach templates.
    """
    HEADERS = {"User-Agent":"Mozilla/5.0 (link research; AnnaSEO)"}

    def find(self, keyword: str, article_url: str,
              project_id: str, article_id: str = "") -> dict:
        """Find backlink opportunities for a published article."""
        log.info(f"[Backlink] Finding opportunities for: {keyword}")
        opps = []

        # 1. Skyscraper: sites linking to competitor articles
        opps += self._find_skyscraper(keyword, article_url)

        # 2. Resource pages
        opps += self._find_resource_pages(keyword)

        # 3. Guest post opportunities
        opps += self._find_guest_posts(keyword)

        # Store opportunities
        con = _db()
        for opp in opps:
            oid = f"opp_{hashlib.md5(f'{project_id}{opp["url"]}'.encode()).hexdigest()[:10]}"
            domain = "{0.netloc}".format(__import__("urllib.parse",fromlist=["urlparse"]).urlparse(opp["url"]))
            template = self._outreach_template(opp, keyword, article_url)
            con.execute("""
                INSERT OR IGNORE INTO backlink_opportunities
                (opp_id,project_id,article_id,keyword,target_url,domain,opp_type,da_estimate,template)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (oid, project_id, article_id, keyword, opp["url"],
                   domain, opp["type"], opp.get("da_estimate",20), template))
        con.commit()

        return {
            "keyword":        keyword,
            "opportunities":  len(opps),
            "by_type":        {t: sum(1 for o in opps if o["type"]==t)
                               for t in set(o["type"] for o in opps)},
            "top_10":         opps[:10],
        }

    def _find_skyscraper(self, keyword: str, our_url: str) -> List[dict]:
        """Find competitor articles ranking for this keyword."""
        results = []
        try:
            r = _req.get("https://html.duckduckgo.com/html/",
                          params={"q": keyword},
                          headers=self.HEADERS, timeout=10)
            if r.ok:
                soup = BeautifulSoup(r.text,"html.parser")
                for res in soup.select(".result")[:8]:
                    link = res.select_one(".result__url")
                    snip = res.select_one(".result__snippet")
                    if link and our_url not in link.get_text():
                        results.append({
                            "url":         link.get_text(strip=True),
                            "type":        "skyscraper",
                            "da_estimate": 30,
                            "snippet":     snip.get_text(strip=True) if snip else "",
                        })
        except Exception as e:
            log.warning(f"[Backlink] Skyscraper search failed: {e}")
        return results[:5]

    def _find_resource_pages(self, keyword: str) -> List[dict]:
        """Find resource/link pages that list external resources."""
        results = []
        try:
            query = f"{keyword} useful resources links"
            r = _req.get("https://html.duckduckgo.com/html/",
                          params={"q": query},
                          headers=self.HEADERS, timeout=10)
            if r.ok:
                soup = BeautifulSoup(r.text,"html.parser")
                for res in soup.select(".result")[:5]:
                    link = res.select_one(".result__url")
                    if link:
                        results.append({
                            "url":  link.get_text(strip=True),
                            "type": "resource_page",
                            "da_estimate": 25,
                        })
        except Exception: pass
        return results[:3]

    def _find_guest_posts(self, keyword: str) -> List[dict]:
        """Find blogs that accept guest posts in this niche."""
        results = []
        try:
            query = f"{keyword} write for us OR guest post OR contribute"
            r = _req.get("https://html.duckduckgo.com/html/",
                          params={"q": query},
                          headers=self.HEADERS, timeout=10)
            if r.ok:
                soup = BeautifulSoup(r.text,"html.parser")
                for res in soup.select(".result")[:5]:
                    link = res.select_one(".result__url")
                    if link:
                        results.append({
                            "url":  link.get_text(strip=True),
                            "type": "guest_post",
                            "da_estimate": 20,
                        })
        except Exception: pass
        return results[:3]

    def _outreach_template(self, opp: dict, keyword: str, our_url: str) -> str:
        """Generate personalised outreach email template using Gemini."""
        key = os.getenv("GEMINI_API_KEY","")
        if not key:
            return (f"Subject: Relevant resource for your {keyword} content\n\n"
                    f"Hi,\n\nI came across your page about {keyword} and wanted to share "
                    f"a resource that your readers might find valuable:\n{our_url}\n\n"
                    f"It covers [specific angle]. Happy to discuss a potential link exchange.\n\nBest,")
        try:
            r = _req.post(f"{GEMINI_URL}?key={key}",
                json={"contents":[{"parts":[{"text":
                    f"Write a personalised link outreach email.\n"
                    f"Target site type: {opp.get('type','')}\n"
                    f"Topic: {keyword}\n"
                    f"Our URL to pitch: {our_url}\n\n"
                    f"Requirements:\n"
                    f"- 4-6 sentences max\n"
                    f"- Specific to their content type\n"
                    f"- Natural, not spammy\n"
                    f"- Subject line + body\n"
                    f"Return: Subject: ...\n\nBody text"}]}],
                    "generationConfig":{"temperature":0.3,"maxOutputTokens":200}},
                timeout=10)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            return f"Subject: Resource suggestion for {keyword}\n\nHi,\n\nYour {keyword} content is great. We have a related resource at {our_url} that your readers might enjoy.\n\nBest,"

    def get_opportunities(self, project_id: str, status: str = "pending") -> List[dict]:
        return [dict(r) for r in _db().execute(
            "SELECT * FROM backlink_opportunities WHERE project_id=? AND outreach_status=? ORDER BY da_estimate DESC",
            (project_id, status)
        ).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 4 — LOCAL SEO ENGINE
# ─────────────────────────────────────────────────────────────────────────────

# GeoLevel from strategy engine — all levels get LocalBusiness schema treatment
GEO_SCHEMA_TYPES = {
    "kerala":     ("LocalBusiness","Kerala, India"),
    "wayanad":    ("LocalBusiness","Wayanad, Kerala, India"),
    "malabar":    ("LocalBusiness","Malabar, Kerala, India"),
    "kochi":      ("LocalBusiness","Kochi, Kerala, India"),
    "kozhikode":  ("LocalBusiness","Kozhikode, Kerala, India"),
    "south_india":("Organization","South India"),
    "national":   ("Organization","India"),
    "global":     ("Organization","Global"),
}

# NAP consistency check platforms (free to check)
NAP_PLATFORMS = [
    ("Google Business",   "site:maps.google.com {business_name}"),
    ("Justdial",          "site:justdial.com {business_name}"),
    ("IndiaMART",         "site:indiamart.com {business_name}"),
    ("Sulekha",           "site:sulekha.com {business_name}"),
    ("TradeIndia",        "site:tradeindia.com {business_name}"),
]


class LocalSEOEngine:
    """
    For businesses with physical locations (Kerala spice farms, local shops).
    Generates LocalBusiness schema, checks NAP consistency across directories,
    creates location-specific keyword variations using GeoLevel enum.
    """
    HEADERS = {"User-Agent":"Mozilla/5.0 (local SEO research; AnnaSEO)"}

    def setup(self, project_id: str, business_name: str, address: str,
               city: str, phone: str, geo_level: str = "kerala",
               hours: dict = None) -> dict:
        """Setup local SEO profile and generate all assets."""
        profile_id = f"lseo_{hashlib.md5(f'{project_id}{business_name}'.encode()).hexdigest()[:10]}"
        _db().execute("""
            INSERT OR REPLACE INTO local_seo_profiles
            (profile_id,project_id,business_name,address,city,phone,hours,geo_level)
            VALUES (?,?,?,?,?,?,?,?)
        """, (profile_id, project_id, business_name, address, city,
               phone, json.dumps(hours or {}), geo_level))
        _db().commit()

        schema_type, region = GEO_SCHEMA_TYPES.get(geo_level, ("Organization","India"))
        schema  = self._generate_schema(business_name, address, city, phone,
                                         hours or {}, schema_type, geo_level)
        nap     = self._check_nap(business_name, city)
        kws     = self._local_keywords(business_name, city, geo_level)
        return {
            "profile_id":      profile_id,
            "schema_json":     schema,
            "nap_check":       nap,
            "local_keywords":  kws,
            "geo_pages_plan":  self._geo_pages(business_name, geo_level),
        }

    def _generate_schema(self, name: str, address: str, city: str,
                           phone: str, hours: dict, schema_type: str,
                           geo_level: str) -> str:
        """Generate LocalBusiness JSON-LD."""
        schema: dict = {
            "@context":     "https://schema.org",
            "@type":        schema_type,
            "name":         name,
            "address": {
                "@type":           "PostalAddress",
                "streetAddress":   address,
                "addressLocality": city,
                "addressCountry":  "IN",
            },
            "telephone": phone,
        }
        if hours:
            schema["openingHoursSpecification"] = [
                {"@type":"OpeningHoursSpecification",
                 "dayOfWeek": days,
                 "opens":  times.get("open","09:00"),
                 "closes": times.get("close","18:00")}
                for days, times in hours.items()
            ]
        if geo_level in ("kerala","wayanad","malabar","kochi","kozhikode"):
            schema["areaServed"] = {"@type":"State","name":"Kerala"}
        return json.dumps(schema, indent=2)

    def _check_nap(self, business_name: str, city: str) -> dict:
        """Check if business appears consistently in directories."""
        results = {"checked": [], "issues": []}
        for platform, query_tpl in NAP_PLATFORMS[:3]:
            query = query_tpl.format(business_name=business_name)
            try:
                r = _req.get("https://html.duckduckgo.com/html/",
                              params={"q": query},
                              headers=self.HEADERS, timeout=8)
                found = business_name.lower() in r.text.lower() if r.ok else False
                results["checked"].append({"platform":platform,"found":found})
                if not found:
                    results["issues"].append(f"Not found on {platform} — add listing")
            except Exception:
                pass
        return results

    def _local_keywords(self, business_name: str, city: str,
                          geo_level: str) -> List[str]:
        """Generate location-specific keyword variations."""
        base = business_name.lower().split()[0]  # first word of business name
        kws  = [
            f"{base} {city.lower()}",
            f"{base} near me",
            f"buy {base} online {city.lower()}",
            f"best {base} supplier {city.lower()}",
            f"{base} wholesale {city.lower()}",
            f"organic {base} {city.lower()}",
            f"{city.lower()} {base} exporter",
        ]
        if geo_level in ("kerala","wayanad","malabar"):
            kws += [f"{base} kerala", f"kerala organic {base}",
                    f"wayanad {base}", f"malabar {base}"]
        return kws

    def _geo_pages(self, business_name: str, geo_level: str) -> List[dict]:
        """Plan geo-targeted landing pages (within programmatic SEO gates)."""
        cities = {
            "kerala":     ["Kochi","Thiruvananthapuram","Kozhikode","Thrissur","Kottayam"],
            "south_india":["Chennai","Bangalore","Hyderabad","Kochi","Coimbatore"],
            "national":   ["Mumbai","Delhi","Bangalore","Chennai","Kolkata"],
        }.get(geo_level, ["Local Area"])
        return [{"city":c, "title":f"{business_name} in {c}", "slug":f"{c.lower()}-page"}
                for c in cities[:5]]   # max 5 geo pages to stay safe


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 5 — ALGORITHM UPDATE IMPACT ASSESSOR
# ─────────────────────────────────────────────────────────────────────────────

# Known algorithm update signals (what each update targets)
KNOWN_UPDATE_SIGNALS = {
    "helpful_content": ["ai_generated", "thin_content", "low_eeat", "no_first_person"],
    "core_web_vitals": ["slow_lcp", "high_inp", "layout_shift"],
    "spam_update":     ["keyword_stuffing", "auto_generated", "cloaking"],
    "product_reviews": ["no_unique_insights", "affiliate_heavy", "no_hands_on"],
    "link_spam":       ["unnatural_links", "paid_links"],
    "march_2024_core": ["ai_watermarks", "low_originality", "no_first_person", "low_eeat"],
}


class AlgorithmUpdateAssessor:
    """
    When a Google core update is detected (via self-dev intelligence crawler),
    automatically score all published articles for vulnerability.
    Prioritise the refresh queue accordingly.
    """

    def register_update(self, name: str, date: str,
                          update_type: str = "core",
                          signals: List[str] = None) -> str:
        """Register a detected algorithm update."""
        uid = f"upd_{hashlib.md5(f'{name}{date}'.encode()).hexdigest()[:10]}"
        _db().execute("""
            INSERT OR REPLACE INTO algorithm_updates
            (update_id,name,date,type,signals) VALUES (?,?,?,?,?)
        """, (uid, name, date, update_type,
               json.dumps(signals or KNOWN_UPDATE_SIGNALS.get(name.lower().replace(" ","_"),[]))))
        _db().commit()
        log.info(f"[AlgoUpdate] Registered: {name} on {date}")
        return uid

    def assess_project(self, project_id: str, update_id: str) -> dict:
        """Score all published articles for vulnerability to this update."""
        con = _db()
        upd = con.execute("SELECT * FROM algorithm_updates WHERE update_id=?",
                           (update_id,)).fetchone()
        if not upd:
            return {"error": "Update not found"}
        upd     = dict(upd)
        signals = json.loads(upd.get("signals","[]"))

        sql_con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        sql_con.row_factory = sqlite3.Row
        articles = [dict(r) for r in sql_con.execute(
            "SELECT * FROM content_articles WHERE project_id=? AND status='published'",
            (project_id,)
        ).fetchall()]
        sql_con.close()

        at_risk, safe, fixes = [], [], []
        for art in articles:
            score, issues = self._vulnerability_score(art, signals)
            if score >= 50:
                at_risk.append({"article_id":art["article_id"],
                                 "keyword":art.get("keyword",""),
                                 "risk_score":score,"issues":issues})
                fix = self._recommend_fix(issues, art, upd["name"])
                if fix: fixes.append(fix)
            else:
                safe.append(art["article_id"])

        report_id = f"rpt_{project_id}_{update_id}"
        con.execute("""
            INSERT OR REPLACE INTO algorithm_impact_reports
            (report_id,project_id,update_id,articles_at_risk,articles_safe,recommended_fixes)
            VALUES (?,?,?,?,?,?)
        """, (report_id, project_id, update_id,
               json.dumps(at_risk[:20]), json.dumps(safe[:20]),
               json.dumps(fixes[:10])))
        con.commit()
        return {
            "update_name":    upd["name"],
            "articles_total": len(articles),
            "at_risk":        len(at_risk),
            "safe":           len(safe),
            "top_risks":      sorted(at_risk, key=lambda x: -x["risk_score"])[:5],
            "quick_fixes":    fixes[:5],
        }

    def _vulnerability_score(self, article: dict, signals: List[str]) -> Tuple[float,List[str]]:
        """Score article vulnerability to a given update's signals."""
        body    = (article.get("body","") or "").lower()
        score   = 0.0
        issues  = []
        eeat    = article.get("eeat_score", 0) or 0
        geo     = article.get("geo_score", 0) or 0
        words   = len(body.split())

        for sig in signals:
            if sig == "ai_watermarks":
                patterns = ["furthermore","certainly","delve","it is worth noting","in conclusion"]
                hits = sum(1 for p in patterns if p in body)
                if hits >= 2:
                    score += 30; issues.append(f"AI watermark patterns ({hits} found)")
            elif sig == "low_eeat":
                if eeat < 70:
                    score += 25; issues.append(f"E-E-A-T score low ({eeat})")
            elif sig == "no_first_person":
                fp = sum(1 for p in ["i ","we ","our ","in our testing"] if p in body)
                if fp < 2:
                    score += 20; issues.append("No first-person experience signals")
            elif sig == "thin_content":
                if words < 800:
                    score += 30; issues.append(f"Thin content ({words} words)")
            elif sig == "low_originality":
                if geo < 70:
                    score += 15; issues.append(f"Low GEO/originality score ({geo})")
        return min(100, score), issues

    def _recommend_fix(self, issues: List[str], article: dict,
                        update_name: str) -> Optional[dict]:
        if not issues: return None
        fixes = {
            "AI watermark patterns":   "Run Pass 7 humanize — remove furthermore/certainly/delve",
            "E-E-A-T score low":       "Add first-person expertise signals + author bio",
            "No first-person":         "Add 3+ 'In our testing...' or 'We found...' statements",
            "Thin content":            "Expand to 1500+ words with specific examples",
            "Low GEO/originality":     "Add direct answers at H2 starts + statistics",
        }
        actions = []
        for issue in issues[:2]:
            for pattern, fix in fixes.items():
                if pattern.lower() in issue.lower():
                    actions.append(fix)
        if not actions: return None
        return {
            "article_id": article["article_id"],
            "keyword":    article.get("keyword",""),
            "update":     update_name,
            "actions":    actions,
            "urgency":    "high" if len(issues) >= 2 else "medium",
        }

    def detect_from_serp_volatility(self, project_id: str) -> Optional[str]:
        """
        Detect algorithm update from ranking volatility.
        If >30% of keywords moved ±5 positions in a week → likely update.
        Returns detected update_id or None.
        """
        con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        con.row_factory = sqlite3.Row
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        try:
            kws = [dict(r) for r in con.execute("""
                SELECT keyword FROM rankings WHERE project_id=? AND recorded_at >= ?
                GROUP BY keyword HAVING MAX(position)-MIN(position) >= 5
            """, (project_id, week_ago)).fetchall()]
            total = con.execute("SELECT COUNT(DISTINCT keyword) FROM rankings WHERE project_id=?",
                                 (project_id,)).fetchone()[0] or 1
        except Exception:
            kws, total = [], 1
        con.close()
        if len(kws) / total >= 0.30:
            uid = self.register_update(
                f"Detected Update {datetime.utcnow().strftime('%Y-%m')}",
                datetime.utcnow().strftime("%Y-%m-%d"),
                signals=["ai_watermarks","low_eeat","thin_content"]
            )
            return uid
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 6 — COMPETITOR MONITORING DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

class CompetitorMonitor:
    """
    Weekly: crawl competitor domains for new content and ranking changes.
    Surfaces opportunities to the content calendar automatically.
    Extends CompetitorGapEngine (one-time) → this is ongoing monitoring.
    """
    HEADERS = {"User-Agent":"Mozilla/5.0 (SEO monitor; AnnaSEO)"}

    def weekly_scan(self, project_id: str,
                     competitor_domains: List[str]) -> dict:
        """Run weekly competitor scan. Ruflo cron job: competitor_monitor_weekly."""
        new_pages_all, new_kws_all = [], []
        for domain in competitor_domains[:5]:
            snap = self._scan_domain(domain)
            prev = self._get_previous_snapshot(project_id, domain)
            new_pages = self._diff_pages(snap["pages"], prev.get("pages",[]) if prev else [])
            new_kws   = self._diff_keywords(snap["keywords"], prev.get("keywords",[]) if prev else [])
            # Store snapshot
            snap_id = f"snap_{project_id}_{hashlib.md5(domain.encode()).hexdigest()[:8]}_{datetime.utcnow().strftime('%Y%m%d')}"
            _db().execute("""
                INSERT OR REPLACE INTO competitor_snapshots
                (snap_id,project_id,domain,new_pages,new_keywords,week_of)
                VALUES (?,?,?,?,?,?)
            """, (snap_id, project_id, domain,
                   json.dumps(new_pages[:20]), json.dumps(new_kws[:20]),
                   datetime.utcnow().strftime("%Y-%m-%d")))
            _db().commit()
            new_pages_all.extend(new_pages)
            new_kws_all.extend(new_kws)

        return {
            "project_id":      project_id,
            "competitors":     len(competitor_domains),
            "new_pages":       len(new_pages_all),
            "new_keywords":    len(new_kws_all),
            "new_pages_detail":new_pages_all[:10],
            "new_kws_detail":  new_kws_all[:10],
            "calendar_suggestions": self._suggest_content(new_kws_all[:5]),
        }

    def _scan_domain(self, domain: str) -> dict:
        """Quick scan of domain sitemap to find pages and extract keywords."""
        pages, keywords = [], []
        try:
            # Try sitemap
            for path in ["/sitemap.xml","/sitemap_index.xml"]:
                url = domain.rstrip("/") + path
                if not url.startswith("http"): url = "https://" + url
                r = _req.get(url, headers=self.HEADERS, timeout=8)
                if r.ok and "xml" in r.headers.get("content-type",""):
                    soup = BeautifulSoup(r.text, "xml")
                    pages = [loc.get_text().strip() for loc in soup.find_all("loc")][:50]
                    # Extract keywords from URLs
                    for p in pages:
                        slug = p.rstrip("/").split("/")[-1]
                        kw   = slug.replace("-"," ").replace("_"," ").strip()
                        if len(kw.split()) >= 2: keywords.append(kw)
                    break
        except Exception: pass
        return {"domain":domain,"pages":pages,"keywords":keywords[:50]}

    def _get_previous_snapshot(self, project_id: str, domain: str) -> Optional[dict]:
        row = _db().execute("""
            SELECT new_pages, new_keywords FROM competitor_snapshots
            WHERE project_id=? AND domain=?
            ORDER BY week_of DESC LIMIT 1
        """, (project_id, domain)).fetchone()
        if row:
            return {"pages": json.loads(row["new_pages"]),
                    "keywords": json.loads(row["new_keywords"])}
        return None

    def _diff_pages(self, current: List[str], previous: List[str]) -> List[str]:
        prev_set = set(previous)
        return [p for p in current if p not in prev_set]

    def _diff_keywords(self, current: List[str], previous: List[str]) -> List[str]:
        prev_set = set(k.lower() for k in previous)
        return [k for k in current if k.lower() not in prev_set]

    def _suggest_content(self, new_keywords: List[str]) -> List[dict]:
        """Auto-suggest content calendar entries for competitor new keywords."""
        return [{"keyword":kw, "suggestion":f"Competitor just published content on '{kw}' — consider covering this topic",
                 "urgency":"medium"} for kw in new_keywords[:5]]

    def get_weekly_reports(self, project_id: str, limit: int = 8) -> List[dict]:
        return [dict(r) for r in _db().execute("""
            SELECT domain, new_pages, new_keywords, week_of FROM competitor_snapshots
            WHERE project_id=? ORDER BY week_of DESC LIMIT ?
        """, (project_id, limit)).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 7 — WHITE LABEL CONFIG
# ─────────────────────────────────────────────────────────────────────────────

class WhiteLabelConfig:
    """
    Agencies run AnnaSEO under their own brand.
    Custom logo, colour scheme, custom domain, hide "Powered by AnnaSEO".
    All reports and exports use agency branding.
    """

    def configure(self, project_id: str, agency_name: str,
                   agency_logo_url: str = "", primary_color: str = "#7F77DD",
                   custom_domain: str = "", hide_powered_by: bool = False) -> str:
        config_id = f"wl_{project_id}"
        _db().execute("""
            INSERT OR REPLACE INTO white_label_configs
            (config_id,project_id,agency_name,agency_logo,primary_color,custom_domain,hide_powered_by)
            VALUES (?,?,?,?,?,?,?)
        """, (config_id, project_id, agency_name, agency_logo_url,
               primary_color, custom_domain, 1 if hide_powered_by else 0))
        _db().commit()
        log.info(f"[WhiteLabel] Configured for {project_id}: {agency_name}")
        return config_id

    def get(self, project_id: str) -> dict:
        row = _db().execute("SELECT * FROM white_label_configs WHERE project_id=?",
                             (project_id,)).fetchone()
        if row: return dict(row)
        return {"agency_name":"AnnaSEO","primary_color":"#7F77DD",
                "hide_powered_by":False}

    def apply_to_html(self, html: str, project_id: str) -> str:
        """Apply white-label branding to any HTML report."""
        config = self.get(project_id)
        html   = html.replace("AnnaSEO", config["agency_name"])
        html   = html.replace("#7F77DD", config["primary_color"])
        if config.get("hide_powered_by"):
            html = re.sub(r"Powered by AnnaSEO.*?</[^>]+>","", html, flags=re.IGNORECASE)
        if config.get("agency_logo"):
            html = re.sub(
                r'<h1[^>]*>.*?</h1>',
                f'<img src="{config["agency_logo"]}" alt="{config["agency_name"]}" style="height:40px"/>',
                html, count=1, flags=re.DOTALL
            )
        return html


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTER — all 7 advanced engines
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks
    from pydantic import BaseModel as PM
    from typing import Optional as Opt, List as L

    app = FastAPI(title="AnnaSEO Advanced Engines",
                  description="Entity authority, programmatic SEO, backlinks, local SEO, algo updates, competitor monitor, white-label")

    entity    = EntityAuthorityBuilder()
    prog      = ProgrammaticSEOBuilder()
    backlink  = BacklinkOpportunityEngine()
    local_seo = LocalSEOEngine()
    algo      = AlgorithmUpdateAssessor()
    monitor   = CompetitorMonitor()
    wl        = WhiteLabelConfig()

    class EntityBody(PM):
        business_name: str
        industry:      str
        description:   str = ""
        website_url:   str = ""

    class ProgTemplateBody(PM):
        name:      str
        template:  str
        variables: L[dict]

    class BacklinkBody(PM):
        keyword:     str
        article_url: str
        article_id:  str = ""

    class LocalSEOBody(PM):
        business_name: str
        address:       str
        city:          str
        phone:         str
        geo_level:     str = "kerala"
        hours:         dict = {}

    class AlgoUpdateBody(PM):
        name:    str
        date:    str
        type:    str = "core"
        signals: L[str] = []

    class CompetitorMonitorBody(PM):
        competitor_domains: L[str]

    class WhiteLabelBody(PM):
        agency_name:     str
        agency_logo_url: str = ""
        primary_color:   str = "#7F77DD"
        custom_domain:   str = ""
        hide_powered_by: bool = False

    # Entity authority
    @app.post("/api/entity/{project_id}/build", tags=["Entity Authority"])
    def build_entity(project_id: str, body: EntityBody):
        return entity.build_profile(project_id, body.business_name, body.industry,
                                     body.description, body.website_url)

    @app.get("/api/entity/{project_id}", tags=["Entity Authority"])
    def get_entity(project_id: str):
        rows = [dict(r) for r in _db().execute(
            "SELECT * FROM entity_profiles WHERE project_id=?", (project_id,)
        ).fetchall()]
        return rows

    # Programmatic SEO
    @app.post("/api/prog-seo/{project_id}/template", tags=["Programmatic SEO"])
    def create_template(project_id: str, body: ProgTemplateBody):
        tid = prog.create_template(project_id, body.name, body.template, body.variables)
        return {"template_id": tid}

    @app.post("/api/prog-seo/generate/{template_id}", tags=["Programmatic SEO"])
    def generate_pages(template_id: str, max_pages: Opt[int] = None, bg: BackgroundTasks = None):
        if bg:
            bg.add_task(prog.generate_pages, template_id, max_pages)
            return {"status": "started"}
        return prog.generate_pages(template_id, max_pages)

    @app.get("/api/prog-seo/pages/{template_id}", tags=["Programmatic SEO"])
    def list_pages(template_id: str, status: Opt[str] = None):
        q = "SELECT * FROM programmatic_pages WHERE template_id=?"
        p = [template_id]
        if status: q += " AND status=?"; p.append(status)
        return [dict(r) for r in _db().execute(q + " LIMIT 100", p).fetchall()]

    # Backlinks
    @app.post("/api/backlinks/{project_id}", tags=["Backlinks"])
    async def find_backlinks(project_id: str, body: BacklinkBody, bg: BackgroundTasks):
        bg.add_task(backlink.find, body.keyword, body.article_url, project_id, body.article_id)
        return {"status": "started", "keyword": body.keyword}

    @app.get("/api/backlinks/{project_id}", tags=["Backlinks"])
    def list_backlinks(project_id: str, status: str = "pending"):
        return backlink.get_opportunities(project_id, status)

    @app.put("/api/backlinks/{opp_id}/status", tags=["Backlinks"])
    def update_status(opp_id: str, status: str):
        _db().execute("UPDATE backlink_opportunities SET outreach_status=? WHERE opp_id=?",
                       (status, opp_id))
        _db().commit()
        return {"updated": opp_id}

    # Local SEO
    @app.post("/api/local-seo/{project_id}/setup", tags=["Local SEO"])
    def setup_local(project_id: str, body: LocalSEOBody):
        return local_seo.setup(project_id, body.business_name, body.address,
                                body.city, body.phone, body.geo_level, body.hours)

    @app.get("/api/local-seo/{project_id}", tags=["Local SEO"])
    def get_local(project_id: str):
        row = _db().execute("SELECT * FROM local_seo_profiles WHERE project_id=?",
                             (project_id,)).fetchone()
        return dict(row) if row else {}

    # Algorithm updates
    @app.post("/api/algo/updates", tags=["Algorithm Updates"])
    def register_update(body: AlgoUpdateBody):
        uid = algo.register_update(body.name, body.date, body.type, body.signals)
        return {"update_id": uid}

    @app.post("/api/algo/{project_id}/assess/{update_id}", tags=["Algorithm Updates"])
    async def assess(project_id: str, update_id: str, bg: BackgroundTasks):
        bg.add_task(algo.assess_project, project_id, update_id)
        return {"status": "started"}

    @app.post("/api/algo/{project_id}/detect", tags=["Algorithm Updates"])
    def detect_update(project_id: str):
        uid = algo.detect_from_serp_volatility(project_id)
        if uid: return {"detected": True, "update_id": uid}
        return {"detected": False, "message": "No significant volatility detected"}

    @app.get("/api/algo/updates", tags=["Algorithm Updates"])
    def list_updates():
        return [dict(r) for r in _db().execute(
            "SELECT * FROM algorithm_updates ORDER BY date DESC LIMIT 20"
        ).fetchall()]

    # Competitor monitor
    @app.post("/api/monitor/{project_id}/scan", tags=["Competitor Monitor"])
    async def weekly_scan(project_id: str, body: CompetitorMonitorBody, bg: BackgroundTasks):
        bg.add_task(monitor.weekly_scan, project_id, body.competitor_domains)
        return {"status": "started", "competitors": len(body.competitor_domains)}

    @app.get("/api/monitor/{project_id}/reports", tags=["Competitor Monitor"])
    def monitor_reports(project_id: str):
        return monitor.get_weekly_reports(project_id)

    # White label
    @app.post("/api/white-label/{project_id}", tags=["White Label"])
    def configure_wl(project_id: str, body: WhiteLabelBody):
        cid = wl.configure(project_id, body.agency_name, body.agency_logo_url,
                             body.primary_color, body.custom_domain, body.hide_powered_by)
        return {"config_id": cid}

    @app.get("/api/white-label/{project_id}", tags=["White Label"])
    def get_wl(project_id: str):
        return wl.get(project_id)

except ImportError:
    pass


if __name__ == "__main__":
    import sys
    print("\nAnnaSEO Advanced Engines Pack")
    print("Engines: EntityAuthorityBuilder, ProgrammaticSEOBuilder, BacklinkOpportunityEngine")
    print("         LocalSEOEngine, AlgorithmUpdateAssessor, CompetitorMonitor, WhiteLabelConfig")
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        print("\n--- Local SEO Demo ---")
        ls = LocalSEOEngine()
        r = ls.setup("proj_demo","Kerala Spice Co","MG Road","Kochi","+91-484-000000","kochi")
        print(f"Local keywords: {r['local_keywords'][:4]}")
        print(f"NAP platforms checked: {len(r['nap_check']['checked'])}")
        print(f"Geo pages planned: {len(r['geo_pages_plan'])}")
        print("\n--- Algorithm Update Assessor Demo ---")
        au = AlgorithmUpdateAssessor()
        uid = au.register_update("March 2026 Core Update","2026-03-15",
                                   signals=["ai_watermarks","low_eeat","no_first_person"])
        print(f"Update registered: {uid}")
        print("\n--- Entity Builder Demo ---")
        eb = EntityAuthorityBuilder()
        r = eb.build_profile("proj_demo","Kerala Spice Co","food_spices",
                               "Premium organic spice exporter from Kerala")
        print(f"Entity gaps: {[g['platform'] for g in r['gaps']]}")
        print(f"Action plan: {r['action_plan'][:2]}")

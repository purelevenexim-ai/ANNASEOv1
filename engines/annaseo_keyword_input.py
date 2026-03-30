"""
================================================================================
ANNASEO — KEYWORD INPUT & UNIVERSE ENGINE  (annaseo_keyword_input.py)
================================================================================
Replaces the single-seed model with the correct customer-driven model:

  CUSTOMER PROVIDES:
    Pillar keywords  : Cinnamon, Turmeric, Black Pepper       (confirmed anchors)
    Supporting words : Organic, Kerala, Buy Online, Wholesale  (qualifiers)
    Business URL     : https://yourspicestore.com              (for site crawl)
    Competitor URLs  : [competitor1.com, competitor2.com]       (for gap analysis)
    Intent focus     : transactional / informational / both

  SYSTEM GENERATES (3 sources combined):
    Source A — Cross-multiplication:
      Pillar × Supporting = "Organic Cinnamon", "Buy Cinnamon Online",
                            "Kerala Turmeric", "Wholesale Black Pepper" …
    Source B — Customer website crawl:
      Extract ranking keywords, H1/H2 text, meta descriptions from their site
    Source C — Competitor website crawl:
      Extract top keywords from each competitor page
    Source D — Google Keyword data (optional, free alternatives if no API key):
      Google Autosuggest per combination + People Also Ask scraping

  SCORING (real signals, not proxies):
    Volume estimate   — based on autosuggest frequency + SERP result count
    Difficulty proxy  — number of authoritative domains in top results
    Relevance score   — how close the keyword is to pillar + supporting intent
    Quick win flag    — already ranking 11-20 (from GSC) = just push harder
    Opportunity score — Volume × (1 - Difficulty) × Relevance

  CUSTOMER REVIEW STAGES:
    Stage 1: Review cross-multiplication results — accept / reject / edit
    Stage 2: Review crawled keywords — accept / reject
    Stage 3: Review final universe — drag-and-drop into pillars / clusters
    (All stages stored in DB, resumable, full edit/delete/add)

DATABASE TABLES:
    keyword_input_sessions   — one per project run, tracks all stages
    pillar_keywords          — customer-provided pillars (confirmed)
    supporting_keywords      — customer-provided qualifiers (confirmed)
    keyword_universe_items   — all generated keywords with source + scores
    keyword_review_actions   — audit log of every customer accept/reject/edit

CRITICAL: A pillar keyword IS the universe seed. "Cinnamon" is not just a keyword —
it is the entire content strategy anchor. Every cluster under it, every article in it,
every internal link targets it.
================================================================================
"""

from __future__ import annotations
import os, re, json, hashlib, time, logging, sqlite3, uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse, urljoin

import requests as _req

log = logging.getLogger("annaseo.keyword_input")
DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))

# ── Intent types ──────────────────────────────────────────────────────────────
INTENT_LABELS = {
    "transactional": "Online Purchase / Sales",
    "informational": "Information / Education",
    "commercial":    "Research Before Buying",
    "comparison":    "Compare Products",
    "local":         "Local / Near Me",
    "wholesale":     "B2B / Wholesale",
}

# ── Signals that make a supporting keyword transactional vs informational ──────
TRANSACTIONAL_SIGNALS = [
    "buy", "purchase", "order", "price", "cost", "wholesale", "bulk", "supplier",
    "shop", "online", "delivery", "export", "import", "rate", "kg", "gram",
    "cheap", "discount", "offer", "deal", "store", "near me",
]
INFORMATIONAL_SIGNALS = [
    "benefits", "uses", "how to", "what is", "why", "health", "recipe",
    "tips", "guide", "natural", "organic", "ayurveda", "properties",
    "nutrition", "side effects", "dosage",
]


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS pillar_keywords (
        pillar_id   TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        keyword     TEXT NOT NULL,
        intent      TEXT DEFAULT 'informational',
        priority    INTEGER DEFAULT 1,
        confirmed   INTEGER DEFAULT 1,
        notes       TEXT DEFAULT '',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS supporting_keywords (
        support_id  TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        keyword     TEXT NOT NULL,
        intent_type TEXT DEFAULT 'transactional',
        confirmed   INTEGER DEFAULT 1,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS keyword_universe_items (
        item_id         TEXT PRIMARY KEY,
        project_id      TEXT NOT NULL,
        session_id      TEXT NOT NULL,
        keyword         TEXT NOT NULL,
        pillar_keyword  TEXT DEFAULT '',
        source          TEXT DEFAULT '',
        intent          TEXT DEFAULT 'informational',
        volume_estimate INTEGER DEFAULT 0,
        difficulty      INTEGER DEFAULT 50,
        relevance_score REAL DEFAULT 0,
        opportunity_score REAL DEFAULT 0,
        quick_win       INTEGER DEFAULT 0,
        status          TEXT DEFAULT 'pending',
        edited_keyword  TEXT DEFAULT '',
        customer_notes  TEXT DEFAULT '',
        created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
        reviewed_at     TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS keyword_input_sessions (
        session_id      TEXT PRIMARY KEY,
        project_id      TEXT NOT NULL,
        seed_keyword    TEXT DEFAULT '',
        stage           TEXT DEFAULT 'input',
        stage_status    TEXT DEFAULT 'pending',
        pillar_support_map TEXT DEFAULT '{}',
        intent_focus    TEXT DEFAULT 'both',
        total_generated INTEGER DEFAULT 0,
        total_accepted  INTEGER DEFAULT 0,
        total_rejected  INTEGER DEFAULT 0,
        sources_done    TEXT DEFAULT '[]',
        customer_url    TEXT DEFAULT '',
        competitor_urls TEXT DEFAULT '[]',
        business_intent TEXT DEFAULT 'mixed',
        target_audience TEXT DEFAULT '',
        geographic_focus TEXT DEFAULT 'India',
        created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS keyword_review_actions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  TEXT NOT NULL,
        item_id     TEXT NOT NULL,
        action      TEXT NOT NULL,
        old_value   TEXT DEFAULT '',
        new_value   TEXT DEFAULT '',
        reason      TEXT DEFAULT '',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_kw_project ON keyword_universe_items(project_id);
    CREATE INDEX IF NOT EXISTS ix_kw_session ON keyword_universe_items(session_id);
    CREATE INDEX IF NOT EXISTS ix_kw_pillar  ON keyword_universe_items(pillar_keyword);
    CREATE INDEX IF NOT EXISTS ix_kw_status  ON keyword_universe_items(status);
    CREATE INDEX IF NOT EXISTS ix_pillar_project ON pillar_keywords(project_id);

    CREATE TABLE IF NOT EXISTS top100_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        keywords    TEXT NOT NULL,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    con.commit()
    # Migration: add columns introduced after initial schema
    try:
        con.execute("ALTER TABLE keyword_input_sessions ADD COLUMN stage_status TEXT DEFAULT 'pending'")
        con.commit()
    except Exception:
        pass
    for _sql in [
        "ALTER TABLE keyword_universe_items ADD COLUMN ai_score REAL DEFAULT 0.0",
        "ALTER TABLE keyword_universe_items ADD COLUMN ai_flags TEXT DEFAULT '[]'",
        "ALTER TABLE keyword_universe_items ADD COLUMN score_signals TEXT DEFAULT '{}'",
        "ALTER TABLE keyword_universe_items ADD COLUMN final_score REAL DEFAULT 0.0",
        "ALTER TABLE keyword_universe_items ADD COLUMN category TEXT DEFAULT 'informational'",
        "ALTER TABLE keyword_input_sessions ADD COLUMN seed_keyword TEXT DEFAULT ''",
        "ALTER TABLE keyword_input_sessions ADD COLUMN pillar_support_map TEXT DEFAULT '{}'",
        "ALTER TABLE keyword_input_sessions ADD COLUMN intent_focus TEXT DEFAULT 'both'",
        "ALTER TABLE keyword_input_sessions ADD COLUMN business_intent TEXT DEFAULT 'mixed'",
        "ALTER TABLE keyword_input_sessions ADD COLUMN target_audience TEXT DEFAULT ''",
        "ALTER TABLE keyword_input_sessions ADD COLUMN geographic_focus TEXT DEFAULT 'India'",
    ]:
        try:
            con.execute(_sql)
            con.commit()
        except Exception:
            pass  # column already exists
    return con


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 1 — CUSTOMER INPUT COLLECTOR
# ─────────────────────────────────────────────────────────────────────────────

class CustomerInputCollector:
    def save_pillars(self, project_id: str, pillars: List[dict]) -> List[str]:
        con = _db()
        saved = []
        for p in pillars:
            kw = p.get("keyword", "").strip().lower()
            if not kw or len(kw) < 2:
                continue
            pid = f"pil_{project_id}_{hashlib.md5(kw.encode()).hexdigest()[:8]}"
            intent = p.get("intent", self._guess_intent(kw))
            con.execute("""
                INSERT OR REPLACE INTO pillar_keywords
                (pillar_id, project_id, keyword, intent, priority, confirmed)
                VALUES (?,?,?,?,?,1)
            """, (pid, project_id, kw, intent, p.get("priority", 1)))
            saved.append(pid)
        con.commit()
        log.info(f"[Input] Saved {len(saved)} pillars for {project_id}")
        return saved

    def save_supporting(self, project_id: str, keywords: List[str]) -> List[str]:
        con = _db()
        saved = []
        for kw_raw in keywords:
            kw = kw_raw.strip().lower()
            if not kw or len(kw) < 2:
                continue
            sid    = f"sup_{project_id}_{hashlib.md5(kw.encode()).hexdigest()[:8]}"
            intent = "transactional" if any(s in kw for s in TRANSACTIONAL_SIGNALS) else "informational"
            con.execute("""
                INSERT OR REPLACE INTO supporting_keywords
                (support_id, project_id, keyword, intent_type, confirmed)
                VALUES (?,?,?,?,1)
            """, (sid, project_id, kw, intent))
            saved.append(sid)
        con.commit()
        log.info(f"[Input] Saved {len(saved)} supporting keywords for {project_id}")
        return saved

    def get_pillars(self, project_id: str, seed: str = "") -> List[dict]:
        query = "SELECT * FROM pillar_keywords WHERE project_id=? AND confirmed=1"
        params = [project_id]
        if seed:
            query += " AND LOWER(keyword) LIKE ?"
            params.append(f"%{seed.lower()}%")
        query += " ORDER BY priority"
        return [dict(r) for r in _db().execute(query, params).fetchall()]

    def get_supporting(self, project_id: str) -> List[dict]:
        return [dict(r) for r in _db().execute(
            "SELECT * FROM supporting_keywords WHERE project_id=? AND confirmed=1",
            (project_id,)
        ).fetchall()]

    def _guess_intent(self, kw: str) -> str:
        kl = kw.lower()
        if any(s in kl for s in TRANSACTIONAL_SIGNALS): return "transactional"
        if any(s in kl for s in INFORMATIONAL_SIGNALS): return "informational"
        return "informational"


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 2 — CROSS MULTIPLIER
# ─────────────────────────────────────────────────────────────────────────────

class CrossMultiplier:
    TEMPLATES = {
        "transactional": [
            "{pillar} price per kg",
            "{pillar} wholesale price",
            "buy {pillar} online",
            "{pillar} bulk buy",
            "best {pillar} online india",
            "where to buy {pillar}",
            "{pillar} near me",
            "{pillar} supplier india",
            "organic {pillar} price",
            "{pillar} export quality",
        ],
        "informational": [
            "{pillar} benefits",
            "{pillar} health benefits",
            "how to use {pillar}",
            "what is {pillar}",
            "{pillar} uses",
            "{pillar} properties",
            "{pillar} ayurvedic uses",
            "{pillar} nutritional value",
            "{pillar} side effects",
            "best type of {pillar}",
        ],
        "local": [
            "{pillar} kerala",
            "{pillar} wayanad",
            "{pillar} india",
            "kerala {pillar} exporter",
            "buy {pillar} kerala",
            "{pillar} malabar",
        ],
        "comparison": [
            "types of {pillar}",
            "best {pillar} quality",
            "organic vs regular {pillar}",
        ],
    }

    def generate(self, pillars: List[dict], supporting: List[dict],
                  intent_focus: str = "both", seed: str = "",
                  pillar_support_map: Optional[Dict[str, List[str]]] = None) -> List[dict]:
        results = []

        for pillar_item in pillars:
            pil = pillar_item["keyword"]
            pil_intent = pillar_item.get("intent", "informational")

            results.append(self._make_item(pil, pil, "pillar_direct", pil_intent, 100))

            # Determine supporting set for this pillar (manual selection enforces local mapping)
            if pillar_support_map and pil.lower() in pillar_support_map:
                selected_supports = set([s.lower() for s in pillar_support_map[pil.lower()] if isinstance(s, str)])
                support_items = [sup_item for sup_item in supporting if sup_item["keyword"].lower() in selected_supports]
            else:
                support_items = supporting

            for sup_item in support_items:
                sup = sup_item["keyword"]
                sup_intent = sup_item.get("intent_type", "informational")
                combos = self._combine(pil, sup, sup_intent)
                for combo, intent in combos:
                    score = self._relevance(combo, pil, sup)
                    results.append(self._make_item(combo, pil, "cross_multiply", intent, score))

            for intent_type, templates in self.TEMPLATES.items():
                if intent_focus not in ("both", intent_type) and intent_focus != "both":
                    continue
                for tmpl in templates:
                    kw = tmpl.replace("{pillar}", pil)
                    score = 75 if intent_type == pil_intent else 60
                    results.append(self._make_item(kw, pil, "template", intent_type, score))

        seen = set()
        unique = []
        for r in results:
            k = r["keyword"].lower()
            if k not in seen:
                seen.add(k)
                unique.append(r)

        if seed:
            filtered = [r for r in unique if seed.lower() in r["keyword"].lower()]
            invalid = [r for r in unique if seed.lower() not in r["keyword"].lower()]
            if invalid:
                log.warning(f"[CrossMul] Seed contamination removed {len(invalid)} items for seed={seed}: {invalid[:5]}")
            unique = filtered

        log.info(f"[CrossMul] Generated {len(unique)} combinations from "
                  f"{len(pillars)} pillars x {len(supporting)} supporting (seed={seed})")
        return unique

    def _combine(self, pillar: str, supporting: str, intent: str) -> List[Tuple[str, str]]:
        combos = []
        p, s = pillar, supporting

        combos.append((f"{s} {p}", intent))
        combos.append((f"{p} {s}", intent))

        if any(t in s for t in ["buy", "purchase", "order", "online", "shop"]):
            combos.append((f"{s} {p}", "transactional"))

        if "benefit" in s or "health" in s or "use" in s:
            combos.append((f"{p} {s}", "informational"))
            combos.append((f"what are the {s} of {p}", "informational"))

        if any(loc in s for loc in ["kerala", "india", "wayanad", "malabar", "coorg"]):
            combos.append((f"{s} {p}", "local"))
            combos.append((f"{p} from {s}", "local"))
            combos.append((f"{s} {p} exporter", "transactional"))

        return list(dict.fromkeys(combos))

    def _relevance(self, keyword: str, pillar: str, supporting: str) -> float:
        score = 50.0
        kl = keyword.lower()
        if pillar.lower() in kl:     score += 20
        if supporting.lower() in kl: score += 15
        words = len(kl.split())
        if 2 <= words <= 4: score += 10
        if 5 <= words <= 6: score += 5
        return min(100, round(score, 1))

    def _make_item(self, keyword: str, pillar: str, source: str,
                    intent: str, relevance: float) -> dict:
        return {
            "keyword":        keyword.lower().strip(),
            "pillar_keyword": pillar.lower().strip(),
            "source":         source,
            "intent":         intent,
            "relevance_score":relevance,
            "volume_estimate":0,
            "difficulty":     50,
            "opportunity_score": 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 3 — WEBSITE KEYWORD EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

class WebsiteKeywordExtractor:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (SEO research; AnnaSEO keyword analysis)",
        "Accept": "text/html,application/xhtml+xml",
    }
    MAX_PAGES = 30

    def crawl(self, url: str, pillars: List[str], label: str = "site_crawl") -> List[dict]:
        if not url.startswith("http"):
            url = f"https://{url}"
        domain = "{0.scheme}://{0.netloc}".format(urlparse(url))
        log.info(f"[WebCrawl] Crawling {domain} (label={label})")

        pages = self._get_pages(domain, url)
        keywords = []

        for page_url in pages[:self.MAX_PAGES]:
            page_kws = self._extract_page_keywords(page_url, pillars, label)
            keywords.extend(page_kws)
            time.sleep(0.8)

        seen = set()
        unique = []
        for kw in keywords:
            k = kw["keyword"].lower()
            if k not in seen and len(k) > 4:
                seen.add(k)
                unique.append(kw)

        log.info(f"[WebCrawl] Extracted {len(unique)} keywords from {domain}")
        return unique

    def _get_pages(self, domain: str, start_url: str) -> List[str]:
        pages = [start_url]
        for path in ["/sitemap.xml", "/sitemap_index.xml"]:
            try:
                r = _req.get(f"{domain}{path}", headers=self.HEADERS, timeout=8)
                if r.ok and "xml" in r.headers.get("content-type", ""):
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(r.text, "xml")
                        locs = [l.get_text().strip() for l in soup.find_all("loc")]
                        pages.extend([l for l in locs if l.startswith(domain)][:50])
                    except Exception:
                        pass
                    if len(pages) > 5:
                        break
            except Exception:
                pass

        if len(pages) <= 3:
            try:
                r = _req.get(start_url, headers=self.HEADERS, timeout=10)
                if r.ok:
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(r.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            href = urljoin(start_url, a["href"])
                            if href.startswith(domain) and href not in pages:
                                pages.append(href)
                    except Exception:
                        pass
            except Exception:
                pass

        return list(dict.fromkeys(pages))[:self.MAX_PAGES]

    def _extract_page_keywords(self, url: str, pillars: List[str], label: str) -> List[dict]:
        keywords = []
        try:
            from bs4 import BeautifulSoup
            r = _req.get(url, headers=self.HEADERS, timeout=10)
            if not r.ok: return keywords
            if "text/html" not in r.headers.get("content-type", ""): return keywords

            soup = BeautifulSoup(r.text, "html.parser")

            slug = urlparse(url).path.replace("-", " ").replace("/", " ").strip()
            if slug:
                keywords.extend(self._slug_to_keywords(slug, pillars, label))

            title = soup.find("title")
            if title:
                keywords.extend(self._text_to_keywords(
                    title.get_text(strip=True), pillars, label, "title"))

            meta_desc = soup.find("meta", {"name": re.compile("description", re.I)})
            if meta_desc and meta_desc.get("content"):
                keywords.extend(self._text_to_keywords(
                    meta_desc["content"], pillars, label, "meta"))

            for tag in soup.find_all(["h1", "h2", "h3"])[:20]:
                text = tag.get_text(strip=True)
                if text:
                    keywords.extend(self._text_to_keywords(text, pillars, label, "heading"))

        except ImportError:
            log.debug("[WebCrawl] beautifulsoup4 not installed — skipping crawl")
        except Exception as e:
            log.debug(f"[WebCrawl] Page error {url}: {e}")
        return keywords

    def _slug_to_keywords(self, slug: str, pillars: List[str], label: str) -> List[dict]:
        words = re.sub(r"[^a-z0-9\s]", " ", slug.lower()).split()
        if not words or len(words) < 2: return []
        kw = " ".join(words[:6]).strip()
        if len(kw) < 5: return []
        pillar = self._nearest_pillar(kw, pillars)
        if not pillar: return []
        return [{"keyword": kw, "pillar_keyword": pillar, "source": label,
                 "intent": "informational", "relevance_score": 70,
                 "volume_estimate": 0, "difficulty": 45, "opportunity_score": 0}]

    def _text_to_keywords(self, text: str, pillars: List[str],
                            label: str, source_type: str) -> List[dict]:
        words = re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
        results = []
        for n in (2, 3, 4):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i+n])
                if any(p in phrase for p in pillars):
                    pillar = self._nearest_pillar(phrase, pillars)
                    results.append({
                        "keyword": phrase, "pillar_keyword": pillar,
                        "source": label,
                        "intent": self._infer_intent(phrase),
                        "relevance_score": 65,
                        "volume_estimate": 0, "difficulty": 45, "opportunity_score": 0,
                    })
        return results

    def _nearest_pillar(self, kw: str, pillars: List[str]) -> str:
        kl = kw.lower()
        for p in pillars:
            if p.lower() in kl:
                return p.lower()
        return ""

    def _infer_intent(self, kw: str) -> str:
        kl = kw.lower()
        if any(s in kl for s in TRANSACTIONAL_SIGNALS): return "transactional"
        if any(s in kl for s in INFORMATIONAL_SIGNALS): return "informational"
        return "informational"


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 4 — GOOGLE KEYWORD ENRICHER
# ─────────────────────────────────────────────────────────────────────────────

class GoogleKeywordEnricher:
    def enrich_batch(self, keywords: List[dict], project_id: str = "") -> List[dict]:
        log.info(f"[GKE] Enriching {len(keywords)} keywords...")
        if os.getenv("DATAFORSEO_LOGIN") and os.getenv("DATAFORSEO_PASSWORD"):
            return self._dataforseo_enrich(keywords)
        return self._free_enrich(keywords)

    def _free_enrich(self, keywords: List[dict]) -> List[dict]:
        for kw_item in keywords:
            kw = kw_item["keyword"]
            vol = self._check_autosuggest_rank(kw)
            kw_item["volume_estimate"] = vol
            diff = kw_item.get("difficulty", 50)
            rel  = kw_item.get("relevance_score", 50)
            kw_item["opportunity_score"] = round(
                min(vol / 1000, 1.0) * (1 - diff / 100) * (rel / 100) * 100, 1
            )
        return keywords

    def _check_autosuggest_rank(self, keyword: str) -> int:
        words = keyword.split()
        if len(words) < 2:
            return 30
        prefix = " ".join(words[:-1])
        try:
            r = _req.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "q": prefix},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5,
            )
            if r.ok:
                data = r.json()
                suggestions = data[1] if len(data) > 1 else []
                kl = keyword.lower()
                for i, s in enumerate(suggestions[:10]):
                    if kl in str(s).lower() or str(s).lower() in kl:
                        return max(20, 80 - i * 8)
        except Exception:
            pass
        return 20

    def _dataforseo_enrich(self, keywords: List[dict]) -> List[dict]:
        import base64
        login = os.getenv("DATAFORSEO_LOGIN")
        pwd   = os.getenv("DATAFORSEO_PASSWORD")
        token = base64.b64encode(f"{login}:{pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        batches = [keywords[i:i+100] for i in range(0, len(keywords), 100)]
        for batch in batches[:5]:
            kw_list = [kw["keyword"] for kw in batch]
            try:
                r = _req.post(
                    "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live",
                    headers=headers,
                    json=[{"keywords": kw_list, "language_name": "English", "location_code": 2356}],
                    timeout=30,
                )
                if r.ok:
                    data = r.json()
                    results = {}
                    for task in data.get("tasks", []):
                        for item in task.get("result", []) or []:
                            kw  = item.get("keyword", "")
                            vol = item.get("search_volume", 0) or 0
                            kd  = item.get("competition_index", 50) or 50
                            results[kw.lower()] = {"volume": vol, "difficulty": kd}
                    for kw_item in batch:
                        k = kw_item["keyword"].lower()
                        if k in results:
                            kw_item["volume_estimate"] = results[k]["volume"]
                            kw_item["difficulty"]      = results[k]["difficulty"]
                            kw_item["opportunity_score"] = round(
                                (results[k]["volume"] / 1000) *
                                (1 - results[k]["difficulty"] / 100) * 100, 1
                            )
            except Exception as e:
                log.warning(f"[GKE/DataForSEO] Batch failed: {e}")
        return keywords


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 5 — UNIVERSE ASSEMBLER
# ─────────────────────────────────────────────────────────────────────────────

class UniverseAssembler:
    def _is_entity_match(self, keyword: str, pillars: List[str]) -> bool:
        if not pillars:
            return True
        kw = keyword.lower()
        for p in pillars:
            pword = p.strip().lower()
            if not pword:
                continue
            if pword in kw:
                return True
        tokens = [t for p in pillars for t in p.lower().split() if len(t) > 2]
        return any(t in kw for t in tokens)

    def _classify_intent(self, keyword: str) -> str:
        kw = keyword.lower()
        if any(tok in kw for tok in TRANSACTIONAL_SIGNALS):
            return "transactional"
        if any(tok in kw for tok in INFORMATIONAL_SIGNALS):
            return "informational"
        if any(x in kw for x in ["vs", "compare", "comparison", "vs."]):
            return "comparison"
        if any(x in kw for x in ["near me", "local", "in india", "kerala", "kochi"]):
            return "local"
        return "commercial"

    def _extract_modifiers(self, keyword: str) -> dict:
        kw = keyword.lower()
        return {
            "quality": [m for m in ["organic", "premium", "export", "supreme", "fresh"] if m in kw],
            "location": [m for m in ["india", "kerala", "kochi", "malabar", "wayanad"] if m in kw],
            "intent": [m for m in TRANSACTIONAL_SIGNALS + INFORMATIONAL_SIGNALS if m in kw],
        }

    # ---------- P3 Scoring Constants ----------
    JUNK_PATTERNS = [
        "drawing", "emoji", "meaning", "experiment",
        "diagram", "kids", "photos", "images"
    ]

    BUYER_KEYWORDS = ["buy", "price", "wholesale", "supplier", "export", "bulk"]

    INTENT_SCORE = {
        "transactional": 100,
        "commercial": 80,
        "comparison": 70,
        "informational": 40,
        "navigational": 20,
    }

    def _is_junk(self, keyword: str) -> bool:
        kw = keyword.lower()
        return any(token in kw for token in self.JUNK_PATTERNS)

    def _buyer_score(self, keyword: str) -> int:
        kw = keyword.lower()
        return 100 if any(token in kw for token in self.BUYER_KEYWORDS) else 40

    def _local_score(self, keyword: str) -> int:
        kw = keyword.lower()
        return 100 if any(loc in kw for loc in ["india", "kerala", "near me"]) else 50

    def _relevance_score(self, keyword: str, entity: str) -> int:
        kw = keyword.lower()
        ent = (entity or "").lower().strip()
        if ent and ent in kw:
            return 100
        return 60

    def _brand_score(self, keyword: str, usp: str) -> int:
        kw = keyword.lower()
        if any(v in kw for v in ["export", "premium", "bulk"]):
            return 90
        if usp and any(word in kw for word in usp.lower().split()):
            return 85
        return 60

    def _naturalness_score(self, keyword: str) -> int:
        # basic heuristic; extend with ML model later
        kw = keyword.lower().strip()
        tokens = kw.split()
        if len(tokens) >= 3 and " " in kw:
            return 90
        if len(tokens) == 2:
            return 80
        return 60

    def _compute_score(self, kw: dict, entity: str, usp: str) -> float:
        keyword = kw.get("keyword", "")
        intent = kw.get("intent", "informational")

        intent_s = self.INTENT_SCORE.get(intent, 40)
        buyer_s = self._buyer_score(keyword)
        rel_s = self._relevance_score(keyword, entity)
        brand_s = self._brand_score(keyword, usp)
        local_s = self._local_score(keyword)
        nat_s = self._naturalness_score(keyword)

        final_score = (
            intent_s * 0.30 +
            buyer_s * 0.25 +
            rel_s * 0.20 +
            brand_s * 0.15 +
            local_s * 0.05 +
            nat_s * 0.05
        )
        return round(min(100, max(0, final_score)), 2)

    def _select_top_100(self, scored: List[dict]) -> List[dict]:
        sorted_kw = sorted(scored, key=lambda x: x.get("final_score", 0), reverse=True)

        money = [k for k in sorted_kw if k.get("category") == "money"][:40]
        consideration = [k for k in sorted_kw if k.get("category") == "consideration"][:30]
        informational = [k for k in sorted_kw if k.get("category") == "informational"][:20]
        local = [k for k in sorted_kw if any(loc in k.get("keyword","") for loc in ["india", "kerala"])][:10]

        final = money + consideration + informational + local
        seen = set(); unique = []
        for kw in final:
            text = kw.get("keyword","")
            if text not in seen:
                seen.add(text)
                unique.append(kw)
        return unique[:100]

    def score_and_select_top100(self, project_id: str, session_id: str, entity: str = "", usp: str = "") -> List[dict]:
        # fallback lookup if not passed
        project_db = get_db()
        if not usp:
            p = project_db.execute("SELECT usp FROM projects WHERE project_id=?", (project_id,)).fetchone()
            usp = p["usp"] if p else ""
        if not entity:
            p = project_db.execute("SELECT keyword FROM pillar_keywords WHERE project_id=? ORDER BY priority LIMIT 1", (project_id,)).fetchone()
            entity = p["keyword"] if p else ""
        project_db.close()

        con = _db()
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM keyword_universe_items WHERE session_id=? AND project_id=?",
            (session_id, project_id)
        ).fetchall()]
        con.close()

        scored = []
        for kw in rows:
            keyword_text = kw.get("keyword", "")
            if self._is_junk(keyword_text):
                continue
            kw_intent = kw.get("intent", "informational")
            kw_obj = {
                "keyword": keyword_text,
                "intent": kw_intent,
                "entities": {
                    "product": [kw.get("pillar_keyword", "")],
                },
            }
            final_score = self._compute_score(kw_obj, entity, usp)
            category = self._categorize(final_score)
            row_copy = kw.copy()  # copy existing data
            row_copy["final_score"] = final_score
            row_copy["category"] = category
            scored.append(row_copy)

        return self._select_top_100(scored)

    def _categorize(self, score: float) -> str:
        if score >= 80:
            return "money"
        if score >= 65:
            return "consideration"
        if score >= 40:
            return "informational"
        return "junk"

    def _cluster_keywords(self, keywords: List[dict]) -> List[dict]:
        clusters = {}
        for kw in keywords:
            intent = kw.get("intent", "commercial")
            modifiers = kw.get("modifiers", {})
            key = (intent, tuple(sorted(modifiers.get("quality", []))), tuple(sorted(modifiers.get("location", []))))
            clusters.setdefault(key, []).append(kw)

        grouped = []
        for key, items in clusters.items():
            primary = sorted(items, key=lambda x: x.get("opportunity_score", 0), reverse=True)[0]
            grouped.append({
                "cluster_key": key,
                "primary": primary,
                "variants": [i for i in items if i["keyword"] != primary["keyword"]],
                "intent": key[0],
                "count": len(items),
            })
        return grouped

    def assemble(self, project_id: str, session_id: str,
                  cross_kws: List[dict], site_kws: List[dict],
                  competitor_kws: List[dict], gsc_kws: List[dict] = None,
                  seed: str = "") -> List[dict]:
        all_kws = list(cross_kws) + list(site_kws) + list(competitor_kws)
        if gsc_kws:
            all_kws.extend(gsc_kws)

        # Entity lock: avoid drift across pillars (clove should not mutate into turmeric etc.)
        if seed:
            pillar_words = [p["keyword"] for p in CustomerInputCollector().get_pillars(project_id, seed=seed)]
        else:
            pillar_words = [p["keyword"] for p in CustomerInputCollector().get_pillars(project_id)]
        filtered = []
        for kw in all_kws:
            text = kw.get("keyword", "").strip()
            if not text or len(text) < 4:
                continue
            if self._is_entity_match(text, pillar_words):
                filtered.append(kw)

        # Exact dedup + best source merging, no destructive normalization that collapses intent / modifier variants.
        deduped: Dict[str, dict] = {}
        for kw in filtered:
            k = kw["keyword"].lower().strip()
            if k not in deduped:
                deduped[k] = kw
            else:
                existing = deduped[k]
                existing_score = existing.get("opportunity_score", 0) or 0
                kw_score = kw.get("opportunity_score", 0) or 0
                if kw_score > existing_score:
                    deduped[k] = {**kw, "source": f"{existing.get('source','')}+{kw.get('source','')}".strip("+")}
                else:
                    deduped[k]["source"] = f"{existing.get('source','')}+{kw.get('source','')}".strip("+")

        gsc_near_rank = set(g["keyword"].lower() for g in (gsc_kws or []))
        for kw in deduped.values():
            if kw["keyword"].lower() in gsc_near_rank:
                kw["quick_win"] = 1

        universe_keywords = []
        for kw in deduped.values():
            # Relaxed seed filter: only filter if seed is provided and the keyword has no relation to it.
            # Previously: if seed and seed.lower() not in kw.get("keyword", "").lower(): continue
            # Now we keep keywords even if they don't contain the literal seed string, as long as they passed _is_entity_match.
            text = kw.get("keyword", "")
            intent = kw.get("intent") or self._classify_intent(text)
            modifiers = kw.get("modifiers") or self._extract_modifiers(text)
            kw["intent"] = intent
            kw["modifiers"] = modifiers
            universe_keywords.append(kw)

        clusters = self._cluster_keywords(universe_keywords)
        log.info(f"[Assembler] created {len(clusters)} clusters from {len(universe_keywords)} keywords")

        # Score and classify each keyword (core P3 scoring)
        entity = pillar_words[0] if pillar_words else ""
        usp = ""  # if project has USP pulled in, pass it here
        for kw in universe_keywords:
            kw["final_score"] = self._compute_score(kw, entity, usp)
            kw["category"] = self._categorize(kw["final_score"])

        final = sorted(universe_keywords,
                       key=lambda x: x.get("final_score", x.get("opportunity_score", 0)), reverse=True)

        top100 = self._select_top_100(final)

        con = _db()
        for kw in final:
            item_id = f"ki_{session_id}_{hashlib.md5(kw['keyword'].encode()).hexdigest()[:8]}"
            serp_domain_proxy = 100 if kw.get("source") in ["site_crawl", "competitor_crawl"] else 70
            serp_intent_diff = 100 if kw.get("intent", "informational") == "transactional" else 70
            ai_flags = {
                "serp_domain_proxy": serp_domain_proxy,
                "serp_intent_diff": serp_intent_diff,
                "brand_tone_matched": kw.get("brand_score", 0) >= 70
            }
            con.execute("""
                INSERT OR REPLACE INTO keyword_universe_items
                (item_id, project_id, session_id, keyword, pillar_keyword,
                 source, intent, volume_estimate, difficulty, relevance_score,
                 opportunity_score, final_score, category, quick_win, status, ai_flags)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (item_id, project_id, session_id, kw["keyword"],
                   kw.get("pillar_keyword", ""),
                   kw.get("source", ""),
                   kw.get("intent", "informational"),
                   int(kw.get("volume_estimate", 0)),
                   int(kw.get("difficulty", 50)),
                   float(kw.get("relevance_score", 50)),
                   float(kw.get("opportunity_score", 0)),
                   float(kw.get("final_score", 0)),
                   kw.get("category", "informational"),
                   int(kw.get("quick_win", 0)),
                   "pending", json.dumps({**kw.get("modifiers", {}), **ai_flags})))
        con.execute("""
            UPDATE keyword_input_sessions SET total_generated=?, updated_at=?
            WHERE session_id=?
        """, (len(final), datetime.utcnow().isoformat(), session_id))
        con.commit()

        log.info(f"[Assembler] {len(final)} unique keywords assembled for {project_id}")
        return {"final": final, "clusters": clusters, "top100": top100}



# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 6 — REVIEW MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class ReviewManager:
    def accept(self, item_id: str, session_id: str):
        self._update(item_id, "accepted")
        self._log(session_id, item_id, "accept")

    def reject(self, item_id: str, session_id: str, reason: str = ""):
        self._update(item_id, "rejected")
        self._log(session_id, item_id, "reject", reason=reason)
        try:
            con = _db()
            kw = con.execute("SELECT keyword, project_id FROM keyword_universe_items WHERE item_id=?",
                              (item_id,)).fetchone()
            if kw:
                from annaseo_domain_context import DomainContextEngine
                DomainContextEngine().feedback(
                    keyword=dict(kw)["keyword"],
                    project_id=dict(kw)["project_id"],
                    verdict="reject",
                    reason=reason or "Customer rejected in keyword review",
                )
        except Exception:
            pass

    def edit(self, item_id: str, session_id: str, new_keyword: str):
        old = self._get_keyword(item_id)
        con = _db()
        con.execute("""
            UPDATE keyword_universe_items
            SET edited_keyword=?, status='accepted', reviewed_at=?
            WHERE item_id=?
        """, (new_keyword.strip().lower(), datetime.utcnow().isoformat(), item_id))
        con.commit()
        self._log(session_id, item_id, "edit", old_value=old, new_value=new_keyword)

    def move_pillar(self, item_id: str, session_id: str, new_pillar: str):
        old_pillar = self._db_get(item_id, "pillar_keyword")
        con = _db()
        con.execute("UPDATE keyword_universe_items SET pillar_keyword=? WHERE item_id=?",
                     (new_pillar.lower(), item_id))
        con.commit()
        self._log(session_id, item_id, "move_pillar", old_value=old_pillar, new_value=new_pillar)

    def accept_all(self, session_id: str):
        con = _db()
        con.execute("""
            UPDATE keyword_universe_items SET status='accepted', reviewed_at=?
            WHERE session_id=? AND status='pending'
        """, (datetime.utcnow().isoformat(), session_id))
        con.commit()

    def get_stats(self, session_id: str) -> dict:
        con = _db()
        rows = [dict(r) for r in con.execute("""
            SELECT status, COUNT(*) as cnt FROM keyword_universe_items
            WHERE session_id=? GROUP BY status
        """, (session_id,)).fetchall()]
        return {r["status"]: r["cnt"] for r in rows}

    def get_review_queue(self, session_id: str, pillar: str = None,
                          status: str = None, intent: str = None,
                          review_method: str = None,
                          sort_by: str = "opp_desc",
                          limit: int = 100, offset: int = 0) -> List[dict]:
        con = _db()
        q = "SELECT * FROM keyword_universe_items WHERE session_id=?"
        p: list = [session_id]
        if status and status != "all":
            q += " AND status=?"
            p.append(status)
        if pillar:
            q += " AND pillar_keyword=?"
            p.append(pillar)
        if intent:
            q += " AND intent=?"
            p.append(intent)
        if review_method == "method1":
            q += " AND source IN ('cross_multiply','site_crawl','competitor_crawl')"
        elif review_method == "method2":
            q += " AND source IN ('research_autosuggest','research_competitor_gap','research_site_crawl','strategy')"
        sort_map = {
            "opp_desc": "opportunity_score DESC, relevance_score DESC",
            "kd_asc":   "difficulty ASC",
            "vol_desc":  "volume_estimate DESC",
            "kw_asc":    "keyword ASC",
        }
        q += f" ORDER BY {sort_map.get(sort_by, 'opportunity_score DESC')} LIMIT ? OFFSET ?"
        p += [limit, offset]
        return [dict(r) for r in con.execute(q, p).fetchall()]

    def _update(self, item_id: str, status: str):
        con = _db()
        con.execute("UPDATE keyword_universe_items SET status=?, reviewed_at=? WHERE item_id=?",
                     (status, datetime.utcnow().isoformat(), item_id))
        con.commit()

    def _log(self, session_id, item_id, action, old_value="", new_value="", reason=""):
        try:
            con = _db()
            con.execute("""
                INSERT INTO keyword_review_actions
                (session_id, item_id, action, old_value, new_value, reason)
                VALUES (?,?,?,?,?,?)
            """, (session_id, item_id, action, old_value, new_value, reason))
            con.commit()
        except Exception:
            pass

    def _get_keyword(self, item_id: str) -> str:
        row = _db().execute("SELECT keyword FROM keyword_universe_items WHERE item_id=?",
                             (item_id,)).fetchone()
        return dict(row)["keyword"] if row else ""

    def _db_get(self, item_id: str, col: str) -> str:
        row = _db().execute(f"SELECT {col} FROM keyword_universe_items WHERE item_id=?",
                             (item_id,)).fetchone()
        return dict(row).get(col, "") if row else ""


# ─────────────────────────────────────────────────────────────────────────────
# MASTER ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class KeywordInputEngine:
    def __init__(self):
        self.input_collector  = CustomerInputCollector()
        self.cross_multiplier = CrossMultiplier()
        self.web_extractor    = WebsiteKeywordExtractor()
        self.enricher         = GoogleKeywordEnricher()
        self.assembler        = UniverseAssembler()
        self.reviewer         = ReviewManager()

    def save_customer_input(self, project_id: str, pillars: List[dict],
                              supporting: List[str], pillar_support_map: Dict[str, List[str]] = None,
                              intent_focus: str = "both",
                              customer_url: str = "", competitor_urls: List[str] = None,
                              business_intent: str = "mixed", target_audience: str = "",
                              geographic_focus: str = "India") -> str:
        self.input_collector.save_pillars(project_id, pillars)
        self.input_collector.save_supporting(project_id, supporting)

        session_id = f"kis_{project_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        seed_keyword = ""
        if pillars and isinstance(pillars, list) and len(pillars) > 0:
            first_pillar = str(pillars[0].get("keyword", "")).strip().lower()
            seed_keyword = first_pillar

        con = _db()
        con.execute("""
            INSERT INTO keyword_input_sessions
            (session_id, project_id, seed_keyword, stage, pillar_support_map, intent_focus, customer_url, competitor_urls, business_intent, target_audience, geographic_focus)
            VALUES (?, ?, ?, 'input', ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, project_id, seed_keyword,
              json.dumps(pillar_support_map or {}), intent_focus,
              customer_url or "", json.dumps(competitor_urls or []),
              business_intent or "mixed", target_audience or "", geographic_focus or "India"))
        con.commit()
        log.info(f"[KIE] Customer input saved: {len(pillars)} pillars, "
                  f"{len(supporting)} supporting — session {session_id}")
        return session_id

    def _run_ai_review_pipeline(self, project_id: str, session_id: str,
                                stage: str = "deepseek",
                                auto_apply: bool = True,
                                backend_url: str = None) -> Optional[dict]:
        """Run a blocking AI review stage by calling the local review endpoint."""
        if not backend_url:
            backend_url = os.getenv("ANNASEO_BACKEND_URL", "http://localhost:8000")
        try:
            resp = _req.post(
                f"{backend_url}/api/ki/{project_id}/ai-review/session/{session_id}",
                json={"stage": stage, "auto_apply": auto_apply, "limit": 5000},
                timeout=240
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.warning(f"[KIE] AI review call failed for session {session_id}: {e}")
            return None

    def generate_universe(self, project_id: str, session_id: str,
                            customer_url: str = "",
                            competitor_urls: List[str] = None) -> dict:
        con = _db()

        def _step(stage, sources):
            con.execute(
                "UPDATE keyword_input_sessions SET stage=?, sources_done=?, updated_at=? WHERE session_id=?",
                (stage, json.dumps(sources), datetime.utcnow().isoformat(), session_id)
            )
            con.commit()

        sources = []
        _step('cross_multiply', sources)

        # Ensure strict per-session seed isolation from customer input
        row = _db().execute(
            "SELECT seed_keyword, pillar_support_map, intent_focus FROM keyword_input_sessions WHERE session_id=?",
            (session_id,)
        ).fetchone()
        session_seed = row["seed_keyword"] if row and row["seed_keyword"] else ""
        pillar_support_map = {}
        intent_focus_db = "both"
        if row:
            try:
                pillar_support_map = json.loads(row.get("pillar_support_map") or "{}")
            except Exception:
                pillar_support_map = {}
            intent_focus_db = row.get("intent_focus") or "both"

        pillars_data    = self.input_collector.get_pillars(project_id, seed=session_seed)
        supporting_data = self.input_collector.get_supporting(project_id)
        if session_seed:
            pillar_words = [p["keyword"] for p in pillars_data if session_seed.lower() in p["keyword"].lower()]
        else:
            pillar_words = [p["keyword"] for p in pillars_data]

        # Step 1: Cross multiplication
        log.info("[KIE] Step 1: Cross-multiplying pillars x supporting...")
        cross_kws = self.cross_multiplier.generate(
            pillars_data,
            supporting_data,
            intent_focus=intent_focus_db,
            seed=session_seed,
            pillar_support_map=pillar_support_map,
        )
        sources.append({"step": "cross_multiply", "count": len(cross_kws), "label": "phrase combinations"})
        _step('crawl_site', sources)

        # Step 2: Customer website crawl
        site_kws = []
        if customer_url:
            log.info(f"[KIE] Step 2: Crawling customer site {customer_url}...")
            try:
                site_kws = self.web_extractor.crawl(customer_url, pillar_words, "site_crawl")
            except Exception as e:
                log.warning(f"[KIE] Site crawl failed: {e}")
        sources.append({"step": "crawl_site", "count": len(site_kws), "label": "keywords from site"})
        _step('crawl_competitors', sources)

        # Step 3: Competitor crawl
        competitor_kws = []
        for comp_url in (competitor_urls or [])[:4]:
            if comp_url:
                log.info(f"[KIE] Step 3: Crawling competitor {comp_url}...")
                try:
                    kws = self.web_extractor.crawl(comp_url, pillar_words, "competitor")
                    competitor_kws.extend(kws)
                except Exception as e:
                    log.warning(f"[KIE] Competitor crawl failed {comp_url}: {e}")
        sources.append({"step": "crawl_competitors", "count": len(competitor_kws), "label": "keywords from competitors"})
        _step('enrich', sources)

        # Step 4: Enrich with autosuggest + volume + difficulty
        log.info("[KIE] Step 4: Enriching keyword scores...")
        all_kws = cross_kws + site_kws + competitor_kws
        enriched = self.enricher.enrich_batch(all_kws, project_id)
        sources.append({"step": "enrich", "count": len(enriched), "label": "keywords enriched"})
        _step('assemble', sources)

        # Step 5: Assemble final universe
        nc = len(cross_kws)
        ns = len(site_kws)
        assembled = self.assembler.assemble(
            project_id, session_id,
            cross_kws=enriched[:nc],
            site_kws=enriched[nc:nc+ns],
            competitor_kws=enriched[nc+ns:],
            seed=session_seed
        )
        final = assembled.get("final", [])
        top100 = assembled.get("top100", [])
        sources.append({"step": "assemble", "count": len(final), "label": "keywords assembled"})
        _step('score', sources)

        # Step 6: Score (done inline — mark complete)
        sources.append({"step": "score", "count": len(final), "label": "keywords scored"})
        _step('review_cross', sources)

        # Step 7: AI Review step (auto-run from pipeline before human review)
        for ai_stage in ["deepseek", "groq", "gemini"]:
            ai_review_result = self._run_ai_review_pipeline(project_id, session_id, stage=ai_stage)
            if ai_review_result:
                log.info(f"[KIE] AI stage {ai_stage} completed for session {session_id}: {ai_review_result.get('flagged_count',0)} flagged")
        _step('ai_review', sources)

        by_pillar = {}
        for kw in final:
            p = kw.get("pillar_keyword", "other")
            if p not in by_pillar:
                by_pillar[p] = {"total": 0}
            by_pillar[p]["total"] += 1

        return {
            "session_id":     session_id,
            "stage":          "ai_review",  # next stage now includes auto AI review
            "total_keywords": len(final),
            "top_100_keywords": top100,
            "by_pillar":      by_pillar,
            "by_source": {
                "cross_multiply": nc,
                "site_crawl":     ns,
                "competitor":     len(competitor_kws),
            },
            "top_10": [
                {"keyword": k["keyword"], "pillar": k.get("pillar_keyword",""),
                 "intent": k.get("intent",""), "score": k.get("opportunity_score",0)}
                for k in final[:10]
            ],
        }

    def confirm_universe(self, session_id: str, project_id: str) -> List[str]:
        con = _db()
        self.reviewer.accept_all(session_id)

        accepted = [dict(r) for r in con.execute("""
            SELECT COALESCE(NULLIF(edited_keyword,''), keyword) as kw
            FROM keyword_universe_items
            WHERE session_id=? AND status='accepted'
            ORDER BY opportunity_score DESC
        """, (session_id,)).fetchall()]

        con.execute("UPDATE keyword_input_sessions SET stage='confirmed', updated_at=? WHERE session_id=?",
                     (datetime.utcnow().isoformat(), session_id))
        con.commit()
        keywords_out = [r["kw"] for r in accepted]
        log.info(f"[KIE] Universe confirmed: {len(keywords_out)} keywords -> 20-phase pipeline")
        return keywords_out

    def get_latest_session(self, project_id: str) -> Optional[dict]:
        row = _db().execute("""
            SELECT * FROM keyword_input_sessions
            WHERE project_id=? ORDER BY created_at DESC LIMIT 1
        """, (project_id,)).fetchone()
        return dict(row) if row else None

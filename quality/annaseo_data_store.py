"""
================================================================================
ANNASEO — DATA STORE ENGINE
================================================================================
File        : annaseo_data_store.py
Purpose     : Intercept and store every result from every engine run.
              This is the feed for the Quality Engine.

Every engine result → DataStore → Quality Engine → User Feedback → Tuning

What gets stored
────────────────
  Keyword Universe results     → pillar keywords, supporting keywords, clusters
  Content results              → article text, SEO scores, GEO scores, E-E-A-T
  SEO Audit results            → technical scores, findings, per-page health
  Publisher results            → published URLs, platform, schedule
  Confirmation Gate decisions  → what the user approved/rejected at each gate
  Rankings data                → GSC positions, CTR, impressions per keyword
  Strategy results             → personas, context, calendar plan

How to integrate
────────────────
  Each engine calls DataStore.record() after completing.
  Takes <2ms — fire and forget, non-blocking.
  Result ID returned for traceability.

  from annaseo_data_store import DataStore
  ds = DataStore()
  ds.record("keyword_universe", project_id="proj_001", data={
      "seed": "cinnamon",
      "pillars": ["cinnamon benefits", "cinnamon tour"],   # <-- bad pillar flagged later
      "clusters": [...],
      "keywords": [...]
  })
================================================================================
"""

from __future__ import annotations

import os, json, hashlib, logging, sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

log = logging.getLogger("annaseo.datastore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))


# ─────────────────────────────────────────────────────────────────────────────
# RESULT TYPES — every engine maps to one of these
# ─────────────────────────────────────────────────────────────────────────────

class ResultType:
    KEYWORD_UNIVERSE   = "keyword_universe"   # pillars, clusters, supporting kws
    KEYWORD_ITEM       = "keyword_item"        # one individual keyword scored
    CONTENT_ARTICLE    = "content_article"     # one generated article + all scores
    SEO_AUDIT_PAGE     = "seo_audit_page"      # one page audit result
    SEO_AUDIT_SITE     = "seo_audit_site"      # full site audit summary
    PUBLISHER_RESULT   = "publisher_result"    # one published article outcome
    RANKING_DATA       = "ranking_data"        # GSC position data
    GATE_DECISION      = "gate_decision"       # confirmation gate approve/reject
    STRATEGY_RESULT    = "strategy_result"     # content strategy output
    CLUSTER_RESULT     = "cluster_result"      # one cluster with all keywords
    CONTENT_CALENDAR   = "content_calendar"    # calendar plan output
    COMPETITOR_RESULT  = "competitor_result"   # competitor analysis output


@dataclass
class ResultRecord:
    record_id:    str
    result_type:  str
    project_id:   str
    engine_name:  str
    seed:         str             = ""    # seed keyword or page URL
    data:         dict            = field(default_factory=dict)
    summary:      str             = ""    # human-readable one-liner
    quality_score:Optional[float] = None  # filled by Quality Engine
    created_at:   str             = field(default_factory=lambda: datetime.utcnow().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ds_results (
        record_id     TEXT PRIMARY KEY,
        result_type   TEXT NOT NULL,
        project_id    TEXT NOT NULL,
        engine_name   TEXT NOT NULL,
        seed          TEXT DEFAULT '',
        data          TEXT NOT NULL,
        summary       TEXT DEFAULT '',
        quality_score REAL,
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS ds_result_items (
        item_id       TEXT PRIMARY KEY,
        record_id     TEXT NOT NULL,
        project_id    TEXT NOT NULL,
        result_type   TEXT NOT NULL,
        item_type     TEXT NOT NULL,
        item_value    TEXT NOT NULL,
        item_meta     TEXT DEFAULT '{}',
        quality_label TEXT DEFAULT 'unreviewed',
        quality_score REAL,
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (record_id) REFERENCES ds_results(record_id)
    );

    CREATE INDEX IF NOT EXISTS idx_ds_results_project   ON ds_results(project_id);
    CREATE INDEX IF NOT EXISTS idx_ds_results_type      ON ds_results(result_type);
    CREATE INDEX IF NOT EXISTS idx_ds_results_created   ON ds_results(created_at);
    CREATE INDEX IF NOT EXISTS idx_ds_items_record      ON ds_result_items(record_id);
    CREATE INDEX IF NOT EXISTS idx_ds_items_type        ON ds_result_items(result_type);
    CREATE INDEX IF NOT EXISTS idx_ds_items_label       ON ds_result_items(quality_label);
    """)
    db.commit()
    return db


# ─────────────────────────────────────────────────────────────────────────────
# DATA STORE — the main interface all engines call
# ─────────────────────────────────────────────────────────────────────────────

class DataStore:
    """
    Central result store. Every engine result flows through here.
    Non-blocking: record() returns immediately.

    Usage (in any engine):
        from annaseo_data_store import DataStore
        ds = DataStore()
        record_id = ds.record(
            result_type = ResultType.KEYWORD_UNIVERSE,
            project_id  = "proj_001",
            engine_name = "20phase_engine",
            seed        = "cinnamon",
            data        = { "pillars": [...], "clusters": [...] },
            summary     = "Generated 45 pillars, 320 clusters"
        )
    """

    def __init__(self):
        self._db = _get_db()

    def record(self, result_type: str, project_id: str, engine_name: str,
                data: dict, seed: str = "", summary: str = "") -> str:
        """Store one engine result. Returns record_id."""
        record_id = f"rec_{hashlib.md5(f'{result_type}{project_id}{engine_name}{datetime.utcnow().isoformat()}'.encode()).hexdigest()[:14]}"

        self._db.execute("""
            INSERT OR REPLACE INTO ds_results
            (record_id, result_type, project_id, engine_name, seed, data, summary)
            VALUES (?,?,?,?,?,?,?)
        """, (record_id, result_type, project_id, engine_name, seed,
              json.dumps(data, default=str)[:100000], summary[:500]))
        self._db.commit()

        # Explode into items for granular quality review
        self._explode_items(record_id, result_type, project_id, data)

        log.debug(f"[DataStore] recorded {result_type} for {project_id}: {record_id}")
        return record_id

    def _explode_items(self, record_id: str, result_type: str,
                        project_id: str, data: dict):
        """
        Break composite results into individual reviewable items.
        This is what appears in the Quality Engine's review queue.
        """
        items = []

        if result_type == ResultType.KEYWORD_UNIVERSE:
            for p in data.get("pillars", []):
                if isinstance(p, str):
                    items.append(("pillar_keyword", p, {}))
                elif isinstance(p, dict):
                    items.append(("pillar_keyword", p.get("keyword", str(p)), p))
            for c in data.get("clusters", [])[:50]:
                name = c.get("name", str(c)) if isinstance(c, dict) else str(c)
                items.append(("cluster_name", name, c if isinstance(c, dict) else {}))
            for kw in data.get("supporting_keywords", [])[:100]:
                kw_val = kw if isinstance(kw, str) else kw.get("keyword", str(kw))
                items.append(("supporting_keyword", kw_val, {}))

        elif result_type == ResultType.KEYWORD_ITEM:
            kw = data.get("keyword", "")
            if kw:
                items.append(("keyword", kw, {
                    "intent":     data.get("intent", ""),
                    "score":      data.get("score", 0),
                    "cluster":    data.get("cluster", ""),
                    "is_pillar":  data.get("is_pillar", False),
                }))

        elif result_type == ResultType.CONTENT_ARTICLE:
            items.append(("article_title",     data.get("title", ""),           {}))
            items.append(("article_body",      data.get("body", "")[:2000],     {
                "seo_score":    data.get("seo_score", 0),
                "eeat_score":   data.get("eeat_score", 0),
                "geo_score":    data.get("geo_score", 0),
                "readability":  data.get("readability_score", 0),
                "word_count":   data.get("word_count", 0),
                "keyword":      data.get("keyword", ""),
            }))
            items.append(("meta_title",        data.get("meta_title", ""),      {}))
            items.append(("meta_description",  data.get("meta_description", ""),{}))
            for faq in data.get("faqs", [])[:5]:
                q = faq.get("question", str(faq)) if isinstance(faq, dict) else str(faq)
                items.append(("faq_question", q, {}))

        elif result_type == ResultType.SEO_AUDIT_PAGE:
            items.append(("page_url",     data.get("url", ""),   {"score": data.get("score", 0)}))
            for f in data.get("findings", [])[:20]:
                title = f.get("title", "") if isinstance(f, dict) else str(f)
                items.append(("audit_finding", title, f if isinstance(f, dict) else {}))

        elif result_type == ResultType.CLUSTER_RESULT:
            cluster_name = data.get("cluster_name", data.get("name", ""))
            items.append(("cluster_name", cluster_name, {
                "cluster_type": data.get("cluster_type", ""),
                "keyword_count": len(data.get("keywords", [])),
            }))
            for kw in data.get("keywords", [])[:20]:
                items.append(("cluster_keyword", kw if isinstance(kw, str) else kw.get("keyword", str(kw)), {}))

        elif result_type == ResultType.STRATEGY_RESULT:
            for persona in data.get("personas", []):
                items.append(("persona", str(persona)[:200], {}))
            for theme in data.get("content_themes", []):
                items.append(("content_theme", str(theme)[:200], {}))

        elif result_type == ResultType.RANKING_DATA:
            for row in data.get("keywords", [])[:50]:
                kw  = row.get("keyword", "")
                pos = row.get("position", 999)
                items.append(("ranking_keyword", kw, {"position": pos, "ctr": row.get("ctr", 0)}))

        # Batch insert items
        for item_type, item_value, item_meta in items:
            if not item_value or not str(item_value).strip():
                continue
            iid = f"item_{hashlib.md5(f'{record_id}{item_type}{item_value}'.encode()).hexdigest()[:12]}"
            self._db.execute("""
                INSERT OR IGNORE INTO ds_result_items
                (item_id, record_id, project_id, result_type, item_type, item_value, item_meta)
                VALUES (?,?,?,?,?,?,?)
            """, (iid, record_id, project_id, result_type,
                  item_type, str(item_value)[:500],
                  json.dumps(item_meta, default=str)[:2000]))
        self._db.commit()

    # ── Query Methods ──────────────────────────────────────────────────────────

    def get_records(self, project_id: str = None, result_type: str = None,
                     limit: int = 100) -> List[dict]:
        q, p = "SELECT * FROM ds_results", []
        filters = []
        if project_id: filters.append("project_id=?"); p.append(project_id)
        if result_type: filters.append("result_type=?"); p.append(result_type)
        if filters: q += " WHERE " + " AND ".join(filters)
        q += " ORDER BY created_at DESC LIMIT ?"
        p.append(limit)
        return [dict(r) for r in self._db.execute(q, p).fetchall()]

    def get_items(self, project_id: str = None, result_type: str = None,
                   item_type: str = None, label: str = None,
                   limit: int = 200) -> List[dict]:
        q, p = "SELECT * FROM ds_result_items", []
        filters = []
        if project_id:  filters.append("project_id=?");   p.append(project_id)
        if result_type: filters.append("result_type=?");   p.append(result_type)
        if item_type:   filters.append("item_type=?");     p.append(item_type)
        if label:       filters.append("quality_label=?"); p.append(label)
        if filters: q += " WHERE " + " AND ".join(filters)
        q += " ORDER BY created_at DESC LIMIT ?"
        p.append(limit)
        return [dict(r) for r in self._db.execute(q, p).fetchall()]

    def get_item(self, item_id: str) -> Optional[dict]:
        r = self._db.execute(
            "SELECT * FROM ds_result_items WHERE item_id=?", (item_id,)
        ).fetchone()
        return dict(r) if r else None

    def set_quality_score(self, record_id: str, score: float):
        self._db.execute(
            "UPDATE ds_results SET quality_score=? WHERE record_id=?",
            (score, record_id))
        self._db.commit()

    def summary_stats(self, project_id: str = None) -> dict:
        p = [project_id] if project_id else []
        where = "WHERE project_id=?" if project_id else ""

        type_counts = {}
        for row in self._db.execute(
            f"SELECT result_type, COUNT(*) as cnt FROM ds_results {where} GROUP BY result_type", p
        ).fetchall():
            type_counts[row["result_type"]] = row["cnt"]

        label_counts = {}
        for row in self._db.execute(
            f"SELECT quality_label, COUNT(*) as cnt FROM ds_result_items {where} GROUP BY quality_label", p
        ).fetchall():
            label_counts[row["quality_label"]] = row["cnt"]

        return {
            "total_records":  sum(type_counts.values()),
            "by_result_type": type_counts,
            "total_items":    sum(label_counts.values()),
            "by_label":       label_counts,
            "unreviewed":     label_counts.get("unreviewed", 0),
            "good":           label_counts.get("good", 0),
            "bad":            label_counts.get("bad", 0),
        }


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION HELPERS — one line per engine
# ─────────────────────────────────────────────────────────────────────────────

def store_keyword_universe(project_id: str, seed: str, pillars: list,
                            clusters: list, supporting: list,
                            engine: str = "20phase_engine") -> str:
    return DataStore().record(
        result_type=ResultType.KEYWORD_UNIVERSE,
        project_id=project_id, engine_name=engine, seed=seed,
        data={"pillars": pillars, "clusters": clusters,
              "supporting_keywords": supporting},
        summary=f"{len(pillars)} pillars, {len(clusters)} clusters"
    )


def store_content_article(project_id: str, keyword: str, title: str,
                           body: str, scores: dict,
                           engine: str = "content_engine") -> str:
    return DataStore().record(
        result_type=ResultType.CONTENT_ARTICLE,
        project_id=project_id, engine_name=engine, seed=keyword,
        data={"keyword": keyword, "title": title, "body": body, **scores},
        summary=f"Article: {title[:60]} | SEO:{scores.get('seo_score',0)}"
    )


def store_seo_audit(project_id: str, url: str, score: float,
                     findings: list, engine: str = "seo_audit") -> str:
    return DataStore().record(
        result_type=ResultType.SEO_AUDIT_PAGE,
        project_id=project_id, engine_name=engine, seed=url,
        data={"url": url, "score": score, "findings": findings},
        summary=f"Audit: {url[:50]} score={score:.0f}"
    )


def store_ranking_data(project_id: str, keywords: list,
                        engine: str = "gsc_monitor") -> str:
    return DataStore().record(
        result_type=ResultType.RANKING_DATA,
        project_id=project_id, engine_name=engine,
        data={"keywords": keywords},
        summary=f"{len(keywords)} keywords tracked"
    )


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel as PM
    from typing import Optional as Opt

    app = FastAPI(title="AnnaSEO DataStore", description="Live result storage for all engines")

    class RecordBody(PM):
        result_type:  str
        project_id:   str
        engine_name:  str
        seed:         str   = ""
        data:         dict  = {}
        summary:      str   = ""

    @app.post("/api/ds/record", tags=["DataStore"])
    def record_result(body: RecordBody):
        rid = DataStore().record(
            body.result_type, body.project_id, body.engine_name,
            body.data, body.seed, body.summary
        )
        return {"record_id": rid}

    @app.get("/api/ds/records", tags=["DataStore"])
    def get_records(project_id: str = None, result_type: str = None, limit: int = 50):
        return DataStore().get_records(project_id, result_type, limit)

    @app.get("/api/ds/items", tags=["DataStore"])
    def get_items(project_id: str = None, result_type: str = None,
                   item_type: str = None, label: str = None, limit: int = 100):
        return DataStore().get_items(project_id, result_type, item_type, label, limit)

    @app.get("/api/ds/stats", tags=["DataStore"])
    def stats(project_id: str = None):
        return DataStore().summary_stats(project_id)

except ImportError:
    pass


if __name__ == "__main__":
    import sys
    ds = DataStore()

    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        print("Storing demo results...")
        rid1 = ds.record(
            ResultType.KEYWORD_UNIVERSE, "proj_demo", "20phase_engine", "cinnamon",
            {"pillars": ["cinnamon benefits", "cinnamon tour", "cinnamon recipes",
                         "buy cinnamon online", "ceylon vs cassia"],
             "clusters": [{"name": "Cinnamon Health", "keywords": ["cinnamon diabetes"]}],
             "supporting_keywords": ["organic cinnamon", "cinnamon price"]},
            "5 pillars, 1 cluster"
        )
        rid2 = ds.record(
            ResultType.CONTENT_ARTICLE, "proj_demo", "content_engine", "cinnamon benefits",
            {"keyword": "cinnamon benefits", "title": "Cinnamon Health Benefits Guide",
             "body": "Cinnamon is a powerful spice with many health benefits...",
             "seo_score": 82, "eeat_score": 78, "geo_score": 71,
             "word_count": 2200, "readability_score": 74},
            "Article: Cinnamon Health Benefits"
        )
        stats = ds.summary_stats("proj_demo")
        print(f"Records: {stats['total_records']}")
        print(f"Items:   {stats['total_items']}")
        print(f"By type: {stats['by_result_type']}")
    else:
        print("AnnaSEO DataStore Engine")
        print("Usage: python annaseo_data_store.py demo")
        print("       Import DataStore in any engine and call ds.record()")

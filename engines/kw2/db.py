"""
kw2 db — schema initialization and helpers for 9 kw2_ tables.
"""
import os
import sqlite3
import json
import time
import uuid
import logging

log = logging.getLogger("kw2.db")


def _db_path() -> str:
    return os.getenv("ANNASEO_DB", "./annaseo.db")


def get_conn():
    """Return a new SQLite connection with row_factory."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_kw2_db(db_path: str | None = None):
    """Create all kw2_ tables if they don't exist."""
    path = db_path or _db_path()
    conn = sqlite3.connect(path)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_sessions (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        preferred_provider TEXT DEFAULT 'auto',
        phase1_done INTEGER DEFAULT 0,
        phase2_done INTEGER DEFAULT 0,
        phase3_done INTEGER DEFAULT 0,
        phase4_done INTEGER DEFAULT 0,
        phase5_done INTEGER DEFAULT 0,
        phase6_done INTEGER DEFAULT 0,
        phase7_done INTEGER DEFAULT 0,
        phase8_done INTEGER DEFAULT 0,
        phase9_done INTEGER DEFAULT 0,
        universe_count INTEGER DEFAULT 0,
        validated_count INTEGER DEFAULT 0,
        top100_count INTEGER DEFAULT 0,
        strategy_json TEXT,
        created_at TEXT,
        updated_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_business_profile (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL UNIQUE,
        domain TEXT,
        universe TEXT,
        pillars TEXT,
        product_catalog TEXT,
        modifiers TEXT,
        audience TEXT,
        intent_signals TEXT,
        geo_scope TEXT,
        business_type TEXT,
        negative_scope TEXT,
        confidence_score REAL DEFAULT 0.0,
        raw_ai_json TEXT,
        manual_input TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_universe_items (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        keyword TEXT NOT NULL,
        source TEXT,
        pillar TEXT,
        raw_score REAL DEFAULT 0.0,
        status TEXT DEFAULT 'raw',
        reject_reason TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_validated_keywords (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        keyword TEXT NOT NULL,
        pillar TEXT,
        cluster TEXT,
        ai_relevance REAL DEFAULT 0.0,
        intent TEXT,
        buyer_readiness REAL DEFAULT 0.0,
        commercial_score REAL DEFAULT 0.0,
        final_score REAL DEFAULT 0.0,
        source TEXT,
        mapped_page TEXT,
        ai_explanation TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_clusters (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        pillar TEXT,
        cluster_name TEXT,
        keyword_ids TEXT,
        top_keyword TEXT,
        avg_score REAL DEFAULT 0.0,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_tree_nodes (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        node_type TEXT,
        label TEXT,
        parent_id TEXT,
        keyword_id TEXT,
        mapped_page TEXT,
        score REAL DEFAULT 0.0,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_graph_edges (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        from_node TEXT NOT NULL,
        to_node TEXT NOT NULL,
        edge_type TEXT,
        weight REAL DEFAULT 1.0,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_internal_links (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        from_page TEXT NOT NULL,
        to_page TEXT NOT NULL,
        anchor_text TEXT,
        placement TEXT,
        intent TEXT,
        link_type TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_calendar (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        keyword TEXT,
        pillar TEXT,
        cluster TEXT,
        scheduled_date TEXT,
        status TEXT DEFAULT 'scheduled',
        article_type TEXT,
        score REAL DEFAULT 0.0,
        title TEXT,
        created_at TEXT
    )""")

    # Indexes for common queries
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_sessions_project ON kw2_sessions(project_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_universe_session ON kw2_universe_items(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_universe_project ON kw2_universe_items(project_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_validated_session ON kw2_validated_keywords(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_clusters_session ON kw2_clusters(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_tree_session ON kw2_tree_nodes(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_links_session ON kw2_internal_links(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_calendar_session ON kw2_calendar(session_id)")

    conn.commit()
    conn.close()
    log.info("kw2 tables initialized")


# ── Helper functions ─────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


def create_session(project_id: str, provider: str = "auto") -> str:
    """Create a new kw2 session, return session_id."""
    sid = _uid("kw2_")
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO kw2_sessions (id, project_id, preferred_provider, created_at, updated_at) VALUES (?,?,?,?,?)",
            (sid, project_id, provider, _now(), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return sid


def update_session(session_id: str, **kwargs):
    """Update session fields. kwargs keys must be valid column names."""
    if not kwargs:
        return
    kwargs["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [session_id]
    conn = get_conn()
    try:
        conn.execute(f"UPDATE kw2_sessions SET {cols} WHERE id=?", vals)
        conn.commit()
    finally:
        conn.close()


def get_session(session_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM kw2_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_latest_session(project_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM kw2_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_business_profile(project_id: str, profile: dict):
    """Upsert business profile. JSON-encodes list/dict fields."""
    pid = _uid("bp_")
    json_fields = ["pillars", "product_catalog", "modifiers", "audience",
                   "intent_signals", "negative_scope"]
    for f in json_fields:
        v = profile.get(f)
        if isinstance(v, (list, dict)):
            profile[f] = json.dumps(v)

    conn = get_conn()
    try:
        conn.execute("""INSERT OR REPLACE INTO kw2_business_profile
            (id, project_id, domain, universe, pillars, product_catalog, modifiers,
             audience, intent_signals, geo_scope, business_type, negative_scope,
             confidence_score, raw_ai_json, manual_input, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, project_id, profile.get("domain", ""),
             profile.get("universe", ""), profile.get("pillars", "[]"),
             profile.get("product_catalog", "[]"), profile.get("modifiers", "[]"),
             profile.get("audience", "[]"), profile.get("intent_signals", "[]"),
             profile.get("geo_scope", ""), profile.get("business_type", ""),
             profile.get("negative_scope", "[]"),
             profile.get("confidence_score", 0.0),
             json.dumps(profile.get("raw_ai_json")) if profile.get("raw_ai_json") else "",
             json.dumps(profile.get("manual_input")) if profile.get("manual_input") else "",
             _now()),
        )
        conn.commit()
    finally:
        conn.close()


def load_business_profile(project_id: str) -> dict | None:
    """Load business profile, JSON-decode list fields."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM kw2_business_profile WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for f in ["pillars", "product_catalog", "modifiers", "audience",
                   "intent_signals", "negative_scope"]:
            v = d.get(f, "")
            if isinstance(v, str) and v:
                try:
                    d[f] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    d[f] = []
        return d
    finally:
        conn.close()


def bulk_insert_universe(session_id: str, project_id: str, items: list[dict]):
    """Bulk insert keyword universe items."""
    if not items:
        return
    conn = get_conn()
    now = _now()
    try:
        conn.executemany(
            """INSERT INTO kw2_universe_items
               (id, session_id, project_id, keyword, source, pillar, raw_score, status, reject_reason, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [
                (_uid("u_"), session_id, project_id,
                 it["keyword"], it.get("source", ""), it.get("pillar", ""),
                 it.get("raw_score", 0.0), it.get("status", "raw"),
                 it.get("reject_reason", ""), now)
                for it in items
            ],
        )
        conn.commit()
    finally:
        conn.close()


def load_universe_items(session_id: str, status: str | None = None) -> list[dict]:
    conn = get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM kw2_universe_items WHERE session_id=? AND status=?",
                (session_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM kw2_universe_items WHERE session_id=?", (session_id,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_universe_status(item_ids: list[str], status: str, reject_reason: str = ""):
    """Batch update universe item status."""
    if not item_ids:
        return
    conn = get_conn()
    try:
        conn.executemany(
            "UPDATE kw2_universe_items SET status=?, reject_reason=? WHERE id=?",
            [(status, reject_reason, iid) for iid in item_ids],
        )
        conn.commit()
    finally:
        conn.close()


def bulk_insert_validated(session_id: str, project_id: str, items: list[dict]):
    """Bulk insert validated keywords."""
    if not items:
        return
    conn = get_conn()
    now = _now()
    try:
        conn.executemany(
            """INSERT INTO kw2_validated_keywords
               (id, session_id, project_id, keyword, pillar, cluster,
                ai_relevance, intent, buyer_readiness, commercial_score,
                final_score, source, mapped_page, ai_explanation, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (_uid("v_"), session_id, project_id,
                 it["keyword"], it.get("pillar", ""), it.get("cluster", ""),
                 it.get("ai_relevance", 0.0), it.get("intent", ""),
                 it.get("buyer_readiness", 0.0), it.get("commercial_score", 0.0),
                 it.get("final_score", 0.0), it.get("source", ""),
                 it.get("mapped_page", ""), it.get("ai_explanation", ""), now)
                for it in items
            ],
        )
        conn.commit()
    finally:
        conn.close()


def load_validated_keywords(session_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM kw2_validated_keywords WHERE session_id=? ORDER BY final_score DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

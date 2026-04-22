"""
GSC Engine — Database Layer
Tables: gsc_integration_settings, gsc_keywords_raw, gsc_keywords_processed,
        gsc_project_config, gsc_keyword_embeddings, gsc_keyword_clusters,
        gsc_keyword_graph, gsc_insights
"""
import sqlite3
import os
import json as _json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "annaseo.db")


def _conn():
    db = os.path.abspath(DB_PATH)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _add_column_if_missing(conn, table: str, column: str, coltype: str):
    """Safely add a column to an existing table (SQLite ALTER TABLE)."""
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_tables():
    """Create GSC tables if they don't exist."""
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS gsc_integration_settings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT UNIQUE NOT NULL,
                site_url    TEXT,
                access_token  TEXT,
                refresh_token TEXT,
                token_expiry  TEXT,
                status      TEXT DEFAULT 'disconnected',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS gsc_keywords_raw (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT NOT NULL,
                keyword     TEXT NOT NULL,
                clicks      INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                ctr         REAL DEFAULT 0,
                position    REAL DEFAULT 0,
                date_start  TEXT,
                date_end    TEXT,
                synced_at   TEXT DEFAULT (datetime('now')),
                UNIQUE(project_id, keyword, date_start, date_end)
            );

            CREATE INDEX IF NOT EXISTS idx_gsc_raw_project
                ON gsc_keywords_raw(project_id);

            CREATE TABLE IF NOT EXISTS gsc_keywords_processed (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id      TEXT NOT NULL,
                keyword         TEXT NOT NULL,
                pillar          TEXT,
                intent          TEXT,
                score           REAL DEFAULT 0,
                source_score    INTEGER DEFAULT 5,
                impression_score REAL DEFAULT 0,
                click_score     REAL DEFAULT 0,
                intent_boost    INTEGER DEFAULT 0,
                opportunity_score REAL DEFAULT 0,
                clicks          INTEGER DEFAULT 0,
                impressions     INTEGER DEFAULT 0,
                ctr             REAL DEFAULT 0,
                position        REAL DEFAULT 0,
                top100          INTEGER DEFAULT 0,
                processed_at    TEXT DEFAULT (datetime('now')),
                UNIQUE(project_id, keyword)
            );

            CREATE INDEX IF NOT EXISTS idx_gsc_proc_project
                ON gsc_keywords_processed(project_id);
            CREATE INDEX IF NOT EXISTS idx_gsc_proc_pillar
                ON gsc_keywords_processed(project_id, pillar);
            CREATE INDEX IF NOT EXISTS idx_gsc_proc_score
                ON gsc_keywords_processed(project_id, score DESC);

            CREATE TABLE IF NOT EXISTS gsc_project_config (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id               TEXT UNIQUE NOT NULL,
                business_summary         TEXT DEFAULT '',
                target_audience          TEXT DEFAULT '',
                goal                     TEXT DEFAULT 'sales',
                pillars                  TEXT DEFAULT '[]',
                purchase_intent_keywords TEXT DEFAULT '[]',
                supporting_angles        TEXT DEFAULT '[]',
                synonyms                 TEXT DEFAULT '{}',
                customer_language_examples TEXT DEFAULT '[]',
                source                   TEXT DEFAULT 'ai',
                generated_at             TEXT,
                created_at               TEXT DEFAULT (datetime('now')),
                updated_at               TEXT DEFAULT (datetime('now'))
            );

            -- Phase 2: Keyword Embeddings
            CREATE TABLE IF NOT EXISTS gsc_keyword_embeddings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT NOT NULL,
                keyword     TEXT NOT NULL,
                vector      BLOB NOT NULL,
                model       TEXT DEFAULT 'all-MiniLM-L6-v2',
                created_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(project_id, keyword)
            );
            CREATE INDEX IF NOT EXISTS idx_gsc_emb_project
                ON gsc_keyword_embeddings(project_id);

            -- Phase 2: Keyword Clusters
            CREATE TABLE IF NOT EXISTS gsc_keyword_clusters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT NOT NULL,
                cluster_id  INTEGER NOT NULL,
                cluster_name TEXT DEFAULT '',
                keyword     TEXT NOT NULL,
                pillar      TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(project_id, keyword)
            );
            CREATE INDEX IF NOT EXISTS idx_gsc_clust_project
                ON gsc_keyword_clusters(project_id);
            CREATE INDEX IF NOT EXISTS idx_gsc_clust_name
                ON gsc_keyword_clusters(project_id, cluster_name);

            -- Phase 2: Keyword Graph (edges)
            CREATE TABLE IF NOT EXISTS gsc_keyword_graph (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT NOT NULL,
                keyword_1   TEXT NOT NULL,
                keyword_2   TEXT NOT NULL,
                similarity  REAL DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(project_id, keyword_1, keyword_2)
            );
            CREATE INDEX IF NOT EXISTS idx_gsc_graph_project
                ON gsc_keyword_graph(project_id);
            CREATE INDEX IF NOT EXISTS idx_gsc_graph_kw1
                ON gsc_keyword_graph(project_id, keyword_1);

            -- Phase 2: Insights
            CREATE TABLE IF NOT EXISTS gsc_insights (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT NOT NULL,
                type        TEXT NOT NULL,
                data        TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_gsc_insights_project
                ON gsc_insights(project_id, type);
        """)
        # Phase 2: add columns to keywords_processed if missing
        _add_column_if_missing(c, "gsc_keywords_processed", "intent_confidence", "REAL DEFAULT 0")
        _add_column_if_missing(c, "gsc_keywords_processed", "cluster_name", "TEXT")
        _add_column_if_missing(c, "gsc_keywords_processed", "cluster_id", "INTEGER")
        _add_column_if_missing(c, "gsc_keywords_processed", "angle", "TEXT")

        # Phase 3: Intelligence Summary + Export/Tasks
        c.executescript("""
            CREATE TABLE IF NOT EXISTS gsc_intelligence_summary (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT UNIQUE NOT NULL,
                data        TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS gsc_tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT NOT NULL,
                keyword     TEXT,
                cluster     TEXT,
                task_type   TEXT NOT NULL,
                title       TEXT NOT NULL,
                description TEXT,
                status      TEXT DEFAULT 'pending',
                priority    INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_gsc_tasks_project
                ON gsc_tasks(project_id, status);

            CREATE TABLE IF NOT EXISTS gsc_exports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT NOT NULL,
                export_type TEXT NOT NULL,
                data        TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_gsc_exports_project
                ON gsc_exports(project_id);
        """)


# ─── Integration Settings ────────────────────────────────────────────────────

def get_integration(project_id: str) -> dict | None:
    init_tables()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM gsc_integration_settings WHERE project_id = ?",
            (project_id,)
        ).fetchone()
        return dict(row) if row else None


def upsert_integration(project_id: str, **kwargs):
    init_tables()
    existing = get_integration(project_id)
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    if existing:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [project_id]
        with _conn() as c:
            c.execute(
                f"UPDATE gsc_integration_settings SET {sets} WHERE project_id = ?",
                vals
            )
    else:
        kwargs["project_id"] = project_id
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" * len(kwargs))
        with _conn() as c:
            c.execute(
                f"INSERT INTO gsc_integration_settings ({cols}) VALUES ({placeholders})",
                list(kwargs.values())
            )


def set_integration_status(project_id: str, status: str):
    upsert_integration(project_id, status=status)


# ─── Raw Keywords ─────────────────────────────────────────────────────────────

def upsert_raw_keywords(project_id: str, rows: list[dict], date_start: str, date_end: str):
    """Bulk upsert raw GSC keyword rows."""
    init_tables()
    now = datetime.utcnow().isoformat()
    data = [
        (
            project_id,
            r["keys"][0] if isinstance(r.get("keys"), list) else r.get("keyword", ""),
            r.get("clicks", 0),
            r.get("impressions", 0),
            r.get("ctr", 0.0),
            r.get("position", 0.0),
            date_start,
            date_end,
            now,
        )
        for r in rows
    ]
    with _conn() as c:
        c.executemany(
            """INSERT INTO gsc_keywords_raw
                (project_id, keyword, clicks, impressions, ctr, position, date_start, date_end, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, keyword, date_start, date_end)
               DO UPDATE SET
                 clicks=excluded.clicks, impressions=excluded.impressions,
                 ctr=excluded.ctr, position=excluded.position, synced_at=excluded.synced_at
            """,
            data
        )
    return len(data)


def get_raw_keywords(project_id: str) -> list[dict]:
    init_tables()
    with _conn() as c:
        rows = c.execute(
            """SELECT keyword, MAX(clicks) as clicks, MAX(impressions) as impressions,
                      AVG(ctr) as ctr, AVG(position) as position
               FROM gsc_keywords_raw
               WHERE project_id = ?
               GROUP BY keyword
               ORDER BY impressions DESC""",
            (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def count_raw_keywords(project_id: str) -> int:
    init_tables()
    with _conn() as c:
        return c.execute(
            "SELECT COUNT(DISTINCT keyword) FROM gsc_keywords_raw WHERE project_id = ?",
            (project_id,)
        ).fetchone()[0]


# ─── Processed Keywords ───────────────────────────────────────────────────────

def upsert_processed_keywords(project_id: str, rows: list[dict]):
    """Bulk upsert processed/scored keywords."""
    init_tables()
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        for r in rows:
            c.execute(
                """INSERT INTO gsc_keywords_processed
                    (project_id, keyword, pillar, intent, score, source_score,
                     impression_score, click_score, intent_boost, opportunity_score,
                     clicks, impressions, ctr, position, top100, processed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(project_id, keyword) DO UPDATE SET
                     pillar=excluded.pillar, intent=excluded.intent, score=excluded.score,
                     source_score=excluded.source_score, impression_score=excluded.impression_score,
                     click_score=excluded.click_score, intent_boost=excluded.intent_boost,
                     opportunity_score=excluded.opportunity_score,
                     clicks=excluded.clicks, impressions=excluded.impressions,
                     ctr=excluded.ctr, position=excluded.position, top100=excluded.top100,
                     processed_at=excluded.processed_at
                """,
                (
                    project_id, r["keyword"], r.get("pillar"), r.get("intent"),
                    r.get("score", 0), r.get("source_score", 5),
                    r.get("impression_score", 0), r.get("click_score", 0),
                    r.get("intent_boost", 0), r.get("opportunity_score", 0),
                    r.get("clicks", 0), r.get("impressions", 0),
                    r.get("ctr", 0), r.get("position", 0),
                    1 if r.get("top100") else 0, now
                )
            )


def get_processed_keywords(project_id: str, pillar: str = None) -> list[dict]:
    init_tables()
    with _conn() as c:
        if pillar:
            rows = c.execute(
                """SELECT * FROM gsc_keywords_processed
                   WHERE project_id = ? AND pillar = ?
                   ORDER BY score DESC""",
                (project_id, pillar)
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT * FROM gsc_keywords_processed
                   WHERE project_id = ?
                   ORDER BY score DESC""",
                (project_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_top100(project_id: str) -> list[dict]:
    init_tables()
    with _conn() as c:
        rows = c.execute(
            """SELECT * FROM gsc_keywords_processed
               WHERE project_id = ? AND top100 = 1
               ORDER BY pillar, score DESC""",
            (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Project Config (AI Understanding) ──────────────────────────────────────

def get_project_config(project_id: str) -> dict | None:
    """Return stored AI project config dict or None."""
    init_tables()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM gsc_project_config WHERE project_id = ?",
            (project_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("pillars", "purchase_intent_keywords", "supporting_angles",
                    "customer_language_examples"):
            try:
                d[key] = _json.loads(d[key] or "[]")
            except (ValueError, TypeError):
                d[key] = []
        try:
            d["synonyms"] = _json.loads(d["synonyms"] or "{}")
        except (ValueError, TypeError):
            d["synonyms"] = {}
        return d


def upsert_project_config(project_id: str, config: dict):
    """Store or replace the AI project config for a project."""
    init_tables()
    now = datetime.utcnow().isoformat()
    row = {
        "project_id":                project_id,
        "business_summary":          str(config.get("business_summary", "")),
        "target_audience":           str(config.get("target_audience", "")),
        "goal":                      str(config.get("goal", "sales")),
        "pillars":                   _json.dumps(config.get("pillars") or []),
        "purchase_intent_keywords":  _json.dumps(config.get("purchase_intent_keywords") or []),
        "supporting_angles":         _json.dumps(config.get("supporting_angles") or []),
        "synonyms":                  _json.dumps(config.get("synonyms") or {}),
        "customer_language_examples":_json.dumps(config.get("customer_language_examples") or []),
        "source":                    str(config.get("source", "ai")),
        "generated_at":              str(config.get("generated_at", now)),
        "updated_at":                now,
    }
    with _conn() as c:
        c.execute(
            """INSERT INTO gsc_project_config
                (project_id, business_summary, target_audience, goal, pillars,
                 purchase_intent_keywords, supporting_angles, synonyms,
                 customer_language_examples, source, generated_at, updated_at)
               VALUES (:project_id, :business_summary, :target_audience, :goal, :pillars,
                 :purchase_intent_keywords, :supporting_angles, :synonyms,
                 :customer_language_examples, :source, :generated_at, :updated_at)
               ON CONFLICT(project_id) DO UPDATE SET
                 business_summary=excluded.business_summary,
                 target_audience=excluded.target_audience,
                 goal=excluded.goal,
                 pillars=excluded.pillars,
                 purchase_intent_keywords=excluded.purchase_intent_keywords,
                 supporting_angles=excluded.supporting_angles,
                 synonyms=excluded.synonyms,
                 customer_language_examples=excluded.customer_language_examples,
                 source=excluded.source,
                 generated_at=excluded.generated_at,
                 updated_at=excluded.updated_at
            """,
            row,
        )


def delete_project_config(project_id: str):
    init_tables()
    with _conn() as c:
        c.execute("DELETE FROM gsc_project_config WHERE project_id = ?", (project_id,))


def get_stats(project_id: str) -> dict:
    init_tables()
    with _conn() as c:
        raw_count = c.execute(
            "SELECT COUNT(*) FROM gsc_keywords_raw WHERE project_id = ?",
            (project_id,)
        ).fetchone()[0]
        proc_count = c.execute(
            "SELECT COUNT(*) FROM gsc_keywords_processed WHERE project_id = ?",
            (project_id,)
        ).fetchone()[0]
        top100_count = c.execute(
            "SELECT COUNT(*) FROM gsc_keywords_processed WHERE project_id = ? AND top100 = 1",
            (project_id,)
        ).fetchone()[0]
        pillars = c.execute(
            "SELECT DISTINCT pillar FROM gsc_keywords_processed WHERE project_id = ? AND pillar IS NOT NULL",
            (project_id,)
        ).fetchall()
        return {
            "raw_count": raw_count,
            "processed_count": proc_count,
            "top100_count": top100_count,
            "pillar_count": len(pillars),
        }


# ─── Phase 2: Embeddings ──────────────────────────────────────────────────────

def upsert_embeddings(project_id: str, rows: list[dict]):
    """Bulk upsert keyword embeddings. Each row: {keyword, vector(bytes), model}."""
    init_tables()
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        c.executemany(
            """INSERT INTO gsc_keyword_embeddings (project_id, keyword, vector, model, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(project_id, keyword) DO UPDATE SET
                 vector=excluded.vector, model=excluded.model, created_at=excluded.created_at""",
            [(project_id, r["keyword"], r["vector"], r.get("model", "all-MiniLM-L6-v2"), now)
             for r in rows]
        )


def get_embeddings(project_id: str) -> list[dict]:
    """Return all stored embeddings for the project."""
    init_tables()
    with _conn() as c:
        rows = c.execute(
            "SELECT keyword, vector, model FROM gsc_keyword_embeddings WHERE project_id = ?",
            (project_id,)
        ).fetchall()
        return [{"keyword": r[0], "vector": bytes(r[1]), "model": r[2]} for r in rows]


def get_embedded_keywords(project_id: str) -> set[str]:
    """Return set of keyword strings that already have embeddings."""
    init_tables()
    with _conn() as c:
        rows = c.execute(
            "SELECT keyword FROM gsc_keyword_embeddings WHERE project_id = ?",
            (project_id,)
        ).fetchall()
        return {r[0] for r in rows}


def count_embeddings(project_id: str) -> int:
    init_tables()
    with _conn() as c:
        return c.execute(
            "SELECT COUNT(*) FROM gsc_keyword_embeddings WHERE project_id = ?",
            (project_id,)
        ).fetchone()[0]


# ─── Phase 2: Clusters ────────────────────────────────────────────────────────

def upsert_clusters(project_id: str, rows: list[dict]):
    """Bulk upsert cluster assignments. Each row: {keyword, cluster_id, cluster_name, pillar}."""
    init_tables()
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        c.executemany(
            """INSERT INTO gsc_keyword_clusters (project_id, cluster_id, cluster_name, keyword, pillar, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, keyword) DO UPDATE SET
                 cluster_id=excluded.cluster_id, cluster_name=excluded.cluster_name,
                 pillar=excluded.pillar, created_at=excluded.created_at""",
            [(project_id, r["cluster_id"], r.get("cluster_name", ""), r["keyword"],
              r.get("pillar"), now) for r in rows]
        )


def get_clusters(project_id: str) -> dict:
    """Return clusters grouped: {cluster_name: [{keyword, pillar, cluster_id}]}."""
    init_tables()
    with _conn() as c:
        rows = c.execute(
            """SELECT cluster_id, cluster_name, keyword, pillar
               FROM gsc_keyword_clusters WHERE project_id = ?
               ORDER BY cluster_name, keyword""",
            (project_id,)
        ).fetchall()
        clusters: dict[str, list[dict]] = {}
        for r in rows:
            name = r[1] or f"cluster_{r[0]}"
            clusters.setdefault(name, []).append({
                "keyword": r[2], "pillar": r[3], "cluster_id": r[0],
            })
        return clusters


def clear_clusters(project_id: str):
    init_tables()
    with _conn() as c:
        c.execute("DELETE FROM gsc_keyword_clusters WHERE project_id = ?", (project_id,))


# ─── Phase 2: Keyword Graph ──────────────────────────────────────────────────

def upsert_graph_edges(project_id: str, edges: list[dict]):
    """Bulk upsert graph edges. Each edge: {keyword_1, keyword_2, similarity}."""
    init_tables()
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        c.executemany(
            """INSERT INTO gsc_keyword_graph (project_id, keyword_1, keyword_2, similarity, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(project_id, keyword_1, keyword_2) DO UPDATE SET
                 similarity=excluded.similarity, created_at=excluded.created_at""",
            [(project_id, e["keyword_1"], e["keyword_2"], e["similarity"], now) for e in edges]
        )


def get_graph(project_id: str, min_similarity: float = 0.0) -> dict:
    """Return graph as {nodes: [...], links: [...]} for UI rendering."""
    init_tables()
    with _conn() as c:
        edges = c.execute(
            """SELECT keyword_1, keyword_2, similarity FROM gsc_keyword_graph
               WHERE project_id = ? AND similarity >= ?
               ORDER BY similarity DESC""",
            (project_id, min_similarity)
        ).fetchall()

        node_set: set[str] = set()
        links = []
        for e in edges:
            node_set.add(e[0])
            node_set.add(e[1])
            links.append({"source": e[0], "target": e[1], "similarity": round(e[2], 3)})

        # Enrich nodes with pillar/intent from processed keywords
        nodes = []
        if node_set:
            placeholders = ",".join("?" * len(node_set))
            kw_data = c.execute(
                f"""SELECT keyword, pillar, intent, score, top100
                    FROM gsc_keywords_processed
                    WHERE project_id = ? AND keyword IN ({placeholders})""",
                [project_id] + list(node_set)
            ).fetchall()
            kw_map = {r[0]: dict(r) for r in kw_data}
            for n in node_set:
                info = kw_map.get(n, {})
                nodes.append({
                    "id": n, "group": info.get("pillar", "unknown"),
                    "intent": info.get("intent", ""), "score": info.get("score", 0),
                    "top100": bool(info.get("top100", 0)),
                })

        return {"nodes": nodes, "links": links}


def clear_graph(project_id: str):
    init_tables()
    with _conn() as c:
        c.execute("DELETE FROM gsc_keyword_graph WHERE project_id = ?", (project_id,))


def count_graph_edges(project_id: str) -> int:
    init_tables()
    with _conn() as c:
        return c.execute(
            "SELECT COUNT(*) FROM gsc_keyword_graph WHERE project_id = ?",
            (project_id,)
        ).fetchone()[0]


# ─── Phase 2: Insights ────────────────────────────────────────────────────────

def save_insights(project_id: str, insight_type: str, data: dict):
    """Save or replace insights by type."""
    init_tables()
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        c.execute("DELETE FROM gsc_insights WHERE project_id = ? AND type = ?",
                  (project_id, insight_type))
        c.execute(
            "INSERT INTO gsc_insights (project_id, type, data, created_at) VALUES (?, ?, ?, ?)",
            (project_id, insight_type, _json.dumps(data), now)
        )


def get_insights(project_id: str, insight_type: str = None) -> dict:
    """Return insights. If type given, return that type's data; else return all."""
    init_tables()
    with _conn() as c:
        if insight_type:
            row = c.execute(
                "SELECT data FROM gsc_insights WHERE project_id = ? AND type = ? ORDER BY created_at DESC LIMIT 1",
                (project_id, insight_type)
            ).fetchone()
            return _json.loads(row[0]) if row else {}
        else:
            rows = c.execute(
                "SELECT type, data, created_at FROM gsc_insights WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,)
            ).fetchall()
            result = {}
            for r in rows:
                if r[0] not in result:  # latest per type
                    result[r[0]] = _json.loads(r[1])
            return result


def update_processed_keywords_phase2(project_id: str, updates: list[dict]):
    """Batch-update Phase 2 columns on processed keywords.
    Each update: {keyword, intent_confidence, cluster_name, cluster_id, angle}."""
    init_tables()
    with _conn() as c:
        for u in updates:
            sets = []
            vals = []
            for col in ("intent_confidence", "cluster_name", "cluster_id", "angle"):
                if col in u:
                    sets.append(f"{col} = ?")
                    vals.append(u[col])
            if sets:
                vals.extend([project_id, u["keyword"]])
                c.execute(
                    f"UPDATE gsc_keywords_processed SET {', '.join(sets)} WHERE project_id = ? AND keyword = ?",
                    vals
                )


# ─── Phase 3: Intelligence Summary ───────────────────────────────────────────

def save_intelligence_summary(project_id: str, summary: dict):
    """Save or update the AI intelligence summary."""
    init_tables()
    with _conn() as c:
        existing = c.execute(
            "SELECT id FROM gsc_intelligence_summary WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        data_str = _json.dumps(summary, default=str)
        if existing:
            c.execute(
                "UPDATE gsc_intelligence_summary SET data = ?, updated_at = datetime('now') WHERE project_id = ?",
                (data_str, project_id),
            )
        else:
            c.execute(
                "INSERT INTO gsc_intelligence_summary (project_id, data) VALUES (?, ?)",
                (project_id, data_str),
            )


def get_intelligence_summary(project_id: str) -> dict | None:
    """Load the AI intelligence summary."""
    init_tables()
    with _conn() as c:
        row = c.execute(
            "SELECT data, updated_at FROM gsc_intelligence_summary WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if not row:
            return None
        result = _json.loads(row[0])
        result["_updated_at"] = row[1]
        return result


# ─── Phase 3: Tasks ──────────────────────────────────────────────────────────

def create_task(project_id: str, task: dict) -> int:
    """Create a task and return its id."""
    init_tables()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO gsc_tasks (project_id, keyword, cluster, task_type, title, description, priority) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, task.get("keyword"), task.get("cluster"), task["task_type"],
             task["title"], task.get("description", ""), task.get("priority", 0)),
        )
        return cur.lastrowid


def get_tasks(project_id: str, status: str = None) -> list[dict]:
    """Get tasks, optionally filtered by status."""
    init_tables()
    with _conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM gsc_tasks WHERE project_id = ? AND status = ? ORDER BY priority DESC, created_at DESC",
                (project_id, status),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM gsc_tasks WHERE project_id = ? ORDER BY priority DESC, created_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def update_task(project_id: str, task_id: int, updates: dict) -> bool:
    """Update a task's status/description."""
    init_tables()
    allowed = {"status", "title", "description", "priority"}
    sets = []
    vals = []
    for k, v in updates.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    if not sets:
        return False
    sets.append("updated_at = datetime('now')")
    vals.extend([project_id, task_id])
    with _conn() as c:
        c.execute(
            f"UPDATE gsc_tasks SET {', '.join(sets)} WHERE project_id = ? AND id = ?",
            vals,
        )
        return True


def delete_task(project_id: str, task_id: int):
    """Delete a task."""
    init_tables()
    with _conn() as c:
        c.execute("DELETE FROM gsc_tasks WHERE project_id = ? AND id = ?", (project_id, task_id))


# ─── Phase 3: Exports ────────────────────────────────────────────────────────

def save_export(project_id: str, export_type: str, data: dict) -> int:
    """Save an export record."""
    init_tables()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO gsc_exports (project_id, export_type, data) VALUES (?, ?, ?)",
            (project_id, export_type, _json.dumps(data, default=str)),
        )
        return cur.lastrowid


def get_export(project_id: str, export_id: int) -> dict | None:
    """Get a specific export."""
    init_tables()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM gsc_exports WHERE project_id = ? AND id = ?",
            (project_id, export_id),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["data"] = _json.loads(d["data"])
        return d

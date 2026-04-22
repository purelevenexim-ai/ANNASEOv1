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


def _deep_json_loads(value, max_depth: int = 12):
    data = value
    for _ in range(max_depth):
        if not isinstance(data, str):
            return data
        raw = data.strip()
        if not raw:
            return ""
        try:
            decoded = json.loads(raw)
        except Exception:
            return data
        if decoded == data:
            return data
        data = decoded
    return data


_tables_verified = False


def get_conn():
    """Return a new SQLite connection with row_factory."""
    global _tables_verified
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if not _tables_verified:
        # Lazy-init: ensure kw2 tables exist on first connection
        try:
            conn.execute("SELECT 1 FROM kw2_sessions LIMIT 1")
            _tables_verified = True
        except sqlite3.OperationalError:
            log.warning("kw2 tables missing — running init_kw2_db()")
            conn.close()
            init_kw2_db()
            conn = sqlite3.connect(_db_path())
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            _tables_verified = True
    return conn


def _normalize_mode(mode: str | None) -> str:
    m = (mode or "brand").strip().lower()
    if m not in {"brand", "expand", "review", "v2"}:
        log.warning("Unknown KW2 mode %r — defaulting to brand", mode)
        return "brand"
    return m


def _flow_for_mode(mode: str | None) -> list[str]:
    m = _normalize_mode(mode)
    if m == "v2":
        return ["UNDERSTAND", "EXPAND", "ORGANIZE", "APPLY"]
    if m == "expand":
        return ["SEARCH", "2", "3", "REVIEW", "4", "5", "6", "7", "8", "9"]
    if m == "review":
        return ["SEARCH"]
    return ["1", "BI", "2", "3", "REVIEW", "4", "5", "6", "7", "8", "9"]


def _decode_session_row(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    d = dict(row)
    d["mode"] = _normalize_mode(d.get("mode"))
    raw_flow = d.get("flow_json")
    flow = None
    if isinstance(raw_flow, str) and raw_flow.strip():
        try:
            flow = json.loads(raw_flow)
        except Exception:
            flow = None
    if not isinstance(flow, list) or not flow:
        flow = _flow_for_mode(d["mode"])

    if d["mode"] == "v2":
        expected = _flow_for_mode("v2")
        norm_flow = [str(x).upper() for x in flow]
        has_legacy_phase = any(x in {"1", "2", "3", "BI", "SEARCH", "REVIEW"} for x in norm_flow)
        if has_legacy_phase or not all(x in norm_flow for x in expected):
            flow = expected

    d["flow"] = flow
    if not d.get("entry_phase"):
        d["entry_phase"] = flow[0]
    if not d.get("current_phase"):
        d["current_phase"] = d["entry_phase"]

    if d["mode"] == "v2":
        allowed = {"UNDERSTAND", "EXPAND", "ORGANIZE", "APPLY"}

        entry = str(d.get("entry_phase") or "").upper()
        if entry not in allowed:
            d["entry_phase"] = "UNDERSTAND"

        current = str(d.get("current_phase") or "").upper()
        if current not in allowed:
            ps = d.get("phase_status")
            phase_status = {}
            if isinstance(ps, str) and ps.strip():
                try:
                    phase_status = json.loads(ps)
                except Exception:
                    phase_status = {}
            elif isinstance(ps, dict):
                phase_status = ps

            if phase_status.get("apply") == "done":
                d["current_phase"] = "APPLY"
            elif phase_status.get("organize") == "done":
                d["current_phase"] = "APPLY"
            elif phase_status.get("expand") == "done":
                d["current_phase"] = "ORGANIZE"
            elif phase_status.get("understand") == "done" or d.get("phase1_done"):
                d["current_phase"] = "EXPAND"
            else:
                d["current_phase"] = "UNDERSTAND"

    # Decode seed_keywords JSON
    raw_seeds = d.get("seed_keywords")
    if isinstance(raw_seeds, str) and raw_seeds.strip():
        try:
            d["seed_keywords"] = json.loads(raw_seeds)
        except Exception:
            d["seed_keywords"] = []
    elif not isinstance(raw_seeds, list):
        d["seed_keywords"] = []
    # Ensure name is a string
    d["name"] = d.get("name") or ""
    return d


def init_kw2_db(db_path: str | None = None):
    """Create all kw2_ tables if they don't exist."""
    path = db_path or _db_path()
    conn = sqlite3.connect(path)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_sessions (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        mode TEXT DEFAULT 'brand',
        flow_json TEXT DEFAULT '[]',
        entry_phase TEXT DEFAULT '1',
        current_phase TEXT DEFAULT '1',
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
        business_readme TEXT DEFAULT '',
        readme_updated_at TEXT DEFAULT '',
        session_graph TEXT DEFAULT '{}',
        created_at TEXT,
        updated_at TEXT
    )""")

    # Lightweight migrations for existing DBs where kw2_sessions already exists.
    existing_cols = {
        r["name"] if isinstance(r, sqlite3.Row) else r[1]
        for r in c.execute("PRAGMA table_info(kw2_sessions)").fetchall()
    }
    for col, ddl in [
        ("mode", "TEXT DEFAULT 'brand'"),
        ("flow_json", "TEXT DEFAULT '[]'"),
        ("entry_phase", "TEXT DEFAULT '1'"),
        ("current_phase", "TEXT DEFAULT '1'"),
        ("business_readme", "TEXT DEFAULT ''"),
        ("readme_updated_at", "TEXT DEFAULT ''"),
        ("session_graph", "TEXT DEFAULT '{}'"),
        ("name", "TEXT DEFAULT ''"),
        ("seed_keywords", "TEXT DEFAULT '[]'"),
        ("phase1_crawl_cache", "TEXT DEFAULT ''"),
    ]:
        if col not in existing_cols:
            c.execute(f"ALTER TABLE kw2_sessions ADD COLUMN {col} {ddl}")

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
        keyword_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
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

    # ── Business Intelligence (deep) tables ──────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_biz_intel (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        goals TEXT DEFAULT '[]',
        pricing_model TEXT DEFAULT 'mid-range',
        usps TEXT DEFAULT '[]',
        audience_segments TEXT DEFAULT '[]',
        website_crawl_done INTEGER DEFAULT 0,
        competitor_crawl_done INTEGER DEFAULT 0,
        strategy_done INTEGER DEFAULT 0,
        website_summary TEXT DEFAULT '',
        knowledge_summary TEXT DEFAULT '',
        seo_strategy TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_biz_pages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        url TEXT NOT NULL,
        page_type TEXT DEFAULT 'other',
        primary_topic TEXT DEFAULT '',
        search_intent TEXT DEFAULT 'informational',
        target_keyword TEXT DEFAULT '',
        keywords_extracted TEXT DEFAULT '[]',
        audience TEXT DEFAULT '',
        funnel_stage TEXT DEFAULT 'TOFU',
        ai_analysis TEXT DEFAULT '{}',
        content_snippet TEXT DEFAULT '',
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_biz_competitors (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        source TEXT DEFAULT 'user',
        target_audience TEXT DEFAULT '',
        business_model TEXT DEFAULT '',
        content_strategy TEXT DEFAULT '',
        tone TEXT DEFAULT '',
        strengths TEXT DEFAULT '[]',
        weaknesses TEXT DEFAULT '[]',
        missed_opportunities TEXT DEFAULT '[]',
        top_keywords TEXT DEFAULT '[]',
        pages_crawled INTEGER DEFAULT 0,
        crawl_done INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_biz_competitor_keywords (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        competitor_id TEXT NOT NULL,
        keyword TEXT NOT NULL,
        intent TEXT DEFAULT 'commercial',
        source_page_type TEXT DEFAULT 'unknown',
        confidence REAL DEFAULT 0.7,
        created_at TEXT
    )""")

    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_biz_intel_session ON kw2_biz_intel(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_biz_pages_session ON kw2_biz_pages(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_biz_comp_session ON kw2_biz_competitors(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_biz_comp_kw_session ON kw2_biz_competitor_keywords(session_id)")

    # ── v2 Keyword Brain tables ──────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_keywords (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        keyword TEXT NOT NULL,
        canonical TEXT NOT NULL,
        pillars TEXT DEFAULT '[]',
        role TEXT DEFAULT 'supporting',
        intent TEXT DEFAULT '',
        sources TEXT DEFAULT '[]',
        variants TEXT DEFAULT '[]',
        ai_relevance REAL DEFAULT 0.0,
        buyer_readiness REAL DEFAULT 0.0,
        commercial_score REAL DEFAULT 0.0,
        final_score REAL DEFAULT 0.0,
        cluster_id TEXT DEFAULT '',
        status TEXT DEFAULT 'candidate',
        reject_reason TEXT DEFAULT '',
        mapped_page TEXT DEFAULT '',
        metadata TEXT DEFAULT '{}',
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_keyword_relations (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        relation_type TEXT DEFAULT 'sibling',
        weight REAL DEFAULT 1.0,
        created_at TEXT
    )""")

    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_kw_session ON kw2_keywords(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_kw_canonical ON kw2_keywords(canonical)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_kw_status ON kw2_keywords(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_kw_cluster ON kw2_keywords(cluster_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_kw_session_status ON kw2_keywords(session_id, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_rel_session ON kw2_keyword_relations(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_rel_source ON kw2_keyword_relations(source_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_rel_target ON kw2_keyword_relations(target_id)")

    # Lightweight migration: add phase_status and v2 columns to existing tables
    sess_cols = {
        r["name"] if isinstance(r, sqlite3.Row) else r[1]
        for r in c.execute("PRAGMA table_info(kw2_sessions)").fetchall()
    }
    if "phase_status" not in sess_cols:
        c.execute("ALTER TABLE kw2_sessions ADD COLUMN phase_status TEXT DEFAULT '{}'")

    prof_cols = {
        r["name"] if isinstance(r, sqlite3.Row) else r[1]
        for r in c.execute("PRAGMA table_info(kw2_business_profile)").fetchall()
    }
    for col, ddl in [
        ("intent_distribution", "TEXT DEFAULT '{}'"),
        ("target_kw_count", "INTEGER DEFAULT 100"),
    ]:
        if col not in prof_cols:
            c.execute(f"ALTER TABLE kw2_business_profile ADD COLUMN {col} {ddl}")

    clust_cols = {
        r["name"] if isinstance(r, sqlite3.Row) else r[1]
        for r in c.execute("PRAGMA table_info(kw2_clusters)").fetchall()
    }
    for col, ddl in [
        ("intent_distribution", "TEXT DEFAULT '{}'"),
        ("keyword_count", "INTEGER DEFAULT 0"),
        ("status", "TEXT DEFAULT 'pending'"),
    ]:
        if col not in clust_cols:
            c.execute(f"ALTER TABLE kw2_clusters ADD COLUMN {col} {ddl}")

    # ── v2 Session columns migration ─────────────────────────────────────
    sess_cols2 = {
        r["name"] if isinstance(r, sqlite3.Row) else r[1]
        for r in c.execute("PRAGMA table_info(kw2_sessions)").fetchall()
    }
    for col, ddl in [
        ("geo_targets", "TEXT DEFAULT '[]'"),
        ("audience_targets", "TEXT DEFAULT '[]'"),
        ("intent_target", "TEXT DEFAULT ''"),
    ]:
        if col not in sess_cols2:
            c.execute(f"ALTER TABLE kw2_sessions ADD COLUMN {col} {ddl}")

    # ── Strategy v2 tables ───────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_strategy_versions (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        version_number INTEGER NOT NULL DEFAULT 1,
        strategy_json TEXT NOT NULL DEFAULT '{}',
        module_2a_json TEXT DEFAULT '{}',
        module_2b_json TEXT DEFAULT '{}',
        module_2d_json TEXT DEFAULT '{}',
        ai_provider TEXT DEFAULT 'auto',
        params_snapshot TEXT DEFAULT '{}',
        is_active INTEGER DEFAULT 1,
        notes TEXT DEFAULT '',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_sv_session ON kw2_strategy_versions(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_sv_active ON kw2_strategy_versions(session_id, is_active)")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_strategy_edits (
        id TEXT PRIMARY KEY,
        strategy_version_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        field_path TEXT NOT NULL,
        old_value TEXT DEFAULT '',
        new_value TEXT DEFAULT '',
        edited_by TEXT DEFAULT 'user',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_se_session ON kw2_strategy_edits(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_se_version ON kw2_strategy_edits(strategy_version_id)")

    # ── Question Intelligence table (phases 3–7) ──────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_intelligence_questions (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        module_code TEXT NOT NULL DEFAULT 'Q1',
        question TEXT NOT NULL,
        answer TEXT DEFAULT '',
        expansion_depth INTEGER DEFAULT 0,
        parent_question_id TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        intent TEXT DEFAULT '',
        funnel_stage TEXT DEFAULT '',
        audience_segment TEXT DEFAULT '',
        geo_relevance TEXT DEFAULT '',
        business_relevance REAL DEFAULT 0.0,
        content_type TEXT DEFAULT '',
        effort TEXT DEFAULT 'medium',
        content_cluster_id TEXT DEFAULT '',
        is_duplicate INTEGER DEFAULT 0,
        duplicate_of TEXT DEFAULT '',
        final_score REAL DEFAULT 0.0,
        score_breakdown TEXT DEFAULT '{}',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_iq_session ON kw2_intelligence_questions(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_iq_module ON kw2_intelligence_questions(session_id, module_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_iq_depth ON kw2_intelligence_questions(session_id, expansion_depth)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_iq_score ON kw2_intelligence_questions(session_id, final_score)")

    iq_cols = {
        r["name"] if isinstance(r, sqlite3.Row) else r[1]
        for r in c.execute("PRAGMA table_info(kw2_intelligence_questions)").fetchall()
    }
    for col, ddl in [
        ("data_source", "TEXT DEFAULT 'ai_inference'"),
        ("expansion_dimension_name", "TEXT DEFAULT ''"),
        ("expansion_dimension_value", "TEXT DEFAULT ''"),
    ]:
        if col not in iq_cols:
            c.execute(f"ALTER TABLE kw2_intelligence_questions ADD COLUMN {col} {ddl}")

    # ── Expansion config ──────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_expansion_config (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL UNIQUE,
        discovered_dimensions TEXT DEFAULT '{}',
        max_depth INTEGER DEFAULT 2,
        max_per_node INTEGER DEFAULT 10,
        dedup_threshold REAL DEFAULT 0.85,
        max_total INTEGER DEFAULT 10000,
        geo_levels TEXT DEFAULT '["country","region","city"]',
        expand_audience INTEGER DEFAULT 1,
        expand_use_cases INTEGER DEFAULT 1,
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_ec_session ON kw2_expansion_config(session_id)")

    # ── Content clusters (post-dedup grouping) ────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_content_clusters (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        cluster_name TEXT NOT NULL,
        description TEXT DEFAULT '',
        pillar TEXT DEFAULT '',
        intent_mix TEXT DEFAULT '{}',
        question_count INTEGER DEFAULT 0,
        avg_score REAL DEFAULT 0.0,
        status TEXT DEFAULT 'active',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_cc_session ON kw2_content_clusters(session_id)")

    # ── Scoring config (user-configurable weights) ────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_scoring_config (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL UNIQUE,
        weights TEXT NOT NULL DEFAULT '{}',
        version INTEGER DEFAULT 1,
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_sc_session ON kw2_scoring_config(session_id)")

    # ── Selected questions (Phase 8 output) ───────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_selected_questions (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        question_id TEXT NOT NULL,
        selection_rank INTEGER NOT NULL,
        selection_reason TEXT DEFAULT '',
        cluster_id TEXT DEFAULT '',
        content_title_id TEXT DEFAULT '',
        status TEXT DEFAULT 'selected',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_sq_session ON kw2_selected_questions(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_sq_rank ON kw2_selected_questions(session_id, selection_rank)")

    # ── Content titles (Phase 9 output) ───────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_content_titles (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        question_id TEXT NOT NULL DEFAULT '',
        selected_question_id TEXT DEFAULT '',
        title TEXT NOT NULL,
        slug TEXT DEFAULT '',
        primary_keyword TEXT DEFAULT '',
        meta_title TEXT DEFAULT '',
        content_type TEXT DEFAULT 'blog',
        word_count_target INTEGER DEFAULT 1500,
        pillar TEXT DEFAULT '',
        cluster_name TEXT DEFAULT '',
        intent TEXT DEFAULT '',
        funnel_stage TEXT DEFAULT 'TOFU',
        brief_json TEXT DEFAULT '{}',
        article_id TEXT DEFAULT '',
        status TEXT DEFAULT 'titled',
        scheduled_date TEXT DEFAULT '',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_ct_session ON kw2_content_titles(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_ct_status ON kw2_content_titles(session_id, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_ct_pillar ON kw2_content_titles(session_id, pillar)")

    # ── Content performance (Phase 11 feedback) ───────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_content_performance (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        content_title_id TEXT NOT NULL,
        article_id TEXT DEFAULT '',
        tracked_date TEXT NOT NULL,
        google_position REAL DEFAULT 0.0,
        organic_clicks INTEGER DEFAULT 0,
        impressions INTEGER DEFAULT 0,
        ctr REAL DEFAULT 0.0,
        conversions INTEGER DEFAULT 0,
        data_source TEXT DEFAULT 'manual',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_cp_session ON kw2_content_performance(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_cp_title ON kw2_content_performance(content_title_id)")

    # ── Prompt Studio tables (Phase 12) ───────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_prompts (
        id TEXT PRIMARY KEY,
        prompt_key TEXT NOT NULL UNIQUE,
        phase INTEGER NOT NULL DEFAULT 0,
        display_name TEXT NOT NULL,
        description TEXT DEFAULT '',
        template TEXT NOT NULL DEFAULT '',
        variables TEXT DEFAULT '[]',
        is_system INTEGER DEFAULT 0,
        version INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_p_key ON kw2_prompts(prompt_key)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_p_phase ON kw2_prompts(phase)")

    c.execute("""CREATE TABLE IF NOT EXISTS kw2_prompt_versions (
        id TEXT PRIMARY KEY,
        prompt_id TEXT NOT NULL,
        template TEXT NOT NULL DEFAULT '',
        version INTEGER NOT NULL,
        changed_by TEXT DEFAULT 'user',
        change_note TEXT DEFAULT '',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_pv_prompt ON kw2_prompt_versions(prompt_id)")

    # ── Learning Engine tables (Phase 12 — Pattern Memory & ROI) ──────────

    # Extracted performance patterns per cluster × title_type
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_patterns (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        cluster_name TEXT NOT NULL DEFAULT '',
        title_type TEXT NOT NULL DEFAULT 'other',
        sample_size INTEGER DEFAULT 0,
        avg_ctr REAL DEFAULT 0.0,
        avg_position REAL DEFAULT 0.0,
        avg_conversions REAL DEFAULT 0.0,
        avg_revenue REAL DEFAULT 0.0,
        avg_cost REAL DEFAULT 0.0,
        avg_time_on_page REAL DEFAULT 0.0,
        avg_bounce_rate REAL DEFAULT 0.0,
        confidence REAL DEFAULT 0.0,
        pattern_score REAL DEFAULT 0.0,
        best_length INTEGER DEFAULT 0,
        best_intent TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    )""")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_kw2_pat_uniq ON kw2_patterns(session_id, cluster_name, title_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_pat_session ON kw2_patterns(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_pat_score ON kw2_patterns(session_id, pattern_score DESC)")

    # Decision log: scale / kill / optimize per content piece
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_decisions_log (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        entity_type TEXT NOT NULL DEFAULT 'content',
        entity_id TEXT NOT NULL DEFAULT '',
        entity_label TEXT DEFAULT '',
        decision TEXT NOT NULL DEFAULT 'optimize',
        reason TEXT DEFAULT '',
        roi_score REAL DEFAULT 0.0,
        confidence REAL DEFAULT 0.0,
        overridden INTEGER DEFAULT 0,
        override_reason TEXT DEFAULT '',
        created_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_dl_session ON kw2_decisions_log(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_dl_decision ON kw2_decisions_log(session_id, decision)")

    # Strategy state: dynamic content mix + cluster priorities
    c.execute("""CREATE TABLE IF NOT EXISTS kw2_strategy_state (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL UNIQUE,
        project_id TEXT NOT NULL,
        content_mix TEXT DEFAULT '{}',
        cluster_priorities TEXT DEFAULT '[]',
        expansion_candidates TEXT DEFAULT '[]',
        roi_summary TEXT DEFAULT '{}',
        last_pattern_run TEXT DEFAULT '',
        last_decision_run TEXT DEFAULT '',
        version INTEGER DEFAULT 1,
        updated_at TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kw2_ss_session ON kw2_strategy_state(session_id)")

    # Migrate kw2_content_performance: add revenue/cost/bounce_rate/time_on_page columns
    existing_cp_cols = {
        r[1] for r in c.execute("PRAGMA table_info(kw2_content_performance)").fetchall()
    }
    _cp_migrations = [
        ("revenue", "REAL DEFAULT 0.0"),
        ("cost", "REAL DEFAULT 0.0"),
        ("bounce_rate", "REAL DEFAULT 0.0"),
        ("time_on_page_seconds", "INTEGER DEFAULT 0"),
    ]
    for col, ddl in _cp_migrations:
        if col not in existing_cp_cols:
            c.execute(f"ALTER TABLE kw2_content_performance ADD COLUMN {col} {ddl}")

    # Migrate kw2_validated_keywords: add spot_check_warning for Phase-5 quality advisory
    existing_vk_cols = {
        r[1] for r in c.execute("PRAGMA table_info(kw2_validated_keywords)").fetchall()
    }
    if "spot_check_warning" not in existing_vk_cols:
        c.execute("ALTER TABLE kw2_validated_keywords ADD COLUMN spot_check_warning TEXT")

    # Migrate kw2_calendar: add source column to track idea origin
    existing_cal_cols = {
        r[1] for r in c.execute("PRAGMA table_info(kw2_calendar)").fetchall()
    }
    if "source" not in existing_cal_cols:
        c.execute("ALTER TABLE kw2_calendar ADD COLUMN source TEXT DEFAULT 'keyword'")

    conn.close()
    log.info("kw2 tables initialized (v2 brain tables included)")

    # Separate connection for ai_usage table (avoids locking issues on init)
    conn2 = sqlite3.connect(_db_path())
    conn2.execute("PRAGMA journal_mode=WAL")
    conn2.execute("""CREATE TABLE IF NOT EXISTS kw2_ai_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        task TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT DEFAULT '',
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cost_usd REAL DEFAULT 0,
        latency_ms INTEGER DEFAULT 0,
        prompt_chars INTEGER DEFAULT 0,
        response_chars INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn2.execute("CREATE INDEX IF NOT EXISTS idx_kw2_ai_usage_session ON kw2_ai_usage(session_id)")
    conn2.execute("CREATE INDEX IF NOT EXISTS idx_kw2_ai_usage_project ON kw2_ai_usage(project_id)")
    conn2.commit()
    conn2.close()


# ── Helper functions ─────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


def create_session(project_id: str, provider: str = "auto", mode: str = "brand",
                   name: str = "", seed_keywords: list[str] | None = None) -> str:
    """Create a new kw2 session, return session_id."""
    sid = _uid("kw2_")
    mode_n = _normalize_mode(mode)
    flow = _flow_for_mode(mode_n)
    entry = flow[0]
    seeds_json = json.dumps(seed_keywords or [])
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO kw2_sessions
               (id, project_id, mode, flow_json, entry_phase, current_phase,
                preferred_provider, name, seed_keywords, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, project_id, mode_n, json.dumps(flow), entry, entry,
             provider, name or "", seeds_json, _now(), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return sid


# Allowlist of columns that may be updated via update_session
_SESSION_COLS = {
    "name", "mode", "current_phase", "entry_phase", "flow_json",
    "phase_status", "session_graph", "business_readme", "readme_updated_at",
    "preferred_provider", "seed_keywords", "phase1_crawl_cache",
    "phase1_done", "phase2_done", "phase3_done", "phase4_done", "phase5_done",
    "phase6_done", "phase7_done", "phase8_done", "phase9_done",
    "universe_count", "validated_count", "top100_count", "strategy_json",
    "updated_at",
    # v2 columns
    "geo_targets", "audience_targets", "intent_target",
}


def update_session(session_id: str, **kwargs):
    """Update session fields. kwargs keys must be valid column names."""
    if not kwargs:
        return
    bad = set(kwargs) - _SESSION_COLS
    if bad:
        raise ValueError(f"Invalid session columns: {bad}")
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
        return _decode_session_row(row)
    finally:
        conn.close()


def get_latest_session(project_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM kw2_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return _decode_session_row(row)
    finally:
        conn.close()


def list_sessions(project_id: str) -> list[dict]:
    """Return all kw2 sessions for a project, newest first, with keyword counts."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM kw2_universe_items WHERE session_id=s.id) AS universe_total,
                      (SELECT COUNT(*) FROM kw2_validated_keywords WHERE session_id=s.id) AS validated_total
               FROM kw2_sessions s
               WHERE s.project_id=?
               ORDER BY s.created_at DESC""",
            (project_id,),
        ).fetchall()
        results = []
        for row in rows:
            d = _decode_session_row(row)
            if d:
                d["universe_total"] = row["universe_total"] if isinstance(row, sqlite3.Row) else 0
                d["validated_total"] = row["validated_total"] if isinstance(row, sqlite3.Row) else 0
                results.append(d)
        return results
    finally:
        conn.close()


def delete_session(session_id: str) -> None:
    """Permanently delete a session and all related data."""
    # All child tables use session_id FK; kw2_sessions PK is `id`
    child_tables = [
        "kw2_biz_competitor_keywords",
        "kw2_biz_competitors",
        "kw2_biz_pages",
        "kw2_biz_intel",
        "kw2_calendar",
        "kw2_internal_links",
        "kw2_graph_edges",
        "kw2_tree_nodes",
        "kw2_clusters",
        "kw2_validated_keywords",
        "kw2_universe_items",
        "kw2_keyword_relations",
        "kw2_keywords",
    ]
    conn = get_conn()
    try:
        for table in child_tables:
            conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM kw2_sessions WHERE id=?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def save_session_graph(session_id: str, graph_json: str) -> None:
    """Persist the SessionGraph JSON blob."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kw2_sessions SET session_graph=?, updated_at=? WHERE id=?",
            (graph_json, _now(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def load_session_graph(session_id: str) -> str | None:
    """Load the raw SessionGraph JSON blob."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT session_graph FROM kw2_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if row:
            val = row[0] if not isinstance(row, dict) else row.get("session_graph")
            return val or "{}"
        return None
    finally:
        conn.close()


def save_business_profile(project_id: str, profile: dict):
    """Upsert business profile. JSON-encodes list/dict fields.
    NOTE: does NOT mutate the caller's dict — works on a shallow copy."""
    pid = _uid("bp_")
    json_fields = ["pillars", "product_catalog", "modifiers", "audience",
                   "intent_signals", "negative_scope"]
    # Work on a copy so the caller's dict is never mutated
    row = dict(profile)
    for f in json_fields:
        v = row.get(f)
        if isinstance(v, (list, dict)):
            row[f] = json.dumps(v)

    conn = get_conn()
    try:
        conn.execute("""INSERT OR REPLACE INTO kw2_business_profile
            (id, project_id, domain, universe, pillars, product_catalog, modifiers,
             audience, intent_signals, geo_scope, business_type, negative_scope,
             confidence_score, raw_ai_json, manual_input, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, project_id, row.get("domain", ""),
             row.get("universe", ""), row.get("pillars", "[]"),
             row.get("product_catalog", "[]"), row.get("modifiers", "[]"),
             row.get("audience", "[]"), row.get("intent_signals", "[]"),
             row.get("geo_scope", ""), row.get("business_type", ""),
             row.get("negative_scope", "[]"),
             row.get("confidence_score", 0.0),
             json.dumps(row.get("raw_ai_json")) if row.get("raw_ai_json") else "",
             json.dumps(row.get("manual_input")) if row.get("manual_input") else "",
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
            decoded = _deep_json_loads(d.get(f, ""))
            d[f] = decoded if isinstance(decoded, list) else []
        for f in ["raw_ai_json", "manual_input"]:
            decoded = _deep_json_loads(d.get(f, ""))
            d[f] = decoded if isinstance(decoded, (dict, list)) else {}
        # Restore pass-through fields from manual_input (not stored as columns)
        mi = d.get("manual_input") or {}
        if isinstance(mi, dict):
            for f in ["usp", "business_locations", "target_locations",
                       "languages", "cultural_context", "customer_reviews"]:
                if f not in d or not d[f]:
                    v = mi.get(f)
                    if v:
                        d[f] = v
        return d
    finally:
        conn.close()


def save_phase1_crawl_cache(session_id: str, cache: dict):
    """Persist Phase 1 crawl intermediate data so an AI-step retry skips re-crawling."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kw2_sessions SET phase1_crawl_cache=?, updated_at=? WHERE id=?",
            (json.dumps(cache), _now(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def load_phase1_crawl_cache(session_id: str) -> dict | None:
    """Load Phase 1 cached crawl data. Returns None if not set."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT phase1_crawl_cache FROM kw2_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not row:
            return None
        raw = row[0] if isinstance(row, tuple) else row["phase1_crawl_cache"]
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None
    finally:
        conn.close()


def clear_universe(session_id: str):
    """Delete all universe items for a session (used when re-running Phase 2 fresh)."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM kw2_universe_items WHERE session_id=?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def get_universe_sources(session_id: str) -> dict:
    """Return a dict of source → count for items already in the DB.
    Used by generate_stream to skip already-checkpointed layers.
    Per-pillar sources use the key 'suggest_{pillar}' and 'ai_{pillar}'.
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT source, pillar, COUNT(*) as cnt FROM kw2_universe_items WHERE session_id=? GROUP BY source, pillar",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    result: dict = {}
    for row in rows:
        src, pillar, cnt = row["source"], row["pillar"], row["cnt"]
        if src in ("suggest",):
            key = f"suggest_{pillar}" if pillar else "suggest"
        elif src in ("ai_expand",):
            key = f"ai_{pillar}" if pillar else "ai_expand"
        else:
            key = src
        result[key] = result.get(key, 0) + cnt
    return result


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


def load_universe_items(
    session_id: str,
    status: str | None = None,
    source_filter: str | None = None,
) -> list[dict]:
    conn = get_conn()
    try:
        query = "SELECT * FROM kw2_universe_items WHERE session_id=?"
        params: list = [session_id]
        if status:
            query += " AND status=?"
            params.append(status)
        if source_filter:
            query += " AND source=?"
            params.append(source_filter)
        rows = conn.execute(query, params).fetchall()
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


# ── Business Intelligence DB helpers ─────────────────────────────────────────

def upsert_biz_intel(session_id: str, project_id: str, data: dict) -> None:
    """Create or update the biz_intel record for a session."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM kw2_biz_intel WHERE session_id=?", (session_id,)).fetchone()
        now = _now()
        json_fields = ["goals", "usps", "audience_segments"]
        for f in json_fields:
            v = data.get(f)
            if isinstance(v, (list, dict)):
                data[f] = json.dumps(v)
        if row:
            sets = ", ".join(f"{k}=?" for k in data if k not in ("id", "session_id", "project_id", "created_at"))
            vals = [data[k] for k in data if k not in ("id", "session_id", "project_id", "created_at")]
            conn.execute(
                f"UPDATE kw2_biz_intel SET {sets}, updated_at=? WHERE session_id=?",
                vals + [now, session_id],
            )
        else:
            rid = _uid("bi_")
            conn.execute(
                """INSERT INTO kw2_biz_intel
                   (id, session_id, project_id, goals, pricing_model, usps, audience_segments,
                    website_crawl_done, competitor_crawl_done, strategy_done,
                    website_summary, knowledge_summary, seo_strategy, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, session_id, project_id,
                 data.get("goals", "[]"), data.get("pricing_model", "mid-range"),
                 data.get("usps", "[]"), data.get("audience_segments", "[]"),
                 data.get("website_crawl_done", 0), data.get("competitor_crawl_done", 0),
                 data.get("strategy_done", 0),
                 data.get("website_summary", ""), data.get("knowledge_summary", ""),
                 data.get("seo_strategy", ""), now, now),
            )
        conn.commit()
    finally:
        conn.close()


def get_biz_intel(session_id: str) -> dict | None:
    """Load biz_intel record for a session."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM kw2_biz_intel WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        for f in ["goals", "usps", "audience_segments"]:
            v = d.get(f, "")
            if isinstance(v, str) and v:
                try:
                    d[f] = json.loads(v)
                except Exception:
                    d[f] = []
        return d
    finally:
        conn.close()


def add_biz_page(session_id: str, project_id: str, page: dict) -> str:
    """Insert a classified page record."""
    pid = _uid("bp_")
    conn = get_conn()
    try:
        kw = page.get("keywords_extracted", [])
        if isinstance(kw, list):
            kw = json.dumps(kw)
        analysis = page.get("ai_analysis", {})
        if isinstance(analysis, dict):
            analysis = json.dumps(analysis)
        conn.execute(
            """INSERT OR IGNORE INTO kw2_biz_pages
               (id, session_id, project_id, url, page_type, primary_topic, search_intent,
                target_keyword, keywords_extracted, audience, funnel_stage, ai_analysis,
                content_snippet, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, session_id, project_id,
             page.get("url", ""), page.get("page_type", "other"),
             page.get("primary_topic", ""), page.get("search_intent", "informational"),
             page.get("target_keyword", ""), kw,
             page.get("audience", ""), page.get("funnel_stage", "TOFU"),
             analysis, page.get("content_snippet", "")[:800], _now()),
        )
        conn.commit()
        return pid
    finally:
        conn.close()


def get_biz_pages(session_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM kw2_biz_pages WHERE session_id=? ORDER BY page_type, created_at",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for f in ["keywords_extracted", "ai_analysis"]:
                v = d.get(f, "")
                if isinstance(v, str) and v:
                    try:
                        d[f] = json.loads(v)
                    except Exception:
                        d[f] = [] if f == "keywords_extracted" else {}
            result.append(d)
        return result
    finally:
        conn.close()


def add_biz_competitor(session_id: str, project_id: str, domain: str, source: str = "user") -> str:
    """Add a competitor for this session. Returns competitor_id."""
    cid = _uid("bc_")
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM kw2_biz_competitors WHERE session_id=? AND domain=?",
            (session_id, domain),
        ).fetchone()
        if existing:
            return existing["id"]
        conn.execute(
            """INSERT INTO kw2_biz_competitors
               (id, session_id, project_id, domain, source, created_at)
               VALUES (?,?,?,?,?,?)""",
            (cid, session_id, project_id, domain, source, _now()),
        )
        conn.commit()
        return cid
    finally:
        conn.close()


def update_biz_competitor(competitor_id: str, data: dict) -> None:
    conn = get_conn()
    try:
        json_fields = ["strengths", "weaknesses", "missed_opportunities", "top_keywords"]
        for f in json_fields:
            v = data.get(f)
            if isinstance(v, (list, dict)):
                data[f] = json.dumps(v)
        sets = ", ".join(f"{k}=?" for k in data)
        vals = list(data.values())
        conn.execute(f"UPDATE kw2_biz_competitors SET {sets} WHERE id=?", vals + [competitor_id])
        conn.commit()
    finally:
        conn.close()


def get_biz_competitors(session_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM kw2_biz_competitors WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for f in ["strengths", "weaknesses", "missed_opportunities", "top_keywords"]:
                v = d.get(f, "")
                if isinstance(v, str) and v:
                    try:
                        d[f] = json.loads(v)
                    except Exception:
                        d[f] = []
            result.append(d)
        return result
    finally:
        conn.close()


def add_biz_competitor_keywords(session_id: str, competitor_id: str, keywords: list[dict]) -> int:
    """Bulk insert competitor keywords. Returns count inserted."""
    if not keywords:
        return 0
    conn = get_conn()
    now = _now()
    try:
        conn.executemany(
            """INSERT OR IGNORE INTO kw2_biz_competitor_keywords
               (id, session_id, competitor_id, keyword, intent, source_page_type, confidence, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            [(_uid("bck_"), session_id, competitor_id,
              kw.get("keyword", ""), kw.get("intent", "commercial"),
              kw.get("source_page_type", "unknown"), float(kw.get("confidence", 0.7)), now)
             for kw in keywords if kw.get("keyword")],
        )
        conn.commit()
        return len(keywords)
    finally:
        conn.close()


def get_biz_competitor_keywords(session_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM kw2_biz_competitor_keywords WHERE session_id=? ORDER BY confidence DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── v2 Keyword Brain helpers ─────────────────────────────────────────────────

def bulk_insert_keywords(session_id: str, project_id: str, items: list[dict]) -> int:
    """Bulk insert into kw2_keywords. Returns count inserted."""
    if not items:
        return 0
    conn = get_conn()
    now = _now()
    try:
        conn.executemany(
            """INSERT INTO kw2_keywords
               (id, session_id, project_id, keyword, canonical, pillars, role,
                intent, sources, variants, ai_relevance, buyer_readiness,
                commercial_score, final_score, cluster_id, status, reject_reason,
                mapped_page, metadata, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (_uid("kw_"), session_id, project_id,
                 it["keyword"], it["canonical"],
                 json.dumps(it.get("pillars", [])),
                 it.get("role", "supporting"),
                 it.get("intent", ""),
                 json.dumps(it.get("sources", [])),
                 json.dumps(it.get("variants", [])),
                 float(it.get("ai_relevance", 0.0)),
                 float(it.get("buyer_readiness", 0.0)),
                 float(it.get("commercial_score", 0.0)),
                 float(it.get("final_score", 0.0)),
                 it.get("cluster_id", ""),
                 it.get("status", "candidate"),
                 it.get("reject_reason", ""),
                 it.get("mapped_page", ""),
                 json.dumps(it.get("metadata", {})),
                 now)
                for it in items
            ],
        )
        conn.commit()
        return len(items)
    finally:
        conn.close()


def load_keywords(session_id: str, status: str | None = None,
                  pillar: str | None = None) -> list[dict]:
    """Load keywords with optional status/pillar filter. JSON-decodes list fields."""
    conn = get_conn()
    try:
        query = "SELECT * FROM kw2_keywords WHERE session_id=?"
        params: list = [session_id]
        if status:
            query += " AND status=?"
            params.append(status)
        if pillar:
            # pillars is a JSON array; use LIKE for SQLite JSON query
            query += " AND pillars LIKE ?"
            params.append(f'%"{pillar}"%')
        query += " ORDER BY final_score DESC"
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for f in ["pillars", "sources", "variants"]:
                v = d.get(f, "[]")
                if isinstance(v, str):
                    try:
                        d[f] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        d[f] = []
            md = d.get("metadata", "{}")
            if isinstance(md, str):
                try:
                    d["metadata"] = json.loads(md)
                except (json.JSONDecodeError, TypeError):
                    d["metadata"] = {}
            result.append(d)
        return result
    finally:
        conn.close()


def update_keyword(keyword_id: str, **kwargs) -> None:
    """Update a single keyword row. JSON-encodes list/dict fields."""
    if not kwargs:
        return
    json_fields = {"pillars", "sources", "variants", "metadata"}
    for k in json_fields:
        if k in kwargs and isinstance(kwargs[k], (list, dict)):
            kwargs[k] = json.dumps(kwargs[k])
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [keyword_id]
    conn = get_conn()
    try:
        conn.execute(f"UPDATE kw2_keywords SET {cols} WHERE id=?", vals)
        conn.commit()
    finally:
        conn.close()


def bulk_update_keyword_status(keyword_ids: list[str], status: str,
                               reject_reason: str = "") -> None:
    """Batch update keyword status."""
    if not keyword_ids:
        return
    conn = get_conn()
    try:
        conn.executemany(
            "UPDATE kw2_keywords SET status=?, reject_reason=? WHERE id=?",
            [(status, reject_reason, kid) for kid in keyword_ids],
        )
        conn.commit()
    finally:
        conn.close()


def get_keyword_by_canonical(session_id: str, canonical: str) -> dict | None:
    """Look up a keyword by canonical form (for dedup during insertion)."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM kw2_keywords WHERE session_id=? AND canonical=? LIMIT 1",
            (session_id, canonical),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for f in ["pillars", "sources", "variants"]:
            v = d.get(f, "[]")
            if isinstance(v, str):
                try:
                    d[f] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    d[f] = []
        return d
    finally:
        conn.close()


def count_keywords(session_id: str, status: str | None = None,
                   pillar: str | None = None) -> int:
    """Count keywords with optional filters."""
    conn = get_conn()
    try:
        query = "SELECT COUNT(*) FROM kw2_keywords WHERE session_id=?"
        params: list = [session_id]
        if status:
            query += " AND status=?"
            params.append(status)
        if pillar:
            query += " AND pillars LIKE ?"
            params.append(f'%"{pillar}"%')
        row = conn.execute(query, params).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def bulk_insert_relations(session_id: str, relations: list[dict]) -> int:
    """Bulk insert keyword relations. Returns count inserted."""
    if not relations:
        return 0
    conn = get_conn()
    now = _now()
    try:
        conn.executemany(
            """INSERT INTO kw2_keyword_relations
               (id, session_id, source_id, target_id, relation_type, weight, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            [
                (_uid("rel_"), session_id,
                 r["source_id"], r["target_id"],
                 r.get("relation_type", "sibling"),
                 float(r.get("weight", 1.0)), now)
                for r in relations
            ],
        )
        conn.commit()
        return len(relations)
    finally:
        conn.close()


def load_relations(session_id: str, relation_type: str | None = None) -> list[dict]:
    """Load keyword relations with optional type filter."""
    conn = get_conn()
    try:
        query = "SELECT * FROM kw2_keyword_relations WHERE session_id=?"
        params: list = [session_id]
        if relation_type:
            query += " AND relation_type=?"
            params.append(relation_type)
        query += " ORDER BY weight DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_relations(session_id: str) -> int:
    """Delete all relations for a session (before rebuild)."""
    conn = get_conn()
    try:
        c = conn.execute(
            "DELETE FROM kw2_keyword_relations WHERE session_id=?",
            (session_id,),
        )
        conn.commit()
        return c.rowcount
    finally:
        conn.close()


def get_phase_status(session_id: str) -> dict:
    """Get the v2 phase_status JSON from session."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT phase_status FROM kw2_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if not row:
            return {}
        raw = row[0] if not isinstance(row, dict) else row.get("phase_status", "{}")
        if isinstance(raw, str) and raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    finally:
        conn.close()


def set_phase_status(session_id: str, phase: str, status: str) -> None:
    """Update a single phase in the phase_status JSON (atomic read-modify-write)."""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT phase_status FROM kw2_sessions WHERE id=?", (session_id,)
        ).fetchone()
        raw = row[0] if row else "{}"
        try:
            current = json.loads(raw) if isinstance(raw, str) and raw else {}
        except (json.JSONDecodeError, TypeError):
            current = {}
        current[phase] = status
        conn.execute(
            "UPDATE kw2_sessions SET phase_status=?, updated_at=? WHERE id=?",
            (json.dumps(current), _now(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── AI Usage Tracking ─────────────────────────────────────────────────────────

def log_ai_usage(session_id: str, project_id: str, task: str, provider: str,
                 model: str = "", input_tokens: int = 0, output_tokens: int = 0,
                 cost_usd: float = 0.0, latency_ms: int = 0,
                 prompt_chars: int = 0, response_chars: int = 0) -> None:
    """Record a single kw2 AI call to kw2_ai_usage."""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO kw2_ai_usage
               (session_id, project_id, task, provider, model,
                input_tokens, output_tokens, cost_usd, latency_ms,
                prompt_chars, response_chars, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, project_id, task, provider, model,
             input_tokens, output_tokens, round(cost_usd, 8), latency_ms,
             prompt_chars, response_chars, _now()),
        )
        conn.commit()
    except Exception as e:
        log.warning(f"[kw2_ai_usage] log failed: {e}")
    finally:
        conn.close()


def get_ai_usage(session_id: str) -> list[dict]:
    """Return all AI usage records for a session, newest first."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM kw2_ai_usage WHERE session_id=? ORDER BY id DESC LIMIT 200",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_project_ai_usage_summary(project_id: str) -> dict:
    """Aggregate AI usage stats for a project."""
    conn = get_conn()
    try:
        totals = conn.execute(
            """SELECT COUNT(*) as calls,
                      SUM(input_tokens) as input_tok,
                      SUM(output_tokens) as output_tok,
                      SUM(cost_usd) as total_cost,
                      SUM(latency_ms) as total_latency_ms
               FROM kw2_ai_usage WHERE project_id=?""",
            (project_id,),
        ).fetchone()
        by_provider = conn.execute(
            """SELECT provider, COUNT(*) as calls,
                      SUM(input_tokens)+SUM(output_tokens) as tokens,
                      SUM(cost_usd) as cost
               FROM kw2_ai_usage WHERE project_id=?
               GROUP BY provider ORDER BY cost DESC""",
            (project_id,),
        ).fetchall()
        by_task = conn.execute(
            """SELECT task, COUNT(*) as calls,
                      SUM(input_tokens)+SUM(output_tokens) as tokens,
                      SUM(cost_usd) as cost
               FROM kw2_ai_usage WHERE project_id=?
               GROUP BY task ORDER BY cost DESC""",
            (project_id,),
        ).fetchall()
        return {
            "calls": totals["calls"] or 0,
            "input_tokens": totals["input_tok"] or 0,
            "output_tokens": totals["output_tok"] or 0,
            "total_cost_usd": round(totals["total_cost"] or 0, 6),
            "avg_latency_ms": round((totals["total_latency_ms"] or 0) / max(1, totals["calls"] or 1)),
            "by_provider": [dict(r) for r in by_provider],
            "by_task": [dict(r) for r in by_task],
        }
    finally:
        conn.close()

"""Full schema — all 35+ tables from DATA_MODELS.md

Revision ID: 20260401_001
Revises:
Create Date: 2026-04-01
"""
from alembic import op

revision = "20260401_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    PRAGMA journal_mode=WAL;

    -- ── Core project tables ───────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS users(
        user_id    TEXT PRIMARY KEY,
        email      TEXT UNIQUE NOT NULL,
        name       TEXT DEFAULT '',
        role       TEXT DEFAULT 'user',
        pw_hash    TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS user_projects(
        user_id    TEXT,
        project_id TEXT,
        role       TEXT DEFAULT 'owner',
        PRIMARY KEY(user_id, project_id)
    );

    CREATE TABLE IF NOT EXISTS projects(
        project_id      TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        industry        TEXT NOT NULL,
        description     TEXT DEFAULT '',
        seed_keywords   TEXT DEFAULT '[]',
        wp_url          TEXT DEFAULT '',
        wp_user         TEXT DEFAULT '',
        wp_pass_enc     TEXT DEFAULT '',
        shopify_store   TEXT DEFAULT '',
        shopify_token_enc TEXT DEFAULT '',
        language        TEXT DEFAULT 'english',
        region          TEXT DEFAULT 'india',
        religion        TEXT DEFAULT 'general',
        status          TEXT DEFAULT 'active',
        owner_id        TEXT DEFAULT '',
        created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS project_competitors(
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        domain     TEXT NOT NULL,
        notes      TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Runs + events ─────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS runs(
        run_id        TEXT PRIMARY KEY,
        project_id    TEXT NOT NULL,
        seed          TEXT NOT NULL,
        status        TEXT DEFAULT 'queued',
        current_phase TEXT DEFAULT '',
        result        TEXT DEFAULT '{}',
        error         TEXT DEFAULT '',
        cost_usd      REAL DEFAULT 0,
        started_at    TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at  TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS run_events(
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id     TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload    TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Keyword pipeline tables ───────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS universes(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   TEXT NOT NULL,
        seed_keyword TEXT NOT NULL,
        seed_id      TEXT DEFAULT '',
        status       TEXT DEFAULT 'pending',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS pillars(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        universe_id     INTEGER NOT NULL,
        pillar_keyword  TEXT NOT NULL,
        pillar_title    TEXT DEFAULT '',
        cluster_name    TEXT DEFAULT '',
        domain_verdict  TEXT DEFAULT '',
        domain_score    REAL DEFAULT 0,
        created_at      TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS clusters(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        universe_id  INTEGER NOT NULL,
        cluster_name TEXT NOT NULL,
        cluster_type TEXT DEFAULT 'Subtopic'
    );

    CREATE TABLE IF NOT EXISTS keywords(
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        cluster_id          INTEGER NOT NULL,
        keyword             TEXT NOT NULL,
        intent              TEXT DEFAULT 'informational',
        volume_estimate     INTEGER DEFAULT 0,
        difficulty_estimate REAL DEFAULT 0,
        opportunity_score   REAL DEFAULT 0,
        is_pillar           INTEGER DEFAULT 0,
        status              TEXT DEFAULT 'not_used',
        created_at          TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS keyword_status_history(
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword_id INTEGER NOT NULL,
        old_status TEXT NOT NULL,
        new_status TEXT NOT NULL,
        changed_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Content tables ────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS content_articles(
        article_id       TEXT PRIMARY KEY,
        project_id       TEXT NOT NULL,
        run_id           TEXT DEFAULT '',
        keyword          TEXT NOT NULL,
        title            TEXT DEFAULT '',
        body             TEXT DEFAULT '',
        meta_title       TEXT DEFAULT '',
        meta_desc        TEXT DEFAULT '',
        seo_score        REAL DEFAULT 0,
        eeat_score       REAL DEFAULT 0,
        geo_score        REAL DEFAULT 0,
        readability      REAL DEFAULT 0,
        word_count       INTEGER DEFAULT 0,
        status           TEXT DEFAULT 'draft',
        published_url    TEXT DEFAULT '',
        published_at     TEXT DEFAULT '',
        schema_json      TEXT DEFAULT '',
        frozen           INTEGER DEFAULT 0,
        pass_1_research  TEXT DEFAULT '',
        pass_2_brief     TEXT DEFAULT '',
        pass_3_draft     TEXT DEFAULT '',
        pass_7_humanized TEXT DEFAULT '',
        created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS content_versions(
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id     TEXT NOT NULL,
        version_number INTEGER DEFAULT 1,
        body           TEXT DEFAULT '',
        scores         TEXT DEFAULT '{}',
        reason         TEXT DEFAULT '',
        created_at     TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS content_calendar(
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id     TEXT NOT NULL,
        article_id     TEXT DEFAULT '',
        scheduled_date TEXT DEFAULT '',
        platform       TEXT DEFAULT 'wordpress',
        status         TEXT DEFAULT 'pending',
        created_at     TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS publication_sequence(
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id     TEXT NOT NULL,
        article_id     TEXT DEFAULT '',
        position       INTEGER DEFAULT 0,
        depends_on_id  INTEGER DEFAULT 0,
        seasonal_event TEXT DEFAULT '',
        published_at   TEXT DEFAULT '',
        status         TEXT DEFAULT 'pending'
    );

    CREATE TABLE IF NOT EXISTS blog_failures(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id   TEXT NOT NULL,
        pass_number  INTEGER DEFAULT 0,
        error        TEXT DEFAULT '',
        attempted_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Strategy tables ───────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS strategies(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id      TEXT NOT NULL,
        universe_id     INTEGER DEFAULT 0,
        claude_strategy TEXT DEFAULT '',
        content_themes  TEXT DEFAULT '[]',
        created_at      TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS personas(
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id     TEXT NOT NULL,
        name           TEXT NOT NULL,
        description    TEXT DEFAULT '',
        pain_points    TEXT DEFAULT '[]',
        keywords_focus TEXT DEFAULT '[]',
        created_at     TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS context_clusters(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   TEXT NOT NULL,
        keyword      TEXT NOT NULL,
        location     TEXT DEFAULT '',
        religion     TEXT DEFAULT '',
        language     TEXT DEFAULT '',
        context_type TEXT DEFAULT '',
        priority     INTEGER DEFAULT 0,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── SEO audit + ranking tables ────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS seo_audits(
        audit_id          TEXT PRIMARY KEY,
        url               TEXT,
        project_id        TEXT DEFAULT '',
        score             REAL DEFAULT 0,
        grade             TEXT DEFAULT '',
        findings          TEXT DEFAULT '[]',
        cwv_lcp           REAL DEFAULT 0,
        cwv_inp           REAL DEFAULT 0,
        cwv_cls           REAL DEFAULT 0,
        ai_score          REAL DEFAULT 0,
        citability_score  REAL DEFAULT 0,
        llms_txt_present  INTEGER DEFAULT 0,
        schema_types      TEXT DEFAULT '[]',
        hreflang_valid    INTEGER DEFAULT 0,
        status            TEXT DEFAULT 'running',
        created_at        TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS rankings(
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  TEXT NOT NULL,
        keyword     TEXT NOT NULL,
        position    REAL DEFAULT 0,
        ctr         REAL DEFAULT 0,
        impressions INTEGER DEFAULT 0,
        clicks      INTEGER DEFAULT 0,
        recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS ranking_history(
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id    TEXT NOT NULL,
        keyword       TEXT NOT NULL,
        position      REAL DEFAULT 0,
        ctr           REAL DEFAULT 0,
        impressions   INTEGER DEFAULT 0,
        clicks        INTEGER DEFAULT 0,
        recorded_date TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS ranking_alerts(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   TEXT NOT NULL,
        keyword      TEXT NOT NULL,
        old_position REAL DEFAULT 0,
        new_position REAL DEFAULT 0,
        change       REAL DEFAULT 0,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Publishing tables ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS publisher_queue(
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id     TEXT NOT NULL,
        article_id     TEXT NOT NULL,
        platform       TEXT DEFAULT 'wordpress',
        scheduled_date TEXT DEFAULT '',
        status         TEXT DEFAULT 'pending',
        retry_count    INTEGER DEFAULT 0,
        last_attempt   TEXT DEFAULT '',
        published_url  TEXT DEFAULT '',
        error          TEXT DEFAULT '',
        created_at     TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS indexnow_log(
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        url           TEXT NOT NULL,
        platform      TEXT DEFAULT '',
        submitted_at  TEXT DEFAULT CURRENT_TIMESTAMP,
        response_code INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS ai_usage(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   TEXT NOT NULL,
        run_id       TEXT DEFAULT '',
        model        TEXT NOT NULL,
        input_tokens  INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cost_usd     REAL DEFAULT 0,
        purpose      TEXT DEFAULT '',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Quality Intelligence (QI) tables ──────────────────────────────────────
    CREATE TABLE IF NOT EXISTS qi_raw_outputs(
        output_id     TEXT PRIMARY KEY,
        run_id        TEXT NOT NULL,
        project_id    TEXT NOT NULL,
        phase         TEXT NOT NULL,
        fn            TEXT DEFAULT '',
        item_type     TEXT DEFAULT '',
        item_value    TEXT DEFAULT '',
        item_meta     TEXT DEFAULT '{}',
        trace_path    TEXT DEFAULT '',
        quality_label TEXT DEFAULT '',
        quality_score REAL DEFAULT 0,
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS qi_phase_snapshots(
        snap_id     TEXT PRIMARY KEY,
        run_id      TEXT NOT NULL,
        project_id  TEXT NOT NULL,
        phase       TEXT NOT NULL,
        raw_output  TEXT DEFAULT '{}',
        items_count INTEGER DEFAULT 0,
        exec_ms     REAL DEFAULT 0,
        mem_mb      REAL DEFAULT 0,
        errors      TEXT DEFAULT '[]',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS qi_user_feedback(
        fb_id      TEXT PRIMARY KEY,
        output_id  TEXT NOT NULL,
        project_id TEXT NOT NULL,
        label      TEXT NOT NULL,
        reason     TEXT DEFAULT '',
        fix_hint   TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS qi_degradation_events(
        event_id          TEXT PRIMARY KEY,
        output_id         TEXT NOT NULL,
        project_id        TEXT NOT NULL,
        item_type         TEXT DEFAULT '',
        item_value        TEXT DEFAULT '',
        origin_phase      TEXT DEFAULT '',
        origin_fn         TEXT DEFAULT '',
        degradation_phase TEXT DEFAULT '',
        degradation_fn    TEXT DEFAULT '',
        failure_mode      TEXT DEFAULT '',
        user_reason       TEXT DEFAULT '',
        created_at        TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS qi_tunings(
        tuning_id     TEXT PRIMARY KEY,
        event_id      TEXT DEFAULT '',
        phase         TEXT DEFAULT '',
        fn_target     TEXT DEFAULT '',
        engine_file   TEXT DEFAULT '',
        tuning_type   TEXT DEFAULT '',
        problem       TEXT DEFAULT '',
        fix           TEXT DEFAULT '',
        before_value  TEXT DEFAULT '',
        after_value   TEXT DEFAULT '',
        evidence      TEXT DEFAULT '{}',
        status        TEXT DEFAULT 'pending',
        approved_by   TEXT DEFAULT '',
        approved_at   TEXT DEFAULT '',
        reject_reason TEXT DEFAULT '',
        rollback_snap TEXT DEFAULT '',
        claude_notes  TEXT DEFAULT '',
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS qi_runs(
        run_id      TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        seed        TEXT DEFAULT '',
        phases_done TEXT DEFAULT '[]',
        started_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Domain Context (DC) tables ────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS dc_project_profiles(
        project_id         TEXT PRIMARY KEY,
        project_name       TEXT DEFAULT '',
        industry           TEXT DEFAULT '',
        seed_keywords      TEXT DEFAULT '[]',
        domain_description TEXT DEFAULT '',
        accept_overrides   TEXT DEFAULT '[]',
        reject_overrides   TEXT DEFAULT '[]',
        cross_domain_rules TEXT DEFAULT '{}',
        content_angles     TEXT DEFAULT '[]',
        avoid_angles       TEXT DEFAULT '[]',
        created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at         TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS dc_project_tunings(
        tuning_id    TEXT PRIMARY KEY,
        project_id   TEXT NOT NULL,
        tuning_scope TEXT DEFAULT '',
        tuning_type  TEXT DEFAULT '',
        engine_file  TEXT DEFAULT '',
        fn_target    TEXT DEFAULT '',
        problem      TEXT DEFAULT '',
        fix          TEXT DEFAULT '',
        before_value TEXT DEFAULT '',
        after_value  TEXT DEFAULT '',
        status       TEXT DEFAULT 'pending',
        approved_by  TEXT DEFAULT '',
        approved_at  TEXT DEFAULT '',
        rollback_snap TEXT DEFAULT '',
        evidence     TEXT DEFAULT '{}',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS dc_classification_log(
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        keyword    TEXT NOT NULL,
        verdict    TEXT DEFAULT '',
        reason     TEXT DEFAULT '',
        score      REAL DEFAULT 0,
        industry   TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS dc_global_tunings(
        tuning_id    TEXT PRIMARY KEY,
        tuning_type  TEXT DEFAULT '',
        engine_file  TEXT DEFAULT '',
        fn_target    TEXT DEFAULT '',
        problem      TEXT DEFAULT '',
        fix          TEXT DEFAULT '',
        before_value TEXT DEFAULT '',
        after_value  TEXT DEFAULT '',
        status       TEXT DEFAULT 'pending',
        approved_by  TEXT DEFAULT '',
        approved_at  TEXT DEFAULT '',
        rollback_snap TEXT DEFAULT '',
        scope_note   TEXT DEFAULT '',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── RSD Engine tables ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS rsd_engine_runs(
        run_id          TEXT PRIMARY KEY,
        engine_name     TEXT NOT NULL,
        started_at      TEXT DEFAULT CURRENT_TIMESTAMP,
        duration_ms     REAL DEFAULT 0,
        peak_memory_mb  REAL DEFAULT 0,
        input_tokens    INTEGER DEFAULT 0,
        output_tokens   INTEGER DEFAULT 0,
        success         INTEGER DEFAULT 0,
        error           TEXT DEFAULT '',
        output_fields   TEXT DEFAULT '[]',
        expected_fields TEXT DEFAULT '[]',
        output_hash     TEXT DEFAULT '',
        quality_signals TEXT DEFAULT '{}',
        created_at      TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS rsd_health_reports(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        engine_name     TEXT NOT NULL,
        version         TEXT DEFAULT '',
        total_score     REAL DEFAULT 0,
        status          TEXT DEFAULT '',
        dimensions      TEXT DEFAULT '{}',
        runs_analysed   INTEGER DEFAULT 0,
        recommendations TEXT DEFAULT '[]',
        needs_tuning    INTEGER DEFAULT 0,
        generated_at    TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS rsd_engine_versions(
        version      TEXT PRIMARY KEY,
        engine_name  TEXT NOT NULL,
        file_path    TEXT DEFAULT '',
        code_hash    TEXT DEFAULT '',
        change_type  TEXT DEFAULT '',
        description  TEXT DEFAULT '',
        changes      TEXT DEFAULT '[]',
        ai_used      TEXT DEFAULT '',
        score_before REAL DEFAULT 0,
        score_after  REAL DEFAULT 0,
        approved_by  TEXT DEFAULT '',
        approved_at  TEXT DEFAULT '',
        rolled_back  INTEGER DEFAULT 0,
        test_results TEXT DEFAULT '{}',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS rsd_approval_requests(
        request_id   TEXT PRIMARY KEY,
        engine_name  TEXT NOT NULL,
        version      TEXT DEFAULT '',
        diff         TEXT DEFAULT '',
        summary      TEXT DEFAULT '',
        claude_notes TEXT DEFAULT '',
        score_before REAL DEFAULT 0,
        score_after  REAL DEFAULT 0,
        test_report  TEXT DEFAULT '{}',
        status       TEXT DEFAULT 'pending',
        decision_by  TEXT DEFAULT '',
        decision_at  TEXT DEFAULT '',
        decision_note TEXT DEFAULT '',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS rsd_changelog(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        engine_name  TEXT NOT NULL,
        version      TEXT DEFAULT '',
        change_type  TEXT DEFAULT '',
        title        TEXT DEFAULT '',
        description  TEXT DEFAULT '',
        score_before REAL DEFAULT 0,
        score_after  REAL DEFAULT 0,
        approved_by  TEXT DEFAULT '',
        rolled_back  INTEGER DEFAULT 0,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Self Development (SD) tables ──────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS sd_intelligence_items(
        item_id          TEXT PRIMARY KEY,
        source_id        TEXT DEFAULT '',
        title            TEXT DEFAULT '',
        url              TEXT DEFAULT '',
        raw_content      TEXT DEFAULT '',
        summary          TEXT DEFAULT '',
        relevance_score  REAL DEFAULT 0,
        engines_affected TEXT DEFAULT '[]',
        change_type      TEXT DEFAULT '',
        action_needed    TEXT DEFAULT '',
        discovered_at    TEXT DEFAULT CURRENT_TIMESTAMP,
        processed        INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS sd_knowledge_gaps(
        gap_id             TEXT PRIMARY KEY,
        title              TEXT DEFAULT '',
        description        TEXT DEFAULT '',
        evidence_urls      TEXT DEFAULT '[]',
        engines_affected   TEXT DEFAULT '[]',
        priority           INTEGER DEFAULT 0,
        gap_type           TEXT DEFAULT '',
        estimated_effort   TEXT DEFAULT '',
        status             TEXT DEFAULT 'open',
        source_items       TEXT DEFAULT '[]',
        implementation     TEXT DEFAULT '',
        created_at         TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sd_user_content(
        content_id       TEXT PRIMARY KEY,
        title            TEXT DEFAULT '',
        content          TEXT DEFAULT '',
        content_type     TEXT DEFAULT '',
        engines_affected TEXT DEFAULT '[]',
        notes            TEXT DEFAULT '',
        status           TEXT DEFAULT 'pending',
        analysis         TEXT DEFAULT '{}',
        added_by         TEXT DEFAULT '',
        created_at       TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sd_implementations(
        impl_id          TEXT PRIMARY KEY,
        gap_id           TEXT DEFAULT '',
        engine_name      TEXT DEFAULT '',
        version          TEXT DEFAULT '',
        code_before      TEXT DEFAULT '',
        code_after       TEXT DEFAULT '',
        diff             TEXT DEFAULT '',
        changes          TEXT DEFAULT '[]',
        ai_used          TEXT DEFAULT '',
        test_code        TEXT DEFAULT '',
        test_results     TEXT DEFAULT '{}',
        claude_notes     TEXT DEFAULT '',
        approval_status  TEXT DEFAULT 'pending',
        approved_by      TEXT DEFAULT '',
        approved_at      TEXT DEFAULT '',
        rejection_reason TEXT DEFAULT '',
        created_at       TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sd_custom_sources(
        source_id        TEXT PRIMARY KEY,
        name             TEXT NOT NULL,
        url              TEXT NOT NULL,
        category         TEXT DEFAULT '',
        crawl_type       TEXT DEFAULT '',
        engines_affected TEXT DEFAULT '[]',
        frequency        TEXT DEFAULT 'weekly',
        keywords         TEXT DEFAULT '[]',
        active           INTEGER DEFAULT 1,
        added_by         TEXT DEFAULT '',
        notes            TEXT DEFAULT '',
        created_at       TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sd_source_crawl_log(
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id      TEXT NOT NULL,
        crawled_at     TEXT DEFAULT CURRENT_TIMESTAMP,
        items_found    INTEGER DEFAULT 0,
        items_relevant INTEGER DEFAULT 0,
        error          TEXT DEFAULT '',
        duration_ms    REAL DEFAULT 0
    );

    -- ── Addon module tables ───────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS prompt_versions(
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        engine_name      TEXT NOT NULL,
        prompt_type      TEXT DEFAULT '',
        content          TEXT DEFAULT '',
        status           TEXT DEFAULT 'active',
        performance_data TEXT DEFAULT '{}',
        created_at       TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS ai_memory(
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        scope      TEXT DEFAULT '',
        layer      INTEGER DEFAULT 1,
        content    TEXT DEFAULT '',
        project_id TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS content_lifecycle(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id   TEXT NOT NULL,
        keyword      TEXT DEFAULT '',
        stage        TEXT DEFAULT 'new',
        last_updated TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS cannibalization_registry(
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword    TEXT NOT NULL,
        title      TEXT DEFAULT '',
        url        TEXT DEFAULT '',
        embedding  TEXT DEFAULT '',
        project_id TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS cluster_types(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        cluster_id   INTEGER NOT NULL,
        cluster_type TEXT DEFAULT 'Subtopic',
        content_spec TEXT DEFAULT '{}'
    );

    -- ── Indexes ───────────────────────────────────────────────────────────────
    CREATE INDEX IF NOT EXISTS ix_runs_project        ON runs(project_id);
    CREATE INDEX IF NOT EXISTS ix_articles_project    ON content_articles(project_id);
    CREATE INDEX IF NOT EXISTS ix_rankings_project    ON rankings(project_id);
    CREATE INDEX IF NOT EXISTS ix_events_run          ON run_events(run_id);
    CREATE INDEX IF NOT EXISTS idx_keywords_cluster   ON keywords(cluster_id);
    CREATE INDEX IF NOT EXISTS idx_keywords_status    ON keywords(status);
    CREATE INDEX IF NOT EXISTS idx_keywords_intent    ON keywords(intent);
    CREATE INDEX IF NOT EXISTS idx_blogs_project      ON content_articles(project_id);
    CREATE INDEX IF NOT EXISTS idx_blogs_status       ON content_articles(status);
    CREATE INDEX IF NOT EXISTS idx_qi_raw_project     ON qi_raw_outputs(project_id);
    CREATE INDEX IF NOT EXISTS idx_qi_raw_phase       ON qi_raw_outputs(phase);
    CREATE INDEX IF NOT EXISTS idx_qi_raw_label       ON qi_raw_outputs(quality_label);
    CREATE INDEX IF NOT EXISTS idx_qi_tune_status     ON qi_tunings(status);
    CREATE INDEX IF NOT EXISTS idx_dc_clf_project     ON dc_classification_log(project_id);
    CREATE INDEX IF NOT EXISTS idx_dc_tunings_scope   ON dc_project_tunings(tuning_scope);
    CREATE INDEX IF NOT EXISTS idx_ranking_project    ON ranking_history(project_id);
    CREATE INDEX IF NOT EXISTS idx_rsd_requests_status ON rsd_approval_requests(status);
    """)


def downgrade():
    tables = [
        "cluster_types", "cannibalization_registry", "content_lifecycle",
        "ai_memory", "prompt_versions", "sd_source_crawl_log",
        "sd_custom_sources", "sd_implementations", "sd_user_content",
        "sd_knowledge_gaps", "sd_intelligence_items", "rsd_changelog",
        "rsd_approval_requests", "rsd_engine_versions", "rsd_health_reports",
        "rsd_engine_runs", "dc_global_tunings", "dc_classification_log",
        "dc_project_tunings", "dc_project_profiles", "qi_runs", "qi_tunings",
        "qi_degradation_events", "qi_user_feedback", "qi_phase_snapshots",
        "qi_raw_outputs", "ai_usage", "indexnow_log", "publisher_queue",
        "ranking_alerts", "ranking_history", "rankings", "seo_audits",
        "context_clusters", "personas", "strategies", "blog_failures",
        "publication_sequence", "content_calendar", "content_versions",
        "content_articles", "keyword_status_history", "keywords", "clusters",
        "pillars", "universes", "run_events", "runs", "project_competitors",
        "projects", "user_projects", "users",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t}")

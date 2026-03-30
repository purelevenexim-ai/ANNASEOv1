# AnnaSEO — Data Models

**Database:** SQLite (dev) → PostgreSQL (prod)
**ORM:** SQLAlchemy + Alembic migrations
**Total tables:** 45+

---

## Core Project Tables

```sql
projects
  id, name, industry, description, seeds, created_at, updated_at
  -- audience intelligence columns (added via migration):
  target_languages TEXT DEFAULT '[]'   -- JSON array: ["english","malayalam"]
  target_locations TEXT DEFAULT '[]'   -- JSON array: ["india","kerala"]
  business_type    TEXT DEFAULT 'B2C'  -- B2C | B2B | D2C | Service | Marketplace
  usp              TEXT DEFAULT ''     -- unique selling proposition
  audience_personas TEXT DEFAULT '[]'  -- JSON array of persona strings
  competitor_urls  TEXT DEFAULT '[]'   -- JSON array of competitor URL strings
  customer_reviews TEXT DEFAULT ''     -- paste of sample reviews

project_settings
  project_id, wp_url, wp_user, wp_pass_hash, shopify_store, shopify_token,
  kill_words, accept_words, language, region, religion

project_competitors
  id, project_id, domain, notes

audience_profiles
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  project_id  TEXT NOT NULL UNIQUE
  target_locations  TEXT DEFAULT '[]'  -- JSON
  target_religions  TEXT DEFAULT '[]'  -- JSON
  target_languages  TEXT DEFAULT '[]'  -- JSON
  personas          TEXT DEFAULT '[]'  -- JSON array of persona strings
  created_at  TEXT DEFAULT (datetime('now'))
  -- upsert: ON CONFLICT(project_id) DO UPDATE SET ...
```

---

## Keyword Pipeline Tables

```sql
universes
  id, project_id, seed_keyword, seed_id, status, created_at

pillars
  id, universe_id, pillar_keyword, pillar_title, cluster_name,
  domain_verdict, domain_score, created_at

clusters
  id, universe_id, cluster_name, cluster_type,
  (types: Pillar, Subtopic, Support, Conversion)

keywords
  id, cluster_id, keyword, intent, volume_estimate, difficulty_estimate,
  opportunity_score, is_pillar, status, created_at

keyword_status_history
  id, keyword_id, old_status, new_status, changed_at
  (statuses: not_used, planned, in_content, published, ranking, optimized)
```

---

## Content Tables

```sql
content_blogs
  id, project_id, keyword_id, pillar_id,
  title, slug, body, meta_title, meta_description,
  seo_score, eeat_score, geo_score, readability_score,
  word_count, status, published_url, published_at,
  pass_1_research, pass_2_brief, pass_3_draft,
  pass_7_humanized, schema_json, created_at

content_versions
  id, blog_id, version_number, body, scores, reason, created_at

content_calendar
  id, project_id, blog_id, scheduled_date, platform, status

publication_sequence
  id, project_id, blog_id, position, published_at, status

blog_failures
  id, blog_id, pass_number, error, attempted_at
```

---

## Strategy Tables

```sql
strategies
  id, project_id, universe_id, claude_strategy, content_themes,
  created_at

personas
  id, project_id, name, description, pain_points, keywords_focus

context_clusters
  id, project_id, keyword, location, religion, language,
  context_type, priority

strategy_sessions
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  session_id  TEXT NOT NULL UNIQUE        -- uuid
  project_id  TEXT NOT NULL
  engine_type TEXT DEFAULT 'development'  -- development | final
  status      TEXT DEFAULT 'pending'      -- pending | running | completed | failed
  input_json  TEXT DEFAULT '{}'           -- UserInput serialized
  result_json TEXT DEFAULT '{}'           -- StrategyOutput serialized
  confidence  REAL DEFAULT 0.0
  tokens_used INTEGER DEFAULT 0
  error       TEXT DEFAULT ''
  created_at  TEXT DEFAULT (datetime('now'))
```

---

## SEO Audit Tables

```sql
seo_audits
  id, project_id, url, score, findings_json, cwv_lcp, cwv_inp, cwv_cls,
  ai_visibility_score, citability_score, llms_txt_present, schema_types,
  hreflang_valid, created_at

ranking_history
  id, project_id, keyword, position, ctr, impressions, clicks,
  recorded_date

ranking_alerts
  id             INTEGER PRIMARY KEY AUTOINCREMENT
  project_id     TEXT NOT NULL
  keyword        TEXT NOT NULL
  old_position   INTEGER
  new_position   INTEGER
  change         INTEGER          -- positive = dropped, negative = gained
  severity       TEXT DEFAULT 'warning'  -- critical | high | warning
  status         TEXT DEFAULT 'new'      -- new | acknowledged | fixed
  diagnosis_json TEXT DEFAULT '{}'       -- RankingMonitor.diagnose_drop() result
  created_at     TEXT DEFAULT (datetime('now'))

ranking_predictions
  id               INTEGER PRIMARY KEY AUTOINCREMENT
  project_id       TEXT NOT NULL
  keyword          TEXT NOT NULL
  pillar           TEXT
  predicted_rank   INTEGER
  predicted_month  INTEGER  -- 1–12
  confidence       TEXT DEFAULT 'medium'  -- low | medium | high
  created_at       TEXT DEFAULT (datetime('now'))
```

---

## Content Freeze System Tables

```sql
content_blogs   (new freeze-lifecycle table — separate from legacy content_blogs)
  blog_id          TEXT PRIMARY KEY   -- uuid
  project_id       TEXT NOT NULL
  pillar           TEXT DEFAULT ''
  cluster          TEXT DEFAULT ''
  keyword          TEXT DEFAULT ''
  title            TEXT DEFAULT ''
  body             TEXT DEFAULT ''
  meta_desc        TEXT DEFAULT ''
  schema_type      TEXT DEFAULT 'Article'
  language         TEXT DEFAULT 'english'
  status           TEXT DEFAULT 'draft'
    -- draft | approved | frozen | published | failed
  frozen_at        TEXT              -- ISO datetime when frozen
  scheduled_date   TEXT              -- YYYY-MM-DD publication target
  published_url    TEXT DEFAULT ''
  internal_links   TEXT DEFAULT '[]' -- JSON array of injected URLs
  word_count       INTEGER DEFAULT 0
  seo_score        REAL DEFAULT 0.0
  version          INTEGER DEFAULT 1
  created_at       TEXT DEFAULT (datetime('now'))
  updated_at       TEXT DEFAULT (datetime('now'))

blog_versions
  id           INTEGER PRIMARY KEY AUTOINCREMENT
  blog_id      TEXT NOT NULL
  version      INTEGER NOT NULL
  title        TEXT DEFAULT ''
  body         TEXT DEFAULT ''
  meta_desc    TEXT DEFAULT ''
  saved_at     TEXT DEFAULT (datetime('now'))

content_freeze_queue
  id             INTEGER PRIMARY KEY AUTOINCREMENT
  blog_id        TEXT NOT NULL
  project_id     TEXT NOT NULL
  pillar         TEXT DEFAULT ''
  scheduled_date TEXT NOT NULL
  published      INTEGER DEFAULT 0  -- 0 | 1
  published_at   TEXT
```

---

## System Graph Tables

```sql
system_graph_cache
  id           INTEGER PRIMARY KEY AUTOINCREMENT
  project_id   TEXT NOT NULL UNIQUE
  graph_json   TEXT DEFAULT '{}'   -- D3-ready nodes + edges JSON
  node_count   INTEGER DEFAULT 0
  edge_count   INTEGER DEFAULT 0
  updated_at   TEXT DEFAULT (datetime('now'))
  -- upsert: ON CONFLICT(project_id) DO UPDATE SET ...
```

---

## Publishing Tables

```sql
publisher_queue
  id, project_id, blog_id, platform, scheduled_date, status,
  retry_count, last_attempt, published_url, error

indexnow_log
  id, url, platform, submitted_at, response_code
```

---

## Quality Intelligence Tables (QI Engine)

```sql
qi_raw_outputs
  output_id, run_id, project_id, phase, fn, item_type, item_value,
  item_meta, trace_path, quality_label, quality_score, created_at

qi_phase_snapshots
  snap_id, run_id, project_id, phase, raw_output, items_count,
  exec_ms, mem_mb, errors, created_at

qi_user_feedback
  fb_id, output_id, project_id, label, reason, fix_hint, created_at

qi_degradation_events
  event_id, output_id, project_id, item_type, item_value,
  origin_phase, origin_fn, degradation_phase, degradation_fn,
  failure_mode, user_reason, created_at

qi_tunings
  tuning_id, event_id, phase, fn_target, engine_file, tuning_type,
  problem, fix, before_value, after_value, evidence, status,
  approved_by, approved_at, reject_reason, rollback_snap,
  claude_notes, created_at

qi_runs
  run_id, project_id, seed, phases_done, started_at
```

---

## Domain Context Tables

```sql
dc_project_profiles
  project_id, project_name, industry, seed_keywords, domain_description,
  accept_overrides, reject_overrides, cross_domain_rules,
  content_angles, avoid_angles, created_at, updated_at

dc_project_tunings
  tuning_id, project_id, tuning_scope, tuning_type, engine_file, fn_target,
  problem, fix, before_value, after_value, status, approved_by,
  approved_at, rollback_snap, evidence, created_at

dc_classification_log
  id, project_id, keyword, verdict, reason, score, industry, created_at

dc_global_tunings
  tuning_id, tuning_type, engine_file, fn_target, problem, fix,
  before_value, after_value, status, approved_by, approved_at,
  rollback_snap, scope_note, created_at
```

---

## RSD Engine Tables

```sql
rsd_engine_runs
  run_id, engine_name, started_at, duration_ms, peak_memory_mb,
  input_tokens, output_tokens, success, error, output_fields,
  expected_fields, output_hash, quality_signals, created_at

rsd_health_reports
  id, engine_name, version, total_score, status, dimensions,
  runs_analysed, recommendations, needs_tuning, generated_at

rsd_engine_versions
  version, engine_name, file_path, code_hash, change_type, description,
  changes, ai_used, score_before, score_after, approved_by, approved_at,
  rolled_back, test_results, created_at

rsd_approval_requests
  request_id, engine_name, version, diff, summary, claude_notes,
  score_before, score_after, test_report, status, decision_by,
  decision_at, decision_note, created_at

rsd_changelog
  id, engine_name, version, change_type, title, description,
  score_before, score_after, approved_by, rolled_back, created_at
```

---

## Self Development Tables

```sql
sd_intelligence_items
  item_id, source_id, title, url, raw_content, summary,
  relevance_score, engines_affected, change_type, action_needed,
  discovered_at, processed

sd_knowledge_gaps
  gap_id, title, description, evidence_urls, engines_affected,
  priority, gap_type, estimated_effort, status, source_items,
  implementation, created_at

sd_user_content
  content_id, title, content, content_type, engines_affected,
  notes, status, analysis, created_at, added_by

sd_implementations
  impl_id, gap_id, engine_name, version, code_before, code_after,
  diff, changes, ai_used, test_code, test_results, claude_notes,
  approval_status, approved_by, approved_at, rejection_reason, created_at

sd_custom_sources
  source_id, name, url, category, crawl_type, engines_affected,
  frequency, keywords, active, added_by, notes, created_at

sd_source_crawl_log
  id, source_id, crawled_at, items_found, items_relevant, error, duration_ms
```

---

## Addon Module Tables

```sql
prompt_versions
  id, engine_name, prompt_type, content, status, performance_data,
  created_at
  (status: active, testing, deprecated)

ai_memory
  id, scope, layer, content, project_id, created_at
  (layers: 1=engine_default, 2=project, 3=learning, 4=interaction)

content_lifecycle
  id, article_id, keyword, stage, last_updated
  (stages: new, growing, peak, declining, refresh_needed)

cannibalization_registry
  id, keyword, title, url, embedding, project_id, created_at

cluster_types
  id, cluster_id, cluster_type, content_spec
  (types: Pillar, Subtopic, Support, Conversion)
```

---

## Indexes (Critical for Performance)

```sql
-- Keyword lookups
CREATE INDEX idx_keywords_cluster ON keywords(cluster_id);
CREATE INDEX idx_keywords_status ON keywords(status);
CREATE INDEX idx_keywords_intent ON keywords(intent);

-- Content lookups
CREATE INDEX idx_blogs_project ON content_blogs(project_id);
CREATE INDEX idx_blogs_status ON content_blogs(status);
CREATE INDEX idx_blogs_keyword ON content_blogs(keyword_id);

-- QI lookups
CREATE INDEX idx_qi_raw_project ON qi_raw_outputs(project_id);
CREATE INDEX idx_qi_raw_phase ON qi_raw_outputs(phase);
CREATE INDEX idx_qi_raw_label ON qi_raw_outputs(quality_label);
CREATE INDEX idx_qi_tune_status ON qi_tunings(status);

-- DC lookups
CREATE INDEX idx_dc_clf_project ON dc_classification_log(project_id);
CREATE INDEX idx_dc_tunings_scope ON dc_project_tunings(tuning_scope);

-- Ranking
CREATE INDEX idx_ranking_project_date ON ranking_history(project_id, recorded_date);
```

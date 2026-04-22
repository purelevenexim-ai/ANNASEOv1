"""
================================================================================
ANNASEO — DATA LINEAGE & ENGINE ATTRIBUTION ENGINE
================================================================================
File        : annaseo_lineage_engine.py

Core problem this solves
─────────────────────────
"Cinnamon tour" appeared as a pillar keyword.
The question is: WHICH exact engine/phase/function created it?

The answer could be any of these:
  P2_KeywordExpansion._google_autosuggest()   → fetched "cinnamon tour" from Google
  P3_Normalization.run()                       → didn't filter it out
  OffTopicFilter.filter()                      → kill list missing "tour"
  P8_TopicDetection._name_topic()              → named a cluster badly
  P10_PillarIdentification                     → selected wrong pillar
  IntentClassifier._classify()                 → misclassified as "informational" not noise
  HDBSCAN clustering                           → merged unrelated keywords

Without lineage, we can't fix the right thing.

What this engine does
──────────────────────
1. TRACE COLLECTION
   Every engine/phase/function wraps output with a trace envelope:
   {
     "value": "cinnamon tour",
     "trace": {
       "engine":   "20phase_engine",
       "phase":    "P2_KeywordExpansion",
       "function": "_google_autosuggest",
       "source":   "google_autosuggest",
       "run_id":   "run_abc123",
       "step":     2,
       "input":    "cinnamon",
       "transformations": [
         {"step": 2, "fn": "_google_autosuggest",     "action": "fetched"},
         {"step": 3, "fn": "P3_Normalization.run",    "action": "passed_through"},
         {"step": 4, "fn": "OffTopicFilter.filter",   "action": "passed_through"},
         {"step": 8, "fn": "P8_TopicDetection",       "action": "clustered_into:Cinnamon_Tourism"},
         {"step":10, "fn": "P10_PillarIdentification","action": "selected_as_pillar"},
       ]
     }
   }

2. DEGRADATION POINT DETECTION
   When a user marks "cinnamon tour" as Bad:
   → Walk the transformation chain backwards
   → Find the FIRST point where degradation could have been caught
   → That is the fix point (not just the final engine that surfaced it)

3. TARGETED TUNING
   Instead of tuning the whole OffTopicFilter:
   → Tune P2's source filter to not fetch tourism terms for spice businesses
   → AND tune P3's normalisation to catch these
   → AND strengthen OffTopicFilter with the exact words
   → AND tune P10's pillar scoring to penalise off-domain pillars

4. QUALITY GATE AT EACH PHASE
   Each phase gets a quality score based on:
   - How many of its outputs were later marked Bad
   - What % of its outputs passed downstream without being filtered
   - Execution quality (time, memory, error rate)
   - Output completeness (required fields present)

Phase → Engine map (complete)
──────────────────────────────
P1   SeedInput             → validates seed, produces Seed object
P2   KeywordExpansion       → produces raw_keywords (500-3000 per seed)
P3   Normalization          → produces clean_keywords (dedup, standardise)
P4   EntityDetection        → produces keyword_entity_map (spaCy)
P5   IntentClassification   → produces intent_map (informational/transactional/etc)
P6   SERPIntelligence       → produces serp_data (competitor analysis)
P7   OpportunityScoring     → produces scored_keywords (0-100 per kw)
P8   TopicDetection         → produces topic_map (HDBSCAN clusters)
P9   ClusterFormation       → produces cluster_map (topic → cluster)
P10  PillarIdentification   → produces pillars (anchor pages per cluster)
P11  KnowledgeGraph         → produces knowledge graph (5-level hierarchy)
P12  InternalLinking        → produces link_map (graph of internal links)
P13  ContentCalendar        → produces publishing_schedule
P14  DedupPrevention        → produces deduplicated_pipeline
P15  ContentBrief           → produces article_brief (H1/H2/H3, FAQ, entities)
P16  ClaudeContent          → produces article_draft (full text)
P17  SEOOptimization        → produces seo_scored_article
P18  SchemaMetadata         → produces json_ld + meta tags
P19  Publishing             → produces published_article (WP/Shopify)
P20  RankingFeedback        → produces ranking_analysis + self-improvement plan

Supporting modules (also traced):
  OffTopicFilter           → filters keywords (annaseo_addons.py)
  HDBSCANClustering        → clusters keywords (annaseo_addons.py)
  KeywordTrafficScorer     → scores keywords (annaseo_addons.py)
  CannibalizationDetector  → dedup articles (annaseo_addons.py)
  ContentGenerationEngine  → 7-pass content (ruflo_content_engine.py)
  SEOScorer                → 41-signal content check
  GEOScorer                → AI citation scoring
  EEATScorer               → experience/expertise/authority/trust
  StrategyDevEngine        → personas, context, business intel
  ConfirmationPipeline     → 5-gate user approval flow
  RSDEngine                → code quality monitoring
================================================================================
"""

from __future__ import annotations

import os, json, time, hashlib, logging, sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from contextlib import contextmanager

log = logging.getLogger("annaseo.lineage")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — PHASE MAP (authoritative)
# Every phase, what it consumes, what it produces, where errors originate
# ─────────────────────────────────────────────────────────────────────────────

PHASE_MAP: Dict[str, dict] = {
    "P1_SeedInput": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P1_SeedInput",
        "input_type":   "raw_keyword_string",
        "output_type":  "Seed object",
        "output_items": ["seed_keyword", "seed_id", "language", "region"],
        "error_modes":  ["invalid seed", "empty keyword", "duplicate seed"],
        "quality_checks":["seed_is_product_related", "seed_has_commercial_potential"],
    },
    "P2_KeywordExpansion": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P2_KeywordExpansion",
        "input_type":   "Seed",
        "output_type":  "List[str] raw_keywords",
        "output_items": ["raw_keywords"],
        "sources":      ["google_autosuggest","youtube_autosuggest","amazon_autosuggest",
                         "duckduckgo","reddit_titles","question_variants"],
        "error_modes":  ["off-topic keywords from autosuggest",
                         "competitor brand names fetched",
                         "tourism/travel terms for product seeds",
                         "irrelevant long-tail pollution"],
        "quality_checks":["all_keywords_relate_to_seed",
                          "no_off_topic_domains",
                          "volume_distribution_reasonable"],
    },
    "P3_Normalization": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P3_Normalization",
        "input_type":   "List[str] raw_keywords",
        "output_type":  "List[str] clean_keywords",
        "error_modes":  ["near-duplicates surviving", "valid keywords removed",
                         "normalisation changing meaning"],
        "quality_checks":["dedup_rate_reasonable", "no_valid_keywords_lost"],
    },
    "OffTopicFilter": {
        "engine_file":  "annaseo_addons.py",
        "class":        "OffTopicFilter",
        "input_type":   "List[str] keywords",
        "output_type":  "List[str] filtered_keywords",
        "error_modes":  ["off-topic keywords passing through kill list",
                         "valid keywords blocked incorrectly",
                         "kill list too narrow for business type"],
        "quality_checks":["off_topic_rate_zero",
                          "no_false_positives",
                          "business_relevant_only"],
    },
    "P4_EntityDetection": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P4_EntityDetection",
        "input_type":   "List[str] keywords",
        "output_type":  "Dict[str, dict] keyword_entity_map",
        "error_modes":  ["entities misclassified", "entities missed",
                         "spaCy model too generic for domain"],
        "quality_checks":["entity_types_match_domain",
                          "coverage_above_80_pct"],
    },
    "P5_IntentClassification": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P5_IntentClassification",
        "input_type":   "List[str] keywords",
        "output_type":  "Dict[str, str] intent_map",
        "intents":      ["informational","transactional","comparison","commercial","navigational"],
        "error_modes":  ["transactional classified as informational",
                         "comparison misclassified",
                         "no-intent noise classified as valid"],
        "quality_checks":["intent_distribution_matches_seed_type",
                          "transactional_kws_have_commercial_signals"],
    },
    "P6_SERPIntelligence": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P6_SERPIntelligence",
        "input_type":   "List[str] keywords",
        "output_type":  "Dict[str, dict] serp_data",
        "error_modes":  ["SERP data outdated (cached too long)",
                         "competitor data fetched incorrectly",
                         "SERP not representative of target region"],
        "quality_checks":["serp_data_freshness_within_14d",
                          "competitor_domains_relevant"],
    },
    "P7_OpportunityScoring": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P7_OpportunityScoring",
        "input_type":   "List[str] + intent_map + serp_data",
        "output_type":  "Dict[str, float] scored_keywords",
        "error_modes":  ["off-topic keywords scoring high",
                         "important keywords scoring too low",
                         "scoring formula not calibrated for niche"],
        "quality_checks":["score_distribution_makes_sense",
                          "top_scorers_are_business_relevant"],
    },
    "P8_TopicDetection": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P8_TopicDetection",
        "input_type":   "List[str] keywords + SBERT embeddings",
        "output_type":  "Dict[str, List[str]] topic_map",
        "error_modes":  ["unrelated keywords clustered together",
                         "good keywords in noise cluster (-1)",
                         "cluster names misleading",
                         "embedding model too generic for domain"],
        "quality_checks":["cluster_internal_coherence",
                          "topic_names_are_meaningful",
                          "noise_pct_below_10"],
    },
    "P9_ClusterFormation": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P9_ClusterFormation",
        "input_type":   "Dict[str, List[str]] topic_map",
        "output_type":  "Dict[str, List[str]] cluster_map",
        "error_modes":  ["clusters too broad (merging unrelated topics)",
                         "clusters too narrow (splitting coherent topics)",
                         "off-topic topics surviving into clusters"],
        "quality_checks":["cluster_count_reasonable",
                          "cluster_names_distinct",
                          "no_off_topic_clusters"],
    },
    "P10_PillarIdentification": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P10_PillarIdentification",
        "input_type":   "Dict[str, List[str]] cluster_map",
        "output_type":  "Dict[str, dict] pillars",
        "error_modes":  ["off-topic cluster selected as pillar",
                         "pillar keyword not commercial enough",
                         "pillar too broad or too narrow",
                         "duplicate pillars across clusters"],
        "quality_checks":["all_pillars_business_relevant",
                          "pillar_keywords_have_search_intent",
                          "no_duplicate_pillars",
                          "no_off_domain_pillars"],
    },
    "P11_KnowledgeGraph": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P11_KnowledgeGraph",
        "input_type":   "Pillars + Clusters + Keywords",
        "output_type":  "KnowledgeGraph (5-level hierarchy)",
        "error_modes":  ["wrong parent-child relationships",
                         "orphan keywords not linked",
                         "graph has cycles"],
        "quality_checks":["hierarchy_depth_correct",
                          "all_keywords_in_graph",
                          "no_orphan_nodes"],
    },
    "P15_ContentBrief": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P15_ContentBrief",
        "input_type":   "article_dict + Seed + entities",
        "output_type":  "Dict content_brief",
        "error_modes":  ["brief misses key angles",
                         "H2 structure not covering SERP competitors",
                         "FAQ questions generic",
                         "internal links wrong"],
        "quality_checks":["brief_covers_serp_headings",
                          "faq_count_at_least_3",
                          "internal_links_relevant"],
    },
    "P16_ClaudeContent": {
        "engine_file":  "ruflo_20phase_engine.py",
        "class":        "P16_ClaudeContentGeneration",
        "input_type":   "content_brief",
        "output_type":  "article_text (2000+ words)",
        "error_modes":  ["AI watermark patterns (furthermore, certainly)",
                         "generic content without HITL",
                         "hallucinated facts/stats",
                         "keyword stuffing",
                         "missing FAQ section",
                         "poor GEO structure (no direct answers)"],
        "quality_checks":["no_ai_watermarks",
                          "eeat_score_above_75",
                          "geo_score_above_75",
                          "word_count_above_1500",
                          "faq_present"],
    },
    "P17_SEOOptimization": {
        "engine_file":  "ruflo_content_engine.py",
        "class":        "SEOScorer",
        "input_type":   "article_text",
        "output_type":  "seo_score (0-100) + issues",
        "error_modes":  ["score passes but content still low quality",
                         "keyword density check too loose",
                         "readability threshold wrong"],
        "quality_checks":["seo_score_above_75",
                          "all_41_signals_checked"],
    },
    "ContentGenerationEngine": {
        "engine_file":  "ruflo_content_engine.py",
        "class":        "ContentGenerationEngine",
        "input_type":   "keyword + brief + style + brand",
        "output_type":  "GeneratedArticle (7 passes)",
        "passes":       ["research","brief","claude_write","seo_check",
                         "eeat_check","geo_check","humanize"],
        "error_modes":  ["low E-E-A-T (no first-person signals)",
                         "low GEO (no direct answers, no stats)",
                         "low readability (long sentences)",
                         "AI watermarks not scrubbed",
                         "HITL not injected"],
        "quality_checks":["all_7_passes_completed",
                          "final_score_above_75_all_dimensions"],
    },
    "StrategyDevEngine": {
        "engine_file":  "ruflo_strategy_dev_engine.py",
        "class":        "StrategyDevelopmentEngine",
        "input_type":   "UserInput (business, keywords, location, religion)",
        "output_type":  "strategy (personas, context, calendar plan)",
        "error_modes":  ["wrong personas for business type",
                         "location context not applied",
                         "religion context missing",
                         "industry template wrong"],
        "quality_checks":["personas_match_target_market",
                          "context_applied_to_keywords"],
    },
    "ConfirmationPipeline": {
        "engine_file":  "ruflo_confirmation_pipeline.py",
        "class":        "ConfirmationPipeline",
        "input_type":   "Universe + Pillars + Keywords",
        "output_type":  "user_confirmed_strategy",
        "gates":        ["G1_Universe","G2_Pillar","G3_KeywordTree",
                         "G4_BlogSuggestions","G5_FinalStrategy"],
        "error_modes":  ["wrong classification (pillar vs supporting)",
                         "dedup threshold too aggressive",
                         "gate not catching bad keywords before user sees them"],
        "quality_checks":["all_5_gates_completed",
                          "no_off_topic_items_reach_gate_4"],
    },
    "SEOAuditEngine": {
        "engine_file":  "ruflo_seo_audit.py",
        "class":        "RufloSEOAudit",
        "input_type":   "URL",
        "output_type":  "AuditReport (score + findings)",
        "checks":       ["technical_14_checks","core_web_vitals",
                         "ai_visibility","hreflang","citability"],
        "error_modes":  ["false positives in findings",
                         "CWV data outdated",
                         "AI crawler check missing new bots"],
        "quality_checks":["score_correlates_with_real_ranking",
                          "findings_are_actionable"],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — TRACE ENVELOPE (wraps every data item with its origin)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Transformation:
    step:      int
    phase:     str
    fn:        str
    action:    str    # "fetched"|"filtered_out"|"passed_through"|"clustered_into"|"selected_as"
    timestamp: str    = field(default_factory=lambda: datetime.utcnow().isoformat())
    detail:    str    = ""


@dataclass
class TraceEnvelope:
    """
    Every data item produced by any engine is wrapped in this.
    Allows us to trace "cinnamon tour" back to exactly which
    function created it and every function that touched it.
    """
    value:            Any
    item_type:        str     # "keyword"|"pillar"|"cluster"|"article"|"brief"|...
    run_id:           str
    project_id:       str
    seed:             str
    origin_phase:     str     # which phase FIRST produced this item
    origin_fn:        str     # which function within that phase
    origin_source:    str     # "google_autosuggest"|"reddit"|"claude"|...
    transformations:  List[Transformation] = field(default_factory=list)
    metadata:         dict    = field(default_factory=dict)
    quality_label:    str     = "unreviewed"
    quality_score:    Optional[float] = None
    created_at:       str     = field(default_factory=lambda: datetime.utcnow().isoformat())

    def trace_id(self) -> str:
        return hashlib.md5(
            f"{self.run_id}{self.item_type}{str(self.value)[:50]}".encode()
        ).hexdigest()[:14]

    def add_transformation(self, phase: str, fn: str, action: str,
                            step: int = None, detail: str = ""):
        self.transformations.append(Transformation(
            step=step or len(self.transformations)+1,
            phase=phase, fn=fn, action=action, detail=detail
        ))

    def degradation_point(self) -> Optional[Transformation]:
        """
        Find the EARLIEST point where this item could have been caught.
        This is the tuning target — not where it surfaced, but where it SHOULD have been stopped.
        """
        SHOULD_FILTER = {
            "keyword":  ["OffTopicFilter","P3_Normalization","P7_OpportunityScoring"],
            "pillar":   ["OffTopicFilter","P10_PillarIdentification","P9_ClusterFormation"],
            "cluster":  ["P9_ClusterFormation","P8_TopicDetection"],
            "article":  ["P16_ClaudeContent","ContentGenerationEngine","P17_SEOOptimization"],
        }
        filter_phases = SHOULD_FILTER.get(self.item_type, [])
        for t in self.transformations:
            if t.phase in filter_phases and t.action == "passed_through":
                return t   # first filter that should have caught it but didn't
        return self.transformations[0] if self.transformations else None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — LINEAGE DATABASE
# ─────────────────────────────────────────────────────────────────────────────

class LineageDB:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS ln_traces (
            trace_id        TEXT PRIMARY KEY,
            run_id          TEXT NOT NULL,
            project_id      TEXT NOT NULL,
            item_type       TEXT NOT NULL,
            item_value      TEXT NOT NULL,
            seed            TEXT DEFAULT '',
            origin_phase    TEXT NOT NULL,
            origin_fn       TEXT NOT NULL,
            origin_source   TEXT DEFAULT '',
            transformations TEXT DEFAULT '[]',
            metadata        TEXT DEFAULT '{}',
            quality_label   TEXT DEFAULT 'unreviewed',
            quality_score   REAL,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ln_phase_quality (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT NOT NULL,
            project_id      TEXT NOT NULL,
            phase           TEXT NOT NULL,
            items_produced  INTEGER DEFAULT 0,
            items_bad       INTEGER DEFAULT 0,
            items_good      INTEGER DEFAULT 0,
            bad_rate        REAL DEFAULT 0,
            avg_score       REAL DEFAULT 0,
            exec_time_ms    REAL DEFAULT 0,
            memory_mb       REAL DEFAULT 0,
            errors          TEXT DEFAULT '[]',
            quality_score   REAL DEFAULT 0,
            scored_at       TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ln_degradation_events (
            event_id        TEXT PRIMARY KEY,
            trace_id        TEXT NOT NULL,
            project_id      TEXT NOT NULL,
            item_type       TEXT NOT NULL,
            item_value      TEXT NOT NULL,
            degradation_phase TEXT NOT NULL,
            degradation_fn    TEXT NOT NULL,
            origin_phase      TEXT NOT NULL,
            origin_source     TEXT DEFAULT '',
            user_reason       TEXT DEFAULT '',
            fix_applied       TEXT DEFAULT '',
            created_at        TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ln_targeted_tunings (
            tuning_id       TEXT PRIMARY KEY,
            degradation_event_id TEXT,
            phase           TEXT NOT NULL,
            fn_target       TEXT NOT NULL,
            tuning_type     TEXT NOT NULL,
            problem         TEXT NOT NULL,
            fix_description TEXT NOT NULL,
            before_value    TEXT DEFAULT '',
            after_value     TEXT DEFAULT '',
            engine_file     TEXT DEFAULT '',
            evidence        TEXT DEFAULT '[]',
            status          TEXT DEFAULT 'pending',
            approved_by     TEXT DEFAULT '',
            approved_at     TEXT DEFAULT '',
            claude_notes    TEXT DEFAULT '{}',
            rollback_value  TEXT DEFAULT '',
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ln_run_registry (
            run_id          TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            seed            TEXT,
            phases_completed TEXT DEFAULT '[]',
            started_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at    TEXT DEFAULT '',
            overall_quality REAL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_ln_traces_project ON ln_traces(project_id);
        CREATE INDEX IF NOT EXISTS idx_ln_traces_phase   ON ln_traces(origin_phase);
        CREATE INDEX IF NOT EXISTS idx_ln_traces_label   ON ln_traces(quality_label);
        CREATE INDEX IF NOT EXISTS idx_ln_traces_type    ON ln_traces(item_type);
        CREATE INDEX IF NOT EXISTS idx_ln_phase_quality  ON ln_phase_quality(run_id);
        CREATE INDEX IF NOT EXISTS idx_ln_degrad_project ON ln_degradation_events(project_id);
        CREATE INDEX IF NOT EXISTS idx_ln_tunings_status ON ln_targeted_tunings(status);
        """)
        self._db.commit()

    def save_trace(self, trace: TraceEnvelope):
        self._db.execute("""
            INSERT OR REPLACE INTO ln_traces
            (trace_id, run_id, project_id, item_type, item_value, seed,
             origin_phase, origin_fn, origin_source, transformations, metadata)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (trace.trace_id(), trace.run_id, trace.project_id,
              trace.item_type, str(trace.value)[:500], trace.seed,
              trace.origin_phase, trace.origin_fn, trace.origin_source,
              json.dumps([asdict(t) for t in trace.transformations]),
              json.dumps(trace.metadata, default=str)[:2000]))
        self._db.commit()

    def save_phase_quality(self, run_id: str, project_id: str, phase: str,
                            items: int, bad: int, good: int, exec_ms: float,
                            memory_mb: float, errors: list):
        bad_rate = bad / max(items, 1) * 100
        avg      = (good / max(good + bad, 1)) * 100
        quality  = max(0, 100 - bad_rate * 2 - len(errors) * 5)
        self._db.execute("""
            INSERT INTO ln_phase_quality
            (run_id, project_id, phase, items_produced, items_bad, items_good,
             bad_rate, avg_score, exec_time_ms, memory_mb, errors, quality_score)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (run_id, project_id, phase, items, bad, good,
              bad_rate, avg, exec_ms, memory_mb,
              json.dumps(errors[:10]), quality))
        self._db.commit()

    def save_degradation(self, trace: TraceEnvelope, reason: str):
        dp  = trace.degradation_point()
        eid = f"dg_{trace.trace_id()}_{int(time.time())}"
        self._db.execute("""
            INSERT OR REPLACE INTO ln_degradation_events
            (event_id, trace_id, project_id, item_type, item_value,
             degradation_phase, degradation_fn, origin_phase, origin_source, user_reason)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (eid, trace.trace_id(), trace.project_id, trace.item_type,
              str(trace.value)[:200],
              dp.phase if dp else trace.origin_phase,
              dp.fn    if dp else trace.origin_fn,
              trace.origin_phase, trace.origin_source, reason))
        self._db.commit()
        return eid

    def mark_label(self, trace_id: str, label: str, score: float = None):
        self._db.execute(
            "UPDATE ln_traces SET quality_label=?, quality_score=? WHERE trace_id=?",
            (label, score, trace_id))
        self._db.commit()

    def get_traces(self, project_id: str = None, item_type: str = None,
                    label: str = None, phase: str = None,
                    limit: int = 100) -> List[dict]:
        q, p = "SELECT * FROM ln_traces", []
        f = []
        if project_id: f.append("project_id=?"); p.append(project_id)
        if item_type:  f.append("item_type=?");  p.append(item_type)
        if label:      f.append("quality_label=?"); p.append(label)
        if phase:      f.append("origin_phase=?"); p.append(phase)
        if f: q += " WHERE " + " AND ".join(f)
        q += " ORDER BY created_at DESC LIMIT ?"; p.append(limit)
        return [dict(r) for r in self._db.execute(q, p).fetchall()]

    def get_phase_quality_report(self, run_id: str = None,
                                  project_id: str = None) -> List[dict]:
        q, p = "SELECT * FROM ln_phase_quality", []
        f = []
        if run_id:     f.append("run_id=?");     p.append(run_id)
        if project_id: f.append("project_id=?"); p.append(project_id)
        if f: q += " WHERE " + " AND ".join(f)
        q += " ORDER BY quality_score ASC"
        return [dict(r) for r in self._db.execute(q, p).fetchall()]

    def get_degradation_events(self, project_id: str = None) -> List[dict]:
        q = "SELECT * FROM ln_degradation_events"
        p = []
        if project_id: q += " WHERE project_id=?"; p.append(project_id)
        q += " ORDER BY created_at DESC LIMIT 100"
        return [dict(r) for r in self._db.execute(q, p).fetchall()]

    def get_pending_tunings(self) -> List[dict]:
        return [dict(r) for r in self._db.execute(
            "SELECT * FROM ln_targeted_tunings WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()]

    def worst_phases(self, project_id: str, top_n: int = 5) -> List[dict]:
        """Return the N worst-performing phases by bad_rate."""
        return [dict(r) for r in self._db.execute(
            "SELECT phase, AVG(bad_rate) as avg_bad, AVG(quality_score) as avg_quality, SUM(items_bad) as total_bad FROM ln_phase_quality WHERE project_id=? GROUP BY phase ORDER BY avg_bad DESC LIMIT ?",
            (project_id, top_n)
        ).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — TRACER (context manager for every engine/phase)
# ─────────────────────────────────────────────────────────────────────────────

class Tracer:
    """
    Wrap every phase execution with this.
    Records timing, memory, and attaches trace envelopes to outputs.

    Usage in any engine:
        from annaseo_lineage_engine import Tracer, TraceEnvelope
        tracer = Tracer(run_id="run_abc", project_id="proj_001", seed="cinnamon")

        with tracer.phase("P2_KeywordExpansion") as t:
            keywords = self._google_autosuggest(seed)
            t.emit_batch("keyword", keywords, fn="_google_autosuggest",
                         source="google_autosuggest")
    """

    def __init__(self, run_id: str, project_id: str, seed: str):
        self.run_id     = run_id
        self.project_id = project_id
        self.seed       = seed
        self._db        = LineageDB()
        self._current_phase: Optional[str] = None
        self._phase_items: List[TraceEnvelope] = []
        self._phase_errors: List[str] = []
        self._t0        = 0.0
        self._mem_start = 0.0

    @contextmanager
    def phase(self, phase_name: str):
        """Context manager for one phase."""
        import psutil, os as _os
        self._current_phase = phase_name
        self._phase_items   = []
        self._phase_errors  = []
        self._t0            = time.perf_counter()
        proc = psutil.Process(_os.getpid())
        self._mem_start = proc.memory_info().rss / 1024 / 1024

        try:
            yield self
        except Exception as e:
            self._phase_errors.append(str(e)[:200])
            log.warning(f"[Tracer] Phase {phase_name} error: {e}")
        finally:
            ms  = (time.perf_counter() - self._t0) * 1000
            mem = proc.memory_info().rss / 1024 / 1024 - self._mem_start
            self._db.save_phase_quality(
                self.run_id, self.project_id, phase_name,
                items=len(self._phase_items), bad=0, good=0,
                exec_ms=ms, memory_mb=max(0, mem),
                errors=self._phase_errors
            )
            self._current_phase = None

    def emit(self, item_type: str, value: Any, fn: str = "",
              source: str = "", metadata: dict = None) -> TraceEnvelope:
        """Emit one traced item from the current phase."""
        t = TraceEnvelope(
            value=value, item_type=item_type,
            run_id=self.run_id, project_id=self.project_id, seed=self.seed,
            origin_phase=self._current_phase or "unknown",
            origin_fn=fn, origin_source=source,
            metadata=metadata or {}
        )
        t.add_transformation(
            phase=self._current_phase or "unknown",
            fn=fn, action="produced"
        )
        self._phase_items.append(t)
        self._db.save_trace(t)
        return t

    def emit_batch(self, item_type: str, values: List[Any],
                    fn: str = "", source: str = "",
                    metadata_fn=None) -> List[TraceEnvelope]:
        """Emit multiple items at once."""
        traces = []
        for v in values:
            meta = metadata_fn(v) if metadata_fn else {}
            traces.append(self.emit(item_type, v, fn, source, meta))
        return traces

    def record_passthrough(self, trace: TraceEnvelope, fn: str, detail: str = ""):
        """Record that an item passed through this phase without being changed."""
        trace.add_transformation(
            phase=self._current_phase or "unknown",
            fn=fn, action="passed_through", detail=detail
        )
        self._db.save_trace(trace)

    def record_filtered(self, trace: TraceEnvelope, fn: str, reason: str = ""):
        """Record that an item was filtered out at this phase."""
        trace.add_transformation(
            phase=self._current_phase or "unknown",
            fn=fn, action="filtered_out", detail=reason
        )
        self._db.save_trace(trace)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — DEGRADATION ANALYSER
# When a user marks something Bad, find EXACTLY which phase failed
# ─────────────────────────────────────────────────────────────────────────────

class DegradationAnalyser:
    """
    Given a trace_id and user reason, determine:
    1. Which phase was the TRUE degradation point
    2. What type of fix is needed (filter/prompt/parameter/rule)
    3. Which exact function to target
    4. Generate the specific tuning
    """
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def __init__(self):
        self._db = LineageDB()

    def analyse(self, trace_id: str, reason: str,
                 project_id: str = "") -> dict:
        """
        Full degradation analysis. Returns targeted tuning plan.
        """
        import requests as _req

        # Get trace
        traces = self._db.get_traces(limit=1)
        trace_row = self._db._db.execute(
            "SELECT * FROM ln_traces WHERE trace_id=?", (trace_id,)
        ).fetchone()
        if not trace_row:
            return {"error": "Trace not found — item may not have lineage data"}

        tr = dict(trace_row)
        transformations = json.loads(tr.get("transformations","[]"))

        # Record degradation event
        te = TraceEnvelope(
            value=tr["item_value"], item_type=tr["item_type"],
            run_id=tr["run_id"], project_id=tr["project_id"],
            seed=tr["seed"], origin_phase=tr["origin_phase"],
            origin_fn=tr["origin_fn"], origin_source=tr["origin_source"],
            transformations=[
                Transformation(**t) for t in transformations
            ]
        )
        event_id = self._db.save_degradation(te, reason)

        # Determine fix target
        dp = te.degradation_point()
        fix_phase  = dp.phase if dp else tr["origin_phase"]
        fix_fn     = dp.fn    if dp else tr["origin_fn"]

        phase_info = PHASE_MAP.get(fix_phase, {})

        # Use Gemini to generate targeted fix
        key = os.getenv("GEMINI_API_KEY","")
        if key:
            fix = self._gemini_fix(tr, transformations, reason, fix_phase,
                                    fix_fn, phase_info)
        else:
            fix = self._rule_fix(tr, reason, fix_phase, fix_fn, phase_info)

        # Save targeted tuning
        tuning_id = f"lt_{event_id}"
        self._db._db.execute("""
            INSERT OR REPLACE INTO ln_targeted_tunings
            (tuning_id, degradation_event_id, phase, fn_target, tuning_type,
             problem, fix_description, before_value, after_value, engine_file, evidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (tuning_id, event_id, fix_phase, fix_fn,
              fix.get("tuning_type","filter"),
              fix.get("problem",""),
              fix.get("fix_description",""),
              fix.get("before_value",""),
              fix.get("after_value",""),
              phase_info.get("engine_file",""),
              json.dumps([reason, tr["item_value"]])))
        self._db._db.commit()

        log.info(f"[DegradationAnalyser] Fix → {fix_phase}.{fix_fn} ({fix.get('tuning_type')})")
        return {
            "event_id":        event_id,
            "tuning_id":       tuning_id,
            "item_value":      tr["item_value"],
            "item_type":       tr["item_type"],
            "origin_phase":    tr["origin_phase"],
            "origin_fn":       tr["origin_fn"],
            "origin_source":   tr["origin_source"],
            "degradation_at":  fix_phase,
            "fix_fn":          fix_fn,
            "tuning_type":     fix.get("tuning_type"),
            "fix_description": fix.get("fix_description"),
            "engine_file":     phase_info.get("engine_file",""),
            "transformation_path": [
                f"{t['phase']}.{t['fn']} → {t['action']}"
                for t in transformations
            ],
        }

    def _gemini_fix(self, tr: dict, transforms: list, reason: str,
                     fix_phase: str, fix_fn: str, phase_info: dict) -> dict:
        import requests as _req
        key = os.getenv("GEMINI_API_KEY","")
        path_str = "\n".join(
            f"  Step {i+1}: {t['phase']}.{t['fn']} → {t['action']}"
            for i, t in enumerate(transforms)
        )
        error_modes = "\n".join(f"  - {e}" for e in phase_info.get("error_modes",[]))

        try:
            prompt = f"""An SEO engine produced bad output. Determine the exact fix.

Bad item:
  Type:   {tr['item_type']}
  Value:  {tr['item_value']}
  Origin: {tr['origin_phase']}.{tr['origin_fn']} (source: {tr['origin_source']})

Transformation path (how the item flowed through the system):
{path_str}

User said it's wrong because: {reason}

The identified degradation point is: {fix_phase}.{fix_fn}
Known error modes for this phase:
{error_modes}

What is the EXACT fix?
- tuning_type: filter | prompt_edit | parameter | scoring_rule | source_filter
- fn_target: exact function name to change
- problem: one sentence describing what went wrong at this specific phase
- fix_description: exactly what to change
- before_value: what the current state is (code/prompt/value)
- after_value: what it should be changed to

Return JSON only:
{{"tuning_type":"...","fn_target":"...","problem":"...","fix_description":"...","before_value":"...","after_value":"..."}}"""
            r = _req.post(
                f"{self.GEMINI_URL}?key={key}",
                json={"contents":[{"parts":[{"text":prompt}]}],
                      "generationConfig":{"temperature":0.05,"maxOutputTokens":400}},
                timeout=15
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception as e:
            log.warning(f"Gemini fix failed: {e}")
        return self._rule_fix(tr, reason, fix_phase, fix_fn, phase_info)

    def _rule_fix(self, tr: dict, reason: str, fix_phase: str,
                   fix_fn: str, phase_info: dict) -> dict:
        """Rule-based fix determination."""
        value = str(tr.get("item_value","")).lower()

        # Detect fix type from reason and phase
        if "off-topic" in reason.lower() or "not related" in reason.lower() or "nothing to do" in reason.lower():
            words = [w for w in value.split() if len(w) > 3]
            return {
                "tuning_type":     "filter",
                "fn_target":       "OffTopicFilter.GLOBAL_KILL",
                "problem":         f"'{value}' passed through {fix_fn} despite being off-topic",
                "fix_description": f"Add these words to OffTopicFilter kill list: {words}",
                "before_value":    f"# GLOBAL_KILL missing: {words}",
                "after_value":     f"# Add to GLOBAL_KILL:\n{json.dumps(words, indent=2)}",
            }
        if "wrong intent" in reason.lower() or "transactional" in reason.lower():
            return {
                "tuning_type":     "scoring_rule",
                "fn_target":       "P5_IntentClassification._classify",
                "problem":         f"Intent misclassified for '{value}'",
                "fix_description": "Add/strengthen intent signal words for correct classification",
                "before_value":    "# Current intent rules",
                "after_value":     f"# Strengthen rules to correctly classify: {value}",
            }
        if "generic" in reason.lower() or "no first-person" in reason.lower() or "low quality" in reason.lower():
            return {
                "tuning_type":     "prompt_edit",
                "fn_target":       "P16_ClaudeContentGeneration.generate",
                "problem":         "Article lacks E-E-A-T signals and specific expertise",
                "fix_description": "Strengthen HITL injection and first-person experience requirement in prompt",
                "before_value":    "# Current Layer 1 system prompt",
                "after_value":     "# Add rule: require first-person expertise signal every 300 words",
            }
        return {
            "tuning_type":     "scoring_rule",
            "fn_target":       fix_fn,
            "problem":         f"'{value}' produced incorrect output at {fix_phase}",
            "fix_description": f"Review {fix_fn} logic — {reason[:100]}",
            "before_value":    "",
            "after_value":     f"# Tune {fix_fn} to prevent: {reason[:100]}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — PHASE QUALITY REPORTER
# Shows health of every phase based on accumulated feedback
# ─────────────────────────────────────────────────────────────────────────────

class PhaseQualityReporter:
    """
    Computes quality score for every phase based on:
    - How many of its outputs were marked Bad by users
    - How many of its outputs passed through without being filtered
    - Execution performance metrics
    """

    def __init__(self):
        self._db = LineageDB()

    def report(self, project_id: str = None) -> List[dict]:
        """Full quality report for all phases."""
        # Count bad items per originating phase
        q = """
            SELECT origin_phase,
                   COUNT(*) as total,
                   SUM(CASE WHEN quality_label='bad'  THEN 1 ELSE 0 END) as bad_count,
                   SUM(CASE WHEN quality_label='good' THEN 1 ELSE 0 END) as good_count,
                   AVG(CASE WHEN quality_score IS NOT NULL THEN quality_score ELSE 50 END) as avg_score
            FROM ln_traces
        """
        p = []
        if project_id:
            q += " WHERE project_id=?"; p.append(project_id)
        q += " GROUP BY origin_phase ORDER BY bad_count DESC"

        rows = self._db._db.execute(q, p).fetchall()
        result = []
        for row in rows:
            r = dict(row)
            bad_rate    = r["bad_count"] / max(r["total"], 1) * 100
            phase_info  = PHASE_MAP.get(r["origin_phase"], {})
            quality     = max(0, 100 - bad_rate * 2)

            # Get execution metrics from phase_quality table
            exec_row = self._db._db.execute(
                "SELECT AVG(exec_time_ms) as ms, AVG(memory_mb) as mb FROM ln_phase_quality WHERE phase=? " + ("AND project_id=?" if project_id else ""),
                ([r["origin_phase"], project_id] if project_id else [r["origin_phase"]])
            ).fetchone()

            result.append({
                "phase":         r["origin_phase"],
                "engine_file":   phase_info.get("engine_file",""),
                "total_items":   r["total"],
                "bad_count":     r["bad_count"],
                "good_count":    r["good_count"],
                "bad_rate_pct":  round(bad_rate, 1),
                "avg_score":     round(r["avg_score"] or 0, 1),
                "quality_score": round(quality, 1),
                "avg_exec_ms":   round(exec_row["ms"] or 0, 0) if exec_row else 0,
                "avg_memory_mb": round(exec_row["mb"] or 0, 1) if exec_row else 0,
                "status":        ("critical" if quality < 60 else
                                  "degraded" if quality < 80 else
                                  "good"     if quality < 90 else "healthy"),
                "error_modes":   phase_info.get("error_modes", [])[:3],
            })
        return result

    def worst_phase(self, project_id: str = None) -> Optional[dict]:
        rows = self.report(project_id)
        return rows[0] if rows else None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — TARGETED TUNING APPLICATOR (Claude + manual approval)
# ─────────────────────────────────────────────────────────────────────────────

class TargetedTuningApplicator:
    """
    Apply a targeted tuning to the specific function that failed.
    Uses same manual approval gate as all other tunings.
    DeepSeek writes the code change. Claude verifies.
    """
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://172.235.16.165:8080")

    def __init__(self):
        self._db = LineageDB()

    def prepare(self, tuning_id: str) -> dict:
        """
        Generate the actual code change using DeepSeek.
        Returns before/after for the approval gate.
        """
        import requests as _req
        row = self._db._db.execute(
            "SELECT * FROM ln_targeted_tunings WHERE tuning_id=?", (tuning_id,)
        ).fetchone()
        if not row:
            return {"error": "Tuning not found"}

        t = dict(row)
        engine_file = Path(os.getenv("ENGINES_DIR","./")) / t.get("engine_file","")

        if t["tuning_type"] == "filter":
            # Simple: extract words and add to kill list
            after_words_raw = t.get("after_value","")
            words = []
            try:
                m = re.search(r'\[.*?\]', after_words_raw, re.DOTALL)
                if m: words = json.loads(m.group(0))
            except Exception:
                words = re.findall(r'"([a-zA-Z]{3,})"', after_words_raw)
            return {
                "ready":      True,
                "tuning_type":"filter",
                "words_to_add": words,
                "target_file": str(engine_file),
                "message":    f"Will add {words} to OffTopicFilter.GLOBAL_KILL"
            }

        # For prompt_edit / scoring_rule: use DeepSeek to write the code change
        try:
            engine_code = engine_file.read_text(encoding="utf-8") if engine_file.exists() else ""
            prompt = f"""Fix this SEO engine function.

Engine: {t['engine_file']}
Function: {t['fn_target']}
Problem: {t['problem']}
Fix needed: {t['fix_description']}

Current code relevant section:
{engine_code[:2000] if engine_code else 'code not available'}

Write the minimal change to {t['fn_target']} that fixes this problem.
Add comment: # LN-FIX: {tuning_id[:12]}
Return only the modified function or the specific lines to add/change."""

            from core.ai_config import AIRouter
            code_change = AIRouter._call_ollama(prompt, "You are a Python SEO engine developer.", 0.1)
            if code_change:
                code_change = code_change.strip()
                self._db._db.execute(
                    "UPDATE ln_targeted_tunings SET after_value=? WHERE tuning_id=?",
                    (code_change[:5000], tuning_id)
                )
                self._db._db.commit()
                return {
                    "ready":       True,
                    "tuning_type": t["tuning_type"],
                    "code_change": code_change[:1000],
                    "target_file": str(engine_file),
                    "target_fn":   t["fn_target"],
                }
        except Exception as e:
            log.warning(f"DeepSeek code generation failed: {e}")

        return {"ready": False, "message": "Manual code change required",
                "fix_description": t["fix_description"]}

    def claude_verify(self, tuning_id: str) -> dict:
        """Claude verifies the targeted tuning before approval."""
        key = os.getenv("ANTHROPIC_API_KEY","")
        row = self._db._db.execute(
            "SELECT * FROM ln_targeted_tunings WHERE tuning_id=?", (tuning_id,)
        ).fetchone()
        if not row or not key:
            return {"recommendation":"needs_manual_review","confidence":0}

        t = dict(row)
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            r = client.messages.create(
                model=os.getenv("CLAUDE_MODEL","claude-sonnet-4-6"),
                max_tokens=400,
                messages=[{"role":"user","content":f"""Review this targeted SEO engine fix.

Problem: {t['problem']}
Phase targeted: {t['phase']} → {t['fn_target']}
Fix type: {t['tuning_type']}
Evidence: {t.get('evidence','[]')}

Proposed change:
{t.get('after_value','')[:600]}

Is this fix correct, targeted, and safe? Will it prevent the reported issue without breaking other engines?

Return JSON: {{"recommendation":"approve|reject","confidence":0-100,"concerns":[],"notes":"..."}}"""}]
            )
            text = r.content[0].text.strip()
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                result = json.loads(m.group(0))
                self._db._db.execute(
                    "UPDATE ln_targeted_tunings SET claude_notes=? WHERE tuning_id=?",
                    (json.dumps(result), tuning_id)
                )
                self._db._db.commit()
                return result
        except Exception as e:
            log.warning(f"Claude verify failed: {e}")
        return {"recommendation":"needs_manual_review","confidence":50}

    def apply(self, tuning_id: str, approved_by: str) -> Tuple[bool, str]:
        """Apply approved tuning to the engine file."""
        row = self._db._db.execute(
            "SELECT * FROM ln_targeted_tunings WHERE tuning_id=?", (tuning_id,)
        ).fetchone()
        if not row:
            return False, "Tuning not found"

        t    = dict(row)
        prep = self.prepare(tuning_id)

        if t["tuning_type"] == "filter" and prep.get("words_to_add"):
            # Apply to annaseo_addons.py OffTopicFilter
            success, msg = self._apply_filter_words(
                prep["words_to_add"], tuning_id
            )
        else:
            success = True
            msg = f"Manual application required for {t['tuning_type']}: see after_value in DB"

        if success:
            self._db._db.execute(
                "UPDATE ln_targeted_tunings SET status='applied', approved_by=?, approved_at=? WHERE tuning_id=?",
                (approved_by, datetime.utcnow().isoformat(), tuning_id)
            )
            self._db._db.commit()
        return success, msg

    def _apply_filter_words(self, words: list, tuning_id: str) -> Tuple[bool, str]:
        """Add words to OffTopicFilter.GLOBAL_KILL."""
        import re as _re
        addons = Path(os.getenv("ENGINES_DIR","./")) / "annaseo_addons.py"
        if not addons.exists():
            return False, "annaseo_addons.py not found"
        try:
            code = addons.read_text(encoding="utf-8")
            # Find GLOBAL_KILL list
            m = _re.search(r'(GLOBAL_KILL\s*=\s*\[)([^\]]*?)(\])', code, _re.DOTALL)
            if not m:
                return False, "GLOBAL_KILL list not found"
            existing = m.group(2)
            new_words = "\n        ".join(
                f'"{w}",' for w in words if f'"{w}"' not in existing
            )
            if not new_words:
                return True, "Words already in kill list"
            # Save rollback
            snap = Path(os.getenv("VERSIONS_DIR","./rsd_versions")) / f"addons_ln_{tuning_id}_pre.py"
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(code, encoding="utf-8")
            # Apply
            new_list = m.group(1) + existing.rstrip() + f"\n        {new_words}\n        # LN-FIX: {tuning_id[:12]}\n    " + m.group(3)
            addons.write_text(code[:m.start()] + new_list + code[m.end():], encoding="utf-8")
            # Save rollback path
            self._db._db.execute(
                "UPDATE ln_targeted_tunings SET rollback_value=? WHERE tuning_id=?",
                (str(snap), tuning_id)
            )
            self._db._db.commit()
            return True, f"Added {len(words)} words to OffTopicFilter: {words}"
        except Exception as e:
            return False, str(e)

    def rollback(self, tuning_id: str, rolled_back_by: str) -> Tuple[bool, str]:
        """Rollback a tuning using saved snapshot."""
        row = self._db._db.execute(
            "SELECT * FROM ln_targeted_tunings WHERE tuning_id=?", (tuning_id,)
        ).fetchone()
        if not row:
            return False, "Not found"
        t    = dict(row)
        snap = Path(t.get("rollback_value",""))
        if not snap.exists():
            return False, "Rollback snapshot not found"

        engine_file = Path(os.getenv("ENGINES_DIR","./")) / t.get("engine_file","")
        if engine_file.exists():
            engine_file.write_text(snap.read_text(encoding="utf-8"), encoding="utf-8")
        self._db._db.execute(
            "UPDATE ln_targeted_tunings SET status='rolled_back' WHERE tuning_id=?",
            (tuning_id,)
        )
        self._db._db.commit()
        return True, f"Rolled back tuning {tuning_id}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — MASTER LINEAGE ENGINE (Ruflo job types)
# ─────────────────────────────────────────────────────────────────────────────

class LineageEngine:
    """
    Master engine. Ruflo calls via job queue.

    Job types:
      ln_register_run      — start a new project run, get run_id
      ln_mark_bad          — user marks item bad with reason → auto-analyse
      ln_mark_good         — user marks item good
      ln_phase_report      — quality score of every phase
      ln_degradation_events— list all degradation events
      ln_prepare_tuning    — generate code change for tuning
      ln_verify_tuning     — Claude verifies tuning
      ln_approve_tuning    — approve + apply
      ln_rollback_tuning   — rollback
      ln_dashboard         — full dashboard state
    """

    def __init__(self):
        self._db       = LineageDB()
        self._analyser = DegradationAnalyser()
        self._reporter = PhaseQualityReporter()
        self._applicator= TargetedTuningApplicator()

    def job_register_run(self, project_id: str, seed: str) -> str:
        """Create a new run_id for a project execution."""
        run_id = f"run_{hashlib.md5(f'{project_id}{seed}{time.time()}'.encode()).hexdigest()[:12]}"
        self._db._db.execute(
            "INSERT OR IGNORE INTO ln_run_registry (run_id, project_id, seed) VALUES (?,?,?)",
            (run_id, project_id, seed)
        )
        self._db._db.commit()
        return run_id

    def job_mark_bad(self, trace_id: str, project_id: str,
                      reason: str) -> dict:
        """User marks item as bad → trigger degradation analysis → create tuning."""
        self._db.mark_label(trace_id, "bad", 0.0)
        result = self._analyser.analyse(trace_id, reason, project_id)

        # Auto-prepare if filter type (simple enough to auto-do)
        if result.get("tuning_type") == "filter":
            prep = self._applicator.prepare(result["tuning_id"])
            result["prepared"] = prep

        return result

    def job_mark_good(self, trace_id: str) -> dict:
        self._db.mark_label(trace_id, "good", 100.0)
        return {"marked": "good", "trace_id": trace_id}

    def job_phase_report(self, project_id: str = None) -> List[dict]:
        return self._reporter.report(project_id)

    def job_worst_phases(self, project_id: str = None,
                          top_n: int = 5) -> List[dict]:
        return self._reporter.report(project_id)[:top_n]

    def job_degradation_events(self, project_id: str = None) -> List[dict]:
        return self._db.get_degradation_events(project_id)

    def job_prepare_tuning(self, tuning_id: str) -> dict:
        return self._applicator.prepare(tuning_id)

    def job_verify_tuning(self, tuning_id: str) -> dict:
        return self._applicator.claude_verify(tuning_id)

    def job_approve_tuning(self, tuning_id: str, approved_by: str) -> dict:
        ok, msg = self._applicator.apply(tuning_id, approved_by)
        return {"success": ok, "message": msg}

    def job_rollback_tuning(self, tuning_id: str, rolled_back_by: str) -> dict:
        ok, msg = self._applicator.rollback(tuning_id, rolled_back_by)
        return {"success": ok, "message": msg}

    def job_dashboard(self, project_id: str = None) -> dict:
        """Full lineage dashboard for the Quality tab."""
        phase_report = self._reporter.report(project_id)
        degradation  = self._db.get_degradation_events(project_id)
        pending      = self._db.get_pending_tunings()
        traces       = self._db.get_traces(project_id=project_id,
                                            label="bad", limit=20)
        return {
            "phase_quality":     phase_report,
            "worst_phase":       phase_report[0] if phase_report else None,
            "degradation_events":degradation[:10],
            "pending_tunings":   pending,
            "bad_items":         traces,
            "summary": {
                "phases_tracked": len(set(p["phase"] for p in phase_report)),
                "total_degradations": len(degradation),
                "pending_tunings": len(pending),
                "critical_phases": [p for p in phase_report if p["status"]=="critical"],
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from pydantic import BaseModel as PM
    from typing import Optional as Opt, List as L
    import re

    app = FastAPI(title="AnnaSEO Lineage Engine",
                  description="Data lineage tracking, degradation detection, targeted engine tuning")

    le = LineageEngine()

    class MarkBadBody(PM):
        trace_id:   str
        project_id: str
        reason:     str

    class ApproveBody(PM):
        approved_by: str

    @app.post("/api/ln/runs/{project_id}", tags=["Lineage"])
    def register_run(project_id: str, seed: str = ""):
        return {"run_id": le.job_register_run(project_id, seed)}

    @app.get("/api/ln/dashboard", tags=["Lineage"])
    def dashboard(project_id: Opt[str] = None):
        return le.job_dashboard(project_id)

    @app.get("/api/ln/phases", tags=["Lineage"])
    def phase_report(project_id: Opt[str] = None):
        return le.job_phase_report(project_id)

    @app.get("/api/ln/traces", tags=["Lineage"])
    def traces(project_id: Opt[str] = None, item_type: Opt[str] = None,
                label: Opt[str] = None, phase: Opt[str] = None, limit: int = 50):
        return le._db.get_traces(project_id, item_type, label, phase, limit)

    @app.post("/api/ln/mark/bad", tags=["Lineage"])
    def mark_bad(body: MarkBadBody, bg: BackgroundTasks):
        bg.add_task(le.job_mark_bad, body.trace_id, body.project_id, body.reason)
        return {"status":"started","message":"Degradation analysis started — tuning will appear in pending list"}

    @app.post("/api/ln/mark/good/{trace_id}", tags=["Lineage"])
    def mark_good(trace_id: str):
        return le.job_mark_good(trace_id)

    @app.get("/api/ln/degradation", tags=["Lineage"])
    def degradation_events(project_id: Opt[str] = None):
        return le.job_degradation_events(project_id)

    @app.get("/api/ln/tunings", tags=["Lineage"])
    def tunings(status: Opt[str] = None):
        if status:
            return [dict(r) for r in le._db._db.execute(
                "SELECT * FROM ln_targeted_tunings WHERE status=? ORDER BY created_at DESC",
                (status,)
            ).fetchall()]
        return le._db.get_pending_tunings()

    @app.post("/api/ln/tunings/{tid}/prepare", tags=["Lineage"])
    def prepare_tuning(tid: str):
        return le.job_prepare_tuning(tid)

    @app.post("/api/ln/tunings/{tid}/verify", tags=["Lineage"])
    def verify_tuning(tid: str):
        return le.job_verify_tuning(tid)

    @app.post("/api/ln/tunings/{tid}/approve", tags=["Lineage"])
    def approve_tuning(tid: str, body: ApproveBody):
        return le.job_approve_tuning(tid, body.approved_by)

    @app.post("/api/ln/tunings/{tid}/rollback", tags=["Lineage"])
    def rollback_tuning(tid: str, rolled_back_by: str = "admin"):
        return le.job_rollback_tuning(tid, rolled_back_by)

    @app.get("/api/ln/phase-map", tags=["Lineage"])
    def phase_map():
        return PHASE_MAP

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, re

    HELP = """
AnnaSEO — Data Lineage & Engine Attribution Engine
─────────────────────────────────────────────────────────────
Traces every item through all 20 phases.
Finds EXACTLY which engine/phase/function produced bad output.
Generates targeted fix for that specific location.

Usage:
  python annaseo_lineage_engine.py demo              # full cinnamon tour demo
  python annaseo_lineage_engine.py phases            # show all phase quality
  python annaseo_lineage_engine.py dashboard         # full dashboard
  python annaseo_lineage_engine.py mark bad <trace_id> "<reason>"
  python annaseo_lineage_engine.py mark good <trace_id>
  python annaseo_lineage_engine.py tunings           # pending tunings
  python annaseo_lineage_engine.py approve <tid> <name>
  python annaseo_lineage_engine.py rollback <tid>
  python annaseo_lineage_engine.py api               # FastAPI on :8007

Integration (add to each engine):
  from annaseo_lineage_engine import Tracer
  tracer = Tracer(run_id, project_id, seed)
  with tracer.phase("P2_KeywordExpansion") as t:
      kws = self._google_autosuggest(seed)
      t.emit_batch("keyword", kws, fn="_google_autosuggest", source="google_autosuggest")
"""
    if len(sys.argv) < 2: print(HELP); exit(0)
    cmd = sys.argv[1]
    le  = LineageEngine()

    if cmd == "demo":
        print("\n  DEMO — Cinnamon tour complete lineage trace")
        print("  " + "─"*52)

        # 1. Register a run
        run_id = le.job_register_run("proj_cinnamon_demo", "cinnamon")
        print(f"\n  Run ID: {run_id}")

        # 2. Simulate P2 producing "cinnamon tour" from Google autosuggest
        db = LineageDB()
        t1 = TraceEnvelope(
            value="cinnamon tour", item_type="keyword",
            run_id=run_id, project_id="proj_cinnamon_demo", seed="cinnamon",
            origin_phase="P2_KeywordExpansion",
            origin_fn="_google_autosuggest",
            origin_source="google_autosuggest",
        )
        t1.add_transformation("P2_KeywordExpansion","_google_autosuggest","fetched",step=1)
        t1.add_transformation("P3_Normalization","run","passed_through",step=2,detail="no filter match")
        t1.add_transformation("OffTopicFilter","filter","passed_through",step=3,detail="'tour' not in kill list")
        t1.add_transformation("P8_TopicDetection","_name_topic","clustered_into:Cinnamon_Tourism",step=4)
        t1.add_transformation("P10_PillarIdentification","run","selected_as_pillar",step=5)
        db.save_trace(t1)
        print(f"\n  Trace saved: {t1.trace_id()}")
        print(f"  Item: '{t1.value}' originated at {t1.origin_phase}.{t1.origin_fn}")
        print(f"  Transformation path:")
        for tr in t1.transformations:
            print(f"    Step {tr.step}: {tr.phase}.{tr.fn} → {tr.action}")

        # 3. Find degradation point
        dp = t1.degradation_point()
        print(f"\n  Degradation point: {dp.phase}.{dp.fn} (should have caught it here)")

        # 4. User marks bad
        print(f"\n  User marks bad: 'Tour has nothing to do with spices'")
        result = le.job_mark_bad(
            t1.trace_id(),
            "proj_cinnamon_demo",
            "Tour has nothing to do with spices. This is a tourism keyword not relevant to cinnamon business."
        )
        print(f"\n  Tuning generated:")
        print(f"    Target:  {result.get('degradation_at')}.{result.get('fix_fn')}")
        print(f"    Type:    {result.get('tuning_type')}")
        print(f"    Fix:     {result.get('fix_description','')[:80]}")
        print(f"    Tuning ID: {result.get('tuning_id')}")

        # 5. Phase report
        print(f"\n  Phase quality report:")
        report = le.job_phase_report("proj_cinnamon_demo")
        for p in report[:5]:
            print(f"    {p['phase']:30} quality={p['quality_score']:.0f} bad={p['bad_count']}")

        print(f"\n  Demo complete. Run 'approve {result.get('tuning_id')} admin' to apply the fix.")

    elif cmd == "phases":
        report = le.job_phase_report()
        print(f"\n  PHASE QUALITY REPORT")
        print("  " + "─"*60)
        for p in report:
            icon = "✗" if p["status"]=="critical" else "⚠" if p["status"]=="degraded" else "✓"
            print(f"  {icon} {p['phase']:32} quality={p['quality_score']:5.1f} bad={p['bad_count']} total={p['total_items']}")

    elif cmd == "dashboard":
        d = le.job_dashboard()
        s = d["summary"]
        print(f"\n  Phases tracked: {s['phases_tracked']} | Degradations: {s['total_degradations']} | Pending tunings: {s['pending_tunings']}")
        if s['critical_phases']:
            print(f"\n  CRITICAL phases:")
            for p in s['critical_phases']:
                print(f"    ✗ {p['phase']} — {p['bad_rate_pct']:.1f}% bad rate")

    elif cmd == "mark":
        if len(sys.argv) < 4: print("Usage: mark bad|good <trace_id> [reason]"); exit(1)
        label, tid = sys.argv[2], sys.argv[3]
        if label == "bad":
            reason = sys.argv[4] if len(sys.argv) > 4 else "marked bad by user"
            print(json.dumps(le.job_mark_bad(tid, "", reason), indent=2))
        else:
            print(json.dumps(le.job_mark_good(tid), indent=2))

    elif cmd == "tunings":
        pending = le._db.get_pending_tunings()
        print(f"\n  {len(pending)} pending tunings:")
        for t in pending:
            print(f"  [{t['tuning_type']:12}] {t['tuning_id'][:16]} {t['phase']}.{t['fn_target'][:30]} — {t['problem'][:50]}")

    elif cmd == "approve":
        if len(sys.argv) < 4: print("Usage: approve <tuning_id> <your_name>"); exit(1)
        print(json.dumps(le.job_approve_tuning(sys.argv[2], sys.argv[3]), indent=2))

    elif cmd == "rollback":
        if len(sys.argv) < 3: print("Usage: rollback <tuning_id>"); exit(1)
        print(json.dumps(le.job_rollback_tuning(sys.argv[2], "cli_user"), indent=2))

    elif cmd == "api":
        try:
            import uvicorn
            print("Lineage Engine API at http://localhost:8007")
            uvicorn.run("annaseo_lineage_engine:app", host="0.0.0.0", port=8007, reload=True)
        except ImportError:
            print("pip install uvicorn")
    else:
        print(f"Unknown: {cmd}\n{HELP}")

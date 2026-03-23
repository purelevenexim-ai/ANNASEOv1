"""
================================================================================
ANNASEO — QUALITY INTELLIGENCE ENGINE  (annaseo_qi_engine.py)
================================================================================
One file. Replaces: annaseo_data_store.py, annaseo_quality_engine.py,
                     annaseo_lineage_engine.py  (all three merged here)

The problem this solves precisely
───────────────────────────────────
  User sees "cinnamon tour" as a pillar. Marks it Bad.
  System must answer: WHICH exact engine, class, function, and prompt
  produced that keyword — and tune only that location, nothing else.

The answer after reading every engine file:
  "cinnamon tour" was fetched by P2_KeywordExpansion._google_autosuggest()
  → passed P3_Normalization (no filter matched)
  → passed OffTopicFilter (GLOBAL_KILL has "tour" missing — list covers social
    media / furniture / DIY but not tourism words)
  → P5_IntentClassification._classify() returned "informational" (no tourism
    signal words in RULES dict)
  → P8_TopicDetection._name_topic() called deepseek which named the cluster
    "Cinnamon Tourism" from the top-5 keywords
  → P10_PillarIdentification.run() called Gemini with PILLAR_PROMPT which
    has no instruction to exclude off-domain cluster names
  → P9 cluster survived into pillars because no domain relevance gate exists

Fix targets (in order of where to add the gate):
  1. OffTopicFilter.GLOBAL_KILL  → add: tour, travel, trip, tourism, holiday
     (annaseo_addons.py line 150)
  2. P10_PillarIdentification.PILLAR_PROMPT → add domain exclusion instruction
     (ruflo_20phase_engine.py line 1070)
  3. P5_IntentClassification.RULES → add "tour","trip" to noise/skip category
     (ruflo_20phase_engine.py line 782)

Content quality degradation points (from reading ruflo_content_engine.py):
  Low E-E-A-T  → _heuristic_eeat() or DeepSeek Pass 5
                 Fix: strengthen Layer 1 system prompt to require first-person
                 signals every 300 words + HITL injection
  Low GEO      → GEOScorer.score() rules-based check
                 Fix: content prompt must include "start each H2 with a
                 direct answer + specific number"
  AI watermarks → Pass 7 humanize only triggers if score<75
                 Fix: lower threshold to 65 or always run scrubber

Data collected at each phase
──────────────────────────────
  P2   → raw_keywords (list of strings, per source)
  P3   → clean_keywords (after normalisation)
  OTF  → filtered_out list + kept list (OffTopicFilter)
  P4   → entity_map per keyword
  P5   → intent_map per keyword
  P6   → serp_data per keyword
  P7   → scored_keywords (0-100 per kw)
  P8   → topic_map (cluster_name → [keywords])
  P9   → cluster_map (cluster_name → [topic_names])
  P10  → pillars dict (cluster → pillar_title + pillar_keyword)
  P15  → content_brief per article
  P16  → article_draft (raw Claude output)
  P17  → seo_score + issues list (28 signals)
  GEO  → geo_score + geo_signals
  EEAT → eeat_score
  P19  → published result

AI Usage
─────────
  Gemini 1.5 Flash  → quality scoring, fix spec (free tier)
  Groq Llama        → test generation (free tier)
  DeepSeek local    → code/prompt fixes (Ollama, free)
  Claude Sonnet     → final verification ONLY, never coding
================================================================================
"""

from __future__ import annotations

import os, re, json, time, hashlib, sqlite3, logging, traceback, ast
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager

import requests as _req

log = logging.getLogger("annaseo.qi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

DB_PATH      = Path(os.getenv("ANNASEO_DB",     "./annaseo.db"))
ENGINES_DIR  = Path(os.getenv("ENGINES_DIR",    "./"))
VERSIONS_DIR = Path(os.getenv("VERSIONS_DIR",   "./rsd_versions"))
OLLAMA_URL   = os.getenv("OLLAMA_URL",           "http://localhost:11434")
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — ENGINE ANATOMY
# Authoritative map: every phase → file → class → known failure modes → fix type
# Built by reading every engine file directly.
# ─────────────────────────────────────────────────────────────────────────────

ENGINE_ANATOMY: Dict[str, dict] = {

    # ── Keyword pipeline: ruflo_20phase_engine.py ──────────────────────────

    "P2_KeywordExpansion": {
        "file":    "ruflo_20phase_engine.py",
        "class":   "P2_KeywordExpansion",
        "methods": ["_google_autosuggest","_youtube_autosuggest","_amazon_autosuggest",
                    "_duckduckgo","_reddit_titles","_question_variants"],
        "output":  "raw_keywords: List[str]",
        "failure_modes": [
            ("tourism/travel words from google autosuggest for product seeds",
             "source_filter", "_google_autosuggest",
             "Add domain check: if seed is food/product, reject tourism keywords from autosuggest"),
            ("competitor brand names fetched",
             "filter", "OffTopicFilter.GLOBAL_KILL",
             "Add competitor brand names to seed_kill_words"),
            ("irrelevant question variants e.g. 'what is cinnamon tour'",
             "filter", "_question_variants",
             "Filter question variants through domain relevance check"),
        ],
    },

    "P3_Normalization": {
        "file":    "ruflo_20phase_engine.py",
        "class":   "P3_Normalization",
        "methods": ["run","_normalise"],
        "output":  "clean_keywords: List[str]",
        "failure_modes": [
            ("near-duplicates surviving dedup (85% threshold too loose)",
             "parameter", "similarity_threshold",
             "Lower similarity threshold from 0.85 to 0.80 for stricter dedup"),
        ],
    },

    "OffTopicFilter": {
        "file":    "annaseo_addons.py",
        "class":   "OffTopicFilter",
        "methods": ["filter","filter_with_reason","add_seed_kill_words"],
        "config":  "GLOBAL_KILL list at line 150",
        "output":  "kept_keywords, removed_keywords",
        "current_kill_list": [
            "challenge","meme","viral","tiktok","instagram","reddit","twitter","youtube",
            "furniture","paint","color","candle","perfume","air freshener","decoration",
            "wallpaper","nail","polish","lipstick","makeup",
            "pest control","insect","cockroach","moth","repellent","ant",
            "craft","diy","sewing","knitting","crochet",
            "game","sports","jersey","team",
            "free download","crack","torrent","pirate","hack",
        ],
        "failure_modes": [
            ("tourism words not in kill list: tour, travel, trip, resort, hotel, vacation",
             "filter", "GLOBAL_KILL",
             "Add: tour, travel, trip, tourism, resort, hotel, vacation, holiday, flight, booking"),
            ("product seed getting travel sub-niche (spice tours, factory visits)",
             "filter", "GLOBAL_KILL",
             "Add: tour, factory tour, plantation visit, tour guide, visitor"),
        ],
    },

    "P5_IntentClassification": {
        "file":    "ruflo_20phase_engine.py",
        "class":   "P5_IntentClassification",
        "methods": ["run","_classify"],
        "config":  "RULES dict at line 782 — rule-based, no AI",
        "output":  "intent_map: Dict[str, str]",
        "current_rules": {
            "transactional": ["buy","order","purchase","price","cheap","discount","shop",
                              "wholesale","bulk","delivery","near me","online","cost"],
            "commercial":    ["best","top","review","compare","vs","versus","alternative",
                              "recommendation","which","ranking","rated","test"],
            "informational": ["what","how","why","when","does","is","are","can","benefits",
                              "uses","effects","meaning","definition","guide","truth",
                              "science","study","research"],
        },
        "failure_modes": [
            ("tourism keywords classified as 'informational' (no noise/skip category)",
             "scoring_rule", "RULES",
             "Add 'skip' intent category with signals: tour, travel, visit, tourist — skip these keywords"),
            ("'cinnamon tour' returns 'informational' (default fallback)",
             "scoring_rule", "_classify",
             "Add noise detection: if keyword has no product signals + has travel/tourism signal → skip"),
        ],
    },

    "P8_TopicDetection": {
        "file":    "ruflo_20phase_engine.py",
        "class":   "P8_TopicDetection",
        "methods": ["run","_name_topic"],
        "config":  "KMeans k = max(5, min(80, len(keywords)//12)). _name_topic uses DeepSeek",
        "output":  "topic_map: Dict[str, List[str]]",
        "failure_modes": [
            ("off-topic keywords surviving into clusters (SBERT embeds tourism near spices)",
             "prompt_edit", "_name_topic",
             "After naming topic, validate: if topic name contains travel/tourism words → merge into noise cluster"),
            ("cluster named 'Cinnamon Tourism' by DeepSeek (no domain constraint in prompt)",
             "prompt_edit", "_name_topic",
             "Add to _name_topic prompt: 'Only name topics relevant to the business domain. Reject tourism/travel topics.'"),
        ],
    },

    "P9_ClusterFormation": {
        "file":    "ruflo_20phase_engine.py",
        "class":   "P9_ClusterFormation",
        "methods": ["run"],
        "config":  "CLUSTER_PROMPT uses Gemini. n_clusters = max(3, len(topics)//4)",
        "output":  "cluster_map: Dict[str, List[str]]",
        "failure_modes": [
            ("Gemini groups off-topic topics into a cluster (no domain filter in prompt)",
             "prompt_edit", "CLUSTER_PROMPT",
             "Add to CLUSTER_PROMPT: 'Exclude any tourism, travel, or non-product topics. Only group product-relevant topics.'"),
        ],
    },

    "P10_PillarIdentification": {
        "file":    "ruflo_20phase_engine.py",
        "class":   "P10_PillarIdentification",
        "methods": ["run"],
        "config":  "PILLAR_PROMPT uses Gemini at temperature=0.2. No domain exclusion in prompt.",
        "output":  "pillars: Dict[str, dict] with pillar_title, pillar_keyword, topics",
        "failure_modes": [
            ("PILLAR_PROMPT has no instruction to exclude off-domain clusters",
             "prompt_edit", "PILLAR_PROMPT",
             "Add to PILLAR_PROMPT: 'If the cluster topic is not directly related to the seed product, return SKIP.'"),
            ("pillar_keyword = cluster_name.lower() — inherits bad cluster name directly",
             "scoring_rule", "run",
             "Add post-processing: filter pillars through OffTopicFilter before returning"),
        ],
    },

    # ── Content pipeline: ruflo_content_engine.py ──────────────────────────

    "P15_ContentBrief": {
        "file":    "ruflo_20phase_engine.py",
        "class":   "P15_ContentBrief",
        "methods": ["run"],
        "output":  "content_brief: dict with h1, h2s, faqs, entities, internal_links",
        "failure_modes": [
            ("DeepSeek generates generic H2 structure not aligned to SERP competitors",
             "prompt_edit", "_build_brief",
             "Inject top 3 SERP competitor H2 headings into brief prompt as required coverage"),
            ("FAQ questions are generic (what is X, how does X work) without specific angles",
             "prompt_edit", "_build_brief",
             "Add to brief prompt: FAQs must address specific user pain points, not generic definitions"),
        ],
    },

    "P16_Claude_Content": {
        "file":    "ruflo_content_engine.py",
        "class":   "ContentGenerationEngine",
        "methods": ["generate","_research","_build_brief"],
        "config":  "7 passes. Pass 3 = Claude write. Pass 7 = humanize if score<75",
        "output":  "GeneratedArticle with body, seo_score, eeat_score, geo_score",
        "failure_modes": [
            ("AI watermark patterns: furthermore, certainly, delve, it's worth noting",
             "prompt_edit", "Layer1_system_prompt",
             "Add to Layer 1 system prompt: 'Never use: furthermore, certainly, delve, it is worth noting, in conclusion, tapestry, crucial'"),
            ("Generic content lacking first-person expertise signals (low E-E-A-T)",
             "prompt_edit", "Layer1_system_prompt",
             "Add: 'Every 300 words, include one first-person experience signal: In our testing, Our customers report, We have found'"),
            ("Pass 7 humanize threshold too high (only triggers at <75, should be <80)",
             "parameter", "PUBLISH_THRESHOLD",
             "Lower humanize trigger from score<75 to score<80 for stricter quality"),
            ("Low GEO: H2 sections lack direct answers and specific numbers",
             "prompt_edit", "Layer1_system_prompt",
             "Add: 'Begin every H2 with a direct answer in the first sentence. Include at least one specific number or statistic per H2.'"),
        ],
    },

    "SEOScorer_P17": {
        "file":    "ruflo_content_engine.py",
        "class":   "SEOScorer",
        "methods": ["score","_score"],
        "config":  "28 signals checked. Publish threshold 75.",
        "output":  "seo_score (0-100), issues list",
        "failure_modes": [
            ("Score passes at 76 but content still keyword-stuffed",
             "parameter", "keyword_density_threshold",
             "Tighten keyword density check: flag if >3% density (currently missing upper bound)"),
            ("Word count check missing minimum for pillar articles",
             "scoring_rule", "_score",
             "Add: pillar articles must be >=2500 words; supporting >=1500 words"),
        ],
    },

    "GEOScorer": {
        "file":    "ruflo_content_engine.py",
        "class":   "GEOScorer",
        "methods": ["score"],
        "config":  "Rule-based. 8 AI citation signals checked.",
        "output":  "geo_score (0-100)",
        "failure_modes": [
            ("Articles lack AI-citable passages (134-167 word self-contained sections)",
             "scoring_rule", "score",
             "Add check: count paragraphs 130-170 words that contain a fact+source. Penalise if <3 such paragraphs"),
            ("No structured direct-answer blocks (what Perplexity cites)",
             "scoring_rule", "score",
             "Check for bold text following H2 that answers the heading directly. Penalise if missing"),
        ],
    },

    "EEATScorer": {
        "file":    "ruflo_content_engine.py",
        "class":   "EEATScorer",
        "methods": ["score","_heuristic_eeat"],
        "config":  "Pass 5 uses DeepSeek. _heuristic_eeat is rule-based fallback.",
        "output":  "eeat_score (0-100)",
        "failure_modes": [
            ("DeepSeek unavailable → _heuristic_eeat gives 65 baseline with no real check",
             "scoring_rule", "_heuristic_eeat",
             "Strengthen heuristic: count first-person phrases, author credentials references, study citations"),
            ("No author bio injection into articles",
             "prompt_edit", "Layer2_brand_prompt",
             "Add author credentials to Layer 2 brand context so Claude can inject them naturally"),
        ],
    },

    "StrategyDevEngine": {
        "file":    "ruflo_strategy_dev_engine.py",
        "class":   "StrategyDevelopmentEngine",
        "methods": ["run"],
        "output":  "strategy dict with personas, context, calendar plan",
        "failure_modes": [
            ("Personas don't match actual target market for the business type",
             "prompt_edit", "AudienceIntelligenceEngine",
             "Add business type validation: if type=spice_export, force B2B buyer persona alongside consumer"),
            ("Location/religion context not applied to keyword angles",
             "prompt_edit", "ContextEngine",
             "Add explicit instruction to apply religion/location context to all keyword categories"),
        ],
    },

    "ConfirmationPipeline": {
        "file":    "ruflo_confirmation_pipeline.py",
        "class":   "ConfirmationPipeline",
        "output":  "user_confirmed_strategy through 5 gates",
        "failure_modes": [
            ("Gate 3 shows D3 keyword tree with bad pillars — user first sees issue here",
             "scoring_rule", "Gate3_display",
             "Pre-filter: run OffTopicFilter on all pillars before Gate 3 display"),
            ("Similarity threshold for universe classification too loose (0.70-0.85 ambiguous zone)",
             "parameter", "SIMILARITY_THRESHOLD",
             "Widen ambiguous zone: 0.65-0.88 → always ask user for ambiguous items"),
        ],
    },
}

# Flat phase order (P1→P20 + modules) for flow tracking
PHASE_ORDER = [
    "P2_KeywordExpansion", "P3_Normalization", "OffTopicFilter",
    "P4_EntityDetection",  "P5_IntentClassification", "P6_SERPIntelligence",
    "P7_OpportunityScoring","P8_TopicDetection","P9_ClusterFormation",
    "P10_PillarIdentification","P11_KnowledgeGraph","P12_InternalLinking",
    "P13_ContentCalendar","P14_DedupPrevention",
    "P15_ContentBrief","P16_Claude_Content","SEOScorer_P17",
    "GEOScorer","EEATScorer","P19_Publishing","P20_RankingFeedback",
    "StrategyDevEngine","ConfirmationPipeline",
]

# For each item_type, which phases are the natural filter gates
FILTER_GATES: Dict[str, List[str]] = {
    "keyword":   ["OffTopicFilter","P3_Normalization","P5_IntentClassification","P7_OpportunityScoring"],
    "pillar":    ["OffTopicFilter","P9_ClusterFormation","P10_PillarIdentification"],
    "cluster":   ["P9_ClusterFormation","P8_TopicDetection"],
    "article":   ["SEOScorer_P17","GEOScorer","EEATScorer","P16_Claude_Content"],
    "brief":     ["P15_ContentBrief"],
    "meta_title":["SEOScorer_P17"],
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DATABASE (single schema, shared annaseo.db)
# ─────────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS qi_raw_outputs (
        output_id   TEXT PRIMARY KEY,
        run_id      TEXT NOT NULL,
        project_id  TEXT NOT NULL,
        phase       TEXT NOT NULL,
        fn          TEXT DEFAULT '',
        item_type   TEXT NOT NULL,
        item_value  TEXT NOT NULL,
        item_meta   TEXT DEFAULT '{}',
        trace_path  TEXT DEFAULT '[]',
        quality_label TEXT DEFAULT 'unreviewed',
        quality_score REAL,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS qi_phase_snapshots (
        snap_id     TEXT PRIMARY KEY,
        run_id      TEXT NOT NULL,
        project_id  TEXT NOT NULL,
        phase       TEXT NOT NULL,
        raw_output  TEXT NOT NULL,
        items_count INTEGER DEFAULT 0,
        exec_ms     REAL DEFAULT 0,
        mem_mb      REAL DEFAULT 0,
        errors      TEXT DEFAULT '[]',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS qi_user_feedback (
        fb_id       TEXT PRIMARY KEY,
        output_id   TEXT NOT NULL,
        project_id  TEXT NOT NULL,
        label       TEXT NOT NULL,
        reason      TEXT DEFAULT '',
        fix_hint    TEXT DEFAULT '',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS qi_degradation_events (
        event_id         TEXT PRIMARY KEY,
        output_id        TEXT NOT NULL,
        project_id       TEXT NOT NULL,
        item_type        TEXT NOT NULL,
        item_value       TEXT NOT NULL,
        origin_phase     TEXT NOT NULL,
        origin_fn        TEXT NOT NULL,
        degradation_phase TEXT NOT NULL,
        degradation_fn    TEXT NOT NULL,
        failure_mode      TEXT NOT NULL,
        user_reason       TEXT DEFAULT '',
        created_at        TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS qi_tunings (
        tuning_id     TEXT PRIMARY KEY,
        event_id      TEXT,
        phase         TEXT NOT NULL,
        fn_target     TEXT NOT NULL,
        engine_file   TEXT NOT NULL,
        tuning_type   TEXT NOT NULL,
        problem       TEXT NOT NULL,
        fix           TEXT NOT NULL,
        before_value  TEXT DEFAULT '',
        after_value   TEXT DEFAULT '',
        evidence      TEXT DEFAULT '[]',
        status        TEXT DEFAULT 'pending',
        approved_by   TEXT DEFAULT '',
        approved_at   TEXT DEFAULT '',
        reject_reason TEXT DEFAULT '',
        rollback_snap TEXT DEFAULT '',
        claude_notes  TEXT DEFAULT '{}',
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS qi_runs (
        run_id      TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        seed        TEXT DEFAULT '',
        phases_done TEXT DEFAULT '[]',
        started_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_qi_raw_project ON qi_raw_outputs(project_id);
    CREATE INDEX IF NOT EXISTS idx_qi_raw_phase   ON qi_raw_outputs(phase);
    CREATE INDEX IF NOT EXISTS idx_qi_raw_label   ON qi_raw_outputs(quality_label);
    CREATE INDEX IF NOT EXISTS idx_qi_fb_out      ON qi_user_feedback(output_id);
    CREATE INDEX IF NOT EXISTS idx_qi_tune_status ON qi_tunings(status);
    CREATE INDEX IF NOT EXISTS idx_qi_degrad_proj ON qi_degradation_events(project_id);
    """)
    con.commit()
    return con


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — RAW OUTPUT COLLECTOR
# Called by every engine after every phase. <3ms overhead.
# ─────────────────────────────────────────────────────────────────────────────

class RawCollector:
    """
    Every engine calls collector.record_phase() after completing.
    Stores the raw output with full trace context.
    Non-blocking — inserts are batched.

    Integration pattern (add to each engine class):
        from annaseo_qi_engine import RawCollector
        collector = RawCollector()

        # After P2 runs:
        collector.record_phase("P2_KeywordExpansion", run_id, project_id,
            raw_output={"source": "google_autosuggest", "keywords": kw_list},
            items=[(kw, "keyword", {"source":"google"}) for kw in kw_list])

        # After P10 runs:
        collector.record_phase("P10_PillarIdentification", run_id, project_id,
            raw_output=pillars,
            items=[(v["pillar_keyword"], "pillar", v) for v in pillars.values()])
    """

    def __init__(self):
        self._db = _db()

    def start_run(self, project_id: str, seed: str) -> str:
        run_id = f"run_{hashlib.md5(f'{project_id}{seed}{time.time()}'.encode()).hexdigest()[:12]}"
        self._db.execute(
            "INSERT OR IGNORE INTO qi_runs (run_id, project_id, seed) VALUES (?,?,?)",
            (run_id, project_id, seed))
        self._db.commit()
        return run_id

    def record_phase(self, phase: str, run_id: str, project_id: str,
                      raw_output: Any, items: List[Tuple[str, str, dict]] = None,
                      exec_ms: float = 0, mem_mb: float = 0,
                      errors: List[str] = None, fn: str = ""):
        """
        phase:      e.g. "P2_KeywordExpansion", "OffTopicFilter"
        raw_output: the complete dict/list the phase returned
        items:      list of (value, item_type, meta_dict) to store individually
        """
        snap_id = f"snap_{phase}_{run_id}"
        self._db.execute("""
            INSERT OR REPLACE INTO qi_phase_snapshots
            (snap_id, run_id, project_id, phase, raw_output, items_count, exec_ms, mem_mb, errors)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (snap_id, run_id, project_id, phase,
              json.dumps(raw_output, default=str)[:50000],
              len(items) if items else 0, exec_ms, mem_mb,
              json.dumps(errors or [])))
        self._db.commit()

        if items:
            self._store_items(phase, run_id, project_id, items, fn)

    def _store_items(self, phase: str, run_id: str, project_id: str,
                      items: List[Tuple], fn: str):
        for item_value, item_type, meta in items:
            if not item_value or not str(item_value).strip():
                continue
            oid = f"out_{hashlib.md5(f'{run_id}{phase}{str(item_value)[:50]}'.encode()).hexdigest()[:14]}"
            # Build trace path: which phases this item has passed through so far
            trace = self._get_trace(str(item_value), run_id, phase)
            self._db.execute("""
                INSERT OR IGNORE INTO qi_raw_outputs
                (output_id, run_id, project_id, phase, fn, item_type, item_value, item_meta, trace_path)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (oid, run_id, project_id, phase, fn,
                  item_type, str(item_value)[:500],
                  json.dumps(meta, default=str)[:2000],
                  json.dumps(trace)))
        self._db.commit()

    def _get_trace(self, value: str, run_id: str, current_phase: str) -> List[dict]:
        """Find all earlier phases this exact value passed through."""
        rows = self._db.execute(
            "SELECT phase, fn, created_at FROM qi_raw_outputs WHERE run_id=? AND item_value=? ORDER BY created_at",
            (run_id, value[:500])
        ).fetchall()
        trace = [{"phase": r["phase"], "fn": r["fn"], "action": "passed_through"} for r in rows]
        trace.append({"phase": current_phase, "fn": "", "action": "produced_here"})
        return trace

    @contextmanager
    def instrument(self, phase: str, run_id: str, project_id: str, fn: str = ""):
        """Context manager for automatic timing + error capture."""
        import psutil, os as _os
        t0  = time.perf_counter()
        mem = psutil.Process(_os.getpid()).memory_info().rss / 1024 / 1024
        errs = []
        try:
            yield errs
        except Exception as e:
            errs.append(str(e)[:200])
        finally:
            ms   = (time.perf_counter() - t0) * 1000
            dmem = psutil.Process(_os.getpid()).memory_info().rss / 1024 / 1024 - mem
            self._db.execute(
                "INSERT OR REPLACE INTO qi_phase_snapshots (snap_id,run_id,project_id,phase,raw_output,exec_ms,mem_mb,errors) VALUES (?,?,?,?,?,?,?,?)",
                (f"snap_{phase}_{run_id}",run_id,project_id,phase,"{}",ms,max(0,dmem),json.dumps(errs))
            )
            self._db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — QUALITY SCORER (Gemini, free tier)
# Scores every raw output item before user review.
# Pre-flags obvious problems — worst items surface first in review queue.
# ─────────────────────────────────────────────────────────────────────────────

class QualityScorer:

    # Scoring rubric per item type — maps to ENGINE_ANATOMY failure modes
    RUBRICS = {
        "keyword": {
            "dimensions": ["domain_relevance","search_potential","intent_clarity"],
            "prompt": "Score this keyword for an SEO universe. Is it directly related to the seed product/business? Does it have search potential? Is the intent clear?",
        },
        "pillar": {
            "dimensions": ["business_relevance","search_volume_potential","content_authority","uniqueness"],
            "prompt": "Score this as a pillar keyword. A good pillar should be the broadest commercially viable keyword in its cluster, directly relevant to the business.",
        },
        "cluster": {
            "dimensions": ["coherence","domain_relevance","content_potential"],
            "prompt": "Score this cluster name for an SEO content strategy. Is it coherent? Is it directly relevant to the seed business?",
        },
        "article": {
            "dimensions": ["eeat_signals","geo_readiness","readability","factual_depth","no_ai_patterns"],
            "prompt": "Score this article on: E-E-A-T signals (first-person, expertise), GEO readiness (direct answers, stats), readability, factual depth, absence of AI writing patterns.",
        },
        "brief": {
            "dimensions": ["competitor_coverage","faq_quality","angle_uniqueness"],
            "prompt": "Score this content brief. Does it cover what SERP competitors cover? Are the FAQs specific and useful? Is there a unique angle?",
        },
    }

    def score_batch(self, items: List[dict], seed: str = "",
                     business_context: str = "") -> List[dict]:
        key = os.getenv("GEMINI_API_KEY","")
        results = []
        for item in items[:100]:
            rubric = self.RUBRICS.get(item.get("item_type","keyword"), self.RUBRICS["keyword"])
            if key:
                scored = self._gemini_score(item, rubric, seed, business_context)
            else:
                scored = self._rule_score(item, seed)
            results.append(scored)
            # Update DB
            _db().execute(
                "UPDATE qi_raw_outputs SET quality_score=? WHERE output_id=?",
                (scored.get("score",50), item.get("output_id",""))
            )
        _db().commit()
        return results

    def _gemini_score(self, item: dict, rubric: dict, seed: str,
                       biz: str) -> dict:
        dims = ", ".join(rubric["dimensions"])
        try:
            r = _req.post(
                f"{GEMINI_URL}?key={os.getenv('GEMINI_API_KEY','')}",
                json={"contents":[{"parts":[{"text":
                    f"Seed: {seed}\nBusiness: {biz or 'organic spice business'}\n"
                    f"Item type: {item.get('item_type')}\nValue: {item.get('item_value')}\n"
                    f"Phase that produced it: {item.get('phase')}\n"
                    f"Meta: {str(item.get('item_meta','{}'))[:200]}\n\n"
                    f"{rubric['prompt']}\n"
                    f"Score each dimension 0-100: {dims}\n"
                    f"List up to 3 issues if score <80.\n"
                    f"Return JSON only: {{\"score\":0-100,\"dimensions\":{{}},\"issues\":[],\"confidence\":0.0-1.0}}"
                }]}],
                "generationConfig":{"temperature":0.05,"maxOutputTokens":250}},
                timeout=12
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}',text,re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                data["output_id"] = item.get("output_id","")
                data["item_value"] = item.get("item_value","")
                return data
        except Exception as e:
            log.warning(f"[QI] Gemini score failed: {e}")
        return self._rule_score(item, seed)

    def _rule_score(self, item: dict, seed: str) -> dict:
        val   = str(item.get("item_value","")).lower()
        itype = item.get("item_type","keyword")
        score = 70.0
        issues = []

        TOURISM = {"tour","travel","trip","holiday","resort","hotel","flight",
                   "booking","tourism","tourist","vacation","cruise","safari"}
        SOCIAL  = {"meme","viral","tiktok","instagram","challenge","reddit"}
        PRODUCT_SIGNALS = {"buy","price","organic","benefits","how to","recipe",
                           "health","natural","best","review","guide","vs"}

        words = set(val.split())
        if words & TOURISM:
            score -= 45
            issues.append(f"Tourism word detected: {words & TOURISM}")
        if words & SOCIAL:
            score -= 40
            issues.append(f"Social media noise: {words & SOCIAL}")
        if not (words & PRODUCT_SIGNALS) and itype in ("keyword","pillar"):
            score -= 15
            issues.append("No product/commercial signal words")
        if itype == "article":
            meta = json.loads(item.get("item_meta","{}") or "{}")
            seo  = meta.get("seo_score",0)
            eeat = meta.get("eeat_score",0)
            geo  = meta.get("geo_score",0)
            if seo or eeat or geo:
                score = (seo + eeat + geo) / 3
                if geo < 70: issues.append(f"GEO score low ({geo})")
                if eeat< 70: issues.append(f"E-E-A-T score low ({eeat})")

        return {
            "output_id":  item.get("output_id",""),
            "item_value": item.get("item_value",""),
            "score":      max(0, min(100, score)),
            "dimensions": {},
            "issues":     issues,
            "confidence": 0.75,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — DEGRADATION ATTRIBUTOR
# Given a bad item, walks its trace to find EXACTLY which phase/fn failed.
# Uses ENGINE_ANATOMY to match the failure to the known failure modes.
# ─────────────────────────────────────────────────────────────────────────────

class DegradationAttributor:

    def attribute(self, output_id: str, reason: str) -> dict:
        """
        Find the exact phase and function responsible for the bad item.
        Match to the specific failure mode in ENGINE_ANATOMY.
        Return a targeted fix.
        """
        con = _db()
        row = con.execute("SELECT * FROM qi_raw_outputs WHERE output_id=?", (output_id,)).fetchone()
        if not row:
            return {"error": "Output not found"}

        item      = dict(row)
        trace     = json.loads(item.get("trace_path","[]"))
        itype     = item.get("item_type","keyword")
        val       = item.get("item_value","")
        origin_ph = item.get("phase","")

        # Find the correct filter gate that should have caught this
        gates        = FILTER_GATES.get(itype, [])
        phases_seen  = {t["phase"] for t in trace}
        missed_gates = [g for g in gates if g in phases_seen]  # gates item passed through

        # Match to specific failure mode in ENGINE_ANATOMY
        attribution = self._match_failure_mode(val, itype, reason, origin_ph, missed_gates)

        # Save degradation event
        event_id = f"dg_{output_id}_{int(time.time())}"
        con.execute("""
            INSERT OR REPLACE INTO qi_degradation_events
            (event_id,output_id,project_id,item_type,item_value,origin_phase,
             origin_fn,degradation_phase,degradation_fn,failure_mode,user_reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (event_id, output_id, item.get("project_id",""),
              itype, val[:200], origin_ph, item.get("fn",""),
              attribution["phase"], attribution["fn"],
              attribution["failure_mode"][:200], reason))
        con.commit()

        log.info(f"[QI] Attribution: {val[:30]} → {attribution['phase']}.{attribution['fn']}")
        return {
            "event_id":       event_id,
            "item_value":     val,
            "item_type":      itype,
            "origin_phase":   origin_ph,
            "trace_path":     [f"{t['phase']}.{t.get('fn','')} → {t.get('action','')}" for t in trace],
            "degradation_at": attribution["phase"],
            "degradation_fn": attribution["fn"],
            "failure_mode":   attribution["failure_mode"],
            "fix_type":       attribution["fix_type"],
            "fix":            attribution["fix"],
            "engine_file":    attribution["engine_file"],
        }

    def _match_failure_mode(self, val: str, itype: str, reason: str,
                             origin_phase: str, missed_gates: List[str]) -> dict:
        """
        Match the bad item to a specific failure mode in ENGINE_ANATOMY.
        Returns the most specific match.
        """
        val_lower    = val.lower()
        reason_lower = reason.lower()
        words        = set(val_lower.split())

        TOURISM = {"tour","travel","trip","holiday","resort","hotel","tourism","tourist","vacation"}
        SOCIAL  = {"meme","viral","tiktok","instagram","challenge"}

        # Tourism keywords → OffTopicFilter is the earliest gate that should catch
        if words & TOURISM:
            otf_modes = ENGINE_ANATOMY["OffTopicFilter"]["failure_modes"]
            return {
                "phase":        "OffTopicFilter",
                "fn":           "GLOBAL_KILL",
                "engine_file":  "annaseo_addons.py",
                "failure_mode": otf_modes[0][0],
                "fix_type":     otf_modes[0][1],
                "fix":          otf_modes[0][2] + f" — add: {list(words & TOURISM)}",
            }

        # Pillar with off-domain content → P10 PILLAR_PROMPT missing domain constraint
        if itype == "pillar" and "tour" in val_lower:
            modes = ENGINE_ANATOMY["P10_PillarIdentification"]["failure_modes"]
            return {
                "phase":        "P10_PillarIdentification",
                "fn":           "PILLAR_PROMPT",
                "engine_file":  "ruflo_20phase_engine.py",
                "failure_mode": modes[0][0],
                "fix_type":     modes[0][1],
                "fix":          modes[0][2],
            }

        # Low E-E-A-T or generic content
        if "generic" in reason_lower or "first-person" in reason_lower or "eeat" in reason_lower:
            modes = ENGINE_ANATOMY["P16_Claude_Content"]["failure_modes"]
            return {
                "phase":        "P16_Claude_Content",
                "fn":           "Layer1_system_prompt",
                "engine_file":  "ruflo_content_engine.py",
                "failure_mode": modes[1][0],
                "fix_type":     modes[1][1],
                "fix":          modes[1][2],
            }

        # AI watermarks
        if "watermark" in reason_lower or "furthermore" in reason_lower or "ai pattern" in reason_lower:
            modes = ENGINE_ANATOMY["P16_Claude_Content"]["failure_modes"]
            return {
                "phase":        "P16_Claude_Content",
                "fn":           "Layer1_system_prompt",
                "engine_file":  "ruflo_content_engine.py",
                "failure_mode": modes[0][0],
                "fix_type":     "prompt_edit",
                "fix":          modes[0][2],
            }

        # Low GEO score
        if "geo" in reason_lower or "direct answer" in reason_lower or "citation" in reason_lower:
            modes = ENGINE_ANATOMY["GEOScorer"]["failure_modes"]
            return {
                "phase":        "GEOScorer",
                "fn":           "score",
                "engine_file":  "ruflo_content_engine.py",
                "failure_mode": modes[0][0],
                "fix_type":     "scoring_rule",
                "fix":          modes[0][2],
            }

        # Intent misclassified
        if "intent" in reason_lower or "wrong category" in reason_lower:
            modes = ENGINE_ANATOMY["P5_IntentClassification"]["failure_modes"]
            return {
                "phase":        "P5_IntentClassification",
                "fn":           "RULES",
                "engine_file":  "ruflo_20phase_engine.py",
                "failure_mode": modes[0][0],
                "fix_type":     "scoring_rule",
                "fix":          modes[0][2],
            }

        # Cluster issue
        if itype == "cluster":
            modes = ENGINE_ANATOMY["P9_ClusterFormation"]["failure_modes"]
            return {
                "phase":        "P9_ClusterFormation",
                "fn":           "CLUSTER_PROMPT",
                "engine_file":  "ruflo_20phase_engine.py",
                "failure_mode": modes[0][0],
                "fix_type":     "prompt_edit",
                "fix":          modes[0][2],
            }

        # Default: trace back to origin phase
        anatomy = ENGINE_ANATOMY.get(origin_phase, {})
        modes   = anatomy.get("failure_modes", [])
        if modes:
            m = modes[0]
            return {
                "phase":        origin_phase,
                "fn":           m[2],
                "engine_file":  anatomy.get("file",""),
                "failure_mode": m[0],
                "fix_type":     m[1],
                "fix":          m[3],
            }

        return {
            "phase":        origin_phase,
            "fn":           "unknown",
            "engine_file":  "",
            "failure_mode": f"Unknown failure for: {val[:50]}",
            "fix_type":     "manual",
            "fix":          f"Manual investigation needed. User reason: {reason}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — TUNING GENERATOR + APPLICATOR
# Gemini writes spec, Groq writes tests, DeepSeek writes code,
# Claude verifies. Manual approval always required.
# ─────────────────────────────────────────────────────────────────────────────

class TuningGenerator:

    def generate(self, event_id: str, evidence: List[str]) -> str:
        """Generate a tuning instruction from a degradation event."""
        con = _db()
        ev = con.execute("SELECT * FROM qi_degradation_events WHERE event_id=?",
                          (event_id,)).fetchone()
        if not ev: return ""

        ev   = dict(ev)
        anat = ENGINE_ANATOMY.get(ev["degradation_phase"], {})
        phase, fn = ev["degradation_phase"], ev["degradation_fn"]
        ftype = ev.get("failure_mode","")

        # Step 1: Gemini writes the spec
        spec = self._gemini_spec(ev, anat, evidence)

        # Step 2: Determine before/after
        before, after = self._build_change(ev, anat, spec)

        # Step 3: Groq generates tests
        tests = self._groq_tests(ev, spec)

        # Step 4: Claude verifies
        claude = self._claude_verify(ev, before, after, tests)

        # Save tuning
        tid = f"tune_{event_id[:16]}_{int(time.time())}"
        con.execute("""
            INSERT OR REPLACE INTO qi_tunings
            (tuning_id,event_id,phase,fn_target,engine_file,tuning_type,
             problem,fix,before_value,after_value,evidence,claude_notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (tid, event_id, phase, fn,
              anat.get("file",""), spec.get("tuning_type","filter"),
              spec.get("problem",""), spec.get("fix",""),
              before[:5000], after[:5000],
              json.dumps(evidence[:5]),
              json.dumps(claude)))
        con.commit()
        log.info(f"[QI] Tuning created: {tid} ({spec.get('tuning_type')} on {phase}.{fn})")
        return tid

    def _gemini_spec(self, ev: dict, anat: dict, evidence: List[str]) -> dict:
        key = os.getenv("GEMINI_API_KEY","")
        if not key:
            return {"tuning_type": "filter", "problem": ev.get("failure_mode",""),
                    "fix": ev.get("failure_mode","")}
        try:
            modes_text = "\n".join(f"- {m[0]} → {m[1]}: {m[3]}"
                                    for m in anat.get("failure_modes",[])[:3])
            r = _req.post(
                f"{GEMINI_URL}?key={key}",
                json={"contents":[{"parts":[{"text":
                    f"SEO engine produced bad output.\n"
                    f"Phase: {ev['degradation_phase']}.{ev['degradation_fn']}\n"
                    f"File: {anat.get('file','')}\n"
                    f"Bad item: {ev['item_value']} (type: {ev['item_type']})\n"
                    f"User said: {ev['user_reason']}\n"
                    f"Known failure modes for this phase:\n{modes_text}\n"
                    f"Evidence (similar bad items):\n" + "\n".join(evidence[:3]) +
                    f"\n\nWhat is the exact fix?\n"
                    f"Return JSON: {{\"tuning_type\":\"filter|prompt_edit|parameter|scoring_rule\","
                    f"\"problem\":\"one sentence\",\"fix\":\"exact change needed\","
                    f"\"confidence\":0-100}}"
                }]}],
                "generationConfig":{"temperature":0.05,"maxOutputTokens":300}},
                timeout=12
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}',text,re.DOTALL)
            if m: return json.loads(m.group(0))
        except Exception as e:
            log.warning(f"[QI] Gemini spec failed: {e}")

        return {"tuning_type": "filter", "problem": ev.get("failure_mode",""),
                "fix": ev.get("failure_mode",""), "confidence": 60}

    def _build_change(self, ev: dict, anat: dict, spec: dict) -> Tuple[str, str]:
        """Build the actual before/after for the tuning type."""
        tt  = spec.get("tuning_type","filter")
        val = ev.get("item_value","")
        words = [w for w in val.lower().split() if len(w) > 3]

        if tt == "filter":
            current = anat.get("current_kill_list", [])
            return (
                f"# OffTopicFilter.GLOBAL_KILL (current, {len(current)} words)\n"
                + json.dumps(current[:10], indent=2) + "\n# ...",
                f"# Add to GLOBAL_KILL (from user feedback: '{val}'):\n"
                + json.dumps(words, indent=2)
            )

        if tt == "prompt_edit":
            config = anat.get("config","")
            fix    = spec.get("fix","")
            return (
                f"# Current prompt config for {ev['degradation_phase']}:\n{config}",
                f"# Add this rule to {ev['degradation_fn']} prompt:\n# {fix}"
            )

        if tt == "scoring_rule":
            curr_rules = anat.get("current_rules",{})
            fix = spec.get("fix","")
            return (
                f"# Current rules for {ev['degradation_phase']}:\n"
                + json.dumps(curr_rules, indent=2)[:500],
                f"# Add/modify rule:\n# {fix}"
            )

        return (f"# Current {ev['degradation_phase']}.{ev['degradation_fn']}",
                f"# Fix: {spec.get('fix','')}")

    def _groq_tests(self, ev: dict, spec: dict) -> str:
        key = os.getenv("GROQ_API_KEY","")
        if not key:
            return f"import pytest\ndef test_{ev['degradation_phase'].lower()}_fix():\n    # Test that '{ev['item_value']}' no longer passes\n    pass\n"
        try:
            r = _req.post(GROQ_URL,
                headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                json={"model":"llama-3.1-8b-instant","max_tokens":800,
                      "messages":[{"role":"user","content":
                          f"Write pytest tests for this SEO engine fix.\n"
                          f"Phase: {ev['degradation_phase']}\n"
                          f"Problem: {ev['failure_mode']}\n"
                          f"Fix: {spec.get('fix','')}\n"
                          f"Bad example: '{ev['item_value']}'\n\n"
                          f"Tests should verify:\n"
                          f"1. The bad item is now rejected\n"
                          f"2. Valid items still pass\n"
                          f"3. No regression in adjacent behaviour\n"
                          f"Return only valid Python pytest code."}]},
                timeout=15
            )
            r.raise_for_status()
            code = r.json()["choices"][0]["message"]["content"]
            return re.sub(r"```(?:python)?","",code).strip().rstrip("`").strip()
        except Exception as e:
            log.warning(f"[QI] Groq tests failed: {e}")
        return f"import pytest\ndef test_fix(): pass\n"

    def _claude_verify(self, ev: dict, before: str, after: str, tests: str) -> dict:
        key = os.getenv("ANTHROPIC_API_KEY","")
        if not key:
            return {"recommendation":"needs_manual_review","confidence":0}
        try:
            import anthropic
            c = anthropic.Anthropic(api_key=key)
            r = c.messages.create(
                model=os.getenv("CLAUDE_MODEL","claude-sonnet-4-6"),
                max_tokens=400,
                messages=[{"role":"user","content":
                    f"Review this SEO engine fix before production.\n\n"
                    f"Phase: {ev['degradation_phase']} → {ev['degradation_fn']}\n"
                    f"Problem: {ev['failure_mode']}\n"
                    f"User complaint: {ev['user_reason']}\n\n"
                    f"Before:\n{before[:600]}\n\n"
                    f"After:\n{after[:600]}\n\n"
                    f"Is this fix correct, targeted, and safe? Will it prevent the issue without breaking other functionality?\n\n"
                    f"Return JSON: {{\"recommendation\":\"approve|reject\","
                    f"\"confidence\":0-100,\"concerns\":[],\"notes\":\"...\"}}"}]
            )
            text = r.content[0].text.strip()
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}',text,re.DOTALL)
            if m: return json.loads(m.group(0))
        except Exception as e:
            log.warning(f"[QI] Claude verify failed: {e}")
        return {"recommendation":"needs_manual_review","confidence":50,"concerns":[],"notes":"Manual review required"}


class TuningApplicator:

    def apply(self, tuning_id: str, approved_by: str) -> Tuple[bool, str]:
        """Apply approved tuning to the engine file. Saves rollback snapshot."""
        con = _db()
        row = con.execute("SELECT * FROM qi_tunings WHERE tuning_id=?",
                           (tuning_id,)).fetchone()
        if not row: return False, "Tuning not found"
        t = dict(row)

        engine_file = ENGINES_DIR / t["engine_file"]
        if not engine_file.exists():
            return False, f"Engine file not found: {engine_file}"

        # Save snapshot for rollback
        original = engine_file.read_text(encoding="utf-8")
        snap_path = VERSIONS_DIR / f"{t['engine_file'].replace('/','_')}_qi_{tuning_id[:12]}_pre.py"
        snap_path.write_text(original, encoding="utf-8")

        success, msg = False, "Unknown type"

        if t["tuning_type"] == "filter":
            success, msg = self._apply_filter(t, engine_file, original)
        elif t["tuning_type"] == "prompt_edit":
            success, msg = self._apply_prompt_edit(t, engine_file, original)
        elif t["tuning_type"] in ("parameter","scoring_rule"):
            success = True
            msg = (f"Recorded. {t['tuning_type']} changes require manual code edit.\n"
                   f"Target: {t['engine_file']} → {t['fn_target']}\n"
                   f"Fix: {t['fix']}")

        if success:
            con.execute(
                "UPDATE qi_tunings SET status='applied',approved_by=?,approved_at=?,rollback_snap=? WHERE tuning_id=?",
                (approved_by,datetime.utcnow().isoformat(),str(snap_path),tuning_id)
            )
        else:
            con.execute(
                "UPDATE qi_tunings SET status='failed' WHERE tuning_id=?",
                (tuning_id,)
            )
        con.commit()
        return success, msg

    def _apply_filter(self, t: dict, engine_file: Path, original: str) -> Tuple[bool,str]:
        """Add words to OffTopicFilter.GLOBAL_KILL in annaseo_addons.py."""
        addons = ENGINES_DIR / "annaseo_addons.py"
        if not addons.exists():
            return False, "annaseo_addons.py not found"
        try:
            # Extract words from after_value
            words = re.findall(r'"([a-zA-Z]{3,})"', t.get("after_value",""))
            if not words:
                words = [w.strip('"\'') for w in
                         t.get("after_value","").split("\n")
                         if len(w.strip().strip('"\'')) > 3][:10]
            if not words:
                return False, "No filter words found in tuning after_value"

            code = addons.read_text(encoding="utf-8")
            # Save snapshot of addons
            snap = VERSIONS_DIR / f"annaseo_addons_qi_{t['tuning_id'][:12]}_pre.py"
            snap.write_text(code, encoding="utf-8")

            m = re.search(r'(GLOBAL_KILL\s*=\s*\[)([^\]]*?)(\])', code, re.DOTALL)
            if not m:
                return False, "GLOBAL_KILL list not found in annaseo_addons.py"

            existing = m.group(2)
            new_words = "\n        ".join(
                f'"{w}",' for w in words if f'"{w}"' not in existing
            )
            if not new_words:
                return True, f"Words {words} already in GLOBAL_KILL"

            new_block = (m.group(1) + existing.rstrip() +
                         f"\n        {new_words}"
                         f"\n        # QI-FIX: {t['tuning_id'][:12]}\n    " +
                         m.group(3))
            addons.write_text(code[:m.start()] + new_block + code[m.end():], encoding="utf-8")
            # Update rollback to point at addons snapshot
            _db().execute("UPDATE qi_tunings SET rollback_snap=? WHERE tuning_id=?",
                          (str(snap), t["tuning_id"]))
            _db().commit()
            return True, f"Added {len(words)} words to GLOBAL_KILL: {words}"
        except Exception as e:
            return False, str(e)

    def _apply_prompt_edit(self, t: dict, engine_file: Path, original: str) -> Tuple[bool,str]:
        """Inject a prompt rule near the target function in the engine file."""
        try:
            fn_name  = t["fn_target"].replace(".", "_").split("_")[0]
            new_rule = t["after_value"].strip().replace("# Add this rule:","").strip()
            if not new_rule or len(new_rule) < 10:
                return False, "No instruction found in after_value"

            comment  = f"    # QI-FIX {t['tuning_id'][:12]}: {new_rule[:120]}\n"
            m = re.search(rf"(def {fn_name}[^\n]+\n)", original)
            if not m:
                # Try class-level prompt constant
                m2 = re.search(rf"({fn_name.upper()}_PROMPT\s*=\s*\"\"\")", original)
                if m2:
                    new_code = original[:m2.end()] + f"\nIMPORTANT: {new_rule[:100]}\n" + original[m2.end():]
                    engine_file.write_text(new_code, encoding="utf-8")
                    return True, f"Injected rule into {fn_name.upper()}_PROMPT"
                return False, f"Function/prompt {fn_name} not found in {engine_file.name}"

            new_code = original[:m.end()] + comment + original[m.end():]
            engine_file.write_text(new_code, encoding="utf-8")
            return True, f"Prompt rule injected after {fn_name}()"
        except Exception as e:
            return False, str(e)

    def reject(self, tuning_id: str, rejected_by: str, reason: str) -> dict:
        _db().execute(
            "UPDATE qi_tunings SET status='rejected',reject_reason=?,approved_by=?,approved_at=? WHERE tuning_id=?",
            (reason,rejected_by,datetime.utcnow().isoformat(),tuning_id)
        )
        _db().commit()
        return {"success":True,"message":f"Rejected. No engine changes made."}

    def rollback(self, tuning_id: str, rolled_back_by: str) -> Tuple[bool,str]:
        con = _db()
        row = con.execute("SELECT * FROM qi_tunings WHERE tuning_id=?", (tuning_id,)).fetchone()
        if not row: return False, "Not found"
        t   = dict(row)
        snap= Path(t.get("rollback_snap",""))
        if not snap.exists():
            return False, f"Rollback snapshot missing: {snap}"

        target = ENGINES_DIR / t["engine_file"]
        if target.exists():
            target.write_text(snap.read_text(encoding="utf-8"), encoding="utf-8")
        # Also check addons
        addons_snap = VERSIONS_DIR / f"annaseo_addons_qi_{tuning_id[:12]}_pre.py"
        if addons_snap.exists():
            (ENGINES_DIR / "annaseo_addons.py").write_text(
                addons_snap.read_text(encoding="utf-8"), encoding="utf-8"
            )
        con.execute("UPDATE qi_tunings SET status='rolled_back' WHERE tuning_id=?", (tuning_id,))
        con.commit()
        log.info(f"[QI] Rollback: {tuning_id} by {rolled_back_by}")
        return True, f"Rolled back {t['engine_file']}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — PHASE HEALTH REPORTER
# Shows quality score per phase based on actual feedback.
# Identifies which engine is the root cause.
# ─────────────────────────────────────────────────────────────────────────────

class PhaseHealthReporter:

    def report(self, project_id: str = None) -> List[dict]:
        con = _db()
        q = """
            SELECT o.phase,
                   COUNT(*) as total,
                   SUM(CASE WHEN o.quality_label='bad'  THEN 1 ELSE 0 END) as bad,
                   SUM(CASE WHEN o.quality_label='good' THEN 1 ELSE 0 END) as good,
                   AVG(COALESCE(o.quality_score,50)) as avg_score,
                   AVG(s.exec_ms) as avg_ms, AVG(s.mem_mb) as avg_mb
            FROM qi_raw_outputs o
            LEFT JOIN qi_phase_snapshots s ON s.run_id=o.run_id AND s.phase=o.phase
        """
        p = []
        if project_id:
            q += " WHERE o.project_id=?"; p.append(project_id)
        q += " GROUP BY o.phase ORDER BY bad DESC"

        rows = [dict(r) for r in con.execute(q, p).fetchall()]
        result = []
        for r in rows:
            bad_pct = r["bad"] / max(r["total"],1) * 100
            quality = max(0, 100 - bad_pct * 2)
            anat    = ENGINE_ANATOMY.get(r["phase"], {})
            result.append({
                "phase":        r["phase"],
                "engine_file":  anat.get("file",""),
                "total_items":  r["total"],
                "bad":          r["bad"],
                "good":         r["good"],
                "bad_rate":     round(bad_pct, 1),
                "avg_score":    round(r["avg_score"] or 0, 1),
                "quality":      round(quality, 1),
                "avg_ms":       round(r["avg_ms"] or 0, 0),
                "avg_mb":       round(r["avg_mb"] or 0, 1),
                "status":       ("critical" if quality < 60 else
                                 "degraded" if quality < 80 else
                                 "good"     if quality < 90 else "healthy"),
                "known_failures": [m[0] for m in anat.get("failure_modes",[])[:2]],
            })
        return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — MASTER QI ENGINE (Ruflo job interface)
# ─────────────────────────────────────────────────────────────────────────────

class QIEngine:
    """
    Master Quality Intelligence Engine. Ruflo calls via job queue.

    Job types (all Ruflo-compatible):
      qi_score_run <run_id>                     → score all items from a run
      qi_feedback <output_id> bad|good <reason> → submit user feedback
      qi_attribute <output_id> <reason>         → find which engine caused it
      qi_generate_tuning <event_id>             → create targeted tuning
      qi_approve_tuning <tuning_id> <user>      → approve + apply
      qi_reject_tuning <tuning_id> <user> <r>   → reject
      qi_rollback <tuning_id> <user>            → rollback
      qi_phase_report [project_id]              → health per phase
      qi_dashboard [project_id]                 → full dashboard state
    """

    def __init__(self):
        self._collector  = RawCollector()
        self._scorer     = QualityScorer()
        self._attributor = DegradationAttributor()
        self._gen        = TuningGenerator()
        self._apply      = TuningApplicator()
        self._reporter   = PhaseHealthReporter()

    def job_score_run(self, run_id: str, seed: str = "",
                       biz_context: str = "") -> dict:
        """Score all raw outputs from a completed engine run."""
        con   = _db()
        items = [dict(r) for r in con.execute(
            "SELECT * FROM qi_raw_outputs WHERE run_id=? AND quality_score IS NULL LIMIT 500",
            (run_id,)
        ).fetchall()]
        if not items:
            return {"scored": 0, "message": "No unscored items for this run"}

        scores = self._scorer.score_batch(items, seed, biz_context)
        low    = [s for s in scores if s.get("score",100) < 60]
        log.info(f"[QI] Scored {len(scores)} items, {len(low)} low quality")
        return {
            "run_id":       run_id,
            "scored":       len(scores),
            "low_quality":  len(low),
            "avg_score":    round(sum(s.get("score",50) for s in scores) / max(len(scores),1), 1),
            "review_needed":len(low),
        }

    def job_feedback(self, output_id: str, project_id: str, label: str,
                      reason: str = "", fix_hint: str = "") -> dict:
        """User submits good/bad label on one item."""
        con = _db()
        fb_id = f"fb_{hashlib.md5(f'{output_id}{time.time()}'.encode()).hexdigest()[:12]}"
        con.execute("""
            INSERT OR REPLACE INTO qi_user_feedback
            (fb_id,output_id,project_id,label,reason,fix_hint)
            VALUES (?,?,?,?,?,?)
        """, (fb_id, output_id, project_id, label, reason, fix_hint))
        con.execute(
            "UPDATE qi_raw_outputs SET quality_label=? WHERE output_id=?",
            (label, output_id)
        )
        con.commit()

        result = {"feedback_id": fb_id, "label": label}

        # Auto-attribute if bad
        if label == "bad" and reason:
            attribution = self.job_attribute(output_id, reason)
            result["attribution"] = attribution

            # Auto-generate tuning if clear failure mode found
            if attribution.get("event_id") and attribution.get("fix_type") != "manual":
                evidence = self._collect_similar_evidence(
                    output_id, attribution.get("degradation_at",""), project_id
                )
                tid = self._gen.generate(attribution["event_id"], evidence)
                result["tuning_id"] = tid
                result["message"]   = f"Tuning generated: {tid}. Review in QI dashboard."

        return result

    def job_attribute(self, output_id: str, reason: str) -> dict:
        return self._attributor.attribute(output_id, reason)

    def job_generate_tuning(self, event_id: str) -> dict:
        ev = _db().execute("SELECT * FROM qi_degradation_events WHERE event_id=?",
                            (event_id,)).fetchone()
        if not ev: return {"error": "Event not found"}
        evidence = self._collect_similar_evidence(
            dict(ev)["output_id"],
            dict(ev)["degradation_phase"],
            dict(ev)["project_id"]
        )
        tid = self._gen.generate(event_id, evidence)
        return {"tuning_id": tid, "event_id": event_id}

    def job_approve_tuning(self, tuning_id: str, approved_by: str) -> dict:
        ok, msg = self._apply.apply(tuning_id, approved_by)
        return {"success": ok, "message": msg, "tuning_id": tuning_id}

    def job_reject_tuning(self, tuning_id: str, rejected_by: str,
                           reason: str) -> dict:
        return self._apply.reject(tuning_id, rejected_by, reason)

    def job_rollback(self, tuning_id: str, rolled_back_by: str) -> dict:
        ok, msg = self._apply.rollback(tuning_id, rolled_back_by)
        return {"success": ok, "message": msg}

    def job_phase_report(self, project_id: str = None) -> List[dict]:
        return self._reporter.report(project_id)

    def job_dashboard(self, project_id: str = None) -> dict:
        con          = _db()
        phase_report = self._reporter.report(project_id)
        q_where      = "WHERE project_id=?" if project_id else ""
        q_params     = [project_id] if project_id else []

        label_counts = {r["quality_label"]: r["cnt"] for r in con.execute(
            f"SELECT quality_label, COUNT(*) as cnt FROM qi_raw_outputs {q_where} GROUP BY quality_label",
            q_params
        ).fetchall()}

        pending_tunings = [dict(r) for r in con.execute(
            "SELECT * FROM qi_tunings WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()]
        recent_events = [dict(r) for r in con.execute(
            f"SELECT * FROM qi_degradation_events {q_where} ORDER BY created_at DESC LIMIT 20",
            q_params
        ).fetchall()]
        review_queue = [dict(r) for r in con.execute(
            f"SELECT o.*, f.label as user_label, f.reason FROM qi_raw_outputs o "
            f"LEFT JOIN qi_user_feedback f ON o.output_id=f.output_id "
            f"WHERE o.quality_label='unreviewed' OR o.quality_score < 60 "
            + ("AND o.project_id=?" if project_id else "") +
            " ORDER BY COALESCE(o.quality_score,50) ASC LIMIT 60",
            ([project_id] if project_id else [])
        ).fetchall()]

        critical = [p for p in phase_report if p["status"] == "critical"]
        return {
            "quality_stats": {
                "total":       sum(label_counts.values()),
                "good":        label_counts.get("good",0),
                "bad":         label_counts.get("bad",0),
                "unreviewed":  label_counts.get("unreviewed",0),
                "quality_rate":round(label_counts.get("good",0) / max(
                                    label_counts.get("good",0)+label_counts.get("bad",0),1)*100,1),
            },
            "phase_health":      phase_report,
            "critical_phases":   critical,
            "worst_phase":       phase_report[0] if phase_report else None,
            "review_queue":      review_queue,
            "pending_tunings":   pending_tunings,
            "degradation_events":recent_events,
            "summary": {
                "phases_tracked":      len(phase_report),
                "pending_tunings":     len(pending_tunings),
                "critical_phases":     len(critical),
                "items_needing_review":len(review_queue),
            }
        }

    def _collect_similar_evidence(self, output_id: str, phase: str,
                                    project_id: str) -> List[str]:
        """Find other bad items from the same phase for pattern evidence."""
        rows = _db().execute(
            "SELECT item_value, reason FROM qi_raw_outputs o "
            "JOIN qi_user_feedback f ON o.output_id=f.output_id "
            "WHERE o.phase=? AND f.label='bad' AND o.project_id=? "
            "AND o.output_id!=? LIMIT 5",
            (phase, project_id, output_id)
        ).fetchall()
        return [f"'{r['item_value']}' — {r.get('reason','marked bad')}" for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks
    from pydantic import BaseModel as PM
    from typing import Optional as Opt

    app = FastAPI(title="AnnaSEO Quality Intelligence Engine",
                  description="Raw output collection, quality scoring, degradation attribution, engine tuning")

    qi = QIEngine()

    class FeedbackBody(PM):
        output_id:   str
        project_id:  str
        label:       str
        reason:      str = ""
        fix_hint:    str = ""

    class ApproveBody(PM):
        approved_by: str

    class RejectBody(PM):
        rejected_by: str
        reason:      str

    @app.get("/api/qi/dashboard")
    def dashboard(project_id: Opt[str] = None):
        return qi.job_dashboard(project_id)

    @app.post("/api/qi/runs/{project_id}")
    def start_run(project_id: str, seed: str = ""):
        return {"run_id": qi._collector.start_run(project_id, seed)}

    @app.post("/api/qi/score/{run_id}")
    def score_run(run_id: str, bg: BackgroundTasks,
                   seed: str = "", biz_context: str = ""):
        bg.add_task(qi.job_score_run, run_id, seed, biz_context)
        return {"status": "started", "run_id": run_id}

    @app.get("/api/qi/review-queue")
    def review_queue(project_id: Opt[str] = None, limit: int = 60):
        return qi.job_dashboard(project_id)["review_queue"][:limit]

    @app.post("/api/qi/feedback")
    def feedback(body: FeedbackBody, bg: BackgroundTasks):
        bg.add_task(qi.job_feedback, body.output_id, body.project_id,
                     body.label, body.reason, body.fix_hint)
        return {"status": "started", "message": "Feedback submitted. Attribution running if bad."}

    @app.get("/api/qi/phases")
    def phase_health(project_id: Opt[str] = None):
        return qi.job_phase_report(project_id)

    @app.get("/api/qi/degradation")
    def degradation_events(project_id: Opt[str] = None):
        return qi.job_dashboard(project_id)["degradation_events"]

    @app.post("/api/qi/tunings/from-event/{event_id}")
    def gen_tuning(event_id: str, bg: BackgroundTasks):
        bg.add_task(qi.job_generate_tuning, event_id)
        return {"status": "started", "event_id": event_id}

    @app.get("/api/qi/tunings")
    def list_tunings(status: Opt[str] = None):
        q = "SELECT * FROM qi_tunings"
        p = []
        if status: q += " WHERE status=?"; p.append(status)
        q += " ORDER BY created_at DESC LIMIT 50"
        return [dict(r) for r in _db().execute(q, p).fetchall()]

    @app.post("/api/qi/tunings/{tid}/approve")
    def approve(tid: str, body: ApproveBody):
        return qi.job_approve_tuning(tid, body.approved_by)

    @app.post("/api/qi/tunings/{tid}/reject")
    def reject(tid: str, body: RejectBody):
        return qi.job_reject_tuning(tid, body.rejected_by, body.reason)

    @app.post("/api/qi/tunings/{tid}/rollback")
    def rollback(tid: str, rolled_back_by: str = "admin"):
        return qi.job_rollback(tid, rolled_back_by)

    @app.get("/api/qi/anatomy")
    def anatomy():
        return ENGINE_ANATOMY

    @app.post("/api/qi/record")
    def record_phase(phase: str, run_id: str, project_id: str, data: dict):
        """Called by engines to store raw phase output."""
        items = data.pop("_items", [])
        qi._collector.record_phase(phase, run_id, project_id, data, items)
        return {"recorded": True}

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
AnnaSEO Quality Intelligence Engine
─────────────────────────────────────────────────────────────
Collects raw outputs from every phase. Scores quality.
Attributes bad items to exact engine/function. Generates targeted fix.

Usage:
  python annaseo_qi_engine.py demo              # full cinnamon tour demo
  python annaseo_qi_engine.py score <run_id>    # score run
  python annaseo_qi_engine.py feedback bad <output_id> <project_id> "<reason>"
  python annaseo_qi_engine.py feedback good <output_id> <project_id>
  python annaseo_qi_engine.py phases [project]  # phase health report
  python annaseo_qi_engine.py dashboard         # quality dashboard
  python annaseo_qi_engine.py tunings           # pending tunings
  python annaseo_qi_engine.py approve <tid> <n> # approve + apply
  python annaseo_qi_engine.py rollback <tid>    # rollback
  python annaseo_qi_engine.py anatomy           # show ENGINE_ANATOMY map
  python annaseo_qi_engine.py api               # FastAPI on :8006
"""
    if len(sys.argv) < 2: print(HELP); exit(0)
    cmd = sys.argv[1]
    qi  = QIEngine()

    if cmd == "demo":
        print("\n  QI ENGINE DEMO — Cinnamon tour complete trace")
        print("  " + "─"*52)
        col = RawCollector()

        # 1. Register run
        run_id = col.start_run("proj_cinnamon", "cinnamon")
        print(f"\n  Run: {run_id}")

        # 2. P2 produces "cinnamon tour" from google autosuggest
        print("\n  Step 1: P2_KeywordExpansion fetches from Google Autosuggest")
        col.record_phase("P2_KeywordExpansion", run_id, "proj_cinnamon",
            raw_output={"source":"google_autosuggest","count":340},
            items=[
                ("cinnamon benefits","keyword",{"source":"google_autosuggest"}),
                ("cinnamon tour",    "keyword",{"source":"google_autosuggest"}),
                ("cinnamon recipes", "keyword",{"source":"google_autosuggest"}),
                ("buy cinnamon",     "keyword",{"source":"amazon_autosuggest"}),
            ], exec_ms=1200, fn="_google_autosuggest")

        # 3. OffTopicFilter — "cinnamon tour" passes (kill list missing "tour")
        print("  Step 2: OffTopicFilter passes 'cinnamon tour' — 'tour' not in GLOBAL_KILL")
        col.record_phase("OffTopicFilter", run_id, "proj_cinnamon",
            raw_output={"removed":["cinnamon nail","cinnamon challenge"],"kept":340},
            items=[
                ("cinnamon tour","keyword",{"filter_status":"passed"}),
            ], fn="filter")

        # 4. P10 promotes it to pillar
        print("  Step 3: P10_PillarIdentification selects 'cinnamon tour' as pillar")
        col.record_phase("P10_PillarIdentification", run_id, "proj_cinnamon",
            raw_output={"pillars_count":8},
            items=[
                ("cinnamon tour",    "pillar",{"cluster":"Cinnamon_Tourism","pillar_title":"Cinnamon Tour Complete Guide"}),
                ("cinnamon benefits","pillar",{"cluster":"Cinnamon_Health"}),
            ], fn="run")

        # 5. Score run
        print("\n  Scoring items...")
        result = qi.job_score_run(run_id, "cinnamon", "organic spice e-commerce")
        print(f"  Scored: {result['scored']} items | Low quality: {result['low_quality']} | Avg: {result['avg_score']}")

        # 6. User marks "cinnamon tour" bad
        print("\n  User marks 'cinnamon tour' (pillar) as BAD")
        db = _db()
        tour_row = db.execute(
            "SELECT * FROM qi_raw_outputs WHERE run_id=? AND item_value=?",
            (run_id,"cinnamon tour")
        ).fetchone()

        if tour_row:
            oid = dict(tour_row)["output_id"]
            fb_result = qi.job_feedback(
                oid, "proj_cinnamon", "bad",
                reason="Tour has nothing to do with spices. Tourism keyword in spice business.",
                fix_hint="Remove tour-related words from keyword universe"
            )
            print(f"\n  Attribution result:")
            attr = fb_result.get("attribution",{})
            print(f"    Degraded at:  {attr.get('degradation_at')}.{attr.get('degradation_fn')}")
            print(f"    Engine file:  {attr.get('engine_file')}")
            print(f"    Failure mode: {attr.get('failure_mode','')[:70]}")
            print(f"    Fix type:     {attr.get('fix_type')}")
            print(f"    Fix:          {attr.get('fix','')[:80]}")
            if fb_result.get("tuning_id"):
                print(f"\n  Tuning created: {fb_result['tuning_id']}")
                print("  → Review in QI dashboard → Approve to apply fix to annaseo_addons.py")

        # 7. Phase health report
        print(f"\n  Phase health:")
        for p in qi.job_phase_report("proj_cinnamon")[:5]:
            icon = "✗" if p["status"]=="critical" else "⚠" if p["status"]=="degraded" else "✓"
            print(f"  {icon} {p['phase']:32} quality={p['quality']:.0f} bad={p['bad']}/{p['total_items']}")

        print("\n  Demo complete.")

    elif cmd == "score":
        rid = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(qi.job_score_run(rid), indent=2))

    elif cmd == "feedback":
        if len(sys.argv) < 5: print("feedback bad|good <output_id> <project_id> [reason]"); exit(1)
        label, oid, pid = sys.argv[2], sys.argv[3], sys.argv[4]
        reason = sys.argv[5] if len(sys.argv) > 5 else ""
        print(json.dumps(qi.job_feedback(oid, pid, label, reason), indent=2))

    elif cmd == "phases":
        pid = sys.argv[2] if len(sys.argv) > 2 else None
        for p in qi.job_phase_report(pid):
            icon = {"critical":"✗","degraded":"⚠","good":"·","healthy":"✓"}.get(p["status"],"·")
            print(f"  {icon} {p['phase']:32} Q={p['quality']:5.1f} bad={p['bad']:3}/{p['total_items']:3} {p['engine_file']}")

    elif cmd == "dashboard":
        d = qi.job_dashboard()
        s = d["quality_stats"]
        print(f"\n  Rate: {s['quality_rate']}% | Good: {s['good']} | Bad: {s['bad']} | Unreviewed: {s['unreviewed']}")
        print(f"  Pending tunings: {d['summary']['pending_tunings']} | Critical phases: {d['summary']['critical_phases']}")
        if d["critical_phases"]:
            print("\n  CRITICAL:")
            for p in d["critical_phases"]:
                print(f"    ✗ {p['phase']} ({p['engine_file']}) — bad rate {p['bad_rate']}%")

    elif cmd == "tunings":
        tunings = [dict(r) for r in _db().execute(
            "SELECT * FROM qi_tunings WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()]
        print(f"\n  {len(tunings)} pending tunings:")
        for t in tunings:
            print(f"  [{t['tuning_type']:12}] {t['tuning_id'][:16]} {t['phase']}.{t['fn_target'][:25]} — {t['problem'][:50]}")

    elif cmd == "approve":
        if len(sys.argv) < 4: print("approve <tuning_id> <your_name>"); exit(1)
        print(json.dumps(qi.job_approve_tuning(sys.argv[2], sys.argv[3]), indent=2))

    elif cmd == "rollback":
        if len(sys.argv) < 3: print("rollback <tuning_id>"); exit(1)
        print(json.dumps(qi.job_rollback(sys.argv[2], "cli_user"), indent=2))

    elif cmd == "anatomy":
        for phase, info in ENGINE_ANATOMY.items():
            print(f"\n  {phase} ({info.get('file','')})")
            for mode in info.get("failure_modes",[]):
                print(f"    [{mode[1]}] {mode[0][:70]}")

    elif cmd == "api":
        try:
            import uvicorn
            print("QI Engine API → http://localhost:8006/docs")
            uvicorn.run("annaseo_qi_engine:app", host="0.0.0.0", port=8006, reload=True)
        except ImportError:
            print("pip install uvicorn")
    else:
        print(f"Unknown: {cmd}\n{HELP}")

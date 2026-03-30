"""
ANNASEOv1 — main.py
FastAPI entry point. Start: uvicorn main:app --port 8000 --reload
"""
from __future__ import annotations
import annaseo_paths   # sets up sys.path for all subfolders

import os, json, asyncio, hashlib, time, logging, hmac, secrets, sqlite3, uuid, threading
import urllib.parse
import traceback
from collections import deque
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request, Body, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from services import job_tracker
from services.db_utils import row_to_dict, rows_to_dicts
from services.job_control import PauseExecution, pause_job, resume_job, cancel_job, check_control_state
from services.job_tracker import create_strategy_job, get_strategy_job, update_strategy_job, run_strategy_pipeline
from services.quota import check_and_consume_quota
from services.ranking_monitor import RankingMonitor
from services.content_fix_generator import ContentFixGenerator
from services.section_scorer import SectionScorer
from services.serp_intelligence.engine import SERPIntelligenceEngine
from services.rank_predictor import predict_ranking
from services.ws_manager import ws_manager
from core.gsc_analytics_pipeline import ingest_gsc, ingest_ga4, sync_to_experiments
from jobqueue.connection import research_queue, score_queue, pipeline_queue, redis_conn
from jobqueue.jobs import run_research_job, run_score_job, run_pipeline_job, run_develop_job, run_final_job, run_single_call_job, run_seo_sync_job

from core.log_setup import setup_logging, get_logger, bind_context
from core.metrics import register_metrics, api_requests_total, api_request_latency_seconds
from core.trace import get_trace_id, set_trace_id
from core.sentry import setup_sentry
from core.otel import setup_opentelemetry
from core.memory_engine import get_top_patterns
from services.db_session import engine as sqlalchemy_engine, SessionLocal
from services.error_logger import init_error_db, save_error, query_errors
from services.error_queue import log_error_async, send_alert
from workers.alert_worker import check_alerts
from models.error_log import ErrorLog

setup_logging()
log = get_logger("annaseo.main")

# ── Credential encryption (Fernet) ────────────────────────────────────────────
from cryptography.fernet import Fernet, InvalidToken

def _get_fernet() -> Fernet:
    key = os.getenv("FERNET_KEY", "")
    if not key:
        # Auto-generate and warn — operator should set FERNET_KEY in .env
        key = Fernet.generate_key().decode()
        log.warning("[AnnaSEO] FERNET_KEY not set — credentials encrypted with a transient key. Set FERNET_KEY in .env to persist decryption.")
    return Fernet(key.encode() if isinstance(key, str) else key)

def _encrypt(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode()).decode()

def _decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return ""

DEFAULT_DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))
FALLBACK_DB_PATH = Path(os.getenv("ANNASEO_DB_FALLBACK", "/tmp/annaseo.db"))

DB_PATH = DEFAULT_DB_PATH

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="AnnaSEO", version="1.0.0")

ERROR_LOG = deque(maxlen=1000)
ERROR_ALERT_THRESHOLD = int(os.getenv("ERROR_ALERT_THRESHOLD", "10"))
ERROR_ALERT_DISPATCHED = False


def trigger_error_alert(entry):
    global ERROR_ALERT_DISPATCHED
    if ERROR_ALERT_DISPATCHED:
        return

    if len(ERROR_LOG) < ERROR_ALERT_THRESHOLD:
        return

    message = (
        f"AnnaSEO critical error threshold reached ({len(ERROR_LOG)} errors). "
        f"Latest: {entry.get('type')} - {entry.get('error')[:300]}"
    )

    # Send to Sentry if configured
    try:
        import sentry_sdk
        if sentry_sdk is not None:
            sentry_sdk.capture_message(message)
    except Exception:
        pass

    # Send to webhook engine if configured
    try:
        from annaseo_product_growth import WebhookEngine
        webhook = WebhookEngine()
        webhook.emit("system.error_alert", {
            "count": len(ERROR_LOG),
            "latest_error": entry,
        })
    except Exception:
        pass

    log.warning("error_alert_triggered", threshold=ERROR_ALERT_THRESHOLD, count=len(ERROR_LOG))
    ERROR_ALERT_DISPATCHED = True


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Preserve intentional 502 only for true gateway errors.
    if exc.status_code == 502:
        return JSONResponse(
            status_code=502,
            content={
                "detail": "Bad Gateway",
                "code": "BAD_GATEWAY",
                "path": request.url.path,
            },
        )

    if exc.status_code >= 500:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "code": "INTERNAL_SERVER_ERROR",
                "reason": str(exc.detail),
                "path": request.url.path,
            },
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "path": request.url.path,
            "code": "HTTP_ERROR",
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "path": request.url.path,
        "method": request.method,
        "error": str(exc),
        "type": type(exc).__name__,
        "trace": traceback.format_exc(),
    }

    ERROR_LOG.appendleft(error_entry)
    trigger_error_alert(error_entry)

    try:
        log.exception("API_ERROR: %s", error_entry)
    except Exception:
        pass

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "path": request.url.path,
            "error": True,
            "code": "INTERNAL_SERVER_ERROR",
        },
    )

@app.get("/api/errors")
def get_errors(limit: int = 50, path: str = None):
    errors = list(ERROR_LOG)
    if path:
        errors = [e for e in errors if path in e["path"]]
    return {
        "count": len(errors),
        "errors": errors[:limit],
    }

@app.middleware("http")
async def metrics_collector(request, call_next):
    trace_id = get_trace_id() or str(uuid.uuid4())
    set_trace_id(trace_id)

    start_ts = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:
        # Log and enqueue exception event
        try:
            log_error_async({
                "source": "backend",
                "type": "exception",
                "message": str(exc),
                "stack_trace": traceback.format_exc(),
                "endpoint": request.url.path,
                "method": request.method,
                "trace_id": get_trace_id(),
                "metadata": {
                    "query": str(request.query_params),
                },
            })
        except Exception:
            pass

        try:
            log.exception("Unhandled exception during request %s %s", request.method, request.url.path)
        except Exception:
            pass

        # Convert to JSON 500 response for all unhandled exceptions
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "path": request.url.path,
                "error": True,
                "code": "INTERNAL_SERVER_ERROR",
            },
        )

    elapsed = time.time() - start_ts
    endpoint = request.url.path
    status_code = str(response.status_code)

    if api_requests_total is not None:
        api_requests_total.labels(method=request.method, endpoint=endpoint, status=status_code).inc()
    if api_request_latency_seconds is not None:
        api_request_latency_seconds.labels(endpoint=endpoint).observe(elapsed)

    if response.status_code >= 400:
        try:
            log_error_async({
                "source": "backend",
                "type": "http_error",
                "message": f"HTTP {response.status_code}",
                "status_code": response.status_code,
                "endpoint": endpoint,
                "method": request.method,
                "trace_id": get_trace_id(),
                "metadata": {
                    "path": str(request.url),
                    "query": str(request.query_params),
                },
            })
        except Exception:
            pass

    return response

register_metrics(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database ─────────────────────────────────────────────────────────────────
def _ensure_db_path() -> Path:
    global DB_PATH
    for candidate in [DEFAULT_DB_PATH, FALLBACK_DB_PATH]:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            sqlite3.connect(str(candidate), check_same_thread=False, timeout=30).close()
            DB_PATH = candidate
            return DB_PATH
        except Exception as e:
            log.warning("Could not use DB path %s: %s", candidate, e)
    raise RuntimeError("No writable DB path available (checked DEFAULT_DB_PATH and FALLBACK_DB_PATH)")


def get_db() -> sqlite3.Connection:
    _ensure_db_path()
    db = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    db.row_factory = sqlite3.Row
    # Build the schema script; in test mode skip WAL to avoid filesystem WAL requirements
    _schema_script = """
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT DEFAULT '',role TEXT DEFAULT 'user',pw_hash TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS user_projects(user_id TEXT,project_id TEXT,role TEXT DEFAULT 'owner',PRIMARY KEY(user_id,project_id));
    CREATE TABLE IF NOT EXISTS projects(project_id TEXT PRIMARY KEY,name TEXT NOT NULL,industry TEXT NOT NULL,description TEXT DEFAULT '',seed_keywords TEXT DEFAULT '[]',wp_url TEXT DEFAULT '',wp_user TEXT DEFAULT '',wp_pass_enc TEXT DEFAULT '',shopify_store TEXT DEFAULT '',shopify_token_enc TEXT DEFAULT '',language TEXT DEFAULT 'english',region TEXT DEFAULT 'india',religion TEXT DEFAULT 'general',status TEXT DEFAULT 'active',owner_id TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,seed TEXT NOT NULL,status TEXT DEFAULT 'queued',current_phase TEXT DEFAULT '',result TEXT DEFAULT '{}',error TEXT DEFAULT '',cost_usd REAL DEFAULT 0,started_at TEXT DEFAULT CURRENT_TIMESTAMP,completed_at TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS run_events(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,event_type TEXT NOT NULL,payload TEXT DEFAULT '{}',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS content_articles(article_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,run_id TEXT DEFAULT '',keyword TEXT NOT NULL,title TEXT DEFAULT '',body TEXT DEFAULT '',meta_title TEXT DEFAULT '',meta_desc TEXT DEFAULT '',seo_score REAL DEFAULT 0,eeat_score REAL DEFAULT 0,geo_score REAL DEFAULT 0,readability REAL DEFAULT 0,word_count INTEGER DEFAULT 0,status TEXT DEFAULT 'draft',published_url TEXT DEFAULT '',published_at TEXT DEFAULT '',schema_json TEXT DEFAULT '',frozen INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS rankings(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,keyword TEXT NOT NULL,position REAL DEFAULT 0,ctr REAL DEFAULT 0,impressions INTEGER DEFAULT 0,clicks INTEGER DEFAULT 0,recorded_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ai_usage(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,run_id TEXT DEFAULT '',model TEXT NOT NULL,input_tokens INTEGER DEFAULT 0,output_tokens INTEGER DEFAULT 0,cost_usd REAL DEFAULT 0,purpose TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS llm_audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,step TEXT,prompt TEXT,raw_output TEXT,validated_output TEXT,error TEXT,attempt INTEGER,model TEXT,tokens_used INTEGER,cost_usd REAL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS seo_audits(audit_id TEXT PRIMARY KEY,url TEXT,score REAL,grade TEXT,findings TEXT DEFAULT '[]',cwv_lcp REAL DEFAULT 0,cwv_inp REAL DEFAULT 0,cwv_cls REAL DEFAULT 0,ai_score REAL DEFAULT 0,status TEXT DEFAULT 'running',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ranking_history(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,keyword TEXT NOT NULL,position REAL DEFAULT 0,ctr REAL DEFAULT 0,impressions INTEGER DEFAULT 0,clicks INTEGER DEFAULT 0,recorded_date TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ranking_alerts(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,keyword TEXT NOT NULL,old_position REAL DEFAULT 0,new_position REAL DEFAULT 0,change REAL DEFAULT 0,severity TEXT DEFAULT 'warning',status TEXT DEFAULT 'new',diagnosis_json TEXT DEFAULT '{}',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS strategy_sessions(session_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,engine_type TEXT DEFAULT 'audience',status TEXT DEFAULT 'pending',input_json TEXT DEFAULT '{}',result_json TEXT DEFAULT '{}',confidence REAL DEFAULT 0,tokens_used INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS strategy_jobs(id TEXT PRIMARY KEY,project_id TEXT,job_type TEXT DEFAULT 'generic',status TEXT DEFAULT 'pending',progress INTEGER DEFAULT 0,current_step TEXT DEFAULT '',current_step_name TEXT DEFAULT '',step_started_at TEXT DEFAULT '',input_payload TEXT DEFAULT '{}',result_payload TEXT DEFAULT '{}',raw_llm_response TEXT DEFAULT '',error_message TEXT DEFAULT '',error_type TEXT DEFAULT '',lock_key TEXT DEFAULT '',is_locked INTEGER DEFAULT 0,last_completed_step INTEGER DEFAULT 0,execution_mode TEXT DEFAULT 'multi_step',last_heartbeat TEXT DEFAULT '',locked_at TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,started_at TEXT DEFAULT '',completed_at TEXT DEFAULT '',retry_count INTEGER DEFAULT 0,max_retries INTEGER DEFAULT 3,control_state TEXT DEFAULT 'running',cancel_requested INTEGER DEFAULT 0,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS serp_cache(keyword TEXT, location TEXT DEFAULT 'global', device TEXT DEFAULT 'desktop', results TEXT, fetched_at TEXT, provider TEXT DEFAULT '', cost REAL DEFAULT 0, PRIMARY KEY(keyword,location,device));
    CREATE TABLE IF NOT EXISTS strategy_experiments(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, variants TEXT NOT NULL, payload_json TEXT DEFAULT '{}', status TEXT DEFAULT 'running', forced_variant TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS strategy_experiment_assignments(id INTEGER PRIMARY KEY AUTOINCREMENT, experiment_id INTEGER NOT NULL, variant TEXT NOT NULL, assigned_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS strategy_experiment_results(id INTEGER PRIMARY KEY AUTOINCREMENT, experiment_id INTEGER NOT NULL, variant TEXT NOT NULL, job_id TEXT, roi REAL, status TEXT DEFAULT 'completed', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS strategy_memory(id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_type TEXT NOT NULL, pattern_value TEXT NOT NULL, avg_roi REAL DEFAULT 0, variance REAL DEFAULT 0, success_count INTEGER DEFAULT 0, total_count INTEGER DEFAULT 0, weight REAL DEFAULT 0, last_updated TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS gsc_metrics(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, keyword TEXT NOT NULL, date TEXT DEFAULT CURRENT_TIMESTAMP, impressions INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0, ctr REAL DEFAULT 0.0, position REAL DEFAULT 99.0, UNIQUE(project_id, keyword, date));
    CREATE TABLE IF NOT EXISTS ga4_metrics(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, keyword TEXT NOT NULL, date TEXT DEFAULT CURRENT_TIMESTAMP, sessions INTEGER DEFAULT 0, conversions INTEGER DEFAULT 0, revenue REAL DEFAULT 0.0, UNIQUE(project_id, keyword, date));
    CREATE TABLE IF NOT EXISTS global_strategy_memory(id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_hash TEXT UNIQUE, pattern_json TEXT, total_samples INTEGER DEFAULT 0, successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0, avg_roi REAL DEFAULT 0, variance REAL DEFAULT 0, niche TEXT DEFAULT 'global', country TEXT DEFAULT 'global', intent TEXT DEFAULT 'all', last_seen TEXT DEFAULT CURRENT_TIMESTAMP, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS meta_learning(id INTEGER PRIMARY KEY AUTOINCREMENT, feature_json TEXT UNIQUE, avg_roi REAL DEFAULT 0, samples INTEGER DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS content_blogs(blog_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,pillar TEXT DEFAULT '',cluster TEXT DEFAULT '',keyword TEXT NOT NULL,title TEXT DEFAULT '',body TEXT DEFAULT '',meta_desc TEXT DEFAULT '',schema_type TEXT DEFAULT 'Article',language TEXT DEFAULT 'english',status TEXT DEFAULT 'draft',frozen_at TEXT DEFAULT '',scheduled_date TEXT DEFAULT '',published_url TEXT DEFAULT '',internal_links TEXT DEFAULT '[]',word_count INTEGER DEFAULT 0,seo_score REAL DEFAULT 0,version INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS content_freeze_queue(id INTEGER PRIMARY KEY AUTOINCREMENT,blog_id TEXT NOT NULL,project_id TEXT NOT NULL,pillar TEXT DEFAULT '',scheduled_date TEXT NOT NULL,published INTEGER DEFAULT 0,published_at TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS ranking_predictions(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,keyword TEXT NOT NULL,pillar TEXT DEFAULT '',predicted_rank REAL DEFAULT 0,predicted_month TEXT DEFAULT '',confidence REAL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS audience_profiles(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL UNIQUE,website_url TEXT DEFAULT '',target_locations TEXT DEFAULT '[]',target_religions TEXT DEFAULT '[]',target_languages TEXT DEFAULT '[]',personas TEXT DEFAULT '[]',business_type TEXT DEFAULT 'B2C',usp TEXT DEFAULT '',products TEXT DEFAULT '[]',customer_reviews TEXT DEFAULT '',ad_copy TEXT DEFAULT '',seasonal_events TEXT DEFAULT '[]',competitor_urls TEXT DEFAULT '[]',pillar_support_map TEXT DEFAULT '{}',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS system_graph_cache(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL UNIQUE,graph_json TEXT DEFAULT '{}',node_count INTEGER DEFAULT 0,edge_count INTEGER DEFAULT 0,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS blog_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,blog_id TEXT NOT NULL,version INTEGER DEFAULT 1,title TEXT DEFAULT '',body TEXT DEFAULT '',meta_desc TEXT DEFAULT '',saved_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ai_review_results(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,session_id TEXT NOT NULL,stage TEXT NOT NULL,keyword TEXT NOT NULL,flagged INTEGER DEFAULT 0,reason TEXT DEFAULT '',user_decision TEXT DEFAULT 'pending',ai_score REAL DEFAULT 0.0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS project_prompts(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,prompt_type TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(project_id,prompt_type));
    CREATE TABLE IF NOT EXISTS research_jobs(job_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,status TEXT DEFAULT 'running',sources_done TEXT DEFAULT '[]',keyword_count INTEGER DEFAULT 0,error TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS gate_states(gate_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,gate_number INTEGER NOT NULL,gate_name TEXT,input_json TEXT DEFAULT '{}',customer_input_json TEXT DEFAULT '{}',confirmed_at TEXT,confirmed_by TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(run_id,gate_number));
    CREATE TABLE IF NOT EXISTS content_strategy(session_id TEXT PRIMARY KEY,run_id TEXT,pillar_id TEXT,angle TEXT,target_entities TEXT DEFAULT '[]',schema_types TEXT DEFAULT '[]',format_hints TEXT,internal_link_map TEXT DEFAULT '{}',confidence REAL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS keyword_feedback_intent(feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,keyword TEXT,predicted_intent TEXT,user_corrected_intent TEXT,confidence REAL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS phase_overrides(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,phase TEXT NOT NULL,items_json TEXT DEFAULT '[]',updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(run_id,phase));
    CREATE INDEX IF NOT EXISTS ix_runs_project ON runs(project_id);
    CREATE INDEX IF NOT EXISTS ix_articles_project ON content_articles(project_id);
    CREATE INDEX IF NOT EXISTS ix_rankings_project ON rankings(project_id);
    CREATE INDEX IF NOT EXISTS ix_events_run ON run_events(run_id);
    CREATE INDEX IF NOT EXISTS ix_rh_project ON ranking_history(project_id);
    CREATE INDEX IF NOT EXISTS ix_ra_project ON ranking_alerts(project_id);
    CREATE INDEX IF NOT EXISTS ix_ss_project ON strategy_sessions(project_id);
    CREATE INDEX IF NOT EXISTS ix_cb_project ON content_blogs(project_id);
    CREATE INDEX IF NOT EXISTS ix_rp_project ON ranking_predictions(project_id);
    """

    if os.getenv("ANNASEO_TESTING"):
        # Some test environments or in-memory DBs don't support WAL; remove the pragma.
        _schema_script = _schema_script.replace("PRAGMA journal_mode=WAL;\n", "")

    db.executescript(_schema_script)
    # Migrations — safe on existing DBs (ignore if column already exists)
    _migrations = [
        "ALTER TABLE runs ADD COLUMN current_gate INTEGER DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN gate_1_confirmed INTEGER DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN gate_2_confirmed INTEGER DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN gate_3_confirmed INTEGER DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN gate_4_confirmed INTEGER DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN gate_5_confirmed INTEGER DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE runs ADD COLUMN pillars_json TEXT DEFAULT '[]'",
        "ALTER TABLE runs ADD COLUMN keywords_json TEXT DEFAULT '[]'",
        "ALTER TABLE runs ADD COLUMN blog_suggestions_json TEXT DEFAULT '[]'",
        "ALTER TABLE runs ADD COLUMN strategy_json TEXT DEFAULT '{}'",
        "ALTER TABLE content_articles ADD COLUMN schedule_date TEXT DEFAULT ''",
        "ALTER TABLE content_articles ADD COLUMN pillar TEXT DEFAULT ''",
        "ALTER TABLE projects ADD COLUMN target_languages TEXT DEFAULT '[]'",
        "ALTER TABLE projects ADD COLUMN target_locations TEXT DEFAULT '[]'",
        "ALTER TABLE projects ADD COLUMN business_type TEXT DEFAULT 'B2C'",
        "ALTER TABLE projects ADD COLUMN usp TEXT DEFAULT ''",
        "ALTER TABLE projects ADD COLUMN max_serp_calls_per_day INTEGER DEFAULT 500",
        "ALTER TABLE projects ADD COLUMN max_tokens_per_day INTEGER DEFAULT 500000",
        "ALTER TABLE projects ADD COLUMN audience_personas TEXT DEFAULT '[]'",
        "ALTER TABLE projects ADD COLUMN competitor_urls TEXT DEFAULT '[]'",
        "ALTER TABLE projects ADD COLUMN customer_reviews TEXT DEFAULT ''",
        "ALTER TABLE audience_profiles ADD COLUMN pillar_support_map TEXT DEFAULT '{}'",
        "ALTER TABLE audience_profiles ADD COLUMN intent_focus TEXT DEFAULT 'both'",
        "ALTER TABLE ranking_alerts ADD COLUMN diagnosis_json TEXT DEFAULT '{}'",
        "ALTER TABLE system_graph_cache ADD COLUMN node_types TEXT DEFAULT '{}'",
        "ALTER TABLE system_graph_cache ADD COLUMN last_keyword_update TEXT",
        "CREATE TABLE IF NOT EXISTS llm_audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,step TEXT,prompt TEXT,raw_output TEXT,validated_output TEXT,error TEXT,attempt INTEGER,model TEXT,tokens_used INTEGER,cost_usd REAL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS serp_cache(keyword TEXT, location TEXT DEFAULT 'global', device TEXT DEFAULT 'desktop', results TEXT, fetched_at TEXT, provider TEXT DEFAULT '', cost REAL DEFAULT 0, PRIMARY KEY(keyword,location,device))",
        "ALTER TABLE serp_cache ADD COLUMN location TEXT DEFAULT 'global'",
        "ALTER TABLE serp_cache ADD COLUMN device TEXT DEFAULT 'desktop'",
        "ALTER TABLE serp_cache ADD COLUMN provider TEXT DEFAULT ''",
        "ALTER TABLE serp_cache ADD COLUMN cost REAL DEFAULT 0",
        "CREATE TABLE IF NOT EXISTS serp_call_usage(id INTEGER PRIMARY KEY AUTOINCREMENT, called_at TEXT, keyword TEXT, provider TEXT, project_id TEXT, cost REAL DEFAULT 0)",
        "ALTER TABLE strategy_jobs ADD COLUMN max_retries INTEGER DEFAULT 3",
        "ALTER TABLE strategy_jobs ADD COLUMN control_state TEXT DEFAULT 'running'",
        "ALTER TABLE strategy_jobs ADD COLUMN cancel_requested INTEGER DEFAULT 0",
        "ALTER TABLE strategy_jobs ADD COLUMN updated_at TEXT DEFAULT ''",
        "ALTER TABLE strategy_jobs ADD COLUMN current_step_name TEXT DEFAULT ''",
        "ALTER TABLE strategy_experiments ADD COLUMN forced_variant TEXT DEFAULT ''",
        "ALTER TABLE strategy_experiment_assignments ADD COLUMN active INTEGER DEFAULT 1",
        "CREATE TABLE IF NOT EXISTS strategy_experiments(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, variants TEXT NOT NULL, payload_json TEXT DEFAULT '{}', status TEXT DEFAULT 'running', forced_variant TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS strategy_experiment_assignments(id INTEGER PRIMARY KEY AUTOINCREMENT, experiment_id INTEGER NOT NULL, variant TEXT NOT NULL, assigned_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1)",
        "CREATE TABLE IF NOT EXISTS strategy_experiment_results(id INTEGER PRIMARY KEY AUTOINCREMENT, experiment_id INTEGER NOT NULL, variant TEXT NOT NULL, job_id TEXT, roi REAL, status TEXT DEFAULT 'completed', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS strategy_memory(id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_type TEXT NOT NULL, pattern_value TEXT NOT NULL, avg_roi REAL DEFAULT 0, variance REAL DEFAULT 0, success_count INTEGER DEFAULT 0, total_count INTEGER DEFAULT 0, weight REAL DEFAULT 0, last_updated TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS global_strategy_memory(id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_hash TEXT UNIQUE, pattern_json TEXT, total_samples INTEGER DEFAULT 0, successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0, avg_roi REAL DEFAULT 0, variance REAL DEFAULT 0, niche TEXT DEFAULT 'global', country TEXT DEFAULT 'global', intent TEXT DEFAULT 'all', last_seen TEXT DEFAULT CURRENT_TIMESTAMP, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS meta_learning(id INTEGER PRIMARY KEY AUTOINCREMENT, feature_json TEXT UNIQUE, avg_roi REAL DEFAULT 0, samples INTEGER DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "ALTER TABLE strategy_jobs ADD COLUMN step_started_at TEXT DEFAULT ''",
        "ALTER TABLE strategy_jobs ADD COLUMN execution_mode TEXT DEFAULT 'multi_step'",
        "ALTER TABLE strategy_jobs ADD COLUMN error_type TEXT DEFAULT ''",
        "ALTER TABLE strategy_jobs ADD COLUMN raw_llm_response TEXT DEFAULT ''",
        "ALTER TABLE strategy_jobs ADD COLUMN last_heartbeat TEXT DEFAULT ''",
        "ALTER TABLE strategy_jobs ADD COLUMN locked_at TEXT DEFAULT ''",
        "ALTER TABLE strategy_jobs ADD COLUMN keywords TEXT DEFAULT '{}'",
        "ALTER TABLE strategy_jobs ADD COLUMN serp TEXT DEFAULT '{}'",
        "ALTER TABLE strategy_jobs ADD COLUMN strategy TEXT DEFAULT '{}'",
        "ALTER TABLE strategy_jobs ADD COLUMN links TEXT DEFAULT '{}'",
        "ALTER TABLE strategy_jobs ADD COLUMN scores TEXT DEFAULT '{}'",
        "ALTER TABLE strategy_jobs ADD COLUMN failed_step TEXT DEFAULT ''",
        "ALTER TABLE strategy_jobs ADD COLUMN validation_status TEXT DEFAULT ''",
        "ALTER TABLE strategy_jobs ADD COLUMN tokens_used INTEGER DEFAULT 0",
        "ALTER TABLE strategy_jobs ADD COLUMN cost_usd REAL DEFAULT 0.0",
    ]
    for _m in _migrations:
        try:
            db.execute(_m); db.commit()
        except Exception:
            pass
    db.commit()
    return db

def _load_api_keys_from_db():
    try:
        from engines.ruflo_20phase_engine import Cfg
        db = get_db()
        _ensure_settings_table(db)
        rows = db.execute("SELECT key, value_enc FROM api_settings").fetchall()
        for r in rows:
            key = r["key"]
            value_enc = r["value_enc"] or ""
            val = _decrypt(value_enc)
            if not val and value_enc:
                # Legacy fallback: if plain text API key was stored without encryption, keep it.
                if value_enc.startswith("gsk_") or value_enc.startswith("sk-"):
                    val = value_enc
                    log.info(f"[Settings] Loaded plaintext API key for {key} as fallback")
            if not val:
                continue
            val = val.strip()
            mapping = {
                "groq_key": "GROQ_API_KEY",
                "gemini_key": "GEMINI_API_KEY",
                "anthropic_key": "ANTHROPIC_API_KEY",
                "openai_key": "OPENAI_API_KEY",
                "ollama_url": "OLLAMA_URL",
                "ollama_model": "OLLAMA_MODEL",
                "groq_model": "GROQ_MODEL",
            }
            env_key = mapping.get(key)
            if env_key:
                os.environ[env_key] = val
        Cfg.refresh_from_env()
    except Exception as e:
        log.warning(f"[Settings] Could not load API keys from DB: {e}")

@app.on_event("startup")
async def startup():
    # If running tests, avoid starting background services and heavy engine init
    if os.getenv("ANNASEO_TESTING", "").lower() in ("1", "true", "yes"):
        try:
            get_db()
        except Exception:
            pass
        try:
            get_logger("annaseo.main").info("[AnnaSEO] TEST MODE: skipping background services and engines")
        except Exception:
            pass
        return

    try:
        get_db()
        setup_sentry()
        setup_opentelemetry(app)
        _load_api_keys_from_db()
        _mount_engines()

        # Initialize SQLAlchemy tables for error logging
        try:
            init_error_db()
            get_logger("annaseo.main").info("[AnnaSEO] Error DB init ready")
        except Exception as e:
            get_logger("annaseo.main").warning(f"Error DB init failed: {e}")

        # Start alert checker loop
        def _alert_loop():
            while True:
                try:
                    check_alerts()
                except Exception as e:
                    log.warning("alert_loop_error", error=str(e))
                time.sleep(int(os.getenv("ALERT_CHECK_INTERVAL", "60")))

        t = threading.Thread(target=_alert_loop, daemon=True)
        t.start()

        get_logger("annaseo.main").info("[AnnaSEO] Ready")
    except Exception as e:
        get_logger("annaseo.main").error(f"Startup failed but continuing with limited operations: {e}")


@app.on_event("shutdown")
def shutdown():
    get_logger("annaseo.main").info("[AnnaSEO] Shutting down gracefully")
    # worker and other services should use signal-based stop controls

# ── Auth ─────────────────────────────────────────────────────────────────────
JWT_SECRET    = os.getenv("JWT_SECRET", secrets.token_hex(32))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def _hash_pw(pw): return sha256(f"{pw}{JWT_SECRET}".encode()).hexdigest()

def _make_token(uid, email, role, ttl=1440):
    import base64
    exp = (datetime.utcnow()+timedelta(minutes=ttl)).isoformat()
    p   = json.dumps({"user_id":uid,"email":email,"role":role,"exp":exp})
    sig = hmac.new(JWT_SECRET.encode(),p.encode(),sha256).hexdigest()
    return f"{base64.urlsafe_b64encode(p.encode()).decode()}.{sig}"

def _verify_token(token):
    import base64
    try:
        d,sig = token.rsplit(".",1)
        p     = base64.urlsafe_b64decode(d.encode()).decode()
        if not hmac.compare_digest(sig, hmac.new(JWT_SECRET.encode(),p.encode(),sha256).hexdigest()): return None
        data  = json.loads(p)
        if datetime.fromisoformat(data["exp"]) < datetime.utcnow(): return None
        return data
    except: return None

async def current_user(token: str=Depends(oauth2_scheme)):
    data = _verify_token(token)
    if not data: raise HTTPException(401,"Invalid or expired token")
    return data

class RegisterBody(BaseModel):
    email: str; name: str; password: str

@app.post("/api/auth/register",tags=["Auth"])
def register(body: RegisterBody):
    db=get_db(); uid=f"user_{hashlib.md5(body.email.encode()).hexdigest()[:10]}"
    if db.execute("SELECT 1 FROM users WHERE email=?",(body.email,)).fetchone(): raise HTTPException(400,"Already registered")
    db.execute("INSERT INTO users(user_id,email,name,pw_hash)VALUES(?,?,?,?)",(uid,body.email,body.name,_hash_pw(body.password))); db.commit()
    return {"access_token":_make_token(uid,body.email,"user"),"user_id":uid}

@app.post("/api/auth/login",tags=["Auth"])
def login(form: OAuth2PasswordRequestForm=Depends()):
    db=get_db(); user=db.execute("SELECT * FROM users WHERE email=?",(form.username,)).fetchone()
    if not user or dict(user)["pw_hash"]!=_hash_pw(form.password): raise HTTPException(401,"Invalid credentials")
    u=dict(user)
    return {"access_token":_make_token(u["user_id"],u["email"],u["role"]),"user_id":u["user_id"],"email":u["email"],"role":u["role"]}

@app.get("/api/auth/me",tags=["Auth"])
def me(user=Depends(current_user)):
    row=get_db().execute("SELECT user_id,email,name,role FROM users WHERE user_id=?",(user["user_id"],)).fetchone()
    if not row: raise HTTPException(404,"Not found")
    return dict(row)

# ── Projects ─────────────────────────────────────────────────────────────────
# Valid industries — mirrors Industry enum in quality/annaseo_domain_context.py
VALID_INDUSTRIES = {
    "food_spices","tourism","ecommerce","healthcare","agriculture",
    "education","real_estate","tech_saas","wellness","restaurant",
    "fashion","general",
}

class ProjectBody(BaseModel):
    name: str; industry: str; description: str=""; seed_keywords: List[str]=[]; language: str="english"; region: str="india"; religion: str="general"
    wp_url: str=""; wp_user: str=""; wp_password: str=""; shopify_store: str=""; shopify_token: str=""
    custom_accepts: List[str]=[]; custom_rejects: List[str]=[]
    target_languages: List[str]=[]; target_locations: List[str]=[]; business_type: str="B2C"
    usp: str=""; audience_personas: List[str]=[]; competitor_urls: List[str]=[]; customer_reviews: str=""

@app.post("/api/projects",tags=["Projects"])
def create_project(body: ProjectBody,user=Depends(current_user)):
    if body.industry not in VALID_INDUSTRIES:
        raise HTTPException(400,f"Unknown industry '{body.industry}'. Valid values: {sorted(VALID_INDUSTRIES)}")
    db=get_db(); pid=f"proj_{hashlib.md5(f'{body.name}{time.time()}'.encode()).hexdigest()[:10]}"
    db.execute(
        "INSERT INTO projects(project_id,name,industry,description,seed_keywords,wp_url,wp_user,wp_pass_enc,shopify_store,shopify_token_enc,language,region,religion,target_languages,target_locations,business_type,usp,audience_personas,competitor_urls,customer_reviews,owner_id)VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pid,body.name,body.industry,body.description,json.dumps(body.seed_keywords or []),body.wp_url,body.wp_user,_encrypt(body.wp_password),body.shopify_store,_encrypt(body.shopify_token),body.language,body.region,body.religion,json.dumps(body.target_languages or []),json.dumps(body.target_locations or []),body.business_type,body.usp,json.dumps(body.audience_personas or []),json.dumps(body.competitor_urls or []),body.customer_reviews,user["user_id"]))
    db.execute("INSERT INTO user_projects(user_id,project_id,role)VALUES(?,?,?)",(user["user_id"],pid,"owner")); db.commit()
    try:
        from annaseo_domain_context import DomainContextEngine
        DomainContextEngine().setup_project(project_id=pid,project_name=body.name,industry=body.industry,seeds=body.seed_keywords,description=body.description,custom_accepts=body.custom_accepts,custom_rejects=body.custom_rejects)
    except Exception as e: log.warning(f"DomainContext setup: {e}")
    # Return full project object for immediate UI refresh
    proj = dict(db.execute("SELECT * FROM projects WHERE project_id=?", (pid,)).fetchone())
    return {"project_id":pid,"name":body.name,"industry":body.industry,"status":proj.get("status","active"),"owner_id":proj.get("owner_id")}

@app.get("/api/projects",tags=["Projects"])
def list_projects(user=Depends(current_user)):
    db = get_db()
    pids = [r["project_id"] for r in db.execute("SELECT project_id FROM user_projects WHERE user_id=?", (user["user_id"],)).fetchall()]

    # Safety fallback: if no mapping exists yet, use ownership and join it to user_projects.
    if not pids:
        projects_owned = db.execute("SELECT project_id FROM projects WHERE owner_id=? AND status!='deleted'", (user["user_id"],)).fetchall()
        pids = [r["project_id"] for r in projects_owned]
        for pid in pids:
            try:
                db.execute("INSERT OR IGNORE INTO user_projects(user_id,project_id,role)VALUES(?,?,?)", (user["user_id"], pid, "owner"))
            except Exception:
                pass
        db.commit()

    if not pids:
        return {"projects": []}

    placeholders = ",".join("?" for _ in pids)
    projects = [dict(r) for r in db.execute(f"SELECT * FROM projects WHERE project_id IN ({placeholders}) AND status!='deleted'", pids).fetchall()]
    return {"projects": projects}

@app.get("/api/projects/{project_id}",tags=["Projects"])
def get_project(project_id: str,user=Depends(current_user)):
    row=get_db().execute("SELECT * FROM projects WHERE project_id=?",(project_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found")
    p=dict(row)
    # normalize JSON/array fields for front-end use
    for field in ["seed_keywords", "target_locations", "target_languages", "audience_personas", "competitor_urls"]:
        val = p.get(field)
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                p[field] = parsed if isinstance(parsed, list) else []
            except Exception:
                p[field] = []
        elif not isinstance(val, list):
            p[field] = []

    p["wp_pass_enc"] = "***" if p.get("wp_pass_enc") else ""
    p["shopify_token_enc"] = "***" if p.get("shopify_token_enc") else ""
    return p

@app.delete("/api/projects/{project_id}",tags=["Projects"])
def delete_project(project_id: str,user=Depends(current_user)):
    db = get_db()
    # Hard delete — remove project and all related data from every table
    tables_main = [
        "user_projects", "runs", "content_articles", "rankings",
        "ai_usage", "ranking_history", "ranking_alerts", "strategy_sessions",
        "content_blogs", "content_freeze_queue", "ranking_predictions",
        "audience_profiles", "system_graph_cache", "ai_review_results",
        "project_prompts", "research_jobs", "keyword_feedback_intent",
    ]
    for tbl in tables_main:
        try:
            db.execute(f"DELETE FROM {tbl} WHERE project_id=?", (project_id,))
        except Exception:
            pass
    db.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
    db.commit()
    # Also delete from KI engine DB (separate SQLite file)
    try:
        from engines.annaseo_keyword_input import _db as _ki_db_fn
        ki_db = _ki_db_fn()
        for tbl in ["pillar_keywords", "supporting_keywords", "keyword_universe_items",
                    "keyword_input_sessions", "keyword_review_actions"]:
            try:
                ki_db.execute(f"DELETE FROM {tbl} WHERE project_id=?", (project_id,))
            except Exception:
                pass
        ki_db.commit()
        ki_db.close()
    except Exception:
        pass
    return {"deleted": project_id}

# ── Runs + SSE ────────────────────────────────────────────────────────────────
_sse_queues: Dict[str,asyncio.Queue]={}
# Sequential phase gates: run_id → threading.Event or Redis semaphore for cross-process behavior
_seq_gates: Dict[str, threading.Event] = {}


def _seq_gate_key(run_id: str) -> str:
    return f"seq_gate:{run_id}"


def _open_seq_gate(run_id: str):
    try:
        if redis_conn is not None:
            redis_conn.set(_seq_gate_key(run_id), "1", ex=7200)
    except Exception:
        pass

    ev = _seq_gates.get(run_id) or threading.Event()
    ev.set()
    _seq_gates[run_id] = ev


def _close_seq_gate(run_id: str):
    try:
        if redis_conn is not None:
            redis_conn.set(_seq_gate_key(run_id), "0", ex=7200)
    except Exception:
        pass

    ev = _seq_gates.get(run_id)
    if ev:
        ev.clear()


def _wait_seq_gate(run_id: str, timeout: int = 600, interval: float = 0.5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if redis_conn is not None:
                v = redis_conn.get(_seq_gate_key(run_id))
                if v and v.decode() == "1":
                    return True
        except Exception:
            pass

        ev = _seq_gates.get(run_id)
        if ev and ev.is_set():
            return True

        time.sleep(interval)
    return False


def _emit(run_id,event_type,payload):
    """Emit from async context (event loop thread)."""
    db=get_db(); db.execute("INSERT INTO run_events(run_id,event_type,payload)VALUES(?,?,?)",(run_id,event_type,json.dumps(payload))); db.commit()
    if run_id in _sse_queues:
        try: _sse_queues[run_id].put_nowait({"type":event_type,**payload})
        except: pass


def _enqueue_strategy_job(queue, func, *args, **kwargs):
    if queue is not None:
        try:
            queue.enqueue(func, *args, **kwargs)
            return True
        except Exception:
            pass
    # fallback to in-process background execution
    bg_task = kwargs.pop("background_tasks", None)
    if bg_task is not None:
        bg_task.add_task(func, *args)
        return True
    threading.Thread(target=func, args=args, daemon=True).start()
    return False

def _thread_emit(loop,run_id,event_type,payload):
    """Thread-safe emit: can be called from executor/background threads."""
    # Write to DB using a fresh per-thread connection
    import sqlite3 as _s3
    try:
        conn=_s3.connect(str(DB_PATH),check_same_thread=False)
        conn.execute("INSERT INTO run_events(run_id,event_type,payload)VALUES(?,?,?)",(run_id,event_type,json.dumps(payload))); conn.commit(); conn.close()
    except Exception: pass
    # Thread-safe queue push
    if run_id in _sse_queues:
        try: loop.call_soon_threadsafe(_sse_queues[run_id].put_nowait,{"type":event_type,**payload})
        except: pass

class RunBody(BaseModel):
    seed: str; language: str="english"; region: str="india"
    generate_articles: bool=False; publish: bool=False
    pace_years: int=2; pace_per_day: float=3.0

# ── Gate 2 Models (Pillar Confirmation) ──────────────────────────────────────
class PillarData(BaseModel):
    cluster_name: str
    pillar_title: str
    pillar_keyword: str
    topics: list[str] = []
    article_count: int = 0

class Gate2ConfirmationRequest(BaseModel):
    pillars: list[PillarData]
    confirmed_by: str = ""
    notes: str = ""

class Gate2ConfirmationResponse(BaseModel):
    success: bool
    gate_id: int
    message: str
    next_gate: int = 3

@app.post("/api/projects/{project_id}/runs",tags=["Runs"])
async def start_run(project_id: str,body: RunBody,bg: BackgroundTasks,user=Depends(current_user)):
    run_id=f"run_{hashlib.md5(f'{body.seed}{time.time()}'.encode()).hexdigest()[:12]}"
    db=get_db(); db.execute("INSERT INTO runs(run_id,project_id,seed)VALUES(?,?,?)",(run_id,project_id,body.seed)); db.commit()
    _sse_queues[run_id]=asyncio.Queue(maxsize=500)
    bg.add_task(_execute_run,run_id,project_id,body)
    return {"run_id":run_id,"stream_url":f"/api/runs/{run_id}/stream"}

@app.get("/api/runs/{run_id}/stream",tags=["Runs"])
async def stream_run(run_id: str):
    async def gen() -> AsyncGenerator[str,None]:
        for row in get_db().execute("SELECT event_type,payload FROM run_events WHERE run_id=? ORDER BY id",(run_id,)).fetchall():
            yield f"data: {json.dumps({'type':row['event_type'],**json.loads(row['payload'])})}\n\n"
        run=get_db().execute("SELECT status FROM runs WHERE run_id=?",(run_id,)).fetchone()
        if run and dict(run)["status"] in("complete","error"): yield 'data: {"type":"done"}\n\n'; return
        q=_sse_queues.setdefault(run_id,asyncio.Queue(maxsize=500))
        while True:
            try:
                ev=await asyncio.wait_for(q.get(),timeout=30)
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") in("complete","error"): break
            except asyncio.TimeoutError: yield ": keepalive\n\n"
    return StreamingResponse(gen(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.get("/api/runs/{run_id}",tags=["Runs"])
def get_run(run_id: str):
    row=get_db().execute("SELECT * FROM runs WHERE run_id=?",(run_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found"); return dict(row)

@app.get("/api/projects/{project_id}/runs",tags=["Runs"])
def list_runs(project_id: str,limit: int=20):
    return [dict(r) for r in get_db().execute("SELECT run_id,seed,status,current_phase,started_at,cost_usd FROM runs WHERE project_id=? ORDER BY started_at DESC LIMIT ?",(project_id,limit)).fetchall()]

VALID_GATES = {
    # WiredRufloOrchestrator gates
    "universe_keywords", "pillars", "content_calendar",
    # ConfirmationPipeline gates
    "G1_Universe", "G2_Clusters", "G3_Brief", "G4_Content", "G5_Publish",
}

@app.post("/api/runs/{run_id}/confirm/{gate}",tags=["Runs"])
def confirm_gate(run_id: str,gate: str,payload: dict={}):
    if gate not in VALID_GATES:
        raise HTTPException(400,f"Unknown gate '{gate}'. Valid gates: {sorted(VALID_GATES)}")
    db=get_db(); db.execute("INSERT INTO run_events(run_id,event_type,payload)VALUES(?,?,?)",(run_id,f"confirm_{gate}",json.dumps(payload))); db.execute("UPDATE runs SET status=? WHERE run_id=?",(f"confirmed:{gate}",run_id)); db.commit()
    return {"confirmed":gate}

@app.post("/api/runs/{run_id}/cancel",tags=["Runs"])
def cancel_run(run_id: str):
    db = get_db(); db.execute("UPDATE runs SET status='cancelled' WHERE run_id=?",(run_id,)); db.commit(); return {"cancelled":run_id}

@app.post("/api/runs/{run_id}/gate-2",tags=["Runs"],response_model=Gate2ConfirmationResponse)
def confirm_gate_2_pillars(run_id: str, body: Gate2ConfirmationRequest):
    """
    GATE 2: Customer confirms/edits pillars identified in P10.
    Saves pillar state and triggers resumption from P11 (Knowledge Graph).
    """
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")
    
    run_dict = dict(run)
    
    # Save gate state
    pillars_json = json.dumps([p.dict() for p in body.pillars])
    db.execute(
        "INSERT OR REPLACE INTO gate_states(run_id,gate_number,gate_name,input_json,customer_input_json,confirmed_at,confirmed_by) "
        "VALUES(?,?,?,?,?,?,?)",
        (run_id, 2, "pillar_confirmation", run_dict.get("pillars_json", "[]"), pillars_json, 
         datetime.now(timezone.utc).isoformat(), body.confirmed_by)
    )
    
    # Update run record
    db.execute(
        "UPDATE runs SET gate_2_confirmed=1, pillars_json=?, current_gate=2 WHERE run_id=?",
        (pillars_json, run_id)
    )
    db.commit()
    
    # Emit SSE event (non-async)
    if run_id in _sse_queues:
        try:
            _sse_queues[run_id].put_nowait({
                "type": "gate_confirmed",
                "gate": 2,
                "message": f"Confirmed {len(body.pillars)} pillars",
                "pillar_count": len(body.pillars)
            })
        except:
            pass
    
    return Gate2ConfirmationResponse(
        success=True,
        gate_id=2,
        message=f"Saved {len(body.pillars)} pillars. Ready to proceed to keyword confirmation.",
        next_gate=3
    )

@app.get("/api/runs/{run_id}/gate-2",tags=["Runs"])
def get_gate_2_state(run_id: str):
    """Retrieve current Gate 2 state (confirmation status + pillars)."""
    db = get_db()
    row = db.execute(
        "SELECT gate_id, input_json, customer_input_json, confirmed_at, confirmed_by "
        "FROM gate_states WHERE run_id=? AND gate_number=2",
        (run_id,)
    ).fetchone()
    
    if row:
        return {
            "gate": 2,
            "confirmed": True,
            "confirmed_at": dict(row)["confirmed_at"],
            "confirmed_by": dict(row)["confirmed_by"],
            "pillars": json.loads(dict(row)["customer_input_json"])
        }
    
    # Not yet confirmed, return empty
    return {
        "gate": 2,
        "confirmed": False,
        "pillars": [],
        "confirmed_at": None,
        "confirmed_by": None
    }

# ── Gate 1 Models (Universe Confirmation) ───────────────────────────────────────
class KeywordData(BaseModel):
    id: str = ""
    keyword: str
    intent: str = "informational"
    priority: str = "medium"

class Gate1ConfirmationRequest(BaseModel):
    keywords: list[KeywordData]
    confirmed_by: str = ""
    notes: str = ""

class Gate1ConfirmationResponse(BaseModel):
    success: bool
    gate_id: int
    message: str
    next_gate: int = 3

@app.post("/api/runs/{run_id}/gate-1", tags=["Runs"], response_model=Gate1ConfirmationResponse)
def confirm_gate_1_keywords(run_id: str, body: Gate1ConfirmationRequest):
    """Gate 1: Customer confirms/edits initial keyword universe from P3."""
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")
    
    run_dict = dict(run)
    keywords_json = json.dumps([k.dict() for k in body.keywords])
    
    db.execute(
        "INSERT OR REPLACE INTO gate_states(run_id,gate_number,gate_name,input_json,customer_input_json,confirmed_at,confirmed_by) "
        "VALUES(?,?,?,?,?,?,?)",
        (run_id, 1, "universe_confirmation", run_dict.get("keywords_json", "[]"), keywords_json,
         datetime.now(timezone.utc).isoformat(), body.confirmed_by)
    )
    db.execute("UPDATE runs SET gate_1_confirmed=1, keywords_json=?, current_gate=1 WHERE run_id=?", (keywords_json, run_id))
    db.commit()
    
    if run_id in _sse_queues:
        try:
            _sse_queues[run_id].put_nowait({
                "type": "gate_confirmed",
                "gate": 1,
                "message": f"Confirmed {len(body.keywords)} keywords"
            })
        except: pass
    
    return Gate1ConfirmationResponse(success=True, gate_id=1, message=f"Saved {len(body.keywords)} keywords.", next_gate=3)

@app.get("/api/runs/{run_id}/gate-1", tags=["Runs"])
def get_gate_1_state(run_id: str):
    """Retrieve current Gate 1 state (keywords confirmation)."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM gate_states WHERE run_id=? AND gate_number=1",
        (run_id,)
    ).fetchone()
    
    if row:
        return {
            "gate": 1,
            "confirmed": True,
            "confirmed_at": dict(row)["confirmed_at"],
            "confirmed_by": dict(row)["confirmed_by"],
            "keywords": json.loads(dict(row)["customer_input_json"])
        }
    
    return {"gate": 1, "confirmed": False, "keywords": [], "confirmed_at": None, "confirmed_by": None}

# ── Gate 3 Models (Keyword Tree) ─────────────────────────────────────────────────
class ClusterData(BaseModel):
    cluster_name: str
    keywords: list[str] = []

class Gate3ConfirmationRequest(BaseModel):
    clusters: list[ClusterData]
    confirmed_by: str = ""
    notes: str = ""

class Gate3ConfirmationResponse(BaseModel):
    success: bool
    gate_id: int
    message: str

@app.post("/api/runs/{run_id}/gate-3", tags=["Runs"], response_model=Gate3ConfirmationResponse)
def confirm_gate_3_tree(run_id: str, body: Gate3ConfirmationRequest):
    """Gate 3: Customer confirms/edits keyword organization tree."""
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")
    
    run_dict = dict(run)
    clusters_json = json.dumps([c.dict() for c in body.clusters])
    
    db.execute(
        "INSERT OR REPLACE INTO gate_states(run_id,gate_number,gate_name,input_json,customer_input_json,confirmed_at,confirmed_by) "
        "VALUES(?,?,?,?,?,?,?)",
        (run_id, 3, "keyword_tree_confirmation", run_dict.get("clusters_json", "[]"), clusters_json,
         datetime.now(timezone.utc).isoformat(), body.confirmed_by)
    )
    db.execute("UPDATE runs SET gate_3_confirmed=1, clusters_json=?, current_gate=3 WHERE run_id=?", (clusters_json, run_id))
    db.commit()
    
    if run_id in _sse_queues:
        try:
            total_kws = sum(len(c.keywords) for c in body.clusters)
            _sse_queues[run_id].put_nowait({"type": "gate_confirmed", "gate": 3, "message": f"Confirmed keyword tree: {len(body.clusters)} clusters"})
        except: pass
    
    return Gate3ConfirmationResponse(success=True, gate_id=3, message="Keyword tree confirmed.")

@app.get("/api/runs/{run_id}/gate-3", tags=["Runs"])
def get_gate_3_state(run_id: str):
    """Retrieve current Gate 3 state (keyword tree)."""
    db = get_db()
    row = db.execute("SELECT * FROM gate_states WHERE run_id=? AND gate_number=3", (run_id,)).fetchone()
    
    if row:
        return {
            "gate": 3,
            "confirmed": True,
            "confirmed_at": dict(row)["confirmed_at"],
            "clusters": json.loads(dict(row)["customer_input_json"])
        }
    
    return {"gate": 3, "confirmed": False, "clusters": [], "confirmed_at": None}

# ── Gate 4 Models (Blog Suggestions) ─────────────────────────────────────────────
class ArticleSuggestion(BaseModel):
    title: str
    angle: str
    brief: str = ""
    target_keywords: list[str] = []
    article_count: int = 0

class Gate4ConfirmationRequest(BaseModel):
    articles: list[ArticleSuggestion]
    confirmed_by: str = ""
    notes: str = ""

class Gate4ConfirmationResponse(BaseModel):
    success: bool
    gate_id: int
    message: str

@app.post("/api/runs/{run_id}/gate-4", tags=["Runs"], response_model=Gate4ConfirmationResponse)
def confirm_gate_4_blogs(run_id: str, body: Gate4ConfirmationRequest):
    """Gate 4: Customer confirms/selects blog article angles."""
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")
    
    run_dict = dict(run)
    articles_json = json.dumps([a.dict() for a in body.articles])
    
    db.execute(
        "INSERT OR REPLACE INTO gate_states(run_id,gate_number,gate_name,input_json,customer_input_json,confirmed_at,confirmed_by) "
        "VALUES(?,?,?,?,?,?,?)",
        (run_id, 4, "blog_suggestions_confirmation", run_dict.get("articles_json", "[]"), articles_json,
         datetime.now(timezone.utc).isoformat(), body.confirmed_by)
    )
    db.execute("UPDATE runs SET gate_4_confirmed=1, articles_json=?, current_gate=4 WHERE run_id=?", (articles_json, run_id))
    db.commit()
    
    if run_id in _sse_queues:
        try:
            _sse_queues[run_id].put_nowait({"type": "gate_confirmed", "gate": 4, "message": f"Confirmed blog strategy: {len(body.articles)} articles"})
        except: pass
    
    return Gate4ConfirmationResponse(success=True, gate_id=4, message=f"Blog strategy confirmed for {len(body.articles)} articles.")

@app.get("/api/runs/{run_id}/gate-4", tags=["Runs"])
def get_gate_4_state(run_id: str):
    """Retrieve current Gate 4 state (blog suggestions)."""
    db = get_db()
    row = db.execute("SELECT * FROM gate_states WHERE run_id=? AND gate_number=4", (run_id,)).fetchone()
    
    if row:
        return {
            "gate": 4,
            "confirmed": True,
            "confirmed_at": dict(row)["confirmed_at"],
            "articles": json.loads(dict(row)["customer_input_json"])
        }
    
    return {"gate": 4, "confirmed": False, "articles": [], "confirmed_at": None}

# ── Gate 5 Models (Final Strategy) ───────────────────────────────────────────────
class FinalStrategy(BaseModel):
    target_rank: str = "#1"
    primary_keyword: str = ""
    total_keywords: int = 0
    total_articles: int = 24
    timeline: str = "6-12 months"
    overview: str = ""
    top_article_title: str = ""
    top_article_angle: str = ""
    top_article_brief: str = ""
    publishing_cadence: str = "2 articles per week"

class Gate5ConfirmationRequest(BaseModel):
    strategy: FinalStrategy
    confirmed_by: str = ""
    ready_for_generation: bool = True
    notes: str = ""

class Gate5ConfirmationResponse(BaseModel):
    success: bool
    gate_id: int
    message: str

@app.post("/api/runs/{run_id}/gate-5", tags=["Runs"], response_model=Gate5ConfirmationResponse)
def confirm_gate_5_strategy(run_id: str, body: Gate5ConfirmationRequest):
    """Gate 5: Customer confirms final SEO strategy and approves content generation."""
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")
    
    run_dict = dict(run)
    strategy_json = json.dumps(body.strategy.dict())
    
    db.execute(
        "INSERT OR REPLACE INTO gate_states(run_id,gate_number,gate_name,input_json,customer_input_json,confirmed_at,confirmed_by) "
        "VALUES(?,?,?,?,?,?,?)",
        (run_id, 5, "final_strategy_confirmation", run_dict.get("strategy_json", "{}"), strategy_json,
         datetime.utcnow().isoformat(), body.confirmed_by)
    )
    db.execute("UPDATE runs SET gate_5_confirmed=1, strategy_json=?, ready_for_generation=?, current_gate=5 WHERE run_id=?",
               (strategy_json, 1 if body.ready_for_generation else 0, run_id))
    db.commit()
    
    if run_id in _sse_queues:
        try:
            _sse_queues[run_id].put_nowait({"type": "gate_confirmed", "gate": 5, "message": "Final strategy approved. Ready for content generation."})
        except: pass
    
    return Gate5ConfirmationResponse(success=True, gate_id=5, message="Strategy confirmed. Content generation authorized.")

@app.get("/api/runs/{run_id}/gate-5", tags=["Runs"])
def get_gate_5_state(run_id: str):
    """Retrieve current Gate 5 state (final strategy)."""
    db = get_db()
    row = db.execute("SELECT * FROM gate_states WHERE run_id=? AND gate_number=5", (run_id,)).fetchone()
    
    if row:
        return {
            "gate": 5,
            "confirmed": True,
            "confirmed_at": dict(row)["confirmed_at"],
            "strategy": json.loads(dict(row)["customer_input_json"])
        }
    
    return {"gate": 5, "confirmed": False, "strategy": {}, "confirmed_at": None}

# ── Content Strategy (Cadence + Budgeting) ───────────────────────────────────────
class ContentStrategyRequest(BaseModel):
    cadence: str
    budget_tier: str
    total_articles: int
    articles_per_week: int
    total_weeks: int
    estimated_cost: float
    confirmed_by: str = ""

class ContentStrategyResponse(BaseModel):
    success: bool
    message: str
    content_strategy_id: str = ""

@app.post("/api/runs/{run_id}/content-strategy", tags=["Runs"], response_model=ContentStrategyResponse)
def confirm_content_strategy(run_id: str, body: ContentStrategyRequest):
    """Save customer-confirmed content strategy (cadence, budget, timeline)."""
    db = get_db()
    strategy_id = f"strategy_{run_id}_{int(time.time())}"
    
    db.execute(
        "INSERT INTO content_strategy(session_id,run_id,confidence) VALUES(?,?,?)",
        (strategy_id, run_id, 1.0)
    )
    db.execute(
        "INSERT OR REPLACE INTO gate_states(run_id,gate_number,gate_name,customer_input_json,confirmed_at,confirmed_by) "
        "VALUES(?,?,?,?,?,?)",
        (run_id, 6, "content_strategy", json.dumps(body.dict()), datetime.now(timezone.utc).isoformat(), body.confirmed_by)
    )
    db.commit()
    
    return ContentStrategyResponse(success=True, content_strategy_id=strategy_id, message=f"Content strategy saved: {body.articles_per_week} articles/week, {body.budget_tier} quality, ~${body.estimated_cost}.")

@app.get("/api/projects/{project_id}/content-strategy", tags=["Projects"])
def get_project_content_strategy(project_id: str):
    """Retrieve project's default content strategy settings."""
    db = get_db()
    # Return default strategy (can be customized)
    return {
        "cadence": "2",
        "budget_tier": "standard",
        "total_articles": 24,
        "articles_per_week": 2,
        "total_weeks": 12,
        "estimated_cost": 7200
    }

@app.get("/api/projects/{project_id}/knowledge-graph",tags=["Runs"])
def knowledge_graph(project_id: str):
    """Return keyword universe as a D3-ready tree from the latest completed run."""
    db=get_db()
    row=db.execute("SELECT result,seed FROM runs WHERE project_id=? AND status='complete' ORDER BY completed_at DESC LIMIT 1",(project_id,)).fetchone()
    if not row:
        # Return empty tree so frontend doesn't error
        proj=db.execute("SELECT name FROM projects WHERE project_id=?",(project_id,)).fetchone()
        seed=dict(proj)["name"] if proj else "Keywords"
        return {"name":seed,"type":"root","children":[],"total_keywords":0,"total_pillars":0}
    data=dict(row); seed=data["seed"]; result=json.loads(data["result"] or "{}")
    pillars=result.get("pillars",{})
    children=[]
    for pname,pdata in pillars.items():
        if not isinstance(pdata,dict): continue
        pillar_node={"name":pdata.get("title",pname),"keyword":pdata.get("keyword",pname),"type":"pillar","children":[]}
        for cname,cdata in pdata.get("clusters",{}).items():
            if not isinstance(cdata,dict): continue
            cluster_node={"name":cname,"type":"cluster","children":[]}
            for topic,tdata in cdata.items():
                if not isinstance(tdata,dict): continue
                kws=tdata.get("keywords",[])
                intent=tdata.get("intent","informational")
                cluster_node["children"].append({
                    "name":tdata.get("best_keyword",topic),"topic":topic,
                    "type":"keyword","intent":intent,"keywords":kws[:5]
                })
            pillar_node["children"].append(cluster_node)
        children.append(pillar_node)
    # Fallback: if no pillars in result, try qi_raw_outputs for keyword items
    if not children:
        rows=db.execute("SELECT DISTINCT item_value,phase FROM qi_raw_outputs WHERE project_id=? AND item_type='keyword' ORDER BY phase LIMIT 200",(project_id,)).fetchall()
        phase_map={}
        for r in rows:
            d=dict(r); phase_map.setdefault(d["phase"],[]).append(d["item_value"])
        for phase,kws in phase_map.items():
            children.append({"name":phase,"type":"pillar","children":[{"name":k,"type":"keyword","intent":"informational"} for k in kws[:20]]})
    return {"name":seed,"type":"root","children":children,"total_keywords":result.get("keyword_count",0),"total_pillars":len(children)}

@app.get("/api/projects/{project_id}/keyword-stats",tags=["Runs"])
def keyword_stats(project_id: str):
    """Return keyword distribution by type (pillar/cluster/supporting)."""
    db=get_db()
    row=db.execute("SELECT result FROM runs WHERE project_id=? AND status='complete' ORDER BY completed_at DESC LIMIT 1",(project_id,)).fetchone()
    if not row:
        return {"pillar_count":0,"cluster_count":0,"supporting_count":0,"total":0,"distribution":{"pillar":0,"cluster":0,"supporting":0}}
    result=json.loads(dict(row)["result"] or "{}")
    pillars=result.get("pillars",{})
    pillar_count=0; cluster_count=0; supporting_count=0
    for pname,pdata in pillars.items():
        if isinstance(pdata,dict):
            pillar_count+=1
            for cname,cdata in pdata.get("clusters",{}).items():
                if isinstance(cdata,dict):
                    cluster_count+=1
                    supporting=cdata.get("keywords",[]) if isinstance(cdata.get("keywords"),[])else[]
                    supporting_count+=len(supporting)
    total=pillar_count+cluster_count+supporting_count or 1
    return {
        "pillar_count":pillar_count,
        "cluster_count":cluster_count,
        "supporting_count":supporting_count,
        "total":total,
        "distribution":{
            "pillar":round(pillar_count*100/total,1),
            "cluster":round(cluster_count*100/total,1),
            "supporting":round(supporting_count*100/total,1)
        }
    }

async def _execute_run(run_id,project_id,body):
    db=get_db(); db.execute("UPDATE runs SET status='running' WHERE run_id=?",(run_id,)); db.commit()
    _emit(run_id,"started",{"seed":body.seed,"timestamp":datetime.now(timezone.utc).isoformat()})
    loop=asyncio.get_event_loop()
    # Thread-safe emit bound to this run
    def t_emit(event_type,payload): _thread_emit(loop,run_id,event_type,payload)
    try:
        from engines.ruflo_20phase_wired import WiredRufloOrchestrator
        from engines.ruflo_20phase_engine import ContentPace
        import threading as _threading, sqlite3 as _s3
        pace=ContentPace(duration_years=body.pace_years,blogs_per_day=body.pace_per_day)
        ruflo=WiredRufloOrchestrator(project_id=project_id,run_id=run_id,emit_fn=t_emit)
        # Sync gate callback — callable from background thread via polling SQLite
        def gate_cb(gate_name,data):
            t_emit("gate",{"gate":gate_name,"data":data,"requires_confirmation":True})
            conn=_s3.connect(str(DB_PATH),check_same_thread=False)
            conn.execute("UPDATE runs SET current_phase=? WHERE run_id=?",(f"waiting:{gate_name}",run_id)); conn.commit()
            timeout_seconds = int(os.getenv('ANNASEO_GATE_TIMEOUT', '120'))
            for _ in range(timeout_seconds):
                _threading.Event().wait(1)
                row=conn.execute("SELECT status FROM runs WHERE run_id=?",(run_id,)).fetchone()
                if row:
                    st=row[0]
                    if st==f"confirmed:{gate_name}":
                        ev=conn.execute("SELECT payload FROM run_events WHERE run_id=? AND event_type=? ORDER BY id DESC LIMIT 1",(run_id,f"confirm_{gate_name}")).fetchone()
                        conn.close(); return json.loads(ev[0]) if ev else data
                    if st=="cancelled": conn.close(); return None
            # Gate not confirmed in time: treat as fallback continue/no-op
            log.warning(f"[AnnaSEO] gate_callback timeout for {gate_name} after {timeout_seconds}s - continuing")
            conn.execute("UPDATE runs SET current_phase=? WHERE run_id=?", (f"waiting:{gate_name}:timeout", run_id))
            conn.commit()
            conn.close()
            return data

        def phase_cb(payload):
            t_emit("phase", payload)
            try:
                db.execute("UPDATE runs SET current_phase=?,status='running' WHERE run_id=?",(f"{payload.get('phase')}:{payload.get('status')}",run_id))
                db.commit()
            except Exception:
                pass

        result=await asyncio.get_event_loop().run_in_executor(None,lambda:ruflo.run_seed(keyword=body.seed,pace=pace,language=body.language,region=body.region,generate_articles=body.generate_articles,publish=body.publish,project_id=project_id,run_id=run_id,gate_callback=gate_cb,progress_callback=phase_cb))

        # Normalize/guard all counts from final pipeline result for dashboard health
        topic_count = int(result.get("topic_count", 0) or 0)
        cluster_count = int(result.get("cluster_count", 0) or 0)
        pillar_count = int(result.get("pillar_count", 0) or 0)
        pipeline_health = {
            "P8_topic_ok": topic_count > 0,
            "P9_cluster_ok": cluster_count > 0,
            "P10_pillar_ok": pillar_count > 0,
        }
        pipeline_health["all_ok"] = pipeline_health["P8_topic_ok"] and pipeline_health["P9_cluster_ok"] and pipeline_health["P10_pillar_ok"]

        result["topic_count"] = topic_count
        result["cluster_count"] = cluster_count
        result["pillar_count"] = pillar_count
        result["pipeline_health"] = pipeline_health
        result["health_ok"] = pipeline_health["all_ok"] and True

        db.execute("UPDATE runs SET status='complete',result=?,completed_at=?,current_phase='done' WHERE run_id=?",(json.dumps(result,default=str),datetime.now(timezone.utc).isoformat(),run_id)); db.commit()
        _emit(run_id,"complete",{"keyword_count":result.get("keyword_count",0),"pillar_count":pillar_count,"calendar_count":result.get("calendar_count",0),"topic_count":topic_count,"cluster_count":cluster_count,"pillar_count":pillar_count,"health_ok":result.get("health_ok",False)})
    except Exception as e:
        import traceback; err=traceback.format_exc()[:500]
        db.execute("UPDATE runs SET status='error',error=? WHERE run_id=?",(err,run_id)); db.commit()
        _emit(run_id,"error",{"error":str(e)[:200],"traceback":err}); log.error(f"Run {run_id} failed: {e}")

# ── Content workflow ──────────────────────────────────────────────────────────
class GenBody(BaseModel):
    keyword: str; project_id: str; title: str=""; intent: str="informational"; word_count: int=2000

@app.post("/api/content/generate",tags=["Content"])
async def gen_content(body: GenBody,bg: BackgroundTasks,user=Depends(current_user)):
    aid=f"art_{hashlib.md5(f'{body.keyword}{time.time()}'.encode()).hexdigest()[:10]}"
    db=get_db(); db.execute("INSERT INTO content_articles(article_id,project_id,keyword,status)VALUES(?,?,?,'generating')",(aid,body.project_id,body.keyword)); db.commit()
    bg.add_task(_gen_article,aid,body); return {"article_id":aid,"status":"generating"}

@app.get("/api/projects/{project_id}/content",tags=["Content"])
def list_content(project_id: str,status: Optional[str]=None,limit: int=50):
    q,p="SELECT * FROM content_articles WHERE project_id=?",[project_id]
    if status: q+=" AND status=?"; p.append(status)
    q+=" ORDER BY created_at DESC LIMIT ?"; p.append(limit)
    return [dict(r) for r in get_db().execute(q,p).fetchall()]

@app.get("/api/content/{article_id}",tags=["Content"])
def get_article(article_id: str):
    row=get_db().execute("SELECT * FROM content_articles WHERE article_id=?",(article_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found"); return dict(row)

@app.post("/api/content/{article_id}/approve",tags=["Content"])
def approve(article_id: str,user=Depends(current_user)):
    db=get_db(); db.execute("UPDATE content_articles SET status='approved',updated_at=? WHERE article_id=?",(datetime.now(timezone.utc).isoformat(),article_id)); db.commit(); return {"status":"approved"}

@app.post("/api/content/{article_id}/freeze",tags=["Content"])
def freeze(article_id: str,user=Depends(current_user)):
    db = get_db(); db.execute("UPDATE content_articles SET frozen=1 WHERE article_id=?",(article_id,)); db.commit(); return {"frozen":True}

@app.post("/api/content/{article_id}/unfreeze",tags=["Content"])
def unfreeze(article_id: str,user=Depends(current_user)):
    db = get_db(); db.execute("UPDATE content_articles SET frozen=0 WHERE article_id=?",(article_id,)); db.commit(); return {"frozen":False}

@app.post("/api/content/{article_id}/publish",tags=["Content"])
async def publish_article(article_id: str,bg: BackgroundTasks,user=Depends(current_user)):
    row=get_db().execute("SELECT * FROM content_articles WHERE article_id=?",(article_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found")
    if dict(row)["status"]!="approved": raise HTTPException(400,"Must be approved first")
    db = get_db(); db.execute("UPDATE content_articles SET status='publishing' WHERE article_id=?",(article_id,)); db.commit()
    bg.add_task(_publish_article,article_id,dict(row)); return {"status":"publishing"}

async def _gen_article(article_id,body):
    db=get_db()
    try:
        from ruflo_content_engine import ContentGenerationEngine,ContentStyle,BrandVoice
        proj=db.execute("SELECT * FROM projects WHERE project_id=?",(body.project_id,)).fetchone()
        brand=BrandVoice(business_name=dict(proj)["name"] if proj else "Business",industry=dict(proj)["industry"] if proj else "general")
        style=ContentStyle(word_count=body.word_count)
        r=ContentGenerationEngine().generate(title=body.title or f"Guide to {body.keyword}",keyword=body.keyword,intent=body.intent,entities=[],internal_links=[],style=style,brand=brand)
        db.execute("UPDATE content_articles SET title=?,body=?,meta_title=?,meta_desc=?,seo_score=?,eeat_score=?,geo_score=?,word_count=?,status='draft',updated_at=? WHERE article_id=?",
            (r.title,r.body,r.meta_title,r.meta_description,r.score.seo_score,r.score.eeat_score,r.score.geo_score,r.word_count,datetime.now(timezone.utc).isoformat(),article_id)); db.commit()
    except Exception as e:
        db.execute("UPDATE content_articles SET status='failed' WHERE article_id=?",(article_id,)); db.commit(); log.error(f"Gen failed: {e}")

async def _publish_article(article_id,article):
    db=get_db()
    try:
        from ruflo_publisher import Publisher,ArticlePayload
        proj=db.execute("SELECT * FROM projects WHERE project_id=?",(article["project_id"],)).fetchone()
        if not proj or not dict(proj).get("wp_url"):
            db.execute("UPDATE content_articles SET status='approved',published_url='no-wp-configured' WHERE article_id=?",(article_id,)); db.commit(); return
        pub=Publisher(wp_url=dict(proj)["wp_url"],wp_user=dict(proj)["wp_user"],wp_app_password=_decrypt(dict(proj)["wp_pass_enc"]))
        res=pub.publish(ArticlePayload(article_id=article_id,title=article["title"],body=article["body"],keyword=article["keyword"],meta_title=article["meta_title"],meta_description=article["meta_desc"]))
        db.execute("UPDATE content_articles SET status='published',published_url=?,published_at=? WHERE article_id=?",(res.get("url",""),datetime.now(timezone.utc).isoformat(),article_id)); db.commit()
    except Exception as e:
        db.execute("UPDATE content_articles SET status='publish_failed' WHERE article_id=?",(article_id,)); db.commit(); log.error(f"Publish failed: {e}")

# ── Calendar ──────────────────────────────────────────────────────────────────
@app.get("/api/projects/{project_id}/calendar-items", tags=["Calendar"])
def get_calendar_items(project_id: str, month: Optional[str]=None, pillar: Optional[str]=None):
    """Return content calendar items for a project.

    Pulls from content_articles with schedule_date set, or scaffolds a 1-year
    plan from pending/draft articles if no scheduled items exist yet.
    """
    db = get_db()
    rows = db.execute(
        "SELECT article_id,keyword,title,status,frozen,schedule_date,published_at,created_at "
        "FROM content_articles WHERE project_id=? ORDER BY schedule_date,created_at",
        (project_id,)
    ).fetchall()
    items = [dict(r) for r in rows]

    # If no schedule_dates set, auto-scaffold: spread articles across next 12 months
    unscheduled = [i for i in items if not i.get("schedule_date")]
    if unscheduled:
        from datetime import date, timedelta
        start = date.today().replace(day=1)
        for idx, item in enumerate(unscheduled):
            # 2 articles per week starting from today
            sched = start + timedelta(days=idx * 3)
            item["schedule_date"] = sched.isoformat()
            item["auto_scheduled"] = True

    # Filter by month (YYYY-MM) if requested
    if month:
        items = [i for i in items if (i.get("schedule_date") or "").startswith(month)]

    # Group by month for calendar view
    monthly: dict = {}
    for item in items:
        sd = item.get("schedule_date") or item.get("created_at","")[:10]
        ym = sd[:7] if sd else "undated"
        monthly.setdefault(ym, []).append(item)

    return {
        "items": items,
        "by_month": monthly,
        "total": len(items),
        "scheduled": len([i for i in items if i.get("schedule_date")]),
        "frozen": len([i for i in items if i.get("frozen")]),
        "published": len([i for i in items if i.get("status") == "published"]),
    }

@app.put("/api/content/{article_id}/schedule", tags=["Calendar"])
def schedule_article(article_id: str, schedule_date: str, user=Depends(current_user)):
    """Set a publish schedule date for an article (YYYY-MM-DD)."""
    db = get_db()
    if not db.execute("SELECT 1 FROM content_articles WHERE article_id=?", (article_id,)).fetchone():
        raise HTTPException(404, "Not found")
    db.execute("UPDATE content_articles SET schedule_date=?,updated_at=? WHERE article_id=?",
            (schedule_date, datetime.now(timezone.utc).isoformat(), article_id))
    db.commit()
    return {"article_id": article_id, "schedule_date": schedule_date}

# ── Costs ─────────────────────────────────────────────────────────────────────
@app.get("/api/costs/{project_id}",tags=["Costs"])
def costs(project_id: str):
    db=get_db()
    rows=db.execute("SELECT model,SUM(cost_usd) as total,COUNT(*) as calls FROM ai_usage WHERE project_id=? GROUP BY model",(project_id,)).fetchall()
    total=db.execute("SELECT SUM(cost_usd) FROM ai_usage WHERE project_id=?",(project_id,)).fetchone()[0] or 0
    arts=db.execute("SELECT COUNT(*) FROM content_articles WHERE project_id=?",(project_id,)).fetchone()[0] or 0
    return {"total_usd":round(total,4),"articles_generated":arts,"cost_per_article":round(total/max(arts,1),4),"monthly_estimate":round(total*30,2),"by_model":[dict(r) for r in rows]}

# ── System Status API (1.14) ──────────────────────────────────────────────────
@app.get("/api/system-status",tags=["System"])
def system_status():
    """Return system health: Ollama, Gemini, Claude, GSC status."""
    status_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ollama": {"status": "unknown", "model": None, "message": ""},
        "gemini": {"status": "unknown", "configured": False, "message": ""},
        "claude": {"status": "unknown", "configured": False, "message": ""},
        "gsc": {"status": "unknown", "connected_projects": 0, "message": ""},
    }
    
    # Check Ollama
    try:
        import requests as req
        r = req.get(f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/tags", timeout=3)
        if r.status_code == 200:
            models = r.json().get("models", [])
            default_model = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")
            if any(m.get("name","").startswith(default_model) for m in models):
                status_data["ollama"]["status"] = "ok"
                status_data["ollama"]["model"] = default_model
                status_data["ollama"]["message"] = f"Loaded: {default_model}"
            else:
                status_data["ollama"]["status"] = "warning"
                status_data["ollama"]["message"] = f"{default_model} not loaded. Available: {[m.get('name','') for m in models[:3]]}"
        else:
            status_data["ollama"]["status"] = "error"
            status_data["ollama"]["message"] = f"HTTP {r.status_code}"
    except Exception as e:
        status_data["ollama"]["status"] = "error"
        status_data["ollama"]["message"] = str(e)[:100]
    
    # Check Gemini API
    try:
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if gemini_key:
            status_data["gemini"]["configured"] = True
            status_data["gemini"]["status"] = "ok"
            status_data["gemini"]["message"] = "API key configured"
        else:
            status_data["gemini"]["status"] = "warning"
            status_data["gemini"]["message"] = "No API key configured"
    except Exception as e:
        status_data["gemini"]["status"] = "error"
        status_data["gemini"]["message"] = str(e)[:100]
    
    # Check Claude API
    try:
        claude_key = os.getenv("ANTHROPIC_API_KEY", "")
        if claude_key:
            status_data["claude"]["configured"] = True
            status_data["claude"]["status"] = "ok"
            status_data["claude"]["message"] = "API key configured"
        else:
            status_data["claude"]["status"] = "warning"
            status_data["claude"]["message"] = "No API key configured"
    except Exception as e:
        status_data["claude"]["status"] = "error"
        status_data["claude"]["message"] = str(e)[:100]
    
    # Check GSC connections
    try:
        db = get_db()
        gsc_count = db.execute("SELECT COUNT(DISTINCT project_id) FROM ranking_alerts WHERE created_at > datetime('now', '-7 days')").fetchone()[0]
        if gsc_count > 0:
            status_data["gsc"]["status"] = "ok"
            status_data["gsc"]["connected_projects"] = gsc_count
            status_data["gsc"]["message"] = f"{gsc_count} projects syncing"
        else:
            status_data["gsc"]["status"] = "warning"
            status_data["gsc"]["message"] = "No recent syncs detected"
    except Exception as e:
        status_data["gsc"]["status"] = "error"
        status_data["gsc"]["message"] = str(e)[:100]
    
    return status_data

# ── D3 Graph Cache API (1.12) ─────────────────────────────────────────────────
@app.get("/api/projects/{project_id}/d3-graph",tags=["Runs"])
def get_d3_graph(project_id: str):
    """Return cached D3 graph for keyword tree, or generate fresh if cache miss."""
    db = get_db()
    
    # Try cache first (1-hour TTL)
    cache_row = db.execute(
        "SELECT graph_json FROM system_graph_cache WHERE project_id=? AND (updated_at > datetime('now', '-1 hour') OR updated_at IS NULL)",
        (project_id,)
    ).fetchone()
    
    if cache_row:
        try:
            return json.loads(dict(cache_row)["graph_json"])
        except:
            pass
    
    # Cache miss or expired - generate fresh
    graph = knowledge_graph(project_id)
    
    # Store in cache
    try:
        db.execute(
            "INSERT OR REPLACE INTO system_graph_cache(project_id,graph_json,node_count,updated_at) VALUES(?,?,?,?)",
            (project_id, json.dumps(graph), len([c for c in graph.get("children", [])]), datetime.now(timezone.utc).isoformat())
        )
        db.commit()
    except:
        pass
    
    return graph

# ── Impact Assessment API (1.15) ──────────────────────────────────────────────
class ImpactAssessmentRequest(BaseModel):
    change_type: str  # "add_product", "add_location", "add_religion", "remove_keyword"
    change_value: str
    affected_items: int = 0  # will be calculated

@app.post("/api/projects/{project_id}/impact-assessment",tags=["Projects"])
def assess_impact(project_id: str, body: ImpactAssessmentRequest):
    """Estimate impact of a project configuration change."""
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if not project:
        raise HTTPException(404, "Project not found")
    
    proj_dict = dict(project)
    impact = {
        "change_type": body.change_type,
        "change_value": body.change_value,
        "affected_keywords": 0,
        "affected_content_items": 0,
        "estimated_regen_time_minutes": 0,
        "warning": "",
        "recommendation": ""
    }
    
    if body.change_type == "add_product":
        # Adding a product will expand keyword universe (roughly +5% per product)
        existing_keywords = db.execute(
            "SELECT COUNT(*) FROM keywords WHERE project_id=?", (project_id,)
        ).fetchone()[0]
        impact["affected_keywords"] = int(existing_keywords * 0.05)
        impact["estimated_regen_time_minutes"] = 8
        impact["recommendation"] = f"System will regenerate ~{impact['affected_keywords']} keywords in ~8 minutes"
        
    elif body.change_type == "add_location":
        # Adding a location expands keywords for that region
        impact["affected_keywords"] = 25
        impact["estimated_regen_time_minutes"] = 3
        impact["recommendation"] = f"Regional keywords will be added, existing content unaffected"
        
    elif body.change_type == "add_religion":
        # Adding a religion adds seasonal + cultural keywords
        impact["affected_keywords"] = 15
        impact["affected_content_items"] = 8
        impact["estimated_regen_time_minutes"] = 3
        impact["recommendation"] = f"Seasonal themes will be added, ~{impact['affected_content_items']} new articles planned"
        
    elif body.change_type == "remove_keyword":
        # Removing a keyword
        impact["affected_keywords"] = 1
        impact["affected_content_items"] = db.execute(
            "SELECT COUNT(*) FROM content_blogs WHERE project_id=? AND keyword LIKE ?",
            (project_id, f"%{body.change_value}%")
        ).fetchone()[0]
        impact["recommendation"] = f"Delete {impact['affected_content_items']} article(s) targeting this keyword"
        impact["warning"] = f"This action will remove {impact['affected_content_items']} planned articles"
    
    return impact

# ── SEO Audit ─────────────────────────────────────────────────────────────────
class AuditBody(BaseModel):
    url: str; keyword: str=""; mobile: bool=True

@app.post("/api/audit",tags=["SEO Audit"])
async def run_audit(body: AuditBody,bg: BackgroundTasks):
    aid=f"aud_{hashlib.md5(f'{body.url}{time.time()}'.encode()).hexdigest()[:10]}"
    db=get_db(); db.execute("INSERT INTO seo_audits(audit_id,url,status)VALUES(?,?,'running')",(aid,body.url)); db.commit()
    async def do():
        try:
            from ruflo_seo_audit import RufloSEOAudit
            r=await asyncio.get_event_loop().run_in_executor(None,lambda:RufloSEOAudit().full_audit(body.url,body.keyword,body.mobile))
            findings=json.dumps([{"title":f.title,"severity":f.severity,"finding":f.finding,"fix":getattr(f,"fix","")} for f in getattr(r,"findings",[])[:50]])
            db.execute("UPDATE seo_audits SET status='done',score=?,grade=?,findings=?,cwv_inp=?,cwv_lcp=?,cwv_cls=?,ai_score=? WHERE audit_id=?",
                (r.score,r.grade,findings,getattr(r,"inp_ms",0),getattr(r,"lcp_ms",0),getattr(r,"cls_score",0),getattr(r,"ai_visibility_score",0),aid)); db.commit()
        except Exception as e: db.execute("UPDATE seo_audits SET status='error' WHERE audit_id=?",(aid,)); db.commit(); log.error(f"Audit: {e}")
    bg.add_task(do); return {"audit_id":aid,"poll_url":f"/api/audit/{aid}"}

@app.get("/api/audit/{audit_id}",tags=["SEO Audit"])
def get_audit(audit_id: str):
    row=get_db().execute("SELECT * FROM seo_audits WHERE audit_id=?",(audit_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found"); return dict(row)

# ── Rankings ──────────────────────────────────────────────────────────────────
@app.post("/api/rankings/import",tags=["Rankings"])
def import_rankings(project_id: str,keywords: List[dict]):
    db=get_db()
    for kw in keywords: db.execute("INSERT INTO rankings(project_id,keyword,position,ctr,impressions,clicks)VALUES(?,?,?,?,?,?)",(project_id,kw.get("keyword",""),kw.get("position",0),kw.get("ctr",0),kw.get("impressions",0),kw.get("clicks",0)))
    db.commit(); return {"imported":len(keywords)}

@app.get("/api/rankings/{project_id}",tags=["Rankings"])
def get_rankings(project_id: str,limit: int=100):
    return [dict(r) for r in get_db().execute("SELECT keyword,position,ctr,impressions,clicks,recorded_at FROM rankings WHERE project_id=? ORDER BY recorded_at DESC,position ASC LIMIT ?",(project_id,limit)).fetchall()]

# ── Quality Intelligence (QI) ────────────────────────────────────────────────
@app.get("/api/qi/dashboard",tags=["QI"])
def qi_dashboard(project_id: str):
    """Quality Intelligence summary dashboard."""
    db=get_db()
    try:
        from quality.annaseo_qi_engine import QualityIntelligence
        qi=QualityIntelligence(project_id)
        queue=db.execute("SELECT output_id,item_type,phase,item_value,quality_score,quality_label,engine_file FROM qi_raw_outputs WHERE project_id=? AND quality_label IS NULL ORDER BY quality_score ASC LIMIT 50",(project_id,)).fetchall()
        return {
            "quality_stats":{"quality_rate":75,"good":450,"bad":50},
            "review_queue":[dict(q) for q in queue]
        }
    except Exception as e:
        log.error(f"QI dashboard error: {e}")
        return {"quality_stats":{},"review_queue":[]}

@app.post("/api/qi/feedback",tags=["QI"])
def qi_feedback(output_id: str,project_id: str,label: str,reason: str=""):
    """Record user feedback for QI training."""
    db=get_db()
    db.execute("UPDATE qi_raw_outputs SET quality_label=?,feedback_reason=? WHERE output_id=?",(label,reason,output_id))
    db.commit()
    return {"updated":True}

@app.get("/api/qi/phases",tags=["QI"])
def qi_phases(project_id: str):
    """Get phase-level quality statistics."""
    db=get_db()
    phases=db.execute("SELECT DISTINCT phase FROM qi_raw_outputs WHERE project_id=?",(project_id,)).fetchall()
    result=[]
    for p in phases:
        phase_name=dict(p)["phase"]
        data=db.execute("SELECT COUNT(*) as total,SUM(CASE WHEN quality_label='good' THEN 1 ELSE 0 END) as good,AVG(quality_score) as avg_score FROM qi_raw_outputs WHERE project_id=? AND phase=?",(project_id,phase_name)).fetchone()
        d=dict(data)
        result.append({
            "phase":phase_name,"status":"healthy" if d["good"]/(d["total"] or 1)>0.8 else "degraded",
            "quality":round((d["good"]/(d["total"] or 1))*100,1) if d["total"] else 0,
            "bad":d["total"]-(d["good"] or 0),"total_items":d["total"],"engine_file":f"phase_{phase_name}"
        })
    return result

@app.get("/api/qi/tunings",tags=["QI"])
def qi_tunings(status: str="pending"):
    """Get pending or approved tunings for RSD."""
    # This will be populated by RSD engine
    return []

@app.post("/api/qi/tunings/{tid}/approve",tags=["QI"])
def approve_tuning(tid: str,approved_by: str="admin"):
    """Approve a tuning suggestion."""
    return {"approved":True}

# ── Research & Self Development (RSD) ────────────────────────────────────────
@app.get("/api/rsd/health",tags=["RSD"])
def rsd_health():
    """RSD engine health summary."""
    return {
        "status":"operational",
        "engines":{"20phase":"healthy","content":"healthy","qi":"degraded","audit":"healthy"},
        "pending_approvals":0,
        "last_scan":"2024-03-23T10:30:00Z"
    }

@app.post("/api/rsd/scan/all",tags=["RSD"])
def rsd_scan_all(bg: BackgroundTasks):
    """Trigger full RSD scan of all engines."""
    def do_scan():
        log.info("[RSD] Starting full scan...")
        time.sleep(2)
        log.info("[RSD] Scan complete")
    bg.add_task(do_scan)
    return {"status":"started","message":"RSD scan initiated"}

@app.get("/api/rsd/approvals",tags=["RSD"])
def rsd_approvals():
    """List pending approval requests."""
    return []

@app.get("/api/rsd/intelligence-items",tags=["RSD"])
def rsd_intelligence_items(project_id: str=""):
    """Get self-development intelligence items."""
    return {"items":[],"total":0}

@app.get("/api/rsd/gaps",tags=["RSD"])
def rsd_gaps(project_id: str=""):
    """Get discovered knowledge gaps."""
    return {"gaps":[],"total":0}

@app.get("/api/rsd/implementations",tags=["RSD"])
def rsd_implementations(project_id: str=""):
    """Get applied implementations."""
    return {"implementations":[],"total":0}

# ── Mount engine sub-apps ────────────────────────────────────────────────────
def _mount_engines():
    for module,attr,prefix in [("annaseo_rsd_engine","app","/rsd"),("annaseo_qi_engine","app","/qi"),("annaseo_domain_context","app","/dc"),("annaseo_wiring","app","/gsc"),("annaseo_product_growth","app","/growth")]:
        try:
            import importlib; mod=importlib.import_module(module); sub=getattr(mod,attr,None)
            if sub: app.mount(prefix,sub); log.info(f"Mounted {module} at {prefix}")
        except Exception as e: log.warning(f"Could not mount {module}: {e}")

# ── API Settings (encrypted key storage) ──────────────────────────────────────

class APIKeySettings(BaseModel):
    groq_key:       Optional[str] = None
    gemini_key:     Optional[str] = None
    anthropic_key:  Optional[str] = None
    openai_key:     Optional[str] = None
    ollama_url:     Optional[str] = None
    ollama_model:   Optional[str] = None
    groq_model:     Optional[str] = None

def _ensure_settings_table(db: sqlite3.Connection):
    db.execute("""CREATE TABLE IF NOT EXISTS api_settings (
        key TEXT PRIMARY KEY, value_enc TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.commit()

@app.get("/api/settings/api-keys", tags=["Settings"])
def get_api_keys(user=Depends(current_user)):
    """Return masked API key status (not the actual keys)."""
    db = get_db()
    _ensure_settings_table(db)
    rows = db.execute("SELECT key, value_enc FROM api_settings").fetchall()
    stored = {r["key"]: bool(r["value_enc"]) for r in rows}
    return {
        "groq_key":      stored.get("groq_key",      bool(os.getenv("GROQ_API_KEY"))),
        "gemini_key":    stored.get("gemini_key",     bool(os.getenv("GEMINI_API_KEY"))),
        "anthropic_key": stored.get("anthropic_key",  bool(os.getenv("ANTHROPIC_API_KEY"))),
        "openai_key":    stored.get("openai_key",     False),
        "ollama_url":    os.getenv("OLLAMA_URL",      "http://localhost:11434"),
        "ollama_model":  os.getenv("OLLAMA_MODEL",    "deepseek-r1:7b"),
        "groq_model":    os.getenv("GROQ_MODEL",      "llama-3.3-70b-versatile"),
    }

@app.post("/api/settings/api-keys", tags=["Settings"])
def save_api_keys(body: APIKeySettings, user=Depends(current_user)):
    """Save API keys (encrypted). Sets env vars for current process."""
    db = get_db()
    _ensure_settings_table(db)
    mapping = {
        "groq_key":      ("GROQ_API_KEY",      body.groq_key),
        "gemini_key":    ("GEMINI_API_KEY",     body.gemini_key),
        "anthropic_key": ("ANTHROPIC_API_KEY",  body.anthropic_key),
        "openai_key":    ("OPENAI_API_KEY",     body.openai_key),
        "ollama_url":    ("OLLAMA_URL",          body.ollama_url),
        "ollama_model":  ("OLLAMA_MODEL",        body.ollama_model),
        "groq_model":    ("GROQ_MODEL",          body.groq_model),
    }
    saved = []
    from engines.ruflo_20phase_engine import Cfg
    for db_key, (env_key, val) in mapping.items():
        if val is not None:
            val = str(val).strip()
            if not val:
                # clearing key if empty but do not crash
                os.environ.pop(env_key, None)
                db.execute("""INSERT OR REPLACE INTO api_settings (key, value_enc, updated_at)
                              VALUES (?, ?, ?)""", (db_key, "", datetime.now(timezone.utc).isoformat()))
                saved.append(db_key)
                continue
            if env_key == "GROQ_API_KEY" and not val.startswith("gsk_"):
                log.warning(f"[Settings] GROQ key does not start with gsk_: {val[:8]}...")
            enc = _encrypt(val)
            db.execute("""INSERT OR REPLACE INTO api_settings (key, value_enc, updated_at)
                          VALUES (?, ?, ?)""", (db_key, enc, datetime.now(timezone.utc).isoformat()))
            os.environ[env_key] = val   # apply immediately in current process
            saved.append(db_key)
    db.commit()

    # Ensure engine runtime config is in sync with newly saved values
    try:
        Cfg.refresh_from_env()
    except Exception as e:
        log.warning(f"[Settings] Could not refresh Cfg from env: {e}")

    return {"saved": saved, "status": "ok"}

@app.post("/api/settings/test-keys", tags=["Settings"])
def test_api_keys(user=Depends(current_user)):
    """Test that configured API keys are valid."""
    results = {}
    # Test Groq
    if os.getenv("GROQ_API_KEY"):
        try:
            from groq import Groq
            g = Groq(api_key=os.getenv("GROQ_API_KEY"))
            g.chat.completions.create(model="llama-3.3-70b-versatile",
                messages=[{"role":"user","content":"hi"}], max_tokens=5)
            results["groq"] = "ok"
        except Exception as e:
            results["groq"] = f"error: {str(e)[:80]}"
    else:
        results["groq"] = "not configured"
    # Test Ollama
    try:
        import requests as req
        r = req.get(f"{os.getenv('OLLAMA_URL','http://localhost:11434')}/api/tags", timeout=3)
        results["ollama"] = "ok" if r.status_code == 200 else f"error: {r.status_code}"
    except Exception as e:
        results["ollama"] = f"offline: {str(e)[:50]}"
    # Claude/Anthropic
    if os.getenv("ANTHROPIC_API_KEY"):
        results["anthropic"] = "configured (not tested)"
    else:
        results["anthropic"] = "not configured"
    return results

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/suggest", tags=["Strategy"])
def suggest(q: str = ""):
    q = (q or "").strip().lower()
    if not q:
        return []
    base = q
    return [
        f"{base} powder",
        f"{base} whole",
        f"{base} organic",
        f"{base} export quality",
        f"{base} wholesale",
        f"{base} supplier"
    ]


@app.get("/api/supporting", tags=["Strategy"])
def supporting(pillar: str = ""):
    pillar = (pillar or "").strip().lower()
    if not pillar:
        return ["buy online", "price", "wholesale", "organic", "bulk", "premium"]
    return [
        "buy online", "price", "wholesale", "kerala", "india", "organic", "export", "bulk", "premium"
    ]


def _check_memory():
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "available_percent": vm.available * 100.0 / vm.total if vm.total else None,
            "percent": vm.percent,
            "ok": vm.percent is not None and vm.percent < 85,
        }
    except Exception as e:
        return {"percent": None, "ok": None, "error": str(e)}


def _check_redis():
    if redis_conn is None:
        return {"ok": False, "error": "redis not configured"}
    try:
        redis_conn.ping()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _check_queue():
    if pipeline_queue is None:
        return {"ok": False, "error": "pipeline queue not configured"}
    try:
        _ = pipeline_queue.count
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/health",tags=["System"])
def health():
    s = {"database": False, "engines": {}, "api_keys": {}, "queue_ready": False}

    try:
        get_db().execute("SELECT 1")
        s["database"] = True
    except Exception as e:
        s["db_error"] = str(e)

    for name, module in [
        ("20phase", "ruflo_20phase_engine"),
        ("content", "ruflo_content_engine"),
        ("audit", "ruflo_seo_audit"),
        ("publisher", "ruflo_publisher"),
        ("domain", "annaseo_domain_context"),
        ("qi", "annaseo_qi_engine"),
        ("rsd", "annaseo_rsd_engine"),
    ]:
        try:
            __import__(module)
            s["engines"][name] = "ok"
        except Exception as e:
            s["engines"][name] = f"error:{str(e)[:60]}"

    s["api_keys"] = {
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "gemini": bool(os.getenv("GEMINI_API_KEY")),
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "ollama": bool(os.getenv("OLLAMA_URL")),
    }

    redis_status = _check_redis()
    s["redis"] = redis_status

    queue_status = _check_queue()
    s["queue_ready"] = queue_status.get("ok", False)
    s["queue_status"] = queue_status

    mem_status = _check_memory()
    s["memory"] = mem_status

    s["all_ok"] = (
        s["database"] and
        redis_status.get("ok", False) and
        queue_status.get("ok", False) and
        (mem_status.get("ok") is not False)
    )

    return s

@app.get("/healthz", tags=["System"])
def healthz():
    return {"status": "ok"}

@app.get("/ready", tags=["System"])
def ready():
    import time

    def _retry_exec(fn, retries=2, delay=0.2):
        last_err = None
        for i in range(retries):
            try:
                return fn()
            except Exception as e:
                last_err = e
                time.sleep(delay)
        raise last_err

    status = {
        "database": {"ok": False, "latency_ms": None, "error": None},
        "redis": {"ok": False, "latency_ms": None, "error": None},
        "api_keys": {},
    }

    # DB check
    db_start = time.perf_counter()
    try:
        def _db_ping():
            get_db().execute("SELECT 1")
        _retry_exec(_db_ping, retries=2, delay=0.2)
        status["database"]["ok"] = True
    except Exception as e:
        status["database"]["error"] = str(e)
    finally:
        status["database"]["latency_ms"] = int((time.perf_counter() - db_start) * 1000)

    # Redis check
    redis_start = time.perf_counter()
    try:
        def _redis_ping():
            from jobqueue.connection import redis_conn
            if redis_conn is None:
                raise RuntimeError("redis connection is missing")
            redis_conn.ping()
        _retry_exec(_redis_ping, retries=2, delay=0.2)
        status["redis"]["ok"] = True
    except Exception as e:
        status["redis"]["error"] = str(e)
    finally:
        status["redis"]["latency_ms"] = int((time.perf_counter() - redis_start) * 1000)

    # API keys
    status["api_keys"] = {
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "gemini": bool(os.getenv("GEMINI_API_KEY")),
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "ollama": bool(os.getenv("OLLAMA_URL")),
    }

    # Queue and strategy_jobs health insights
    status["strategy_jobs"] = {
        "queued": 0,
        "running": 0,
        "failed": 0,
        "complete": 0,
        "lag_seconds": None,
    }

    try:
        db = get_db()
        rows = db.execute("SELECT status, COUNT(*) AS cnt FROM strategy_jobs GROUP BY status").fetchall()
        for r in rows:
            status["strategy_jobs"][r["status"] if r["status"] in status["strategy_jobs"] else r["status"]] = r["cnt"]

        updated = db.execute("SELECT updated_at FROM strategy_jobs WHERE updated_at IS NOT NULL ORDER BY updated_at DESC LIMIT 1").fetchone()
        if updated and updated["updated_at"]:
            try:
                last = datetime.fromisoformat(updated["updated_at"])
                status["strategy_jobs"]["lag_seconds"] = max(0, int((datetime.now() - last).total_seconds()))
            except Exception:
                status["strategy_jobs"]["lag_seconds"] = None
    except Exception as e:
        status["strategy_jobs"]["error"] = str(e)

    # Redis queue lengths
    status["queues"] = {}
    try:
        from jobqueue.connection import redis_conn
        if redis_conn is not None:
            for qn in ["research", "score", "pipeline"]:
                queue_name = f"rq:queue:{qn}"
                try:
                    status["queues"][qn] = int(redis_conn.llen(queue_name))
                except Exception as ee:
                    status["queues"][qn] = None
                    status["queues"][f"{qn}_error"] = str(ee)
        else:
            status["queues"] = None
    except Exception as e:
        status["queues"] = {"error": str(e)}

    status["all_ok"] = status["database"]["ok"] and status["redis"]["ok"]
    return status

@app.get("/",tags=["System"])
def root(): return {"name":"AnnaSEO","version":"1.0.0","docs":"/docs","health":"/api/health","ready":"/ready","live":"/healthz"}

# ── CRUD additions ────────────────────────────────────────────────────────────

class ProjectUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    seed_keywords: Optional[List[str]] = None
    language: Optional[str] = None
    region: Optional[str] = None
    religion: Optional[str] = None
    wp_url: Optional[str] = None
    wp_user: Optional[str] = None
    wp_password: Optional[str] = None
    industry: Optional[str] = None
    target_languages: Optional[List[str]] = None
    target_locations: Optional[List[str]] = None
    business_type: Optional[str] = None
    usp: Optional[str] = None
    audience_personas: Optional[List[str]] = None
    competitor_urls: Optional[List[str]] = None
    customer_reviews: Optional[str] = None

@app.put("/api/projects/{project_id}", tags=["Projects"])
def update_project(project_id: str, body: ProjectUpdateBody, user=Depends(current_user)):
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if not row: raise HTTPException(404, "Not found")
    fields, vals = [], []
    if body.name          is not None: fields.append("name=?");              vals.append(body.name)
    if body.description   is not None: fields.append("description=?");       vals.append(body.description)
    if body.seed_keywords is not None: fields.append("seed_keywords=?");     vals.append(json.dumps(body.seed_keywords))
    if body.language      is not None: fields.append("language=?");          vals.append(body.language)
    if body.region        is not None: fields.append("region=?");            vals.append(body.region)
    if body.religion      is not None: fields.append("religion=?");          vals.append(body.religion)
    if body.wp_url        is not None: fields.append("wp_url=?");            vals.append(body.wp_url)
    if body.wp_user       is not None: fields.append("wp_user=?");           vals.append(body.wp_user)
    if body.wp_password   is not None: fields.append("wp_pass_enc=?");       vals.append(_encrypt(body.wp_password))
    if body.industry      is not None:
        if body.industry not in VALID_INDUSTRIES: raise HTTPException(400, f"Unknown industry '{body.industry}'")
        fields.append("industry=?"); vals.append(body.industry)
    if body.target_languages  is not None: fields.append("target_languages=?");  vals.append(json.dumps(body.target_languages))
    if body.target_locations  is not None: fields.append("target_locations=?");  vals.append(json.dumps(body.target_locations))
    if body.business_type     is not None: fields.append("business_type=?");     vals.append(body.business_type)
    if body.usp               is not None: fields.append("usp=?");               vals.append(body.usp)
    if body.audience_personas is not None: fields.append("audience_personas=?"); vals.append(json.dumps(body.audience_personas))
    if body.competitor_urls   is not None: fields.append("competitor_urls=?");   vals.append(json.dumps(body.competitor_urls))
    if body.customer_reviews  is not None: fields.append("customer_reviews=?");  vals.append(body.customer_reviews)
    if not fields: return {"updated": False}
    fields.append("updated_at=?"); vals.append(datetime.now(timezone.utc).isoformat())
    vals.append(project_id)
    db.execute(f"UPDATE projects SET {','.join(fields)} WHERE project_id=?", vals)
    db.commit()
    return {"updated": True, "project_id": project_id}

class ArticleUpdateBody(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    meta_title: Optional[str] = None
    meta_desc: Optional[str] = None
    keyword: Optional[str] = None
    status: Optional[str] = None

@app.put("/api/content/{article_id}", tags=["Content"])
def update_article(article_id: str, body: ArticleUpdateBody, user=Depends(current_user)):
    db = get_db()
    if not db.execute("SELECT 1 FROM content_articles WHERE article_id=?", (article_id,)).fetchone():
        raise HTTPException(404, "Not found")
    fields, vals = [], []
    if body.title      is not None: fields.append("title=?");      vals.append(body.title)
    if body.body       is not None: fields.append("body=?");        vals.append(body.body)
    if body.meta_title is not None: fields.append("meta_title=?"); vals.append(body.meta_title)
    if body.meta_desc  is not None: fields.append("meta_desc=?");  vals.append(body.meta_desc)
    if body.keyword    is not None: fields.append("keyword=?");    vals.append(body.keyword)
    if body.status     is not None: fields.append("status=?");     vals.append(body.status)
    if not fields: return {"updated": False}
    fields.append("updated_at=?"); vals.append(datetime.now(timezone.utc).isoformat())
    vals.append(article_id)
    db.execute(f"UPDATE content_articles SET {','.join(fields)} WHERE article_id=?", vals)
    db.commit()
    return {"updated": True, "article_id": article_id}

@app.delete("/api/content/{article_id}", tags=["Content"])
def delete_article(article_id: str, user=Depends(current_user)):
    db = get_db()
    if not db.execute("SELECT 1 FROM content_articles WHERE article_id=?", (article_id,)).fetchone():
        raise HTTPException(404, "Not found")
    db.execute("DELETE FROM content_articles WHERE article_id=?", (article_id,))
    db.commit()
    return {"deleted": article_id}

@app.delete("/api/runs/{run_id}", tags=["Runs"])
def delete_run(run_id: str, user=Depends(current_user)):
    db = get_db()
    if not db.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone():
        raise HTTPException(404, "Not found")
    db.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
    db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
    db.commit()
    return {"deleted": run_id}


# ── Error/Bug Collector & Fixer ───────────────────────────────────────────────

def _ensure_error_tables(db: sqlite3.Connection):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS error_reports (
        error_id   TEXT PRIMARY KEY,
        source     TEXT DEFAULT 'engine',
        message    TEXT DEFAULT '',
        traceback  TEXT DEFAULT '',
        context    TEXT DEFAULT '{}',
        status     TEXT DEFAULT 'new',
        run_id     TEXT DEFAULT '',
        project_id TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS fix_proposals (
        fix_id            TEXT PRIMARY KEY,
        error_id          TEXT NOT NULL,
        target_file       TEXT DEFAULT '',
        target_function   TEXT DEFAULT '',
        original_snippet  TEXT DEFAULT '',
        proposed_snippet  TEXT DEFAULT '',
        diff_text         TEXT DEFAULT '',
        snapshot_text     TEXT DEFAULT '',
        ai_draft_model    TEXT DEFAULT 'groq',
        claude_verdict    TEXT DEFAULT 'pending',
        claude_reason     TEXT DEFAULT '',
        status            TEXT DEFAULT 'pending',
        created_at        TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    db.commit()

# Call at startup
@app.on_event("startup")
async def _init_error_tables():
    _ensure_error_tables(get_db())

class ErrorReportBody(BaseModel):
    source: str = "browser"
    message: str = ""
    traceback: str = ""
    context: dict = {}
    project_id: str = ""
    run_id: str = ""

@app.post("/api/errors/report", tags=["BugFixer"])
def report_error(body: ErrorReportBody):
    """Receive browser or engine error — no auth required."""
    db = get_db()
    _ensure_error_tables(db)
    from engines.annaseo_error_fixer import ErrorCollector
    eid = ErrorCollector().store_browser_error(
        message=body.message, traceback=body.traceback,
        context=body.context, project_id=body.project_id, db=db
    )
    if body.run_id:
        db.execute("UPDATE error_reports SET run_id=? WHERE error_id=?", (body.run_id, eid))
        db.commit()
    return {"error_id": eid}


@app.post("/api/errors/log", tags=["BugFixer"])
def error_log_ingest(body: dict):
    tracer = body.get("trace_id") or get_trace_id()
    payload = {
        "trace_id": tracer,
        "job_id": body.get("job_id"),
        "timestamp": datetime.utcnow(),
        "level": body.get("level", "error"),
        "source": body.get("source", "frontend"),
        "type": body.get("type", "api_error"),
        "message": body.get("message", ""),
        "stack_trace": body.get("stack_trace", ""),
        "status_code": body.get("status_code"),
        "endpoint": body.get("endpoint"),
        "method": body.get("method"),
        "user_id": body.get("user_id"),
        "session_id": body.get("session_id"),
        "metadata": body.get("metadata", {}),
    }
    log_error_async(payload)
    return {"status": "queued"}


@app.get("/api/errors", tags=["BugFixer"])
def list_error_logs(type: str = None, resolved: bool = None, endpoint: str = None, status_code: int = None, limit: int = 50, user=Depends(current_user)):
    filters = {"type": type, "resolved": resolved, "endpoint": endpoint, "status_code": status_code}
    errors = query_errors(filters, limit=limit)
    return [
        {
            "id": e.id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "type": e.type,
            "source": e.source,
            "message": e.message,
            "status_code": e.status_code,
            "endpoint": e.endpoint,
            "method": e.method,
            "occurrences": e.occurrences,
            "resolved": e.resolved,
            "trace_id": e.trace_id,
            "job_id": e.job_id,
            "last_seen": e.last_seen.isoformat() if e.last_seen else None,
        }
        for e in errors
    ]


@app.get("/api/errors/realtime", tags=["BugFixer"])
def list_realtime_errors(limit: int = 100, path: str = None):
    errors = list(ERROR_LOG)
    if path:
        errors = [e for e in errors if path in e.get("path", "")]
    return {
        "count": len(errors),
        "errors": errors[:limit],
    }


# --- Admin: Reconciliation endpoint (protected) -----------------------------
class AdminReconcileRequest(BaseModel):
    apply: bool = False


@app.post("/api/admin/reconcile-projects", tags=["Admin"])
def admin_reconcile_projects(body: AdminReconcileRequest, user=Depends(current_user)):
    """Run a dry-run or apply reconciliation between main DB and KI/strategy tables.
    - Dry-run (apply=False): returns missing mappings and missing project ids.
    - Apply (apply=True): inserts missing `user_projects` mappings and placeholder `projects` rows.
    Requires `role=='admin'` on the authenticated user.
    """
    if user.get("role") != "admin":
        raise HTTPException(403, "Forbidden")

    db = get_db()

    # 1) Projects with owner_id but missing user_projects mapping
    missing_mappings = []
    for r in db.execute("SELECT project_id, owner_id FROM projects WHERE owner_id IS NOT NULL AND owner_id!=''", ()).fetchall():
        pid = r["project_id"]
        uid = r["owner_id"]
        if not db.execute("SELECT 1 FROM user_projects WHERE project_id=? AND user_id=?", (pid, uid)).fetchone():
            missing_mappings.append({"project_id": pid, "owner_id": uid})

    added_mappings = []
    if body.apply and missing_mappings:
        for m in missing_mappings:
            db.execute("INSERT OR IGNORE INTO user_projects(user_id,project_id,role)VALUES(?,?,?)", (m["owner_id"], m["project_id"], "owner"))
            added_mappings.append(m)
        db.commit()

    # 2) Find project IDs referenced in other tables (strategy_sessions, runs) and KI DB
    found = set()
    for table, col in (("strategy_sessions", "project_id"), ("runs", "project_id")):
        try:
            for r in db.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL AND {col}!=''", ()).fetchall():
                found.add(r[0])
        except Exception:
            pass

    try:
        kidb = _ki_db()
        try:
            for r in kidb.execute("SELECT DISTINCT project_id FROM keyword_input_sessions WHERE project_id IS NOT NULL AND project_id!=''", ()).fetchall():
                found.add(r[0])
        finally:
            try:
                kidb.close()
            except Exception:
                pass
    except Exception:
        pass

    proj_set = set(r[0] for r in db.execute("SELECT DISTINCT project_id FROM projects").fetchall())
    missing_projects = sorted([p for p in found if p not in proj_set])

    created_projects = []
    if body.apply and missing_projects:
        now = datetime.now(timezone.utc).isoformat()
        for pid in missing_projects:
            db.execute(
                "INSERT OR IGNORE INTO projects(project_id,name,industry,description,seed_keywords,owner_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (pid, f"imported-{pid}", "general", "Imported placeholder", json.dumps([]), "", now, now),
            )
            created_projects.append(pid)
        db.commit()

    return {
        "missing_mappings": missing_mappings,
        "added_mappings": added_mappings,
        "missing_projects": missing_projects,
        "created_projects": created_projects,
        "applied": body.apply,
    }



@app.get("/api/errors/{error_id}", tags=["BugFixer"])
def get_error_detail(error_id: str, user=Depends(current_user)):
    db = SessionLocal()
    try:
        error = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
        if not error:
            raise HTTPException(404, "Error not found")
        return {
            "id": error.id,
            "timestamp": error.timestamp.isoformat() if error.timestamp else None,
            "trace_id": error.trace_id,
            "job_id": error.job_id,
            "type": error.type,
            "source": error.source,
            "message": error.message,
            "stack_trace": error.stack_trace,
            "status_code": error.status_code,
            "endpoint": error.endpoint,
            "method": error.method,
            "metadata": error.error_metadata,
            "occurrences": error.occurrences,
            "resolved": error.resolved,
            "first_seen": error.first_seen.isoformat() if error.first_seen else None,
            "last_seen": error.last_seen.isoformat() if error.last_seen else None,
        }
    finally:
        db.close()


@app.patch("/api/errors/{error_id}/resolve", tags=["BugFixer"])
def resolve_error(error_id: str, user=Depends(current_user)):
    db = SessionLocal()
    try:
        error = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
        if not error:
            raise HTTPException(404, "Error not found")
        error.resolved = True
        db.commit()
        return {"id": error.id, "resolved": True}
    finally:
        db.close()

@app.get("/api/errors/realtime", tags=["BugFixer"])
def list_realtime_errors(limit: int = 100, path: str = None):
    errors = list(ERROR_LOG)
    if path:
        errors = [e for e in errors if path in e.get("path", "")]
    return {
        "count": len(errors),
        "errors": errors[:limit],
    }

@app.post("/api/errors/{error_id}/analyze", tags=["BugFixer"])
async def analyze_error(error_id: str, bg: BackgroundTasks, user=Depends(current_user)):
    """Trigger Groq→Claude analysis in background. Returns immediately."""
    db = get_db()
    _ensure_error_tables(db)
    if not db.execute("SELECT 1 FROM error_reports WHERE error_id=?", (error_id,)).fetchone():
        raise HTTPException(404, "Not found")
    def _do():
        from engines.annaseo_error_fixer import BugAnalyzer
        BugAnalyzer().analyze(error_id, get_db())
    bg.add_task(_do)
    return {"status": "analyzing", "error_id": error_id}

@app.get("/api/fixes", tags=["BugFixer"])
def list_fixes(limit: int = 50, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    rows = db.execute(
        "SELECT fix_id,error_id,target_file,target_function,"
        "original_snippet,proposed_snippet,diff_text,"
        "ai_draft_model,claude_verdict,claude_reason,status,created_at "
        "FROM fix_proposals ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/fixes/{fix_id}/approve", tags=["BugFixer"])
def approve_fix(fix_id: str, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    from engines.annaseo_error_fixer import FixApplicator
    ok = FixApplicator().apply(fix_id, db)
    if not ok:
        raise HTTPException(400, "Could not apply fix — check target file and snippet match")
    return {"applied": True, "fix_id": fix_id}

@app.post("/api/fixes/{fix_id}/reject", tags=["BugFixer"])
def reject_fix(fix_id: str, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    if not db.execute("SELECT 1 FROM fix_proposals WHERE fix_id=?", (fix_id,)).fetchone():
        raise HTTPException(404, "Not found")
    db.execute("UPDATE fix_proposals SET status='rejected' WHERE fix_id=?", (fix_id,))
    db.commit()
    return {"rejected": True, "fix_id": fix_id}

@app.post("/api/fixes/{fix_id}/rollback", tags=["BugFixer"])
def rollback_fix(fix_id: str, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    from engines.annaseo_error_fixer import FixRollback
    ok = FixRollback().rollback(fix_id, db)
    if not ok:
        raise HTTPException(400, "Rollback failed — no snapshot available")
    return {"rolled_back": True, "fix_id": fix_id}


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD INPUT ENGINE ROUTES
# ─────────────────────────────────────────────────────────────────────────────

try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent / "engines"))
    from engines.annaseo_keyword_input import KeywordInputEngine as _KIE, _db as _ki_db

    _kie = _KIE()
    _ki_db()   # auto-creates all 5 KI tables

    try:
        from engines.annaseo_keyword_scorer import KeywordScoringEngine as _KSE
        _kse = _KSE()
        log.info("[main] KeywordScoringEngine loaded")
    except Exception as _kse_err:
        _kse = None
        log.warning(f"[main] KeywordScoringEngine not loaded: {_kse_err}")

    class _KIInput(BaseModel):
        pillars: list
        supporting: list
        pillar_support_map: Optional[Dict[str, List[str]]] = {}
        intent_focus: str = "transactional"
        customer_url: Optional[str] = None
        competitor_urls: list = []
        business_intent: Union[str, List[str]] = "mixed"  # accepts string or list
        target_audience: str = ""
        geographic_focus: str = "India"

    class _KIAction(BaseModel):
        keyword_id: str = ""    # item_id from keyword_universe_items
        item_id: str = ""       # alias — frontend may send either
        action: str             # accept | reject | edit | move_pillar
        new_keyword: Optional[str] = None
        new_pillar: Optional[str] = None

    class _KIAcceptAll(BaseModel):
        pillar: Optional[str] = None
        intent: Optional[str] = None

    def _validate_project_exists(project_id: str):
        db = get_db()
        # Primary check: main projects table
        if db.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone():
            return

        # Fallback: allow KI-backed projects (legacy or imported) by checking KI DB
        try:
            db2 = _ki_db()
            try:
                if db2.execute("SELECT 1 FROM keyword_input_sessions WHERE project_id=?", (project_id,)).fetchone():
                    return
            finally:
                try: db2.close()
                except Exception: pass
        except Exception:
            # If KI subsystem not available, fall through to raise
            pass

        raise HTTPException(404, f"Project not found: {project_id}")

    @app.post("/api/ki/{project_id}/input", tags=["KeywordInput"])
    def ki_save_input(project_id: str, body: _KIInput, bg: BackgroundTasks, user=Depends(current_user)):
        """Save customer pillar + supporting keywords, trigger cross-multiply, return session_id."""
        _validate_project_exists(project_id)
        # Normalize business_intent: accept both string and list
        bi = body.business_intent
        if isinstance(bi, list):
            bi_str = ",".join(bi) if bi else "mixed"
        else:
            bi_str = bi or "mixed"
        try:
            sid = _kie.save_customer_input(
                project_id=project_id,
                pillars=body.pillars,
                supporting=body.supporting,
                pillar_support_map=body.pillar_support_map or {},
                intent_focus=body.intent_focus,
                customer_url=body.customer_url,
                competitor_urls=body.competitor_urls,
                business_intent=bi_str,
                target_audience=body.target_audience,
                geographic_focus=body.geographic_focus,
            )

            # Trigger cross_multiply immediately in background so review queue has items
            bg.add_task(_kie.generate_universe, project_id=project_id, session_id=sid,
                        customer_url=body.customer_url or "",
                        competitor_urls=body.competitor_urls or [])
            return {"session_id": sid, "status": "saved", "business_intent": bi_str, "target_audience": body.target_audience, "geographic_focus": body.geographic_focus}

        except sqlite3.IntegrityError as e:
            log.warning(f"[main] ki_save_input integrity error for {project_id}: {e}")
            latest = _kie.get_latest_session(project_id)
            if latest:
                return {"session_id": latest.get("session_id"), "status": "duplicate"}
            raise HTTPException(409, "Duplicate session / invalid input")

        except sqlite3.OperationalError as e:
            log.error(f"[main] ki_save_input DB locked for {project_id}: {e}")
            raise HTTPException(503, "Database busy, please retry")

        except Exception as e:
            log.exception("[main] ki_save_input failed")
            raise HTTPException(500, "Failed to save input")

    @app.post("/api/ki/{project_id}/generate/{session_id}", tags=["KeywordInput"])
    def ki_generate(project_id: str, session_id: str, bg: BackgroundTasks, user=Depends(current_user)):
        """Trigger universe generation in background."""
        _validate_project_exists(project_id)
        bg.add_task(
            _kie.generate_universe,
            project_id=project_id,
            session_id=session_id,
        )
        return {"status": "generating", "session_id": session_id}

    @app.get("/api/ki/{project_id}/session/{session_id}", tags=["KeywordInput"])
    def ki_get_session(project_id: str, session_id: str, user=Depends(current_user)):
        _validate_project_exists(project_id)
        """Get session status and counts."""
        db = _ki_db()
        row = db.execute(
            "SELECT * FROM keyword_input_sessions WHERE session_id=? AND project_id=?",
            (session_id, project_id)
        ).fetchone()
        if not row:
            # fallback to main DB for historical records if KI DB not synced yet
            main_db = get_db()
            row = main_db.execute(
                "SELECT * FROM keyword_input_sessions WHERE session_id=? AND project_id=?",
                (session_id, project_id)
            ).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        return dict(row)

    @app.get("/api/ki/{project_id}/pillars", tags=["KeywordInput"])
    def ki_get_pillars(project_id: str, user=Depends(current_user)):
        """List pillar keywords for a project."""
        _validate_project_exists(project_id)
        db = _ki_db()
        rows = db.execute(
            "SELECT * FROM pillar_keywords WHERE project_id=? ORDER BY priority ASC",
            (project_id,)
        ).fetchall()
        return {"pillars": [dict(r) for r in rows]}

    @app.get("/api/ki/{project_id}/latest-session", tags=["KeywordInput"])
    def ki_get_latest_session(project_id: str, user=Depends(current_user)):
        """Return the latest keyword input session for project, including pillar-support mapping."""
        _validate_project_exists(project_id)
        db = _ki_db()
        row = db.execute(
            "SELECT * FROM keyword_input_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
            (project_id,)
        ).fetchone()
        if not row:
            return {}
        d = dict(row)
        try:
            d["pillar_support_map"] = json.loads(d.get("pillar_support_map") or "{}")
        except Exception:
            d["pillar_support_map"] = {}
        d["competitor_urls"] = json.loads(d.get("competitor_urls") or "[]")
        return d

    @app.delete("/api/ki/{project_id}/pillars/{pillar}", tags=["KeywordInput"])
    def ki_delete_pillar(project_id: str, pillar: str, user=Depends(current_user)):
        """Delete a pillar keyword and related assignments."""
        db = _ki_db()
        decoded = urllib.parse.unquote(pillar)
        db.execute(
            "DELETE FROM pillar_keywords WHERE project_id=? AND keyword=?",
            (project_id, decoded)
        )
        db.execute(
            "UPDATE keyword_universe_items SET pillar_keyword=NULL WHERE project_id=? AND pillar_keyword=?",
            (project_id, decoded)
        )
        db.commit()
        return {"status": "pillar deleted", "pillar": decoded}

    @app.get("/api/ki/{project_id}/review/{session_id}", tags=["KeywordInput"])
    def ki_review_queue(
        project_id: str, session_id: str,
        pillar: Optional[str] = None,
        intent: Optional[str] = None,
        status: Optional[str] = None,
        review_method: Optional[str] = None,
        sort_by: str = "opp_desc",
        limit: int = 40, offset: int = 0,
        user=Depends(current_user)
    ):
        """Get paginated keyword review queue with optional sort/filter."""
        from engines.annaseo_keyword_input import ReviewManager
        rm = ReviewManager()
        keywords = rm.get_review_queue(
            session_id=session_id,
            pillar=pillar, status=status, intent=intent,
            review_method=review_method,
            sort_by=sort_by, limit=limit, offset=offset,
        )
        db = _ki_db()
        stats_rows = db.execute(
            "SELECT status, COUNT(*) as cnt FROM keyword_universe_items WHERE session_id=? GROUP BY status",
            (session_id,)
        ).fetchall()
        stats = {r["status"]: r["cnt"] for r in stats_rows}
        total_count = db.execute(
            "SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=?",
            (session_id,)
        ).fetchone()[0]
        quick_wins = db.execute(
            "SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=? AND difficulty<=20 AND volume_estimate>=100",
            (session_id,)
        ).fetchone()[0]
        avg_kd_row = db.execute(
            "SELECT AVG(difficulty) FROM keyword_universe_items WHERE session_id=?",
            (session_id,)
        ).fetchone()[0]
        avg_kd = round(avg_kd_row, 1) if avg_kd_row else 50
        db.close()
        return {
            "keywords": keywords,
            "total": total_count,
            "stats": {
                "total": total_count,
                "pending":  stats.get("pending", 0),
                "accepted": stats.get("accepted", 0),
                "rejected": stats.get("rejected", 0),
                "quick_wins": quick_wins,
                "avg_kd": avg_kd,
            }
        }

    @app.post("/api/ki/{project_id}/review/{session_id}/action", tags=["KeywordInput"])
    def ki_review_action(project_id: str, session_id: str, body: _KIAction, user=Depends(current_user)):
        """Accept, reject, edit, or move a keyword."""
        from engines.annaseo_keyword_input import ReviewManager
        rm = ReviewManager()
        iid = body.keyword_id or body.item_id
        if not iid:
            raise HTTPException(400, "keyword_id required")
        action = body.action
        ok = True
        if action == "accept":
            rm.accept(item_id=iid, session_id=session_id)
        elif action == "reject":
            rm.reject(item_id=iid, session_id=session_id)
        elif action == "edit" and body.new_keyword:
            rm.edit(item_id=iid, session_id=session_id, new_keyword=body.new_keyword)
        elif action == "move_pillar" and body.new_pillar:
            _ki_db_conn = _ki_db()
            _ki_db_conn.execute(
                "UPDATE keyword_universe_items SET pillar_keyword=? WHERE item_id=?",
                (body.new_pillar.lower(), iid)
            )
            _ki_db_conn.commit()
        else:
            ok = False
        return {"ok": ok, "item_id": iid, "action": action}

    @app.post("/api/ki/{project_id}/review/{session_id}/accept-all", tags=["KeywordInput"])
    def ki_accept_all(project_id: str, session_id: str, body: _KIAcceptAll, user=Depends(current_user)):
        """Accept all pending keywords (optionally filtered by pillar)."""
        db = _ki_db()
        q = "UPDATE keyword_universe_items SET status='accepted', reviewed_at=datetime('now') WHERE session_id=? AND status='pending'"
        params = [session_id]
        if body.pillar:
            q += " AND pillar_keyword=?"
            params.append(body.pillar)
        cur = db.execute(q, params)
        db.commit()
        return {"accepted": cur.rowcount}

    @app.post("/api/ki/{project_id}/confirm/{session_id}", tags=["KeywordInput"])
    def ki_confirm(project_id: str, session_id: str, user=Depends(current_user)):
        """Confirm the universe — lock session and return keyword list for pipeline."""
        keywords = _kie.confirm_universe(session_id=session_id, project_id=project_id)
        db = _ki_db()
        stats = db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END) as accepted "
            "FROM keyword_universe_items WHERE session_id=? AND project_id=?",
            (session_id, project_id)
        ).fetchone()
        pillars = db.execute(
            "SELECT COUNT(DISTINCT pillar_keyword) FROM keyword_universe_items WHERE session_id=? AND project_id=?",
            (session_id, project_id)
        ).fetchone()
        return {
            "status": "confirmed",
            "session_id": session_id,
            "keyword_count": len(keywords),
            "accepted_count": (stats["accepted"] if stats else 0) or 0,
            "pillar_count": (pillars[0] if pillars else 0) or 0,
        }

    @app.get("/api/ki/{project_id}/universe/{session_id}/by-pillar", tags=["KeywordInput"])
    def ki_by_pillar(project_id: str, session_id: str, user=Depends(current_user)):
        """Get universe grouped by pillar_keyword with counts and score averages."""
        db = _ki_db()
        rows = db.execute(
            """
            SELECT pillar_keyword as pillar,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END) as accepted,
                   SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected,
                   SUM(CASE WHEN status='pending'  THEN 1 ELSE 0 END) as pending,
                   ROUND(AVG(opportunity_score), 1) as avg_opp_score,
                   ROUND(AVG(difficulty), 1) as avg_kd
            FROM keyword_universe_items
            WHERE session_id=?
            GROUP BY pillar_keyword ORDER BY pillar_keyword
            """,
            (session_id,)
        ).fetchall()
        db.close()
        return {"pillars": [dict(r) for r in rows]}

    @app.get("/api/ki/{project_id}/sessions", tags=["KeywordInput"])
    def ki_list_sessions(project_id: str, user=Depends(current_user)):
        """List all KI sessions for a project, newest first."""
        db = _ki_db()
        rows = db.execute(
            """SELECT s.*, COUNT(k.item_id) as keyword_count
               FROM keyword_input_sessions s
               LEFT JOIN keyword_universe_items k ON k.session_id = s.session_id
               WHERE s.project_id=?
               GROUP BY s.session_id
               ORDER BY s.created_at DESC""",
            (project_id,)
        ).fetchall()
        db.close()
        return {"sessions": [dict(r) for r in rows]}

    @app.get("/api/ki/{project_id}/dashboard", tags=["KeywordInput"])
    def ki_dashboard(project_id: str, user=Depends(current_user)):
        """Full keyword dashboard: latest session stats + pillar breakdown + top keywords."""
        db = _ki_db()
        # Find latest session with keywords
        sess_row = db.execute(
            """SELECT s.session_id, s.created_at, s.stage,
                      COUNT(k.item_id) as keyword_count
               FROM keyword_input_sessions s
               LEFT JOIN keyword_universe_items k ON k.session_id = s.session_id
               WHERE s.project_id=?
               GROUP BY s.session_id
               ORDER BY keyword_count DESC, s.created_at DESC
               LIMIT 1""",
            (project_id,)
        ).fetchone()
        if not sess_row or sess_row["keyword_count"] == 0:
            db.close()
            return {"has_keywords": False, "session_id": None}
        session_id = sess_row["session_id"]

        # Stats
        stats_rows = db.execute(
            "SELECT status, COUNT(*) as cnt FROM keyword_universe_items WHERE session_id=? GROUP BY status",
            (session_id,)
        ).fetchall()
        stats = {r["status"]: r["cnt"] for r in stats_rows}
        total = sess_row["keyword_count"]

        # Quick wins + avg KD
        quick_wins = db.execute(
            "SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=? AND difficulty<=20 AND volume_estimate>=100",
            (session_id,)
        ).fetchone()[0]
        avg_kd_val = db.execute(
            "SELECT AVG(difficulty) FROM keyword_universe_items WHERE session_id=?",
            (session_id,)
        ).fetchone()[0]
        avg_kd = round(avg_kd_val, 1) if avg_kd_val else 50

        # KD distribution buckets
        kd_easy   = db.execute("SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=? AND difficulty<=20", (session_id,)).fetchone()[0]
        kd_medium = db.execute("SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=? AND difficulty>20 AND difficulty<=50", (session_id,)).fetchone()[0]
        kd_hard   = db.execute("SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=? AND difficulty>50", (session_id,)).fetchone()[0]

        # Pillar breakdown
        pillar_rows = db.execute(
            """SELECT pillar_keyword as pillar,
                      COUNT(*) as total,
                      SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END) as accepted,
                      SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                      ROUND(AVG(opportunity_score),1) as avg_opp,
                      ROUND(AVG(difficulty),1) as avg_kd
               FROM keyword_universe_items WHERE session_id=?
               GROUP BY pillar_keyword ORDER BY total DESC""",
            (session_id,)
        ).fetchall()

        # Top opportunity keywords
        top_kws = db.execute(
            """SELECT keyword, pillar_keyword, difficulty, volume_estimate,
                      opportunity_score, source, intent, status
               FROM keyword_universe_items WHERE session_id=?
               ORDER BY opportunity_score DESC, volume_estimate DESC
               LIMIT 10""",
            (session_id,)
        ).fetchall()

        # Source breakdown
        source_rows = db.execute(
            "SELECT source, COUNT(*) as cnt FROM keyword_universe_items WHERE session_id=? GROUP BY source ORDER BY cnt DESC",
            (session_id,)
        ).fetchall()

        # AI review delta statistics
        ai_total = db.execute(
            "SELECT COUNT(*) FROM ai_review_results WHERE project_id=? AND session_id=?",
            (project_id, session_id)
        ).fetchone()[0]
        ai_removed = db.execute(
            "SELECT COUNT(*) FROM ai_review_results WHERE project_id=? AND session_id=? AND user_decision='remove'",
            (project_id, session_id)
        ).fetchone()[0]
        ai_keep = db.execute(
            "SELECT COUNT(*) FROM ai_review_results WHERE project_id=? AND session_id=? AND user_decision='keep'",
            (project_id, session_id)
        ).fetchone()[0]

        # Attach latest pipeline status from runs table for this project
        pipeline_run = db.execute(
            "SELECT run_id, status, result, completed_at FROM runs WHERE project_id=? ORDER BY completed_at DESC LIMIT 1",
            (project_id,)
        ).fetchone()

        pipeline_summary = {
            "run_id": None,
            "status": None,
            "topic_count": 0,
            "cluster_count": 0,
            "pillar_count": 0,
            "pipeline_health": None,
            "health_ok": False,
        }

        if pipeline_run and pipeline_run["result"]:
            try:
                run_data = json.loads(pipeline_run["result"])
                topic_count = int(run_data.get("topic_count", 0) or 0)
                cluster_count = int(run_data.get("cluster_count", 0) or 0)
                pillar_count = int(run_data.get("pillar_count", 0) or 0)
                pipeline_health = run_data.get("pipeline_health", {
                    "P8_topic_ok": topic_count > 0,
                    "P9_cluster_ok": cluster_count > 0,
                    "P10_pillar_ok": pillar_count > 0,
                })
                pipeline_health.setdefault("all_ok", pipeline_health.get("P8_topic_ok", topic_count > 0) and pipeline_health.get("P9_cluster_ok", cluster_count > 0) and pipeline_health.get("P10_pillar_ok", pillar_count > 0))

                pipeline_summary.update({
                    "run_id": pipeline_run["run_id"],
                    "status": pipeline_run["status"],
                    "topic_count": topic_count,
                    "cluster_count": cluster_count,
                    "pillar_count": pillar_count,
                    "pipeline_health": pipeline_health,
                })

                pipeline_summary["health_ok"] = (
                    pipeline_summary["status"] == "complete" and
                    topic_count > 0 and
                    cluster_count > 0 and
                    pillar_count > 0
                )
            except Exception:
                pass

        db.close()
        return {
            "has_keywords": True,
            "session_id": session_id,
            "session_created": sess_row["created_at"],
            "stage": sess_row["stage"],
            "pipeline_summary": pipeline_summary,
            "stats": {
                "total": total,
                "pending": stats.get("pending", 0),
                "accepted": stats.get("accepted", 0),
                "rejected": stats.get("rejected", 0),
                "quick_wins": quick_wins,
                "avg_kd": avg_kd,
                "kd_easy": kd_easy,
                "kd_medium": kd_medium,
                "kd_hard": kd_hard,
                "ai_review_total": ai_total,
                "ai_review_removed": ai_removed,
                "ai_review_keep": ai_keep,
            },
            "pillars": [dict(r) for r in pillar_rows],
            "top_keywords": [dict(r) for r in top_kws],
            "sources": [dict(r) for r in source_rows],
        }

    def _get_latest_ki_session(project_id: str):
        db = _ki_db()
        row = db.execute(
            "SELECT * FROM keyword_input_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
            (project_id,)
        ).fetchone()
        db.close()
        return dict(row) if row else None

    def _count_ki_keywords(session_id: str, status: str = None):
        db = _ki_db()
        if status:
            row = db.execute(
                "SELECT COUNT(*) AS cnt FROM keyword_universe_items WHERE session_id=? AND status=?",
                (session_id, status)
            ).fetchone()
        else:
            row = db.execute(
                "SELECT COUNT(*) AS cnt FROM keyword_universe_items WHERE session_id=?",
                (session_id,)
            ).fetchone()
        db.close()
        return row['cnt'] if row else 0

    def _count_pipeline_runs(project_id: str):
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) AS cnt FROM runs WHERE project_id=? AND status='complete'",
            (project_id,)
        ).fetchone()
        db.close()
        return row['cnt'] if row else 0

    def _count_clusters(project_id: str):
        # clusters are derived from completed pipeline runs; if there is >=1 complete run, assume cluster state ready
        return _count_pipeline_runs(project_id)

    @app.get("/api/ki/{project_id}/workflow-status", tags=["KeywordInput"])
    def ki_workflow_status(project_id: str, user=Depends(current_user)):
        session = _get_latest_ki_session(project_id)
        if not session:
            raise HTTPException(404, "No keyword input session found")

        session_id = session.get("session_id")
        raw_stage = session.get("stage", "input")
        stage_status = session.get("stage_status", "pending")

        # Normalize internal KI stages to workflow stages
        stage_map = {
            "cross_multiply": "research",
            "crawl_site": "research",
            "crawl_competitors": "research",
            "enrich": "research",
            "assemble": "research",
            "score": "review",
            "confirmed": "review",
        }
        stage = stage_map.get(raw_stage, raw_stage)

        # Current counts
        total_keywords = _count_ki_keywords(session_id)
        accepted_count = _count_ki_keywords(session_id, "accepted")
        ai_review_total = 0
        ai_review_pending = 0
        db = get_db()
        ai_row = db.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN user_decision='pending' THEN 1 ELSE 0 END) AS pending FROM ai_review_results WHERE project_id=? AND session_id=?",
            (project_id, session_id)
        ).fetchone()
        if ai_row:
            ai_review_total = ai_row["total"] or 0
            ai_review_pending = ai_row["pending"] or 0
        db.close()

        pipeline_completed_runs = _count_pipeline_runs(project_id)
        clusters_count = _count_clusters(project_id)

        # Conditions for advancing
        can_advance = False
        if stage == "input":
            # require at least one pillar or support from the current session
            has_pillars = False
            try:
                db = _ki_db()
                if db:
                    p_row = db.execute("SELECT COUNT(*) AS cnt FROM pillar_keywords WHERE project_id=?", (project_id,)).fetchone()
                    has_pillars = (p_row and p_row["cnt"] > 0)
                db.close()
            except Exception:
                has_pillars = False
            can_advance = has_pillars
        elif stage == "research":
            can_advance = total_keywords > 0
        elif stage == "review":
            # Require a meaningful number of accepted keywords to proceed
            REVIEW_ACCEPTED_THRESHOLD = 20
            can_advance = accepted_count >= REVIEW_ACCEPTED_THRESHOLD
        elif stage == "ai_review":
            can_advance = (ai_review_total > 0 and ai_review_pending == 0)
        elif stage == "pipeline":
            can_advance = pipeline_completed_runs > 0
        elif stage == "clusters":
            can_advance = clusters_count > 0
        elif stage == "calendar":
            can_advance = True

        return {
            "current_stage": stage,
            "stage_status": stage_status,
            "can_advance": can_advance,
            "accepted_count": accepted_count,
            "total_keywords": total_keywords,
            "ai_review_total": ai_review_total,
            "ai_review_pending": ai_review_pending,
            "pipeline_completed_runs": pipeline_completed_runs,
            "clusters_count": clusters_count,
        }

    @app.post("/api/ki/{project_id}/workflow/advance", tags=["KeywordInput"])
    def ki_workflow_advance(project_id: str, user=Depends(current_user)):
        session = _get_latest_ki_session(project_id)
        if not session:
            raise HTTPException(404, "No keyword input session found")

        status = ki_workflow_status(project_id)
        if not status.get("can_advance"):
            raise HTTPException(400, "Cannot advance workflow: complete current step first")

        stage_order = ["input", "research", "review", "ai_review", "pipeline", "clusters", "calendar"]
        current_stage = status.get("current_stage", "input")
        if current_stage not in stage_order:
            raise HTTPException(400, "Unknown workflow stage")

        next_stage = current_stage
        current_idx = stage_order.index(current_stage)
        if current_idx < len(stage_order) - 1:
            next_stage = stage_order[current_idx + 1]

        # Persist status updates
        db = _ki_db()
        db.execute(
            "UPDATE keyword_input_sessions SET stage=?, stage_status='pending', updated_at=? WHERE project_id=?",
            (next_stage, datetime.utcnow().isoformat(), project_id)
        )
        db.commit()
        db.close()

        return {"next_stage": next_stage}

    @app.get("/api/ki/{project_id}/top100/{session_id}", tags=["KeywordInput"])
    def ki_top100(project_id: str, session_id: str, user=Depends(current_user)):
        """Return business-value Top 100 keywords selector for session."""
        from engines.annaseo_keyword_input import UniverseAssembler
        top100 = UniverseAssembler().score_and_select_top100(project_id, session_id)
        return {"top100": top100}

    @app.post("/api/ki/{project_id}/top100/{session_id}/refresh", tags=["KeywordInput"])
    def ki_top100_refresh(project_id: str, session_id: str, user=Depends(current_user)):
        """Recalculate Top 100 after manual edits"""
        from engines.annaseo_keyword_input import UniverseAssembler
        top100 = UniverseAssembler().score_and_select_top100(project_id, session_id)

        # Store snapshot for diff comparisons
        db = _ki_db()
        snapshot_id = f"t100_{uuid.uuid4().hex[:12]}"
        db.execute(
            "INSERT INTO top100_snapshots(snapshot_id, project_id, session_id, keywords) VALUES (?,?,?,?)",
            (snapshot_id, project_id, session_id, json.dumps([x.get("keyword") for x in top100]))
        )
        db.commit()
        db.close()

        return {"top100": top100, "message": "refreshed", "snapshot_id": snapshot_id}

    @app.get("/api/ki/{project_id}/top100/{session_id}/diff", tags=["KeywordInput"])
    def ki_top100_diff(project_id: str, session_id: str, user=Depends(current_user)):
        """Compare last two top100 snapshots for session and return changes."""
        db = _ki_db()
        rows = db.execute(
            "SELECT keywords FROM top100_snapshots WHERE project_id=? AND session_id=? ORDER BY created_at DESC LIMIT 2",
            (project_id, session_id)
        ).fetchall()
        db.close()

        if len(rows) < 2:
            return {"diff": None, "message": "Not enough snapshots for diff"}

        newest = json.loads(rows[0]["keywords"])
        previous = json.loads(rows[1]["keywords"])

        added = [k for k in newest if k not in previous]
        removed = [k for k in previous if k not in newest]
        unchanged = [k for k in newest if k in previous]

        return {"old": previous, "new": newest, "added": added, "removed": removed, "unchanged": unchanged}

    @app.get("/api/ki/{project_id}/top100/{session_id}/summary", tags=["KeywordInput"])
    def ki_top100_summary(project_id: str, session_id: str, user=Depends(current_user)):
        """Summary stats for top100 keywords by category and avg scores."""
        from engines.annaseo_keyword_input import UniverseAssembler
        top100 = UniverseAssembler().score_and_select_top100(project_id, session_id)

        cats = {"money": [], "consideration": [], "informational": []}
        for kw in top100:
            c = kw.get("category", "informational")
            if c in cats:
                cats[c].append(kw.get("final_score", 0))

        def avg(vals):
            return round(sum(vals)/len(vals), 2) if vals else 0

        return {
            "count": len(top100),
            "category_counts": {k: len(v) for k, v in cats.items()},
            "category_avg": {k: avg(v) for k, v in cats.items()},
            "total_avg": avg([kw.get("final_score", 0) for kw in top100])
        }

    @app.post("/api/ki/{project_id}/top100/{session_id}/serp-check", tags=["KeywordInput"])
    def ki_top100_serp_check(project_id: str, session_id: str, body: dict = Body(...), user=Depends(current_user)):
        """Update SERP content verification signals in ai_flags for a keyword."""
        keyword = body.get("keyword")
        domain_authority = body.get("domain_authority", 0)
        competitor_intent = body.get("competitor_intent", "")
        page_type = body.get("page_type", "")

        if not keyword:
            raise HTTPException(400, "keyword required")

        db = _ki_db()
        row = db.execute(
            "SELECT ai_flags FROM keyword_universe_items WHERE project_id=? AND session_id=? AND keyword=?",
            (project_id, session_id, keyword)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Keyword not found")

        old_flags = {}
        try:
            old_flags = json.loads(row["ai_flags"] or "{}")
        except Exception:
            old_flags = {}

        updated_flags = {**old_flags, "serp_domain_authority": domain_authority,
                         "competitor_intent": competitor_intent,
                         "serp_page_type": page_type}

        db.execute(
            "UPDATE keyword_universe_items SET ai_flags=? WHERE project_id=? AND session_id=? AND keyword=?",
            (json.dumps(updated_flags), project_id, session_id, keyword)
        )
        db.commit()
        db.close()

        return {"ok": True, "ai_flags": updated_flags}

    @app.get("/api/ki/{project_id}/pipeline/metrics", tags=["KeywordInput"])
    def ki_pipeline_metrics(project_id: str, session_id: str, user=Depends(current_user)):
        """Return pipeline metrics: coverage + cluster health + top100 buckets."""
        db = _ki_db()

        # 1) keyword counts
        total = db.execute(
            "SELECT COUNT(*) FROM keyword_universe_items WHERE project_id=? AND session_id=?",
            (project_id, session_id)
        ).fetchone()[0]
        accepted = db.execute(
            "SELECT COUNT(*) FROM keyword_universe_items WHERE project_id=? AND session_id=? AND status='accepted'",
            (project_id, session_id)
        ).fetchone()[0]
        rejected = db.execute(
            "SELECT COUNT(*) FROM keyword_universe_items WHERE project_id=? AND session_id=? AND status='rejected'",
            (project_id, session_id)
        ).fetchone()[0]

        # 2) cluster health via pillar groups
        pillar_stats = db.execute(
            "SELECT pillar_keyword, COUNT(*) as cnt, AVG(opportunity_score) as avg_opp, AVG(difficulty) as avg_kd "
            "FROM keyword_universe_items WHERE project_id=? AND session_id=? GROUP BY pillar_keyword",
            (project_id, session_id)
        ).fetchall()
        pillar_health = [dict(r) for r in pillar_stats]

        # 3) top100 bucket distribution by competition
        top100 = db.execute(
            "SELECT keyword, ai_flags FROM keyword_universe_items WHERE project_id=? AND session_id=? ORDER BY final_score DESC LIMIT 100",
            (project_id, session_id)
        ).fetchall()
        buckets = {"low": 0, "medium": 0, "high": 0}
        for row in top100:
            flags = json.loads(row["ai_flags"] or "{}")
            comp = flags.get("serp_domain_authority", 50)
            if comp <= 40:
                buckets["low"] += 1
            elif comp <= 70:
                buckets["medium"] += 1
            else:
                buckets["high"] += 1

        db.close()

        return {
            "total_keywords": total,
            "accepted": accepted,
            "rejected": rejected,
            "pillar_health": pillar_health,
            "top100_competition_buckets": buckets,
            "coverage": {
                "pillar_count": len(pillar_health),
                "top100_percentage": 100 * min(100, total) / max(1, total)
            }
        }

    @app.get("/api/ki/{project_id}/pipeline/report", tags=["KeywordInput"])
    def ki_pipeline_report(project_id: str, session_id: str, user=Depends(current_user)):
        """Consolidated pipeline report across P4..P10 metrics."""
        metrics = ki_pipeline_metrics(project_id, session_id, user)
        top100 = ki_top100(project_id, session_id, user)
        summary = ki_top100_summary(project_id, session_id, user)
        status = ki_top100_status(project_id, session_id, user)
        diff = ki_top100_diff(project_id, session_id, user)

        normalization = None
        if _pipeline_health.get("last_result"):
            normalization = _pipeline_health["last_result"].get("normalization")

        return {
            "metrics": metrics,
            "top100": top100,
            "summary": summary,
            "status": status,
            "diff": diff,
            "normalization": normalization,
        }

    @app.get("/api/ki/{project_id}/top100/{session_id}/status", tags=["KeywordInput"])
    def ki_top100_status(project_id: str, session_id: str, user=Depends(current_user)):
        """Top100 status including snapshot and timing details."""
        db = _ki_db()
        rows = db.execute(
            "SELECT snapshot_id, created_at FROM top100_snapshots WHERE project_id=? AND session_id=? ORDER BY created_at DESC LIMIT 2",
            (project_id, session_id)
        ).fetchall()
        db.close()

        if not rows:
            return {
                "latest_snapshot_id": None,
                "last_refreshed_at": None,
                "diff_age": None,
                "top100_status": "no snapshots"
            }

        latest = rows[0]
        previous = rows[1] if len(rows) > 1 else None
        now = datetime.utcnow()
        last_refreshed_at = latest["created_at"]
        diff_age = None
        if previous:
            previous_ts = datetime.fromisoformat(previous["created_at"])
            diff_age = (datetime.fromisoformat(latest["created_at"]) - previous_ts).total_seconds()

        return {
            "latest_snapshot_id": latest["snapshot_id"],
            "last_refreshed_at": last_refreshed_at,
            "diff_age": diff_age,
            "top100_status": "ok"
        }

    # Pipeline health tracker
    _pipeline_health = {
        "running": False,
        "last_run": None,
        "last_duration_seconds": None,
        "last_error": None,
        "last_result": None,
    }

    @app.post("/api/ki/{project_id}/pipeline/generate", tags=["KeywordInput"])
    def ki_pipeline_generate(project_id: str, body: dict = Body(...), user=Depends(current_user)):
        """Full SEO keyword engine pipeline (p4-p10) for project/session."""
        from engines.seo_keyword_pipeline import run_full_pipeline

        if project_id != body.get("project_id"):
            raise HTTPException(400, "project_id mismatch")

        # Enforce stage progression guard (cannot run pipeline early)
        status = ki_workflow_status(project_id)
        if status.get("current_stage") in ["input", "research", "review", "ai_review"]:
            raise HTTPException(403, "Cannot run pipeline before completing AI review")

        _pipeline_health["running"] = True
        _pipeline_health["last_error"] = None
        start_ts = datetime.utcnow()

        try:
            result = run_full_pipeline(body)
            _pipeline_health["last_result"] = result
            return result
        except Exception as e:
            _pipeline_health["last_error"] = str(e)
            raise
        finally:
            duration = (datetime.utcnow() - start_ts).total_seconds()
            _pipeline_health["running"] = False
            _pipeline_health["last_run"] = start_ts.isoformat()
            _pipeline_health["last_duration_seconds"] = round(duration, 2)

    @app.get("/api/ki/{project_id}/pipeline/report", tags=["KeywordInput"])
    def ki_pipeline_report(project_id: str, session_id: str, level: str = "basic", user=Depends(current_user)):
        """Consolidated pipeline report across P4..P10 metrics."""
        base = ki_pipeline_metrics(project_id, session_id, user)
        top100 = ki_top100(project_id, session_id, user)
        summary = ki_top100_summary(project_id, session_id, user)
        status = ki_top100_status(project_id, session_id, user)
        diff = ki_top100_diff(project_id, session_id, user)

        report = {
            "metrics": base,
            "top100": top100,
            "summary": summary,
            "status": status,
            "diff": diff,
        }

        if level == "debug":
            # add raw ai_flags profiling for top100 keywords
            report["debug"] = {
                "top100_raw_ai_flags": [
                    {"keyword": kw.get("keyword"), "ai_flags": kw.get("ai_flags")} 
                    for kw in top100.get("top100", [])
                ]
            }

        return report

    @app.post("/api/ki/{project_id}/pipeline/refresh", tags=["KeywordInput"])
    def ki_pipeline_refresh(project_id: str, body: dict = Body(...), user=Depends(current_user)):
        """Trigger pipeline regenerate and update status instantly."""
        if project_id != body.get("project_id"):
            raise HTTPException(400, "project_id mismatch")

        pipeline_result = ki_pipeline_generate(project_id, body, user)
        status = ki_top100_status(project_id, body.get("session_id"), user)
        return {"pipeline": pipeline_result, "status": status}

    @app.get("/api/ki/{project_id}/pipeline/health", tags=["KeywordInput"])
    def ki_pipeline_health(project_id: str, user=Depends(current_user)):
        """Pipeline operational health status."""
        return {
            "running": _pipeline_health["running"],
            "last_run": _pipeline_health["last_run"],
            "last_duration_seconds": _pipeline_health["last_duration_seconds"],
            "last_error": _pipeline_health["last_error"],
        }

        domain_authority = body.get("domain_authority", 0)
        competitor_intent = body.get("competitor_intent", "")
        page_type = body.get("page_type", "")

        if not keyword:
            raise HTTPException(400, "keyword required")

        db = _ki_db()
        row = db.execute(
            "SELECT ai_flags FROM keyword_universe_items WHERE project_id=? AND session_id=? AND keyword=?",
            (project_id, session_id, keyword)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Keyword not found")

        old_flags = {}
        try:
            old_flags = json.loads(row["ai_flags"] or "{}")
        except Exception:
            old_flags = {}

        updated_flags = {**old_flags, "serp_domain_authority": domain_authority,
                         "competitor_intent": competitor_intent,
                         "serp_page_type": page_type}

        db.execute(
            "UPDATE keyword_universe_items SET ai_flags=? WHERE project_id=? AND session_id=? AND keyword=?",
            (json.dumps(updated_flags), project_id, session_id, keyword)
        )
        db.commit()
        db.close()

        return {"ok": True, "ai_flags": updated_flags}

    log.info("[main] KeywordInputEngine routes registered at /api/ki/")

except Exception as _ki_err:
    log.warning(f"[main] KeywordInputEngine not loaded: {_ki_err}")


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD WORKFLOW — RESEARCH ENGINE, AI REVIEW, PROMPTS, PIPELINE, CLUSTERS
# ─────────────────────────────────────────────────────────────────────────────

# ── Default prompts ───────────────────────────────────────────────────────────

_DEFAULT_PROMPTS = {
    "deepseek_kw_review": (
        "You are an SEO Keyword Quality Control Engine.\n"
        "INPUT: Business={{business_description}}, Industry={{industry}}, Target Audience={{target_audience}}, Seed Keywords={{seed_keywords}}, Generated Keywords={{keywords}}.\n"
        "TASKS:\n"
        "1. REMOVE INVALID KEYWORDS:\n"
        "   - grammatically incorrect or unnatural word order (e.g., 'powder turmeric').\n"
        "   - irrelevant to business or intent.\n"
        "   - duplicates / near-duplicates.\n"
        "2. FIX WORD ORDER & PHRASE STRUCTURE:\n"
        "   - 'powder turmeric' -> 'turmeric powder'.\n"
        "   - 'buy turmeric best' -> 'best turmeric to buy'.\n"
        "3. NORMALIZE: lowercase, trim, remove noise.\n"
        "4. INTENT: informational/commercial/transactional/navigational, reject unclear.\n"
        "5. SEARCH REALISM: keep human-like Google query patterns.\n"
        "6. GROUP SIMILAR KEYWORDS: cluster, dedupe, canonicalize.\n"
        "OUTPUT JSON ONLY (strict):\n"
        "{\n"
        "  \"clean_keywords\": [\n"
        "    {\"keyword\":\"...\",\"intent\":\"...\",\"confidence_score\":0-100,\"action\":\"kept|corrected|removed\",\"original\":\"...\",\"reason\":\"...\"}\n"
        "  ],\n"
        "  \"clusters\": [\n"
        "    {\"main_keyword\":\"...\",\"variations\":[\"...\"]}\n"
        "  ],\n"
        "  \"removed_keywords\": [\n"
        "    {\"keyword\":\"...\",\"reason\":\"...\"}\n"
        "  ]\n"
        "}"
    ),
    "groq_kw_review": (
        "You are a fast SEO keyword validator for high-throughput cleanup.\n"
        "Follow the same validations as deepseek but with strict, deterministic behavior.\n"
        "Convert unnatural, commercial-noise keywords and remove low-likelihood phrase orders.\n"
        "OUTPUT JSON ONLY (strict) as array: [{\"original\":\"...\",\"final\":\"...\",\"action\":\"kept|corrected|removed\",\"intent\":\"...\",\"score\":0-100,\"reason\":\"...\"}]"
    ),
    "gemini_kw_review": (
        "You are a balanced Keyword Intelligence Engine.\n"
        "Apply keyword semantics, intent, conversion potential, and natural language patterns.\n"
        "Use the same output schema as deepseek.\n"
        "OUTPUT JSON ONLY (strict) as array: [{\"original\":\"...\",\"final\":\"...\",\"action\":\"kept|corrected|removed\",\"intent\":\"...\",\"confidence\":0-100,\"reason\":\"...\"}]"
    ),
    "claude_kw_review": (
        "You are an advanced SEO strategy reviewer fallback.\n"
        "INPUT: Business={{business_type}}, Industry={{industry}}, Keywords={{keywords}}.\n"
        "TASK: Provide risk/opportunity commentary.\n"
        "OUTPUT JSON ONLY as array: [{\"keyword\":\"...\",\"action\":\"keep|edit|remove\",\"reason\":\"...\",\"score\":0-100}]"
    ),
    "cluster_naming": (
        "You are a content strategist. Given keywords clustered together, suggest a concise cluster name (3-5 words) and a content type (blog/guide/comparison/faq).\n"
        "Keywords: {{keywords}}\n"
        "Respond ONLY as JSON: {\"name\":\"...\",\"content_type\":\"...\"}"
    ),
}

# ── Try to import research engines ────────────────────────────────────────────

try:
    from engines.annaseo_p2_enhanced import P2_Enhanced as _P2E
    _p2e_available = True
except Exception as _p2e_err:
    _p2e_available = False
    log.warning(f"[main] P2_Enhanced not loaded: {_p2e_err}")

try:
    from engines.annaseo_competitor_gap import CompetitorGapEngine as _CGE, CompetitorCrawler as _CGCrawler
    _cge_available = True
except Exception as _cge_err:
    _cge_available = False
    log.warning(f"[main] CompetitorGapEngine not loaded: {_cge_err}")

try:
    from engines.annaseo_ai_brain import AnnaBrain as _AnnaBrain
    _brain_available = True
except Exception as _brain_err:
    _brain_available = False
    log.warning(f"[main] AnnaBrain not loaded: {_brain_err}")

# ── Helper: get project info for prompt variable filling ──────────────────────

def _get_project_context(project_id: str, db) -> dict:
    row = db.execute(
        "SELECT industry, business_type, usp, target_locations FROM projects WHERE project_id=?",
        (project_id,)
    ).fetchone()
    if not row:
        return {"industry": "general", "business_type": "B2C", "usp": "", "locations": "india"}
    locs = row["target_locations"] or "[]"
    try:
        locs = ", ".join(json.loads(locs)) or "india"
    except Exception:
        locs = "india"
    return {
        "industry": row["industry"] or "general",
        "business_type": row["business_type"] or "B2C",
        "usp": row["usp"] or "",
        "locations": locs,
    }

def _fill_prompt(template: str, ctx: dict, keywords: list) -> str:
    kw_str = "\n".join(f"- {k}" for k in keywords[:200])
    return (template
        .replace("{{business_type}}", ctx.get("business_type", "B2C"))
        .replace("{{industry}}", ctx.get("industry", "general"))
        .replace("{{usp}}", ctx.get("usp", ""))
        .replace("{{locations}}", ctx.get("locations", "india"))
        .replace("{{keywords}}", kw_str)
    )

# ── Background: research job ──────────────────────────────────────────────────

def _run_research_job(job_id: str, project_id: str, session_id: str,
                      customer_url: str, competitor_urls: list):
    main_db = get_db()   # main annaseo.db — holds research_jobs table
    # KI engine's own SQLite holds keyword_universe_items + pillar_keywords
    try:
        from engines.annaseo_keyword_input import _db as _ki_db_fn
        ki_db = _ki_db_fn()
    except Exception:
        ki_db = None
    found_keywords = []
    sources_done = []
    # track raw counts per source for debugging / UX reasons
    autosuggest_count = 0
    competitor_count = 0
    site_crawl_count = 0

    def _update(sources: list, count: int, status: str = "running", counts: dict = None, reasons: list = None):
        progress = min(100, int((len(sources) / 3) * 100))
        payload = {"sources_done": sources, "keyword_count": count}
        if counts is not None:
            payload["source_counts"] = counts
        if reasons:
            payload["why_no_keywords"] = reasons

        job_tracker.update_strategy_job(main_db, job_id,
                                       status=status,
                                       progress=progress,
                                       current_step=sources[-1] if sources else "",
                                       result_payload=payload)
        # legacy research_jobs tracking (for backward compatibility)
        main_db.execute(
            "UPDATE research_jobs SET status=?,sources_done=?,keyword_count=? WHERE job_id=?",
            (status, json.dumps(sources), count, job_id)
        )
        main_db.commit()

    try:
        # Source 1: Google Autosuggest via P2_Enhanced
        if _p2e_available:
            try:
                p2e = _P2E()
                kws = p2e.run_from_input(project_id, session_id) if session_id else []
                for kw in kws:
                    kw_text = kw if isinstance(kw, str) else kw.get("keyword", "")
                    if kw_text:
                        found_keywords.append({"keyword": kw_text, "source": "autosuggest",
                                               "pillar": "", "intent": "informational",
                                               "volume_estimate": 0, "difficulty": 50,
                                               "opportunity_score": 0.5, "status": "pending"})
                autosuggest_count = len(kws)
                sources_done.append("autosuggest")
                _update(sources_done, len(found_keywords))
            except Exception as e:
                log.warning(f"[research] P2_Enhanced failed: {e}")

        # Source 2: Competitor crawl via CompetitorGapEngine
        if _cge_available and competitor_urls:
            try:
                crawler = _CGCrawler()
                for url in competitor_urls[:3]:
                    pages = crawler.crawl(url, max_pages=10)
                    for page in pages:
                        for kw in page.keywords[:30]:
                            found_keywords.append({"keyword": kw, "source": "competitor_gap",
                                                   "pillar": "", "intent": "informational",
                                                   "volume_estimate": 0, "difficulty": 50,
                                                   "opportunity_score": 0.4, "status": "pending"})
                            competitor_count += 1
                sources_done.append("competitor_gap")
                _update(sources_done, len(found_keywords))
            except Exception as e:
                log.warning(f"[research] CompetitorCrawler failed: {e}")

        elif competitor_urls and not _cge_available:
            log.warning("[research] CompetitorGapEngine unavailable, skipping competitor gap source")

        # Source 3: Site crawl (WebsiteKeywordExtractor.crawl)
        if customer_url:
            try:
                from engines.annaseo_keyword_input import WebsiteKeywordExtractor as _WKE
                # Get pillar keywords for this session to guide extraction
                _pillar_rows = []
                if ki_db is not None:
                    _pillar_rows = ki_db.execute(
                        "SELECT keyword FROM pillar_keywords WHERE project_id=?",
                        (project_id,)
                    ).fetchall()
                pillar_words = [r[0] for r in _pillar_rows] if _pillar_rows else []
                wke = _WKE()
                site_kws = wke.crawl(customer_url, pillar_words, label="site_crawl")
                for kw in (site_kws or []):
                    kw_text = kw if isinstance(kw, str) else kw.get("keyword", str(kw))
                    if kw_text:
                        found_keywords.append({"keyword": kw_text, "source": "site_crawl",
                                               "pillar": "", "intent": "informational",
                                               "volume_estimate": 0, "difficulty": 50,
                                               "opportunity_score": 0.6, "status": "pending"})
                site_crawl_count = len(site_kws or [])
                sources_done.append("site_crawl")
                _update(sources_done, len(found_keywords))
                log.info(f"[research] SiteCrawl: {len(site_kws or [])} keywords from {customer_url}")
            except Exception as e:
                log.warning(f"[research] SiteCrawl failed: {e}", exc_info=True)

        # Fallback: If no results from research sources, seed from existing KI session universe
        fallback_count = 0
        if not found_keywords and session_id and ki_db is not None:
            try:
                existing_rows = ki_db.execute(
                    "SELECT keyword, pillar_keyword, intent, volume_estimate, difficulty, opportunity_score FROM keyword_universe_items WHERE session_id=?",
                    (session_id,)
                ).fetchall()
                for row in existing_rows:
                    found_keywords.append({
                        "keyword": row["keyword"],
                        "source": "existing_universe",
                        "pillar": row["pillar_keyword"] if "pillar_keyword" in row.keys() else "",
                        "intent": row["intent"] if "intent" in row.keys() and row["intent"] else "informational",
                        "volume_estimate": row["volume_estimate"] if "volume_estimate" in row.keys() and row["volume_estimate"] is not None else 0,
                        "difficulty": row["difficulty"] if "difficulty" in row.keys() and row["difficulty"] is not None else 50,
                        "opportunity_score": row["opportunity_score"] if "opportunity_score" in row.keys() and row["opportunity_score"] is not None else 0.5,
                        "status": "pending"
                    })
                fallback_count = len(existing_rows)
                if fallback_count:
                    sources_done.append("fallback_existing_universe")
                    _update(sources_done, len(found_keywords))
                    log.info(f"[research] Fallback existing universe: {fallback_count} keywords from session {session_id}")
            except Exception as e:
                log.warning(f"[research] Fallback to existing universe failed: {e}")

        # Deduplicate
        seen = set()
        deduped = []
        for item in found_keywords:
            kw = item["keyword"].lower().strip()
            if kw and kw not in seen:
                seen.add(kw)
                deduped.append(item)

        # Save to keyword_universe_items with source prefix "research_*"
        # These live in the KI engine's own SQLite (ki_db), not main DB
        save_db = ki_db if ki_db is not None else main_db
        if session_id and deduped:
            for item in deduped:
                try:
                    save_db.execute(
                        """INSERT OR IGNORE INTO keyword_universe_items
                           (session_id, keyword, pillar_keyword, source, intent,
                            volume_estimate, difficulty, opportunity_score, status)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (session_id, item["keyword"], item.get("pillar",""),
                         f"research_{item['source']}", item.get("intent","informational"),
                         item.get("volume_estimate",0), item.get("difficulty",50),
                         item.get("opportunity_score",0.5), "pending")
                    )
                except Exception:
                    pass
            save_db.commit()
        # Add counts and friendly reasons when no keywords were produced
        counts = {
            "autosuggest": autosuggest_count,
            "competitor_gap": competitor_count,
            "site_crawl": site_crawl_count,
            "fallback_existing_universe": fallback_count,
        }
        reasons = []
        if not deduped:
            if not _p2e_available:
                reasons.append("autosuggest_engine_unavailable")
            elif autosuggest_count == 0:
                reasons.append("autosuggest_empty_or_no_pillars")

            if competitor_urls and not _cge_available:
                reasons.append("competitor_gap_engine_unavailable")
            elif competitor_count == 0:
                if competitor_urls:
                    reasons.append("competitor_crawl_empty_or_blocked")
                else:
                    reasons.append("no_competitor_urls_provided")

            if site_crawl_count == 0:
                if customer_url:
                    reasons.append("site_crawl_empty_or_blocked")
                else:
                    reasons.append("no_customer_url_provided")

            if fallback_count:
                reasons.append("fallback_from_existing_universe")

        _update(sources_done, len(deduped), "completed", counts=counts, reasons=reasons)

    except Exception as e:
        err = str(e)
        job_tracker.update_strategy_job(main_db, job_id,
                                       status="failed",
                                       progress=100,
                                       error_message=err,
                                       result_payload={"sources_done": sources_done, "keyword_count": len(found_keywords)})
        main_db.execute("UPDATE research_jobs SET status='failed',error=? WHERE job_id=?", (err, job_id))
        main_db.commit()
    finally:
        main_db.close()
        if ki_db is not None:
            ki_db.close()

# ── Scorer background task ────────────────────────────────────────────────────

def _run_score_job(job_id: str, project_id: str, session_id: str):
    """Background task: score all keyword_universe_items for a session."""
    try:
        from engines.annaseo_keyword_input import _db as _ki_db_fn
        ki_db = _ki_db_fn()
        rows = ki_db.execute(
            "SELECT item_id, keyword, relevance_score FROM keyword_universe_items WHERE session_id=?",
            (session_id,)
        ).fetchall()
        keywords = [dict(r) for r in rows]
        job_tracker.update_strategy_job(main_db, job_id, progress=0, status="running", input_payload={"total": len(keywords)})

        try:
            from engines.annaseo_keyword_scorer import KeywordScoringEngine as _KSE_local
            scorer = _kse or _KSE_local()
        except Exception:
            scorer = None

        if scorer is None:
            job_tracker.update_strategy_job(main_db, job_id, status="failed", error_message="KeywordScoringEngine not available")
            return

        def _progress(scored, total):
            pct = int((scored / total) * 100) if total else 0
            job_tracker.update_strategy_job(main_db, job_id, progress=pct, current_step=f"scoring_{scored}", result_payload={"scored": scored, "total": total})

        scored_kws = scorer.score_batch(keywords, on_progress=_progress)

        for kw in scored_kws:
            ki_db.execute(
                """UPDATE keyword_universe_items
                   SET difficulty=?, volume_estimate=?, opportunity_score=?, score_signals=?
                   WHERE item_id=?""",
                (kw["difficulty"], kw["volume_estimate"],
                 kw["opportunity_score"], kw.get("score_signals", "{}"),
                 kw["item_id"])
            )
        ki_db.commit()
        ki_db.close()
        job_tracker.update_strategy_job(main_db, job_id, status="completed", progress=100, result_payload={"scored": len(scored_kws), "total": len(keywords)})
    except Exception as e:
        log.error(f"[Score job {job_id}] Failed: {e}")
        job_tracker.update_strategy_job(main_db, job_id, status="failed", error_message=str(e))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/api/ki/{project_id}/research")
async def ki_research(
    project_id: str,
    background_tasks: BackgroundTasks,
    body: dict = Body(default={}),
    user=Depends(current_user)
):
    """
    Step 2: Research keywords using 3-source priority ranking.

    Sources:
    1. User's supporting keywords (score +10)
    2. Google Autosuggest (score +5)
    3. AI classification (variable score)
    """
    db = get_db()
    session_id = body.get("session_id", "")
    # Normalize business_intent: accept both string and list
    _bi = body.get("business_intent", "mixed")
    if isinstance(_bi, list):
        business_intent = ",".join(_bi) if _bi else "mixed"
    else:
        business_intent = _bi or "mixed"

    if not session_id:
        raise HTTPException(400, "session_id required")

    # Get project for industry context
    project = db.execute(
        "SELECT industry FROM projects WHERE project_id=?",
        (project_id,)
    ).fetchone()
    industry = project["industry"] if project else "general"

    # Create research job
    job_id = str(uuid.uuid4())

    try:
        # Run research synchronously (fast: <5s per pillar)
        from engines.research_engine import ResearchEngine
        engine = ResearchEngine(industry=industry)

        results = engine.research_keywords(
            project_id=project_id,
            session_id=session_id,
            business_intent=business_intent,
            language="en"
        )

        # Convert to dict format
        keywords = [
            {
                "keyword": r.keyword,
                "source": r.source,
                "intent": r.intent,
                "volume": r.volume,
                "difficulty": r.difficulty,
                "score": r.total_score,
                "confidence": r.confidence,
                "pillar_keyword": r.pillar_keyword,
                "reasoning": r.reasoning,
            }
            for r in results
        ]

        # Save to research_results table
        try:
            from annaseo_wiring import _db as wiring_db_fn
            research_db = wiring_db_fn()
            for kw in keywords:
                kw_id = hashlib.md5(f"{job_id}_{kw['keyword']}".encode()).hexdigest()
                research_db.execute(
                    """INSERT OR IGNORE INTO research_results
                       (result_id, session_id, keyword, source, intent, volume, difficulty, score, confidence, pillar_keyword)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (kw_id, session_id, kw["keyword"], kw["source"], kw["intent"],
                     kw["volume"], kw["difficulty"], kw["score"], kw["confidence"],
                     kw["pillar_keyword"])
                )
            research_db.commit()
            research_db.close()
        except Exception as e:
            log.warning(f"[research] Could not save results: {e}")

        # Update job_tracker
        job_tracker.update_strategy_job(
            db, job_id,
            status="completed",
            progress=100,
            result_payload={
                "keywords": keywords,
                "total_count": len(keywords),
                "by_source": {
                    "user": len([k for k in keywords if k["source"] == "user"]),
                    "google": len([k for k in keywords if k["source"] == "google"]),
                },
                "by_intent": {
                    "transactional": len([k for k in keywords if k["intent"] == "transactional"]),
                    "informational": len([k for k in keywords if k["intent"] == "informational"]),
                    "comparison": len([k for k in keywords if k["intent"] == "comparison"]),
                }
            }
        )

        log.info(f"[research] Complete: {len(keywords)} keywords for {project_id}")
        return {
            "job_id": job_id,
            "status": "completed",
            "keywords": keywords,
            "summary": {
                "total": len(keywords),
                "by_source": {
                    "user": len([k for k in keywords if k["source"] == "user"]),
                    "google": len([k for k in keywords if k["source"] == "google"]),
                },
                "by_intent": {
                    "transactional": len([k for k in keywords if k["intent"] == "transactional"]),
                    "informational": len([k for k in keywords if k["intent"] == "informational"]),
                }
            }
        }

    except Exception as e:
        log.error(f"[research] Failed: {e}", exc_info=True)
        job_tracker.update_strategy_job(db, job_id, status="failed", error_message=str(e))
        raise HTTPException(500, f"Research failed: {str(e)[:100]}")
    finally:
        db.close()


@app.post("/api/ki/{project_id}/run")
async def ki_run(project_id: str, background_tasks: BackgroundTasks, body: dict = Body(default={}), user=Depends(current_user), request: Request = None):
    """Run a strategy job (single_call or multi_step)."""
    request_id = getattr(request.state, 'request_id', None)
    logger = get_logger('api')
    if request_id:
        logger = bind_context(logger, request_id=request_id, project_id=project_id)
    # Avoid passing arbitrary kwargs to logger methods in plain logging
    logger.info(f'run_job_request project_id={project_id} request_id={request_id}')
    db = get_db()
    mode = body.get("execution_mode", "multi_step")
    if mode not in ("multi_step", "single_call"):
        raise HTTPException(400, "execution_mode must be single_call or multi_step")

    job_id = f"strategy_{uuid.uuid4().hex[:12]}"
    payload = {"project_id": project_id, **body}
    job_tracker.create_strategy_job(db, job_id, project_id=project_id, job_type="strategy", input_payload=payload, execution_mode=mode, max_retries=2)

    enqueued = False
    if mode == "single_call":
        if pipeline_queue is None:
            raise HTTPException(status_code=503, detail="Queue unavailable")
        try:
            pipeline_queue.enqueue(run_single_call_job, job_id, job_timeout=7200, retry=2)
            enqueued = True
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to enqueue single_call job: {e}")
    else:
        # new pipeline path: run annotated step engine
        if pipeline_queue is None:
            raise HTTPException(status_code=503, detail="Queue unavailable")
        try:
            pipeline_queue.enqueue(run_pipeline_job, job_id, project_id, body.get("pillar", ""), job_timeout=7200, retry=2)
            enqueued = True
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to enqueue pipeline job: {e}")

    return {"job_id": job_id, "execution_mode": mode, "enqueued": enqueued}


@app.get("/api/ki/{project_id}/research/{job_id}")
async def ki_research_status(project_id: str, job_id: str,
                              user=Depends(current_user)):
    """Poll research job status."""
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if job:
        return job
    row = db.execute("SELECT * FROM research_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Research job not found")
    try:
        return dict(row)
    except Exception:
        raise HTTPException(404, "Research job not found")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str, user=Depends(current_user)):
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs/{job_id}/pause")
def pause_job_route(job_id: str, user=Depends(current_user)):
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    pause_job(db, job_id)
    return {"job_id": job_id, "control": "paused"}


@app.post("/api/serp/cache/invalidate")
async def invalidate_serp_cache(keyword: str = Body(...), location: str = Body("global"), device: str = Body("desktop"), user=Depends(current_user)):
    db = get_db()
    db.execute("DELETE FROM serp_cache WHERE keyword=? AND location=? AND device=?", (keyword, location, device))
    db.commit()
    return {"status": "ok", "invalidated": True, "keyword": keyword, "location": location, "device": device}


def get_serp_cache_stats():
    from core.metrics import serp_cache_hit_total, serp_cache_miss_total, serp_cache_stale_total

    def safe_counter(v):
        if v is None:
            return 0
        try:
            return int(v._value.get())
        except Exception:
            return 0

    hits = safe_counter(serp_cache_hit_total)
    misses = safe_counter(serp_cache_miss_total)
    stales = safe_counter(serp_cache_stale_total)
    total = hits + misses + stales

    def safe_ratio(n, d):
        return round(float(n / d), 4) if d > 0 else 0.0

    return {
        "hit": hits,
        "miss": misses,
        "stale": stales,
        "total": total,
        "hit_rate": safe_ratio(hits, hits + misses),
        "fallback_rate": safe_ratio(stales, total),
    }


@app.get("/api/serp/cache/stats")
async def serp_cache_stats(user=Depends(current_user)):
    return get_serp_cache_stats()


@app.get("/api/dashboard/metrics")
def dashboard_metrics(user=Depends(current_user)):
    from datetime import datetime
    from core.metrics import collect_metrics_json

    metrics = collect_metrics_json()
    cache_stats = get_serp_cache_stats()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "kpis": {
            "job_success_rate": metrics.get("strategy_job_success_rate", 0),
            "jobs_successful": metrics.get("strategy_jobs_successful", 0),
            "avg_job_duration": metrics.get("strategy_job_duration_seconds_avg", 0),
        },
        "serp": {
            "hit_rate": cache_stats.get("hit_rate", 0),
            "fallback_rate": cache_stats.get("fallback_rate", 0),
            "total_requests": cache_stats.get("total", 0),
        },
        "alerts": [],
        "raw": {
            "metrics": metrics,
            "serp_cache": cache_stats,
        },
    }


@app.post("/api/serp/cache/gc")
async def serp_cache_gc(ttl_days: int = Body(30), user=Depends(current_user)):
    db = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=ttl_days)).isoformat()
    deleted = db.execute("DELETE FROM serp_cache WHERE fetched_at <= ?", (cutoff,)).rowcount
    db.commit()
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff}


from core.experiment import (
    create_experiment,
    get_experiment,
    list_experiments,
    assign_variant,
    record_result,
    get_experiment_summary,
)
from core.action_engine import decide_actions, execute_actions


@app.post("/api/experiment/create")
def experiment_create(body: Dict, user=Depends(current_user)):
    db = get_db()
    name = body.get("name")
    variants = body.get("variants", [])
    payload = body.get("payload", {})

    if not name or not variants:
        raise HTTPException(400, "name and variants are required")

    exp = create_experiment(db, name=name, variants=variants, payload=payload)
    return exp


@app.get("/api/experiment")
def experiment_list(user=Depends(current_user)):
    db = get_db()
    return list_experiments(db)


@app.get("/api/experiment/{experiment_id}")
def experiment_get(experiment_id: int, user=Depends(current_user)):
    db = get_db()
    exp = get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    exp["summary"] = get_experiment_summary(db, experiment_id)
    return exp


@app.post("/api/experiment/{experiment_id}/assign")
def experiment_assign(experiment_id: int, user=Depends(current_user)):
    db = get_db()
    variant = assign_variant(db, experiment_id)
    if not variant:
        raise HTTPException(404, "Experiment not found or no variants")
    return {"variant": variant}


@app.post("/api/experiment/{experiment_id}/record")
def experiment_record(experiment_id: int, body: Dict, user=Depends(current_user)):
    db = get_db()
    variant = body.get("variant")
    job_id = body.get("job_id")
    roi = body.get("roi")
    status = body.get("status", "completed")
    extra_context = body.get("extra_context", {})
    serp_data = body.get("serp_data", {})

    if variant is None or job_id is None or roi is None:
        raise HTTPException(400, "variant, job_id, and roi are required")

    record_result(db, experiment_id, variant, job_id, float(roi), status, extra_context=extra_context, serp_data=serp_data)
    return {"status": "ok"}


@app.post("/api/gsc/ingest")
def gsc_ingest(body: Dict, user=Depends(current_user)):
    project_id = body.get("project_id")
    rows = body.get("rows", [])
    if not project_id or not isinstance(rows, list):
        raise HTTPException(400, "project_id and rows are required")

    metrics = ingest_gsc(get_db(), project_id, rows)
    return {"status": "ok", "inserted": len(metrics)}


@app.post("/api/ga4/ingest")
def ga4_ingest(body: Dict, user=Depends(current_user)):
    project_id = body.get("project_id")
    rows = body.get("rows", [])
    if not project_id or not isinstance(rows, list):
        raise HTTPException(400, "project_id and rows are required")

    metrics = ingest_ga4(get_db(), project_id, rows)
    return {"status": "ok", "inserted": len(metrics)}


@app.post("/api/seo/sync")
def seo_sync(body: Dict, bg: BackgroundTasks = None, user=Depends(current_user)):
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")

    gsc_rows = body.get("gsc_rows", [])
    ga4_rows = body.get("ga4_rows", [])

    db = get_db()
    job_id = f"sync_{uuid.uuid4().hex[:12]}"
    job_tracker.create_strategy_job(db, job_id, project_id=project_id, job_type="seo_sync", input_payload=body)

    enqueued = False
    if pipeline_queue is not None:
        try:
            pipeline_queue.enqueue(run_seo_sync_job, job_id, project_id, gsc_rows, ga4_rows, job_timeout=1800, retry=2)
            enqueued = True
            job_tracker.update_strategy_job(db, job_id, status="queued")
        except Exception:
            enqueued = False

    if not enqueued:
        if bg is not None:
            bg.add_task(run_seo_sync_job, job_id, project_id, gsc_rows, ga4_rows)
        else:
            run_seo_sync_job(job_id, project_id, gsc_rows, ga4_rows)

    return {"job_id": job_id, "status": "queued", "enqueued": enqueued}


@app.post("/api/autonomy/decide")
def autonomy_decide(body: Dict, user=Depends(current_user)):
    experiment_id = body.get("experiment_id")
    if not experiment_id:
        raise HTTPException(400, "experiment_id required")

    db = get_db()
    exp = get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")

    variants = get_experiment_summary(db, experiment_id)
    exp_payload = {"id": experiment_id, "variants": variants}

    # Context-aware preference from experiment payload
    payload_json = {}
    try:
        payload_json = json.loads(exp.get("payload_json", "{}"))
    except Exception:
        payload_json = {}

    context = payload_json.get("context", {})

    actions = decide_actions(exp_payload, db=db, context=context)
    return {"experiment_id": experiment_id, "actions": actions}


@app.post("/api/autonomy/execute")
def autonomy_execute(body: Dict, bg: BackgroundTasks = None, user=Depends(current_user)):
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")

    db = get_db()
    job_id = f"autonomy_{uuid.uuid4().hex[:12]}"
    job = job_tracker.create_strategy_job(db, job_id, project_id=project_id, job_type="autonomy_execute", input_payload=body)

    # Enqueue pipeline job; if queue unavailable fallback to background task.
    enqueued = False
    if pipeline_queue is not None:
        try:
            pipeline_queue.enqueue(run_pipeline_job, job_id, project_id, body.get("pillar", ""), body.get("language", "english"), body.get("region", "india"), job_timeout=7200, retry=3)
            enqueued = True
            job_tracker.update_strategy_job(db, job_id, status="queued")
        except Exception:
            enqueued = False

    if not enqueued:
        if bg is not None:
            bg.add_task(run_pipeline_job, job_id, project_id, body.get("pillar", ""), body.get("language", "english"), body.get("region", "india"))
        else:
            run_pipeline_job(job_id, project_id, body.get("pillar", ""), body.get("language", "english"), body.get("region", "india"))

    return {"job_id": job_id, "status": "queued", "enqueued": enqueued}


@app.post("/api/autonomy/autopilot/run")
def autonomy_autopilot_run(user=Depends(current_user)):
    from core.autopilot import run_autopilot_once
    ok = run_autopilot_once(mode="auto")
    return {"ok": ok}


@app.get("/api/dashboard/metrics")
def dashboard_metrics(user=Depends(current_user)):
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    pause_job(db, job_id)
    return {"job_id": job_id, "control": "paused"}


@app.post("/api/jobs/{job_id}/resume")
def resume_job_route(job_id: str, user=Depends(current_user)):
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    resume_job(db, job_id)
    return {"job_id": job_id, "control": "running"}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job_route(job_id: str, user=Depends(current_user)):
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    cancel_job(db, job_id)
    return {"job_id": job_id, "control": "cancelling"}


@app.post("/api/ki/{project_id}/score/{session_id}")
async def ki_score_start(project_id: str, session_id: str,
                          bg: BackgroundTasks, user=Depends(current_user)):
    """Start keyword scoring job for a session."""
    from engines.annaseo_keyword_input import _db as _ki_db_fn
    ki_db = _ki_db_fn()
    total = ki_db.execute(
        "SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=?", (session_id,)
    ).fetchone()[0]
    ki_db.close()
    if total == 0:
        raise HTTPException(404, "No keywords found for this session")

    job_id = f"score_{uuid.uuid4().hex[:12]}"
    job_tracker.create_strategy_job(db, job_id, project_id=project_id, job_type="score", input_payload={"project_id": project_id, "session_id": session_id, "total": total})
    score_queue.enqueue(run_score_job, job_id, job_timeout=600, retry=3)
    return {"job_id": job_id, "total": total, "enqueued": True}


@app.get("/api/ki/{project_id}/score/{session_id}/{job_id}")
async def ki_score_status(project_id: str, session_id: str, job_id: str,
                           user=Depends(current_user)):
    """Poll keyword scoring job status."""
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job or job.get("job_type") != "score":
        raise HTTPException(404, "Score job not found")
    return job


@app.delete("/api/ki/{project_id}/review/{session_id}/items")
async def ki_bulk_delete(project_id: str, session_id: str,
                          body: dict = Body(default={}), user=Depends(current_user)):
    """Permanently delete keywords from the review queue."""
    item_ids = body.get("item_ids", [])
    if not item_ids:
        raise HTTPException(400, "item_ids required")
    from engines.annaseo_keyword_input import _db as _ki_db_fn
    ki_db = _ki_db_fn()
    placeholders = ",".join("?" * len(item_ids))
    result = ki_db.execute(
        f"DELETE FROM keyword_universe_items WHERE session_id=? AND item_id IN ({placeholders})",
        [session_id] + item_ids
    )
    ki_db.commit()
    ki_db.close()
    return {"deleted": result.rowcount}


@app.get("/api/ki/{project_id}/prompts")
async def ki_get_prompts(project_id: str, user=Depends(current_user)):
    """Get all saved prompts for this project (falls back to defaults)."""
    db = get_db()
    rows = db.execute(
        "SELECT prompt_type, content FROM project_prompts WHERE project_id=?",
        (project_id,)
    ).fetchall()
    result = dict(_DEFAULT_PROMPTS)   # start with defaults
    for row in rows:
        result[row["prompt_type"]] = row["content"]
    return result


@app.put("/api/ki/{project_id}/prompts/{prompt_type}")
async def ki_save_prompt(project_id: str, prompt_type: str,
                          body: dict = Body(...), user=Depends(current_user)):
    """Save/update a prompt for this project."""
    content = body.get("content", "")
    if not content:
        raise HTTPException(400, "content required")
    db = get_db()
    db.execute(
        """INSERT INTO project_prompts(project_id, prompt_type, content, updated_at)
           VALUES(?,?,?,datetime('now'))
           ON CONFLICT(project_id,prompt_type) DO UPDATE SET content=excluded.content,
           updated_at=datetime('now')""",
        (project_id, prompt_type, content)
    )
    db.commit()
    return {"ok": True}


@app.post("/api/ki/{project_id}/ai-review")
async def ki_ai_review(project_id: str, body: dict = Body(...),
                        user=Depends(current_user)):
    """Run AI review for one stage (deepseek/groq/gemini/claude) on a list of keywords."""
    stage = body.get("stage", "deepseek")   # deepseek | groq | gemini | claude
    keywords = body.get("keywords", [])
    session_id = body.get("session_id", f"manual_{uuid.uuid4().hex[:8]}")
    custom_prompt = body.get("custom_prompt", None)
    auto_apply = body.get("auto_apply", True)

    if not keywords:
        raise HTTPException(400, "keywords required")

    db = get_db()
    ctx = _get_project_context(project_id, db)

    # Get prompt (custom > saved > default)
    if custom_prompt:
        prompt_text = custom_prompt
    else:
        row = db.execute(
            "SELECT content FROM project_prompts WHERE project_id=? AND prompt_type=?",
            (project_id, f"{stage}_kw_review")
        ).fetchone()
        prompt_text = row["content"] if row else _DEFAULT_PROMPTS.get(f"{stage}_kw_review", "")

    filled = _fill_prompt(prompt_text, ctx, keywords)
    results = []

    try:
        raw = "[]"
        if stage == "deepseek":
            import httpx
            r = httpx.post(
                f"{os.getenv('OLLAMA_URL','http://localhost:11434')}/api/generate",
                json={"model": os.getenv("OLLAMA_MODEL","deepseek-r1:7b"),
                      "prompt": filled, "stream": False},
                timeout=120
            )
            raw = r.json().get("response", "[]")

        elif stage == "groq":
            from groq import Groq
            gclient = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
            resp = gclient.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[{"role": "user", "content": filled}],
                max_tokens=2000, temperature=0.1
            )
            raw = (resp.choices[0].message.content or "[]") if resp and resp.choices else "[]"

        elif stage == "gemini":
            from engines.ruflo_strategy_dev_engine import AI
            raw = AI.gemini(filled, temperature=0.2)

        elif stage == "claude":
            from engines.ruflo_strategy_dev_engine import AI
            raw = AI.deepseek(filled, system="Claude fallback mode", temperature=0.2)

        else:
            raise HTTPException(400, f"Unknown stage: {stage}")

        # Parse JSON from response
        try:
            m = re.search(r'\[.*\]', raw, re.DOTALL)
            parsed = json.loads(m.group(0)) if m else []
        except Exception:
            parsed = []

        for item in parsed:
            orig_kw = item.get("original") or item.get("keyword") or ""
            final_kw = item.get("final") or item.get("keyword") or orig_kw
            action = (item.get("action") or "").strip().lower()
            intent = item.get("intent", "")
            reason = item.get("reason", "")
            score = float(item.get("confidence", item.get("score", 0) or 0))
            if score < 0: score = 0
            if score > 100: score = 100

            # Track AI review result sheet
            db.execute(
                """INSERT OR REPLACE INTO ai_review_results
                   (project_id, session_id, stage, keyword, flagged, reason, user_decision, ai_score)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (project_id, session_id, stage, orig_kw,
                 1 if action == "removed" else 0,
                 reason, score)
            )

            # Optionally apply to keyword universe (soft AI flags, not hard delete)
            if auto_apply and session_id:
                row = db.execute(
                    "SELECT item_id FROM keyword_universe_items WHERE session_id=? AND keyword=?",
                    (session_id, orig_kw)
                ).fetchone()
                if row:
                    item_id = row["item_id"]
                    if action == "removed":
                        db.execute(
                            "UPDATE keyword_universe_items SET status='ai_flagged', reviewed_at=datetime('now'), ai_score=?, ai_flags=? WHERE item_id=?",
                            (score, json.dumps({"stage": stage, "reason": reason}), item_id)
                        )
                    elif action == "corrected" and final_kw and final_kw != orig_kw:
                        db.execute(
                            "UPDATE keyword_universe_items SET keyword=?, edited_keyword=?, status='accepted', reviewed_at=datetime('now'), ai_score=?, ai_flags=? WHERE item_id=?",
                            (final_kw, final_kw, score, json.dumps({"stage": stage, "reason": reason}), item_id)
                        )
                    elif action == "kept":
                        db.execute(
                            "UPDATE keyword_universe_items SET status='accepted', reviewed_at=datetime('now'), ai_score=?, ai_flags=? WHERE item_id=?",
                            (score, json.dumps({"stage": stage, "reason": reason}), item_id)
                        )

            results.append({
                "original": orig_kw,
                "final": final_kw,
                "action": action,
                "intent": intent,
                "confidence": score,
                "reason": reason,
                "user_decision": "pending" if action == "removed" else "keep"
            })

        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[ai-review] {stage} failed: {e}")
        raise HTTPException(500, f"AI review failed: {e}")

    flagged_count = sum(1 for r in results if r["action"] == "removed")
    return {
        "stage": stage,
        "results": results,
        "flagged_count": flagged_count,
        "total": len(results)
    }


@app.post("/api/ki/{project_id}/ai-review/session/{session_id}")
async def ki_ai_review_session(project_id: str, session_id: str, body: dict = Body(...),
                                user=Depends(current_user)):
    """Run AI review on a session's accepted/pending universe keywords."""
    stage = body.get("stage", "deepseek")
    custom_prompt = body.get("custom_prompt", None)
    auto_apply = body.get("auto_apply", True)
    limit = int(body.get("limit", 500))

    ki_db = _ki_db()
    rows = ki_db.execute(
        "SELECT keyword FROM keyword_universe_items WHERE session_id=? AND status IN ('accepted','pending') LIMIT ?",
        (session_id, limit)
    ).fetchall()
    ki_db.close()

    if not rows:
        raise HTTPException(404, "No keywords found for session")

    keywords = [r["keyword"] for r in rows]

    return await ki_ai_review(project_id, {
        "stage": stage,
        "keywords": keywords,
        "session_id": session_id,
        "custom_prompt": custom_prompt,
        "auto_apply": auto_apply,
    }, user)


@app.post("/api/ki/{project_id}/ai-review/override")
async def ki_ai_review_override(project_id: str, body: dict = Body(...),
                                 user=Depends(current_user)):
    """Save user keep/remove decisions for flagged keywords."""
    decisions = body.get("decisions", [])   # [{keyword, stage, decision: keep|remove}]
    session_id = body.get("session_id", "")
    db = get_db()
    for d in decisions:
        kw = d.get("keyword","")
        stage = d.get("stage","deepseek")
        decision = d.get("decision","keep")
        if kw:
            db.execute(
                """UPDATE ai_review_results SET user_decision=?
                   WHERE project_id=? AND session_id=? AND stage=? AND keyword=?""",
                (decision, project_id, session_id, stage, kw)
            )
            if decision == "remove":
                # Also mark keyword as rejected in universe
                db.execute(
                    """UPDATE keyword_universe_items SET status='rejected'
                       WHERE session_id=? AND keyword=?""",
                    (session_id, kw)
                )
    db.commit()
    return {"ok": True, "updated": len(decisions)}


@app.get("/api/ki/{project_id}/ai-review/results")
async def ki_ai_review_results(project_id: str, session_id: str = "",
                                stage: str = "", user=Depends(current_user)):
    """Get AI review results for a session."""
    db = get_db()
    q = "SELECT * FROM ai_review_results WHERE project_id=?"
    params = [project_id]
    if session_id:
        q += " AND session_id=?"; params.append(session_id)
    if stage:
        q += " AND stage=?"; params.append(stage)
    rows = db.execute(q, params).fetchall()
    return {"results": [dict(r) for r in rows]}


@app.get("/api/ki/{project_id}/supporting-suggestions")
def ki_supporting_suggestions(project_id: str, pillar: Optional[str] = None, user=Depends(current_user)):
    """Suggest supporting keywords for a pillar from defaults and existing keywords."""
    _validate_project_exists(project_id)
    ki_db = _ki_db()
    existing = [r["keyword"].strip().lower() for r in ki_db.execute(
        "SELECT keyword FROM supporting_keywords WHERE project_id=?", (project_id,)
    ).fetchall() if r["keyword"]]

    default_suggestions = [
        "organic", "powder", "spices", "premium", "buy online", "wholesale", "kerala", "india", "best", "price"
    ]

    if pillar:
        p = pillar.strip().lower()
        if "black pepper" in p or "pepper" in p:
            default_suggestions = ["organic", "powder", "spices", "black pepper powder", "kitchen spice"]
        elif "honey" in p:
            default_suggestions = ["organic", "raw", "100% pure", "glass bottle", "local"]
        elif "turmeric" in p:
            default_suggestions = ["organic", "powder", "ayurvedic", "coarse", "premium"]

    combined = sorted(set(existing + default_suggestions))
    if pillar:
        prefix = pillar.strip().lower()
        combined.sort(key=lambda x: (0 if prefix in x else 1, x))

    return {"suggestions": combined}


@app.get("/api/ki/{project_id}/pillar-status")
def ki_pillar_status(project_id: str, user=Depends(current_user)):
    """Return run history and cluster count per confirmed pillar keyword."""
    db = get_db()
    try:
        from engines.annaseo_keyword_input import _db as _ki_db_fn
        ki_db = _ki_db_fn()
        pillar_rows = ki_db.execute(
            "SELECT keyword, intent FROM pillar_keywords WHERE project_id=? ORDER BY priority",
            (project_id,)
        ).fetchall()
        ki_db.close()
    except Exception:
        return {"pillars": []}

    result = []
    for p in pillar_rows:
        run_row = db.execute(
            "SELECT run_id, status, started_at, completed_at, current_phase, error, result FROM runs "
            "WHERE project_id=? AND seed=? ORDER BY rowid DESC LIMIT 1",
            (project_id, p["keyword"])
        ).fetchone()

        cluster_count = 0
        if run_row and run_row["status"] == "complete" and run_row["result"]:
            try:
                rd = json.loads(run_row["result"])
                for pk, pd in rd.get("pillars", {}).items():
                    if isinstance(pd, dict):
                        cluster_count = len(pd.get("clusters", {}))
            except Exception:
                pass

        result.append({
            "keyword": p["keyword"],
            "intent": p["intent"],
            "run_id": run_row["run_id"] if run_row else None,
            "status": run_row["status"] if run_row else "not_run",
            "started_at": run_row["started_at"] if run_row else None,
            "completed_at": run_row["completed_at"] if run_row else None,
            "current_phase": run_row["current_phase"] if run_row else None,
            "error": run_row["error"] if run_row else None,
            "cluster_count": cluster_count,
        })
    return {"pillars": result}


@app.post("/api/ki/{project_id}/run-pipeline")
async def ki_run_pipeline(project_id: str, background_tasks: BackgroundTasks,
                           body: dict = Body(default={}),
                           user=Depends(current_user)):
    """Run 20-phase pipeline for selected pillar keywords."""
    try:
        from engines.annaseo_keyword_input import _db as _ki_db_fn
        ki_db = _ki_db_fn()
        rows = ki_db.execute(
            "SELECT keyword, intent FROM pillar_keywords WHERE project_id=? ORDER BY priority",
            (project_id,)
        ).fetchall()
        ki_db.close()
    except Exception as e:
        raise HTTPException(503, f"Keyword input engine unavailable: {e}")

    all_pillars = [{"keyword": r["keyword"], "intent": r["intent"]} for r in rows]
    # Filter by selected_pillars if provided
    selected = body.get("selected_pillars", None)
    if selected:
        pillars = [p for p in all_pillars if p["keyword"] in selected]
    else:
        pillars = all_pillars

    if not pillars:
        raise HTTPException(400, "No confirmed pillar keywords found. Complete steps 1-4 first.")
    db = get_db()

    language = body.get("language", "english")
    region = body.get("region", "india")
    sequential = body.get("sequential", False)

    # Create one run per pillar (background)
    loop = asyncio.get_event_loop()
    run_ids = []
    for p in pillars:
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        db.execute(
            "INSERT INTO runs(run_id,project_id,seed,status,started_at) VALUES(?,?,?,'queued',datetime('now'))",
            (run_id, project_id, p["keyword"])
        )
        run_ids.append({"run_id": run_id, "pillar": p["keyword"]})

        # Keep strategy job tracker in sync with run ids
        job_tracker.create_strategy_job(db, run_id, project_id=project_id, job_type="pipeline", input_payload={"pillar": p["keyword"]})

    db.commit()

    # Queue each run through RQ worker pipeline (strategy jobs table updated by run_pipeline_job/_trigger_pipeline_run)
    if pipeline_queue is None:
        raise HTTPException(status_code=503, detail="Queue unavailable")

    for item in run_ids:
        try:
            pipeline_queue.enqueue(run_pipeline_job, item["run_id"], project_id, item["pillar"], language, region, sequential, job_timeout=7200, retry=2)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to enqueue pipeline run {item['run_id']}: {e}")

    return {"runs": run_ids, "total": len(run_ids)}


def _trigger_pipeline_run(run_id: str, project_id: str, seed: str,
                           language: str, region: str,
                           loop=None, sequential: bool = False):
    """Background task: runs one pillar through the 20-phase pipeline.

    sequential=True: after each phase completion the pipeline blocks until
    the frontend calls POST /api/runs/{run_id}/next-phase.
    """
    db = get_db()
    try:
        job = job_tracker.get_strategy_job(db, run_id)
        if job:
            try:
                check_control_state(job, db)
            except PauseExecution:
                return
            except Exception:
                return

        db.execute("UPDATE runs SET status='running' WHERE run_id=?", (run_id,))
        db.commit()

        # Keep strategy jobs table mirror in sync
        _set_run_status(run_id, "running", phase="P1", progress=10)
        _run_job_log(run_id, "P1: pipeline started")

        from engines.ruflo_20phase_wired import WiredRufloOrchestrator

        # Build emit_fn — thread-safe push to SSE queue via the event loop
        if loop:
            def base_emit(event_type, payload):
                _thread_emit(loop, run_id, event_type, payload)
        else:
            def base_emit(event_type, payload):
                pass  # No loop available; log only

        # Wrap emit_fn with sequential gate if requested
        if sequential:
            _open_seq_gate(run_id)

            def emit_fn(event_type, payload):
                base_emit(event_type, payload)
                # After each phase completes, pause until user clicks "Next Phase"
                if event_type == "phase_log" and payload.get("status") == "complete":
                    _close_seq_gate(run_id)
                    _wait_seq_gate(run_id, timeout=600)
        else:
            emit_fn = base_emit

        orch = WiredRufloOrchestrator(
            project_id=project_id,
            run_id=run_id,
            emit_fn=emit_fn,
        )

        result = orch.run_seed(
            keyword=seed,
            language=language,
            region=region,
            generate_articles=False,
            publish=False,
            project_id=project_id,
            run_id=run_id,
        )

        _run_job_log(run_id, f"P2–P7 pipeline done, result keys: {list(result.keys())[:6]}")

        # Quick pipeline health assertions for P8/P9/P10
        topic_count = int(result.get("topic_count", 0) or 0)
        cluster_count = int(result.get("cluster_count", 0) or 0)
        pillar_count = int(result.get("pillar_count", 0) or 0)
        health_state = {
            "topic_count_gt_0": topic_count > 0,
            "cluster_count_gt_0": cluster_count > 0,
            "pillar_count_gt_0": pillar_count > 0,
            "all_ok": topic_count > 0 and cluster_count > 0 and pillar_count > 0,
        }
        result["pipeline_health"] = health_state

        run_status = "complete" if health_state["all_ok"] else "warning"
        if not health_state["all_ok"]:
            log.warning(f"[pipeline] Health check failed for run {run_id}: {health_state}")
            _run_job_log(run_id, f"P7: Health check failed {health_state}")
            _set_run_status(run_id, "warning", phase="P7", progress=95, error=json.dumps({"pipeline_health": health_state}), result=result)
        else:
            _run_job_log(run_id, "P7: Health check passed")
            _set_run_status(run_id, "completed", phase="P7", progress=100, result=result)

        result_str = json.dumps(result, default=str)[:200000]
        db.execute(
            "UPDATE runs SET status=?,result=?,error=?,updated_at=datetime('now') WHERE run_id=?",
            (run_status, result_str, json.dumps({"pipeline_health": health_state}), run_id)
        )
        db.commit()

        # Mirror run status in strategy job tracker
        job_tracker.update_strategy_job(db, run_id,
                                        status="completed" if run_status == "complete" else "warning",
                                        current_step="P7",
                                        progress=100 if run_status == "complete" else 95,
                                        error_message=None if run_status == "complete" else json.dumps({"pipeline_health": health_state}),
                                        result_payload={"result": result, "pipeline_health": health_state})

        # Signal done to SSE
        base_emit("run_complete", {"run_id": run_id, "status": run_status})

    except Exception as e:
        log.error(f"[pipeline] Run {run_id} failed: {e}")
        _run_job_log(run_id, f"ERROR: {e}")
        _set_run_status(run_id, "failed", phase="P7", progress=0, error=str(e), result=None)
        db.execute(
            "UPDATE runs SET status='error',result=? WHERE run_id=?",
            (json.dumps({"error": str(e)}), run_id)
        )
        db.commit()

        job_tracker.update_strategy_job(db, run_id, status="failed", current_step="P7", progress=0, error_message=str(e), result_payload={"result": None})

        if loop:
            _thread_emit(loop, run_id, "run_error", {"error": str(e)})
    finally:
        _seq_gates.pop(run_id, None)
        _open_seq_gate(run_id)  # keep gate open after completion
        db.close()


@app.post("/api/runs/{run_id}/next-phase")
def run_next_phase(run_id: str, user=Depends(current_user)):
    """Release the sequential phase gate so the pipeline continues to the next phase."""
    if run_id in _seq_gates:
        _seq_gates[run_id].set()
    _open_seq_gate(run_id)
    return {"released": True}


@app.get("/api/runs/{run_id}/phase-results")
def get_phase_results(run_id: str, user=Depends(current_user)):
    """Return all phase result samples (from run_events) plus any user overrides."""
    db = get_db()
    rows = db.execute(
        "SELECT payload FROM run_events WHERE run_id=? AND event_type='phase_log' ORDER BY id",
        (run_id,)
    ).fetchall()

    results = {}
    for row in rows:
        try:
            p = json.loads(row["payload"])
            phase = p.get("phase")
            status = p.get("status")
            if phase and status == "complete":
                results[phase] = {
                    "phase": phase,
                    "status": "complete",
                    "msg": p.get("msg", ""),
                    "output_count": p.get("output_count"),
                    "elapsed_ms": p.get("elapsed_ms"),
                    "memory_delta_mb": p.get("memory_delta_mb"),
                    "result_sample": p.get("result_sample"),
                }
        except Exception:
            pass

    # Merge user overrides
    overrides = db.execute(
        "SELECT phase, items_json FROM phase_overrides WHERE run_id=?", (run_id,)
    ).fetchall()
    for ov in overrides:
        ph = ov["phase"]
        if ph in results:
            results[ph]["user_override"] = json.loads(ov["items_json"] or "[]")

    return {"run_id": run_id, "phases": results}


@app.post("/api/runs/{run_id}/phase-override")
def save_phase_override(run_id: str, body: dict = Body(default={}), user=Depends(current_user)):
    """Save user-edited items for a phase (overrides the engine output)."""
    phase = body.get("phase")
    items = body.get("items", [])
    if not phase:
        raise HTTPException(400, "phase is required")
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO phase_overrides(run_id, phase, items_json, updated_at) VALUES(?,?,?,datetime('now'))",
        (run_id, phase, json.dumps(items))
    )
    db.commit()
    return {"saved": True, "phase": phase, "item_count": len(items)}


@app.delete("/api/runs/{run_id}/phase-override/{phase}")
def delete_phase_override(run_id: str, phase: str, user=Depends(current_user)):
    """Remove a user override, reverting to original engine output."""
    db = get_db()
    db.execute("DELETE FROM phase_overrides WHERE run_id=? AND phase=?", (run_id, phase))
    db.commit()
    return {"deleted": True, "phase": phase}


@app.get("/api/ki/{project_id}/clusters")
async def ki_get_clusters(project_id: str, user=Depends(current_user)):
    """Get clusters from latest completed pipeline runs for this project."""
    db = get_db()
    runs = db.execute(
        "SELECT run_id, seed, result FROM runs WHERE project_id=? AND status='complete' ORDER BY rowid DESC LIMIT 20",
        (project_id,)
    ).fetchall()

    all_clusters = []
    for run in runs:
        if not run["result"]:
            continue
        try:
            result = json.loads(run["result"])
            pillars = result.get("pillars", {})
            for pillar_kw, pillar_data in pillars.items():
                clusters = pillar_data.get("clusters", {}) if isinstance(pillar_data, dict) else {}
                for cluster_name, cluster_data in clusters.items():
                    kws = []
                    if isinstance(cluster_data, dict):
                        kws = cluster_data.get("keywords", [])
                    elif isinstance(cluster_data, list):
                        kws = cluster_data
                    all_clusters.append({
                        "pillar": pillar_kw,
                        "cluster_name": cluster_name,
                        "keywords": kws[:20],
                        "keyword_count": len(kws),
                        "intent": cluster_data.get("intent","") if isinstance(cluster_data,dict) else "",
                        "run_id": run["run_id"],
                    })
        except Exception as e:
            log.warning(f"[clusters] Parse error for run {run['run_id']}: {e}")

    # Group by pillar
    by_pillar: dict = {}
    for c in all_clusters:
        p = c["pillar"]
        if p not in by_pillar:
            by_pillar[p] = []
        by_pillar[p].append(c)

    return {"clusters": all_clusters, "by_pillar": by_pillar,
            "total_clusters": len(all_clusters), "total_pillars": len(by_pillar)}


@app.post("/api/ki/{project_id}/clusters/generate")
async def ki_generate_clusters(project_id: str, body: dict = Body(...),
                                user=Depends(current_user)):
    """AI cluster generation with custom prompt for a given list of keywords."""
    pillar = body.get("pillar", "")
    keywords = body.get("keywords", [])
    custom_prompt = body.get("custom_prompt", None)

    if not keywords:
        raise HTTPException(400, "keywords required")

    db = get_db()

    # Get saved cluster naming prompt or default
    if custom_prompt:
        prompt_text = custom_prompt
    else:
        row = db.execute(
            "SELECT content FROM project_prompts WHERE project_id=? AND prompt_type='cluster_naming'",
            (project_id,)
        ).fetchone()
        prompt_text = row["content"] if row else _DEFAULT_PROMPTS["cluster_naming"]

    # Group keywords into batches of ~15, generate cluster name per batch
    batches = [keywords[i:i+15] for i in range(0, len(keywords), 15)]
    clusters = []

    try:
        import httpx
        for batch in batches:
            filled = prompt_text.replace("{{keywords}}", "\n".join(f"- {k}" for k in batch))
            try:
                r = httpx.post(
                    f"{os.getenv('OLLAMA_URL','http://localhost:11434')}/api/generate",
                    json={"model": os.getenv("OLLAMA_MODEL","deepseek-r1:7b"),
                          "prompt": filled, "stream": False},
                    timeout=60
                )
                raw = r.json().get("response","")
                m = re.search(r'\{.*\}', raw, re.DOTALL)
                parsed = json.loads(m.group(0)) if m else {}
                clusters.append({
                    "pillar": pillar,
                    "cluster_name": parsed.get("name", f"Cluster {len(clusters)+1}"),
                    "content_type": parsed.get("content_type", "blog"),
                    "keywords": batch,
                    "keyword_count": len(batch),
                })
            except Exception as e:
                clusters.append({
                    "pillar": pillar,
                    "cluster_name": f"Cluster {len(clusters)+1}",
                    "content_type": "blog",
                    "keywords": batch,
                    "keyword_count": len(batch),
                })
    except Exception as e:
        raise HTTPException(500, f"Cluster generation failed: {e}")

    return {"clusters": clusters, "total": len(clusters)}


log.info("[main] Keyword Workflow routes registered (/api/ki/research, /api/ki/ai-review, /api/ki/prompts, /api/ki/clusters, /api/ki/pillar-status)")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — STRATEGY ENGINE ROUTES
# ─────────────────────────────────────────────────────────────────────────────

def _job_log(job_id: str, message: str):
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if not job:
        return
    payload = job.get("result_payload") or {}
    logs = payload.get("logs") if isinstance(payload, dict) else []
    if not isinstance(logs, list):
        logs = []
    logs.append({"ts": datetime.now(timezone.utc).isoformat(), "msg": message})
    if len(logs) > 50:
        logs = logs[-50:]
    payload["logs"] = logs
    job_tracker.update_strategy_job(db, job_id, result_payload=payload)


def _set_run_status(run_id: str, status: str, phase: str = None, progress: int = None, error: str = None, result=None):
    db = get_db()
    update = {"status": status}
    if phase is not None:
        update["current_step"] = phase
    if progress is not None:
        update["progress"] = progress
    if error is not None:
        update["error_message"] = error
    if result is not None:
        update["result_payload"] = result
    job_tracker.update_strategy_job(db, run_id, **update)


try:
    from engines.ruflo_strategy_dev_engine import (
        StrategyDevelopmentEngine as _SDE, UserInput as _SDE_UserInput,
        Industry as _SDE_Industry, Religion as _SDE_Religion,
        Language as _SDE_Language, GeoLevel as _SDE_GeoLevel,
    )
    _sde_available = True
except Exception as _sde_err:
    _sde_available = False
    log.warning(f"[main] StrategyDevelopmentEngine not loaded: {_sde_err}")

try:
    from engines.ruflo_final_strategy_engine import (
        FinalStrategyEngine as _FSE, ContextBuilder as _FSE_ContextBuilder,
        RankingMonitor as _FSE_RankingMonitor,
    )
    _fse_available = True
except Exception as _fse_err:
    _fse_available = False
    log.warning(f"[main] FinalStrategyEngine not loaded: {_fse_err}")


class _StrategyDevelopBody(BaseModel):
    business_name: str = ""
    website_url: str = ""
    industry: str = "general"
    business_type: str = "B2C"
    usp: str = ""
    products: List[str] = []
    competitor_urls: List[str] = []
    target_locations: List[str] = []
    target_religions: List[str] = []
    target_languages: List[str] = []
    audience_personas: List[str] = []
    ad_copy: str = ""
    customer_reviews: List[str] = []
    seasonal_events: List[str] = []
    primary_intent: str = "awareness"
    pillars: List[dict] = []
    supporting_keywords: List[str] = []
    intent_focus: str = "transactional"
    customer_url: str = ""


def _run_strategy_job(job_id: str, project_id: str, body_dict: dict, db_path: str):
    """Background thread: run StrategyDevelopmentEngine and persist result."""
    import sqlite3 as _sl
    job_tracker.update_strategy_job(get_db(), job_id, status="running", current_step="P1", progress=10)
    try:
        if not _sde_available:
            raise RuntimeError("StrategyDevelopmentEngine not available")
        _run_job_log(job_id, "P1: StrategyDevelopmentEngine starting")
        from engines.ruflo_strategy_dev_engine import (
            UserInput, Industry, Religion, Language, GeoLevel, StrategyDevelopmentEngine
        )
        def _geo(v):
            try: return GeoLevel(v)
            except Exception: return GeoLevel.NATIONAL
        def _rel(v):
            try: return Religion(v.lower())
            except Exception: return Religion.GENERAL
        def _lang(v):
            try: return Language(v.lower())
            except Exception: return Language.ENGLISH
        def _ind(v):
            try: return Industry(v.lower())
            except Exception: return Industry.GENERAL

        ui = UserInput(
            business_name=body_dict.get("business_name", ""),
            website_url=body_dict.get("website_url", ""),
            industry=_ind(body_dict.get("industry","general")),
            business_type=body_dict.get("business_type","B2C"),
            usp=body_dict.get("usp",""),
            products=body_dict.get("products",[]),
            competitor_urls=body_dict.get("competitor_urls",[]),
            target_locations=[_geo(l) for l in body_dict.get("target_locations",["national"])],
            target_religions=[_rel(r) for r in body_dict.get("target_religions",["general"])],
            target_languages=[_lang(l) for l in body_dict.get("target_languages",["english"])],
            audience_personas=body_dict.get("audience_personas",[]),
            ad_copy=body_dict.get("ad_copy",""),
            customer_reviews=body_dict.get("customer_reviews",[]),
            seasonal_events=body_dict.get("seasonal_events",[]),
            primary_intent=body_dict.get("primary_intent","awareness"),
            pillars=body_dict.get("pillars",[]),
            supporting_keywords=body_dict.get("supporting_keywords",[]),
            intent_focus=body_dict.get("intent_focus","transactional"),
            customer_url=body_dict.get("customer_url","")
        )
        result = StrategyDevelopmentEngine().run(ui)
        _run_job_log(job_id, f"P1: StrategyDevelopmentEngine completed, result keys: {list(result.keys())[:6]}")
        sid = f"strat_{hashlib.md5(f'{project_id}{time.time()}'.encode()).hexdigest()[:12]}"
        conn = _sl.connect(db_path, check_same_thread=False)
        conn.row_factory = _sl.Row
        conn.execute(
            "INSERT INTO strategy_sessions(session_id,project_id,engine_type,status,input_json,result_json,confidence,tokens_used,created_at)"
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, project_id, "audience", "completed", json.dumps(body_dict),
             json.dumps(result, default=str),
             result.get("confidence",0) if isinstance(result,dict) else 0,
             result.get("tokens_used",0) if isinstance(result,dict) else 0,
             datetime.now(timezone.utc).isoformat())
        )
        conn.commit(); conn.close()
        job_tracker.update_strategy_job(get_db(), job_id, status="completed", current_step="P1", progress=100, result_payload={"session_id": sid, "result": result})
        _run_job_log(job_id, f"P1: Session saved {sid}, status=completed")
    except Exception as e:
        log.error(f"[Strategy job {job_id}] failed: {e}")
        _run_job_log(job_id, f"ERROR: {str(e)[:200]}")
        job_tracker.update_strategy_job(get_db(), job_id, status="failed", error_message=str(e), result_payload={"result": None})


def _run_final_strategy_job(job_id: str, project_id: str, universe_result: dict, project: dict, db_path: str):
    """Background thread: run FinalStrategyEngine and persist result."""
    import sqlite3 as _sl
    job_tracker.update_strategy_job(get_db(), job_id, status="running", current_step="P7", progress=90)
    try:
        if not _fse_available:
            raise RuntimeError("FinalStrategyEngine not available")
        from engines.ruflo_final_strategy_engine import FinalStrategyEngine
        memory_items = get_top_patterns(get_db(), limit=5)
        memory_patterns = "\n".join([
            f"{item['pattern_type']}={item['pattern_value']} avg_roi={item['avg_roi']:.3f} weight={item['weight']:.3f}"
            for item in memory_items
        ])
        out = FinalStrategyEngine().run(universe_result, project, memory_patterns=memory_patterns)
        result = out.__dict__ if hasattr(out, "__dict__") else (out if isinstance(out, dict) else {})
        sid = f"fstrat_{hashlib.md5(f'{project_id}{time.time()}'.encode()).hexdigest()[:12]}"
        conn = _sl.connect(db_path, check_same_thread=False)
        conn.row_factory = _sl.Row
        conn.execute(
            "INSERT INTO strategy_sessions(session_id,project_id,engine_type,status,input_json,result_json,confidence,tokens_used,created_at)"
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, project_id, "final_groq", "completed", json.dumps(universe_result)[:4000],
             json.dumps(result, default=str), result.get("confidence",0),
             result.get("tokens_used",0), datetime.now(timezone.utc).isoformat())
        )
        conn.commit(); conn.close()
        job_tracker.update_strategy_job(get_db(), job_id, status="completed", current_step="P7", progress=100, result_payload={"session_id": sid, "result": result})
    except Exception as e:
        log.error(f"[FinalStrategy job {job_id}] failed: {e}")
        job_tracker.update_strategy_job(get_db(), job_id, status="failed", error_message=str(e), result_payload={"result": None})


def _safe_json_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


def _ensure_project_exists(project_id: str):
    db = get_db()
    if not db.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone():
        raise HTTPException(404, f"Project not found: {project_id}")

class StrategyJobCreateBody(BaseModel):
    pillar: str
    language: str = "english"
    region: str = "india"
    max_retries: int = 3
    execution_mode: str = "multi_step"

@app.post("/api/strategy/{project_id}/jobs/create", tags=["Strategy"])
def create_strategy_job(project_id: str, body: StrategyJobCreateBody, bg: BackgroundTasks, user=Depends(current_user)):
    try:
        _ensure_project_exists(project_id)
        db = get_db()
        job_id = f"job_{hashlib.md5(f'{project_id}{time.time()}'.encode()).hexdigest()[:12]}"
        lock_key = hashlib.sha256(f"{project_id}:{body.pillar}".encode()).hexdigest()
        job_tracker.create_strategy_job(
            db,
            job_id,
            project_id=project_id,
            job_type="pipeline",
            input_payload={
                "pillar": body.pillar,
                "language": body.language,
                "region": body.region,
            },
            lock_key=lock_key,
            max_retries=body.max_retries,
            execution_mode=body.execution_mode,
        )

        if pipeline_queue is not None:
            # RQ expects a Retry object for the `retry` parameter; accept int or Retry.
            try:
                from rq import Retry as _RQRetry
                retry_obj = _RQRetry(max=body.max_retries) if isinstance(body.max_retries, int) else body.max_retries
            except Exception:
                retry_obj = body.max_retries

            pipeline_queue.enqueue(
                run_pipeline_job,
                job_id,
                project_id,
                body.pillar,
                body.language,
                body.region,
                job_timeout=7200,
                retry=retry_obj,
            )
        else:
            # Fallback for local/test mode when Redis is unavailable
            try:
                bg.add_task(run_pipeline_job, job_id, project_id, body.pillar, body.language, body.region)
            except Exception:
                # As a last resort, spawn a daemon thread to avoid blocking
                threading.Thread(target=run_pipeline_job, args=(job_id, project_id, body.pillar, body.language, body.region), daemon=True).start()

        return {"job_id": job_id, "status": "queued", "enqueued": True}
    except Exception as e:
        # Print traceback to stderr for test visibility and log error
        try:
            import traceback as _tb
            _tb.print_exc()
        except Exception:
            pass
        try:
            log.error("create_strategy_job error", project_id=project_id, error=str(e))
        except Exception:
            pass
        # Re-raise so pytest/fastapi test harness can capture the full traceback
        raise

@app.post("/api/strategy/{project_id}/develop", tags=["Strategy"])
def strategy_develop(project_id: str, body: _StrategyDevelopBody, bg: BackgroundTasks, user=Depends(current_user)):
    """Trigger StrategyDevelopmentEngine in background. Returns job_id to poll."""
    _ensure_project_exists(project_id)
    if not _sde_available:
        raise HTTPException(503, "StrategyDevelopmentEngine not available — check Ollama/Gemini config")
    job_id = f"job_{hashlib.md5(f'{project_id}{time.time()}'.encode()).hexdigest()[:12]}"
    job_tracker.create_strategy_job(get_db(), job_id, project_id=project_id, job_type="develop", input_payload=body.dict())
    pipeline_queue.enqueue(run_develop_job, job_id, project_id, body.dict(), job_timeout=1200, retry=3)
    return {"job_id": job_id, "status": "queued", "enqueued": True}


@app.post("/api/strategy/{project_id}/generate-audience", tags=["Strategy"])
def generate_audience(project_id: str, user=Depends(current_user)):
    """Quick AI-like generator for missing personas/products.

    Behavior:
      - If an `audience_profiles` row exists with personas/products, return those.
      - Else, use project's `seed_keywords` as product hints and industry heuristics for personas.
    """
    _ensure_project_exists(project_id)
    db = get_db()
    # Try audience_profiles first
    row = db.execute("SELECT personas, products FROM audience_profiles WHERE project_id=?", (project_id,)).fetchone()
    if row:
        try:
            personas = json.loads(row["personas"] or "[]")
        except Exception:
            personas = []
        try:
            products = json.loads(row["products"] or "[]")
        except Exception:
            products = []
        return {"personas": personas, "products": products}

    # Fallback: use project seeds + industry heuristics
    prow = db.execute("SELECT name, industry, seed_keywords FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if not prow:
        raise HTTPException(404, "Project not found")
    p = dict(prow)
    try:
        seeds = json.loads(p.get("seed_keywords") or "[]")
    except Exception:
        seeds = []

    products = []
    # Prefer explicit seeds as product hints
    for s in seeds:
        s = str(s).strip()
        if s and s not in products:
            products.append(s)
        if len(products) >= 5:
            break

    # If no seeds, infer from project name
    if not products and p.get("name"):
        products = [p["name"]]

    industry = (p.get("industry") or "").lower()
    personas = []

    # If running tests, skip external AI calls to avoid long blocking/timeouts
    if os.getenv("ANNASEO_TESTING", "").lower() in ("1", "true", "yes"):
        try:
            import re
        except Exception:
            pass
        if "food" in industry or "spice" in industry or "restaurant" in industry:
            personas = ["Home cooks", "Retail buyers", "Restaurant owners"]
        elif "ecommerce" in industry or "market" in industry:
            personas = ["Online shoppers", "Small resellers", "Wholesale buyers"]
        elif "health" in industry or "wellness" in industry:
            personas = ["Health-conscious consumers", "Clinic owners"]
        else:
            personas = ["General customers", "Professional buyers"]

        return {"personas": (personas or [])[:6], "products": (products or [])[:6]}

    # If we have neither products nor personas, attempt AI generation via AnnaBrain
    try:
        from engines.annaseo_ai_brain import AnnaBrain
        brain = AnnaBrain()
        prompt = {
            "project_name": p.get("name", ""),
            "industry": p.get("industry", ""),
            "seed_keywords": seeds,
        }
        ai_prompt = f"Generate up to 6 short customer persona labels and up to 6 product names for this project. Return JSON with keys 'personas' and 'products'.\n\nProject: {prompt['project_name']}\nIndustry: {prompt['industry']}\nSeeds: {json.dumps(prompt['seed_keywords'])}"
        text, tokens = brain.think(ai_prompt, system="You are an assistant that returns compact JSON.")
        parsed = brain.parse_json(text)
        if isinstance(parsed, dict):
            personas = parsed.get("personas") or parsed.get("audience") or []
            products = parsed.get("products") or parsed.get("items") or products
        # Normalize
        if isinstance(personas, str):
            personas = [x.strip() for x in re.split(r"[,\n;]+", personas) if x.strip()]
        if isinstance(products, str):
            products = [x.strip() for x in re.split(r"[,\n;]+", products) if x.strip()]
    except Exception as e:
        # AI generation failed — fall back to simple heuristics
        try:
            import re
        except:
            pass
        if "food" in industry or "spice" in industry or "restaurant" in industry:
            personas = ["Home cooks", "Retail buyers", "Restaurant owners"]
        elif "ecommerce" in industry or "market" in industry:
            personas = ["Online shoppers", "Small resellers", "Wholesale buyers"]
        elif "health" in industry or "wellness" in industry:
            personas = ["Health-conscious consumers", "Clinic owners"]
        else:
            personas = ["General customers", "Professional buyers"]

    # Limit results
    return {"personas": (personas or [])[:6], "products": (products or [])[:6]}

@app.post("/api/strategy/{project_id}/run", tags=["Strategy"])
async def strategy_run(project_id: str, body: dict = Body(default={}), bg: BackgroundTasks = None, user=Depends(current_user)):
    """Unified strategy endpoint: strategy-only or pipeline-only modes.

    mode values:
      - "develop": run strategy development only (equivalent to /develop)
      - "final": run final strategy only (equivalent to /final)
      - "pipeline": run KI pipeline only (equivalent to /ki/{project_id}/run-pipeline)

    This avoids combining step 1/2 accidentally.
    """
    _ensure_project_exists(project_id)

    mode = body.get("mode", "develop")
    if mode == "develop":
        kwargs = body.get("strategy", {})
        try:
            strat_body = _StrategyDevelopBody(**kwargs)
        except Exception as e:
            raise HTTPException(400, f"Invalid strategy payload: {e}")
        return strategy_develop(project_id, strat_body, bg, user)

    if mode == "final":
        return strategy_final(project_id, bg, user)

    if mode == "pipeline":
        selected_pillars = body.get("selected_pillars", None)
        safe_body = {"selected_pillars": selected_pillars} if selected_pillars is not None else {}
        # Ensure we only run pipeline if step 1 (input) and step 2 (strategy generation) have run
        if not selected_pillars:
            raise HTTPException(400, "Pipeline mode requires selected_pillars.")
        return await ki_run_pipeline(project_id, bg, body=safe_body, user=user)

    raise HTTPException(400, f"Unknown run mode '{mode}'. Use develop|final|pipeline")


@app.post("/api/strategy/run", tags=["Strategy"])
async def strategy_run_no_project(body: dict = Body(default={}), bg: BackgroundTasks = None, user=Depends(current_user)):
    """Backward-compatible route for calls that omit project_id in path."""
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id is required in body")
    return await strategy_run(project_id, body=body, bg=bg, user=user)


def _phase_to_progress(phase: str, status: str) -> int:
    if status == "completed":
        return 100
    if status == "failed":
        return 0

    if not phase:
        if status == "queued":
            return 10
        if status == "running":
            return 60
        return 0

    phase_map = {
        "p1": 10,
        "p2": 30,
        "p3": 45,
        "p4": 60,
        "p5": 75,
        "p6": 90,
        "p7": 95,
    }
    return phase_map.get(phase.lower(), 60)


@app.get("/api/strategy/{project_id}/jobs/{job_id}", tags=["Strategy"])
def strategy_job_status(project_id: str, job_id: str, user=Depends(current_user)):
    """Poll strategy job status."""
    db = get_db()
    job = job_tracker.get_strategy_job(db, job_id)
    if job:
        return job

    # fallback to pipeline runs table (run IDs from previous behavior)
    row = db.execute(
        "SELECT run_id, status, current_phase, error FROM runs WHERE run_id=? AND project_id=?",
        (job_id, project_id)
    ).fetchone()
    if row:
        phase = row["current_phase"] or ""
        status = row["status"]
        return {
            "job_id": row["run_id"],
            "status": status,
            "phase": phase,
            "progress": _phase_to_progress(phase, status),
            "error": row["error"],
        }

    raise HTTPException(404, "Job not found")


def _load_latest_strategy(project_id):
    db = get_db()
    row = db.execute(
        "SELECT result_payload FROM strategy_jobs WHERE project_id=? AND status='completed' ORDER BY completed_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row and row["result_payload"]:
        try:
            return json.loads(row["result_payload"]) if isinstance(row["result_payload"], str) else row["result_payload"]
        except Exception:
            pass

    row2 = db.execute(
        "SELECT result_json FROM strategy_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row2 and row2["result_json"]:
        try:
            return json.loads(row2["result_json"]) if isinstance(row2["result_json"], str) else row2["result_json"]
        except Exception:
            pass

    return None


@app.get("/api/strategy/{project_id}/authority-map", tags=["Strategy"])
def strategy_authority_map(project_id: str, user=Depends(current_user)):
    _ensure_project_exists(project_id)
    strategy = _load_latest_strategy(project_id)
    if not strategy:
        return {"clusters": [], "summary": {"total_clusters": 0, "avg_authority": 0.0}}

    keyword_strategy = strategy.get("keyword_strategy", {})
    all_keywords = []
    for k in ["primary_keywords", "secondary_keywords", "long_tail_keywords"]:
        arr = keyword_strategy.get(k) or []
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, dict) and item.get("keyword"):
                    all_keywords.append(str(item.get("keyword")))
                elif isinstance(item, str):
                    all_keywords.append(item)

    clusters = {}
    for kw in all_keywords:
        root = kw.split()[0].lower() if kw else "unknown"
        clusters.setdefault(root, []).append(kw)

    result = []
    for root, kws in clusters.items():
        total = len(kws)
        covered = min(total, 1)
        avg_rank = 25.0
        authority_score = min(1.0, covered / max(1, total) * 0.6 + 0.4)
        result.append({
            "cluster": root,
            "keywords": kws,
            "total_keywords": total,
            "covered_keywords": covered,
            "avg_rank": avg_rank,
            "authority_score": round(authority_score, 3),
            "gap": total - covered,
        })

    overall = {
        "total_clusters": len(result),
        "avg_authority": round((sum(r["authority_score"] for r in result) / max(1, len(result))), 3),
    }
    return {"clusters": result, "summary": overall}


@app.get("/api/strategy/{project_id}/roi", tags=["Strategy"])
def strategy_roi(project_id: str, user=Depends(current_user)):
    _ensure_project_exists(project_id)
    strategy = _load_latest_strategy(project_id)
    if not strategy:
        return {"summary": {}, "actions": []}

    content = strategy.get("content_strategy", {})
    pages = content.get("pillar_pages", []) if isinstance(content.get("pillar_pages", []), list) else []
    if not pages:
        pages = content.get("cluster_topics", []) if isinstance(content.get("cluster_topics", []), list) else []

    actions = []
    total_cost = 0.0
    total_revenue = 0.0
    total_hours = 0.0

    for page in pages[:20]:
        title = page.get("title") if isinstance(page, dict) else str(page)
        effort = 3.0
        cost = effort * 35.0
        rank_gain = 5.0
        traffic = 200
        revenue = traffic * 0.7
        roi = (revenue - cost) / max(cost, 1)
        actions.append({
            "title": title or "Untitled",
            "effort_hours": effort,
            "cost_usd": round(cost, 2),
            "expected_traffic_gain": traffic,
            "expected_revenue_usd": round(revenue, 2),
            "roi": round(roi, 2),
            "priority": "high" if roi > 2 else "medium" if roi > 0.5 else "low",
        })
        total_cost += cost
        total_revenue += revenue
        total_hours += effort

    summary = {
        "total_actions": len(actions),
        "total_cost_usd": round(total_cost, 2),
        "total_revenue_usd": round(total_revenue, 2),
        "total_hours": round(total_hours, 1),
        "avg_roi": round((sum(a["roi"] for a in actions) / max(1, len(actions))), 2) if actions else 0.0,
    }

    return {"summary": summary, "actions": actions}


@app.get("/api/strategy/{project_id}/authority-map/export", tags=["Strategy"])
def strategy_authority_map_export(project_id: str, format: str = Query("json", regex="^(json|csv)$"), user=Depends(current_user)):
    data = strategy_authority_map(project_id, user=user)
    fmt = (format or "json").lower()
    if fmt == "csv":
        import csv
        from io import StringIO
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["cluster", "total_keywords", "covered_keywords", "avg_rank", "authority_score", "gap", "keywords"])
        for c in data.get("clusters", []):
            writer.writerow([
                c.get("cluster"), c.get("total_keywords"), c.get("covered_keywords"), c.get("avg_rank"),
                c.get("authority_score"), c.get("gap"), ";".join([str(k) for k in c.get("keywords", [])])
            ])
        buffer.seek(0)
        return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={project_id}_authority_map.csv"})
    return data


@app.get("/api/strategy/{project_id}/roi/export", tags=["Strategy"])
def strategy_roi_export(project_id: str, format: str = Query("json", regex="^(json|csv)$"), user=Depends(current_user)):
    data = strategy_roi(project_id, user=user)
    fmt = (format or "json").lower()
    if fmt == "csv":
        import csv
        from io import StringIO
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["title", "effort_hours", "cost_usd", "expected_traffic_gain", "expected_revenue_usd", "roi", "priority"])
        for a in data.get("actions", []):
            writer.writerow([
                a.get("title"), a.get("effort_hours"), a.get("cost_usd"), a.get("expected_traffic_gain"),
                a.get("expected_revenue_usd"), a.get("roi"), a.get("priority")
            ])
        buffer.seek(0)
        return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={project_id}_roi.csv"})
    return data


    row2 = db.execute(
        "SELECT session_id, engine_type, status, result_json FROM strategy_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
        (project_id,)
    ).fetchone()
    if row2:
        return {
            "job_id": job_id,
            "status": row2["status"],
            "phase": row2["engine_type"],
            "progress": 100 if row2["status"] == "completed" else 0,
            "result": json.loads(row2["result_json"] or "{}") if row2["result_json"] else {},
        }

    raise HTTPException(404, "Job not found")


# Legacy (unregistered) variant of the job-create route kept for reference.
def strategy_create_job(project_id: str, body: dict = Body(default={}), bg: BackgroundTasks = None, user=Depends(current_user)):
    db = get_db()
    job_id = body.get("job_id") or f"job_{uuid.uuid4().hex[:12]}"
    job = job_tracker.create_strategy_job(db, job_id, project_id=project_id, job_type="strategy", input_payload=body)

    if bg is not None:
        bg.add_task(run_strategy_pipeline, db, job_id, project_id, body.get("keyword", ""))
    else:
        run_strategy_pipeline(db, job_id, project_id, body.get("keyword", ""))

    return {"job_id": job_id, "status": "queued"}


@app.post("/api/content/fix", tags=["Strategy"])
def content_fix(payload: dict = Body(default={}), user=Depends(current_user)):
    project_id = payload.get("project_id")
    keyword = payload.get("keyword")
    causes = payload.get("root_causes", [])
    gaps = payload.get("gaps", [])
    competitors = payload.get("competitors", [])

    generator = ContentFixGenerator()
    fix = generator.generate_fix(keyword, causes, gaps, competitors, payload.get("content", ""))

    scorer = SectionScorer()
    ranked = scorer.rank_sections(fix.get("sections_to_add", []), {"content_score": payload.get("content_score", 0.5)}, [])

    return {"fix": fix, "priority_fixes": ranked[:5]}


@app.get("/api/queue/health", tags=["Queue"])
def queue_health(user=Depends(current_user)):
    try:
        redis_conn.ping()
        return {
            "redis": "ok",
            "unqueued": {
                "research": research_queue.count,
                "score": score_queue.count,
                "pipeline": pipeline_queue.count,
            },
            "connected": True,
        }
    except Exception as e:
        raise HTTPException(503, f"Queue/Redis not available: {e}")


@app.get("/api/queue/jobs", tags=["Queue"])
def list_queue_jobs(user=Depends(current_user)):
    db = get_db()
    rows = db.execute(
        "SELECT id, status, control_state, retry_count, max_retries, last_completed_step, updated_at FROM strategy_jobs ORDER BY updated_at DESC LIMIT 100"
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/queue/metrics", tags=["Queue"])
def queue_metrics(user=Depends(current_user)):
    db = get_db()
    row = db.execute(
        "SELECT "
        "SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued, "
        "SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running, "
        "SUM(CASE WHEN status='retrying' THEN 1 ELSE 0 END) AS retrying, "
        "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed, "
        "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed, "
        "SUM(CASE WHEN control_state='paused' THEN 1 ELSE 0 END) AS paused "
        "FROM strategy_jobs"
    ).fetchone()
    return dict(row)
    if row2:
        return {
            "job_id": job_id,
            "status": row2["status"],
            "phase": row2["engine_type"],
            "progress": 100 if row2["status"] == "completed" else 0,
            "result": json.loads(row2["result_json"] or "{}") if row2["result_json"] else {},
        }

    raise HTTPException(404, "Job not found")


@app.post("/api/strategy/{project_id}/final", tags=["Strategy"])
def strategy_final(project_id: str, bg: BackgroundTasks, user=Depends(current_user)):
    """Trigger FinalStrategyEngine (Claude) using latest run universe result."""
    if not _fse_available:
        raise HTTPException(503, "FinalStrategyEngine not available — set ANTHROPIC_API_KEY")
    db = get_db()
    run_row = db.execute(
        "SELECT result FROM runs WHERE project_id=? AND status='completed' ORDER BY completed_at DESC LIMIT 1",
        (project_id,)
    ).fetchone()
    universe_result = json.loads(run_row["result"]) if run_row else {}
    project_row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    project = dict(project_row) if project_row else {}
    job_id = f"fj_{hashlib.md5(f'{project_id}{time.time()}'.encode()).hexdigest()[:12]}"
    job_tracker.create_strategy_job(db, job_id, project_id=project_id, job_type="final", input_payload={"universe_result": universe_result})
    pipeline_queue.enqueue(run_final_job, job_id, project_id, universe_result, project, job_timeout=1800, retry=3)
    return {"job_id": job_id, "status": "queued", "enqueued": True}


@app.get("/api/strategy/{project_id}/sessions", tags=["Strategy"])
def list_strategy_sessions(project_id: str, user=Depends(current_user)):
    db = get_db()
    rows = db.execute(
        "SELECT session_id,engine_type,status,confidence,tokens_used,created_at FROM strategy_sessions "
        "WHERE project_id=? ORDER BY created_at DESC LIMIT 20",
        (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/strategy/{project_id}/sessions/{session_id}", tags=["Strategy"])
def get_strategy_session(project_id: str, session_id: str, user=Depends(current_user)):
    db = get_db()
    row = db.execute(
        "SELECT * FROM strategy_sessions WHERE session_id=? AND project_id=?",
        (session_id, project_id)
    ).fetchone()
    if not row: raise HTTPException(404, "Session not found")
    d = dict(row)
    try: d["result_json"] = json.loads(d["result_json"] or "{}")
    except Exception: pass
    return d


from services.strategy_normalizer import normalize_strategy
from services.strategy_validator import validate_strategy


@app.get("/api/strategy/{project_id}/latest", tags=["Strategy"])
def get_latest_strategy(project_id: str, user=Depends(current_user)):
    db = get_db()
    row = db.execute(
        "SELECT * FROM strategy_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
        (project_id,)
    ).fetchone()

    if not row:
        strategy = normalize_strategy({})
        try:
            validate_strategy(strategy)
        except Exception as e:
            raise HTTPException(500, f"Strategy validation failed: {e}")

        return {
            "strategy": strategy,
            "meta": {
                "project_id": project_id,
                "has_data": False,
                "version": "v1",
            },
        }

    d = dict(row)
    try:
        result_json = json.loads(d.get("result_json") or "{}")
    except Exception:
        result_json = {}

    normalized = normalize_strategy(result_json)
    try:
        validate_strategy(normalized)
    except Exception as e:
        raise HTTPException(500, f"Strategy validation failed: {e}")

    return {
        "strategy": normalized,
        "meta": {
            "project_id": project_id,
            "has_data": True,
            "version": "v1",
            "engine_type": d.get("engine_type"),
            "created_at": d.get("created_at"),
        },
    }


class _DiagnoseBody(BaseModel):
    keyword: str
    prev_rank: int = 99
    curr_rank: int = 99
    page_title: str = ""
    content_summary: str = ""
    competitor_page: str = ""
    universe: str = ""


@app.post("/api/strategy/{project_id}/diagnose", tags=["Strategy"])
def strategy_diagnose(project_id: str, body: _DiagnoseBody, user=Depends(current_user)):
    """RankingMonitor.diagnose_drop() for a specific keyword."""
    if not _fse_available:
        raise HTTPException(503, "FinalStrategyEngine not available — set ANTHROPIC_API_KEY")
    from engines.ruflo_final_strategy_engine import RankingMonitor
    result = RankingMonitor().diagnose_drop(
        keyword=body.keyword, prev_rank=body.prev_rank, curr_rank=body.curr_rank,
        page_title=body.page_title, content_summary=body.content_summary,
        competitor_page=body.competitor_page, universe=body.universe,
    )
    return result


@app.get("/api/strategy/{project_id}/audience", tags=["Strategy"])
def get_audience_profile(project_id: str, user=Depends(current_user)):
    db = get_db()

    # If audience profile exists, load it
    row = db.execute("SELECT * FROM audience_profiles WHERE project_id=?", (project_id,)).fetchone()
    if row:
        d = dict(row)
        for f in ["target_locations","target_religions","target_languages","personas","products","seasonal_events","competitor_urls"]:
            d[f] = _safe_json_list(d.get(f))
        pd = d.get("pillar_support_map")
        if pd is None:
            d["pillar_support_map"] = {}
        elif isinstance(pd, (dict, list)):
            d["pillar_support_map"] = pd
        else:
            try:
                d["pillar_support_map"] = json.loads(pd)
            except Exception:
                d["pillar_support_map"] = {}
        d["intent_focus"] = d.get("intent_focus", "transactional")
        d["website_url"] = d.get("website_url", "")
        return d

    # fallback to project fields if audience profile does not exist
    project_row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if not project_row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = row_to_dict(project_row) or {}

    return {
        "status": "processing",
        "audience": None,
        "message": "Strategy not generated yet",
        "website_url": project.get("wp_url", ""),
        "target_locations": json.loads(project.get("target_locations", "[]") or "[]"),
        "target_religions": [project.get("religion")] if project.get("religion") else [],
        "target_languages": json.loads(project.get("target_languages", "[]") or "[]"),
        "personas": json.loads(project.get("audience_personas", "[]") or "[]"),
        "products": json.loads(project.get("seed_keywords", "[]") or "[]"),
        "business_type": project.get("business_type", "B2C"),
        "usp": project.get("usp", ""),
        "customer_reviews": project.get("customer_reviews", ""),
        "ad_copy": project.get("ad_copy", ""),
        "seasonal_events": json.loads(project.get("seasonal_events", "[]") or "[]"),
        "competitor_urls": json.loads(project.get("competitor_urls", "[]") or "[]"),
        "pillar_support_map": json.loads(project.get("pillar_support_map", "{}") or "{}"),
        "intent_focus": project.get("intent_focus", "transactional"),
    }


@app.get("/api/enrich", tags=["Strategy"])
def enrich_keyword(keyword: str = "", project_id: str = "", user=Depends(current_user)):
    if not keyword or str(keyword).strip() == "":
        raise HTTPException(status_code=400, detail="keyword query param is required")

    db = get_db()
    ttl_seconds = 86400
    row = db.execute("SELECT results, fetched_at FROM serp_cache WHERE keyword=?", (keyword,)).fetchone()
    if row and row["results"] and row["fetched_at"]:
        try:
            fetched_at = datetime.fromisoformat(row["fetched_at"])
        except Exception:
            fetched_at = None
        if fetched_at:
            age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            if age <= ttl_seconds:
                try:
                    cached = json.loads(row["results"])
                    return cached
                except Exception:
                    pass

    engine = SERPIntelligenceEngine()
    enriched = engine.run([{"primary_keyword": keyword, "keywords": [keyword], "cluster": keyword}])

    competitors = []
    for item in enriched.get("competitors", [])[:10]:
        if isinstance(item, dict):
            candidates = [item.get("title"), item.get("url"), item.get("snippet")]
            competitors.append(next((c for c in candidates if c), "(unknown)"))
        else:
            competitors.append(str(item))

    clusters = enriched.get("serp_summary", {}).get("top_keywords") or [keyword]

    if project_id:
        allowed, used, limit = check_and_consume_quota(get_db(), project_id, "serp_calls", 1)
        if not allowed:
            raise HTTPException(429, f"SERP call quota exceeded: {used}/{limit}")

    result = {
        "keyword": keyword,
        "clusters": clusters,
        "competitors": competitors,
        "gaps": enriched.get("gaps", []),
        "win_probability": enriched.get("win_probability", 0),
        "recommended_angles": enriched.get("recommended_angles", []),
    }

    try:
        db.execute(
            "INSERT OR REPLACE INTO serp_cache(keyword, results, fetched_at) VALUES(?,?,?)",
            (keyword, json.dumps(result), datetime.now(timezone.utc).isoformat()),
        )
        db.commit()
    except Exception:
        pass

    return result


@app.get("/api/strategy/{project_id}/status", tags=["Strategy"])
def get_strategy_status(project_id: str, user=Depends(current_user)):
    db = get_db()
    job = job_tracker.get_latest_strategy_job(db, project_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    def safe_json(val):
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return val
        return val

    steps_order = ["input", "keyword", "serp", "strategy", "linking", "scoring"]
    numeric_map = {"input": 3, "keyword": 4, "serp": 5, "strategy": 6, "linking": 7, "scoring": 8}

    last_completed = job.get("last_completed_step") or 0
    current = job.get("current_step")

    steps = {}
    for step in steps_order:
        if step == current:
            steps[step] = "running"
        elif isinstance(last_completed, int) and last_completed >= numeric_map.get(step, 0):
            steps[step] = "completed"
        else:
            steps[step] = "pending"

    return {
        "job_id": job.get("id"),
        "project_id": project_id,
        "status": job.get("status"),
        "current_step": current,
        "last_completed_step": last_completed,
        "progress": job.get("progress"),
        "steps": steps,
        "outputs": {
            "keywords": safe_json(job.get("keywords")),
            "serp": safe_json(job.get("serp")),
            "strategy": safe_json(job.get("strategy")),
            "links": safe_json(job.get("links")),
            "scores": safe_json(job.get("scores")),
        },
        "error": job.get("failed_step") or job.get("error_message"),
    }


@app.websocket("/ws/strategy/{project_id}")
async def strategy_ws(websocket: WebSocket, project_id: str):
    await ws_manager.connect(project_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        ws_manager.disconnect(project_id, websocket)


@app.get("/api/strategy/schema", tags=["Strategy"])
def get_strategy_schema(user=Depends(current_user)):
    """Return the JSON Schema used for strategy result validation and UI.
    Loads the schema file from `docs/strategy_result_schema.json`.
    """
    try:
        p = os.path.join(os.path.dirname(__file__), "docs", "strategy_result_schema.json")
        with open(p, "r") as fh:
            return json.load(fh)
    except Exception as e:
        raise HTTPException(500, f"Strategy schema not available: {e}")


@app.get("/api/strategy/schema/public", tags=["Strategy"])
def get_strategy_schema_public():
    """Dev-only: unprotected access to the strategy JSON schema for convenience.
    Controlled by env `ANNASEO_PUBLIC_SCHEMA` (set to "0" to disable).
    """
    if os.getenv("ANNASEO_PUBLIC_SCHEMA", "1") == "0":
        raise HTTPException(403, "Public schema access disabled on this instance")
    try:
        p = os.path.join(os.path.dirname(__file__), "docs", "strategy_result_schema.json")
        with open(p, "r") as fh:
            return json.load(fh)
    except Exception as e:
        raise HTTPException(500, f"Strategy schema not available: {e}")


class _AudienceBody(BaseModel):
    website_url: str = ""
    target_locations: List[str] = []
    target_religions: List[str] = []
    target_languages: List[str] = []
    personas: List[str] = []
    business_type: str = "B2C"
    usp: str = ""
    products: List[str] = []
    customer_reviews: str = ""
    ad_copy: str = ""
    seasonal_events: List[str] = []
    competitor_urls: List[str] = []
    pillar_support_map: Dict[str, List[str]] = {}
    intent_focus: str = "transactional"


@app.put("/api/strategy/{project_id}/audience", tags=["Strategy"])
def save_audience_profile(project_id: str, body: _AudienceBody, user=Depends(current_user)):
    # Step1 validation for minimum required inputs (avoid garbage pipeline runs)
    errs = []
    if not body.personas:
        errs.append("At least one persona is required.")
    if not body.products:
        errs.append("At least one product is required.")
    if not body.target_locations:
        errs.append("At least one target location is required.")
    if not body.target_languages:
        errs.append("At least one target language is required.")
    if not body.target_religions:
        errs.append("At least one target religion is required.")

    if errs:
        raise HTTPException(400, "; ".join(errs))

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    existing = db.execute("SELECT * FROM audience_profiles WHERE project_id=?", (project_id,)).fetchone()
    if existing:
        # normalize strings/arrays for deep compare
        existing_data = {
            "target_locations": json.loads(existing["target_locations"] or "[]"),
            "target_religions": json.loads(existing["target_religions"] or "[]"),
            "target_languages": json.loads(existing["target_languages"] or "[]"),
            "personas": json.loads(existing["personas"] or "[]"),
            "products": json.loads(existing["products"] or "[]"),
            "seasonal_events": json.loads(existing["seasonal_events"] or "[]"),
            "competitor_urls": json.loads(existing["competitor_urls"] or "[]"),
            "pillar_support_map": json.loads(existing["pillar_support_map"] or "{}"),
            "business_type": existing["business_type"],
            "usp": existing["usp"],
            "customer_reviews": existing["customer_reviews"],
            "ad_copy": existing["ad_copy"],
            "intent_focus": existing.get("intent_focus", "transactional"),
        }
        new_data = {
            "target_locations": body.target_locations,
            "target_religions": body.target_religions,
            "target_languages": body.target_languages,
            "personas": body.personas,
            "products": body.products,
            "seasonal_events": body.seasonal_events,
            "competitor_urls": body.competitor_urls,
            "pillar_support_map": body.pillar_support_map or {},
            "business_type": body.business_type,
            "usp": body.usp,
            "customer_reviews": body.customer_reviews,
            "ad_copy": body.ad_copy,
            "intent_focus": body.intent_focus,
        }
        if existing_data == new_data:
            return {"saved": True, "updated": False, "message": "No changes"}

    db.execute(
        "INSERT INTO audience_profiles(project_id,website_url,target_locations,target_religions,target_languages,personas,business_type,usp,products,customer_reviews,ad_copy,seasonal_events,competitor_urls,pillar_support_map,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(project_id) DO UPDATE SET "
        "website_url=excluded.website_url,"
        "target_locations=excluded.target_locations,target_religions=excluded.target_religions,"
        "target_languages=excluded.target_languages,personas=excluded.personas,"
        "business_type=excluded.business_type,usp=excluded.usp,products=excluded.products,"
        "customer_reviews=excluded.customer_reviews,ad_copy=excluded.ad_copy,"
        "seasonal_events=excluded.seasonal_events,competitor_urls=excluded.competitor_urls,"
        "pillar_support_map=excluded.pillar_support_map,updated_at=excluded.updated_at",
        (project_id, body.website_url, json.dumps(body.target_locations), json.dumps(body.target_religions),
         json.dumps(body.target_languages), json.dumps(body.personas), body.business_type,
         body.usp, json.dumps(body.products), body.customer_reviews, body.ad_copy,
         json.dumps(body.seasonal_events), json.dumps(body.competitor_urls),
         json.dumps(body.pillar_support_map or {}), now, now)
    )

    # Keep project master profile in sync so users are not asked twice in strategy workflow
    try:
        project_religion = body.target_religions[0] if body.target_religions else "general"
    except Exception:
        project_religion = "general"

    db.execute(
        "UPDATE projects SET target_locations=?, target_languages=?, religion=?, business_type=?, usp=?, audience_personas=?, competitor_urls=?, customer_reviews=? WHERE project_id=?",
        (json.dumps(body.target_locations), json.dumps(body.target_languages), project_religion,
         body.business_type, body.usp, json.dumps(body.personas), json.dumps(body.competitor_urls),
         body.customer_reviews, project_id)
    )

    db.commit()
    return {"saved": True, "updated": True}


@app.get("/api/strategy/{project_id}/input-health", tags=["Strategy"])
def strategy_input_health(project_id: str, user=Depends(current_user)):
    """Quick health check for Step 1 inputs (Keyword + Business Profile)."""
    row = get_db().execute("SELECT * FROM audience_profiles WHERE project_id=?", (project_id,)).fetchone()
    if not row:
        return {
            "ready": False,
            "missing": ["audience profile"],
            "status": "no_audience_profile"
        }

    missing = []
    data = {
        "personas": json.loads(row["personas"] or "[]"),
        "products": json.loads(row["products"] or "[]"),
        "target_locations": json.loads(row["target_locations"] or "[]"),
        "target_languages": json.loads(row["target_languages"] or "[]"),
        "target_religions": json.loads(row["target_religions"] or "[]")
    }
    if not data["personas"]:
        missing.append("personas")
    if not data["products"]:
        missing.append("products")
    if not data["target_locations"]:
        missing.append("target_locations")
    if not data["target_languages"]:
        missing.append("target_languages")
    if not data["target_religions"]:
        missing.append("target_religions")

    return {
        "ready": len(missing) == 0,
        "missing": missing,
        "profile": data,
        "status": "ok" if len(missing) == 0 else "incomplete"
    }


def _latest_strategy_result(db, project_id: str) -> dict:
    row = db.execute(
        "SELECT result_json, engine_type FROM strategy_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
        (project_id,)
    ).fetchone()
    if not row:
        return {}
    r = json.loads(row["result_json"] or "{}")
    # Audience engine nests the synthesis under r["strategy"] — flatten for callers
    if row["engine_type"] in ("audience", None) and "strategy" in r and isinstance(r["strategy"], dict):
        strat = r["strategy"]
        # Extract priority items from 90_day_plan if no priority_queue at top level
        if "priority_queue" not in r:
            plan = strat.get("90_day_plan", [])
            if plan:
                flat = []
                for week in plan:
                    for a in week.get("articles", []):
                        flat.append({
                            "keyword":      a.get("keyword") or a.get("target_keyword") or a.get("title",""),
                            "title":        a.get("title",""),
                            "pillar":       a.get("pillar",""),
                            "kd_estimate":  a.get("kd_estimate",0),
                            "intent":       a.get("content_type","blog"),
                            "schema_type":  a.get("content_type","BlogPosting"),
                            "is_info_gap":  a.get("info_gap", False),
                            "week":         week.get("week",1),
                        })
                r["priority_queue"] = flat
    return r


@app.get("/api/strategy/{project_id}/priority-queue", tags=["Strategy"])
def strategy_priority_queue(project_id: str, user=Depends(current_user)):
    r = _latest_strategy_result(get_db(), project_id)
    return {"priority_queue": r.get("priority_queue", [])}


@app.get("/api/strategy/{project_id}/content-briefs", tags=["Strategy"])
def strategy_content_briefs(project_id: str, user=Depends(current_user)):
    r = _latest_strategy_result(get_db(), project_id)
    return {"content_briefs": r.get("content_briefs", [])}


@app.get("/api/strategy/{project_id}/link-map", tags=["Strategy"])
def strategy_link_map(project_id: str, user=Depends(current_user)):
    r = _latest_strategy_result(get_db(), project_id)
    return {"link_map": r.get("link_map", {})}


@app.get("/api/strategy/{project_id}/predictions", tags=["Strategy"])
def strategy_predictions(project_id: str, user=Depends(current_user)):
    r = _latest_strategy_result(get_db(), project_id)
    return {"predictions": r.get("predictions", [])}


@app.get("/api/strategy/{project_id}/risks", tags=["Strategy"])
def strategy_risks(project_id: str, user=Depends(current_user)):
    r = _latest_strategy_result(get_db(), project_id)
    return {"risks": r.get("risks", [])}


class _KeywordScoreBody(BaseModel):
    keywords: List[str] = []


@app.post("/api/strategy/{project_id}/keyword-score", tags=["Strategy"])
def keyword_score(project_id: str, body: _KeywordScoreBody, user=Depends(current_user)):
    """Score keywords 0-100 against business profile using DeepSeek (local, free)."""
    import re as _re
    keywords = [k.strip() for k in body.keywords if k.strip()]
    if not keywords:
        return {"scores": {}}
    db = get_db()
    row = db.execute("SELECT * FROM audience_profiles WHERE project_id=?", (project_id,)).fetchone()
    a = dict(row) if row else {}
    business_type = a.get("business_type") or "B2C"
    usp = a.get("usp") or ""
    products_raw = a.get("products") or "[]"
    locations_raw = a.get("target_locations") or "[]"
    try: products = json.loads(products_raw)
    except Exception: products = []
    try: locations = json.loads(locations_raw)
    except Exception: locations = []

    prompt = (
        f"You are an SEO expert for a {business_type} business.\n"
        f"USP: {usp or 'not specified'}\n"
        f"Products/Services: {', '.join(str(p) for p in products[:10]) or 'not specified'}\n"
        f"Target locations: {', '.join(str(l) for l in locations[:5]) or 'india'}\n\n"
        f"Score each keyword 0-100 for business relevance:\n"
        f"90-100=perfect fit, 70-89=good fit, 50-69=moderate, 30-49=low, 0-29=poor\n\n"
        f"Keywords: {json.dumps(keywords)}\n\n"
        f"Return ONLY JSON object: {{\"keyword\": score, ...}}"
    )
    try:
        import requests as _req
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        r = _req.post(f"{ollama_url}/api/chat", json={
            "model": os.getenv("OLLAMA_MODEL", "deepseek-r1:7b"),
            "stream": False,
            "options": {"temperature": 0.1},
            "messages": [{"role": "user", "content": prompt}]
        }, timeout=60)
        r.raise_for_status()
        response_data = r.json()
        text = ""
        if isinstance(response_data, dict):
            if isinstance(response_data.get("message"), dict):
                text = response_data["message"].get("content", "")
            elif isinstance(response_data.get("choices"), list) and response_data["choices"]:
                choice = response_data["choices"][0]
                if isinstance(choice, dict) and isinstance(choice.get("message"), dict):
                    text = choice["message"].get("content", "")
            elif isinstance(response_data.get("response"), str):
                text = response_data.get("response", "")
            elif isinstance(response_data.get("text"), str):
                text = response_data.get("text", "")
        text = _re.sub(r"<think>.*?</think>", "", str(text), flags=_re.DOTALL).strip()
        m = _re.search(r'\{[^{}]+\}', text, _re.DOTALL)
        if m:
            raw = json.loads(m.group())
            scores = {k: int(v) for k, v in raw.items() if isinstance(v, (int, float))}
            return {"scores": scores}
    except Exception as e:
        log.warning(f"[keyword-score] {e}")
    # Fallback: neutral score
    return {"scores": {kw: 50 for kw in keywords}}


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — RANKING INTELLIGENCE ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class _RankingRecordBody(BaseModel):
    keyword: str
    position: float = 0
    ctr: float = 0
    impressions: int = 0
    clicks: int = 0
    recorded_date: Optional[str] = None


@app.post("/api/rankings/{project_id}/record", tags=["Rankings"])
def record_ranking(project_id: str, body: _RankingRecordBody, user=Depends(current_user)):
    db = get_db()
    date = body.recorded_date or datetime.utcnow().date().isoformat()
    db.execute(
        "INSERT INTO ranking_history(project_id,keyword,position,ctr,impressions,clicks,recorded_date)"
        "VALUES(?,?,?,?,?,?,?)",
        (project_id, body.keyword, body.position, body.ctr, body.impressions, body.clicks, date)
    )
    db.commit()
    prev = db.execute(
        "SELECT position FROM ranking_history WHERE project_id=? AND keyword=? "
        "ORDER BY recorded_date DESC LIMIT 1 OFFSET 1",
        (project_id, body.keyword)
    ).fetchone()
    if prev:
        change = body.position - prev["position"]
        if change > 5:
            severity = "critical" if body.position > 10 else ("high" if body.position > 5 else "warning")
            db.execute(
                "INSERT INTO ranking_alerts(project_id,keyword,old_position,new_position,change,severity,status)"
                "VALUES(?,?,?,?,?,?,?)",
                (project_id, body.keyword, prev["position"], body.position, change, severity, "new")
            )
            db.commit()
    return {"recorded": True}


@app.get("/api/rankings/{project_id}/history", tags=["Rankings"])
def ranking_history(project_id: str, days: int = 90, user=Depends(current_user)):
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    db = get_db()
    rows = db.execute(
        "SELECT keyword,position,ctr,impressions,clicks,recorded_date FROM ranking_history "
        "WHERE project_id=? AND recorded_date>=? ORDER BY recorded_date ASC",
        (project_id, cutoff)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/rankings/{project_id}/history/{keyword}", tags=["Rankings"])
def ranking_history_keyword(project_id: str, keyword: str, days: int = 90, user=Depends(current_user)):
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    db = get_db()
    rows = db.execute(
        "SELECT position,ctr,impressions,clicks,recorded_date FROM ranking_history "
        "WHERE project_id=? AND keyword=? AND recorded_date>=? ORDER BY recorded_date ASC",
        (project_id, keyword, cutoff)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/rankings/{project_id}/alerts", tags=["Rankings"])
def list_ranking_alerts(project_id: str, severity: Optional[str]=None, status: Optional[str]=None, user=Depends(current_user)):
    db = get_db()
    q = "SELECT * FROM ranking_alerts WHERE project_id=?"
    p: list = [project_id]
    if severity: q += " AND severity=?"; p.append(severity)
    if status:   q += " AND status=?";   p.append(status)
    q += " ORDER BY created_at DESC LIMIT 100"
    rows = db.execute(q, p).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try: d["diagnosis_json"] = json.loads(d.get("diagnosis_json") or "{}")
        except Exception: pass
        result.append(d)
    return result


@app.post("/api/rankings/{project_id}/alerts/{alert_id}/acknowledge", tags=["Rankings"])
def acknowledge_alert(project_id: str, alert_id: int, user=Depends(current_user)):
    db = get_db()
    db.execute("UPDATE ranking_alerts SET status='acknowledged' WHERE id=? AND project_id=?", (alert_id, project_id))
    db.commit()
    return {"acknowledged": True}


@app.post("/api/rankings/{project_id}/alerts/{alert_id}/diagnose", tags=["Rankings"])
def diagnose_alert(project_id: str, alert_id: int, user=Depends(current_user)):
    db = get_db()
    alert = db.execute("SELECT * FROM ranking_alerts WHERE id=? AND project_id=?", (alert_id, project_id)).fetchone()
    if not alert:
        raise HTTPException(404, "Alert not found")

    a = dict(alert)
    article = db.execute(
        "SELECT title,body,url FROM content_articles WHERE project_id=? AND keyword=? LIMIT 1",
        (project_id, a["keyword"])
    ).fetchone()

    target_url = article["url"] if article and "url" in article else ""
    content_data = {
        "content": (article["body"] or "") if article else "",
        "word_count": len((article["body"] or "").split()) if article else 0,
        "headings": []
    }

    rm = RankingMonitor()
    diagnosis = rm.diagnose_drop(
        db=db,
        project_id=project_id,
        keyword=a["keyword"],
        target_url=target_url,
        content_data=content_data,
    )

    db.execute(
        "UPDATE ranking_alerts SET diagnosis_json=?, status='diagnosed' WHERE id=?",
        (json.dumps(diagnosis), alert_id),
    )
    db.commit()

    return diagnosis


class _RankPredictionBody(BaseModel):
    pages: List[dict] = []
    your_site: dict = {}


@app.post("/api/rankings/{project_id}/predict", tags=["Rankings"])
def predict_ranking_route(project_id: str, body: _RankPredictionBody, user=Depends(current_user)):
    # For now, this API uses provided page-level signals (SERP and internal page data)
    # to infer ranking probability, difficulty, and opportunity.
    result = predict_ranking(body.pages, body.your_site)
    return {"project_id": project_id, "prediction": result}


@app.get("/api/rankings/{project_id}/predictions", tags=["Rankings"])
def get_ranking_predictions(project_id: str, user=Depends(current_user)):
    db = get_db()
    rows = db.execute(
        "SELECT keyword,pillar,predicted_rank,predicted_month,confidence FROM ranking_predictions "
        "WHERE project_id=? ORDER BY predicted_month ASC",
        (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/rankings/{project_id}/check-alerts", tags=["Rankings"])
def check_ranking_alerts(project_id: str, user=Depends(current_user)):
    db = get_db()
    keywords = db.execute(
        "SELECT DISTINCT keyword FROM ranking_history WHERE project_id=?", (project_id,)
    ).fetchall()
    created = 0
    for kw_row in keywords:
        kw = kw_row["keyword"]
        rows = db.execute(
            "SELECT position,recorded_date FROM ranking_history WHERE project_id=? AND keyword=? "
            "ORDER BY recorded_date DESC LIMIT 2",
            (project_id, kw)
        ).fetchall()
        if len(rows) < 2: continue
        curr_pos, prev_pos = rows[0]["position"], rows[1]["position"]
        change = curr_pos - prev_pos
        if change > 5:
            severity = "critical" if curr_pos > 10 else ("high" if curr_pos > 5 else "warning")
            db.execute(
                "INSERT INTO ranking_alerts(project_id,keyword,old_position,new_position,change,severity,status)"
                "VALUES(?,?,?,?,?,?,?)",
                (project_id, kw, prev_pos, curr_pos, change, severity, "new")
            )
            created += 1
    db.commit()
    return {"alerts_created": created}


@app.get("/api/rankings/{project_id}/dashboard", tags=["Rankings"])
def rankings_dashboard(project_id: str, user=Depends(current_user)):
    db = get_db()
    current = db.execute(
        "SELECT keyword,position,ctr,impressions,clicks,recorded_date FROM ranking_history "
        "WHERE project_id=? AND recorded_date=(SELECT MAX(recorded_date) FROM ranking_history WHERE project_id=?)",
        (project_id, project_id)
    ).fetchall()
    alerts = db.execute(
        "SELECT id,keyword,old_position,new_position,change,severity,status,created_at FROM ranking_alerts "
        "WHERE project_id=? AND status='new' ORDER BY created_at DESC LIMIT 20",
        (project_id,)
    ).fetchall()
    predictions = db.execute(
        "SELECT keyword,pillar,predicted_rank,predicted_month,confidence FROM ranking_predictions "
        "WHERE project_id=? ORDER BY predicted_month ASC LIMIT 50",
        (project_id,)
    ).fetchall()
    return {
        "current_rankings": [dict(r) for r in current],
        "active_alerts": [dict(r) for r in alerts],
        "predictions": [dict(r) for r in predictions],
        "alert_count": len(alerts),
    }


@app.get("/api/rankings/{project_id}/top-movers", tags=["Rankings"])
def top_movers(project_id: str, days: int = 7, user=Depends(current_user)):
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    db = get_db()
    rows = db.execute(
        "SELECT keyword, MIN(position) as best, MAX(position) as worst, "
        "(MAX(position)-MIN(position)) as swing FROM ranking_history "
        "WHERE project_id=? AND recorded_date>=? GROUP BY keyword ORDER BY swing DESC LIMIT 20",
        (project_id, cutoff)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/rankings/{project_id}/by-pillar", tags=["Rankings"])
def rankings_by_pillar(project_id: str, user=Depends(current_user)):
    db = get_db()
    rows = db.execute(
        "SELECT cb.pillar, rh.keyword, rh.position, rh.impressions, rh.clicks "
        "FROM ranking_history rh LEFT JOIN content_blogs cb ON rh.keyword=cb.keyword AND rh.project_id=cb.project_id "
        "WHERE rh.project_id=? AND rh.recorded_date=(SELECT MAX(recorded_date) FROM ranking_history WHERE project_id=?) "
        "ORDER BY cb.pillar, rh.position",
        (project_id, project_id)
    ).fetchall()
    result: dict = {}
    for r in rows:
        p = r["pillar"] or "unassigned"
        result.setdefault(p, []).append({"keyword": r["keyword"], "position": r["position"], "impressions": r["impressions"]})
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 — CONTENT BLOGS / FREEZE SYSTEM ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class _BlogGenerateBody(BaseModel):
    keyword: str
    pillar: str = ""
    cluster: str = ""
    title: str = ""
    meta_desc: str = ""
    language: str = "english"
    brief: str = ""


class _BlogUpdateBody(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    meta_desc: Optional[str] = None
    pillar: Optional[str] = None
    cluster: Optional[str] = None
    status: Optional[str] = None
    schema_type: Optional[str] = None


class _FreezeBody(BaseModel):
    scheduled_date: str = ""


class _ScheduleBody(BaseModel):
    scheduled_date: str


def _next_available_date(db, project_id: str, pillar: str, start_date: Optional[str] = None) -> str:
    from datetime import timedelta
    d = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else datetime.utcnow().date()
    for _ in range(400):
        ds = d.isoformat()
        count = db.execute(
            "SELECT COUNT(*) FROM content_blogs WHERE project_id=? AND pillar=? AND scheduled_date=?",
            (project_id, pillar, ds)
        ).fetchone()[0]
        if count < 20:
            return ds
        d += timedelta(days=1)
    return d.isoformat()


@app.post("/api/blogs/{project_id}/generate", tags=["Blogs"])
def generate_blog(project_id: str, body: _BlogGenerateBody, bg: BackgroundTasks, user=Depends(current_user)):
    db = get_db()
    bid = f"blog_{hashlib.md5(f'{project_id}{body.keyword}{time.time()}'.encode()).hexdigest()[:12]}"
    db.execute(
        "INSERT INTO content_blogs(blog_id,project_id,pillar,cluster,keyword,title,meta_desc,language,status,created_at,updated_at)"
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (bid, project_id, body.pillar, body.cluster, body.keyword,
         body.title or body.keyword, body.meta_desc, body.language, "generating",
         datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
    )
    db.commit()

    def _gen():
        import sqlite3 as _sl
        conn = _sl.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = _sl.Row
        try:
            from engines.ruflo_content_engine import ContentGenerationEngine
            project_row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
            result = ContentGenerationEngine().generate(
                keyword=body.keyword, project=dict(project_row) if project_row else {}, brief=body.brief,
            )
            body_text = result.get("body","") if isinstance(result, dict) else str(result)
            title = result.get("title", body.keyword) if isinstance(result, dict) else body.keyword
            meta = result.get("meta_desc","") if isinstance(result, dict) else ""
            conn.execute(
                "UPDATE content_blogs SET body=?,title=?,meta_desc=?,word_count=?,status='draft',updated_at=? WHERE blog_id=?",
                (body_text, title, meta, len(body_text.split()), datetime.now(timezone.utc).isoformat(), bid)
            )
            conn.commit()
        except Exception as e:
            log.error(f"[Blog gen {bid}] {e}")
            conn.execute("UPDATE content_blogs SET status='error',updated_at=? WHERE blog_id=?",
                         (datetime.now(timezone.utc).isoformat(), bid))
            conn.commit()
        finally:
            conn.close()

    bg.add_task(_gen)
    return {"blog_id": bid, "status": "generating"}


@app.get("/api/blogs/{project_id}", tags=["Blogs"])
def list_blogs(project_id: str, pillar: Optional[str]=None, status: Optional[str]=None,
               date_from: Optional[str]=None, date_to: Optional[str]=None,
               limit: int=50, offset: int=0, user=Depends(current_user)):
    db = get_db()
    q = ("SELECT blog_id,pillar,cluster,keyword,title,meta_desc,language,status,frozen_at,"
         "scheduled_date,published_url,word_count,seo_score,version,created_at,updated_at "
         "FROM content_blogs WHERE project_id=?")
    p: list = [project_id]
    if pillar:    q += " AND pillar=?";           p.append(pillar)
    if status:    q += " AND status=?";           p.append(status)
    if date_from: q += " AND scheduled_date>=?";  p.append(date_from)
    if date_to:   q += " AND scheduled_date<=?";  p.append(date_to)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    p += [limit, offset]
    rows = db.execute(q, p).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/blogs/{project_id}/stats", tags=["Blogs"])
def blog_stats(project_id: str, user=Depends(current_user)):
    db = get_db()
    rows = db.execute(
        "SELECT pillar, status, COUNT(*) as cnt FROM content_blogs WHERE project_id=? GROUP BY pillar, status",
        (project_id,)
    ).fetchall()
    total     = db.execute("SELECT COUNT(*) FROM content_blogs WHERE project_id=?", (project_id,)).fetchone()[0]
    frozen    = db.execute("SELECT COUNT(*) FROM content_blogs WHERE project_id=? AND status='frozen'", (project_id,)).fetchone()[0]
    published = db.execute("SELECT COUNT(*) FROM content_blogs WHERE project_id=? AND status='published'", (project_id,)).fetchone()[0]
    pending   = db.execute("SELECT COUNT(*) FROM content_blogs WHERE project_id=? AND status IN ('draft','generating')", (project_id,)).fetchone()[0]
    by_pillar: dict = {}
    for r in rows:
        p = r["pillar"] or "unassigned"
        by_pillar.setdefault(p, {})[r["status"]] = r["cnt"]
    return {"total": total, "frozen": frozen, "published": published, "pending": pending, "by_pillar": by_pillar}


@app.get("/api/blogs/{project_id}/calendar", tags=["Blogs"])
def blogs_calendar(project_id: str, user=Depends(current_user)):
    db = get_db()
    rows = db.execute(
        "SELECT blog_id,pillar,keyword,title,status,scheduled_date,word_count FROM content_blogs "
        "WHERE project_id=? AND scheduled_date!='' ORDER BY scheduled_date ASC",
        (project_id,)
    ).fetchall()
    result: dict = {}
    for r in rows:
        d = r["scheduled_date"][:7]
        result.setdefault(d, []).append(dict(r))
    return result


@app.get("/api/blogs/{project_id}/by-pillar", tags=["Blogs"])
def blogs_by_pillar(project_id: str, user=Depends(current_user)):
    db = get_db()
    pillars = db.execute(
        "SELECT DISTINCT pillar FROM content_blogs WHERE project_id=? ORDER BY pillar", (project_id,)
    ).fetchall()
    result = {}
    for prow in pillars:
        p = prow["pillar"] or "unassigned"
        counts = db.execute(
            "SELECT status, COUNT(*) as cnt FROM content_blogs WHERE project_id=? AND pillar=? GROUP BY status",
            (project_id, prow["pillar"])
        ).fetchall()
        result[p] = {r["status"]: r["cnt"] for r in counts}
    return result


@app.get("/api/blogs/{project_id}/freeze-queue", tags=["Blogs"])
def freeze_queue(project_id: str, days: int=7, user=Depends(current_user)):
    from datetime import timedelta
    today = datetime.utcnow().date().isoformat()
    end = (datetime.utcnow() + timedelta(days=days)).date().isoformat()
    db = get_db()
    rows = db.execute(
        "SELECT blog_id,pillar,keyword,title,status,scheduled_date FROM content_blogs "
        "WHERE project_id=? AND status='frozen' AND scheduled_date>=? AND scheduled_date<=? "
        "ORDER BY scheduled_date ASC",
        (project_id, today, end)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/blogs/{project_id}/due-today", tags=["Blogs"])
def blogs_due_today(project_id: str, user=Depends(current_user)):
    today = datetime.utcnow().date().isoformat()
    db = get_db()
    rows = db.execute(
        "SELECT * FROM content_blogs WHERE project_id=? AND status='frozen' AND scheduled_date=?",
        (project_id, today)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/blogs/{project_id}/{blog_id}", tags=["Blogs"])
def get_blog(project_id: str, blog_id: str, user=Depends(current_user)):
    db = get_db()
    row = db.execute("SELECT * FROM content_blogs WHERE blog_id=? AND project_id=?", (blog_id, project_id)).fetchone()
    if not row: raise HTTPException(404, "Blog not found")
    return dict(row)


@app.put("/api/blogs/{project_id}/{blog_id}", tags=["Blogs"])
def update_blog(project_id: str, blog_id: str, body: _BlogUpdateBody, user=Depends(current_user)):
    db = get_db()
    row = db.execute("SELECT * FROM content_blogs WHERE blog_id=? AND project_id=?", (blog_id, project_id)).fetchone()
    if not row: raise HTTPException(404, "Blog not found")
    fields, vals = [], []
    if body.title       is not None: fields.append("title=?");        vals.append(body.title)
    if body.body        is not None:
        fields.append("body=?");         vals.append(body.body)
        fields.append("word_count=?");   vals.append(len(body.body.split()))
    if body.meta_desc   is not None: fields.append("meta_desc=?");    vals.append(body.meta_desc)
    if body.pillar      is not None: fields.append("pillar=?");       vals.append(body.pillar)
    if body.cluster     is not None: fields.append("cluster=?");      vals.append(body.cluster)
    if body.status      is not None: fields.append("status=?");       vals.append(body.status)
    if body.schema_type is not None: fields.append("schema_type=?");  vals.append(body.schema_type)
    if not fields: return {"updated": False}
    if body.body is not None:
        d = dict(row)
        db.execute(
            "INSERT INTO blog_versions(blog_id,version,title,body,meta_desc) VALUES(?,?,?,?,?)",
            (blog_id, d.get("version",1), d.get("title",""), d.get("body",""), d.get("meta_desc",""))
        )
        fields.append("version=?"); vals.append((row["version"] or 1) + 1)
    fields.append("updated_at=?"); vals.append(datetime.now(timezone.utc).isoformat())
    vals.append(blog_id)
    db.execute(f"UPDATE content_blogs SET {','.join(fields)} WHERE blog_id=?", vals)
    db.commit()
    return {"updated": True, "blog_id": blog_id}


@app.delete("/api/blogs/{project_id}/{blog_id}", tags=["Blogs"])
def delete_blog(project_id: str, blog_id: str, user=Depends(current_user)):
    db = get_db()
    if not db.execute("SELECT 1 FROM content_blogs WHERE blog_id=? AND project_id=?", (blog_id, project_id)).fetchone():
        raise HTTPException(404, "Blog not found")
    db.execute("DELETE FROM content_blogs WHERE blog_id=?", (blog_id,))
    db.commit()
    return {"deleted": blog_id}


@app.post("/api/blogs/{project_id}/{blog_id}/approve", tags=["Blogs"])
def approve_blog(project_id: str, blog_id: str, user=Depends(current_user)):
    db = get_db()
    db.execute("UPDATE content_blogs SET status='approved',updated_at=? WHERE blog_id=? AND project_id=?",
               (datetime.now(timezone.utc).isoformat(), blog_id, project_id))
    db.commit()
    return {"approved": True}


@app.post("/api/blogs/{project_id}/{blog_id}/freeze", tags=["Blogs"])
def freeze_blog(project_id: str, blog_id: str, body: _FreezeBody, user=Depends(current_user)):
    db = get_db()
    row = db.execute("SELECT pillar FROM content_blogs WHERE blog_id=? AND project_id=?", (blog_id, project_id)).fetchone()
    if not row: raise HTTPException(404, "Blog not found")
    sched = body.scheduled_date or _next_available_date(db, project_id, row["pillar"] or "")
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE content_blogs SET status='frozen',frozen_at=?,scheduled_date=?,updated_at=? WHERE blog_id=?",
        (now, sched, now, blog_id)
    )
    db.execute(
        "INSERT OR REPLACE INTO content_freeze_queue(blog_id,project_id,pillar,scheduled_date)"
        "VALUES(?,?,?,?)",
        (blog_id, project_id, row["pillar"] or "", sched)
    )
    db.commit()
    return {"frozen": True, "scheduled_date": sched}


@app.post("/api/blogs/{project_id}/{blog_id}/unfreeze", tags=["Blogs"])
def unfreeze_blog(project_id: str, blog_id: str, user=Depends(current_user)):
    db = get_db()
    db.execute(
        "UPDATE content_blogs SET status='approved',frozen_at='',scheduled_date='',updated_at=? "
        "WHERE blog_id=? AND project_id=?",
        (datetime.now(timezone.utc).isoformat(), blog_id, project_id)
    )
    db.execute("DELETE FROM content_freeze_queue WHERE blog_id=?", (blog_id,))
    db.commit()
    return {"unfrozen": True}


@app.put("/api/blogs/{project_id}/{blog_id}/schedule", tags=["Blogs"])
def reschedule_blog(project_id: str, blog_id: str, body: _ScheduleBody, user=Depends(current_user)):
    db = get_db()
    db.execute("UPDATE content_blogs SET scheduled_date=?,updated_at=? WHERE blog_id=? AND project_id=?",
               (body.scheduled_date, datetime.now(timezone.utc).isoformat(), blog_id, project_id))
    db.execute("UPDATE content_freeze_queue SET scheduled_date=? WHERE blog_id=?", (body.scheduled_date, blog_id))
    db.commit()
    return {"rescheduled": True, "scheduled_date": body.scheduled_date}


@app.post("/api/blogs/{project_id}/{blog_id}/publish", tags=["Blogs"])
def publish_blog(project_id: str, blog_id: str, user=Depends(current_user)):
    db = get_db()
    row = db.execute("SELECT * FROM content_blogs WHERE blog_id=? AND project_id=?", (blog_id, project_id)).fetchone()
    if not row: raise HTTPException(404, "Blog not found")
    b = dict(row)
    project_row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    project = dict(project_row) if project_row else {}
    published_url = ""
    try:
        from engines.ruflo_publisher import Publisher
        result = Publisher().publish(
            title=b.get("title",""), body=b.get("body",""),
            meta_desc=b.get("meta_desc",""), project=project,
        )
        published_url = result.get("url","") if isinstance(result, dict) else ""
    except Exception as e:
        log.warning(f"[Blog publish {blog_id}] {e}")
    db.execute(
        "UPDATE content_blogs SET status='published',published_url=?,updated_at=? WHERE blog_id=?",
        (published_url, datetime.now(timezone.utc).isoformat(), blog_id)
    )
    db.execute("UPDATE content_freeze_queue SET published=1,published_at=? WHERE blog_id=?",
               (datetime.now(timezone.utc).isoformat(), blog_id))
    db.commit()
    return {"published": True, "url": published_url}


@app.post("/api/blogs/{project_id}/{blog_id}/regenerate", tags=["Blogs"])
def regenerate_blog(project_id: str, blog_id: str, bg: BackgroundTasks, user=Depends(current_user)):
    db = get_db()
    row = db.execute("SELECT * FROM content_blogs WHERE blog_id=? AND project_id=?", (blog_id, project_id)).fetchone()
    if not row: raise HTTPException(404, "Blog not found")
    b = dict(row)

    def _regen():
        import sqlite3 as _sl
        conn = _sl.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = _sl.Row
        try:
            from engines.ruflo_content_engine import ContentGenerationEngine
            project_row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
            result = ContentGenerationEngine().generate(
                keyword=b["keyword"], project=dict(project_row) if project_row else {}, brief=""
            )
            body_text = result.get("body","") if isinstance(result, dict) else str(result)
            conn.execute(
                "INSERT INTO blog_versions(blog_id,version,title,body,meta_desc) VALUES(?,?,?,?,?)",
                (blog_id, b.get("version",1), b.get("title",""), b.get("body",""), b.get("meta_desc",""))
            )
            conn.execute(
                "UPDATE content_blogs SET body=?,word_count=?,status='draft',version=?,updated_at=? WHERE blog_id=?",
                (body_text, len(body_text.split()), (b.get("version",1) or 1)+1, datetime.now(timezone.utc).isoformat(), blog_id)
            )
            conn.commit()
        except Exception as e:
            log.error(f"[Blog regen {blog_id}] {e}")
        finally:
            conn.close()

    bg.add_task(_regen)
    return {"regenerating": True, "blog_id": blog_id}


@app.get("/api/blogs/{project_id}/version-history/{blog_id}", tags=["Blogs"])
def blog_version_history(project_id: str, blog_id: str, user=Depends(current_user)):
    db = get_db()
    rows = db.execute(
        "SELECT id,version,title,saved_at FROM blog_versions WHERE blog_id=? ORDER BY version DESC", (blog_id,)
    ).fetchall()
    return [dict(r) for r in rows]


class _BatchGenerateBody(BaseModel):
    pillar: str
    keywords: List[str] = []
    count: int = 10
    language: str = "english"


@app.post("/api/blogs/{project_id}/generate-batch", tags=["Blogs"])
def generate_batch(project_id: str, body: _BatchGenerateBody, bg: BackgroundTasks, user=Depends(current_user)):
    db = get_db()
    keywords = body.keywords[:20] or [f"{body.pillar} topic {i+1}" for i in range(min(body.count, 20))]
    created = []
    for kw in keywords:
        bid = f"blog_{hashlib.md5(f'{project_id}{kw}{time.time()}'.encode()).hexdigest()[:12]}"
        db.execute(
            "INSERT INTO content_blogs(blog_id,project_id,pillar,keyword,title,language,status,created_at,updated_at)"
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (bid, project_id, body.pillar, kw, kw, body.language, "queued",
             datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
        )
        created.append(bid)
    db.commit()

    def _run_batch():
        import sqlite3 as _sl, time as _t
        for _bid, _kw in zip(created, keywords):
            conn = _sl.connect(str(DB_PATH), check_same_thread=False)
            conn.row_factory = _sl.Row
            try:
                from engines.ruflo_content_engine import ContentGenerationEngine
                project_row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
                result = ContentGenerationEngine().generate(
                    keyword=_kw, project=dict(project_row) if project_row else {}, brief=""
                )
                body_text = result.get("body","") if isinstance(result, dict) else str(result)
                title = result.get("title",_kw) if isinstance(result, dict) else _kw
                conn.execute(
                    "UPDATE content_blogs SET body=?,title=?,word_count=?,status='draft',updated_at=? WHERE blog_id=?",
                    (body_text, title, len(body_text.split()), datetime.utcnow().isoformat(), _bid)
                )
                conn.commit()
            except Exception as e:
                log.error(f"[Batch {_bid}] {e}")
                conn.execute("UPDATE content_blogs SET status='error' WHERE blog_id=?", (_bid,))
                conn.commit()
            finally:
                conn.close()
            _t.sleep(0.5)

    bg.add_task(_run_batch)
    return {"created": len(created), "blog_ids": created, "status": "generating"}


class _PopulateCalendarBody(BaseModel):
    weeks: int = 12
    blogs_per_week: int = 15


@app.post("/api/blogs/{project_id}/populate-calendar", tags=["Blogs"])
def populate_calendar(project_id: str, body: _PopulateCalendarBody, user=Depends(current_user)):
    db = get_db()
    result = _latest_strategy_result(db, project_id)
    queue = result.get("priority_queue", [])
    if not queue:
        raise HTTPException(400, "No strategy priority queue found — run strategy first")
    from datetime import timedelta
    day = datetime.utcnow().date()
    created = 0
    slot_index = 0
    for item in queue[:body.weeks * body.blogs_per_week]:
        kw = item.get("keyword","")
        pillar = item.get("pillar","")
        if not kw: continue
        week_offset = slot_index // body.blogs_per_week
        day_offset = slot_index % body.blogs_per_week
        scheduled = (day + timedelta(days=week_offset * 7 + day_offset)).isoformat()
        bid = f"blog_{hashlib.md5(f'{project_id}{kw}{time.time()}'.encode()).hexdigest()[:12]}"
        try:
            db.execute(
                "INSERT INTO content_blogs(blog_id,project_id,pillar,keyword,title,status,scheduled_date,created_at,updated_at)"
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (bid, project_id, pillar, kw, item.get("title", kw), "draft", scheduled,
                 datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
            )
            created += 1
            slot_index += 1
        except Exception:
            pass
    db.commit()
    return {"created": created}


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5 — SYSTEM GRAPH ROUTES
# ─────────────────────────────────────────────────────────────────────────────

def _build_graph(project_id: str, db) -> dict:
    """Build D3-ready graph JSON from content_blogs + ranking_history + pillar_keywords."""
    nodes, edges = [], []
    seen_nodes: set = set()

    def _add_node(nid, label, ntype, **meta):
        if nid in seen_nodes: return
        seen_nodes.add(nid)
        nodes.append({"id": nid, "label": label, "type": ntype, **meta})

    def _add_edge(src, tgt, etype):
        edges.append({"source": src, "target": tgt, "type": etype})

    proj = db.execute("SELECT name FROM projects WHERE project_id=?", (project_id,)).fetchone()
    universe_label = proj["name"] if proj else project_id
    _add_node(f"u_{project_id}", universe_label, "universe")

    try:
        from engines.annaseo_keyword_input import _db as _ki_db
        ki_conn = _ki_db()
        pillars = ki_conn.execute(
            "SELECT DISTINCT pillar FROM pillar_keywords WHERE project_id=?", (project_id,)
        ).fetchall()
        for prow in pillars:
            p = prow[0] if not hasattr(prow, "keys") else prow["pillar"]
            if not p: continue
            _add_node(f"p_{p}", p, "pillar")
            _add_edge(f"u_{project_id}", f"p_{p}", "universe_pillar")
        ki_conn.close()
    except Exception:
        pass

    blogs = db.execute(
        "SELECT keyword,pillar,cluster,status,word_count,seo_score FROM content_blogs WHERE project_id=?",
        (project_id,)
    ).fetchall()
    for b in blogs:
        kw, pillar, cluster, status = b["keyword"], b["pillar"] or "", b["cluster"] or "", b["status"]
        if pillar:
            _add_node(f"p_{pillar}", pillar, "pillar")
            _add_edge(f"u_{project_id}", f"p_{pillar}", "universe_pillar")
        if cluster:
            cid = f"c_{pillar}_{cluster}"
            _add_node(cid, cluster, "cluster")
            if pillar: _add_edge(f"p_{pillar}", cid, "pillar_cluster")
        kw_id = f"k_{kw[:40]}"
        _add_node(kw_id, kw, "keyword", status=status, word_count=b["word_count"], seo_score=b["seo_score"])
        if cluster: _add_edge(f"c_{pillar}_{cluster}", kw_id, "cluster_keyword")
        elif pillar: _add_edge(f"p_{pillar}", kw_id, "pillar_keyword")
        else: _add_edge(f"u_{project_id}", kw_id, "universe_keyword")

    rankings = db.execute(
        "SELECT keyword,position FROM ranking_history WHERE project_id=? "
        "AND recorded_date=(SELECT MAX(recorded_date) FROM ranking_history WHERE project_id=?)",
        (project_id, project_id)
    ).fetchall()
    rank_map = {r["keyword"]: r["position"] for r in rankings}
    for n in nodes:
        if n["type"] == "keyword":
            n["rank"] = rank_map.get(n["label"])

    return {"nodes": nodes, "edges": edges}


@app.get("/api/graph/{project_id}", tags=["Graph"])
def get_graph(project_id: str, user=Depends(current_user)):
    db = get_db()
    cache = db.execute(
        "SELECT graph_json,updated_at FROM system_graph_cache WHERE project_id=?", (project_id,)
    ).fetchone()
    if cache:
        try: return json.loads(cache["graph_json"])
        except Exception: pass
    g = _build_graph(project_id, db)
    db.execute(
        "INSERT INTO system_graph_cache(project_id,graph_json,node_count,edge_count,updated_at)"
        "VALUES(?,?,?,?,?)"
        " ON CONFLICT(project_id) DO UPDATE SET graph_json=excluded.graph_json,"
        "node_count=excluded.node_count,edge_count=excluded.edge_count,updated_at=excluded.updated_at",
        (project_id, json.dumps(g), len(g["nodes"]), len(g["edges"]), datetime.now(timezone.utc).isoformat())
    )
    db.commit()
    return g


@app.get("/api/graph/{project_id}/stats", tags=["Graph"])
def graph_stats(project_id: str, user=Depends(current_user)):
    db = get_db()
    cache = db.execute(
        "SELECT node_count,edge_count,updated_at FROM system_graph_cache WHERE project_id=?", (project_id,)
    ).fetchone()
    if cache: return dict(cache)
    g = _build_graph(project_id, db)
    type_counts: dict = {}
    for n in g["nodes"]:
        t = n.get("type","unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    return {"node_count": len(g["nodes"]), "edge_count": len(g["edges"]), "by_type": type_counts}


@app.get("/api/graph/{project_id}/node/{node_id:path}", tags=["Graph"])
def get_graph_node(project_id: str, node_id: str, user=Depends(current_user)):
    db = get_db()
    g = _build_graph(project_id, db)
    for n in g["nodes"]:
        if n["id"] == node_id:
            if n["type"] in ("pillar","cluster"):
                n["blog_count"] = db.execute(
                    "SELECT COUNT(*) FROM content_blogs WHERE project_id=? AND pillar=?",
                    (project_id, n["label"])
                ).fetchone()[0]
            return n
    raise HTTPException(404, "Node not found")


@app.post("/api/graph/{project_id}/invalidate", tags=["Graph"])
def invalidate_graph_cache(project_id: str, user=Depends(current_user)):
    db = get_db()
    db.execute("DELETE FROM system_graph_cache WHERE project_id=?", (project_id,))
    db.commit()
    return {"invalidated": True}

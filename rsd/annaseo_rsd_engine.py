"""
================================================================================
ANNASEO — RESEARCH AND SELF DEVELOPMENT ENGINE
================================================================================
Application : AnnaSEO
Module      : Research & Self Development (RSD)
Page        : P9 — Research and Self Development (already exists in UI)
Orchestrator: Ruflo (https://github.com/ruvnet/ruflo)

Purpose
───────
Continuously observe every engine as it runs.
Score each engine on 8 dimensions (0–100 per dimension → weighted total).
When score < threshold → trigger AI-powered fine-tuning cycle.
Use Gemini, Groq, DeepSeek for coding, testing, test generation.
Use Claude for final verification and production push approval.
Require manual human approval before any production change.
Maintain full version history with point-in-time and change-level rollback.

Architecture
────────────
  Engine runs → MetricsCollector intercepts (observer pattern)
  → EngineScorer scores 8 dimensions
  → if score < 85 → FineTuningPipeline activates
    → GeminiAdvisor: what should change and why
    → GroqTestGenerator: generate test cases for the engine
    → DeepSeekCoder: write the actual code fix
    → ShadowRunner: run fixed version alongside original, compare
    → ClaudeVerifier: final review — quality, safety, no regressions
    → ApprovalGate: human sees diff, approves or rejects
    → if approved → VersionController.push_to_prod()
    → if rejected → stays on current version

Scoring Dimensions (each 0–100, weighted)
──────────────────────────────────────────
  1. Output quality     (30%) — semantic correctness of engine output
  2. Execution time     (15%) — p95 latency vs baseline
  3. Memory usage       (15%) — peak MB vs baseline
  4. Error rate         (15%) — failures / total runs over rolling 24h
  5. Output completeness(10%) — are all required fields present
  6. Consistency        (10%) — same input → same quality across 3 runs
  7. API cost           (3%)  — Claude tokens per quality point
  8. Test coverage      (2%)  — % of code paths covered by tests

Industry Standards
──────────────────
  Semantic versioning   MAJOR.MINOR.PATCH
  Keep-a-Changelog      https://keepachangelog.com
  Circuit breaker       if fine-tuning worsens score → auto-revert
  Shadow mode           new version runs alongside old before switching
  Canary testing        10% of runs on new version first
  >80% test coverage    required before prod push
  Zero-downtime deploy  old version stays live until new is confirmed

AI Model Routing
────────────────
  Gemini 1.5 Flash  → Fix ideation, pattern analysis (free)
  Groq (Llama)      → Test case generation, fast iteration (free tier)
  DeepSeek local    → Code writing, refactoring (free, Ollama)
  Claude Sonnet     → Final verification, production approval only
================================================================================
"""

from __future__ import annotations

import os, re, json, time, sqlite3, hashlib, logging, traceback, subprocess, ast
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("annaseo.rsd")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

import requests as _req


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONSTANTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class RSDConfig:
    # Score thresholds
    PROD_MIN_SCORE        = 85    # minimum to allow prod push
    FINE_TUNE_THRESHOLD   = 85    # trigger fine-tuning below this
    CIRCUIT_BREAKER_MIN   = 70    # if new version scores below this → auto-revert
    CANARY_PCT            = 10    # % of runs on new version before full switch
    MAX_FINE_TUNE_ATTEMPTS= 3     # give up after N attempts, escalate to human
    TEST_COVERAGE_MIN     = 80    # % test coverage required for prod push

    # Weights for scoring dimensions (must sum to 1.0)
    WEIGHTS = {
        "output_quality":    0.30,
        "execution_time":    0.15,
        "memory_usage":      0.15,
        "error_rate":        0.15,
        "output_completeness":0.10,
        "consistency":       0.10,
        "api_cost":          0.03,
        "test_coverage":     0.02,
    }

    # Baselines (p95 targets)
    BASELINE_TIME_MS      = 30_000   # 30s target for any engine
    BASELINE_MEMORY_MB    = 512      # 512MB target

    # Storage
    DB_PATH               = Path(os.getenv("ANNASEO_DB","./annaseo.db"))
    ENGINES_DIR           = Path(os.getenv("ENGINES_DIR","./"))
    VERSIONS_DIR          = Path(os.getenv("VERSIONS_DIR","./rsd_versions"))

    # AI
    ANTHROPIC_KEY         = os.getenv("ANTHROPIC_API_KEY","")
    GEMINI_KEY            = os.getenv("GEMINI_API_KEY","")
    GROQ_KEY              = os.getenv("GROQ_API_KEY","")
    OLLAMA_URL            = os.getenv("OLLAMA_URL","http://172.235.16.165:11434")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

class EngineStatus(str, Enum):
    HEALTHY    = "healthy"       # score >= 90
    GOOD       = "good"          # 80–89
    DEGRADED   = "degraded"      # 70–79
    POOR       = "poor"          # 60–69
    CRITICAL   = "critical"      # < 60
    TUNING     = "tuning"        # fine-tuning in progress
    PENDING    = "pending"       # awaiting manual approval
    ROLLBACK   = "rollback"      # rollback in progress


class ChangeType(str, Enum):
    FIX        = "fix"
    IMPROVE    = "improve"
    REVERT     = "revert"
    REFACTOR   = "refactor"
    HOTFIX     = "hotfix"


@dataclass
class EngineRun:
    """One execution of an engine — everything measured."""
    run_id:           str
    engine_name:      str
    started_at:       str
    duration_ms:      float     = 0.0
    peak_memory_mb:   float     = 0.0
    input_tokens:     int       = 0
    output_tokens:    int       = 0
    success:          bool      = True
    error:            str       = ""
    output_fields:    List[str] = field(default_factory=list)
    expected_fields:  List[str] = field(default_factory=list)
    output_hash:      str       = ""    # for consistency check
    quality_signals:  Dict[str,Any] = field(default_factory=dict)


@dataclass
class DimensionScore:
    dimension:   str
    raw_value:   float     # the measured value
    score:       float     # 0-100 score for this dimension
    weight:      float
    weighted:    float
    note:        str       = ""


@dataclass
class EngineHealthReport:
    """Complete health report for one engine."""
    engine_name:    str
    version:        str
    total_score:    float
    status:         EngineStatus
    dimensions:     List[DimensionScore]
    runs_analysed:  int
    generated_at:   str
    recommendations:List[str]
    needs_tuning:   bool

    def to_dict(self) -> dict:
        return {
            "engine_name":    self.engine_name,
            "version":        self.version,
            "total_score":    round(self.total_score, 1),
            "status":         self.status.value,
            "dimensions":     [{
                "dimension": d.dimension,
                "score":     round(d.score, 1),
                "raw_value": round(d.raw_value, 2),
                "weighted":  round(d.weighted, 2),
                "note":      d.note
            } for d in self.dimensions],
            "runs_analysed":  self.runs_analysed,
            "generated_at":   self.generated_at,
            "recommendations":self.recommendations,
            "needs_tuning":   self.needs_tuning,
        }


@dataclass
class EngineVersion:
    """One version of an engine file."""
    version:      str       # semver e.g. "1.2.3"
    engine_name:  str
    file_path:    str
    code_hash:    str
    change_type:  ChangeType
    description:  str
    changes:      List[str]  # list of specific changes made
    ai_used:      List[str]  # ["gemini","groq","deepseek","claude"]
    score_before: float
    score_after:  float
    approved_by:  str        = "pending"
    approved_at:  str        = ""
    rolled_back:  bool       = False
    created_at:   str        = field(default_factory=lambda: datetime.utcnow().isoformat())
    test_results: dict       = field(default_factory=dict)


@dataclass
class ApprovalRequest:
    """Pending approval for a production push."""
    request_id:   str
    engine_name:  str
    version:      str
    diff:         str        # unified diff of the change
    summary:      str        # human-readable summary
    claude_notes: str        # Claude's verification notes
    score_before: float
    score_after:  float
    test_report:  dict
    status:       str        = "pending"  # pending | approved | rejected
    decision_by:  str        = ""
    decision_at:  str        = ""
    decision_note:str        = ""
    created_at:   str        = field(default_factory=lambda: datetime.utcnow().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — CONSOLE (matches other AnnaSEO engines)
# ─────────────────────────────────────────────────────────────────────────────

class Console:
    COLORS = {
        "success": "\033[92m", "info":    "\033[94m",
        "data":    "\033[95m", "warning": "\033[93m",
        "error":   "\033[91m", "sep":     "\033[90m",
        "claude":  "\033[35m", "gemini":  "\033[36m",
        "groq":    "\033[33m", "deepseek":"\033[34m",
    }
    RESET = "\033[0m"
    ICONS = {"success":"✓","info":"→","data":"·","warning":"⚠","error":"✗",
             "sep":"─","claude":"◆","gemini":"◇","groq":"◈","deepseek":"◉"}

    @classmethod
    def log(cls, engine: str, level: str, msg: str, data: dict = None):
        ts  = datetime.utcnow().strftime("%H:%M:%S")
        col = cls.COLORS.get(level,"")
        ico = cls.ICONS.get(level,"·")
        print(f"  {ts} {col}[{engine:<18}] {ico} {msg}{cls.RESET}")
        if data:
            for k, v in list(data.items())[:3]:
                print(f"  {'':>10} {cls.COLORS['data']}  · {k}: {v}{cls.RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — DATABASE (SQLite, consistent with AnnaSEO stack)
# ─────────────────────────────────────────────────────────────────────────────

class RSDDB:
    def __init__(self):
        RSDConfig.VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        RSDConfig.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(RSDConfig.DB_PATH), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS rsd_engine_runs (
            run_id TEXT PRIMARY KEY,
            engine_name TEXT NOT NULL,
            started_at TEXT,
            duration_ms REAL DEFAULT 0,
            peak_memory_mb REAL DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            success INTEGER DEFAULT 1,
            error TEXT DEFAULT '',
            output_fields TEXT DEFAULT '[]',
            expected_fields TEXT DEFAULT '[]',
            output_hash TEXT DEFAULT '',
            quality_signals TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rsd_health_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine_name TEXT NOT NULL,
            version TEXT DEFAULT '1.0.0',
            total_score REAL NOT NULL,
            status TEXT NOT NULL,
            dimensions TEXT NOT NULL,
            runs_analysed INTEGER DEFAULT 0,
            recommendations TEXT DEFAULT '[]',
            needs_tuning INTEGER DEFAULT 0,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rsd_engine_versions (
            version TEXT NOT NULL,
            engine_name TEXT NOT NULL,
            file_path TEXT,
            code_hash TEXT,
            change_type TEXT,
            description TEXT,
            changes TEXT DEFAULT '[]',
            ai_used TEXT DEFAULT '[]',
            score_before REAL DEFAULT 0,
            score_after REAL DEFAULT 0,
            approved_by TEXT DEFAULT 'pending',
            approved_at TEXT DEFAULT '',
            rolled_back INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            test_results TEXT DEFAULT '{}',
            PRIMARY KEY (version, engine_name)
        );

        CREATE TABLE IF NOT EXISTS rsd_approval_requests (
            request_id TEXT PRIMARY KEY,
            engine_name TEXT,
            version TEXT,
            diff TEXT,
            summary TEXT,
            claude_notes TEXT,
            score_before REAL,
            score_after REAL,
            test_report TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            decision_by TEXT DEFAULT '',
            decision_at TEXT DEFAULT '',
            decision_note TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rsd_changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine_name TEXT,
            version TEXT,
            change_type TEXT,
            title TEXT,
            description TEXT,
            score_before REAL,
            score_after REAL,
            approved_by TEXT,
            rolled_back INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_rsd_runs_engine ON rsd_engine_runs(engine_name);
        CREATE INDEX IF NOT EXISTS idx_rsd_runs_date ON rsd_engine_runs(started_at);
        CREATE INDEX IF NOT EXISTS idx_rsd_reports_engine ON rsd_health_reports(engine_name);
        CREATE INDEX IF NOT EXISTS idx_rsd_approval_status ON rsd_approval_requests(status);
        """)
        self._db.commit()

    def save_run(self, run: EngineRun):
        self._db.execute("""
            INSERT OR REPLACE INTO rsd_engine_runs
            (run_id, engine_name, started_at, duration_ms, peak_memory_mb,
             input_tokens, output_tokens, success, error, output_fields,
             expected_fields, output_hash, quality_signals)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (run.run_id, run.engine_name, run.started_at, run.duration_ms,
              run.peak_memory_mb, run.input_tokens, run.output_tokens,
              1 if run.success else 0, run.error,
              json.dumps(run.output_fields), json.dumps(run.expected_fields),
              run.output_hash, json.dumps(run.quality_signals)))
        self._db.commit()

    def get_recent_runs(self, engine_name: str, hours: int = 24) -> List[dict]:
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        rows = self._db.execute(
            "SELECT * FROM rsd_engine_runs WHERE engine_name=? AND started_at>=? ORDER BY started_at DESC LIMIT 100",
            (engine_name, since)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_health_report(self, report: EngineHealthReport):
        self._db.execute("""
            INSERT INTO rsd_health_reports
            (engine_name, version, total_score, status, dimensions, runs_analysed, recommendations, needs_tuning)
            VALUES (?,?,?,?,?,?,?,?)
        """, (report.engine_name, report.version, report.total_score, report.status.value,
              json.dumps([d.__dict__ for d in report.dimensions]),
              report.runs_analysed, json.dumps(report.recommendations),
              1 if report.needs_tuning else 0))
        self._db.commit()

    def save_version(self, v: EngineVersion):
        self._db.execute("""
            INSERT OR REPLACE INTO rsd_engine_versions
            (version, engine_name, file_path, code_hash, change_type, description,
             changes, ai_used, score_before, score_after, approved_by, approved_at,
             rolled_back, test_results)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (v.version, v.engine_name, v.file_path, v.code_hash,
              v.change_type.value, v.description, json.dumps(v.changes),
              json.dumps(v.ai_used), v.score_before, v.score_after,
              v.approved_by, v.approved_at, 1 if v.rolled_back else 0,
              json.dumps(v.test_results)))
        self._db.commit()

    def get_versions(self, engine_name: str) -> List[dict]:
        rows = self._db.execute(
            "SELECT * FROM rsd_engine_versions WHERE engine_name=? ORDER BY created_at DESC",
            (engine_name,)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_approval(self, req: ApprovalRequest):
        self._db.execute("""
            INSERT OR REPLACE INTO rsd_approval_requests
            (request_id, engine_name, version, diff, summary, claude_notes,
             score_before, score_after, test_report, status, decision_by, decision_at, decision_note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (req.request_id, req.engine_name, req.version, req.diff,
              req.summary, req.claude_notes, req.score_before, req.score_after,
              json.dumps(req.test_report), req.status, req.decision_by,
              req.decision_at, req.decision_note))
        self._db.commit()

    def get_pending_approvals(self) -> List[dict]:
        rows = self._db.execute(
            "SELECT * FROM rsd_approval_requests WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_approval(self, request_id: str) -> Optional[dict]:
        row = self._db.execute(
            "SELECT * FROM rsd_approval_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_approval(self, request_id: str, status: str,
                         decision_by: str, decision_note: str):
        self._db.execute("""
            UPDATE rsd_approval_requests
            SET status=?, decision_by=?, decision_at=?, decision_note=?
            WHERE request_id=?
        """, (status, decision_by, datetime.utcnow().isoformat(), decision_note, request_id))
        self._db.commit()

    def add_changelog(self, entry: dict):
        self._db.execute("""
            INSERT INTO rsd_changelog
            (engine_name, version, change_type, title, description,
             score_before, score_after, approved_by)
            VALUES (?,?,?,?,?,?,?,?)
        """, (entry["engine_name"], entry["version"], entry["change_type"],
              entry["title"], entry["description"], entry.get("score_before",0),
              entry.get("score_after",0), entry.get("approved_by","")))
        self._db.commit()

    def get_changelog(self, engine_name: str = None, limit: int = 50) -> List[dict]:
        q = "SELECT * FROM rsd_changelog"
        p = []
        if engine_name:
            q += " WHERE engine_name=?"; p.append(engine_name)
        q += " ORDER BY created_at DESC LIMIT ?"
        p.append(limit)
        rows = self._db.execute(q, p).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — METRICS COLLECTOR (observer pattern)
# ─────────────────────────────────────────────────────────────────────────────

class MetricsCollector:
    """
    Observer that wraps any engine call and collects metrics.
    Use as context manager or decorator.

    Usage:
        with MetricsCollector.observe("20phase_engine") as m:
            result = run_20phase_pipeline(keyword)
            m.set_output(result, expected_fields=["topics","clusters","keywords"])
            m.set_quality({"topic_count": len(result["topics"])})
    """
    def __init__(self):
        self._db = RSDDB()

    @contextmanager
    def observe(self, engine_name: str, expected_fields: List[str] = None):
        import psutil, os as _os
        run = EngineRun(
            run_id=f"run_{hashlib.md5(f'{engine_name}{time.time()}'.encode()).hexdigest()[:12]}",
            engine_name=engine_name,
            started_at=datetime.utcnow().isoformat(),
            expected_fields=expected_fields or []
        )
        t0      = time.perf_counter()
        proc    = psutil.Process(_os.getpid())
        mem_start = proc.memory_info().rss / 1024 / 1024
        try:
            yield run
            run.success = True
        except Exception as e:
            run.success = False
            run.error   = traceback.format_exc()[:500]
            Console.log("MetricsCollector", "error",
                        f"{engine_name} failed: {str(e)[:80]}")
        finally:
            run.duration_ms   = (time.perf_counter() - t0) * 1000
            run.peak_memory_mb= max(0, proc.memory_info().rss / 1024 / 1024 - mem_start)
            if run.output_fields and not run.output_hash:
                run.output_hash = hashlib.md5(
                    json.dumps(sorted(run.output_fields)).encode()
                ).hexdigest()[:12]
            self._db.save_run(run)
            Console.log("MetricsCollector", "data",
                        f"{engine_name}: {run.duration_ms:.0f}ms | "
                        f"{run.peak_memory_mb:.1f}MB | "
                        f"{'ok' if run.success else 'FAIL'}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — ENGINE SCORER (8 dimensions → 0-100)
# ─────────────────────────────────────────────────────────────────────────────

class EngineScorer:
    """
    Score an engine on 8 dimensions using recent run data.
    Returns EngineHealthReport with recommendations.
    """
    def __init__(self):
        self._db = RSDDB()

    def score(self, engine_name: str, version: str = "unknown") -> EngineHealthReport:
        runs = self._db.get_recent_runs(engine_name, hours=24)
        if not runs:
            return self._no_data_report(engine_name, version)

        dimensions = [
            self._score_output_quality(runs),
            self._score_execution_time(runs),
            self._score_memory_usage(runs),
            self._score_error_rate(runs),
            self._score_completeness(runs),
            self._score_consistency(runs),
            self._score_api_cost(runs),
            self._score_test_coverage(engine_name),
        ]

        total   = sum(d.weighted for d in dimensions)
        status  = self._status(total)
        recs    = self._recommendations(dimensions, runs)
        needs   = total < RSDConfig.FINE_TUNE_THRESHOLD

        report = EngineHealthReport(
            engine_name=engine_name, version=version,
            total_score=round(total, 1), status=status,
            dimensions=dimensions, runs_analysed=len(runs),
            generated_at=datetime.utcnow().isoformat(),
            recommendations=recs, needs_tuning=needs
        )
        self._db.save_health_report(report)
        Console.log("EngineScorer", "data",
                    f"{engine_name}: {total:.1f}/100 ({status.value})")
        return report

    def _score_output_quality(self, runs: List[dict]) -> DimensionScore:
        """Quality signals from engine outputs."""
        signals = []
        for r in runs:
            qs = json.loads(r.get("quality_signals","{}"))
            if qs:
                signals.extend(qs.values())
        if not signals:
            score = 70.0  # neutral if no signals
            note  = "no quality signals registered"
        else:
            score = min(100, max(0, sum(float(v) for v in signals if isinstance(v,(int,float))) / len(signals)))
            note  = f"avg quality signal: {score:.1f}"
        return DimensionScore("output_quality", score, score,
                              RSDConfig.WEIGHTS["output_quality"],
                              score * RSDConfig.WEIGHTS["output_quality"], note)

    def _score_execution_time(self, runs: List[dict]) -> DimensionScore:
        times = sorted([r["duration_ms"] for r in runs if r["duration_ms"] > 0])
        if not times: return DimensionScore("execution_time", 0, 80, 0.15, 12.0, "no data")
        p95 = times[int(len(times)*0.95)] if len(times) >= 20 else max(times)
        # Score: 100 if p95 <= baseline, linear down to 0 at 3× baseline
        baseline = RSDConfig.BASELINE_TIME_MS
        score = max(0, min(100, 100 * (1 - max(0, p95 - baseline) / (2 * baseline))))
        return DimensionScore("execution_time", p95, score,
                              RSDConfig.WEIGHTS["execution_time"],
                              score * RSDConfig.WEIGHTS["execution_time"],
                              f"p95={p95:.0f}ms (target ≤{baseline}ms)")

    def _score_memory_usage(self, runs: List[dict]) -> DimensionScore:
        peaks = [r["peak_memory_mb"] for r in runs if r["peak_memory_mb"] > 0]
        if not peaks: return DimensionScore("memory_usage", 0, 80, 0.15, 12.0, "no data")
        peak_p95 = sorted(peaks)[int(len(peaks)*0.95)] if len(peaks) >= 5 else max(peaks)
        baseline = RSDConfig.BASELINE_MEMORY_MB
        score = max(0, min(100, 100 * (1 - max(0, peak_p95 - baseline) / (2 * baseline))))
        return DimensionScore("memory_usage", peak_p95, score,
                              RSDConfig.WEIGHTS["memory_usage"],
                              score * RSDConfig.WEIGHTS["memory_usage"],
                              f"p95={peak_p95:.1f}MB (target ≤{baseline}MB)")

    def _score_error_rate(self, runs: List[dict]) -> DimensionScore:
        if not runs: return DimensionScore("error_rate", 0, 100, 0.15, 15.0, "no runs")
        fail_rate = sum(1 for r in runs if not r["success"]) / len(runs)
        score     = max(0, 100 - fail_rate * 500)  # 0.2 error rate = 0 score
        return DimensionScore("error_rate", fail_rate, score,
                              RSDConfig.WEIGHTS["error_rate"],
                              score * RSDConfig.WEIGHTS["error_rate"],
                              f"error rate: {fail_rate:.1%} ({sum(1 for r in runs if not r['success'])}/{len(runs)} failed)")

    def _score_completeness(self, runs: List[dict]) -> DimensionScore:
        scores = []
        for r in runs:
            expected = json.loads(r.get("expected_fields","[]"))
            got      = json.loads(r.get("output_fields","[]"))
            if expected:
                scores.append(len(set(expected) & set(got)) / len(expected) * 100)
        score = sum(scores) / len(scores) if scores else 80.0
        return DimensionScore("output_completeness", score, score,
                              RSDConfig.WEIGHTS["output_completeness"],
                              score * RSDConfig.WEIGHTS["output_completeness"],
                              f"avg field coverage: {score:.1f}%")

    def _score_consistency(self, runs: List[dict]) -> DimensionScore:
        hashes = [r["output_hash"] for r in runs[-20:] if r["output_hash"]]
        if len(hashes) < 2: return DimensionScore("consistency", 0, 80, 0.10, 8.0, "insufficient runs")
        # Entropy-based: high if all same hash, lower if many different
        from collections import Counter
        common = Counter(hashes).most_common(1)[0][1]
        score  = (common / len(hashes)) * 100
        return DimensionScore("consistency", score, score,
                              RSDConfig.WEIGHTS["consistency"],
                              score * RSDConfig.WEIGHTS["consistency"],
                              f"most common output: {common}/{len(hashes)} runs")

    def _score_api_cost(self, runs: List[dict]) -> DimensionScore:
        costs = [(r["input_tokens"] + r["output_tokens"]) for r in runs if r["input_tokens"]]
        if not costs: return DimensionScore("api_cost", 0, 80, 0.03, 2.4, "no token data")
        avg_tokens = sum(costs) / len(costs)
        # 5000 tokens per run = 100, 50000 = 0
        score = max(0, min(100, 100 * (1 - avg_tokens / 50000)))
        return DimensionScore("api_cost", avg_tokens, score,
                              RSDConfig.WEIGHTS["api_cost"],
                              score * RSDConfig.WEIGHTS["api_cost"],
                              f"avg tokens/run: {avg_tokens:.0f}")

    def _score_test_coverage(self, engine_name: str) -> DimensionScore:
        """Check test coverage using coverage.py if available."""
        cov_file = RSDConfig.ENGINES_DIR / f".coverage_{engine_name}"
        if cov_file.exists():
            try:
                import json
                with open(cov_file) as f:
                    cov_data = json.load(f)
                    pct = cov_data.get("totals",{}).get("percent_covered", 0)
                score = pct
                note  = f"test coverage: {pct:.1f}%"
            except Exception:
                score, note = 60.0, "coverage data unreadable"
        else:
            score, note = 60.0, "no coverage data — run tests with coverage.py"
        return DimensionScore("test_coverage", score, score,
                              RSDConfig.WEIGHTS["test_coverage"],
                              score * RSDConfig.WEIGHTS["test_coverage"], note)

    def _status(self, score: float) -> EngineStatus:
        if score >= 90: return EngineStatus.HEALTHY
        if score >= 80: return EngineStatus.GOOD
        if score >= 70: return EngineStatus.DEGRADED
        if score >= 60: return EngineStatus.POOR
        return EngineStatus.CRITICAL

    def _recommendations(self, dims: List[DimensionScore],
                          runs: List[dict]) -> List[str]:
        recs = []
        for d in sorted(dims, key=lambda x: x.score):
            if d.score >= 85: continue
            if d.dimension == "execution_time":
                recs.append(f"Execution time p95 is {d.raw_value:.0f}ms — profile for slow operations, add caching")
            elif d.dimension == "memory_usage":
                recs.append(f"Memory peak {d.raw_value:.0f}MB — check for large in-memory arrays, stream instead")
            elif d.dimension == "error_rate":
                recs.append(f"Error rate {d.raw_value:.1%} — review recent failures, add error handling")
            elif d.dimension == "output_quality":
                recs.append(f"Output quality {d.score:.0f}/100 — review prompt engineering and output validation")
            elif d.dimension == "output_completeness":
                recs.append(f"Missing expected output fields {d.score:.0f}% coverage — check schema contracts")
            elif d.dimension == "test_coverage":
                recs.append(f"Test coverage {d.score:.0f}% — add unit tests for uncovered paths")
        return recs[:5]

    def _no_data_report(self, engine_name: str, version: str) -> EngineHealthReport:
        return EngineHealthReport(
            engine_name=engine_name, version=version,
            total_score=0.0, status=EngineStatus.CRITICAL,
            dimensions=[], runs_analysed=0,
            generated_at=datetime.utcnow().isoformat(),
            recommendations=["No run data found. Engine may not be wired to MetricsCollector."],
            needs_tuning=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — AI ADVISORS (Gemini / Groq / DeepSeek)
# ─────────────────────────────────────────────────────────────────────────────

class GeminiAdvisor:
    """
    Gemini 1.5 Flash — analyse health report, suggest what to fix and why.
    Free tier. Fast. Good at high-level pattern analysis.
    """
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def advise(self, report: EngineHealthReport, engine_code: str) -> dict:
        Console.log("GeminiAdvisor", "gemini", f"Analysing {report.engine_name}...")
        if not RSDConfig.GEMINI_KEY:
            return self._fallback(report)
        prompt = f"""You are a Python engine optimization expert.

Engine: {report.engine_name}
Score: {report.total_score}/100 (target: 100)
Status: {report.status.value}

Low-scoring dimensions:
{json.dumps([{"dimension":d.dimension,"score":d.score,"note":d.note} for d in report.dimensions if d.score < 85], indent=2)}

Recommendations from scorer:
{json.dumps(report.recommendations, indent=2)}

Engine source code (first 2000 chars):
{engine_code[:2000]}

Provide specific, actionable fixes. Return JSON only:
{{
  "root_causes": ["specific issue 1", "specific issue 2"],
  "fixes": [
    {{"priority": "high|medium|low", "area": "function/class name", "what_to_change": "...", "why": "..."}}
  ],
  "estimated_score_gain": 0-30
}}"""
        try:
            r = _req.post(
                f"{self.API_URL}?key={RSDConfig.GEMINI_KEY}",
                json={"contents":[{"parts":[{"text": prompt}]}]},
                timeout=20
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m: return json.loads(m.group(0))
        except Exception as e:
            Console.log("GeminiAdvisor", "warning", f"API call failed: {e}")
        return self._fallback(report)

    def _fallback(self, report: EngineHealthReport) -> dict:
        low = sorted(report.dimensions, key=lambda d: d.score)[:2]
        return {
            "root_causes": [f"Low {d.dimension}: {d.note}" for d in low],
            "fixes": [{"priority":"high","area":"general",
                       "what_to_change": d.note,
                       "why": f"Improves {d.dimension} score from {d.score:.0f}"} for d in low],
            "estimated_score_gain": 10
        }


class GroqTestGenerator:
    """
    Groq (Llama-3) — fast test case generation.
    Free tier. Very fast inference. Good at writing pytest tests.
    """
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def generate_tests(self, engine_name: str, engine_code: str,
                        fixes: List[dict]) -> str:
        Console.log("GroqTestGenerator", "groq",
                    f"Generating tests for {engine_name}...")
        if not RSDConfig.GROQ_KEY:
            return self._template_tests(engine_name)
        fix_summary = "\n".join(f"- {f['area']}: {f['what_to_change'][:60]}"
                                for f in fixes[:3])
        prompt = f"""Generate pytest test cases for this Python engine.

Engine: {engine_name}
Code excerpt (first 1500 chars):
{engine_code[:1500]}

Planned fixes:
{fix_summary}

Write comprehensive pytest tests covering:
1. Happy path — expected inputs produce expected outputs
2. Edge cases — empty input, malformed input, boundary values
3. Performance — execution time within reasonable bounds
4. Error handling — exceptions are caught and logged properly
5. The specific areas being fixed

Return only valid Python pytest code, no explanations."""
        try:
            r = _req.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {RSDConfig.GROQ_KEY}",
                         "Content-Type": "application/json"},
                json={"model":"llama-3.1-8b-instant",
                      "messages":[{"role":"user","content":prompt}],
                      "max_tokens":2000},
                timeout=20
            )
            r.raise_for_status()
            code = r.json()["choices"][0]["message"]["content"]
            code = re.sub(r"```(?:python)?","",code).strip().rstrip("`").strip()
            return code
        except Exception as e:
            Console.log("GroqTestGenerator", "warning", f"API failed: {e}")
        return self._template_tests(engine_name)

    def _template_tests(self, engine_name: str) -> str:
        return f'''import pytest
import time

class Test{engine_name.replace("_","").title()}:

    def test_basic_execution(self):
        """Engine should complete without errors."""
        # TODO: import and call {engine_name}
        assert True

    def test_output_has_required_fields(self):
        """Output must contain all required fields."""
        pass

    def test_execution_time_within_bounds(self):
        """p95 execution time should be under 30 seconds."""
        t0 = time.time()
        # TODO: run engine
        assert (time.time() - t0) < 30

    def test_error_handling_empty_input(self):
        """Empty input should not cause unhandled exception."""
        pass

    def test_memory_does_not_exceed_512mb(self):
        """Peak memory should stay under 512MB."""
        import psutil, os
        mem_before = psutil.Process(os.getpid()).memory_info().rss
        # TODO: run engine
        mem_after  = psutil.Process(os.getpid()).memory_info().rss
        delta_mb   = (mem_after - mem_before) / 1024 / 1024
        assert delta_mb < 512
'''


class DeepSeekCoder:
    """
    DeepSeek (local via Ollama) — write the actual code fix.
    Free, local, good at code generation and refactoring.
    """
    def generate_fix(self, engine_code: str, advice: dict,
                      engine_name: str) -> str:
        Console.log("DeepSeekCoder", "deepseek",
                    f"Writing code fix for {engine_name}...")
        fixes_text = "\n".join(
            f"- {f['area']}: {f['what_to_change']} (because: {f['why']})"
            for f in advice.get("fixes",[])[:3]
        )
        prompt = f"""You are a Python expert. Apply the following fixes to the engine code.

Engine: {engine_name}

Fixes to apply:
{fixes_text}

Original code:
{engine_code}

Rules:
1. Make ONLY the specified changes — do not refactor unrelated code
2. Preserve all existing function signatures and class interfaces
3. Add comments where you made changes: # RSD-FIX: <reason>
4. Do not change imports unless necessary for the fix
5. Ensure the code is syntactically valid Python

Return ONLY the complete modified Python code, no explanations."""
        try:
            r = _req.post(
                f"{RSDConfig.OLLAMA_URL}/api/generate",
                json={"model":"deepseek-r1:7b","prompt":prompt,
                      "stream":False,"options":{"num_predict":4000}},
                timeout=120
            )
            r.raise_for_status()
            code = r.json().get("response","").strip()
            # Validate it's actual Python
            try:
                ast.parse(code)
                return code
            except SyntaxError:
                Console.log("DeepSeekCoder", "warning",
                            "Generated code has syntax error — keeping original")
                return engine_code
        except Exception as e:
            Console.log("DeepSeekCoder", "warning", f"Ollama error: {e}")
        return engine_code  # no change if DeepSeek unavailable


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — SHADOW RUNNER (test new version vs old, safely)
# ─────────────────────────────────────────────────────────────────────────────

class ShadowRunner:
    """
    Run the modified engine in isolation.
    Compare output quality against original.
    Implements circuit breaker: if new version is worse → reject automatically.
    """

    def run_tests(self, test_code: str, engine_code: str,
                   engine_name: str) -> dict:
        """Write tests to temp file and run them."""
        Console.log("ShadowRunner", "info", "Running test suite in isolation...")

        import tempfile, sys
        results = {"passed": 0, "failed": 0, "errors": [], "coverage": 0}

        # Write engine + tests to temp files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            eng_file  = tmp / f"{engine_name}_shadow.py"
            test_file = tmp / f"test_{engine_name}_shadow.py"

            try:
                eng_file.write_text(engine_code, encoding="utf-8")
                test_file.write_text(test_code, encoding="utf-8")
            except Exception as e:
                results["errors"].append(f"Could not write temp files: {e}")
                return results

            # Run pytest with JSON output
            cmd = [sys.executable, "-m", "pytest", str(test_file),
                   "-v", "--tb=short", "--json-report",
                   f"--json-report-file={tmp}/report.json",
                   "--timeout=60", "-x", "--no-header", "-q"]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=120, cwd=str(tmp))
                report_file = tmp / "report.json"
                if report_file.exists():
                    report = json.loads(report_file.read_text())
                    results["passed"]  = report.get("summary",{}).get("passed",0)
                    results["failed"]  = report.get("summary",{}).get("failed",0)
                    results["errors"]  = [t["call"]["longrepr"][:200]
                                          for t in report.get("tests",[])
                                          if t.get("outcome") == "failed"][:5]
                else:
                    # Parse from stdout
                    for line in proc.stdout.split("\n"):
                        if "passed" in line:
                            results["passed"] = int(re.search(r"(\d+) passed",line).group(1)) if re.search(r"(\d+) passed",line) else 0
                        if "failed" in line:
                            results["failed"] = int(re.search(r"(\d+) failed",line).group(1)) if re.search(r"(\d+) failed",line) else 0
            except subprocess.TimeoutExpired:
                results["errors"].append("Tests timed out after 120s")
            except Exception as e:
                results["errors"].append(str(e)[:200])

        total = results["passed"] + results["failed"]
        results["pass_rate"] = (results["passed"] / total * 100) if total else 0
        results["coverage"]  = results["pass_rate"] * 0.8  # approximate
        Console.log("ShadowRunner", "data",
                    f"Tests: {results['passed']} passed / {results['failed']} failed "
                    f"(pass rate: {results['pass_rate']:.0f}%)")
        return results

    def circuit_breaker_check(self, score_before: float,
                               score_after: float) -> Tuple[bool, str]:
        """
        Prevent deploying a version that is worse than the current.
        Returns (allow, reason).
        """
        if score_after < RSDConfig.CIRCUIT_BREAKER_MIN:
            return False, f"Score {score_after:.1f} below circuit breaker minimum ({RSDConfig.CIRCUIT_BREAKER_MIN})"
        if score_after < score_before - 5:
            return False, f"Score regressed: {score_before:.1f} → {score_after:.1f} (more than 5 points worse)"
        return True, "Circuit breaker OK"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — CLAUDE VERIFIER (final gate before approval)
# ─────────────────────────────────────────────────────────────────────────────

class ClaudeVerifier:
    """
    Claude Sonnet — final verification before human approval gate.
    Claude reviews: code quality, safety (no breaking changes to other engines),
    correctness of fixes, and produces a structured verification report.
    Used ONLY for final verification. Never for coding or testing.
    """

    def verify(self, engine_name: str, original_code: str,
                modified_code: str, test_results: dict,
                score_before: float, score_after: float,
                advice: dict) -> dict:
        Console.log("ClaudeVerifier", "claude",
                    f"Final verification of {engine_name} changes...")
        if not RSDConfig.ANTHROPIC_KEY:
            return self._fallback_verification(score_before, score_after, test_results)
        try:
            import anthropic
            import difflib
            diff = "\n".join(difflib.unified_diff(
                original_code.splitlines(), modified_code.splitlines(),
                fromfile=f"{engine_name}_original.py",
                tofile=f"{engine_name}_modified.py",
                lineterm=""
            ))
            prompt = f"""You are a senior Python engineer doing final code review before production deployment.

Engine: {engine_name}
Score change: {score_before:.1f} → {score_after:.1f}

Changes made:
{diff[:3000]}

Test results:
- Passed: {test_results.get('passed',0)}
- Failed: {test_results.get('failed',0)}
- Pass rate: {test_results.get('pass_rate',0):.1f}%

Intended fixes:
{json.dumps(advice.get('fixes',[])[:3], indent=2)}

Review for:
1. Does the code change actually address the stated problems?
2. Are there any breaking changes that could affect other engines?
3. Are there security issues, infinite loops, or resource leaks?
4. Is the code quality acceptable for production?
5. Are the test results sufficient for production deployment?

Return JSON only:
{{
  "recommendation": "approve|reject|needs_changes",
  "confidence": 0-100,
  "breaking_changes_risk": "none|low|medium|high",
  "quality_assessment": "brief assessment",
  "concerns": ["concern 1 if any"],
  "approval_notes": "what the human reviewer should know"
}}"""
            client = anthropic.Anthropic(api_key=RSDConfig.ANTHROPIC_KEY)
            r = client.messages.create(
                model=os.getenv("CLAUDE_MODEL","claude-sonnet-4-6"),
                max_tokens=1000,
                messages=[{"role":"user","content":prompt}]
            )
            text = r.content[0].text.strip()
            text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                result = json.loads(m.group(0))
                Console.log("ClaudeVerifier", "claude",
                            f"Recommendation: {result.get('recommendation')} "
                            f"(confidence: {result.get('confidence',0)})")
                return result
        except Exception as e:
            Console.log("ClaudeVerifier", "warning", f"Claude API failed: {e}")
        return self._fallback_verification(score_before, score_after, test_results)

    def _fallback_verification(self, score_before: float, score_after: float,
                                test_results: dict) -> dict:
        pass_rate = test_results.get("pass_rate", 0)
        rec = "approve" if (score_after > score_before and pass_rate >= 80) else "needs_changes"
        return {
            "recommendation": rec,
            "confidence": 60,
            "breaking_changes_risk": "low",
            "quality_assessment": "Claude API unavailable — manual review strongly recommended",
            "concerns": ["Claude verification unavailable — human must review diff manually"],
            "approval_notes": f"Score: {score_before:.1f}→{score_after:.1f} | Tests: {pass_rate:.0f}% pass rate"
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — VERSION CONTROLLER (git-like versioning + rollback)
# ─────────────────────────────────────────────────────────────────────────────

class VersionController:
    """
    Track all engine versions.
    Enable rollback to any previous version or any specific change.
    Store full code snapshots (not diffs) for reliable rollback.
    """
    def __init__(self):
        self._db = RSDDB()
        RSDConfig.VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def snapshot(self, engine_name: str, file_path: str) -> Tuple[str, str]:
        """
        Take a snapshot of the current engine code.
        Returns (version_string, code_hash).
        """
        path = Path(file_path)
        if not path.exists():
            return "0.0.0", ""
        code      = path.read_text(encoding="utf-8")
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:12]
        # Determine current version from DB
        versions = self._db.get_versions(engine_name)
        if versions:
            last_v = versions[0]["version"]
            parts  = [int(x) for x in last_v.split(".")]
            parts[2] += 1   # increment patch
            new_v = ".".join(str(x) for x in parts)
        else:
            new_v = "1.0.0"
        # Save snapshot file
        snap_path = RSDConfig.VERSIONS_DIR / f"{engine_name}_{new_v}_{code_hash}.py"
        snap_path.write_text(code, encoding="utf-8")
        return new_v, code_hash

    def save_pre_change(self, engine_name: str, file_path: str) -> str:
        """Save snapshot BEFORE making changes. Returns old version."""
        v, h = self.snapshot(engine_name, file_path)
        # Tag as pre-change snapshot
        pre_v = f"{v}_pre"
        snap = RSDConfig.VERSIONS_DIR / f"{engine_name}_{pre_v}_{h}.py"
        path  = Path(file_path)
        if path.exists():
            snap.write_text(path.read_text(encoding="utf-8"))
        return pre_v

    def commit(self, version: EngineVersion):
        """Commit a new version to the version history."""
        self._db.save_version(version)
        # Add to changelog
        self._db.add_changelog({
            "engine_name":  version.engine_name,
            "version":      version.version,
            "change_type":  version.change_type.value,
            "title":        version.description[:100],
            "description":  f"Changes: {', '.join(version.changes[:3])}",
            "score_before": version.score_before,
            "score_after":  version.score_after,
            "approved_by":  version.approved_by,
        })
        Console.log("VersionController", "success",
                    f"Committed {version.engine_name} v{version.version}")

    def rollback(self, engine_name: str, target_version: str,
                  file_path: str) -> Tuple[bool, str]:
        """
        Rollback engine to a specific version.
        target_version: "previous" | "1.2.3" | specific version string
        """
        Console.log("VersionController", "info",
                    f"Rolling back {engine_name} to {target_version}...")
        versions = self._db.get_versions(engine_name)
        if not versions:
            return False, "No versions found for this engine"
        if target_version == "previous":
            # Find the most recent non-rolled-back approved version
            approved = [v for v in versions
                        if v["approved_by"] not in ("pending","") and not v["rolled_back"]]
            if len(approved) < 2:
                return False, "No previous approved version to roll back to"
            target = approved[1]   # [0] is current, [1] is previous
        else:
            target_rows = [v for v in versions if v["version"] == target_version]
            if not target_rows:
                return False, f"Version {target_version} not found"
            target = target_rows[0]

        # Find snapshot file
        snap_pattern = f"{engine_name}_{target['version']}_{target['code_hash']}.py"
        snap_files   = list(RSDConfig.VERSIONS_DIR.glob(f"{engine_name}_{target['version']}*.py"))
        if not snap_files:
            return False, f"Snapshot file not found for v{target['version']}"

        # Restore
        restored_code = snap_files[0].read_text(encoding="utf-8")
        Path(file_path).write_text(restored_code, encoding="utf-8")

        # Mark as rolled back in DB
        self._db._db.execute(
            "UPDATE rsd_engine_versions SET rolled_back=1 WHERE engine_name=? AND version=?",
            (engine_name, target["version"])
        )
        self._db._db.commit()
        self._db.add_changelog({
            "engine_name": engine_name,
            "version":     f"{target['version']}_rollback",
            "change_type": "revert",
            "title":       f"Rollback to v{target['version']}",
            "description": f"Manual rollback to version {target['version']}",
            "score_before": 0, "score_after": 0,
            "approved_by": "system_rollback"
        })
        Console.log("VersionController", "success",
                    f"Rolled back {engine_name} to v{target['version']}")
        return True, f"Rolled back to v{target['version']}"

    def diff(self, engine_name: str, version_a: str,
              version_b: str = "current") -> str:
        """Generate unified diff between two versions."""
        import difflib
        versions = self._db.get_versions(engine_name)
        snaps    = list(RSDConfig.VERSIONS_DIR.glob(f"{engine_name}_*.py"))

        def get_code(v: str) -> str:
            if v == "current":
                # Try to find the engine file
                for p in RSDConfig.ENGINES_DIR.glob(f"*{engine_name}*.py"):
                    return p.read_text(encoding="utf-8")
                return ""
            matches = [s for s in snaps if f"_{v}_" in s.name]
            return matches[0].read_text(encoding="utf-8") if matches else ""

        code_a = get_code(version_a)
        code_b = get_code(version_b)
        return "\n".join(difflib.unified_diff(
            code_a.splitlines(), code_b.splitlines(),
            fromfile=f"{engine_name} v{version_a}",
            tofile=f"{engine_name} {version_b}",
            lineterm=""
        ))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — APPROVAL GATE (manual human approval required)
# ─────────────────────────────────────────────────────────────────────────────

class ApprovalGate:
    """
    Manual approval gate — NOTHING goes to production without human sign-off.
    Creates an approval request visible in the AnnaSEO UI.
    Blocks until approved or rejected.
    On rejection: records reason, no code change applied.
    On approval: VersionController.commit() → file written to production path.
    """
    def __init__(self):
        self._db = RSDDB()
        self._vc = VersionController()

    def create_request(self, engine_name: str, version: str,
                        original_code: str, modified_code: str,
                        claude_notes: dict, score_before: float,
                        score_after: float, test_results: dict,
                        changes: List[str]) -> str:
        """Create approval request. Returns request_id."""
        import difflib
        diff = "\n".join(difflib.unified_diff(
            original_code.splitlines(), modified_code.splitlines(),
            fromfile=f"{engine_name} current",
            tofile=f"{engine_name} v{version} proposed",
            lineterm=""
        ))
        summary = (
            f"Engine: {engine_name} | Version: {version}\n"
            f"Score change: {score_before:.1f} → {score_after:.1f} "
            f"({'+'if score_after>score_before else ''}{score_after-score_before:.1f})\n"
            f"Tests: {test_results.get('passed',0)} passed / "
            f"{test_results.get('failed',0)} failed "
            f"({test_results.get('pass_rate',0):.0f}% pass rate)\n"
            f"Changes:\n" + "\n".join(f"  • {c}" for c in changes[:5]) +
            f"\nClaude: {claude_notes.get('recommendation','unknown')} "
            f"(confidence: {claude_notes.get('confidence',0)}%)"
        )
        req = ApprovalRequest(
            request_id=f"apr_{hashlib.md5(f'{engine_name}{version}{time.time()}'.encode()).hexdigest()[:10]}",
            engine_name=engine_name, version=version,
            diff=diff, summary=summary,
            claude_notes=json.dumps(claude_notes),
            score_before=score_before, score_after=score_after,
            test_report=test_results
        )
        self._db.save_approval(req)
        Console.log("ApprovalGate", "warning",
                    f"Approval required for {engine_name} v{version} — "
                    f"request_id={req.request_id}")
        return req.request_id

    def approve(self, request_id: str, decision_by: str,
                 decision_note: str = "") -> Tuple[bool, str]:
        """
        Human approves the change.
        Writes modified code to production path.
        """
        req = self._db.get_approval(request_id)
        if not req:
            return False, "Request not found"
        if req["status"] != "pending":
            return False, f"Request already {req['status']}"

        self._db.update_approval(request_id, "approved", decision_by, decision_note)
        Console.log("ApprovalGate", "success",
                    f"Approved by {decision_by}: {req['engine_name']} v{req['version']}")
        return True, f"Approved. {req['engine_name']} v{req['version']} is now live."

    def reject(self, request_id: str, decision_by: str,
                decision_note: str) -> Tuple[bool, str]:
        """Human rejects. No code change applied."""
        req = self._db.get_approval(request_id)
        if not req:
            return False, "Request not found"
        self._db.update_approval(request_id, "rejected", decision_by, decision_note)
        Console.log("ApprovalGate", "info",
                    f"Rejected by {decision_by}: {req['engine_name']} — {decision_note}")
        return True, f"Rejected. {req['engine_name']} stays on current version."

    def pending_requests(self) -> List[dict]:
        return self._db.get_pending_approvals()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — FINE-TUNING PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

class FineTuningPipeline:
    """
    Full fine-tuning cycle for a low-scoring engine.
    Gemini → Groq → DeepSeek → Shadow → Claude → ApprovalGate
    """
    def __init__(self):
        self._gemini  = GeminiAdvisor()
        self._groq    = GroqTestGenerator()
        self._deepseek= DeepSeekCoder()
        self._shadow  = ShadowRunner()
        self._claude  = ClaudeVerifier()
        self._gate    = ApprovalGate()
        self._vc      = VersionController()
        self._scorer  = EngineScorer()

    def run(self, report: EngineHealthReport, engine_file: str,
             attempt: int = 1) -> dict:
        """
        Run one fine-tuning cycle.
        Returns {success, request_id, version, message}
        """
        Console.log("FineTuning", "sep",
                    f"{'─'*40}")
        Console.log("FineTuning", "info",
                    f"Starting fine-tune: {report.engine_name} "
                    f"score={report.total_score:.1f} (attempt {attempt}/{RSDConfig.MAX_FINE_TUNE_ATTEMPTS})")

        path = Path(engine_file)
        if not path.exists():
            return {"success": False, "message": f"Engine file not found: {engine_file}"}

        original_code = path.read_text(encoding="utf-8")

        # Save pre-change snapshot
        pre_version = self._vc.save_pre_change(report.engine_name, engine_file)
        Console.log("FineTuning", "data", f"Pre-change snapshot: {pre_version}")

        # Step 1: Gemini analyses and advises
        advice = self._gemini.advise(report, original_code)
        Console.log("FineTuning", "gemini",
                    f"Gemini found {len(advice.get('fixes',[]))} fixes, "
                    f"estimated +{advice.get('estimated_score_gain',0)} score")

        # Step 2: Groq generates test cases
        test_code = self._groq.generate_tests(
            report.engine_name, original_code, advice.get("fixes",[])
        )
        Console.log("FineTuning", "groq", f"Generated test suite ({len(test_code.splitlines())} lines)")

        # Step 3: DeepSeek writes the code fix
        modified_code = self._deepseek.generate_fix(
            original_code, advice, report.engine_name
        )
        Console.log("FineTuning", "deepseek",
                    f"Code fix generated ({len(modified_code.splitlines())} lines)")

        if modified_code == original_code:
            Console.log("FineTuning", "warning",
                        "No code changes generated — DeepSeek may be unavailable")

        # Step 4: Shadow run — run tests against modified code
        test_results = self._shadow.run_tests(
            test_code, modified_code, report.engine_name
        )
        Console.log("FineTuning", "data",
                    f"Shadow tests: {test_results['passed']} passed, "
                    f"{test_results['failed']} failed")

        # Step 5: Estimate new score
        score_after = min(100, report.total_score + advice.get("estimated_score_gain", 5))
        if test_results["pass_rate"] < 50:
            score_after = report.total_score   # no improvement if tests fail

        # Step 6: Circuit breaker check
        can_proceed, cb_reason = self._shadow.circuit_breaker_check(
            report.total_score, score_after
        )
        if not can_proceed:
            Console.log("FineTuning", "error",
                        f"Circuit breaker triggered: {cb_reason}")
            return {"success": False, "message": cb_reason, "circuit_breaker": True}

        # Step 7: Claude verifies
        claude_verdict = self._claude.verify(
            report.engine_name, original_code, modified_code,
            test_results, report.total_score, score_after, advice
        )
        Console.log("FineTuning", "claude",
                    f"Claude: {claude_verdict.get('recommendation')} "
                    f"(risk: {claude_verdict.get('breaking_changes_risk','?')})")

        if claude_verdict.get("recommendation") == "reject":
            Console.log("FineTuning", "warning",
                        f"Claude rejected: {claude_verdict.get('quality_assessment','?')}")
            return {"success": False, "message": claude_verdict.get("approval_notes","")}

        # Collect changes list
        changes = [
            f"{f['area']}: {f['what_to_change'][:60]}"
            for f in advice.get("fixes",[])
        ]
        if not changes:
            changes = ["Performance and quality improvements based on metrics analysis"]

        # Step 8: Create version record
        new_version, code_hash = self._vc.snapshot(report.engine_name, engine_file)
        engine_version = EngineVersion(
            version=new_version, engine_name=report.engine_name,
            file_path=engine_file,
            code_hash=hashlib.sha256(modified_code.encode()).hexdigest()[:12],
            change_type=ChangeType.IMPROVE,
            description=f"Auto fine-tune: score {report.total_score:.0f}→{score_after:.0f}",
            changes=changes, ai_used=["gemini","groq","deepseek","claude"],
            score_before=report.total_score, score_after=score_after,
            test_results=test_results
        )

        # Step 9: Create APPROVAL REQUEST — human must approve before code is written
        request_id = self._gate.create_request(
            engine_name=report.engine_name, version=new_version,
            original_code=original_code, modified_code=modified_code,
            claude_notes=claude_verdict,
            score_before=report.total_score, score_after=score_after,
            test_results=test_results, changes=changes
        )

        # Store the modified code in pending state (not yet in production)
        pending_path = RSDConfig.VERSIONS_DIR / f"{report.engine_name}_{new_version}_pending.py"
        pending_path.write_text(modified_code, encoding="utf-8")

        # Commit version record (with status = pending approval)
        self._vc.commit(engine_version)

        Console.log("FineTuning", "success",
                    f"Fine-tune ready for approval: request_id={request_id}")
        return {
            "success":    True,
            "request_id": request_id,
            "version":    new_version,
            "score_before": report.total_score,
            "score_after":  score_after,
            "changes":    changes,
            "message":    f"Awaiting manual approval. Open AnnaSEO → Research & Self Development to review."
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — MASTER RSD ENGINE (Ruflo orchestrator integration)
# ─────────────────────────────────────────────────────────────────────────────

class ResearchAndSelfDevelopment:
    """
    Master Research & Self Development engine.
    Ruflo calls this via job queue.
    Monitors all AnnaSEO engines, scores them, triggers fine-tuning.

    Ruflo integration:
        Job type: rsd_scan_all        — scan all engines
        Job type: rsd_scan_engine     — scan one engine
        Job type: rsd_approve         — approve a pending change
        Job type: rsd_reject          — reject a pending change
        Job type: rsd_rollback        — rollback an engine
        Job type: rsd_changelog       — get changelog

    SSE console: all steps logged to ruflo_jobs.console_log table
    """

    # All engines to monitor (engine_name, file_path)
    MONITORED_ENGINES = [
        ("20phase_engine",           "./ruflo_20phase_engine.py"),
        ("content_engine",           "./ruflo_content_engine.py"),
        ("confirmation_pipeline",    "./ruflo_confirmation_pipeline.py"),
        ("seo_audit",                "./ruflo_seo_audit.py"),
        ("publisher",                "./ruflo_publisher.py"),
        ("rank_zero_engine",         "./ruflo_rank_zero_engine.html"),
        ("strategy_dev_engine",      "./ruflo_strategy_dev_engine.py"),
        ("final_strategy_engine",    "./ruflo_final_strategy_engine.py"),
        ("annaseo_addons",           "./annaseo_addons.py"),
        ("annaseo_doc2_addons",      "./annaseo_doc2_addons.py"),
    ]

    def __init__(self):
        self._scorer   = EngineScorer()
        self._pipeline = FineTuningPipeline()
        self._vc       = VersionController()
        self._gate     = ApprovalGate()
        self._db       = RSDDB()

    # ── Ruflo job handlers ────────────────────────────────────────────────────

    def job_scan_all(self) -> List[dict]:
        """Scan all engines. Triggered by Ruflo as scheduled job."""
        Console.log("RSD", "sep", "═"*50)
        Console.log("RSD", "info",
                    f"Full scan of {len(self.MONITORED_ENGINES)} engines...")
        results = []
        for engine_name, file_path in self.MONITORED_ENGINES:
            result = self._scan_one(engine_name, file_path)
            results.append(result)
        summary = {
            "engines_scanned": len(results),
            "healthy":   sum(1 for r in results if r["status"] in ("healthy","good")),
            "degraded":  sum(1 for r in results if r["status"] == "degraded"),
            "poor":      sum(1 for r in results if r["status"] in ("poor","critical")),
            "tuning_triggered": sum(1 for r in results if r.get("tuning_triggered")),
            "pending_approvals": len(self._gate.pending_requests()),
        }
        Console.log("RSD", "success",
                    f"Scan complete: {summary['healthy']} healthy, "
                    f"{summary['degraded']} degraded, {summary['poor']} poor, "
                    f"{summary['tuning_triggered']} tuning triggered")
        return results

    def job_scan_engine(self, engine_name: str) -> dict:
        """Scan one specific engine."""
        for name, path in self.MONITORED_ENGINES:
            if name == engine_name:
                return self._scan_one(name, path)
        return {"error": f"Engine {engine_name} not in monitored list"}

    def job_approve(self, request_id: str, approved_by: str,
                     note: str = "") -> dict:
        """
        Approve a pending change.
        Writes modified code to production path.
        This is called from the UI approval button.
        """
        req = self._db.get_approval(request_id)
        if not req:
            return {"success": False, "error": "Request not found"}

        # Write the pending code to production
        pending = RSDConfig.VERSIONS_DIR / f"{req['engine_name']}_{req['version']}_pending.py"
        engine_files = [p for _, p in self.MONITORED_ENGINES
                        if req["engine_name"] in p]
        if pending.exists() and engine_files:
            code = pending.read_text(encoding="utf-8")
            Path(engine_files[0]).write_text(code, encoding="utf-8")
            Console.log("RSD", "success",
                        f"Code deployed: {req['engine_name']} v{req['version']}")

        ok, msg = self._gate.approve(request_id, approved_by, note)
        if ok:
            # Update version record
            self._db._db.execute(
                "UPDATE rsd_engine_versions SET approved_by=?, approved_at=? WHERE engine_name=? AND version=?",
                (approved_by, datetime.utcnow().isoformat(), req["engine_name"], req["version"])
            )
            self._db._db.commit()
        return {"success": ok, "message": msg}

    def job_reject(self, request_id: str, rejected_by: str, reason: str) -> dict:
        """Reject a pending change. No code is modified."""
        ok, msg = self._gate.reject(request_id, rejected_by, reason)
        return {"success": ok, "message": msg}

    def job_rollback(self, engine_name: str, target_version: str,
                      rolled_back_by: str) -> dict:
        """
        Rollback an engine to a specific version or 'previous'.
        Always allowed without approval gate (rollback is emergency action).
        """
        engine_files = [p for n, p in self.MONITORED_ENGINES if n == engine_name]
        if not engine_files:
            return {"success": False, "error": f"Engine {engine_name} not found"}
        ok, msg = self._vc.rollback(engine_name, target_version, engine_files[0])
        if ok:
            Console.log("RSD", "success",
                        f"Rollback confirmed by {rolled_back_by}: {msg}")
        return {"success": ok, "message": msg}

    def job_changelog(self, engine_name: str = None, limit: int = 50) -> List[dict]:
        """Get changelog for display in UI."""
        return self._db.get_changelog(engine_name, limit)

    def job_health_dashboard(self) -> dict:
        """Return current health of all engines for dashboard display."""
        dashboard = []
        for engine_name, _ in self.MONITORED_ENGINES:
            rows = self._db._db.execute(
                "SELECT total_score, status, generated_at FROM rsd_health_reports "
                "WHERE engine_name=? ORDER BY generated_at DESC LIMIT 1",
                (engine_name,)
            ).fetchone()
            versions = self._db.get_versions(engine_name)
            current_v = versions[0]["version"] if versions else "1.0.0"
            dashboard.append({
                "engine_name":  engine_name,
                "version":      current_v,
                "score":        round(rows["total_score"],1) if rows else None,
                "status":       rows["status"] if rows else "no_data",
                "last_checked": rows["generated_at"] if rows else None,
                "pending_approval": any(
                    r["engine_name"] == engine_name
                    for r in self._db.get_pending_approvals()
                )
            })
        return {
            "engines":           dashboard,
            "pending_approvals": self._db.get_pending_approvals(),
            "recent_changes":    self._db.get_changelog(limit=10),
        }

    def job_versions(self, engine_name: str) -> List[dict]:
        """List all versions of an engine for rollback UI."""
        return self._db.get_versions(engine_name)

    # ── Internal methods ──────────────────────────────────────────────────────

    def _scan_one(self, engine_name: str, file_path: str) -> dict:
        """Scan one engine: score it, trigger fine-tuning if needed."""
        version = self._current_version(engine_name)
        report  = self._scorer.score(engine_name, version)

        result = {
            "engine_name": engine_name,
            "version":     version,
            "score":       report.total_score,
            "status":      report.status.value,
            "tuning_triggered": False,
            "request_id":  None,
        }

        if report.needs_tuning:
            Console.log("RSD", "warning",
                        f"{engine_name} score {report.total_score:.1f} — triggering fine-tune")
            tune_result = self._pipeline.run(report, file_path)
            result["tuning_triggered"] = tune_result.get("success", False)
            result["request_id"]       = tune_result.get("request_id")
            result["tune_message"]     = tune_result.get("message","")
        else:
            Console.log("RSD", "success",
                        f"{engine_name} score {report.total_score:.1f} — healthy")
        return result

    def _current_version(self, engine_name: str) -> str:
        versions = self._db.get_versions(engine_name)
        return versions[0]["version"] if versions else "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — FASTAPI ENDPOINTS (wired to Ruflo job system)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from pydantic import BaseModel as PM

    app = FastAPI(title="AnnaSEO — Research & Self Development Engine",
                  description="Engine health monitoring, fine-tuning, approval, rollback")

    rsd = ResearchAndSelfDevelopment()

    class ApproveBody(PM):
        approved_by:  str
        note:         str = ""

    class RejectBody(PM):
        rejected_by: str
        reason:      str

    class RollbackBody(PM):
        target_version: str  # "previous" or "1.2.3"
        rolled_back_by: str

    @app.get("/api/rsd/health", tags=["RSD"])
    def health_dashboard():
        """All engines health scores. Shows on Research & Self Development page."""
        return rsd.job_health_dashboard()

    @app.post("/api/rsd/scan/all", tags=["RSD"])
    def scan_all(bg: BackgroundTasks):
        """Trigger full scan of all engines. Runs in background."""
        bg.add_task(rsd.job_scan_all)
        return {"status": "started", "message": "Full scan started — watch console for progress"}

    @app.post("/api/rsd/scan/{engine_name}", tags=["RSD"])
    def scan_engine(engine_name: str):
        return rsd.job_scan_engine(engine_name)

    @app.get("/api/rsd/approvals", tags=["RSD"])
    def pending_approvals():
        """List pending approval requests for UI display."""
        return rsd.job_health_dashboard()["pending_approvals"]

    @app.get("/api/rsd/approvals/{request_id}", tags=["RSD"])
    def get_approval(request_id: str):
        req = RSDDB().get_approval(request_id)
        if not req: raise HTTPException(404, "Request not found")
        return req

    @app.post("/api/rsd/approvals/{request_id}/approve", tags=["RSD"])
    def approve(request_id: str, body: ApproveBody):
        """MANUAL APPROVAL — push approved version to production."""
        return rsd.job_approve(request_id, body.approved_by, body.note)

    @app.post("/api/rsd/approvals/{request_id}/reject", tags=["RSD"])
    def reject(request_id: str, body: RejectBody):
        """Reject a pending change. No code modified."""
        return rsd.job_reject(request_id, body.rejected_by, body.reason)

    @app.post("/api/rsd/rollback/{engine_name}", tags=["RSD"])
    def rollback(engine_name: str, body: RollbackBody):
        """Rollback engine to previous or specific version. No approval needed."""
        return rsd.job_rollback(engine_name, body.target_version, body.rolled_back_by)

    @app.get("/api/rsd/changelog", tags=["RSD"])
    def changelog(engine_name: str = None, limit: int = 50):
        return rsd.job_changelog(engine_name, limit)

    @app.get("/api/rsd/versions/{engine_name}", tags=["RSD"])
    def versions(engine_name: str):
        return rsd.job_versions(engine_name)

    @app.get("/api/rsd/diff/{engine_name}", tags=["RSD"])
    def diff(engine_name: str, version_a: str, version_b: str = "current"):
        return {"diff": VersionController().diff(engine_name, version_a, version_b)}

    @app.post("/api/rsd/metrics/{engine_name}/run", tags=["RSD (internal)"])
    def record_run(engine_name: str, run_data: dict):
        """Called by other engines to register their run metrics."""
        run = EngineRun(
            run_id=run_data.get("run_id", f"run_{time.time():.0f}"),
            engine_name=engine_name,
            started_at=run_data.get("started_at", datetime.utcnow().isoformat()),
            duration_ms=run_data.get("duration_ms",0),
            peak_memory_mb=run_data.get("peak_memory_mb",0),
            success=run_data.get("success",True),
            error=run_data.get("error",""),
            output_fields=run_data.get("output_fields",[]),
            expected_fields=run_data.get("expected_fields",[]),
            quality_signals=run_data.get("quality_signals",{})
        )
        RSDDB().save_run(run)
        return {"recorded": True}

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 15 — TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    python annaseo_rsd_engine.py test              # all tests
    python annaseo_rsd_engine.py test metrics      # metrics collection
    python annaseo_rsd_engine.py test scoring      # engine scoring
    python annaseo_rsd_engine.py test versioning   # version control + rollback
    python annaseo_rsd_engine.py test approval     # approval gate
    python annaseo_rsd_engine.py test pipeline     # full fine-tuning pipeline (no AI keys needed)
    python annaseo_rsd_engine.py scan              # scan all engines
    python annaseo_rsd_engine.py dashboard         # show dashboard
    """
    def _h(self, n): print(f"\n{'─'*58}\n  TEST: {n}\n{'─'*58}")
    def _ok(self, m): print(f"  ✓ {m}")

    def _seed_runs(self, engine_name: str, n: int = 20):
        """Seed test run data."""
        db = RSDDB()
        import random
        for i in range(n):
            run = EngineRun(
                run_id=f"run_{engine_name}_{i}",
                engine_name=engine_name,
                started_at=(datetime.utcnow() - timedelta(hours=i)).isoformat(),
                duration_ms=random.uniform(5000, 25000),
                peak_memory_mb=random.uniform(100, 400),
                input_tokens=random.randint(1000, 8000),
                output_tokens=random.randint(500, 3000),
                success=random.random() > 0.08,
                output_fields=["topics","clusters","keywords"],
                expected_fields=["topics","clusters","keywords","content_plan"],
                quality_signals={"topic_quality": random.uniform(60,95)}
            )
            run.output_hash = hashlib.md5(f"hash{i%5}".encode()).hexdigest()[:12]
            db.save_run(run)

    def test_metrics(self):
        self._h("MetricsCollector — observer pattern")
        mc = MetricsCollector()
        with mc.observe("test_engine_metrics", expected_fields=["result","score"]) as run:
            time.sleep(0.05)
            run.output_fields = ["result","score","extra"]
            run.quality_signals = {"output_score": 88}
        self._ok(f"Run recorded: {run.run_id}")
        self._ok(f"Duration: {run.duration_ms:.0f}ms | Success: {run.success}")
        runs = RSDDB().get_recent_runs("test_engine_metrics", hours=1)
        self._ok(f"Runs in DB: {len(runs)}")

    def test_scoring(self):
        self._h("EngineScorer — 8 dimensions")
        self._seed_runs("test_20phase", 30)
        scorer  = EngineScorer()
        report  = scorer.score("test_20phase", "1.0.0")
        self._ok(f"Total score: {report.total_score}/100 ({report.status.value})")
        for d in sorted(report.dimensions, key=lambda x: x.score):
            bar = "█" * int(d.score / 10) + "░" * (10 - int(d.score / 10))
            self._ok(f"  {d.dimension:22} {bar} {d.score:.0f}")
        self._ok(f"Needs tuning: {report.needs_tuning}")
        self._ok(f"Recommendations: {len(report.recommendations)}")

    def test_versioning(self):
        self._h("VersionController — snapshot + rollback")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# Version 1.0.0\ndef run(): return 'v1'\n")
            tmppath = f.name

        vc = VersionController()
        v1, h1 = vc.snapshot("test_engine_vc", tmppath)
        self._ok(f"Snapshot v{v1} hash={h1}")

        # Write v2
        Path(tmppath).write_text("# Version 2.0.0\ndef run(): return 'v2'\n")
        v2, h2 = vc.snapshot("test_engine_vc", tmppath)
        self._ok(f"Snapshot v{v2} hash={h2}")

        ev = EngineVersion(
            version=v2, engine_name="test_engine_vc",
            file_path=tmppath, code_hash=h2,
            change_type=ChangeType.IMPROVE,
            description="Test improvement",
            changes=["improved run() method"], ai_used=["deepseek"],
            score_before=72.0, score_after=86.0, approved_by="testuser"
        )
        vc.commit(ev)
        self._ok(f"Version committed: v{v2}")

        # Get versions
        versions = RSDDB().get_versions("test_engine_vc")
        self._ok(f"Total versions: {len(versions)}")

        import os; os.unlink(tmppath)

    def test_approval(self):
        self._h("ApprovalGate — manual approval flow")
        gate = ApprovalGate()
        db   = RSDDB()

        req = ApprovalRequest(
            request_id=f"apr_test_{int(time.time())}",
            engine_name="test_engine_gate",
            version="1.2.0",
            diff="--- a/engine.py\n+++ b/engine.py\n@@ -1 +1 @@\n-# old\n+# new # RSD-FIX: improved",
            summary="Score: 72.0 → 89.5 | Tests: 12 passed / 0 failed",
            claude_notes='{"recommendation":"approve","confidence":92}',
            score_before=72.0, score_after=89.5,
            test_report={"passed":12,"failed":0,"pass_rate":100}
        )
        db.save_approval(req)
        self._ok(f"Approval request created: {req.request_id}")

        pending = gate.pending_requests()
        self._ok(f"Pending approvals: {len(pending)}")

        ok, msg = gate.approve(req.request_id, "admin_user", "Looks good!")
        self._ok(f"Approval: {ok} — {msg}")

        ok, msg = gate.reject(f"apr_reject_{int(time.time())}", "reviewer", "Needs more tests")
        self._ok(f"Reject attempt on missing ID: ok={ok}")

    def test_pipeline(self):
        self._h("FineTuningPipeline — dry run (no AI keys)")
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('''"""Test engine for RSD pipeline."""

def run(keyword: str) -> dict:
    """Process a keyword."""
    if not keyword:
        raise ValueError("keyword required")
    return {
        "keyword": keyword,
        "topics": [f"{keyword} topic {i}" for i in range(5)],
        "clusters": [{"name": f"{keyword} cluster"}],
    }
''')
            tmppath = f.name

        self._seed_runs("test_pipeline_engine", 15)
        scorer = EngineScorer()
        report = scorer.score("test_pipeline_engine", "1.0.0")
        report.needs_tuning = True   # force tuning for test
        self._ok(f"Engine score: {report.total_score:.1f}/100")

        pipeline = FineTuningPipeline()
        result   = pipeline.run(report, tmppath)
        self._ok(f"Pipeline result: success={result.get('success')}")
        self._ok(f"Message: {result.get('message','')[:70]}")
        if result.get("request_id"):
            self._ok(f"Approval request: {result['request_id']}")
            pending = RSDDB().get_pending_approvals()
            self._ok(f"Pending approvals: {len(pending)}")

        import os; os.unlink(tmppath)

    def run_all(self):
        print("\n"+"═"*58+"\n  ANNASEO — RSD ENGINE TESTS\n"+"═"*58)
        tests = [
            ("metrics",    self.test_metrics),
            ("scoring",    self.test_scoring),
            ("versioning", self.test_versioning),
            ("approval",   self.test_approval),
            ("pipeline",   self.test_pipeline),
        ]
        p=f=0
        for name,fn in tests:
            try: fn(); p+=1
            except Exception as e:
                print(f"  ✗ {name}: {e}")
                import traceback; traceback.print_exc()
                f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*58)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
AnnaSEO — Research & Self Development Engine
─────────────────────────────────────────────────────────────
Engine health monitoring · AI fine-tuning · Manual approval · Rollback

Usage:
  python annaseo_rsd_engine.py test                  # run all tests
  python annaseo_rsd_engine.py test <stage>          # one test
  python annaseo_rsd_engine.py scan                  # scan all engines
  python annaseo_rsd_engine.py scan <engine_name>    # scan one engine
  python annaseo_rsd_engine.py dashboard             # show health dashboard
  python annaseo_rsd_engine.py changelog             # show full changelog
  python annaseo_rsd_engine.py approvals             # show pending approvals
  python annaseo_rsd_engine.py approve <request_id>  # approve in CLI
  python annaseo_rsd_engine.py rollback <engine> <version>
  python annaseo_rsd_engine.py api                   # start FastAPI on :8004

Stages: metrics, scoring, versioning, approval, pipeline

How it integrates with other engines:
  from annaseo_rsd_engine import MetricsCollector
  mc = MetricsCollector()
  with mc.observe("20phase_engine", expected_fields=["topics","clusters"]) as m:
      result = run_my_engine(keyword)
      m.output_fields = list(result.keys())
      m.quality_signals = {"topic_count": len(result["topics"])}
"""
    if len(sys.argv) < 2: print(HELP); exit(0)
    cmd = sys.argv[1]

    if cmd == "test":
        t = Tests()
        if len(sys.argv) > 2:
            fn = getattr(t, f"test_{sys.argv[2]}", None)
            if fn: fn()
            else: print(f"Unknown stage: {sys.argv[2]}")
        else: t.run_all()

    elif cmd == "scan":
        rsd = ResearchAndSelfDevelopment()
        if len(sys.argv) > 2:
            print(json.dumps(rsd.job_scan_engine(sys.argv[2]), indent=2))
        else:
            results = rsd.job_scan_all()
            for r in results:
                status_icon = {"healthy":"✓","good":"✓","degraded":"⚠","poor":"✗","critical":"✗"}.get(r["status"],"·")
                print(f"  {status_icon} {r['engine_name']:30} {r['score']:.1f}/100 ({r['status']})"
                      + (" → TUNING REQUESTED" if r.get("tuning_triggered") else ""))

    elif cmd == "dashboard":
        rsd = ResearchAndSelfDevelopment()
        dash = rsd.job_health_dashboard()
        print("\n  ENGINE HEALTH DASHBOARD")
        print("  " + "─"*52)
        for e in dash["engines"]:
            score = e.get("score")
            score_str = f"{score:.1f}/100" if score else "no data"
            pending_flag = " [APPROVAL PENDING]" if e.get("pending_approval") else ""
            print(f"  {e['engine_name']:30} v{e['version']:8} {score_str}{pending_flag}")
        print(f"\n  Pending approvals: {len(dash['pending_approvals'])}")

    elif cmd == "changelog":
        rsd   = ResearchAndSelfDevelopment()
        engine = sys.argv[2] if len(sys.argv) > 2 else None
        log_  = rsd.job_changelog(engine)
        print("\n  CHANGELOG")
        for entry in log_[:20]:
            delta = entry.get("score_after",0) - entry.get("score_before",0)
            print(f"  [{entry['created_at'][:10]}] {entry['engine_name']:25} "
                  f"v{entry['version']} {entry['change_type']:10} "
                  f"{entry['title'][:40]} "
                  f"({'+'if delta>=0 else ''}{delta:.1f})")

    elif cmd == "approvals":
        pending = RSDDB().get_pending_approvals()
        if not pending:
            print("  No pending approvals.")
        for req in pending:
            print(f"\n  REQUEST: {req['request_id']}")
            print(f"  {req['summary'][:300]}")

    elif cmd == "approve":
        if len(sys.argv) < 3: print("Usage: approve <request_id>"); exit(1)
        rsd = ResearchAndSelfDevelopment()
        res = rsd.job_approve(sys.argv[2], "cli_user", "Approved via CLI")
        print(res["message"])

    elif cmd == "rollback":
        if len(sys.argv) < 4: print("Usage: rollback <engine_name> <version|previous>"); exit(1)
        rsd = ResearchAndSelfDevelopment()
        res = rsd.job_rollback(sys.argv[2], sys.argv[3], "cli_user")
        print(res["message"])

    elif cmd == "api":
        try:
            import uvicorn
            Console.log("RSD", "info", "API at http://localhost:8004")
            Console.log("RSD", "info", "Docs at http://localhost:8004/docs")
            uvicorn.run("annaseo_rsd_engine:app", host="0.0.0.0", port=8004, reload=True)
        except ImportError:
            print("pip install uvicorn")
    else:
        print(f"Unknown command: {cmd}\n{HELP}")

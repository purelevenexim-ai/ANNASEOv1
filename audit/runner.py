"""
audit/runner.py
===============
Full audit runner — orchestrates all 5 quality layers.

Usage (standalone):
    python -m audit.runner --session-id <id> --project-id <pid>

Usage (programmatic):
    from audit.runner import run_full_audit
    report = run_full_audit(session_id="abc", project_id="proj1")

What it does:
  1. Loads kw2 session data from DB
  2. Runs rule-based AI reasoning validator
  3. Compares against baseline (regression)
  4. Optionally runs LLM-as-Judge (requires Ollama)
  5. Computes composite audit score + recommendations
  6. Saves result to audits/<timestamp>_<session_id>/audit_report.json
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("audit.runner")

_AUDITS_DIR = Path(os.getenv("ANNASEO_ROOT", "/root/ANNASEOv1")) / "audits"


def _load_session_data(session_id: str, project_id: str) -> dict[str, Any]:
    """Load kw2 session output from DB."""
    try:
        from engines.kw2 import db as kw2db
        with kw2db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM kw2_sessions WHERE id=? AND project_id=?",
                (session_id, project_id),
            ).fetchone()
        if not row:
            return {}
        data = dict(row)
        # Parse any JSON-encoded fields
        for field in ("keywords", "clusters", "strategy", "profile", "business_profile"):
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = json.loads(data[field])
                except Exception:
                    pass
        return data
    except Exception as exc:
        log.warning("Could not load session from DB: %s", exc)
        return {}


def run_full_audit(
    session_id: str = "",
    project_id: str = "",
    result: dict[str, Any] | None = None,
    use_llm_judge: bool = False,
    save_report: bool = True,
    baseline_id: str | None = None,
    source_text: str = "",
) -> dict[str, Any]:
    """
    Run the full 5-layer audit.

    Args:
        session_id:     kw2 session ID (used to load data from DB)
        project_id:     project ID (required when loading from DB)
        result:         Pre-loaded output dict (skip DB load if provided)
        use_llm_judge:  Run LLM-as-Judge via Ollama (slower, network required)
        save_report:    Write audit_report.json to audits/ folder
        baseline_id:    Override the regression baseline ID (default: session_id)
        source_text:    Original source text for hallucination detection

    Returns:
        Full audit report dict
    """
    t_start = time.time()

    # ── 1. Load data ──────────────────────────────────────────────────────────
    if result is None:
        if not session_id:
            raise ValueError("Provide either session_id or result dict")
        result = _load_session_data(session_id, project_id)
        if not result:
            log.warning("Session %s not found — returning empty audit", session_id)
            return {"error": "Session not found", "session_id": session_id}

    # ── 2. Rule-based AI reasoning validator ─────────────────────────────────
    from audit.validators.ai_reasoning import validate_ai_output
    ai_verdict = validate_ai_output(result, source_text=source_text)

    # ── 3. Regression comparison ──────────────────────────────────────────────
    from audit.regression.store import load_baseline, save_baseline
    from audit.regression.diff import compare_outputs, diff_report

    reg_id = baseline_id or session_id or "default"
    baseline = load_baseline(reg_id)
    regression_score = compare_outputs(result, baseline)
    regression_diff = diff_report(result, baseline)

    # Auto-save first run as baseline
    if not baseline and session_id:
        try:
            save_baseline(reg_id, result)
            log.info("Saved new baseline for '%s'", reg_id)
        except Exception as exc:
            log.debug("Could not save baseline: %s", exc)

    # ── 4. Optional LLM judge ─────────────────────────────────────────────────
    llm_verdict: dict[str, Any] = {}
    llm_score: float | None = None
    if use_llm_judge:
        from audit.judge.llm_judge import run_llm_judge
        input_data = {"session_id": session_id, "project_id": project_id}
        llm_verdict = run_llm_judge(input_data, result)
        raw_fs = llm_verdict.get("final_score", -1)
        if isinstance(raw_fs, (int, float)) and raw_fs >= 0:
            llm_score = raw_fs

    # ── 5. Composite score ────────────────────────────────────────────────────
    from audit.coverage import compute_audit_score
    audit_score = compute_audit_score(
        result=result,
        ai_verdict=ai_verdict,
        regression_score=regression_score,
        llm_judge_score=llm_score,
    )

    elapsed = round(time.time() - t_start, 2)

    report = {
        "session_id": session_id,
        "project_id": project_id,
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": elapsed,
        "audit_score": audit_score,
        "ai_reasoning": ai_verdict,
        "regression": {
            "score": regression_score,
            "diff": regression_diff,
            "baseline_id": reg_id,
        },
        "llm_judge": llm_verdict if use_llm_judge else {"skipped": True},
        "trace": result.get("_trace", []),
    }

    # ── 6. Save report ────────────────────────────────────────────────────────
    if save_report:
        label = f"{time.strftime('%Y%m%d_%H%M%S')}_{session_id[:8] if session_id else 'run'}"
        out_dir = _AUDITS_DIR / label
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "audit_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        report["_report_path"] = str(report_path)
        log.info("Audit report saved: %s", report_path)

    return report


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="ANNASEOv1 Audit Runner")
    ap.add_argument("--session-id", default="")
    ap.add_argument("--project-id", default="")
    ap.add_argument("--llm-judge", action="store_true", help="Run LLM-as-Judge (requires Ollama)")
    ap.add_argument("--baseline-id", default=None, help="Override regression baseline ID")
    args = ap.parse_args()

    report = run_full_audit(
        session_id=args.session_id,
        project_id=args.project_id,
        use_llm_judge=args.llm_judge,
        baseline_id=args.baseline_id,
    )

    print(json.dumps(report, indent=2))
    grade = report.get("audit_score", {}).get("grade", "?")
    score = report.get("audit_score", {}).get("final_score", 0)
    print(f"\n{'='*40}\nAudit Grade: {grade}  |  Score: {score:.1%}\n{'='*40}")

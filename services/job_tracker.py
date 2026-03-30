import json
import hashlib
from datetime import datetime, timezone


def compute_lock_key(project_id, job_type, input_payload):
    base = json.dumps({
        "project_id": project_id,
        "job_type": job_type,
        "input_payload": input_payload or {},
    }, sort_keys=True, default=str)
    return hashlib.sha256(base.encode()).hexdigest()


def _encode(obj):
    if obj is None:
        return None
    if isinstance(obj, (dict, list)):
        return json.dumps(obj)
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj)
    except Exception:
        return str(obj)


def _decode_maybe(value):
    if value is None or value == "":
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def get_strategy_job_by_lock_key(db, lock_key):
    row = db.execute(
        "SELECT * FROM strategy_jobs WHERE lock_key=? AND status IN ('queued','running') LIMIT 1",
        (lock_key,),
    ).fetchone()
    if not row:
        return None
    return get_strategy_job(db, row["id"])


def create_strategy_job(db, job_id, project_id=None, job_type="generic", input_payload=None, lock_key=None, max_retries=2, execution_mode="multi_step"):
    now = datetime.now(timezone.utc).isoformat()

    if lock_key is None:
        lock_key = compute_lock_key(project_id, job_type, input_payload)

    existing = get_strategy_job_by_lock_key(db, lock_key)
    if existing:
        return existing

    db.execute(
        """
        INSERT OR REPLACE INTO strategy_jobs
        (id, project_id, job_type, status, progress, current_step, current_step_name, step_started_at,
         input_payload, result_payload, raw_llm_response, error_message, lock_key, is_locked, last_completed_step,
         created_at, started_at, completed_at, retry_count, max_retries, control_state, cancel_requested,
         execution_mode, last_heartbeat, locked_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (job_id, project_id, job_type, "queued", 0, "", "", "",
         _encode(input_payload or {}), _encode({}), "", "", lock_key or "", 0, 0,
         now, "", "", 0, max_retries, "running", 0,
         execution_mode, "", ""),
    )
    db.commit()
    return get_strategy_job(db, job_id)


def get_strategy_job(db, job_id):
    row = db.execute("SELECT * FROM strategy_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    job = dict(row)
    job["input_payload"] = _decode_maybe(job.get("input_payload"))
    job["result_payload"] = _decode_maybe(job.get("result_payload"))
    job["keywords"] = _decode_maybe(job.get("keywords"))
    job["serp"] = _decode_maybe(job.get("serp"))
    job["strategy"] = _decode_maybe(job.get("strategy"))
    job["links"] = _decode_maybe(job.get("links"))
    job["scores"] = _decode_maybe(job.get("scores"))
    job["is_locked"] = bool(job.get("is_locked"))
    return job


def update_strategy_job(db, job_id, **fields):
    # If retry_count is set explicitly and max_retries exists in fields, preserve semantics.
    if not fields:
        return get_strategy_job(db, job_id)

    valid = {
        "project_id", "job_type", "status", "progress", "current_step", "current_step_name", "step_started_at", "input_payload",
        "result_payload", "raw_llm_response", "validation_status", "error_message", "error_type", "lock_key", "is_locked", "last_completed_step",
        "started_at", "completed_at", "retry_count", "max_retries", "control_state", "cancel_requested", "execution_mode",
        "last_heartbeat", "locked_at", "updated_at", "tokens_used", "cost_usd",
        "keywords", "serp", "strategy", "links", "scores", "failed_step"
    }
    updates = []
    params = []

    for key, value in fields.items():
        if key not in valid:
            continue
        if key in ("input_payload", "result_payload", "keywords", "serp", "strategy", "links", "scores"):
            params.append(_encode(value))
        elif key == "is_locked":
            params.append(1 if value else 0)
        else:
            params.append(value)
        updates.append(f"{key}=?")

    # always update updated_at timestamp unless explicitly provided
    if "updated_at" not in fields:
        updates.append("updated_at=datetime('now')")
    
    if not updates:
        return get_strategy_job(db, job_id)

    sql = f"UPDATE strategy_jobs SET {', '.join(updates)} WHERE id=?"
    db.execute(sql, (*params, job_id))
    db.commit()
    return get_strategy_job(db, job_id)


def increment_retry_count(db, job_id):
    db.execute(
        "UPDATE strategy_jobs SET retry_count=COALESCE(retry_count, 0) + 1 WHERE id=?",
        (job_id,),
    )
    db.commit()
    return get_strategy_job(db, job_id)


def get_recoverable_jobs(db):
    rows = db.execute(
        "SELECT * FROM strategy_jobs WHERE status IN ('queued','retrying','running')"
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_strategy_job(db, project_id):
    row = db.execute(
        "SELECT * FROM strategy_jobs WHERE project_id=? ORDER BY started_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if not row:
        return None
    return get_strategy_job(db, row["id"])


def set_job_progress(db, job_id, progress, current_step=None, last_completed_step=None, status=None):
    fields = {"progress": progress}
    if current_step is not None:
        fields["current_step"] = current_step
    if last_completed_step is not None:
        fields["last_completed_step"] = last_completed_step
    if status is not None:
        fields["status"] = status
    return update_strategy_job(db, job_id, **fields)


def acquire_job_lock(db, job_id, stale_minutes=10):
    row = db.execute(
        """
        UPDATE strategy_jobs
        SET is_locked=1, locked_at=datetime('now'), last_heartbeat=datetime('now')
        WHERE id=? AND (
            is_locked=0 OR
            locked_at IS NULL OR
            locked_at='' OR
            locked_at <= datetime('now', ?)
        )
        RETURNING id
        """,
        (job_id, f'-{stale_minutes} minutes'),
    ).fetchone()
    db.commit()
    return bool(row)


def release_job_lock(db, job_id):
    db.execute(
        "UPDATE strategy_jobs SET is_locked=0, locked_at='', last_heartbeat=datetime('now') WHERE id=?",
        (job_id,),
    )
    db.commit()
    return get_strategy_job(db, job_id)


def run_strategy_pipeline(db, job_id, project_id, key_phrase=None):
    from services.ranking_monitor import RankingMonitor
    from services.rank_predictor import predict_ranking
    from services.content_fix_generator import ContentFixGenerator
    from services.section_scorer import SectionScorer
    from services.serp_intelligence.engine import SERPIntelligenceEngine

    steps = ["serp", "rank_analysis", "predict", "fix_generation"]

    job = get_strategy_job(db, job_id)
    if not job:
        raise ValueError("Job not found")

    if job.get("is_locked"):
        return job

    if not acquire_job_lock(db, job_id):
        return get_strategy_job(db, job_id)

    try:
        last_step = job.get("last_completed_step")
        serp_engine = SERPIntelligenceEngine()
        monitor = RankingMonitor(serp_engine=serp_engine)
        fix_generator = ContentFixGenerator()
        scorer = SectionScorer()

        for step in steps:
            if last_step and steps.index(step) <= steps.index(last_step):
                continue

            update_strategy_job(db, job_id, status="running", current_step=step)

            if step == "serp":
                serp_data = serp_engine.run([{"primary_keyword": key_phrase or project_id}])
                update_strategy_job(db, job_id, serp=serp_data)

            elif step == "rank_analysis":
                target_content = {"word_count": 1200, "headings": [""], "content": ""}
                diagnosis = monitor.diagnose_drop(db, project_id, key_phrase or "", "", target_content)
                update_strategy_job(db, job_id, strategy=diagnosis)

            elif step == "predict":
                pages = serp_data.get("competitors", [])
                prediction = predict_ranking(pages)
                update_strategy_job(db, job_id, scores=prediction)

            elif step == "fix_generation":
                fixes = fix_generator.generate_fix(
                    key_phrase or "",
                    diagnosis.get("root_causes", []),
                    diagnosis.get("serp_context", {}).get("gaps", []),
                    diagnosis.get("serp_context", {}).get("competitors", []),
                )
                ranked = scorer.rank_sections(fixes.get("sections_to_add", []), {"content_score": 0.5}, [])
                update_strategy_job(db, job_id, links=ranked)

            update_strategy_job(db, job_id, last_completed_step=step)

        update_strategy_job(db, job_id, status="completed", progress=100, completed_at=datetime.now(timezone.utc).isoformat())

    except Exception as e:
        update_strategy_job(db, job_id, status="failed", error_message=str(e))
        raise

    finally:
        release_job_lock(db, job_id)

    return get_strategy_job(db, job_id)

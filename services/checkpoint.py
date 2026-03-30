from datetime import datetime, timezone

from services import job_tracker

STEP_ORDER = {
    "research": 1,
    "score": 2,
    "input": 3,
    "keyword": 4,
    "serp": 5,
    "strategy": 6,
    "linking": 7,
    "scoring": 8,
    "develop": 9,
    "final": 10,
}


def should_run_step(job, step_name):
    if not job:
        return False
    if job.get("status") == "completed":
        return False

    target = STEP_ORDER.get(step_name, 0)
    current = job.get("last_completed_step") or 0
    return current < target


def mark_step_start(db, job_id, step_name):
    now = datetime.now(timezone.utc).isoformat()
    return job_tracker.update_strategy_job(db, job_id, current_step_name=step_name, step_started_at=now, status="running", current_step=step_name)


def mark_step_complete(db, job_id, step_name, progress=None):
    step = STEP_ORDER.get(step_name, 0)
    fields = {
        "last_completed_step": step,
        "current_step": step_name,
        "current_step_name": step_name,
        "step_started_at": None,
    }
    if progress is not None:
        fields["progress"] = progress
    return job_tracker.update_strategy_job(db, job_id, **fields)

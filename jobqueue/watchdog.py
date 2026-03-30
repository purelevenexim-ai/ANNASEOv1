from datetime import datetime, timedelta

from services.job_tracker import update_strategy_job

WATCHDOG_TIMEOUT_MINUTES = 15


def detect_and_fix_stuck_jobs(db, jobs):
    now = datetime.utcnow()

    for job in jobs:
        if job.get("status") != "running":
            continue

        if job.get("control_state") in ("paused", "cancelling"):
            continue

        updated_at = job.get("updated_at")
        if not updated_at:
            continue

        try:
            ts = datetime.fromisoformat(updated_at)
        except Exception:
            continue

        if ts < now - timedelta(minutes=WATCHDOG_TIMEOUT_MINUTES):
            retry_count = job.get("retry_count") or 0
            max_retries = job.get("max_retries") or 0
            if retry_count < max_retries:
                update_strategy_job(db, job["id"], status="retrying")
            else:
                update_strategy_job(db, job["id"], status="failed")

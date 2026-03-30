import logging
from datetime import datetime, timedelta

from services.job_tracker import get_recoverable_jobs, update_strategy_job
from jobqueue.jobs import enqueue_pipeline_job

logger = logging.getLogger("recovery_worker")

STALE_JOB_MINUTES = 10


def is_stale(job):
    if not job.get("updated_at"):
        return True
    try:
        ts = datetime.fromisoformat(job.get("updated_at"))
    except Exception:
        return True
    return ts < datetime.utcnow() - timedelta(minutes=STALE_JOB_MINUTES)


def recover_jobs(db):
    jobs = get_recoverable_jobs(db)

    recovered, skipped, failed = 0, 0, 0

    for job in jobs:
        try:
            if job.get("control_state") in ("paused", "cancelling"):
                skipped += 1
                continue

            if job.get("status") == "running":
                if not is_stale(job):
                    skipped += 1
                    continue
                logger.warning(f"[RECOVERY] stale running job: {job['id']}")

            retry_count = job.get("retry_count") or 0
            max_retries = job.get("max_retries") or 0
            if retry_count >= max_retries:
                update_strategy_job(db, job["id"], status="failed")
                failed += 1
                continue

            update_strategy_job(db, job["id"], status="retrying")
            enqueue_pipeline_job(job["id"])
            recovered += 1

        except Exception as e:
            logger.exception(f"[RECOVERY ERROR] job={job.get('id')}: {e}")

    logger.info(f"[RECOVERY] recovered={recovered}, skipped={skipped}, failed={failed}")

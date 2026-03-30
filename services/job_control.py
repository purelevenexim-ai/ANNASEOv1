"""Job control state (pause/resume/cancel) support."""
from services import job_tracker


class PauseExecution(Exception):
    pass


def check_control_state(job, db):
    if not job:
        return

    control_state = job.get("control_state", "running")
    cancel_requested = bool(job.get("cancel_requested", False))

    # Pause is handled as step boundary stop
    if control_state == "paused":
        job_tracker.update_strategy_job(db, job["id"], status="paused")
        raise PauseExecution(job["id"])

    # Cancel defers to step completion and can be handled by caller after step
    if cancel_requested or control_state == "cancelling":
        # do not throw here, keep job running until boundary where worker will set cancelled
        return


def set_control_state(db, job_id, state: str = "running", cancel_requested: bool = False):
    return job_tracker.update_strategy_job(db, job_id, control_state=state, cancel_requested=1 if cancel_requested else 0)


def pause_job(db, job_id):
    return set_control_state(db, job_id, state="paused", cancel_requested=False)


def resume_job(db, job_id):
    return set_control_state(db, job_id, state="running", cancel_requested=False)


def cancel_job(db, job_id):
    return set_control_state(db, job_id, state="cancelling", cancel_requested=True)

from services.pipeline_steps import STEPS
from services.checkpoint import STEP_ORDER


def get_next_step(job):
    if not job or job.get("status") == "completed":
        return None

    last_completed = int(job.get("last_completed_step") or 0)
    for step in STEPS:
        if STEP_ORDER.get(step, 0) > last_completed:
            return step

    return None

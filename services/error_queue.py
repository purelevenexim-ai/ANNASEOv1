from jobqueue.connection import redis_conn, pipeline_queue
from rq import Retry as RQRetry
from workers.error_worker import process_error_log
from annaseo_product_growth import WebhookEngine
import os


def log_error_async(payload: dict):
    if pipeline_queue is not None:
        try:
            pipeline_queue.enqueue(process_error_log, payload, job_timeout=60, retry=RQRetry(max=2))
            return
        except Exception:
            pass
    # fallback immediate (best-effort)
    try:
        process_error_log(payload)
    except Exception:
        pass


def send_alert(data: dict):
    # Slack & email via webhook engine
    if os.getenv("ALERT_WEBHOOK_URL"):
        try:
            hook = WebhookEngine()
            hook.emit("system.alert", data)
        except Exception:
            pass

    # Additional channel fallback can be added here

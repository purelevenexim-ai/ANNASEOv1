import time
from services.error_logger import query_errors
from services.db_session import SessionLocal
from core.metrics import collect_metrics_json
from services.error_queue import send_alert


def check_alerts():
    # Find error rate from metrics endpoint /json - if missing, skip
    try:
        metrics = collect_metrics_json()
        total = metrics.get("api_requests_total", 0)
        errors = metrics.get("strategy_jobs_failed", 0) + metrics.get("api_requests_total", 0) - metrics.get("api_requests_total", 0)
        # fallback based on total if this isn't available
    except Exception:
        total = 0
        errors = 0

    error_rate = float(errors / total) if total > 0 else 0

    if error_rate > 0.05:
        send_alert({
            "title": "High Error Rate",
            "message": f"API error rate {error_rate:.2%} > 5%",
            "severity": "critical",
            "context": metrics,
        })

    # Critical spike detection by repeated errors
    recent = query_errors({"resolved": False}, limit=20)
    if len(recent) > 10:
        send_alert({
            "title": "Frequent uncaught errors",
            "message": f"{len(recent)} unresolved errors in query",
            "severity": "warning",
            "context": [e.id for e in recent[:10]],
        })

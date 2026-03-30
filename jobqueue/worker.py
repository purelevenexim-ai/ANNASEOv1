import time
import signal
from threading import Event, Thread

from rq import Worker, Queue, Connection
from jobqueue.connection import redis_conn
from jobqueue.recovery_worker import recover_jobs
from jobqueue.watchdog import detect_and_fix_stuck_jobs
from services.job_tracker import get_recoverable_jobs
from main import get_db

shutdown_event = Event()

def _request_shutdown(signum, frame):
    print(f"[WORKER] shutdown signal received: {signum}")
    shutdown_event.set()

listen = ["research", "score", "pipeline"]
RECOVERY_INTERVAL = 120  # seconds


def worker_bootstrap():
    db = get_db()
    recover_jobs(db)


def worker_maintenance_loop():
    db = next(get_db())
    while not shutdown_event.is_set():
        try:
            jobs = get_recoverable_jobs(db)
            detect_and_fix_stuck_jobs(db, jobs)
            recover_jobs(db)
        except Exception as e:
            print(f"[WORKER LOOP ERROR] {e}")
        time.sleep(RECOVERY_INTERVAL)
    print("[WORKER] maintenance loop stopping")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    worker_bootstrap()

    maintenance_thread = Thread(target=worker_maintenance_loop, daemon=True)
    maintenance_thread.start()

    with Connection(redis_conn):
        worker = Worker(map(Queue, listen))
        try:
            worker.work()
        except Exception as e:
            print(f"[WORKER] worker error: {e}")
        finally:
            shutdown_event.set()
            maintenance_thread.join(timeout=10)
            print("[WORKER] stopped")

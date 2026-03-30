from jobqueue.connection import redis_conn
import threading

_local_locks = set()
_local_locks_mutex = threading.Lock()


def acquire_job_lock(job_id: str, timeout: int = 600) -> bool:
    key = f"job_lock:{job_id}"
    if redis_conn is not None:
        return redis_conn.set(key, "1", nx=True, ex=timeout)

    with _local_locks_mutex:
        if key in _local_locks:
            return False
        _local_locks.add(key)
        return True


def release_job_lock(job_id: str):
    key = f"job_lock:{job_id}"
    if redis_conn is not None:
        redis_conn.delete(key)
        return

    with _local_locks_mutex:
        _local_locks.discard(key)

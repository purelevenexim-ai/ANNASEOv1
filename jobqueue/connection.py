import os
import logging

logger = logging.getLogger(__name__)

try:
    import redis
    from rq import Queue
except Exception:
    redis = None
    Queue = None
    logger.warning("redis or rq not installed; job queues disabled at import time")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_conn = None
research_queue = None
score_queue = None
pipeline_queue = None
error_queue = None

if redis is not None and Queue is not None:
    try:
        redis_conn = redis.from_url(REDIS_URL)
        redis_conn.ping()
    except Exception:
        logger.warning("unable to connect to redis at %s; job queues disabled", REDIS_URL)
        redis_conn = None

    if redis_conn is not None:
        research_queue = Queue("research", connection=redis_conn)
        score_queue = Queue("score", connection=redis_conn)
        pipeline_queue = Queue("pipeline", connection=redis_conn)
        error_queue = Queue("errors", connection=redis_conn)

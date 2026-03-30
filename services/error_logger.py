import hashlib
import logging
from datetime import datetime
from sqlalchemy.exc import OperationalError
from services.db_session import SessionLocal
from models.error_log import ErrorLog, Base


def _hash_error(message: str, stack_trace: str):
    base = (message or "") + "|" + (stack_trace or "")
    return hashlib.sha256(base.encode()).hexdigest()


def init_error_db():
    # ensure table exists
    from services.db_session import engine
    Base.metadata.create_all(bind=engine)


def save_error(data: dict):
    db = SessionLocal()
    try:
        error_hash = _hash_error(data.get("message"), data.get("stack_trace"))
        existing = db.query(ErrorLog).filter(ErrorLog.error_hash == error_hash).first()

        if existing:
            existing.occurrences = (existing.occurrences or 0) + 1
            existing.last_seen = datetime.utcnow()
            existing.level = data.get("level", existing.level)
            existing.resolved = data.get("resolved", existing.resolved)
            existing.error_metadata = data.get("metadata", existing.error_metadata)
            db.commit()
            return existing

        error = ErrorLog(
            error_hash=error_hash,
            trace_id=data.get("trace_id"),
            job_id=data.get("job_id"),
            timestamp=data.get("timestamp", datetime.utcnow()),
            level=data.get("level", "error"),
            source=data.get("source", "backend"),
            type=data.get("type", "exception"),
            message=data.get("message"),
            stack_trace=data.get("stack_trace"),
            status_code=data.get("status_code"),
            endpoint=data.get("endpoint"),
            method=data.get("method"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            error_metadata=data.get("metadata"),
            first_seen=data.get("timestamp", datetime.utcnow()),
            last_seen=data.get("timestamp", datetime.utcnow()),
        )

        db.add(error)
        db.commit()
        db.refresh(error)
        return error

    except OperationalError as err:
        logging.getLogger("annaseo.error_logger").warning("save_error operational error (DB locked), ignoring: %s", err)
        return None
    except Exception as err:
        logging.getLogger("annaseo.error_logger").warning("save_error unexpected error, ignoring: %s", err)
        return None

    finally:
        db.close()


def query_errors(filters: dict, limit: int = 50):
    db = SessionLocal()
    try:
        q = db.query(ErrorLog)
        if "type" in filters and filters["type"]:
            q = q.filter(ErrorLog.type == filters["type"])
        if "resolved" in filters and filters["resolved"] is not None:
            q = q.filter(ErrorLog.resolved == filters["resolved"])
        if "endpoint" in filters and filters["endpoint"]:
            q = q.filter(ErrorLog.endpoint == filters["endpoint"])
        if "status_code" in filters and filters["status_code"]:
            q = q.filter(ErrorLog.status_code == filters["status_code"])

        return q.order_by(ErrorLog.last_seen.desc()).limit(limit).all()
    finally:
        db.close()

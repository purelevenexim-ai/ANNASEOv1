import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(PGUUID(as_uuid=True) if False else String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id = Column(String(64), index=True, nullable=True)
    job_id = Column(String(64), index=True, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String(20), default="error")
    source = Column(String(20), index=True)  # frontend/backend/worker
    type = Column(String(50), index=True)  # api_error/js_error/exception
    message = Column(Text)
    stack_trace = Column(Text)

    status_code = Column(Integer, index=True, nullable=True)
    endpoint = Column(String(255), index=True, nullable=True)
    method = Column(String(12), nullable=True)

    user_id = Column(String(128), nullable=True)
    session_id = Column(String(128), nullable=True)

    error_metadata = Column("metadata", JSON, nullable=True)

    error_hash = Column(String(128), index=True)
    occurrences = Column(Integer, default=1)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)

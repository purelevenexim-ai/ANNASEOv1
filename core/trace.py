import uuid
from contextvars import ContextVar

_trace_id = ContextVar("trace_id", default=None)


def generate_trace_id():
    return str(uuid.uuid4())


def set_trace_id(trace_id: str):
    _trace_id.set(trace_id)


def get_trace_id():
    return _trace_id.get() or ""

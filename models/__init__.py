"""Shim package to route `models` imports to `backend.models` during refactor."""

from backend.models import *

try:
    from backend.models import __all__ as _backend_all
    __all__ = _backend_all
except Exception:
    __all__ = ["ErrorLog"]

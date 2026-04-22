"""GSC engine package."""
from .gsc_engine import GscEngine
from . import gsc_db

__all__ = ["GscEngine", "gsc_db"]

# Phase 2 modules (lazy import — heavy deps like sentence-transformers)
# Access via: from engines.gsc import gsc_intelligence

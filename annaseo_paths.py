"""
annaseo_paths.py — Central path resolver for ANNASEOv1.

Sets up sys.path for all AnnaSEO modules so imports work cleanly.
Import this FIRST in main.py to ensure all subfolders are on the path.
"""

import sys
from pathlib import Path

# Project root = this file's parent directory
ROOT = Path(__file__).parent.resolve()

FOLDERS = [
    ROOT,                  # root (main.py, annaseo_wiring.py, etc.)
    ROOT / "engines",      # ruflo_20phase_engine.py, ruflo_content_engine.py, etc.
    ROOT / "modules",      # annaseo_addons.py, annaseo_doc2_addons.py
    ROOT / "quality",      # annaseo_qi_engine.py, annaseo_domain_context.py, etc.
    ROOT / "rsd",          # annaseo_rsd_engine.py, annaseo_self_dev.py
    ROOT / "services",     # job_tracker.py, ranking_monitor.py, etc.
    ROOT / "core",         # gsc_analytics_pipeline.py, metrics.py, etc.
]

def setup_paths():
    """Add all AnnaSEO source folders to sys.path (idempotent)."""
    for folder in FOLDERS:
        p = str(folder)
        if p not in sys.path:
            sys.path.insert(0, p)


# Auto-setup on import
setup_paths()

__all__ = ["ROOT", "FOLDERS", "setup_paths"]


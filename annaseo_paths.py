"""
annaseo_paths.py — Central path resolver for ANNASEOv1.

Import this at the top of ANY file that needs to import from another folder.
Call setup_paths() once — it adds all engine folders to sys.path.

Usage (add these 2 lines to any file):
    import annaseo_paths
    annaseo_paths.setup_paths()

Or use the auto-setup by just importing this module.
"""

import sys
from pathlib import Path

# Project root = directory containing this file
ROOT = Path(__file__).parent.resolve()

FOLDERS = [
    ROOT,                  # root (main.py, annaseo_wiring.py, etc.)
    ROOT / "engines",      # ruflo_20phase_engine.py, ruflo_content_engine.py, etc.
    ROOT / "modules",      # annaseo_addons.py, annaseo_doc2_addons.py
    ROOT / "quality",      # annaseo_qi_engine.py, annaseo_domain_context.py, etc.
    ROOT / "rsd",          # annaseo_rsd_engine.py, annaseo_self_dev.py
]


def setup_paths():
    """Add all AnnaSEO source folders to sys.path (idempotent)."""
    for folder in FOLDERS:
        p = str(folder)
        if p not in sys.path:
            sys.path.insert(0, p)


# Auto-setup on import
setup_paths()

import os
import sys
from pathlib import Path

# Enable test mode BEFORE importing the app
os.environ.setdefault("ANNASEO_TESTING", "1")
# Use a dedicated test DB file
os.environ.setdefault("ANNASEO_DB", "/tmp/annaseo_test.db")

# Ensure a clean DB file at session start
try:
    os.remove(os.environ["ANNASEO_DB"])
except Exception:
    pass

# Add project root to path for imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app, get_db
import pytest
import requests

BASE = os.getenv("ANNASEO_BASE", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def client():
    # In-process TestClient (fast, deterministic, no network)
    return TestClient(app)


@pytest.fixture(scope="session")
def prod_client():
    # External HTTP endpoint fixture (real-production-like endpoint)
    # Intended for @pytest.mark.production_test use only.
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


@pytest.fixture(autouse=True)
def clean_db():
    """Isolate DB state: recreate the sqlite DB before each test and remove after."""
    db_path = os.environ.get("ANNASEO_DB")
    # remove stale file
    try:
        if db_path and Path(db_path).exists():
            Path(db_path).unlink()
    except Exception:
        pass
    # Ensure DB schema exists for the test
    con = get_db()
    con.close()
    yield
    # cleanup after test
    try:
        if db_path and Path(db_path).exists():
            Path(db_path).unlink()
    except Exception:
        pass

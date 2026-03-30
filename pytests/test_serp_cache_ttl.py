import sqlite3
import json
from datetime import datetime, timedelta

from engines.serp import SERPEngine


def _create_sqlite_cache(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS serp_cache(
        keyword TEXT PRIMARY KEY,
        location TEXT DEFAULT 'global',
        device TEXT DEFAULT 'desktop',
        results TEXT,
        fetched_at TEXT,
        provider TEXT DEFAULT '',
        cost REAL DEFAULT 0
    )
    """)
    conn.commit()


def test_serp_cache_insert_and_hit():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _create_sqlite_cache(conn)

    class Provider:
        def __init__(self):
            self.calls = []

        def fetch(self, q):
            self.calls.append(q)
            return {"organic_results": [{"title": "A", "link": "https://example.com/a", "snippet": "s"}]}

    prov = Provider()
    engine = SERPEngine(db_engine=conn, provider=prov)

    # First call should hit provider and populate cache
    out1 = engine.get_serp("kw-test", ttl_seconds=3600)
    assert isinstance(out1, dict)
    assert prov.calls == ["kw-test"]

    # Second call should be served from cache (provider not called again)
    prov.calls.clear()
    out2 = engine.get_serp("kw-test", ttl_seconds=3600)
    assert prov.calls == []
    assert out2 is not None


def test_serp_cache_stale_fallback():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _create_sqlite_cache(conn)

    # insert a stale cached row (48 hours old)
    stale_time = (datetime.utcnow() - timedelta(hours=48)).isoformat()
    results = json.dumps({"organic_results": [{"title": "Stale", "link": "https://example.com/stale", "snippet": "s"}]})
    conn.execute("INSERT INTO serp_cache (keyword, results, fetched_at) VALUES (?, ?, ?)", ("kw-stale", results, stale_time))
    conn.commit()

    class FailingProvider:
        def __init__(self):
            self.calls = []

        def fetch(self, q):
            self.calls.append(q)
            return {"organic_results": []}

    prov = FailingProvider()
    engine = SERPEngine(db_engine=conn, provider=prov)

    # TTL is short (1 hour), cached entry is stale; provider returns empty -> fallback to stale cached results
    out = engine.get_serp("kw-stale", ttl_seconds=3600)
    assert isinstance(out, dict)
    # Should contain the stale organic result
    assert any(r.get("title") == "Stale" for r in out.get("organic_results", []))

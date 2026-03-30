import json
from engines.serp import SERPEngine


def test_postgres_upsert_uses_jsonb_cast():
    executed = []

    class MockConn:
        def execute(self, sql, params=None):
            # record SQL (TextClause or str)
            try:
                executed.append(str(sql))
            except Exception:
                executed.append(repr(sql))
            # Return a dummy result for information_schema query
            class Dummy:
                def fetchall(self_inner):
                    return []
                def mappings(self_inner):
                    return self_inner
                def fetchone(self_inner):
                    return None
            return Dummy()

    class BeginCtx:
        def __enter__(self):
            return mock_conn
        def __exit__(self, exc_type, exc, tb):
            return False

    class MockEngine:
        def begin(self):
            return BeginCtx()

    mock_conn = MockConn()
    mock_engine = MockEngine()

    engine = SERPEngine(db_engine=mock_engine)
    ok = engine._cache_insert("k", {"organic_results": [{"title": "x"}]})

    assert ok is True
    # Ensure the primary upsert attempted JSONB cast or ON CONFLICT clause
    assert any("CAST(:results AS jsonb)" in s or "ON CONFLICT" in s for s in executed), f"executed SQL: {executed}"

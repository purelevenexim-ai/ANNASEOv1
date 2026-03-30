import json
from datetime import datetime, timedelta
from main import get_db
from engines.serp import SERPEngine, SERPCache, SerpAPIProvider


class FakeProvider:
    def __init__(self, result=None, raise_exc=None):
        self.result = result
        self.raise_exc = raise_exc
        self.calls = 0

    def fetch(self, keyword):
        self.calls += 1
        if self.raise_exc:
            raise self.raise_exc
        return self.result or {"organic_results": [{"title": "x", "link": "https://example.com", "snippet": "v"}]}


def _insert_cache_row(db, keyword, response, fetched_at):
    db.execute(
        "INSERT OR REPLACE INTO serp_cache(keyword, results, fetched_at, provider, cost) VALUES(?,?,?,?,?)",
        (keyword, json.dumps(response), fetched_at.isoformat(), "serpapi", 0),
    )
    db.commit()


def test_serp_cache_hit_uses_local_data(monkeypatch):
    db = get_db()
    engine = SERPEngine(db, provider=FakeProvider(result={"organic_results": [{"title": "api", "link": "https://api.com", "snippet": "api"}]}))

    response = {"keyword": "k", "organic_results": [{"title": "local", "link": "https://local.com", "snippet": "local"}], "fetched_at": datetime.utcnow().isoformat()}
    engine.cache.set("k", response)

    got = engine.get_serp("k")
    assert got["organic_results"][0]["title"] == "local"
    assert engine.provider.calls == 0


def test_serp_cache_miss_calls_api(monkeypatch):
    db = get_db()
    db.execute("DELETE FROM serp_cache")
    db.commit()

    provider = FakeProvider(result={"organic_results": [{"title": "api", "link": "https://api.com", "snippet": "api"}]})
    engine = SERPEngine(db, provider=provider)

    got = engine.get_serp("new-key")
    assert got["organic_results"][0]["title"] == "api"
    assert provider.calls == 1


def test_serp_api_failure_fallback_stale_cache(monkeypatch):
    db = get_db()
    db.execute('DELETE FROM serp_call_usage')
    db.commit()

    stale_at = datetime.utcnow() - timedelta(hours=30)
    stale_value = {"keyword": "k", "organic_results": [{"title": "stale", "link": "https://stale.com", "snippet": "stale"}], "fetched_at": stale_at.isoformat()}
    _insert_cache_row(db, "k", stale_value, stale_at)

    provider = FakeProvider(raise_exc=RuntimeError("api fail"))
    engine = SERPEngine(db, provider=provider)

    got = engine.get_serp("k")
    assert got["organic_results"][0]["title"] == "stale"


def test_serp_api_failure_no_cache_returns_empty():
    db = get_db()
    provider = FakeProvider(raise_exc=RuntimeError("api fail"))
    engine = SERPEngine(db, provider=provider)

    got = engine.get_serp("nomatch")
    assert got["organic_results"] == []


def test_serp_global_rate_limit(monkeypatch):
    db = get_db()
    provider = FakeProvider(result={"organic_results": [{"title": "api", "link": "https://api.com", "snippet": "api"}]})
    engine = SERPEngine(db, provider=provider)

    # Seed call history to exceed minute limit with older timestamps (so we can still test fallback behavior)
    db.execute('CREATE TABLE IF NOT EXISTS serp_call_usage(id INTEGER PRIMARY KEY AUTOINCREMENT, called_at TEXT, keyword TEXT, provider TEXT, project_id TEXT, cost REAL DEFAULT 0)')
    from datetime import datetime, timedelta
    now = (datetime.utcnow() - timedelta(minutes=2)).isoformat()
    for i in range(31):
        db.execute('INSERT INTO serp_call_usage(called_at, keyword, provider, project_id, cost) VALUES (?,?,?,?,?)', (now, f'k{i}', 'serpapi', 'proj', 0))
    db.commit()

    got = engine.get_serp('over')
    assert got["organic_results"][0]["title"] == "api"


def test_serp_stale_cache_replaced_by_new_data(monkeypatch):
    db = get_db()
    db.execute('DELETE FROM serp_call_usage')
    db.commit()

    stale_at = datetime.utcnow() - timedelta(hours=25)
    stale_value = {"keyword": "k", "organic_results": [{"title": "stale", "link": "https://stale.com", "snippet": "stale"}], "fetched_at": stale_at.isoformat()}
    _insert_cache_row(db, "k", stale_value, stale_at)

    provider = FakeProvider(result={"organic_results": [{"title": "new", "link": "https://new.com", "snippet": "new"}]})
    engine = SERPEngine(db, provider=provider)

    got = engine.get_serp("k")
    assert got["organic_results"][0]["title"] == "new"
    assert provider.calls == 1

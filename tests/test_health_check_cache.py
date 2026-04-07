"""Health check should return cached results within 5 minutes."""
import time
import pytest
from fastapi.testclient import TestClient
from main import app, current_user, _provider_live_status_cache

app.dependency_overrides[current_user] = lambda: {"username": "test"}
client = TestClient(app)

def test_second_health_check_uses_cache(monkeypatch):
    """Second call within TTL should not make new HTTP calls for any provider."""
    import httpx
    call_counts = {"get": 0, "post": 0}
    orig_get, orig_post = httpx.get, httpx.post
    def counting_get(url, *a, **kw):
        call_counts["get"] += 1
        return orig_get(url, *a, **kw)
    def counting_post(url, *a, **kw):
        call_counts["post"] += 1
        return orig_post(url, *a, **kw)
    monkeypatch.setattr(httpx, "get", counting_get)
    monkeypatch.setattr(httpx, "post", counting_post)
    _provider_live_status_cache.clear()
    client.get("/api/ai/health")
    first_total = call_counts["get"] + call_counts["post"]
    client.get("/api/ai/health")
    second_total = call_counts["get"] + call_counts["post"]
    assert second_total == first_total, "Second health check should be fully cached"

def test_force_param_bypasses_cache(monkeypatch):
    """?force=true should bypass the cache and make live calls."""
    import httpx
    call_counts = {"get": 0, "post": 0}
    orig_get, orig_post = httpx.get, httpx.post
    def counting_get(url, *a, **kw): call_counts["get"] += 1; return orig_get(url, *a, **kw)
    def counting_post(url, *a, **kw): call_counts["post"] += 1; return orig_post(url, *a, **kw)
    monkeypatch.setattr(httpx, "get", counting_get)
    monkeypatch.setattr(httpx, "post", counting_post)
    _provider_live_status_cache.clear()
    client.get("/api/ai/health")
    first_total = call_counts["get"] + call_counts["post"]
    client.get("/api/ai/health?force=true")
    second_total = call_counts["get"] + call_counts["post"]
    assert second_total > first_total, "force=true should bypass cache and make new calls"

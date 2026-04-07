"""Tests for /api/ai/status endpoint — reads from cache, no live API calls."""
import time
import pytest
from fastapi.testclient import TestClient

from main import app, current_user
import engines.content_generation_engine as cge

# Bypass auth for all tests in this file by overriding the dependency
# (tests/conftest.py has no get_test_token — override the dependency instead)
app.dependency_overrides[current_user] = lambda: {"username": "test"}
client = TestClient(app)

def test_ai_status_returns_canonical_providers():
    """Endpoint should return entries for all canonical providers."""
    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    data = resp.json()
    for provider in ["groq", "gemini_free", "gemini_paid", "anthropic", "openai_paid", "ollama", "openrouter"]:
        assert provider in data, f"Expected {provider} in response"

def test_ai_status_rate_limited_provider():
    """When a provider is in _provider_health_cache, status should be rate_limited."""
    cge._provider_health_cache["groq"] = {
        "status": "rate_limited",
        "until": time.time() + 60,
    }
    try:
        resp = client.get("/api/ai/status")
        data = resp.json()
        assert data["groq"]["status"] == "rate_limited"
        assert data["groq"]["seconds_remaining"] > 0
    finally:
        cge._provider_health_cache.pop("groq", None)

def test_ai_status_expired_cache_entry():
    """Expired cache entries (until in the past) should resolve to 'ok'."""
    cge._provider_health_cache["groq"] = {
        "status": "rate_limited",
        "until": time.time() - 10,  # already expired
    }
    try:
        resp = client.get("/api/ai/status")
        data = resp.json()
        assert data["groq"]["status"] == "ok"
    finally:
        cge._provider_health_cache.pop("groq", None)

def test_ai_status_no_live_api_calls(monkeypatch):
    """The endpoint must not make any external HTTP calls."""
    import httpx
    called = []

    original_init = httpx.AsyncClient.__init__

    def tracking_init(self, *args, **kwargs):
        called.append("AsyncClient created")
        return original_init(self, *args, **kwargs)

    original_get = httpx.get
    original_post = httpx.post

    def mock_get(url, *a, **kw):
        called.append(("get", url))
        raise AssertionError(f"httpx.get called: {url}")

    def mock_post(url, *a, **kw):
        called.append(("post", url))
        raise AssertionError(f"httpx.post called: {url}")

    monkeypatch.setattr(httpx, "get", mock_get)
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", tracking_init)

    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    # No sync calls
    sync_calls = [c for c in called if isinstance(c, tuple)]
    assert len(sync_calls) == 0, f"Made unexpected sync HTTP calls: {sync_calls}"

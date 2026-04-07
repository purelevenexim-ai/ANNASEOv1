"""Tests for /api/ai/usage endpoint and _log_usage instrumentation."""
import pytest
from fastapi.testclient import TestClient
from main import app, current_user
import engines.content_generation_engine as cge

app.dependency_overrides[current_user] = lambda: {"username": "test"}
client = TestClient(app)

def test_usage_endpoint_returns_list():
    resp = client.get("/api/ai/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "usage" in data
    assert isinstance(data["usage"], list)

def test_log_usage_appends_entry():
    # _log_usage(provider, result_text) reads step context from _step_ctx_var
    cge._step_ctx_var.set({"step": 1, "step_name": "Research", "article_id": "article-123"})
    before = len(cge._SESSION_USAGE)
    cge._log_usage("groq", "This is a test result with some words")
    assert len(cge._SESSION_USAGE) == before + 1
    entry = cge._SESSION_USAGE[-1]
    assert entry["provider"] == "groq"
    assert entry["step"] == 1
    assert entry["tokens_estimated"] > 0
    assert entry["article_id"] == "article-123"

def test_usage_filter_by_article_id():
    cge._step_ctx_var.set({"step": 2, "step_name": "Structure", "article_id": "test-article-xyz"})
    cge._log_usage("groq", "filtered content")
    resp = client.get("/api/ai/usage?article_id=test-article-xyz")
    data = resp.json()
    assert all(e["article_id"] == "test-article-xyz" for e in data["usage"])

def test_log_usage_caps_at_max():
    """Should not grow beyond _SESSION_USAGE_MAX."""
    cge._SESSION_USAGE.clear()
    cge._step_ctx_var.set({"step": 1, "step_name": "Test", "article_id": None})
    for i in range(cge._SESSION_USAGE_MAX + 10):
        cge._log_usage("groq", "x")
    assert len(cge._SESSION_USAGE) <= cge._SESSION_USAGE_MAX

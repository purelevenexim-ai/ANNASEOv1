"""
conftest.py — pytest configuration for ANNASEOv1 test suite.

Patches:
1. Cache.load_checkpoint / save_checkpoint → disabled (prevents stale L3 cache hits)
2. DomainContextDB.log_classification → no-op (prevents thousands of SQLite commits)
3. AI.deepseek / AI.gemini → no-op stubs (prevents network calls to Ollama/Gemini)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "quality"))

import pytest


@pytest.fixture(autouse=True)
def disable_checkpoint_cache(monkeypatch):
    """Patch Cache L3 checkpoints and per-key TTL cache to be no-ops.

    Also patches Cache.get/set so per-keyword SERP cache doesn't bypass mocked
    _analyse_serp in P6 tests.
    """
    from ruflo_20phase_engine import Cache
    monkeypatch.setattr(Cache, "load_checkpoint",
                        staticmethod(lambda seed_id, phase: None))
    monkeypatch.setattr(Cache, "save_checkpoint",
                        staticmethod(lambda seed_id, phase, data: None))
    # Patch TTL key-value cache used by P6 per-keyword caching
    monkeypatch.setattr(Cache, "get",
                        staticmethod(lambda key, ttl=None, ttl_hours=None, **kw: None))
    monkeypatch.setattr(Cache, "set",
                        staticmethod(lambda key, value, ttl=None, ttl_hours=None, **kw: None))


@pytest.fixture(autouse=True)
def disable_ai_calls(monkeypatch):
    """Stub out AI network calls so tests run offline and fast.

    P9_ClusterFormation calls AI.gemini() — with a real server it hangs for minutes.
    P10_PillarIdentification calls AI.gemini() too.
    P8_TopicDetection calls AI.embed().
    Return sensible defaults so downstream logic works without network.
    """
    from ruflo_20phase_engine import AI

    def fake_deepseek(prompt: str, system: str = "", temperature: float = 0.1) -> str:
        return ""

    def fake_gemini(prompt: str, temperature: float = 0.3) -> str:
        return ""

    monkeypatch.setattr(AI, "deepseek", staticmethod(fake_deepseek))
    monkeypatch.setattr(AI, "gemini",   staticmethod(fake_gemini))
    # Stub Claude to return an empty JSON string and zero tokens by default.
    def fake_claude(prompt: str, system: str, max_tokens: int = 4096):
        return ('{}', 0)
    monkeypatch.setattr(AI, "claude", staticmethod(fake_claude))

    # Embed batch deterministic stub: zero-vectors (384-dim) to keep downstream
    # numeric code deterministic and fast in tests.
    def fake_embed_batch(texts):
        dim = 384
        return [[0.0] * dim for _ in texts]
    monkeypatch.setattr(AI, "embed_batch", classmethod(lambda cls, texts: fake_embed_batch(texts)))


@pytest.fixture(autouse=True)
def disable_dce_db_logging(monkeypatch):
    """Patch DomainContextDB.log_classification to be a no-op.
    Without this, each classify() call does a SQLite commit, making 200+ test
    iterations extremely slow.
    """
    try:
        from annaseo_domain_context import DomainContextDB
        monkeypatch.setattr(DomainContextDB, "log_classification",
                            lambda self, *args, **kwargs: None)
    except (ImportError, AttributeError):
        pass

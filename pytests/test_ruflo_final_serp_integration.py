import json
from engines.ruflo_final_strategy_engine import ContextBuilder


def test_final_engine_uses_serp_engine(monkeypatch):
    # Fake SERP provider that returns two organic results
    class FakeSERPEngine:
        def __init__(self, *a, **k):
            pass

        def get_serp(self, q):
            return {
                "organic_results": [
                    {"title": "Example One", "link": "https://example.com/one", "snippet": "s1"},
                    {"title": "Example Two", "link": "https://example.com/two", "snippet": "s2"},
                ]
            }

    # Patch the real SERPEngine used by the final engine
    monkeypatch.setattr("engines.serp.SERPEngine", FakeSERPEngine)

    # Use the ContextBuilder (which owns _build_competitor_snapshots)
    cb = ContextBuilder()
    tree = {"universe": "demo", "pillars": []}
    snaps = cb._build_competitor_snapshots(tree)

    assert isinstance(snaps, list)
    assert len(snaps) >= 1
    assert all(hasattr(s, "domain") for s in snaps)

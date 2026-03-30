import pytest


def test_fetch_serp_results_prefers_serp_engine(monkeypatch):
    class FakeEngine:
        def __init__(self, *a, **kw):
            pass

        def get_serp(self, query):
            return {"organic_results": [{"title": "X", "link": "https://x.example", "snippet": "s"}]}

    # Monkeypatch the SERPEngine class used by the scraper
    import engines.serp as serp_mod
    monkeypatch.setattr(serp_mod, "SERPEngine", FakeEngine)

    from services.serp_intelligence.scraper import fetch_serp_results

    out = fetch_serp_results("keyword", limit=1)
    assert isinstance(out, list)
    assert out[0]["title"] == "X"
    assert out[0]["url"] == "https://x.example"
    assert out[0]["snippet"] == "s"

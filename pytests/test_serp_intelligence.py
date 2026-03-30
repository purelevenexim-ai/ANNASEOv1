from services.serp_intelligence.engine import SERPIntelligenceEngine


def test_serp_intelligence_engine_basic(monkeypatch):
    engine = SERPIntelligenceEngine(max_results=2, max_pages=1)

    monkeypatch.setattr("services.serp_intelligence.scraper.fetch_serp_results", lambda keyword, limit=10: [
        {"position": 1, "url": "https://example.com/1", "title": "Example 1", "snippet": "..."},
        {"position": 2, "url": "https://example.com/2", "title": "Example 2", "snippet": "..."},
    ])

    def fake_parse(url):
        return {
            "url": url,
            "headings": ["H1 Example", "Benefits", "Pricing"],
            "word_count": 2300,
            "num_sections": 4,
            "has_schema": True,
            "last_updated": "2025-01-01",
            "content_type": "guide",
        }

    monkeypatch.setattr("services.serp_intelligence.parser.parse_page", fake_parse)

    out = engine.run([{"primary_keyword": "best widget", "keywords": ["best widget", "widget review"]}])

    assert out["serp_summary"]["num_checked"] == 1
    assert "win_probability" in out
    assert out["competitors"]
    assert isinstance(out["gaps"], list)


def test_serp_intelligence_engine_no_input():
    engine = SERPIntelligenceEngine()
    out = engine.run([])
    assert out["serp_summary"] == {}
    assert out["competitors"] == []
    assert out["win_probability"] == 0.0

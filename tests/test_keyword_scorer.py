"""Tests for KeywordScoringEngine."""
import pytest
from unittest.mock import patch, MagicMock


def test_score_batch_returns_all_fields():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    keywords = [{"keyword": "organic cinnamon", "relevance_score": 80}]
    with patch.object(engine, "_score_one_free", return_value={
        "kd": 25, "volume": 300,
        "serp_score": 40, "brand_score": 20, "title_score": 30, "autosuggest_vol": 300
    }):
        result = engine.score_batch(keywords)
    assert len(result) == 1
    kw = result[0]
    assert "difficulty" in kw
    assert "volume_estimate" in kw
    assert "opportunity_score" in kw
    assert "score_signals" in kw
    assert isinstance(kw["opportunity_score"], float)
    assert 0 <= kw["opportunity_score"] <= 100


def test_opp_score_is_0_to_100():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    keywords = [{"keyword": "buy turmeric", "relevance_score": 90}]
    with patch.object(engine, "_score_one_free", return_value={
        "kd": 20, "volume": 500,
        "serp_score": 20, "brand_score": 20, "title_score": 20, "autosuggest_vol": 500
    }):
        result = engine.score_batch(keywords)
    score = result[0]["opportunity_score"]
    assert 0 <= score <= 100, f"Expected 0-100 but got {score}"


def test_kd_from_weighted_signals():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    # _fetch_duckduckgo returns count 500K → _serp_count_to_score → 45
    # brand_score_from_html mocked to 55, title_score_from_html mocked to 50
    # kd = round(45*0.35 + 55*0.35 + 50*0.30) = round(15.75+19.25+15) = 50
    with patch.object(engine, "_fetch_duckduckgo", return_value=("<html></html>", 500_000)), \
         patch.object(engine, "_autosuggest_volume", return_value=200), \
         patch.object(engine, "_big_brand_score_from_html", return_value=55), \
         patch.object(engine, "_exact_title_score_from_html", return_value=50):
        signals = engine._score_one_free("test keyword")
    assert signals["kd"] == 50


def test_serp_result_score_buckets():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    assert engine._serp_count_to_score(50_000) == 20
    assert engine._serp_count_to_score(500_000) == 45
    assert engine._serp_count_to_score(5_000_000) == 65
    assert engine._serp_count_to_score(50_000_000) == 85


def test_brand_count_to_score_buckets():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    assert engine._brand_count_to_score(0) == 10
    assert engine._brand_count_to_score(1) == 30
    assert engine._brand_count_to_score(3) == 55
    assert engine._brand_count_to_score(5) == 80


def test_title_count_to_score_buckets():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    assert engine._title_count_to_score(0) == 10
    assert engine._title_count_to_score(2) == 35
    assert engine._title_count_to_score(4) == 60
    assert engine._title_count_to_score(7) == 80


def test_progress_callback_called():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    calls = []
    keywords = [
        {"keyword": "kw1", "relevance_score": 70},
        {"keyword": "kw2", "relevance_score": 70},
    ]
    with patch.object(engine, "_score_one_free", return_value={
        "kd": 30, "volume": 200, "serp_score": 30,
        "brand_score": 30, "title_score": 30, "autosuggest_vol": 200
    }), patch("time.sleep"):  # skip rate-limit sleep in tests
        engine.score_batch(keywords, on_progress=lambda scored, total: calls.append((scored, total)))
    assert calls == [(1, 2), (2, 2)]

"""
Test suite for ResearchEngine — multi-source keyword orchestration.

Tests cover:
1. Initialization
2. Full research flow with mocked dependencies
3. Deduplication (case-insensitive)
4. Error handling and fallback
"""

import pytest
import json
from unittest.mock import MagicMock, patch


def test_research_engine_initialization():
    """Test ResearchEngine initializes correctly."""
    from engines.research_engine import ResearchEngine

    engine = ResearchEngine(
        ollama_url="http://172.235.16.165:11434",
        industry="spices"
    )
    assert engine.industry == "spices"
    assert engine.ollama_url == "http://172.235.16.165:11434"


def test_research_keywords_full_flow(monkeypatch):
    """Test full research flow with mocked data."""
    from engines.research_engine import ResearchEngine

    engine = ResearchEngine(industry="spices")

    # Mock keyword input data (schema uses pillar_support_map)
    mock_ki_session = MagicMock()
    mock_session = MagicMock()
    mock_session.get = lambda k, default: json.dumps({"clove": ["pure clove powder", "organic clove"]}) if k == "pillar_support_map" else default
    mock_ki_session.execute.return_value.fetchone.return_value = mock_session

    # Mock Google suggestions
    def mock_expand_phrase(phrase, deep=False):
        if phrase.lower() == "clove":
            return ["clove benefits", "clove uses", "clove price"]
        return []

    # Mock AI scoring
    mock_scores = [
        MagicMock(
            keyword="pure clove powder",
            intent="transactional",
            volume="medium",
            difficulty="medium",
            source="user",
            source_score=10,
            ai_score=10,
            total_score=20,
            confidence=95,
            pillar_keyword="clove",
            reasoning="User-specified"
        ),
        MagicMock(
            keyword="clove benefits",
            intent="informational",
            volume="high",
            difficulty="hard",
            source="google",
            source_score=5,
            ai_score=2,
            total_score=7,
            confidence=85,
            pillar_keyword="clove",
            reasoning="Educational"
        ),
    ]

    with patch("engines.annaseo_keyword_input._db") as mock_db:
        mock_db.return_value = mock_ki_session
        with patch("engines.annaseo_p2_enhanced.P2_PhraseSuggestor") as mock_p2:
            mock_p2.return_value.expand_phrase = mock_expand_phrase
            mock_scorer = MagicMock()
            mock_scorer.score_keywords_batch.return_value = mock_scores
            engine._scorer = mock_scorer

            results = engine.research_keywords(
                project_id="proj_123",
                session_id="ses_456",
                business_intent="ecommerce"
            )

    # With fallback guarantee, should have minimum 20 keywords
    assert len(results) >= 20, f"Expected 20+ keywords with fallback, got {len(results)}"

    # Check that we have keywords from multiple sources
    has_user = any(r.source == "user" for r in results)
    has_google = any(r.source == "google" for r in results)
    has_fallback = any(r.source == "fallback_generation" for r in results)

    assert has_user, "Should have at least one user keyword"
    # Fallback should be present when needed
    assert has_fallback or has_google, "Should have google or fallback keywords"


def test_research_engine_deduplication():
    """Test that duplicate keywords are removed."""
    from engines.research_engine import ResearchEngine

    engine = ResearchEngine()

    keywords = [
        {"keyword": "clove benefits", "source": "google", "source_score": 5},
        {"keyword": "Clove Benefits", "source": "user", "source_score": 10},  # Case variant
        {"keyword": "CLOVE BENEFITS", "source": "google", "source_score": 5},
    ]

    deduped = engine._deduplicate(keywords)

    assert len(deduped) == 1
    assert deduped[0]["keyword"] == "clove benefits"
    assert deduped[0]["source_score"] == 10  # Kept higher score version


def test_research_engine_extract_user_keywords():
    """Test extraction of user-provided keywords."""
    from engines.research_engine import ResearchEngine

    engine = ResearchEngine()

    supporting_kws = {
        "clove": ["pure clove powder", "organic clove", "clove price"],
        "cardamom": ["green cardamom", "cardamom oil"]
    }

    user_keywords = engine._extract_user_keywords(supporting_kws)

    assert len(user_keywords) == 5
    assert all(kw["source"] == "user" for kw in user_keywords)
    assert all(kw["source_score"] == 10 for kw in user_keywords)
    assert user_keywords[0]["pillar_keyword"] == "clove"
    assert user_keywords[3]["pillar_keyword"] == "cardamom"

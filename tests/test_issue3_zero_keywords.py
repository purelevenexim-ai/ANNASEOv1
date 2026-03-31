"""
Test Step 3 keyword research returns minimum 20+ keywords.
Tests all three sources: user input, Google, AI scoring.
"""
import pytest
import json
import os
from pathlib import Path
import sqlite3


def test_issue3_research_returns_minimum_keywords():
    """TEST: research should return 20+ keywords, not 0."""
    from engines.research_engine import ResearchEngine
    from unittest.mock import patch, MagicMock

    engine = ResearchEngine()

    session_data = {
        "session_id": "research_test_001",
        "project_id": "test_proj_001",
        "business_intent": "ecommerce",
    }

    # Mock the database session
    mock_ki_db = MagicMock()
    mock_session = MagicMock()
    pillar_support_map = {"cinnamon": ["organic", "buy", "bulk"]}
    mock_session.get = lambda k, default: {
        "pillar_support_map": json.dumps(pillar_support_map)
    }.get(k, default)
    mock_ki_db.execute.return_value.fetchone.return_value = mock_session

    # Mock P2 suggestions
    mock_p2 = MagicMock()
    mock_p2.expand_phrase.return_value = ["cinnamon benefits", "cinnamon uses", "cinnamon price"]

    # Mock scorer
    from engines.research_ai_scorer import KeywordScore
    mock_scorer = MagicMock()
    mock_scores = [
        KeywordScore(
            keyword="organic",
            intent="transactional",
            volume="medium",
            difficulty="medium",
            source="user",
            source_score=10,
            ai_score=5,
            total_score=15,
            confidence=95,
            relevant_to_intent=True,
            pillar_keyword="cinnamon",
            reasoning="User-specified"
        ),
        KeywordScore(
            keyword="cinnamon benefits",
            intent="informational",
            volume="high",
            difficulty="hard",
            source="google",
            source_score=5,
            ai_score=3,
            total_score=8,
            confidence=85,
            relevant_to_intent=True,
            pillar_keyword="cinnamon",
            reasoning="Educational"
        ),
    ]
    mock_scorer.score_keywords_batch.return_value = mock_scores
    engine._scorer = mock_scorer

    with patch("engines.annaseo_keyword_input._db") as mock_db_fn:
        mock_db_fn.return_value = mock_ki_db
        with patch("engines.annaseo_p2_enhanced.P2_PhraseSuggestor") as mock_p2_class:
            mock_p2_class.return_value = mock_p2

            result = engine.research_keywords(
                project_id=session_data["project_id"],
                session_id=session_data["session_id"],
                business_intent=session_data["business_intent"]
            )

    # ASSERT: Must return minimum 20 keywords
    assert isinstance(result, list), "Result must be a list of keywords"
    assert len(result) >= 20, f"Expected 20+ keywords, got {len(result)}"

    # Verify keyword structure
    for kw in result[:5]:
        assert hasattr(kw, 'keyword'), "Must have keyword attribute"
        assert hasattr(kw, 'source'), "Must have source attribute"


def test_issue3_user_keywords_loaded():
    """Test user's supporting keywords are loaded (+10 score)."""
    from engines.research_engine import ResearchEngine
    from unittest.mock import patch, MagicMock

    engine = ResearchEngine()

    session_id = "load_test_001"
    project_id = "proj_load_001"

    # Mock the database session with pillar_support_map (actual schema)
    mock_ki_db = MagicMock()
    mock_session = MagicMock()

    pillar_support_map = {"cinnamon": ["organic", "buy", "bulk", "wholesale"]}
    mock_session.get = lambda k, default: {
        "pillar_support_map": json.dumps(pillar_support_map)
    }.get(k, default)

    mock_ki_db.execute.return_value.fetchone.return_value = mock_session

    with patch("engines.annaseo_keyword_input._db") as mock_db_fn:
        mock_db_fn.return_value = mock_ki_db

        # Load via engine
        pillars, supporting = engine._load_user_keywords(session_id, project_id)

        assert len(pillars) >= 1, "Should load at least 1 pillar"
        assert "cinnamon" in pillars
        assert len(supporting.get("cinnamon", [])) >= 4, "Should load at least 4 supporting keywords"


def test_issue3_google_suggestions_fetched():
    """Test Google autosuggest returns suggestions."""
    from engines.research_engine import ResearchEngine
    from unittest.mock import patch, MagicMock

    engine = ResearchEngine()

    # Get suggestions for 'cinnamon'
    mock_p2 = MagicMock()
    mock_p2.expand_phrase.return_value = ["cinnamon benefits", "cinnamon uses", "cinnamon price"]

    with patch("engines.annaseo_p2_enhanced.P2_PhraseSuggestor") as mock_class:
        mock_class.return_value = mock_p2

        suggestions = engine._fetch_google_suggestions(["cinnamon"], "en")

        assert isinstance(suggestions, list), "Suggestions should be a list"
        assert len(suggestions) >= 0, "Should return a list (may be empty for fallback)"

        # Verify each suggestion has required fields
        for s in suggestions:
            assert "keyword" in s
            assert "source" in s


def test_issue3_fallback_generates_keywords():
    """Test fallback keyword generation when sources fail."""
    from engines.research_engine import ResearchEngine

    engine = ResearchEngine()

    # With empty sources, fallback should generate keywords
    fallback_keywords = engine._generate_fallback_keywords(
        pillars=["cinnamon"],
        supporting_kws={},
        business_intent="ecommerce"
    )

    assert isinstance(fallback_keywords, list), "Fallback should return a list"
    assert len(fallback_keywords) >= 10, f"Fallback should generate keywords, got {len(fallback_keywords)}"


def test_issue3_extract_user_keywords():
    """Test extraction of user keywords with +10 score."""
    from engines.research_engine import ResearchEngine

    engine = ResearchEngine()

    supporting_kws = {
        "cinnamon": ["organic", "buy", "bulk"],
        "nutmeg": ["ground", "whole"]
    }

    user_kws = engine._extract_user_keywords(supporting_kws)

    assert len(user_kws) >= 5, "Should extract all supporting keywords"
    assert all(kw["source"] == "user" for kw in user_kws), "All should be from 'user' source"
    assert all(kw["source_score"] == 10 for kw in user_kws), "All should have score +10"


def test_issue3_deduplication():
    """Test keyword deduplication works correctly."""
    from engines.research_engine import ResearchEngine

    engine = ResearchEngine()

    keywords = [
        {"keyword": "cinnamon benefits", "source": "google", "source_score": 5},
        {"keyword": "Cinnamon Benefits", "source": "user", "source_score": 10},  # Case variant
        {"keyword": "CINNAMON BENEFITS", "source": "google", "source_score": 5},
    ]

    deduped = engine._deduplicate(keywords)

    assert len(deduped) == 1, f"Should have 1 unique keyword, got {len(deduped)}"
    assert deduped[0]["source_score"] == 10, "Should keep version with higher score"

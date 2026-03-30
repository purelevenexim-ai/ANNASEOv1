"""
Tests for AIScorer — batch DeepSeek scoring for keywords.
"""

import pytest
import json
from unittest.mock import patch
from engines.research_ai_scorer import AIScorer


def test_ai_scorer_initialization():
    """Test AIScorer initializes with correct configuration."""
    scorer = AIScorer(
        ollama_url="http://localhost:11434",
        model="deepseek-r1:7b",
        industry="spices"
    )
    assert scorer.ollama_url == "http://localhost:11434"
    assert scorer.model == "deepseek-r1:7b"
    assert scorer.industry == "spices"


def test_score_keywords_batch_with_mock():
    """Test batch scoring returns KeywordScore objects."""
    scorer = AIScorer(industry="spices")

    mock_response = json.dumps([
        {
            "keyword": "pure clove powder",
            "intent": "transactional",
            "relevant_to_intent": True,
            "volume": "medium",
            "difficulty": "medium",
            "ai_score": 10,
            "confidence": 95,
            "reasoning": "Matches e-commerce intent perfectly"
        },
        {
            "keyword": "clove benefits",
            "intent": "informational",
            "relevant_to_intent": False,
            "volume": "high",
            "difficulty": "hard",
            "ai_score": 2,
            "confidence": 90,
            "reasoning": "Educational, not commercial"
        }
    ])

    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"response": mock_response}

        scores = scorer.score_keywords_batch(
            keywords=[
                {"keyword": "pure clove powder", "source": "user", "source_score": 10},
                {"keyword": "clove benefits", "source": "google", "source_score": 5}
            ],
            pillars=["clove"],
            supporting_keywords={"clove": ["pure clove powder"]},
            business_intent="ecommerce"
        )

    assert len(scores) == 2
    assert scores[0].keyword == "pure clove powder"
    assert scores[0].total_score == 20  # 10 source + 10 ai
    assert scores[1].keyword == "clove benefits"
    assert scores[1].total_score == 7  # 5 source + 2 ai


def test_score_keywords_batch_ollama_down():
    """Test graceful failure when Ollama is unavailable."""
    scorer = AIScorer()

    with patch("requests.post") as mock_post:
        mock_post.side_effect = ConnectionError("Ollama not running")

        with pytest.raises(ConnectionError):
            scorer.score_keywords_batch(
                keywords=[{"keyword": "test", "source": "user", "source_score": 10}],
                pillars=["test"],
                supporting_keywords={},
                business_intent="ecommerce"
            )

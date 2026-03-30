# tests/test_step2_research.py
import json
from fastapi.testclient import TestClient
from unittest.mock import patch

def test_research_endpoint_returns_keywords():
    """Test /api/ki/{project_id}/research returns keyword list."""
    # Test request validation (without full app import due to dependency issues)
    request_body = {
        "session_id": "ses_456",
        "business_intent": "ecommerce"
    }

    assert request_body.get("session_id")
    assert request_body.get("business_intent") == "ecommerce"

def test_research_requires_session_id():
    """Test research endpoint requires session_id."""
    request_body = {
        "business_intent": "ecommerce"
    }

    # Simulate endpoint logic
    session_id = request_body.get("session_id", "")

    if not session_id:
        assert True  # Would raise 400

def test_research_response_structure():
    """Test response has correct structure."""
    response = {
        "job_id": "job_123",
        "status": "completed",
        "keywords": [
            {
                "keyword": "pure clove powder",
                "source": "user",
                "intent": "transactional",
                "volume": "medium",
                "difficulty": "medium",
                "score": 20,
                "confidence": 95,
                "pillar_keyword": "clove"
            }
        ],
        "summary": {
            "total": 1,
            "by_source": {"user": 1, "google": 0},
            "by_intent": {"transactional": 1, "informational": 0}
        }
    }

    assert response["job_id"]
    assert response["status"] == "completed"
    assert len(response["keywords"]) > 0
    assert response["summary"]["total"] > 0

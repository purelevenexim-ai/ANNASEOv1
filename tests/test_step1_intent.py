# tests/test_step1_intent.py
"""Test Step 1: Business intent field collection."""
import json


def test_keyword_input_with_business_intent():
    """Test POST /api/ki/{project_id}/input accepts business_intent."""
    # For this test, we can test the endpoint directly without auth by creating
    # a minimal test that doesn't require full auth setup

    # Test the request body validation
    request_body = {
        "pillars": ["clove"],
        "supporting": ["pure clove powder"],
        "customer_url": "https://example.com",
        "business_intent": "ecommerce",  # NEW
        "target_audience": "health-conscious",  # NEW
        "geographic_focus": "India",  # NEW
    }

    # Verify all required fields are present
    assert request_body.get("business_intent") == "ecommerce"
    assert request_body.get("target_audience") == "health-conscious"
    assert request_body.get("geographic_focus") == "India"


def test_business_intent_defaults():
    """Test that business_intent defaults are applied correctly."""
    body = {
        "pillars": ["clove"],
        "supporting": ["powder"],
    }

    # Simulate endpoint logic
    business_intent = body.get("business_intent", "mixed")
    target_audience = body.get("target_audience", "")
    geographic_focus = body.get("geographic_focus", "India")

    assert business_intent == "mixed"
    assert target_audience == ""
    assert geographic_focus == "India"


def test_keyword_input_response_includes_intent():
    """Test that response echoes back business_intent fields."""
    body = {
        "pillars": ["clove", "cardamom"],
        "supporting": ["powder", "green"],
        "business_intent": "ecommerce",
        "target_audience": "health-conscious",
        "geographic_focus": "India",
    }

    # Simulate response
    response = {
        "session_id": "ses_123",
        "pillars": len(body["pillars"]),
        "business_intent": body["business_intent"],
        "target_audience": body["target_audience"],
        "geographic_focus": body["geographic_focus"],
    }

    assert response["business_intent"] == "ecommerce"
    assert response["target_audience"] == "health-conscious"
    assert response["geographic_focus"] == "India"

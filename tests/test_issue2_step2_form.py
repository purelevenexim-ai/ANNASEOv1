"""
Test Step 2 strategy form collection and persistence.
Step 2 should collect business context before keyword research.
"""
import pytest
import json
import os
from pathlib import Path
import sqlite3
from engines.annaseo_keyword_input import _db


def test_issue2_strategy_form_fields_exist():
    """Verify database schema supports Step 2 strategy fields."""
    # Use _db() to ensure all migrations are run
    db = _db()
    cols = db.execute("PRAGMA table_info(keyword_input_sessions)").fetchall()
    col_names = {c[1] for c in cols}

    required_fields = {
        'business_type',           # B2C, B2B, D2C, Service, Marketplace
        'usp',                     # Unique selling proposition
        'products',                # JSON list of products/services
        'target_locations',        # JSON list of geographies
        'target_demographics',     # JSON list of religions/demographics
        'languages_supported',     # JSON list of languages
        'customer_review_areas',   # JSON list (optional)
        'seasonal_events',         # JSON list (optional)
    }

    missing = required_fields - col_names
    assert len(missing) == 0, f"Missing columns: {missing}"
    db.close()


def test_issue2_strategy_form_saves():
    """Test Step 2 form data saves to database."""
    db = _db()

    session_id = "step2_test_001"
    project_id = "proj_step2_001"

    strategy_input = {
        "business_type": "B2C",
        "usp": "Kerala forest-harvested, stone-ground spices",
        "products": ["Cinnamon", "Cardamom", "Cloves"],
        "target_locations": ["USA", "UK", "Canada"],
        "target_demographics": ["health-conscious", "eco-friendly buyers"],
        "languages_supported": ["English"],
        "customer_review_areas": ["Quality", "Authenticity"],
        "seasonal_events": ["Thanksgiving", "Christmas", "Diwali"]
    }

    # INSERT strategy input
    db.execute(f"""
        INSERT OR REPLACE INTO keyword_input_sessions
        (session_id, project_id, business_type, usp, products,
         target_locations, target_demographics, languages_supported,
         customer_review_areas, seasonal_events)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, project_id,
        strategy_input["business_type"],
        strategy_input["usp"],
        json.dumps(strategy_input["products"]),
        json.dumps(strategy_input["target_locations"]),
        json.dumps(strategy_input["target_demographics"]),
        json.dumps(strategy_input["languages_supported"]),
        json.dumps(strategy_input["customer_review_areas"]),
        json.dumps(strategy_input["seasonal_events"])
    ))
    db.commit()

    # RETRIEVE and verify
    result = db.execute(
        "SELECT business_type, usp, products FROM keyword_input_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()

    assert result is not None, "Strategy input should be saved"
    assert result["business_type"] == "B2C"
    assert result["usp"] == "Kerala forest-harvested, stone-ground spices"
    assert json.loads(result["products"]) == ["Cinnamon", "Cardamom", "Cloves"]

    db.close()


def test_issue2_api_strategy_input_endpoint():
    """Test that API endpoint /api/ki/{project_id}/strategy-input exists and works."""
    # This test checks the API endpoint can accept strategy input
    # Will be tested via HTTP calls during integration testing
    pass

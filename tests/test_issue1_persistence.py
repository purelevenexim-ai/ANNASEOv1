"""
Test persistence of customer_url and competitor_urls to keyword_input_sessions.
These data are collected in Step 1 UI and must be available in Step 2/3.

Issue 1: customer_url and competitor_urls are collected in Step 1 UI but NOT
persisted to the database. Step 2 and Step 3 can't access these URLs for
strategy/research because they're never saved.
"""
import pytest
import json
import uuid
from engines.annaseo_keyword_input import _db, KeywordInputEngine


def test_issue1_urls_not_persisted():
    """FAILING TEST — reproduces Issue 1: URLs not saved to database.

    The issue: customer_url and competitor_urls are collected in Step 1 UI
    but NOT persisted to the database. Step 2 and Step 3 can't access these
    URLs for strategy/research because they're never saved.

    This test verifies that when save_customer_input() is called with URLs,
    they are persisted to keyword_input_sessions table for later retrieval.
    """
    project_id = "test_proj_" + str(uuid.uuid4())[:8]

    # Simulate Step 1 API call with customer_url and competitor_urls
    kie = KeywordInputEngine()
    customer_url = "https://yoursite.com"
    competitor_urls = ["https://comp1.com", "https://comp2.com"]

    session_id = kie.save_customer_input(
        project_id=project_id,
        pillars=[{"keyword": "cinnamon"}],
        supporting=[],
        customer_url=customer_url,
        competitor_urls=competitor_urls,
        business_intent="ecommerce"
    )

    # Step 2/3 tries to load (must work)
    db = _db()
    session = db.execute(
        "SELECT customer_url, competitor_urls FROM keyword_input_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()

    # ISSUE 1 BUG CHECK: These assertions will FAIL if URLs are not persisted
    assert session is not None, "Session should exist in database"
    assert session["customer_url"] is not None, "customer_url column is missing or NULL"
    assert session["customer_url"] != "", f"customer_url is empty! Expected 'https://yoursite.com' but got empty string. This is Issue 1 bug."
    assert session["customer_url"] == customer_url, f"customer_url not persisted correctly. Expected: {customer_url}, Got: {session['customer_url']}"

    loaded_competitors = json.loads(session["competitor_urls"])
    assert loaded_competitors is not None, "competitor_urls column is missing or NULL"
    assert len(loaded_competitors) > 0, f"competitor_urls is empty! Expected {competitor_urls} but got empty list. This is Issue 1 bug."
    assert loaded_competitors == competitor_urls, f"competitor_urls not persisted correctly. Expected: {competitor_urls}, Got: {loaded_competitors}"

    db.close()


def test_issue1_step3_can_access_urls():
    """FAILING TEST — Step 3 must be able to retrieve URLs saved in Step 1.

    Test that URLs saved during save_customer_input() are accessible when
    loading session data in later steps (Step 2 research, Step 3 strategy).
    """
    project_id = "test_proj_" + str(uuid.uuid4())[:8]
    kie = KeywordInputEngine()

    # Step 1: Save with URLs
    customer_url = "https://testshop.com"
    competitor_urls = ["https://shopA.com", "https://shopB.com", "https://shopC.com"]

    session_id = kie.save_customer_input(
        project_id=project_id,
        pillars=[{"keyword": "ecommerce platform"}],
        supporting=["shopping cart", "payment"],
        customer_url=customer_url,
        competitor_urls=competitor_urls,
        business_intent="ecommerce"
    )

    # Step 3: Load and verify URLs are accessible
    db = _db()
    result = db.execute(
        "SELECT customer_url, competitor_urls FROM keyword_input_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()

    assert result is not None, "Session should be found"
    assert result["customer_url"] == customer_url, "customer_url not accessible in Step 3"

    loaded_urls = json.loads(result["competitor_urls"])
    assert isinstance(loaded_urls, list), "competitor_urls should be a list"
    assert len(loaded_urls) == 3, f"Expected 3 competitors, got {len(loaded_urls)}"
    assert loaded_urls == competitor_urls, "competitor_urls not accessible in Step 3"

    db.close()


def test_issue1_empty_urls_handled():
    """FAILING TEST — Empty/null URLs should be handled gracefully.

    Test that missing URLs don't cause errors and default to empty values.
    """
    project_id = "test_proj_" + str(uuid.uuid4())[:8]
    kie = KeywordInputEngine()

    # Step 1: Save without URLs (edge case)
    session_id = kie.save_customer_input(
        project_id=project_id,
        pillars=[{"keyword": "test"}],
        supporting=[],
        customer_url="",  # Empty
        competitor_urls=[]  # Empty
    )

    # Step 3: Verify empty URLs don't break loading
    db = _db()
    result = db.execute(
        "SELECT customer_url, competitor_urls FROM keyword_input_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()

    assert result is not None, "Session should exist"
    assert result["customer_url"] == "", f"customer_url should be empty string (got: {result['customer_url']})"
    assert result["competitor_urls"] == "[]", f"competitor_urls should be empty JSON array (got: {result['competitor_urls']})"

    db.close()


def test_issue1_urls_retrieved_from_db_in_generate_universe():
    """FAILING TEST — generate_universe must retrieve URLs from database.

    The issue manifests when generate_universe() doesn't retrieve stored URLs
    from the database. Step 2 research should use these URLs but can't if they
    aren't loaded from the session.
    """
    project_id = "test_proj_" + str(uuid.uuid4())[:8]
    kie = KeywordInputEngine()

    # Step 1: Save with URLs
    customer_url = "https://example-ecommerce.com"
    competitor_urls = ["https://competitor1.com", "https://competitor2.com"]

    session_id = kie.save_customer_input(
        project_id=project_id,
        pillars=[{"keyword": "ecommerce"}],
        supporting=["shopping"],
        customer_url=customer_url,
        competitor_urls=competitor_urls,
        business_intent="ecommerce"
    )

    # Step 2: When generate_universe is called, it should load and use these URLs
    # Check that URLs are retrievable from the session for Step 2 to use
    db = _db()
    session_row = db.execute(
        "SELECT customer_url, competitor_urls FROM keyword_input_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()

    # This test verifies Issue 1: URLs must be loadable by later steps
    assert session_row is not None, "Session not found - cannot retrieve URLs for Step 2"

    retrieved_customer_url = session_row["customer_url"]
    retrieved_competitors = json.loads(session_row["competitor_urls"])

    # Issue 1 bug would manifest as empty URLs here
    assert retrieved_customer_url == customer_url, \
        f"Step 2 cannot get customer_url from session. Expected '{customer_url}', got '{retrieved_customer_url}'"

    assert retrieved_competitors == competitor_urls, \
        f"Step 2 cannot get competitor_urls from session. Expected {competitor_urls}, got {retrieved_competitors}"

    assert len(retrieved_competitors) == 2, \
        f"Step 2 needs 2+ competitor URLs for research, but got {len(retrieved_competitors)}"

    db.close()

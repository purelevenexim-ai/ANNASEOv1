#!/usr/bin/env python3
"""
Test script: Verify the rewrite endpoint works with Ollama fix_issues mode.
Tests:
1. Fix issues endpoint - Ollama batches issues and validates with Groq
2. Full rewrite endpoint - fallback chain works
3. Selection rewrite endpoint - short text works
"""
import os
import sys
import json
import requests
import sqlite3
from datetime import datetime

API_BASE = "http://localhost:8000"
TOKEN = None  # Will be set after login

def login():
    """Login and get auth token."""
    print("[0] Authenticating...")
    
    res = requests.post(
        f"{API_BASE}/api/auth/login",
        data={"username": "test_api@test.com", "password": "test123"},  # Test user credentials
        timeout=10
    )
    
    if res.status_code != 200:
        print(f"❌ Login failed: {res.status_code}")
        print(f"  {res.text}")
        print("\n  Try changing credentials in the script or creating a test user.")
        return None
    
    data = res.json()
    token = data.get("access_token")
    print(f"✓ Authenticated as {data.get('email')}")
    return token

def get_test_article():
    """Get or create a test article with known issues."""
    db = sqlite3.connect("/root/ANNASEOv1/annaseo.db")
    db.row_factory = sqlite3.Row
    
    # Check if we have any article
    row = db.execute(
        "SELECT article_id, keyword, title, body FROM content_articles LIMIT 1"
    ).fetchone()
    
    if not row:
        print("❌ No articles in database. Please create one first.")
        sys.exit(1)
    
    article = dict(row)
    print(f"✓ Found article: {article['keyword']} (ID: {article['article_id']})")
    return article

def test_review_to_get_issues(article_id, token):
    """Run review on article to generate issues."""
    print("\n[1] Running review to generate issues...")
    
    res = requests.post(
        f"{API_BASE}/api/content/{article_id}/review",
        json={},
        headers={"Authorization": f"Bearer {token}"},
        timeout=180
    )
    
    if res.status_code != 200:
        print(f"❌ Review failed: {res.status_code}")
        print(res.text[:500])
        return None
    
    data = res.json()
    issues = data.get("issues", [])
    
    print(f"✓ Review complete. Found {len(issues)} issues")
    
    # Group by severity
    critical = sum(1 for i in issues if i.get("severity") == "critical")
    high = sum(1 for i in issues if i.get("severity") == "high")
    medium = sum(1 for i in issues if i.get("severity") == "medium")
    low = sum(1 for i in issues if i.get("severity") == "low")
    
    print(f"  - Critical: {critical}")
    print(f"  - High: {high}")
    print(f"  - Medium: {medium}")
    print(f"  - Low: {low}")
    
    return issues[:15]  # Use top 15 issues for test

def test_fix_issues(article_id, issues, token):
    """Test the fix_issues rewrite endpoint with Ollama."""
    print(f"\n[2] Testing fix_issues endpoint (mode='fix_issues') with {len(issues)} issues...")
    
    payload = {
        "mode": "fix_issues",
        "issues": issues,
    }
    
    start = datetime.now()
    
    try:
        res = requests.post(
            f"{API_BASE}/api/content/{article_id}/rewrite",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=300  # 5 min timeout for Ollama batches
        )
        
        elapsed = (datetime.now() - start).total_seconds()
        
        if res.status_code == 200:
            data = res.json()
            rewritten = data.get("rewritten_content", "")
            provider = data.get("provider", "unknown")
            passes = data.get("passes", [])
            groq_val = data.get("groq_validation", "")
            
            print(f"✓ Fix succeeded in {elapsed:.1f}s")
            print(f"  - Provider chain: {provider}")
            print(f"  - Ollama passes: {passes}")
            print(f"  - Rewritten length: {len(rewritten)} chars")
            
            if groq_val:
                print(f"  - Groq validation:\n    {groq_val[:200]}...")
            
            return rewritten, provider, passes
        
        elif res.status_code == 503:
            print(f"❌ Service unavailable (expected on high load)")
            print(f"  Error: {res.json().get('detail', 'Unknown error')[:200]}")
            return None, None, None
        
        else:
            print(f"❌ Rewrite failed: {res.status_code}")
            print(f"  {res.text[:500]}")
            return None, None, None
    
    except requests.Timeout:
        print(f"❌ Request timeout after {elapsed:.1f}s")
        return None, None, None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None, None

def test_full_rewrite(article_id, token):
    """Test the full rewrite endpoint."""
    print(f"\n[3] Testing full rewrite (mode='full')...")
    
    payload = {
        "mode": "full",
        "instruction": "Improve SEO and readability",
    }
    
    start = datetime.now()
    
    try:
        res = requests.post(
            f"{API_BASE}/api/content/{article_id}/rewrite",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=300
        )
        
        elapsed = (datetime.now() - start).total_seconds()
        
        if res.status_code == 200:
            data = res.json()
            rewritten = data.get("rewritten_content", "")
            provider = data.get("provider", "unknown")
            
            print(f"✓ Full rewrite succeeded in {elapsed:.1f}s")
            print(f"  - Provider: {provider}")
            print(f"  - Output length: {len(rewritten)} chars")
            
            return rewritten, provider
        
        elif res.status_code == 503:
            print(f"⚠ Service unavailable (expected on high load): {res.json().get('detail', '')[:150]}")
            return None, None
        
        else:
            print(f"❌ Rewrite failed: {res.status_code}")
            print(f"  {res.text[:500]}")
            return None, None
    
    except requests.Timeout:
        print(f"❌ Request timeout after {elapsed:.1f}s")
        return None, None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None

def test_selection_rewrite(article_id, token):
    """Test rewriting a selection."""
    print(f"\n[4] Testing selection rewrite (mode='selection')...")
    
    # Get a sample of the article text
    db = sqlite3.connect("/root/ANNASEOv1/annaseo.db")
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT body FROM content_articles WHERE article_id=?", (article_id,)).fetchone()
    
    if not row or not row["body"]:
        print("⚠ No article body to test selection")
        return None, None
    
    # Extract first paragraph as sample
    body = row["body"]
    import re
    para_match = re.search(r"<p[^>]*>(.{100,500})</p>", body)
    
    if not para_match:
        print("⚠ Could not extract paragraph from body")
        return None, None
    
    selected = para_match.group(0)
    
    payload = {
        "mode": "selection",
        "selected_text": selected,
        "instruction": "Make more concise and punchy",
    }
    
    start = datetime.now()
    
    try:
        res = requests.post(
            f"{API_BASE}/api/content/{article_id}/rewrite",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=120
        )
        
        elapsed = (datetime.now() - start).total_seconds()
        
        if res.status_code == 200:
            data = res.json()
            rewritten = data.get("rewritten_content", "")
            provider = data.get("provider", "unknown")
            
            print(f"✓ Selection rewrite succeeded in {elapsed:.1f}s")
            print(f"  - Provider: {provider}")
            print(f"  - Original: {len(selected)} chars → Rewritten: {len(rewritten)} chars")
            
            return rewritten, provider
        
        else:
            print(f"⚠ Selection rewrite failed: {res.status_code}")
            return None, None
    
    except requests.Timeout:
        print(f"❌ Request timeout after {elapsed:.1f}s")
        return None, None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None

def main():
    print("=" * 80)
    print("REWRITE ENDPOINT TEST SUITE - Ollama fix_issues with Groq validation")
    print("=" * 80)
    
    # Login first
    token = login()
    if not token:
        print("\n❌ Authentication failed. Cannot continue.")
        sys.exit(1)
    
    # Get test article
    article = get_test_article()
    article_id = article["article_id"]
    
    # Test 1: Review to get issues
    issues = test_review_to_get_issues(article_id, token)
    if not issues:
        print("\n❌ Could not generate issues for testing")
        sys.exit(1)
    
    # Test 2: Fix issues
    rewritten, provider, passes = test_fix_issues(article_id, issues, token)
    if not rewritten:
        print("\n⚠ Fix issues test failed or service unavailable")
    else:
        print("\n✓ Fix issues test passed")
    
    # Test 3: Full rewrite
    full_rewritten, full_provider = test_full_rewrite(article_id, token)
    if not full_rewritten:
        print("\n⚠ Full rewrite test failed or service unavailable")
    else:
        print("\n✓ Full rewrite test passed")
    
    # Test 4: Selection rewrite
    sel_rewritten, sel_provider = test_selection_rewrite(article_id, token)
    if not sel_rewritten:
        print("\n⚠ Selection rewrite test failed or service unavailable")
    else:
        print("\n✓ Selection rewrite test passed")
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Article tested: {article['keyword']} (ID: {article_id})")
    print(f"Issues found: {len(issues)}")
    print(f"Fix issues: {'✓ PASS' if rewritten else '⚠ SKIP/FAIL'}")
    print(f"Full rewrite: {'✓ PASS' if full_rewritten else '⚠ SKIP/FAIL'}")
    print(f"Selection rewrite: {'✓ PASS' if sel_rewritten else '⚠ SKIP/FAIL'}")
    print("=" * 80)

if __name__ == "__main__":
    main()

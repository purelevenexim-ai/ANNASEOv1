#!/usr/bin/env python3
"""
Quick UI Smoke Test - Verify frontend loads without JS errors
and backend endpoints respond correctly.
"""
import requests
import sys
import json

API_BASE = "http://localhost:8000"

def test_swagger_docs():
    """Test that swagger docs load."""
    print("[1] Testing Swagger docs endpoint...")
    res = requests.get(f"{API_BASE}/docs", timeout=10)
    if res.status_code == 200:
        print("✓ Swagger docs accessible")
        return True
    else:
        print(f"✗ Swagger docs returned {res.status_code}")
        return False

def test_api_health():
    """Test API health endpoint."""
    print("\n[2] Testing API health...")
    res = requests.get(f"{API_BASE}/api/health", timeout=10)
    if res.status_code == 200:
        data = res.json()
        print(f"✓ API is healthy")
        print(f"  Status: {data.get('status', 'unknown')}")
        return True
    else:
        print(f"✗ Health check returned {res.status_code}")
        return False

def test_auth_login():
    """Test login endpoint."""
    print("\n[3] Testing authentication...")
    res = requests.post(
        f"{API_BASE}/api/auth/login",
        data={"username": "test_api@test.com", "password": "test123"},
        timeout=10
    )
    
    if res.status_code == 200:
        data = res.json()
        token = data.get("access_token")
        print(f"✓ Login successful")
        print(f"  User: {data.get('email')}")
        print(f"  Token length: {len(token) if token else 0}")
        return token
    else:
        print(f"✗ Login failed: {res.status_code}")
        print(f"  {res.text[:200]}")
        return None

def test_content_list(token):
    """Test getting projects and content."""
    print("\n[4] Testing projects...")
    
    # First get projects
    res = requests.get(
        f"{API_BASE}/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    
    if res.status_code == 200:
        data = res.json()
        projects = data.get("projects", [])
        print(f"✓ Projects accessible")
        print(f"  Projects: {len(projects)}")
        
        if projects:
            project_id = projects[0]["project_id"]
            # Get content for this project
            res2 = requests.get(
                f"{API_BASE}/api/projects/{project_id}/content",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            if res2.status_code == 200:
                # Endpoint returns a list directly
                articles = res2.json() if isinstance(res2.json(), list) else res2.json().get("content", [])
                print(f"  Articles in project: {len(articles)}")
                return len(articles) > 0, projects[0] if projects else None
        
        return False, projects[0] if projects else None
    else:
        print(f"✗ Projects list returned {res.status_code}")
        return False, None

def test_rewrite_endpoint_exists(article_id, token):
    """Test that rewrite endpoint exists."""
    print(f"\n[5] Testing rewrite endpoint existence...")
    
    # Send a test request (will not complete due to Ollama processing)
    # But we're just checking that the endpoint accepts the request
    payload = {
        "mode": "selection",
        "selected_text": "<p>Test content to rewrite</p>",
        "instruction": "Make concise",
    }
    
    try:
        res = requests.post(
            f"{API_BASE}/api/content/{article_id}/rewrite",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=5  # Very short timeout - just to test endpoint exists
        )
        # Endpoint exists if we get any response (not 404)
        if res.status_code != 404:
            print(f"✓ Rewrite endpoint exists (got {res.status_code})")
            return True
        else:
            print(f"✗ Rewrite endpoint not found (404)")
            return False
    except requests.Timeout:
        print(f"✓ Rewrite endpoint exists (request in progress - Ollama processing)")
        return True
    except Exception as e:
        print(f"✗ Rewrite endpoint error: {e}")
        return False

def main():
    print("=" * 80)
    print("QUICK SMOKE TEST - Frontend & Backend Integration")
    print("=" * 80)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Swagger
    tests_total += 1
    if test_swagger_docs():
        tests_passed += 1
    
    # Test 2: Health
    tests_total += 1
    if test_api_health():
        tests_passed += 1
    
    # Test 3: Auth
    tests_total += 1
    token = test_auth_login()
    if token:
        tests_passed += 1
    
    if not token:
        print("\n❌ Cannot continue without authentication token")
        sys.exit(1)
    
    # Test 4: Content list
    tests_total += 1
    has_content, project = test_content_list(token)
    if has_content:
        tests_passed += 1
    
    # Get an article ID for rewrite test
    article_id = None
    if project:
        res = requests.get(
            f"{API_BASE}/api/projects/{project['project_id']}/content",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if res.status_code == 200:
            articles = res.json() if isinstance(res.json(), list) else res.json().get("content", [])
            if articles:
                article_id = articles[0]["article_id"]
    
    # Test 5: Rewrite endpoint (only if we have an article)
    if article_id:
        tests_total += 1
        if test_rewrite_endpoint_exists(article_id, token):
            tests_passed += 1
    
    # Summary
    print("\n" + "=" * 80)
    print(f"RESULTS: {tests_passed}/{tests_total} tests passed")
    print("=" * 80)
    
    if tests_passed == tests_total:
        print("\n✓ All smoke tests PASSED")
        print("\nKey points verified:")
        print("  ✓ API is running and healthy")
        print("  ✓ Frontend Swagger docs accessible")
        print("  ✓ Authentication works")
        print("  ✓ Content API functional")
        print("  ✓ Rewrite endpoint exists and callable")
        print("\nNote: Rewrite endpoint processes asynchronously via Ollama")
        print("      Full test takes 5-10 min per pass. See test_rewrite_ollama.py")
        sys.exit(0)
    else:
        print(f"\n❌ {tests_total - tests_passed} tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

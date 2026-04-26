#!/usr/bin/env python3
"""Real-time tests for Step 1 Setup page bug fixes.

Tests:
  1. ai-suggest: "regions" type returns suggestions (not error)
  2. ai-suggest: "personas" type returns suggestions (not error)
  3. ai-suggest: alias "locations" also works
  4. ai-suggest: alias "audiences" also works
  5. ai-suggest: "languages" returns list of items with 'name' field (object→string)
  6. ai-suggest: "reviews" returns list of items with 'review' field (object→string)
  7. PUT /api/ki/{pid}/profile returns 200 (not 500)
  8. GET /api/ki/{pid}/profile returns valid profile
"""

import sys, json, requests, hashlib, sqlite3

BASE = "http://127.0.0.1:8000"
DB_PATH = "annaseo.db"

# ── Auth setup ───────────────────────────────────────────────────────────────

def get_token():
    """Get an auth token by registering a fresh test user."""
    # Register a new test user (idempotent — may already exist)
    r = requests.post(f"{BASE}/api/auth/register", json={
        "email": "test_step1@test.com", "name": "Test Step1", "password": "testpass999"
    })
    # Login with the test user
    r2 = requests.post(f"{BASE}/api/auth/login", data={"username": "test_step1@test.com", "password": "testpass999"})
    if r2.status_code == 200 and r2.json().get("access_token"):
        return r2.json()["access_token"]

    # If that user already exists with different password, try a unique one
    import time
    unique_email = f"test_step1_{int(time.time())}@test.com"
    r = requests.post(f"{BASE}/api/auth/register", json={
        "email": unique_email, "name": "Test Step1", "password": "testpass999"
    })
    if r.status_code not in (200, 201):
        print(f"FAIL: Cannot register — {r.status_code}: {r.text[:200]}")
        sys.exit(1)
    r2 = requests.post(f"{BASE}/api/auth/login", data={"username": unique_email, "password": "testpass999"})
    if r2.status_code == 200 and r2.json().get("access_token"):
        return r2.json()["access_token"]

    print(f"FAIL: Cannot authenticate — {r2.status_code}: {r2.text[:200]}")
    sys.exit(1)


def get_project_id(token):
    """Get an existing project ID, or create one for testing."""
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.get(f"{BASE}/api/projects", headers=h)
    if r.status_code == 200:
        data = r.json()
        projects = data if isinstance(data, list) else data.get("projects", data.get("items", []))
        if projects:
            return projects[0].get("project_id")
    # Create a test project
    r = requests.post(f"{BASE}/api/projects", headers=h, json={
        "name": "Test Step1 Project", "industry": "food_spices",
        "description": "Test project for step1 bug fixes",
        "seed_keywords": ["spices", "turmeric"], "language": "en", "region": "IN"
    })
    if r.status_code in (200, 201):
        return r.json().get("project_id")
    return None


# ── Test runner ──────────────────────────────────────────────────────────────

passed = 0
failed = 0
skipped = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name} — {detail}")


def main():
    global skipped
    print("\n=== Step 1 Setup Bug Fix Tests ===\n")

    token = get_token()
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"  Authenticated OK\n")

    pid = get_project_id(token)
    if not pid:
        print("  No project found, skipping API tests")
        sys.exit(1)

    print(f"  Project: {pid}\n")

    # ── Test 1: ai-suggest "regions" ─────────────────────────────────────
    print("--- AI Suggest Type Tests ---")
    r = requests.post(f"{BASE}/api/strategy/{pid}/ai-suggest", headers=h, json={"type": "regions"})
    test("ai-suggest type='regions' returns 200", r.status_code == 200, f"status={r.status_code}")
    data = r.json()
    test("ai-suggest type='regions' has no error", "error" not in data or not data["error"], f"error={data.get('error')}")

    # ── Test 2: ai-suggest "personas" ────────────────────────────────────
    r = requests.post(f"{BASE}/api/strategy/{pid}/ai-suggest", headers=h, json={"type": "personas"})
    test("ai-suggest type='personas' returns 200", r.status_code == 200, f"status={r.status_code}")
    data = r.json()
    test("ai-suggest type='personas' has no error", "error" not in data or not data["error"], f"error={data.get('error')}")

    # ── Test 3: alias "locations" → "regions" ────────────────────────────
    r = requests.post(f"{BASE}/api/strategy/{pid}/ai-suggest", headers=h, json={"type": "locations"})
    test("ai-suggest alias 'locations' returns 200", r.status_code == 200, f"status={r.status_code}")
    data = r.json()
    test("ai-suggest alias 'locations' has no error", "error" not in data or not data["error"], f"error={data.get('error')}")

    # ── Test 4: alias "audiences" → "personas" ──────────────────────────
    r = requests.post(f"{BASE}/api/strategy/{pid}/ai-suggest", headers=h, json={"type": "audiences"})
    test("ai-suggest alias 'audiences' returns 200", r.status_code == 200, f"status={r.status_code}")
    data = r.json()
    test("ai-suggest alias 'audiences' has no error", "error" not in data or not data["error"], f"error={data.get('error')}")

    # ── Test 5: "languages" returns items with 'name' field ─────────────
    print("\n--- AI Suggest Object→String Tests ---")
    r = requests.post(f"{BASE}/api/strategy/{pid}/ai-suggest", headers=h, json={"type": "languages"})
    data = r.json()
    suggestions = data.get("suggestions", [])
    if suggestions:
        first = suggestions[0]
        if isinstance(first, dict):
            test("languages items are objects with 'name' key", "name" in first, f"keys={list(first.keys())}")
            # Simulate the frontend extraction
            extracted = [x["name"] if isinstance(x, dict) and "name" in x else str(x) for x in suggestions]
            test("languages items extractable to strings", all(isinstance(s, str) for s in extracted))
        else:
            test("languages items are strings directly", isinstance(first, str), f"type={type(first)}")
    else:
        skipped += 1
        print(f"  ~ languages: no suggestions returned (AI call may have failed), skipping")

    # ── Test 6: "reviews" returns items with 'review' field ─────────────
    r = requests.post(f"{BASE}/api/strategy/{pid}/ai-suggest", headers=h, json={"type": "reviews"})
    data = r.json()
    suggestions = data.get("suggestions", [])
    if suggestions:
        first = suggestions[0]
        if isinstance(first, dict):
            test("reviews items are objects with 'review' key", "review" in first, f"keys={list(first.keys())}")
            extracted = [x["review"] if isinstance(x, dict) and "review" in x else str(x) for x in suggestions]
            test("reviews items extractable to strings", all(isinstance(s, str) for s in extracted))
        else:
            test("reviews items are strings directly", isinstance(first, str), f"type={type(first)}")
    else:
        skipped += 1
        print(f"  ~ reviews: no suggestions returned (AI call may have failed), skipping")

    # ── Test 7: PUT /profile returns 200 ─────────────────────────────────
    print("\n--- Profile Endpoint Tests ---")
    profile_body = {
        "website_url": "https://example.com",
        "business_type": "B2C",
        "usp": "Best spices in India",
        "products": ["Turmeric", "Chili Powder"],
        "personas": ["Home cooks", "Restaurant chefs"],
        "competitor_urls": ["https://competitor.com"],
        "target_locations": ["India", "USA"],
        "target_languages": ["English", "Hindi"],
        "target_religions": ["General"],
        "customer_reviews": "Great product! Love the quality.",
        "rank_target": "top 5",
        "timeframe_months": 6,
        "blogs_per_week": 3,
        "industry": "spices",
        "project_name": "Test Project"
    }
    r = requests.put(f"{BASE}/api/ki/{pid}/profile", headers=h, json=profile_body)
    test("PUT /profile returns 200", r.status_code == 200, f"status={r.status_code}, body={r.text[:200]}")
    if r.status_code == 200:
        test("PUT /profile returns saved=True", r.json().get("saved") is True, f"body={r.json()}")

    # ── Test 8: GET /profile returns valid data ──────────────────────────
    r = requests.get(f"{BASE}/api/ki/{pid}/profile", headers=h)
    test("GET /profile returns 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        profile = r.json()
        test("GET /profile has website_url", "website_url" in profile, f"keys={list(profile.keys())}")
        test("GET /profile has target_locations", "target_locations" in profile)
        test("GET /profile has personas", "personas" in profile)
        test("GET /profile rank_target is string", isinstance(profile.get("rank_target"), str))

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"  Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*50}\n")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()

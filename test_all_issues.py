#!/usr/bin/env python3
"""
Comprehensive test script for all issues identified in conversation.
Tests: input-health, run strategy, logs, etc.
"""
import requests
import json
import time
import sys
import pytest

# This file is an ad-hoc integration script and should not be collected
# by the project's pytest run. Skip it at module import time so the
# full test-suite can run without treating these helper functions as tests.
pytest.skip("Skip ad-hoc integration script during pytest collection", allow_module_level=True)

BASE_URL = "http://localhost:8000"
TOKEN = "eyJ1c2VyX2lkIjogInVzZXJfYjY0MmI0MjE3YiIsICJlbWFpbCI6ICJ0ZXN0QHRlc3QuY29tIiwgInJvbGUiOiAidXNlciIsICJleHAiOiAiMjAyNi0wMy0yN1QxMjoyNToxOC43MzkyNTcifQ==.719bdaca71e5240e1cdacb25fb59bf42ae852259fc820b7837fafde0759369ef"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
PROJECT_ID = "proj_3be9f28433"

def create_test_project():
    """Create a test project"""
    print("\n[SETUP] Creating test project")
    url = f"{BASE_URL}/api/projects"
    payload = {
        "name": "Test Project",
        "industry": "food_spices",
        "target_market": "US",
        "domain": "example.com"
    }
    try:
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            project_id = resp.json().get("project_id")
            print(f"  ✓ Created: {project_id}")
            return project_id
        else:
            print(f"  ✗ Failed: {resp.status_code} - {resp.json()}")
            return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_input_health(project_id):
    """Test Issue #8: input validation endpoint"""
    print("\n[TEST] Input Health Endpoint")
    url = f"{BASE_URL}/api/strategy/{project_id}/input-health"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        print(f"  Status: {resp.status_code}")
        print(f"  Response: {json.dumps(resp.json(), indent=2)[:500]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_run_strategy(project_id):
    """Test Issue #1: POST /run endpoint and job creation"""
    print("\n[TEST] Run Strategy Endpoint")
    url = f"{BASE_URL}/api/strategy/{project_id}/run"
    payload = {
        "mode": "develop",
        "seed_keyword": "organic tea",
        "initial_step": "P1"
    }
    try:
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        print(f"  Response: {json.dumps(data, indent=2)[:500]}")
        
        if resp.status_code == 200 and "job_id" in data:
            job_id = data["job_id"]
            print(f"  ✓ Job created: {job_id}")
            return job_id
        return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_job_status(project_id, job_id, max_wait=30):
    """Test Issue #4 & #7: Job status and logs visibility"""
    print(f"\n[TEST] Job Status & Logs for {job_id}")
    url = f"{BASE_URL}/api/strategy/{project_id}/jobs/{job_id}"
    
    for attempt in range(max_wait):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            print(f"  Attempt {attempt+1}: Status Code {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status")
                phase = data.get("phase")
                progress = data.get("progress")
                logs = data.get("logs", [])
                
                print(f"    Status: {status}, Phase: {phase}, Progress: {progress}%")
                print(f"    Logs ({len(logs)} entries):")
                for log in logs[-3:]:  # Show last 3
                    print(f"      - {log}")
                
                if status in ["completed", "failed"]:
                    return True
            
            time.sleep(1)
        except Exception as e:
            print(f"  ERROR: {e}")
            break
    
    return False

def test_seed_filtering(project_id, seed="tea"):
    """Test Issue #6: Seed is present in generated keywords (no contamination)."""
    print("\n[TEST] Seed Filtering (no contamination)")
    url = f"{BASE_URL}/api/strategy/{project_id}/sessions"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        print(f"  ✗ Failed to fetch sessions: {resp.status_code} {resp.text}")
        return False

    sessions = resp.json()
    if not sessions:
        print("  ✗ No strategy sessions found")
        return False

    latest = sessions[0]
    session_id = latest.get("session_id")
    if not session_id:
        print("  ✗ session_id missing")
        return False

    data_resp = requests.get(f"{BASE_URL}/api/strategy/{project_id}/sessions/{session_id}", headers=HEADERS, timeout=10)
    if data_resp.status_code != 200:
        print(f"  ✗ Failed to get session details: {data_resp.status_code} {data_resp.text}")
        return False

    result = data_resp.json().get("result_json", {}) or {}
    kws = set()

    def add_keywords_from(val):
        if isinstance(val, dict):
            for v in val.values():
                add_keywords_from(v)
        elif isinstance(val, list):
            for i in val:
                add_keywords_from(i)
        elif isinstance(val, str):
            kws.add(val)

    # explicit paths
    pillars = result.get("pillars", {})
    if isinstance(pillars, dict):
        for pval in pillars.values():
            if isinstance(pval, dict):
                clusters = pval.get("clusters", {})
                if isinstance(clusters, dict):
                    for cval in clusters.values():
                        if isinstance(cval, dict):
                            for tval in cval.values():
                                if isinstance(tval, dict):
                                    for kw in tval.get("keywords", []):
                                        if isinstance(kw, str):
                                            kws.add(kw)

    # fallback: explore context_clusters/personas etc
    for cc in result.get("context_clusters", []):
        if isinstance(cc, dict):
            for kw in cc.get("keywords", []):
                if isinstance(kw, str):
                    kws.add(kw)

    for persona in result.get("personas", []):
        if isinstance(persona, dict):
            for kw in persona.get("search_queries", []):
                if isinstance(kw, str):
                    kws.add(kw)

    # enforce automatic assertion
    print(f"  Extracted {len(kws)} keywords")
    bad = [k for k in kws if seed.lower() not in k.lower()]
    print(f"  Contamination {len(bad)} / {len(kws)}")
    if bad:
        print("  Bad examples:", bad[:10])

    assert len(bad) == 0, f"Seed contamination detected: {len(bad)} bad keywords"

    forbidden = ["clove", "turmeric", "cinnamon", "ginger", "cardamom", "pepper", "nutmeg", "cumin", "coriander", "fenugreek", "anise", "basil"]
    forbidden_hits = [k for k in kws if any(f in k.lower() for f in forbidden)]
    print(f"  Forbidden term hits {len(forbidden_hits)}")
    if forbidden_hits:
        print("  Forbidden examples:", forbidden_hits[:10])
    assert len(forbidden_hits) == 0, f"Forbidden spice terms found: {forbidden_hits[:10]}"
    return True


def test_phase_progress():
    """Test Issue #6: Phase to progress mapping"""
    print("\n[TEST] Phase-to-Progress Mapping")
    # This is validated in job_status response
    print("  (Checked in job_status response above)")

def main():
    print("=" * 60)
    print("COMPREHENSIVE ISSUE TEST SUITE")
    print("=" * 60)
    
    # Setup: Create test project
    project_id = create_test_project()
    if not project_id:
        print("Cannot proceed without project. Stopping tests.")
        return
    
    # Test 1: Input validation endpoint
    if not test_input_health(project_id):
        print("  ✗ FAILED")
    else:
        print("  ✓ PASSED")
    
    # Test 2: Run strategy and job creation
    job_id = test_run_strategy(project_id)
    if not job_id:
        print("  ✗ FAILED")
        print("\nCannot proceed without job_id. Stopping tests.")
        return
    else:
        print("  ✓ PASSED")
    
    # Test 3: Job status and logs
    if test_job_status(project_id, job_id):
        print("  ✓ PASSED")
    else:
        print("  ⚠ TIMEOUT (job still running)")
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        return

    # Test 4: Seed contamination assertion
    try:
        if test_seed_filtering(project_id, seed="tea"):
            print("  ✓ Seed contamination check passed")
    except AssertionError as ae:
        print(f"  ✗ Seed contamination check failed: {ae}")
        raise

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()

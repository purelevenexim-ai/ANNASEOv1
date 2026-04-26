#!/usr/bin/env python3
"""
Test Ollama remote integration — generates content and monitors Ollama calls.
"""
import sys
import time
import requests
import json
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

# ── Test 1: Verify Ollama reachability ────────────────────────────────────────
print("=" * 80)
print("TEST 1: Ollama Server Reachability")
print("=" * 80)

import os
ollama_url = os.getenv('OLLAMA_URL', 'http://172.235.16.165:11434')
print(f"Ollama URL: {ollama_url}")

try:
    resp = requests.get(f"{ollama_url}/api/version", timeout=5)
    version = resp.json().get('version', 'unknown')
    print(f"✓ Ollama responding: v{version}")
except Exception as e:
    print(f"✗ Failed to reach Ollama: {e}")
    sys.exit(1)

# ── Test 2: Direct Ollama inference ───────────────────────────────────────────
print("\n" + "=" * 80)
print("TEST 2: Direct Ollama Inference (SEO Content)")
print("=" * 80)

prompt = "Write a 100-word SEO-friendly introduction for a blog post about 'best practices for remote team management'. Include the keyword in the first sentence."
print(f"Prompt: {prompt[:70]}...")

try:
    start = time.time()
    resp = requests.post(
        f"{ollama_url}/api/generate",
        json={
            "model": os.getenv('OLLAMA_MODEL', 'qwen2.5:3b'),
            "prompt": prompt,
            "stream": False,
            "temperature": 0.7,
        },
        timeout=120,
    )
    duration = time.time() - start
    result = resp.json()
    
    output = result.get('response', '').strip()
    print(f"\n✓ Response generated in {duration:.1f}s:")
    print(f"  {output[:200]}...")
    print(f"\n  Total tokens: {result.get('prompt_eval_count', 0)} → {result.get('eval_count', 0)}")
    print(f"  Speed: {result.get('eval_count', 0) / (result.get('eval_duration', 1) / 1e9):.1f} tok/s")
except Exception as e:
    print(f"✗ Direct inference failed: {e}")
    sys.exit(1)

# ── Test 3: Trigger AnnaSEO content generation ────────────────────────────────
print("\n" + "=" * 80)
print("TEST 3: AnnaSEO Content Generation Pipeline (with Ollama fallback)")
print("=" * 80)

api_url = "http://localhost:8000"
print(f"AnnaSEO API: {api_url}")

# Get auth token
print("\nAuthenticating...")
import uuid
test_email = f"test_{uuid.uuid4().hex[:8]}@annaseo.com"

auth_resp = requests.post(
    f"{api_url}/api/auth/login",
    data={"username": "admin@annaseo.com", "password": "admin123"},
    timeout=10,
)

if auth_resp.status_code == 401:
    # Try to register
    print("  Admin account not found — registering test user...")
    reg_resp = requests.post(
        f"{api_url}/api/auth/register",
        json={
            "email": test_email,
            "name": "Test User",
            "password": "testpass123",
        },
        timeout=10,
    )
    if reg_resp.status_code == 400 and "already registered" in reg_resp.text.lower():
        # Use login
        auth_resp = requests.post(
            f"{api_url}/api/auth/login",
            data={"username": test_email, "password": "testpass123"},
            timeout=10,
        )
        if auth_resp.status_code != 200:
            print(f"  Login with existing account failed: {auth_resp.status_code}")
            sys.exit(1)
    elif reg_resp.status_code != 200:
        print(f"  Registration failed: {reg_resp.status_code}")
        print(reg_resp.text[:200])
        sys.exit(1)
    auth_data = reg_resp.json()
    token = auth_data.get('access_token')
    print(f"  ✓ Registered and got token")
else:
    if auth_resp.status_code != 200:
        print(f"✗ Login failed: {auth_resp.status_code}")
        # Try manual registration
        print("  Trying to register new test user...")
        reg_resp = requests.post(
            f"{api_url}/api/auth/register",
            json={
                "email": test_email,
                "name": "Test User",
                "password": "testpass123",
            },
            timeout=10,
        )
        if reg_resp.status_code != 200:
            print(f"  Registration failed: {reg_resp.status_code}")
            sys.exit(1)
        auth_data = reg_resp.json()
    else:
        auth_data = auth_resp.json()
    token = auth_data.get('access_token')
    print(f"✓ Logged in")

headers = {"Authorization": f"Bearer {token}"}

# Get a project
print("\nFetching/creating project...")
projects_resp = requests.get(f"{api_url}/api/projects", headers=headers, timeout=10)
if projects_resp.status_code != 200:
    print(f"✗ Failed to fetch projects: {projects_resp.status_code}")
    sys.exit(1)

projects_data = projects_resp.json()
projects = projects_data.get('projects', [])

if not projects:
    print("  No projects found — creating one...")
    create_proj_resp = requests.post(
        f"{api_url}/api/projects",
        json={
            "name": "Ollama Test Project",
            "industry": "tech_saas",
            "description": "Testing Ollama remote integration",
            "seed_keywords": ["remote team management", "distributed teams"],
        },
        headers=headers,
        timeout=10,
    )
    if create_proj_resp.status_code != 200:
        print(f"✗ Failed to create project: {create_proj_resp.status_code}")
        print(create_proj_resp.text[:200])
        sys.exit(1)
    project_id = create_proj_resp.json()['project_id']
    print(f"  ✓ Created project: {project_id}")
else:
    project_id = projects[0].get('project_id', projects[0].get('proj_id'))
    print(f"✓ Using existing project: {project_id}")

payload = {
    "keyword": "remote team management",
    "intent": "informational",
    "page_type": "article",
    "target_wc": 2000,
    "project_id": project_id,
}

print(f"\nGenerating content for keyword: '{payload['keyword']}'...")
print("(Ollama will be used as fallback if cloud providers rate-limit)")

try:
    resp = requests.post(
        f"{api_url}/api/content/generate",
        json=payload,
        headers=headers,
        timeout=10,
    )
    if resp.status_code not in (200, 202):
        print(f"✗ Generate request failed: {resp.status_code}")
        print(resp.text[:200])
        sys.exit(1)
    
    result = resp.json()
    article_id = result.get('article_id')
    print(f"✓ Job submitted: article_id = {article_id}")
    
    # ── Poll for completion ──────────────────────────────────────────────────────
    print("\nPolling pipeline progress (max 120 seconds)...")
    poll_interval = 3
    max_polls = 120 // poll_interval
    
    for poll in range(max_polls):
        resp_status = requests.get(f"{api_url}/api/content/{article_id}/pipeline")
        if resp_status.status_code != 200:
            print(f"  [{poll}] Status request failed: {resp_status.status_code}")
            continue
        
        pipeline = resp_status.json().get('pipeline', {})
        status = pipeline.get('status', 'unknown')
        current_step = pipeline.get('current_step', 0)
        total_steps = pipeline.get('total_steps', 0)
        
        # ── Look for Ollama calls in logs ─────────────────────────────────────
        steps = pipeline.get('steps', [])
        ollama_step = next((s for s in steps if 'ollama' in s.get('ai_used', '').lower()), None)
        
        step_info = f"Step {current_step}/{total_steps}"
        if ollama_step:
            step_info += " [⚡ OLLAMA USED]"
        
        print(f"  [{poll}] {status:15} {step_info}")
        
        if status in ('completed', 'failed', 'error'):
            print(f"\n✓ Generation {status}")
            break
        
        time.sleep(poll_interval)
    
    # ── Fetch final result ───────────────────────────────────────────────────────
    print("\nFinal result:")
    resp_final = requests.get(f"{api_url}/api/content/{article_id}")
    if resp_final.status_code == 200:
        content = resp_final.json()
        print(f"  Title: {content.get('title', 'N/A')[:60]}")
        print(f"  Status: {content.get('status', 'N/A')}")
        print(f"  Word count: {content.get('word_count', 0)}")
        
        # Check if draft html exists
        draft = content.get('draft_html', '')
        if draft:
            print(f"  ✓ Draft generated ({len(draft)} chars)")
        
        # Get pipeline details to see what AI was used where
        pipeline_data = content.get('pipeline_snapshot', {})
        if pipeline_data:
            steps = pipeline_data.get('steps', [])
            ollama_used = [s['name'] for s in steps if s.get('ai_first') == 'ollama']
            if ollama_used:
                print(f"  ⚡ Ollama used in: {', '.join(ollama_used)}")
    else:
        print(f"  Failed to fetch: {resp_final.status_code}")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✓ Test complete — Check /var/log/syslog or journalctl for Ollama calls:")
print("  journalctl -u annaseo -f | grep -i ollama")
print("=" * 80)

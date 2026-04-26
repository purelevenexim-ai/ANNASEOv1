#!/usr/bin/env python3
"""
Content Generation Monitor — Real-time test with Ollama integration verification.
Shows which steps used Ollama vs cloud APIs, timing, and quality at each stage.
"""
import sys
import time
import json
import requests
import threading
from datetime import datetime
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

import os
API_URL = "http://localhost:8000"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://172.235.16.165:11434")

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def log_step(step_num, msg, status="INFO"):
    colors = {
        "INFO": Colors.OKBLUE,
        "SUCCESS": Colors.OKGREEN,
        "WARNING": Colors.WARNING,
        "ERROR": Colors.FAIL,
    }
    color = colors.get(status, Colors.OKBLUE)
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}] Step {step_num}: {msg}{Colors.ENDC}")

def verify_ollama_ready():
    """Verify Ollama server is reachable and has model loaded."""
    print(f"\n{Colors.BOLD}=== PHASE 0: Verify External Ollama Server ==={Colors.ENDC}")
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = r.json().get("models", [])
            if models:
                model_name = models[0].get("name", "unknown")
                model_size = models[0].get("size", 0) / 1e9
                print(f"{Colors.OKGREEN}✓ Ollama online @ {OLLAMA_URL}{Colors.ENDC}")
                print(f"  Model: {model_name} ({model_size:.1f}GB)")
                return True
        print(f"{Colors.FAIL}✗ Ollama responded but no models loaded{Colors.ENDC}")
        return False
    except Exception as e:
        print(f"{Colors.FAIL}✗ Cannot reach Ollama: {e}{Colors.ENDC}")
        return False

def authenticate():
    """Get auth token for API calls."""
    print(f"\n{Colors.BOLD}=== PHASE 1: Authentication ==={Colors.ENDC}")
    import uuid
    email = f"monitor_{uuid.uuid4().hex[:8]}@test.com"
    
    try:
        # Try to register
        r = requests.post(
            f"{API_URL}/api/auth/register",
            json={"email": email, "name": "Monitor User", "password": "monitor123"},
            timeout=10,
        )
        if r.status_code == 200:
            token = r.json()["access_token"]
            log_step(1, f"Registered & got token", "SUCCESS")
            return token
        else:
            log_step(1, f"Registration failed: {r.status_code}", "ERROR")
            return None
    except Exception as e:
        log_step(1, f"Auth error: {e}", "ERROR")
        return None

def get_or_create_project(token):
    """Get a project to generate content for."""
    print(f"\n{Colors.BOLD}=== PHASE 2: Project Setup ==={Colors.ENDC}")
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Check for existing projects
        r = requests.get(f"{API_URL}/api/projects", headers=headers, timeout=10)
        if r.status_code == 200:
            projects = r.json().get("projects", [])
            if projects:
                proj_id = projects[0]["project_id"]
                log_step(2, f"Using existing project: {proj_id}", "SUCCESS")
                return proj_id
        
        # Create new project
        r = requests.post(
            f"{API_URL}/api/projects",
            json={
                "name": "Ollama Monitor Test",
                "industry": "tech_saas",
                "description": "Testing Ollama integration with remote server",
                "seed_keywords": ["remote team management tools", "distributed work"],
            },
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            proj_id = r.json()["project_id"]
            log_step(2, f"Created project: {proj_id}", "SUCCESS")
            return proj_id
        else:
            log_step(2, f"Project creation failed: {r.status_code}", "ERROR")
            return None
    except Exception as e:
        log_step(2, f"Project setup error: {e}", "ERROR")
        return None

def generate_content(token, project_id):
    """Trigger content generation."""
    print(f"\n{Colors.BOLD}=== PHASE 3: Trigger Content Generation ==={Colors.ENDC}")
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "keyword": "best practices for remote team management 2026",
        "intent": "informational",
        "page_type": "article",
        "target_wc": 2000,
        "project_id": project_id,
    }
    
    try:
        log_step(3, "Submitting content generation job...", "INFO")
        r = requests.post(
            f"{API_URL}/api/content/generate",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if r.status_code in (200, 202):
            article_id = r.json()["article_id"]
            log_step(3, f"Job submitted: {article_id}", "SUCCESS")
            return article_id
        else:
            log_step(3, f"Generation submission failed: {r.status_code}", "ERROR")
            print(r.text[:200])
            return None
    except Exception as e:
        log_step(3, f"Generation error: {e}", "ERROR")
        return None

def monitor_pipeline(token, article_id, max_wait_sec=300):
    """Poll pipeline progress and track Ollama usage."""
    print(f"\n{Colors.BOLD}=== PHASE 4: Monitor Pipeline Progress ==={Colors.ENDC}")
    headers = {"Authorization": f"Bearer {token}"}
    
    step_list = [
        (1, "Research", "Research keywords & SERP analysis"),
        (2, "Structure", "Plan article structure & sections"),
        (3, "Links", "Identify internal linking opportunities"),
        (4, "References", "Gather reference links"),
        (5, "Wikipedia", "Fetch Wikipedia context"),
        (6, "Draft", "Generate article draft"),
        (7, "Review", "Quality review of draft"),
        (8, "Issues", "53-rule compliance check"),
        (9, "Redevelop", "Rewrite to fix issues"),
        (10, "Score", "Final quality scoring"),
        (11, "Quality Loop", "Iterate until score ≥ 75%"),
    ]
    
    step_ai_tracker = {}  # Track which AI was used per step
    step_timing = {}      # Track time per step
    prev_step = 0
    start_time = time.time()
    
    poll_interval = 3
    max_polls = max_wait_sec // poll_interval
    
    for poll in range(max_polls):
        try:
            resp = requests.get(
                f"{API_URL}/api/content/{article_id}/pipeline",
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                log_step(4, f"Poll failed: {resp.status_code}", "WARNING")
                continue
            
            pipeline = resp.json().get("pipeline", {})
            status = pipeline.get("status", "unknown")
            current_step = pipeline.get("current_step", 0)
            steps_data = pipeline.get("steps", [])
            
            # Track AI usage per step
            for step_data in steps_data:
                step_num = step_data.get("step", 0)
                ai_used = step_data.get("ai_used", "unknown")
                if step_num not in step_ai_tracker:
                    step_ai_tracker[step_num] = ai_used
                    
                    # Find step name
                    step_name = next((s[1] for s in step_list if s[0] == step_num), "Unknown")
                    
                    # Color code by AI provider
                    ai_colors = {
                        "ollama": Colors.WARNING,  # Yellow for Ollama (fallback)
                        "gemini": Colors.OKBLUE,
                        "groq": Colors.OKCYAN,
                        "anthropic": Colors.OKGREEN,
                    }
                    ai_color = next((c for ai, c in ai_colors.items() if ai in ai_used.lower()), Colors.OKBLUE)
                    
                    log_step(4, f"Step {step_num}: {step_name} → {ai_color}{ai_used}{Colors.ENDC}", "INFO")
            
            # Progress bar
            if current_step != prev_step:
                if current_step > 0 and current_step <= len(step_list):
                    step_info = step_list[current_step - 1]
                    elapsed = time.time() - start_time
                    print(f"  {Colors.BOLD}Progress: {current_step}/11 — {step_info[1]}{Colors.ENDC} ({elapsed:.0f}s elapsed)")
                prev_step = current_step
            
            # Check for completion or error
            if status == "completed":
                elapsed = time.time() - start_time
                log_step(4, f"Generation COMPLETED in {elapsed:.0f}s", "SUCCESS")
                return True, step_ai_tracker
            elif status in ("failed", "error"):
                error_msg = pipeline.get("error_message", "Unknown error")
                log_step(4, f"Generation FAILED: {error_msg}", "ERROR")
                return False, step_ai_tracker
            
            time.sleep(poll_interval)
        
        except Exception as e:
            log_step(4, f"Poll error: {str(e)[:80]}", "WARNING")
            time.sleep(poll_interval)
    
    log_step(4, f"Timeout — did not complete within {max_wait_sec}s", "WARNING")
    return False, step_ai_tracker

def fetch_final_result(token, article_id):
    """Fetch final generated content and metadata."""
    print(f"\n{Colors.BOLD}=== PHASE 5: Final Result ==={Colors.ENDC}")
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        r = requests.get(
            f"{API_URL}/api/content/{article_id}",
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            content = r.json()
            
            title = content.get("title", "N/A")
            word_count = content.get("word_count", 0)
            seo_score = content.get("seo_score", 0)
            status = content.get("status", "N/A")
            
            log_step(5, f"Article generated successfully", "SUCCESS")
            print(f"  Title: {title[:60]}")
            print(f"  Word count: {word_count}")
            print(f"  SEO score: {seo_score}")
            print(f"  Status: {status}")
            
            # Check for Ollama-generated content
            draft = content.get("draft_html", "")
            if draft and len(draft) > 100:
                log_step(5, f"✓ Draft HTML available ({len(draft)} chars)", "SUCCESS")
            
            return True
        else:
            log_step(5, f"Failed to fetch result: {r.status_code}", "ERROR")
            return False
    except Exception as e:
        log_step(5, f"Fetch error: {e}", "ERROR")
        return False

def print_summary(ai_tracker):
    """Print summary of AI usage across pipeline."""
    print(f"\n{Colors.BOLD}=== SUMMARY: AI Provider Usage ==={Colors.ENDC}")
    
    step_list = {
        1: "Research", 2: "Structure", 3: "Links", 4: "References", 5: "Wikipedia",
        6: "Draft", 7: "Review", 8: "Issues", 9: "Redevelop", 10: "Score", 11: "Quality Loop"
    }
    
    ollama_steps = []
    cloud_steps = []
    
    for step_num in sorted(ai_tracker.keys()):
        ai_used = ai_tracker[step_num]
        step_name = step_list.get(step_num, "Unknown")
        
        if "ollama" in ai_used.lower():
            ollama_steps.append((step_num, step_name, ai_used))
            color = Colors.WARNING
        else:
            cloud_steps.append((step_num, step_name, ai_used))
            color = Colors.OKGREEN
        
        print(f"  Step {step_num:2d}: {step_name:15s} → {color}{ai_used}{Colors.ENDC}")
    
    print(f"\n{Colors.OKGREEN}Cloud APIs used: {len(cloud_steps)} steps{Colors.ENDC}")
    print(f"{Colors.WARNING}Ollama used (fallback): {len(ollama_steps)} steps{Colors.ENDC}")
    
    if ollama_steps:
        print(f"\n{Colors.BOLD}Remote Ollama Steps:{Colors.ENDC}")
        for step_num, step_name, ai_used in ollama_steps:
            print(f"  ✓ Step {step_num}: {step_name}")

def main():
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("╔════════════════════════════════════════╗")
    print("║  Content Generation Monitor            ║")
    print("║  Testing Remote Ollama Integration     ║")
    print("╚════════════════════════════════════════╝{Colors.ENDC}\n")
    
    # Phase 0: Verify Ollama
    if not verify_ollama_ready():
        print(f"\n{Colors.FAIL}Cannot proceed without Ollama server. Exiting.{Colors.ENDC}")
        sys.exit(1)
    
    # Phase 1: Auth
    token = authenticate()
    if not token:
        print(f"\n{Colors.FAIL}Authentication failed. Exiting.{Colors.ENDC}")
        sys.exit(1)
    
    # Phase 2: Project
    project_id = get_or_create_project(token)
    if not project_id:
        print(f"\n{Colors.FAIL}Project setup failed. Exiting.{Colors.ENDC}")
        sys.exit(1)
    
    # Phase 3: Generate
    article_id = generate_content(token, project_id)
    if not article_id:
        print(f"\n{Colors.FAIL}Content generation trigger failed. Exiting.{Colors.ENDC}")
        sys.exit(1)
    
    # Phase 4: Monitor
    success, ai_tracker = monitor_pipeline(token, article_id, max_wait_sec=300)
    
    # Phase 5: Final result
    if success:
        fetch_final_result(token, article_id)
    
    # Summary
    print_summary(ai_tracker)
    
    print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ Monitor test complete{Colors.ENDC}\n")

if __name__ == "__main__":
    main()

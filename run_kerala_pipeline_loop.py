#!/usr/bin/env python3
"""
Kerala Naadan Coffee Powder — Full Pipeline Regeneration Loop
=============================================================
Runs the full 12-step content generation pipeline on art_509864ae02
using FREE OpenRouter models, then scores the result.
Loops until review score >= 95% AND story score >= 9.5.

Usage: python3 run_kerala_pipeline_loop.py
"""

import asyncio
import json
import os
import sys
import time
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8000"
ARTICLE_ID = "art_509864ae02"
PROJECT_ID = "proj_kerala_naadan"
KEYWORD = "kerala naadan coffee powder"
TARGET_REVIEW_PCT = 95
TARGET_STORY = 9.5
MAX_LOOPS = 5

TOKEN = os.getenv("ANNASEO_TEST_TOKEN", "eyJ1c2VyX2lkIjogInVzZXJfdGVzdGFkbWluIiwgImVtYWlsIjogInRlc3RAdGVzdC5jb20iLCAicm9sZSI6ICJhZG1pbiIsICJleHAiOiAiMjAyNi0wNS0yM1QwNTo1NzoxOC4wMTEyNzMifQ==.a484e3e9c4e50782dd66702b8b9ea0db330f7a7b5fd1fdb03ddede6407d63945")

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def api_get(path):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def api_post(path, body=None):
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=body or {}, timeout=120)
    r.raise_for_status()
    return r.json()


def get_scores():
    """Get current scores for the article."""
    try:
        assessment = api_get(f"/api/content/{ARTICLE_ID}/assessment")
        return {
            "overall": assessment.get("scores", {}).get("overall", 0),
            "review_pct": assessment.get("scores", {}).get("overall", 0),
            "story": assessment.get("scores", {}).get("story_raw", 0),
            "seo": assessment.get("scores", {}).get("seo", 0),
            "aeo": assessment.get("scores", {}).get("aeo", 0),
            "eeat": assessment.get("scores", {}).get("eeat", 0),
            "geo": assessment.get("scores", {}).get("geo", 0),
        }
    except Exception as e:
        print(f"  [scores] assessment failed: {e}")
        # Fallback: just run review
        try:
            review = api_post(f"/api/content/{ARTICLE_ID}/review")
            pct = review.get("percentage", 0)
            return {"overall": pct, "review_pct": pct, "story": 0}
        except Exception as e2:
            print(f"  [scores] review also failed: {e2}")
            return {"overall": 0, "review_pct": 0, "story": 0}


def run_review_and_get_score():
    """Run the review step and return score."""
    print("  Running full review...")
    try:
        review = api_post(f"/api/content/{ARTICLE_ID}/review")
        pct = review.get("percentage", 0)
        fails = review.get("failed_rules", [])
        print(f"  Review: {pct}% ({review.get('score',0)}/{review.get('max_possible',0)} pts), {len(fails)} failed rules")
        if fails:
            for f in fails[:5]:
                print(f"    - [{f.get('rule_id')}] {f.get('description','')}: {f.get('reason','')[:80]}")
        return pct, fails
    except Exception as e:
        print(f"  Review failed: {e}")
        return 0, []


def run_story_score():
    """Run story score and return story score."""
    try:
        story = api_get(f"/api/content/{ARTICLE_ID}/story-score")
        score = story.get("total_score", 0)
        print(f"  Story score: {score:.1f}/10 — {story.get('grade','?')}")
        for k, v in story.get("breakdown", {}).items():
            print(f"    {k}: {v}")
        return score
    except Exception as e:
        print(f"  Story score failed: {e}")
        return 0


def poll_pipeline_completion(run_id: str, timeout_secs: int = 600) -> bool:
    """Poll pipeline status until complete or timeout."""
    start = time.time()
    last_step = ""
    while time.time() - start < timeout_secs:
        try:
            pipeline = api_get(f"/api/content/{ARTICLE_ID}/pipeline")
            status = pipeline.get("status", "unknown")
            current_step = pipeline.get("current_step", "")
            progress = pipeline.get("progress_pct", 0)

            step_label = f"Step {current_step}" if current_step else "..."
            if step_label != last_step:
                print(f"  [{status}] {step_label} ({progress:.0f}%)")
                last_step = step_label

            if status in ("complete", "done", "completed"):
                print(f"  Pipeline COMPLETE in {time.time()-start:.0f}s")
                return True
            elif status in ("failed", "error", "cancelled"):
                print(f"  Pipeline FAILED: {pipeline.get('error','unknown error')}")
                return False
            elif status == "waiting_ai_recovery":
                print(f"  Pipeline waiting for AI recovery — check provider dashboard")
                # Try to continue automatically with a different provider
                time.sleep(30)
                continue

        except Exception as e:
            print(f"  Poll error: {e}")

        time.sleep(8)

    print(f"  Pipeline TIMEOUT after {timeout_secs}s")
    return False


def run_pipeline_loop():
    print("=" * 60)
    print("Kerala Naadan Coffee Powder — Full Pipeline Loop")
    print(f"Target: Review >= {TARGET_REVIEW_PCT}% AND Story >= {TARGET_STORY}")
    print("Using: Free OpenRouter models (or_nemotron_free, or_gemma4_31b, or_qwen)")
    print("=" * 60)
    print()

    for loop in range(1, MAX_LOOPS + 1):
        print(f"\n{'='*60}")
        print(f"LOOP {loop}/{MAX_LOOPS}")
        print(f"{'='*60}")

        # Step 1: Regenerate article via content pipeline
        print("\n[1] Triggering full content regeneration...")
        try:
            # Use regenerate endpoint which runs the full pipeline
            regen_resp = api_post(f"/api/content/{ARTICLE_ID}/regenerate", {
                "ai_provider": "auto",
                "force": True,
                "free_models_only": True,
            })
            run_id = regen_resp.get("run_id") or regen_resp.get("article_id", ARTICLE_ID)
            print(f"  Regeneration started — run_id: {run_id}")
        except Exception as e:
            print(f"  Regenerate failed: {e}")
            print("  Trying generate endpoint...")
            try:
                gen_resp = api_post("/api/content/generate", {
                    "project_id": PROJECT_ID,
                    "keyword": KEYWORD,
                    "article_id": ARTICLE_ID,
                    "ai_provider": "auto",
                    "force_regenerate": True,
                })
                run_id = gen_resp.get("run_id", ARTICLE_ID)
                print(f"  Generation started — run_id: {run_id}")
            except Exception as e2:
                print(f"  Generation also failed: {e2}")
                break

        # Step 2: Wait for pipeline to complete
        print("\n[2] Waiting for pipeline completion (up to 10 minutes)...")
        success = poll_pipeline_completion(run_id, timeout_secs=600)
        if not success:
            print("  Pipeline did not complete successfully")
            if loop < MAX_LOOPS:
                print("  Checking scores anyway...")
            else:
                break

        # Give server a moment to write the final article
        time.sleep(3)

        # Step 3: Score the result
        print("\n[3] Scoring the generated article...")
        review_pct, failed_rules = run_review_and_get_score()
        story_score = run_story_score()

        # Step 4: Try to get full assessment
        print("\n[4] Full assessment...")
        try:
            assessment = api_get(f"/api/content/{ARTICLE_ID}/assessment")
            scores = assessment.get("scores", {})
            print(f"  Overall: {scores.get('overall',0)}%")
            print(f"  SEO: {scores.get('seo',0)}%  AEO: {scores.get('aeo',0)}%  EEAT: {scores.get('eeat',0)}%  GEO: {scores.get('geo',0)}%")
            print(f"  Story: {scores.get('story',0)}% (raw {scores.get('story_raw',0):.1f}/10)")
        except Exception as e:
            print(f"  Assessment: {e}")

        # Step 5: Ledger
        print("\n[5] Issue ledger...")
        try:
            ledger = api_get(f"/api/content/{ARTICLE_ID}/ledger")
            total = ledger.get("total_issues", 0)
            print(f"  Total issues: {total}")
            for issue in ledger.get("ledger", [])[:5]:
                print(f"    [{issue.get('severity','?')}] {issue.get('message','')[:80]}")
        except Exception as e:
            print(f"  Ledger: {e}")

        # Step 6: Check targets
        print(f"\n[6] Score check: Review={review_pct}% (target={TARGET_REVIEW_PCT}%), Story={story_score:.1f} (target={TARGET_STORY})")

        if review_pct >= TARGET_REVIEW_PCT and story_score >= TARGET_STORY:
            print("\n" + "=" * 60)
            print("SUCCESS! All targets met.")
            print(f"  Review: {review_pct}% >= {TARGET_REVIEW_PCT}%")
            print(f"  Story:  {story_score:.1f} >= {TARGET_STORY}")
            print("=" * 60)
            return True

        if loop < MAX_LOOPS:
            print(f"\nTargets not met — starting loop {loop + 1}...")
            print("Running quality fix pass before next regeneration...")
            # Try auto-fix issues
            try:
                if failed_rules:
                    rule_ids = [r.get("rule_id") for r in failed_rules[:10] if r.get("rule_id")]
                    fix_resp = api_post(f"/api/content/{ARTICLE_ID}/fix-rules", {"rule_ids": rule_ids})
                    print(f"  Fix pass: {fix_resp.get('message','done')}")
                    time.sleep(5)
            except Exception as e:
                print(f"  Fix pass failed (non-fatal): {e}")
        else:
            print(f"\nMax loops ({MAX_LOOPS}) reached.")

    # Final scores
    print("\n" + "=" * 60)
    print("FINAL SCORES:")
    review_pct, _ = run_review_and_get_score()
    story_score = run_story_score()
    try:
        assessment = api_get(f"/api/content/{ARTICLE_ID}/assessment")
        scores = assessment.get("scores", {})
        print(f"  Overall: {scores.get('overall',0)}%")
        print(f"  SEO: {scores.get('seo',0)}%  AEO: {scores.get('aeo',0)}%  EEAT: {scores.get('eeat',0)}%  GEO: {scores.get('geo',0)}%  Story: {scores.get('story_raw',0):.1f}/10")
    except Exception:
        pass
    print("=" * 60)

    return review_pct >= TARGET_REVIEW_PCT and story_score >= TARGET_STORY


if __name__ == "__main__":
    succeeded = run_pipeline_loop()
    sys.exit(0 if succeeded else 1)

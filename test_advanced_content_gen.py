#!/usr/bin/env python3
"""
Test script for 10-step content generation pipeline
Tests with 3 keywords
"""

import asyncio
import json
import sys
sys.path.insert(0, '/root/ANNASEOv1')

from engines.content_generation_engine import SEOContentPipeline

async def test_pipeline():
    """Test 10-step pipeline with 3 keywords"""
    
    test_keywords = [
        {"keyword": "kerala spices supplier", "intent": "commercial", "desc": "High-intent commercial query"},
        {"keyword": "how to make curry powder at home", "intent": "informational", "desc": "Long-tail informational"},
        {"keyword": "best spices for chicken biryani", "intent": "comparison", "desc": "Comparison/buying intent"},
    ]
    
    results = {}
    
    for i, test_case in enumerate(test_keywords, 1):
        keyword = test_case["keyword"]
        print(f"\n{'='*70}")
        print(f"TEST {i}: {keyword}")
        print(f"Intent: {test_case['intent']} | {test_case['desc']}")
        print(f"{'='*70}\n")
        
        pipeline = SEOContentPipeline(keyword, test_case["intent"])
        
        step_count = 0
        async def progress_cb(event):
            nonlocal step_count
            if "step" in event:
                status = event.get("status", "unknown")
                step_count += 1
                print(f"  Step {event['step']}: {event.get('name', 'Unknown')} ... {status}")
        
        try:
            # Run full pipeline
            print("Starting 10-step pipeline...\n")
            step_results = await pipeline.run_full_pipeline(progress_callback=progress_cb)
            
            # Get final state
            state = pipeline.get_pipeline_state()
            
            # Store results
            results[keyword] = {
                "status": "success",
                "versions_created": state["versions_created"],
                "steps_completed": step_count,
                "versions": state["versions"],
                "analysis": state.get("analysis"),
                "structure": state.get("structure"),
            }
            
            # Print summary
            print(f"\n✓ Pipeline completed successfully!")
            print(f"  - Versions created: {state['versions_created']}")
            print(f"  - Total steps: {len(state['versions'])}")
            
            if state["versions"]:
                latest = state["versions"][-1]
                print(f"  - Latest version: {latest['version']} ({latest['step_name']})")
                print(f"  - Issues identified: {latest.get('issues_count', 0)}")
            
            if state.get("analysis"):
                print(f"  - Key themes: {len(state['analysis'].get('key_themes', []))}")
                print(f"  - Content gaps: {len(state['analysis'].get('content_gaps', []))}")
            
            if state.get("structure"):
                print(f"  - H2 sections: {len(state['structure'].get('h2_sections', []))}")
                print(f"  - FAQ count: {state['structure'].get('faq_count', 0)}")
            
        except Exception as e:
            print(f"✗ Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            results[keyword] = {"status": "failed", "error": str(e)}
    
    # Print final test report
    print(f"\n\n{'='*70}")
    print("TEST REPORT SUMMARY")
    print(f"{'='*70}\n")
    
    for keyword, result in results.items():
        status_icon = "✓" if result["status"] == "success" else "✗"
        print(f"{status_icon} {keyword}")
        if result["status"] == "success":
            print(f"   - Versions: {result['versions_created']}")
            print(f"   - Steps: {result['steps_completed']}")
        else:
            print(f"   - Error: {result.get('error', 'Unknown')}")
    
    # Save detailed results
    report_path = "/tmp/content_generation_test_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nDetailed report saved: {report_path}")
    
    success_count = sum(1 for r in results.values() if r["status"] == "success")
    print(f"\n{'='*70}")
    print(f"RESULTS: {success_count}/{len(test_keywords)} tests passed")
    print(f"{'='*70}\n")
    
    return success_count == len(test_keywords)

if __name__ == "__main__":
    success = asyncio.run(test_pipeline())
    sys.exit(0 if success else 1)

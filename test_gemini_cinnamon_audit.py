#!/usr/bin/env python3
"""
COMPREHENSIVE AUDIT TEST: "online cinnamon kerala" with Gemini
Tracks every metric, phase, AI call, failure, and quality indicator.
"""
import asyncio
import time
import json
import sys
import os
import re
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))


class AuditTracker:
    """Comprehensive tracking of pipeline execution"""
    def __init__(self):
        self.start_time = time.time()
        self.phases = {}
        self.ai_calls = []
        self.errors = []
        self.warnings = []
        self.unused_features = set()
        self.overused_features = defaultdict(int)
        self.step_timings = {}
        self.ai_provider_usage = defaultdict(int)
        self.ai_provider_costs = defaultdict(float)
        self.retry_counts = defaultdict(int)
        self.timeout_events = []
        self.quality_scores = {}
        self.rule_failures = []
        
    def track_step_start(self, step_num, step_name):
        self.step_timings[step_num] = {
            'name': step_name,
            'start': time.time(),
            'end': None,
            'duration': None,
            'ai_calls': []
        }
        
    def track_step_end(self, step_num):
        if step_num in self.step_timings:
            self.step_timings[step_num]['end'] = time.time()
            self.step_timings[step_num]['duration'] = (
                self.step_timings[step_num]['end'] - 
                self.step_timings[step_num]['start']
            )
    
    def track_ai_call(self, provider, step, duration, tokens_in, tokens_out, cost, success):
        self.ai_calls.append({
            'provider': provider,
            'step': step,
            'duration': duration,
            'tokens_in': tokens_in,
            'tokens_out': tokens_out,
            'cost': cost,
            'success': success,
            'timestamp': time.time()
        })
        if success:
            self.ai_provider_usage[provider] += 1
            self.ai_provider_costs[provider] += cost
    
    def generate_report(self):
        total_time = time.time() - self.start_time
        total_cost = sum(self.ai_provider_costs.values())
        total_calls = sum(self.ai_provider_usage.values())
        
        report = {
            'summary': {
                'total_time': total_time,
                'total_cost': total_cost,
                'total_ai_calls': total_calls,
                'errors': len(self.errors),
                'warnings': len(self.warnings)
            },
            'step_timings': self.step_timings,
            'ai_calls': self.ai_calls,
            'provider_usage': dict(self.ai_provider_usage),
            'provider_costs': dict(self.ai_provider_costs),
            'errors': self.errors,
            'warnings': self.warnings,
            'retry_counts': dict(self.retry_counts),
            'quality_scores': self.quality_scores
        }
        return report


async def run_comprehensive_test():
    """Run test with full tracking"""
    from engines.content_generation_engine import SEOContentPipeline, AIRoutingConfig, StepAIConfig
    
    tracker = AuditTracker()
    
    # Pure-OR chain (Gemini Flash via OpenRouter as primary). Avoiding mixed
    # OR + direct providers keeps `_call_ai_with_chain` in SEQUENTIAL mode and
    # prevents wasted parallel-race retries on broken `gemini_paid` (status=0).
    gemini_step = StepAIConfig("or_gemini_flash", "or_deepseek", "or_gemini_lite")
    
    routing = AIRoutingConfig(
        research=gemini_step,
        structure=gemini_step,
        verify=gemini_step,
        links=gemini_step,
        references=gemini_step,
        draft=gemini_step,
        recovery=gemini_step,
        review=gemini_step,
        issues=gemini_step,
        humanize=gemini_step,
        redevelop=gemini_step,
        quality_loop=gemini_step,
        score=StepAIConfig("skip", "skip", "skip"),  # local scoring only
    )
    
    keyword = "online cinnamon kerala"
    project_id = "audit_gemini"
    
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), "annaseo.db")
    db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    db.row_factory = sqlite3.Row
    
    import hashlib
    article_id = f"audit_{hashlib.md5(f'{keyword}{time.time()}'.encode()).hexdigest()[:10]}"
    
    db.execute(
        "INSERT OR REPLACE INTO content_articles(article_id,project_id,keyword,status,page_type) "
        "VALUES(?,?,?,'generating','article')",
        (article_id, project_id, keyword)
    )
    db.commit()
    
    print(f"\n{'='*80}")
    print(f"🔬 COMPREHENSIVE AUDIT TEST: '{keyword}'")
    print(f"Article ID: {article_id}")
    print(f"Provider: Gemini Flash (all steps)")
    print(f"Mode: Full instrumentation & tracking")
    print(f"{'='*80}\n")
    
    pipeline = SEOContentPipeline(
        keyword=keyword,
        project_id=project_id,
        article_id=article_id,
        title="",
        intent="commercial",
        word_count=2500,
        supporting_keywords=["buy cinnamon online", "kerala cinnamon price", "ceylon cinnamon"],
        target_audience="health-conscious consumers, spice buyers, restaurants",
        content_type="blog",
        page_type="article",
        ai_routing=routing,
        db=db,
    )
    
    # Hook into pipeline to track everything - FIX 91: proper step tracking
    original_call_ai = pipeline._call_ai_raw_with_chain
    
    async def tracked_call_ai(cfg, prompt, temperature=0.6, max_tokens=6000, use_prompt_directly=False):
        # Determine current step by inspecting call stack (FIX 91)
        import inspect
        step = 'unknown'
        for frame_info in inspect.stack():
            func_name = frame_info.function
            if func_name.startswith('_step') or func_name.startswith('_lean_step'):
                # Extract step name from function name (_step6_draft → draft)
                step = func_name.split('_')[-1]
                break
        
        call_start = time.time()
        try:
            result = await original_call_ai(cfg, prompt, temperature, max_tokens, use_prompt_directly)
            duration = time.time() - call_start
            # Estimate tokens and cost (rough)
            tokens_in = len(prompt) // 4
            tokens_out = len(result) // 4 if result else 0
            cost = (tokens_in * 0.075 + tokens_out * 0.30) / 1_000_000
            tracker.track_ai_call(cfg.first, step, duration, tokens_in, tokens_out, cost, True)
            return result
        except Exception as e:
            duration = time.time() - call_start
            tracker.track_ai_call(cfg.first, step, duration, 0, 0, 0, False)
            tracker.errors.append(f"AI call failed in {step}: {str(e)}")
            raise
    
    pipeline._call_ai_raw_with_chain = tracked_call_ai
    
    try:
        result = await pipeline.run()
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ PIPELINE FAILED: {e}")
        print(f"{'='*80}")
        import traceback
        traceback.print_exc()
        tracker.errors.append(f"Pipeline crash: {str(e)}")
    
    # Generate comprehensive report
    report = tracker.generate_report()
    
    # Analyze content quality
    html = pipeline.state.final_html or ""
    text = re.sub(r"<[^>]+>", " ", html)
    word_count = len(text.split())
    
    print(f"\n{'='*80}")
    print(f"✅ PIPELINE COMPLETE")
    print(f"{'='*80}\n")
    
    print(f"── TIMING ANALYSIS ──")
    print(f"  Total time: {report['summary']['total_time']:.1f}s ({report['summary']['total_time']/60:.1f} min)")
    for step_num in sorted(report['step_timings'].keys()):
        step = report['step_timings'][step_num]
        if step['duration']:
            print(f"    S{step_num:2d} {step['name']:20s}: {step['duration']:6.1f}s")
    
    print(f"\n── AI USAGE ANALYSIS ──")
    print(f"  Total calls: {report['summary']['total_ai_calls']}")
    for provider, count in sorted(report['provider_usage'].items(), key=lambda x: -x[1]):
        cost = report['provider_costs'][provider]
        print(f"    {provider:20s}: {count:3d} calls, ${cost:.4f}")
    print(f"  Total cost: ${report['summary']['total_cost']:.4f}")
    
    print(f"\n── QUALITY SCORING ──")
    try:
        from quality.content_rules import check_all_rules
        scored = check_all_rules(
            body_html=html,
            keyword=keyword,
            title=pipeline.state.title or "",
            meta_title=pipeline.state.meta_title or "",
            meta_desc=pipeline.state.meta_desc or "",
            page_type="article",
        )
        print(f"  Score: {scored['percentage']}% ({scored['total_earned']}/{scored['max_possible']} pts)")
        print(f"  Passed: {scored['summary']['passed_count']}/{scored['summary']['total_rules']} rules")
        
        failing = [r for r in scored["rules"] if not r.get("passed")]
        if failing:
            print(f"\n  ── TOP FAILURES ({len(failing)}) ──")
            for r in sorted(failing, key=lambda x: x.get("points_max", 0), reverse=True)[:15]:
                pts_lost = r.get("points_max", 0) - r.get("points_earned", 0)
                print(f"    {r.get('rule_id','?'):5s} {r.get('name',''):50s} -{pts_lost}pts")
    except Exception as e:
        print(f"  Scoring failed: {e}")
        scored = None
    
    print(f"\n── ERRORS & WARNINGS ──")
    print(f"  Errors: {len(report['errors'])}")
    print(f"  Warnings: {len(report['warnings'])}")
    if report['errors']:
        for err in report['errors'][:10]:
            print(f"    ❌ {err}")
    
    # Save outputs
    with open("/tmp/gemini_audit_output.html", "w") as f:
        f.write(html)
    
    with open("/tmp/gemini_audit_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n  Output: /tmp/gemini_audit_output.html")
    print(f"  Report: /tmp/gemini_audit_report.json")
    
    print(f"\n{'='*80}")
    score_pct = scored['percentage'] if scored else 0
    if score_pct >= 90:
        print(f"  ✅ GRADE A+ — {score_pct}% — Excellent")
    elif score_pct >= 85:
        print(f"  ✅ GRADE A — {score_pct}% — Very good")
    elif score_pct >= 70:
        print(f"  ⚠️ GRADE B — {score_pct}% — Good")
    else:
        print(f"  ❌ GRADE C/D — {score_pct}% — Needs work")
    print(f"  Time: {report['summary']['total_time']/60:.1f} min | Cost: ${report['summary']['total_cost']:.4f} | Words: {word_count}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(run_comprehensive_test())

#!/usr/bin/env python3
"""
Live test: Generate article for "online black pepper kerala" using Ollama REMOTE only.
Tests the full pipeline with mistral:7b-instruct on remote server.
"""
import asyncio
import time
import json
import sys
import os
import re
import faulthandler
import signal
faulthandler.enable()
faulthandler.register(signal.SIGUSR1)  # Dump traceback on SIGUSR1 without killing

sys.path.insert(0, os.path.dirname(__file__))

# Force Ollama LOCAL routing (remote is stuck)
os.environ["OLLAMA_URL"] = "http://localhost:11434"
os.environ["OLLAMA_MODEL"] = "qwen2.5:3b"


async def run_test():
    from engines.content_generation_engine import SEOContentPipeline, AIRoutingConfig, StepAIConfig

    # All-Ollama routing — every step uses Ollama, no fallbacks
    ollama_step = StepAIConfig("ollama", "skip", "skip")
    routing = AIRoutingConfig(
        research=ollama_step,
        structure=ollama_step,
        verify=ollama_step,
        links=ollama_step,
        references=ollama_step,
        draft=ollama_step,
        recovery=ollama_step,
        review=ollama_step,
        issues=ollama_step,
        humanize=ollama_step,
        redevelop=ollama_step,
        score=StepAIConfig("skip", "skip", "skip"),  # scoring is deterministic
        quality_loop=ollama_step,
    )

    keyword = "online black pepper kerala"
    project_id = "test_pepper"

    # Set up DB
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), "annaseo.db")
    db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    db.row_factory = sqlite3.Row

    import hashlib
    article_id = f"test_{hashlib.md5(f'{keyword}{time.time()}'.encode()).hexdigest()[:10]}"

    db.execute(
        "INSERT OR REPLACE INTO content_articles(article_id,project_id,keyword,status,page_type) VALUES(?,?,?,'generating','article')",
        (article_id, project_id, keyword)
    )
    db.commit()

    print(f"\n{'='*80}")
    print(f"LIVE TEST: '{keyword}'")
    print(f"Article ID: {article_id}")
    print(f"Provider: Ollama REMOTE (mistral:7b-instruct-q4_K_M @ 172.235.16.165:8080)")
    print(f"{'='*80}\n")

    t_start = time.time()

    pipeline = SEOContentPipeline(
        keyword=keyword,
        project_id=project_id,
        article_id=article_id,
        title="",
        intent="commercial",
        word_count=2000,
        supporting_keywords=["buy black pepper online", "kerala black pepper price", "malabar pepper", "tellicherry pepper"],
        target_audience="spice buyers, home cooks, wholesale buyers",
        content_type="blog",
        page_type="article",
        ai_routing=routing,
        db=db,
    )

    try:
        result = await pipeline.run()
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ PIPELINE FAILED: {e}")
        print(f"{'='*80}")
        import traceback
        traceback.print_exc()
        # Still try to report partial results
        t_total = time.time() - t_start
        print(f"\nFailed after {t_total:.1f}s")
        print("\n── STEP STATUS AT FAILURE ──")
        for i, step in enumerate(pipeline.state.steps):
            status_raw = step.status or "unknown"
            icon = "✅" if status_raw == "done" else "❌" if status_raw == "error" else "⏳"
            print(f"  {icon} S{i+1:2d} {step.name:30s} {step.summary or '(no summary)'}")
        return

    t_total = time.time() - t_start

    print(f"\n{'='*80}")
    print(f"PIPELINE COMPLETE — {t_total:.1f}s total")
    print(f"{'='*80}\n")

    # Step timings
    print("── PHASE BREAKDOWN ──")
    steps = pipeline.state.steps
    for i, step in enumerate(steps):
        status_raw = step.status or "unknown"
        icon = "✅" if status_raw in ("done", "completed") else "⚠️" if status_raw == "skipped" else "❌" if status_raw == "error" else "⏳"
        elapsed_str = "—"
        if step.started_at and step.ended_at:
            try:
                from datetime import datetime, timezone
                t0 = datetime.fromisoformat(step.started_at)
                t1 = datetime.fromisoformat(step.ended_at)
                elapsed_str = f"{(t1 - t0).total_seconds():.1f}s"
            except Exception:
                elapsed_str = "?"
        name = step.name if hasattr(step, 'name') else f"Step {i+1}"
        summary = step.summary or "(no summary)"
        print(f"  {icon} S{i+1:2d} {name:30s} {elapsed_str:>8s}  {summary[:80]}")

    # Content stats
    html = pipeline.state.final_html or pipeline.state.draft_html or ""
    text = re.sub(r"<[^>]+>", " ", html)
    words = text.split()
    word_count = len(words)

    h2_count = len(re.findall(r"<h2", html, re.I))
    h3_count = len(re.findall(r"<h3", html, re.I))
    p_count = len(re.findall(r"<p", html, re.I))
    table_count = len(re.findall(r"<table", html, re.I))
    list_count = len(re.findall(r"<[uo]l", html, re.I))
    link_count = len(re.findall(r"<a\s", html, re.I))
    bold_count = len(re.findall(r"<strong", html, re.I))

    print(f"\n── CONTENT STATS ──")
    print(f"  Words:      {word_count}")
    print(f"  H2s:        {h2_count}")
    print(f"  H3s:        {h3_count}")
    print(f"  Paragraphs: {p_count}")
    print(f"  Tables:     {table_count}")
    print(f"  Lists:      {list_count}")
    print(f"  Links:      {link_count}")
    print(f"  Bold:       {bold_count}")

    # Quality scoring
    print(f"\n── QUALITY SCORE ──")
    scored = None
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

        print(f"\n  ── PILLAR BREAKDOWN ──")
        for pillar in scored.get("pillars", []):
            pct = round(pillar['earned'] / pillar['max'] * 100) if pillar['max'] > 0 else 0
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"    {pillar['name']:30s} {pillar['earned']:3d}/{pillar['max']:3d} ({pct:3d}%) {bar}")

        failing = [r for r in scored["rules"] if not r.get("passed")]
        if failing:
            print(f"\n  ── FAILING RULES ({len(failing)}) ──")
            for r in sorted(failing, key=lambda x: x.get("points_max", 0), reverse=True)[:25]:
                pts_lost = r.get("points_max", 0) - r.get("points_earned", 0)
                print(f"    {r.get('rule_id','?'):5s} {r.get('name',''):40s} -{pts_lost}pts  {r.get('fix','')[:60]}")
    except Exception as e:
        print(f"  Scoring failed: {e}")
        import traceback
        traceback.print_exc()

    # Pipeline log analysis
    print(f"\n── PIPELINE LOG ANALYSIS ──")
    logs = pipeline._logs if hasattr(pipeline, '_logs') else []
    log_by_level = {}
    for entry in logs:
        lvl = entry.get("level", "info") if isinstance(entry, dict) else "info"
        log_by_level[lvl] = log_by_level.get(lvl, 0) + 1
    for lvl in ["error", "warn", "info", "success"]:
        if lvl in log_by_level:
            icon = "❌" if lvl == "error" else "⚠️" if lvl == "warn" else "ℹ️" if lvl == "info" else "✅"
            print(f"  {icon} {lvl}: {log_by_level[lvl]} entries")

    errors = [e for e in logs if isinstance(e, dict) and e.get("level") in ("error", "warn")]
    if errors:
        print(f"\n  ── ERRORS & WARNINGS ──")
        for e in errors[:20]:
            print(f"    [{e.get('level','?').upper()}] S{e.get('step','?')}: {e.get('msg', e.get('message',''))[:100]}")

    # Cost
    print(f"\n── COST ESTIMATE ──")
    print(f"  Provider: Ollama REMOTE (self-hosted) = $0.00")
    print(f"  Total time: {t_total:.1f}s")

    # Save output
    with open("/tmp/pepper_test_output.html", "w") as f:
        f.write(html)
    print(f"  Output saved to: /tmp/pepper_test_output.html")

    # Final verdict
    print(f"\n{'='*80}")
    score_pct = scored['percentage'] if scored else pipeline.state.seo_score
    if score_pct >= 85:
        print(f"  ✅ GRADE A — {score_pct}% — Production quality")
    elif score_pct >= 70:
        print(f"  ⚠️ GRADE B — {score_pct}% — Good, needs minor fixes")
    elif score_pct >= 55:
        print(f"  ⚠️ GRADE C — {score_pct}% — Mediocre, needs improvement")
    else:
        print(f"  ❌ GRADE D/F — {score_pct}% — Poor quality")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(run_test())

#!/usr/bin/env python3
"""
Live test: "kerala clove online" with Ollama local (qwen2.5:3b)

Testing objectives:
1. Full quality restored (3 quality loop passes, full prompts, 4000+ tokens)
2. Dynamic timeout calculation working
3. Actual time and final score with slow model
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
faulthandler.register(signal.SIGUSR1)

sys.path.insert(0, os.path.dirname(__file__))

# Force Ollama LOCAL routing
os.environ["OLLAMA_URL"] = "http://localhost:11434"
os.environ["OLLAMA_MODEL"] = "qwen2.5:3b"


async def run_test():
    from engines.content_generation_engine import SEOContentPipeline, AIRoutingConfig, StepAIConfig

    # All-Ollama routing
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
        score=StepAIConfig("skip", "skip", "skip"),
        quality_loop=ollama_step,
    )

    keyword = "kerala clove online"
    project_id = "test_clove"

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
    print(f"🌶️ LIVE TEST: '{keyword}'")
    print(f"Article ID: {article_id}")
    print(f"Model: Ollama Local (qwen2.5:3b @ localhost:11434)")
    print(f"Expected time: 40-60 min (slow model, FULL quality)")
    print(f"Target score: 85%+ Grade A")
    print(f"{'='*80}\n")

    t_start = time.time()

    pipeline = SEOContentPipeline(
        keyword=keyword,
        project_id=project_id,
        article_id=article_id,
        title="",
        intent="commercial",
        word_count=2000,
        supporting_keywords=["buy cloves online",  "kerala cloves price", "clove spice"],
        target_audience="spice buyers, restaurants, home cooks",
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
        t_total = time.time() - t_start
        print(f"\nFailed after {t_total/60:.1f} min")
        return

    t_total = time.time() - t_start

    print(f"\n{'='*80}")
    print(f"✅ PIPELINE COMPLETE — {t_total/60:.1f} min ({t_total:.0f}s)")
    print(f"{'='*80}\n")

    # Content stats
    html = pipeline.state.final_html or ""
    text = re.sub(r"<[^>]+>", " ", html)
    word_count = len(text.split())

    print(f"── CONTENT STATS ──")
    print(f"  Words: {word_count}")

    # Quality scoring
    print(f"\n── QUALITY SCORE ──")
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
            for r in sorted(failing, key=lambda x: x.get("points_max", 0), reverse=True)[:15]:
                pts_lost = r.get("points_max", 0) - r.get("points_earned", 0)
                print(f"    {r.get('rule_id','?'):5s} {r.get('name',''):40s} -{pts_lost}pts")
    except Exception as e:
        print(f"  Scoring failed: {e}")

    # Pipeline log
    logs = pipeline._logs if hasattr(pipeline, '_logs') else []
    errors = [e for e in logs if isinstance(e, dict) and e.get("level") in ("error", "warn")]
    if errors:
        print(f"\n── ERRORS & WARNINGS ({len(errors)}) ──")
        for e in errors[:10]:
            print(f"  [{e.get('level','?').upper()}] S{e.get('step','?')}: {e.get('msg', e.get('message',''))[:80]}")

    # Save
    with open("/tmp/clove_test_output.html", "w") as f:
        f.write(html)
    print(f"\n  Output saved to: /tmp/clove_test_output.html")

    # Final verdict
    score_pct = scored['percentage'] if scored else 0
    print(f"\n{'='*80}")
    if score_pct >= 85:
        print(f"  ✅ GRADE A — {score_pct}% — Production quality")
    elif score_pct >= 70:
        print(f"  ⚠️ GRADE B — {score_pct}% — Good")
    else:
        print(f"  ❌ GRADE C/D — {score_pct}% — Needs work")
    print(f"  Time: {t_total/60:.1f} min | Words: {word_count}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(run_test())

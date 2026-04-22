"""
Live E2E test — Cinnamon keyword pipeline.

Pillars: Organic Cinnamon, Spices, Buy Online
Runs: Phase 1 (profile) → Expand → Organize → Apply
Then generates 200+ content calendar entries.
"""
import os, sys, json, time, traceback

os.chdir("/root/ANNASEOv1")
sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2 import db
from engines.kw2.keyword_brain import KeywordBrain
from engines.kw2.organizer import Organizer
from engines.kw2.applicator import Applicator

db.init_kw2_db()

PROJECT_ID = "cinnamon_e2e_001"
PILLARS = ["Organic Cinnamon", "Cinnamon Spices", "Buy Cinnamon Online"]
PROFILE = {
    "domain": "cinnamonworld.com",
    "universe": "Cinnamon & Spice Products",
    "pillars": PILLARS,
    "modifiers": [
        "ceylon", "organic", "wholesale", "bulk", "powder",
        "sticks", "extract", "ground", "true", "premium",
        "pure", "natural", "fair trade", "single origin",
    ],
    "audience": [
        "health-conscious consumers",
        "professional chefs",
        "spice retailers",
        "home bakers",
    ],
    "geo_scope": "global",
    "business_type": "ecommerce",
    "negative_scope": [
        "candle", "air freshener", "perfume", "essential oil diffuser",
        "incense", "potpourri", "fragrance",
    ],
    "intent_distribution": {"commercial": 60, "informational": 25, "navigational": 15},
}


def section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def main():
    start_all = time.time()

    # ── Phase 1: Setup ───────────────────────────────────────────────────
    section("PHASE 1: Business Profile Setup")
    db.save_business_profile(PROJECT_ID, PROFILE)
    session_id = db.create_session(PROJECT_ID, "auto", "v2")
    print(f"  Project:  {PROJECT_ID}")
    print(f"  Session:  {session_id}")
    print(f"  Pillars:  {PILLARS}")
    print(f"  Universe: {PROFILE['universe']}")
    loaded = db.load_business_profile(PROJECT_ID)
    assert loaded is not None, "Profile not saved!"
    print("  ✅ Profile saved & verified")

    # ── Phase 2: Expand ──────────────────────────────────────────────────
    section("PHASE 2: Keyword Expansion (KeywordBrain)")
    t0 = time.time()

    brain = KeywordBrain()
    try:
        stats = brain.expand(PROJECT_ID, session_id, ai_provider="auto")
    except Exception as e:
        print(f"  ❌ Expand failed: {e}")
        traceback.print_exc()
        return

    expand_time = time.time() - t0
    print(f"  Generated:        {stats.get('total_generated', 0)}")
    print(f"  After filter:     {stats.get('after_filter', 0)}")
    print(f"  After merge:      {stats.get('after_merge', 0)}")
    print(f"  Validated:        {stats.get('validated', 0)}")
    print(f"  After dedup:      {stats.get('after_dedup', 0)}")
    print(f"  Rejected:         {stats.get('rejected', 0)}")
    print(f"  Clusters:         {stats.get('clusters', 0)}")
    print(f"  Per-pillar:       {stats.get('per_pillar', {})}")
    print(f"  Time:             {expand_time:.1f}s")

    # Check we have enough keywords
    kw_count = db.count_keywords(session_id, status="candidate")
    print(f"\n  📊 Candidate keywords in DB: {kw_count}")
    if kw_count < 50:
        print(f"  ⚠️  Low keyword count ({kw_count}) — may affect quality")

    # Sample some keywords
    sample = db.load_keywords(session_id, status="candidate")[:20]
    print(f"\n  Sample keywords ({min(20, len(sample))}):")
    for kw in sample:
        print(f"    - {kw['keyword']} [intent={kw.get('intent','-')}, "
              f"pillars={kw.get('pillars','-')}, "
              f"score={kw.get('ai_relevance', 0):.2f}]")

    # Auto-approve all clusters for next phase
    section("PHASE 2b: Auto-approve all clusters")
    conn = db.get_conn()
    try:
        clusters = conn.execute(
            "SELECT * FROM kw2_clusters WHERE session_id=?", (session_id,)
        ).fetchall()
        cluster_list = [dict(c) for c in clusters]
        print(f"  Found {len(cluster_list)} clusters to approve")
        for cl in cluster_list:
            conn.execute(
                "UPDATE kw2_clusters SET status='approved' WHERE id=?",
                (cl["id"],)
            )
        # Approve all candidate keywords
        conn.execute(
            "UPDATE kw2_keywords SET status='approved' WHERE session_id=? AND status='candidate'",
            (session_id,)
        )
        conn.commit()
        approved_count = conn.execute(
            "SELECT count(*) FROM kw2_keywords WHERE session_id=? AND status='approved'",
            (session_id,)
        ).fetchone()[0]
        print(f"  ✅ Approved {approved_count} keywords, {len(cluster_list)} clusters")
    finally:
        conn.close()

    db.set_phase_status(session_id, "expand", "done")

    # ── Phase 3: Organize ────────────────────────────────────────────────
    section("PHASE 3: Organize (Scoring + Clustering + Relations + Top-100)")
    t0 = time.time()

    organizer = Organizer()
    try:
        org_stats = organizer.organize(PROJECT_ID, session_id, ai_provider="auto")
    except Exception as e:
        print(f"  ❌ Organize failed: {e}")
        traceback.print_exc()
        return

    org_time = time.time() - t0
    print(f"  Scored:           {org_stats.get('scored', 0)}")
    print(f"  Relations:        {org_stats.get('total_relations', 0)}")
    print(f"  Pillar stats:     {org_stats.get('pillar_stats', {})}")
    print(f"  Time:             {org_time:.1f}s")

    # Print graph stats
    try:
        graph = organizer.get_graph_data(session_id)
        print(f"\n  📊 Graph: {len(graph.get('nodes',[]))} nodes, "
              f"{len(graph.get('edges',[]))} edges")
    except Exception:
        pass

    # Print top-100 sample
    try:
        top100_list = organizer.get_top100(session_id)
        print(f"\n  Top-100 total: {len(top100_list)} keywords")
        for kw in top100_list[:10]:
            print(f"    - {kw['keyword']} (score={kw.get('final_score',0):.3f}, "
                  f"intent={kw.get('intent','-')}, pillars={kw.get('pillars',[])})")
    except Exception as e:
        print(f"  ⚠️  Top-100 read error: {e}")

    # ── Phase 4: Apply ───────────────────────────────────────────────────
    section("PHASE 4: Apply (Links + Calendar + Strategy)")
    t0 = time.time()

    applicator = Applicator()
    try:
        app_stats = applicator.apply(
            PROJECT_ID, session_id, ai_provider="auto",
            blogs_per_week=5,       # 5 blogs/week
            duration_weeks=52,      # full year = 260 articles
        )
    except Exception as e:
        print(f"  ❌ Apply failed: {e}")
        traceback.print_exc()
        return

    app_time = time.time() - t0
    print(f"  Links:     {app_stats.get('links', {})}")
    print(f"  Calendar:  {app_stats.get('calendar', {})}")
    print(f"  Strategy:  {'generated' if app_stats.get('strategy_generated') else 'failed'}")
    print(f"  Time:      {app_time:.1f}s")

    # ── Content Summary ──────────────────────────────────────────────────
    section("CONTENT GENERATION SUMMARY")

    conn = db.get_conn()
    try:
        # Calendar entries = content pieces
        total_cal = conn.execute(
            "SELECT count(*) FROM kw2_calendar WHERE session_id=?", (session_id,)
        ).fetchone()[0]
        print(f"\n  📅 Total calendar entries (content pieces): {total_cal}")

        if total_cal >= 200:
            print(f"  ✅ TARGET MET: {total_cal} >= 200 content pieces")
        else:
            print(f"  ⚠️  Below target: {total_cal} < 200")

        # By pillar
        pillar_counts = conn.execute(
            "SELECT pillar, count(*) FROM kw2_calendar WHERE session_id=? GROUP BY pillar",
            (session_id,)
        ).fetchall()
        print(f"\n  Content by pillar:")
        for row in pillar_counts:
            print(f"    - {row[0]}: {row[1]} articles")

        # By month (first 3 months)
        month_counts = conn.execute(
            """SELECT substr(scheduled_date, 1, 7) as month, count(*)
               FROM kw2_calendar WHERE session_id=?
               GROUP BY month ORDER BY month LIMIT 6""",
            (session_id,)
        ).fetchall()
        print(f"\n  Content by month:")
        for row in month_counts:
            print(f"    - {row[0]}: {row[1]} articles")

        # Links summary
        total_links = conn.execute(
            "SELECT count(*) FROM kw2_internal_links WHERE session_id=?",
            (session_id,)
        ).fetchone()[0]
        print(f"\n  🔗 Internal links: {total_links}")

        link_types = conn.execute(
            "SELECT link_type, count(*) FROM kw2_internal_links WHERE session_id=? GROUP BY link_type",
            (session_id,)
        ).fetchall()
        for row in link_types:
            print(f"    - {row[0]}: {row[1]}")

        # Strategy preview
        strategy_raw = conn.execute(
            "SELECT strategy_json FROM kw2_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if strategy_raw and strategy_raw[0]:
            strat = json.loads(strategy_raw[0])
            if isinstance(strat, dict):
                print(f"\n  📋 Strategy keys: {list(strat.keys())}")
                if "summary" in strat:
                    print(f"  Summary: {str(strat['summary'])[:300]}")
            elif isinstance(strat, str):
                print(f"\n  📋 Strategy: {strat[:300]}")
    finally:
        conn.close()

    # ── Quality Evaluation ───────────────────────────────────────────────
    section("KEYWORD QUALITY EVALUATION")

    all_kws = db.load_keywords(session_id)
    approved = [k for k in all_kws if k.get("status") in ("approved", "top100")]
    top100_all = [k for k in all_kws if k.get("status") == "top100"]

    # 1. Intent distribution
    intent_counts = {"commercial": 0, "informational": 0, "navigational": 0,
                     "transactional": 0, "other": 0}
    for k in approved:
        i = k.get("intent", "other").lower()
        if i in intent_counts:
            intent_counts[i] += 1
        else:
            intent_counts["other"] += 1

    total_with_intent = sum(intent_counts.values())
    print(f"\n  Intent distribution (approved keywords):")
    for intent, count in intent_counts.items():
        pct = (count / total_with_intent * 100) if total_with_intent else 0
        target_pct = PROFILE["intent_distribution"].get(intent, 0)
        diff = abs(pct - target_pct)
        flag = "⚠️" if diff > 20 else "✅"
        print(f"    {flag} {intent}: {count} ({pct:.1f}%) [target: {target_pct}%]")

    # 2. Pillar coverage
    print(f"\n  Pillar coverage:")
    for p in PILLARS:
        p_kws = [k for k in approved if p in k.get("pillars", [])]
        print(f"    - {p}: {len(p_kws)} keywords")

    # 3. Role distribution
    role_counts = {"pillar": 0, "bridge": 0, "supporting": 0}
    for k in approved:
        r = k.get("role", "supporting")
        role_counts[r] = role_counts.get(r, 0) + 1
    print(f"\n  Role distribution:")
    for role, count in role_counts.items():
        print(f"    - {role}: {count}")

    # 4. Score distribution (approved)
    if approved:
        scores = [k.get("final_score", 0) or k.get("ai_relevance", 0) for k in approved]
        avg_score = sum(scores) / len(scores) if scores else 0
        max_score = max(scores) if scores else 0
        min_score = min(scores) if scores else 0
        high_quality = sum(1 for s in scores if s >= 0.7)
        print(f"\n  Score distribution:")
        print(f"    Avg:  {avg_score:.3f}")
        print(f"    Min:  {min_score:.3f}")
        print(f"    Max:  {max_score:.3f}")
        print(f"    >=0.7: {high_quality} ({high_quality/len(scores)*100:.0f}%)")

    # 5. Cluster quality
    conn = db.get_conn()
    try:
        clusters = conn.execute(
            "SELECT * FROM kw2_clusters WHERE session_id=?", (session_id,)
        ).fetchall()
        clusters = [dict(c) for c in clusters]
        print(f"\n  Cluster quality:")
        print(f"    Total clusters: {len(clusters)}")
        if clusters:
            sizes = [c.get("keyword_count", 0) for c in clusters]
            print(f"    Avg size: {sum(sizes)/len(sizes):.1f}")
            print(f"    Min/Max: {min(sizes)}/{max(sizes)}")
            tiny = sum(1 for s in sizes if s < 3)
            print(f"    Tiny (<3 kws): {tiny}")
    finally:
        conn.close()

    # ── Final Summary ────────────────────────────────────────────────────
    total_time = time.time() - start_all
    section("FINAL SUMMARY")
    print(f"  Total keywords (approved): {len(approved)}")
    print(f"  Top-100 per pillar:        {len(top100_all)}")
    print(f"  Content pieces:            {total_cal}")
    print(f"  Internal links:            {total_links}")
    print(f"  Total time:                {total_time:.1f}s")

    quality_issues = []
    if len(approved) < 100:
        quality_issues.append(f"Low keyword count: {len(approved)} (target: 200+)")
    if total_cal < 200:
        quality_issues.append(f"Content below target: {total_cal} < 200")
    if avg_score < 0.5:
        quality_issues.append(f"Low avg score: {avg_score:.3f}")
    if intent_counts.get("commercial", 0) < 10:
        quality_issues.append("Very few commercial intent keywords")
    if any(len([k for k in approved if p in k.get("pillars", [])]) < 20
           for p in PILLARS):
        quality_issues.append("Uneven pillar coverage")

    if quality_issues:
        print(f"\n  ⚠️  Quality issues found:")
        for issue in quality_issues:
            print(f"    - {issue}")
    else:
        print(f"\n  ✅ All quality checks passed!")

    print()


if __name__ == "__main__":
    main()

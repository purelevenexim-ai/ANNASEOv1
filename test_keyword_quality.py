#!/usr/bin/env python3
"""
Keyword Quality Test — Tests AI scoring pipeline with multiple businesses.
Run: python3 test_keyword_quality.py
"""
import requests, json, time, sys, sqlite3
from collections import Counter

API = "http://localhost:8000"

def get_token():
    r = requests.post(f"{API}/api/auth/login",
                      data={"username": "anna@gmail.com", "password": "admin"})
    return r.json().get("access_token", "")

def create_test_project(token, name, industry, btype, locations, biz_locs, products, personas, pillars_map):
    """Create project + session + keywords for testing."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Create project
    r = requests.post(f"{API}/api/projects", headers=headers, json={
        "name": name, "industry": industry, "business_type": btype,
        "target_locations": locations,
        "business_locations": biz_locs,
    })
    proj = r.json()
    project_id = proj.get("project_id", "")
    if not project_id:
        print(f"  ERROR creating project: {proj}")
        return None, None, None, None

    # Create audience profile
    try:
        db = sqlite3.connect("annaseo.db")
        db.execute("""INSERT OR REPLACE INTO audience_profiles 
                      (project_id, products, personas, target_audience, usp)
                      VALUES (?, ?, ?, ?, ?)""",
                   (project_id, json.dumps(products), json.dumps(personas),
                    btype, f"Leading {industry} provider"))
        db.commit()
        db.close()
    except Exception as e:
        print(f"  Warning: audience profile: {e}")

    # Create keyword input session
    r = requests.post(f"{API}/api/ki/{project_id}/input", headers=headers, json={
        "pillar_support_map": pillars_map,
        "intent_focus": "mixed",
        "geographic_focus": biz_locs[0] if biz_locs else "Global",
        "business_intent": "mixed",
    })
    sess_data = r.json()
    session_id = sess_data.get("session_id", "")

    # Generate keywords via research stream (simulated — just use Google autosuggest-like keywords)
    # We'll construct test keywords manually to simulate all sources
    test_keywords = []
    pillars = list(pillars_map.keys())

    for pillar in pillars:
        supporting = pillars_map.get(pillar, [])
        # User supporting keywords (source=user)
        for sk in supporting:
            test_keywords.append({
                "keyword": f"{sk} {pillar}".lower(),
                "pillar": pillar, "source": "user", "intent": "informational",
                "keyword_type": "supporting"
            })
            test_keywords.append({
                "keyword": f"{pillar} {sk}".lower(),
                "pillar": pillar, "source": "user", "intent": "informational",
                "keyword_type": "supporting"
            })

        # Cross-multiply (source=cross_multiply)
        for sk in supporting:
            for loc in locations[:2]:
                test_keywords.append({
                    "keyword": f"{sk} {pillar} in {loc}".lower(),
                    "pillar": pillar, "source": "cross_multiply", "intent": "commercial",
                    "keyword_type": "long_tail"
                })

        # Google autosuggest style (source=google)
        google_patterns = [
            f"what is {pillar}", f"how to use {pillar}", f"best {pillar}",
            f"{pillar} benefits", f"{pillar} side effects", f"{pillar} recipe",
            f"{pillar} price", f"buy {pillar}", f"{pillar} online",
            f"{pillar} wholesale", f"{pillar} suppliers", f"{pillar} vs",
            f"organic {pillar}", f"{pillar} powder", f"{pillar} tea",
            f"where to buy {pillar}", f"{pillar} for cooking",
            f"cheap {pillar}", f"{pillar} near me", f"fresh {pillar}",
            f"how to grow {pillar}", f"{pillar} plant", f"{pillar} tree",
            f"why is {pillar} expensive", f"{pillar} nutrition facts",
            f"{pillar} health benefits", f"is {pillar} good for you",
            f"{pillar} cake recipe", f"{pillar} smoothie", f"{pillar} latte",
            f"{pillar} essential oil", f"{pillar} supplement",
            f"{pillar} face mask", f"diy {pillar} scrub",
        ]
        # Add some noise / irrelevant keywords
        google_patterns.extend([
            f"{pillar}", f"organic", f"powder", f"spices",
            f"{pillar} desktop linux", f"{pillar} software",
            f"{pillar} movie", f"{pillar} song lyrics",
        ])
        for p in google_patterns:
            test_keywords.append({
                "keyword": p.lower(), "pillar": pillar.lower(),
                "source": "google", "intent": "informational",
                "keyword_type": "long_tail" if len(p.split()) >= 3 else "short_tail"
            })

        # Site crawl keywords (source=site_crawl)
        for prod in products[:3]:
            test_keywords.append({
                "keyword": f"{prod} {pillar}".lower(),
                "pillar": pillar, "source": "site_crawl", "intent": "commercial",
                "keyword_type": "supporting"
            })

        # Wikipedia (source=wikipedia)
        wiki_patterns = [
            f"{pillar} history", f"{pillar} origin", f"{pillar} cultivation",
            f"{pillar} species", f"{pillar} trade",
        ]
        for wp in wiki_patterns:
            test_keywords.append({
                "keyword": wp.lower(), "pillar": pillar, "source": "wikipedia",
                "intent": "informational", "keyword_type": "long_tail"
            })

    # Deduplicate
    seen = set()
    unique_kws = []
    for kw in test_keywords:
        k = kw["keyword"].lower().strip()
        if k and k not in seen:
            seen.add(k)
            unique_kws.append(kw)

    return project_id, session_id, unique_kws, pillars


def run_cluster_test(token, project_id, session_id, keywords, pillars, label):
    """Run the cluster-keywords endpoint and analyze results."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"\n{'='*70}")
    print(f"TEST: {label}")
    print(f"{'='*70}")
    print(f"  Input: {len(keywords)} keywords, {len(pillars)} pillars: {pillars}")

    source_dist = Counter(kw["source"] for kw in keywords)
    print(f"  Sources: {dict(source_dist)}")

    start = time.time()
    r = requests.post(f"{API}/api/ki/{project_id}/cluster-keywords", headers=headers, json={
        "keywords": keywords,
        "pillars": pillars,
        "session_id": session_id,
        "business_profile": {},
    }, timeout=180)
    elapsed = time.time() - start

    if not r.ok:
        print(f"  ERROR: {r.status_code} — {r.text[:200]}")
        return None

    data = r.json()
    print(f"\n  ⏱  Completed in {elapsed:.1f}s")
    print(f"  📊 Scored: {data['total_scored']} | Kept: {data['total_kept']} | Dropped: {data['total_dropped']}")
    print(f"  👤 User-boosted: {data.get('user_boosted', '?')} | 🤖 AI-generated: {data.get('ai_generated', '?')}")

    # Analyze kept keywords
    all_scored = data.get("all_scored", [])
    kept_kws = [kw for kw in all_scored if kw["ai_score"] >= 30][:100]

    # Score distribution
    score_ranges = {"90-100": 0, "70-89": 0, "50-69": 0, "40-49": 0, "30-39": 0, "<30": 0}
    for kw in all_scored:
        s = kw["ai_score"]
        if s >= 90: score_ranges["90-100"] += 1
        elif s >= 70: score_ranges["70-89"] += 1
        elif s >= 50: score_ranges["50-69"] += 1
        elif s >= 40: score_ranges["40-49"] += 1
        elif s >= 30: score_ranges["30-39"] += 1
        else: score_ranges["<30"] += 1
    print(f"\n  Score Distribution (all {len(all_scored)} scored):")
    for band, count in score_ranges.items():
        bar = "█" * (count // 2)
        print(f"    {band:>7}: {count:3d} {bar}")

    # Source distribution in kept
    kept_sources = Counter(kw["source"] for kw in kept_kws)
    print(f"\n  Sources in top {len(kept_kws)} kept:")
    for src, cnt in kept_sources.most_common():
        print(f"    {src:<16}: {cnt}")

    # Business potential in kept
    bp_dist = Counter(kw.get("business_potential", 0) for kw in kept_kws)
    print(f"\n  Business Potential (kept):")
    for bp in sorted(bp_dist.keys(), reverse=True):
        print(f"    BP{bp}: {bp_dist[bp]} keywords")

    # User boost impact
    user_in_kept = [kw for kw in kept_kws if kw.get("user_boost", 0) > 0]
    if user_in_kept:
        print(f"\n  User Keyword Boost Impact (+20): {len(user_in_kept)} keywords boosted")
        for kw in user_in_kept[:5]:
            print(f"    +20 → {kw['ai_score']:3d} | {kw['keyword']} (raw={kw.get('raw_ai_score', '?')})")

    # Top 15 keywords
    print(f"\n  🏆 Top 15 Keywords:")
    for i, kw in enumerate(kept_kws[:15]):
        boost_tag = " [+20 USER]" if kw.get("user_boost", 0) > 0 else ""
        ai_tag = " [AI-GEN]" if kw.get("source") == "ai_generated" else ""
        bp_tag = f" BP{kw.get('business_potential', '?')}"
        print(f"    {i+1:2d}. {kw['ai_score']:3d}{bp_tag} | {kw['keyword']:<50} [{kw['source']}] {kw.get('intent','')}{boost_tag}{ai_tag}")

    # Bottom 10 (rejected)
    rejected = sorted(all_scored, key=lambda x: x["ai_score"])[:10]
    print(f"\n  ❌ Bottom 10 (Rejected):")
    for kw in rejected:
        print(f"    {kw['ai_score']:3d} | {kw['keyword']:<50} [{kw['source']}] — {kw.get('ai_reasoning', '')}")

    # Clusters
    print(f"\n  📁 Clusters:")
    for pillar, info in data.get("clustered", {}).items():
        clusters = info.get("clusters", [])
        print(f"    Pillar '{pillar}': {info['total']} kws, {len(clusters)} clusters")
        for cl in clusters[:5]:
            print(f"      • {cl['cluster_name']} ({cl['keyword_count']} kws, avg={cl['avg_score']})")

    return data


def main():
    token = get_token()
    if not token:
        print("ERROR: Could not get auth token")
        sys.exit(1)
    print(f"✓ Authenticated")

    results = {}

    # ═══ BUSINESS 1: Indian Spice Exporter (existing project) ═══
    print("\n\n" + "━"*70)
    print("BUSINESS 1: Indian Spice Company (Cinnamon)")
    print("━"*70)

    # Use existing project data
    db = sqlite3.connect("annaseo.db")
    db.row_factory = sqlite3.Row
    rows = db.execute('SELECT keyword, pillar_keyword, source, intent, keyword_type FROM keyword_universe_items WHERE project_id="proj_8ae940595b"').fetchall()
    existing_kws = [{"keyword": r["keyword"], "pillar": r["pillar_keyword"], "source": r["source"],
                     "intent": r["intent"], "keyword_type": r["keyword_type"]} for r in rows]
    sess = db.execute('SELECT session_id FROM keyword_universe_items WHERE project_id="proj_8ae940595b" LIMIT 1').fetchone()
    existing_session = sess["session_id"] if sess else ""
    existing_pillars = list(set(r["pillar_keyword"] for r in rows if r["pillar_keyword"]))
    db.close()

    if existing_kws:
        results["spice"] = run_cluster_test(token, "proj_8ae940595b", existing_session,
                                           existing_kws, existing_pillars, "Indian Spice Exporter — Cinnamon")

    # ═══ BUSINESS 2: SaaS Company ═══
    print("\n\n" + "━"*70)
    print("BUSINESS 2: SaaS Project Management Tool")
    print("━"*70)

    pid2, sid2, kws2, pils2 = create_test_project(
        token,
        name="TaskFlow SaaS",
        industry="tech_saas",
        btype="B2B",
        locations=["United States", "United Kingdom", "Canada", "Australia"],
        biz_locs=["San Francisco, USA"],
        products=["project management software", "task tracking tool", "team collaboration platform", "agile sprint board"],
        personas=["startup founders", "project managers", "engineering teams", "remote teams", "small business owners"],
        pillars_map={
            "project management": ["agile", "scrum", "kanban", "remote teams", "sprint planning"],
            "team collaboration": ["remote work", "async communication", "productivity", "task tracking"],
        }
    )
    if kws2:
        results["saas"] = run_cluster_test(token, pid2, sid2, kws2, pils2, "SaaS Project Management — B2B")

    # ═══ BUSINESS 3: Local Bakery ═══
    print("\n\n" + "━"*70)
    print("BUSINESS 3: Local Artisan Bakery")
    print("━"*70)

    pid3, sid3, kws3, pils3 = create_test_project(
        token,
        name="Sweet Rise Bakery",
        industry="restaurant",
        btype="B2C",
        locations=["Austin, Texas", "Texas", "United States"],
        biz_locs=["Austin, Texas"],
        products=["sourdough bread", "custom wedding cakes", "artisan pastries", "gluten-free options", "catering services"],
        personas=["wedding planners", "health-conscious consumers", "foodies", "event organizers", "local families"],
        pillars_map={
            "sourdough bread": ["artisan", "starter", "recipe", "gluten free", "whole wheat"],
            "wedding cakes": ["custom design", "tiered", "fondant", "buttercream", "rustic"],
        }
    )
    if kws3:
        results["bakery"] = run_cluster_test(token, pid3, sid3, kws3, pils3, "Local Bakery — Austin")

    # ═══ SUMMARY ═══
    print("\n\n" + "═"*70)
    print("FINAL SUMMARY")
    print("═"*70)

    for biz_name, data in results.items():
        if not data:
            continue
        print(f"\n  {biz_name.upper()}:")
        print(f"    Scored: {data['total_scored']} → Kept: {data['total_kept']} → Dropped: {data['total_dropped']}")
        print(f"    User boosted: {data.get('user_boosted', '?')} | AI generated: {data.get('ai_generated', '?')}")
        all_s = data.get("all_scored", [])
        if all_s:
            kept = [k for k in all_s if k["ai_score"] >= 30][:100]
            avg_kept = sum(k["ai_score"] for k in kept) / len(kept) if kept else 0
            avg_all = sum(k["ai_score"] for k in all_s) / len(all_s) if all_s else 0
            print(f"    Avg score (kept): {avg_kept:.1f} | Avg score (all): {avg_all:.1f}")
            bp3 = sum(1 for k in kept if k.get("business_potential", 0) >= 3)
            bp2 = sum(1 for k in kept if k.get("business_potential", 0) == 2)
            print(f"    BP3 (revenue): {bp3} | BP2 (authority): {bp2} | BP0-1 (low value): {len(kept) - bp3 - bp2}")

    print("\n✅ All tests complete!")


if __name__ == "__main__":
    main()

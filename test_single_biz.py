#!/usr/bin/env python3
"""Quick single-business test for keyword pipeline."""
import requests, json, time, sys, sqlite3
from collections import Counter

API = "http://localhost:8000"
BIZ = sys.argv[1] if len(sys.argv) > 1 else "saas"

def get_token():
    r = requests.post(f"{API}/api/auth/login", data={"username": "anna@gmail.com", "password": "admin"})
    return r.json().get("access_token", "")

BUSINESSES = {
    "saas": {
        "name": "TaskFlow SaaS", "industry": "tech_saas", "btype": "B2B",
        "locations": ["United States", "United Kingdom", "Canada", "Australia"],
        "biz_locs": ["San Francisco, USA"],
        "products": ["project management software", "task tracking tool", "team collaboration platform", "agile sprint board"],
        "personas": ["startup founders", "project managers", "engineering teams", "remote teams", "small business owners"],
        "pillars_map": {
            "project management": ["agile", "scrum", "kanban", "remote teams", "sprint planning"],
            "team collaboration": ["remote work", "async communication", "productivity", "task tracking"],
        }
    },
    "bakery": {
        "name": "Sweet Rise Bakery", "industry": "restaurant", "btype": "B2C",
        "locations": ["Austin, Texas", "Texas", "United States"],
        "biz_locs": ["Austin, Texas"],
        "products": ["sourdough bread", "custom wedding cakes", "artisan pastries", "gluten-free options", "catering services"],
        "personas": ["wedding planners", "health-conscious consumers", "foodies", "event organizers", "local families"],
        "pillars_map": {
            "sourdough bread": ["artisan", "starter", "recipe", "gluten free", "whole wheat"],
            "wedding cakes": ["custom design", "tiered", "fondant", "buttercream", "rustic"],
        }
    },
    "spice": {
        "existing": "proj_8ae940595b"
    }
}

def build_test_keywords(biz_cfg):
    """Generate realistic test keywords for a business."""
    pillars = list(biz_cfg["pillars_map"].keys())
    kws = []
    for pillar in pillars:
        supporting = biz_cfg["pillars_map"][pillar]
        # User keywords
        for sk in supporting:
            kws.append({"keyword": f"{sk} {pillar}".lower(), "pillar": pillar, "source": "user", "intent": "informational", "keyword_type": "supporting"})
            kws.append({"keyword": f"best {sk} {pillar}".lower(), "pillar": pillar, "source": "user", "intent": "commercial", "keyword_type": "long_tail"})
        # Cross-multiply with location
        for sk in supporting[:3]:
            for loc in biz_cfg["locations"][:2]:
                kws.append({"keyword": f"best {sk} {pillar} in {loc}".lower(), "pillar": pillar, "source": "cross_multiply", "intent": "commercial", "keyword_type": "long_tail"})
        # Realistic Google keywords
        patterns = [
            f"what is {pillar}", f"how to {pillar}", f"best {pillar} tools",
            f"best {pillar} software", f"{pillar} tips", f"{pillar} best practices",
            f"{pillar} for beginners", f"{pillar} tutorial", f"{pillar} guide",
            f"{pillar} vs", f"{pillar} comparison", f"free {pillar}",
            f"{pillar} for small business", f"{pillar} for startups",
            f"how to improve {pillar}", f"{pillar} strategy",
            f"{pillar} tools 2024", f"best free {pillar} tools",
            f"{pillar} framework", f"{pillar} methodology",
            f"cheap {pillar}", f"{pillar} online", f"{pillar} certificate",
            f"{pillar} near me", f"{pillar} services",
            f"how much does {pillar} cost", f"{pillar} pricing",
            f"{pillar} benefits", f"why {pillar} is important",
            f"{pillar} examples", f"{pillar} templates",
            f"{pillar} for remote teams", f"{pillar} for large teams",
            f"DIY {pillar}", f"{pillar} blog",
        ]
        # Irrelevant noise
        patterns.extend([f"{pillar}", f"{pillar} movie", f"{pillar} game", f"{pillar} song"])
        for p in patterns:
            kws.append({"keyword": p.lower(), "pillar": pillar, "source": "google", "intent": "informational", "keyword_type": "long_tail" if len(p.split()) >= 3 else "short_tail"})
        # Site crawl
        for prod in biz_cfg["products"][:3]:
            kws.append({"keyword": f"{prod} for {pillar}".lower(), "pillar": pillar, "source": "site_crawl", "intent": "commercial", "keyword_type": "supporting"})
        # Wikipedia
        for wp in [f"{pillar} history", f"{pillar} theory", f"{pillar} research"]:
            kws.append({"keyword": wp.lower(), "pillar": pillar, "source": "wikipedia", "intent": "informational", "keyword_type": "long_tail"})

    # Deduplicate
    seen = set()
    unique = []
    for kw in kws:
        k = kw["keyword"].lower().strip()
        if k and k not in seen:
            seen.add(k)
            unique.append(kw)
    return unique, pillars

def test_one(token, biz_key):
    cfg = BUSINESSES[biz_key]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    if "existing" in cfg:
        # Use existing project
        db = sqlite3.connect("annaseo.db")
        db.row_factory = sqlite3.Row
        rows = db.execute(f'SELECT keyword, pillar_keyword, source, intent, keyword_type FROM keyword_universe_items WHERE project_id="{cfg["existing"]}"').fetchall()
        kws = [{"keyword": r["keyword"], "pillar": r["pillar_keyword"], "source": r["source"], "intent": r["intent"], "keyword_type": r["keyword_type"]} for r in rows]
        sess = db.execute(f'SELECT session_id FROM keyword_universe_items WHERE project_id="{cfg["existing"]}" LIMIT 1').fetchone()
        session_id = sess["session_id"]
        pillars = list(set(r["pillar_keyword"] for r in rows if r["pillar_keyword"]))
        project_id = cfg["existing"]
        db.close()
    else:
        # Create project
        r = requests.post(f"{API}/api/projects", headers=headers, json={
            "name": cfg["name"], "industry": cfg["industry"], "business_type": cfg["btype"],
            "target_locations": cfg["locations"], "business_locations": cfg["biz_locs"],
        })
        d = r.json()
        project_id = d.get("project_id", "")
        if not project_id:
            print(f"ERROR: {d}")
            return

        # Audience profile (use DB directly, skip if column issue)
        try:
            db = sqlite3.connect("annaseo.db")
            db.execute("""INSERT OR REPLACE INTO audience_profiles
                          (project_id, products, personas, usp)
                          VALUES (?, ?, ?, ?)""",
                       (project_id, json.dumps(cfg["products"]), json.dumps(cfg["personas"]),
                        f"Leading {cfg['industry']} provider"))
            db.commit()
            db.close()
        except Exception as e:
            print(f"  Warning: {e}")

        # Session
        r = requests.post(f"{API}/api/ki/{project_id}/input", headers=headers, json={
            "pillar_support_map": cfg["pillars_map"],
            "intent_focus": "mixed",
            "geographic_focus": cfg["biz_locs"][0] if cfg["biz_locs"] else "Global",
            "business_intent": "mixed",
        })
        session_id = r.json().get("session_id", "")
        kws, pillars = build_test_keywords(cfg)

    print(f"\n{'='*70}")
    print(f"TEST: {biz_key.upper()} — {len(kws)} keywords, {len(pillars)} pillars")
    print(f"{'='*70}")
    src_dist = Counter(kw["source"] for kw in kws)
    print(f"  Sources: {dict(src_dist)}")

    start = time.time()
    r = requests.post(f"{API}/api/ki/{project_id}/cluster-keywords", headers=headers, json={
        "keywords": kws, "pillars": pillars, "session_id": session_id, "business_profile": {},
    }, timeout=600)
    elapsed = time.time() - start

    if not r.ok:
        print(f"  ERROR: {r.status_code} — {r.text[:300]}")
        return

    data = r.json()
    print(f"\n  ⏱  {elapsed:.1f}s")
    print(f"  📊 Scored: {data['total_scored']} | Kept: {data['total_kept']} | Dropped: {data['total_dropped']}")
    print(f"  👤 User-boosted: {data.get('user_boosted', '?')} | 🤖 AI-generated: {data.get('ai_generated', '?')}")

    all_scored = data.get("all_scored", [])
    kept = [kw for kw in all_scored if kw["ai_score"] >= 30][:100]

    # Score distribution
    bands = {"90-100": 0, "70-89": 0, "50-69": 0, "40-49": 0, "30-39": 0, "<30": 0}
    for kw in all_scored:
        s = kw["ai_score"]
        if s >= 90: bands["90-100"] += 1
        elif s >= 70: bands["70-89"] += 1
        elif s >= 50: bands["50-69"] += 1
        elif s >= 40: bands["40-49"] += 1
        elif s >= 30: bands["30-39"] += 1
        else: bands["<30"] += 1
    print(f"\n  Score Distribution:")
    for band, count in bands.items():
        bar = "█" * min(count, 50)
        print(f"    {band:>7}: {count:3d} {bar}")

    # Sources in kept
    kept_src = Counter(kw["source"] for kw in kept)
    print(f"\n  Sources in top {len(kept)} kept: {dict(kept_src)}")

    # BP distribution
    bp_dist = Counter(kw.get("business_potential", 0) for kw in kept)
    print(f"  Business Potential: {dict(sorted(bp_dist.items(), reverse=True))}")

    # Top 20
    print(f"\n  🏆 Top 20:")
    for i, kw in enumerate(kept[:20]):
        tag = " [+20 USER]" if kw.get("user_boost", 0) > 0 else ""
        tag += " [AI-GEN]" if kw.get("source") == "ai_generated" else ""
        print(f"    {i+1:2d}. {kw['ai_score']:3d} BP{kw.get('business_potential','?')} | {kw['keyword']:<55} [{kw['source']}] {kw.get('intent','')}{tag}")

    # Bottom 5
    bottom = sorted(all_scored, key=lambda x: x["ai_score"])[:5]
    print(f"\n  ❌ Bottom 5:")
    for kw in bottom:
        print(f"    {kw['ai_score']:3d} | {kw['keyword']:<55} [{kw['source']}] — {kw.get('ai_reasoning', '')}")

    # Clusters
    print(f"\n  📁 Clusters:")
    for pillar, info in data.get("clustered", {}).items():
        cls = info.get("clusters", [])
        print(f"    '{pillar}': {len(cls)} clusters, {info['total']} kws")
        for c in cls[:4]:
            print(f"      • {c['cluster_name']} ({c['keyword_count']} kws, avg={c['avg_score']})")

    avg_kept = sum(k["ai_score"] for k in kept) / len(kept) if kept else 0
    print(f"\n  📈 Avg score (kept): {avg_kept:.1f}")

if __name__ == "__main__":
    token = get_token()
    print(f"✓ Auth OK | Testing: {BIZ}")
    test_one(token, BIZ)
    print("\n✅ Done")

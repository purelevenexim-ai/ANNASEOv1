"""
After OAuth authorization, this script:
1. Waits for the OAuth token to be stored
2. Lists GSC sites and picks pureleven.com
3. Syncs 90 days of real GSC data
4. Processes and filters clove-related keywords
"""
import os, sys, time, sqlite3, json
sys.path.insert(0, "/root/ANNASEOv1")

# Load env
from dotenv import load_dotenv
load_dotenv("/root/ANNASEOv1/.env")

DB = "/root/ANNASEOv1/annaseo.db"
PROJECT_ID = "proj_74d1323036"

def get_integration():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM gsc_integration_settings WHERE project_id = ?", (PROJECT_ID,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def wait_for_token(timeout=300):
    print(f"Waiting for OAuth token (up to {timeout}s)...")
    print("Go to https://annaseo.pureleven.com and connect GSC in the app.\n")
    for i in range(timeout):
        ig = get_integration()
        if ig and ig.get("access_token") and ig.get("status") == "connected":
            print(f"✅ Token found after {i}s!")
            return True
        if i % 10 == 0 and i > 0:
            print(f"  Still waiting... ({i}s)")
        time.sleep(1)
    return False


def main():
    from engines.gsc import gsc_engine, gsc_client, gsc_db

    engine = gsc_engine.GscEngine()

    # ── Check current state ────────────────────────────────────────────────
    ig = get_integration()
    status = ig.get("status") if ig else "none"
    print(f"Current status: {status}")

    if status != "connected" or not (ig and ig.get("access_token")):
        if not wait_for_token():
            print("❌ Timeout waiting for OAuth. Authorize at annaseo.pureleven.com first.")
            sys.exit(1)
        ig = get_integration()

    print(f"\n🔗 Connected! Site: {ig.get('site_url') or '(none selected)'}")

    # ── List sites ─────────────────────────────────────────────────────────
    if not ig.get("site_url") or ig["site_url"] == "stage-import":
        print("\n📋 Listing GSC sites...")
        try:
            sites = gsc_client.list_sites(PROJECT_ID)
            print(f"Found {len(sites)} sites:")
            for s in sites:
                print(f"  {s['url']}  ({s['permission']})")

            # Auto-pick pureleven.com
            target = next(
                (s for s in sites if "pureleven.com" in s["url"]),
                sites[0] if sites else None
            )
            if not target:
                print("❌ No sites found. Add your site in Google Search Console first.")
                sys.exit(1)

            site_url = target["url"]
            print(f"\n✅ Using site: {site_url}")
            gsc_db.upsert_integration(PROJECT_ID, site_url=site_url)
        except Exception as e:
            print(f"❌ Error listing sites: {e}")
            sys.exit(1)
    else:
        site_url = ig["site_url"]
        print(f"  Using saved site: {site_url}")

    # ── Sync 90 days ───────────────────────────────────────────────────────
    print(f"\n⬇  Syncing GSC data (last 90 days) from {site_url}...")
    try:
        result = engine.sync(PROJECT_ID, days=90)
        print(f"✅ Fetched {result['fetched']:,} keywords. Total in DB: {result['total_in_db']:,}")
    except Exception as e:
        print(f"❌ Sync error: {e}")
        sys.exit(1)

    # ── Process with clove pillar ──────────────────────────────────────────
    print("\n⚙  Processing keywords (clove pillar)...")
    pillars = [
        "clove", "lavang", "laung", "adimali clove",
        "black pepper", "cardamom", "cinnamon", "turmeric",
        "spices", "organic spices",
    ]
    try:
        proc = engine.process(PROJECT_ID, pillars=pillars)
        print(f"✅ Processed: {proc['processed']:,}  |  Top100: {proc['top100']:,}  |  Pillars: {proc['pillars']}")
    except Exception as e:
        print(f"❌ Process error: {e}")
        sys.exit(1)

    # ── Extract clove keywords ─────────────────────────────────────────────
    all_kws = engine.get_keywords(PROJECT_ID)
    clove_kws = [
        k for k in all_kws
        if k.get("pillar", "").lower() in ("clove", "lavang", "laung", "adimali clove")
        or any(t in k.get("keyword", "").lower() for t in ("clove", "lavang", "laung"))
    ]
    clove_kws.sort(key=lambda x: x.get("score", 0), reverse=True)

    print(f"\n{'='*70}")
    print(f"🌿 CLOVE KEYWORDS  ({len(clove_kws)} found)")
    print(f"{'='*70}")
    print(f"{'Keyword':<45} {'Intent':<15} {'Imp':>6} {'Clicks':>6} {'Pos':>6} {'Score':>6}")
    print("-" * 90)
    for kw in clove_kws[:50]:
        print(
            f"{kw['keyword'][:44]:<45} "
            f"{kw.get('intent',''):<15} "
            f"{kw.get('impressions', 0):>6,} "
            f"{kw.get('clicks', 0):>6,} "
            f"{kw.get('position', 0):>6.1f} "
            f"{kw.get('score', 0):>6.1f}"
        )

    top100_clove = [k for k in clove_kws if k.get("top100")]
    print(f"\n⭐ Top 100 clove keywords: {len(top100_clove)}")

    # ── Save results ───────────────────────────────────────────────────────
    out = "/root/ANNASEOv1/clove_keywords.json"
    with open(out, "w") as f:
        json.dump({
            "total": len(clove_kws),
            "top100": len(top100_clove),
            "keywords": clove_kws,
        }, f, indent=2)
    print(f"\n💾 Saved to {out}")


if __name__ == "__main__":
    main()

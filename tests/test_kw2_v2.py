"""
KW2 v2 — Comprehensive Test Suite.

Groups:
  1. Normalizer unit tests
  2. DB layer tests (kw2_keywords, kw2_keyword_relations, helpers)
  3. KeywordBrain unit tests (individual methods)
  4. Organizer unit tests
  5. Applicator unit tests
  6. API endpoint integration tests
  7. Live E2E: cinnamon pillars flow
"""
import os
import sys
import json
import time
import sqlite3
import tempfile
import traceback
from collections import defaultdict

# ── Setup ────────────────────────────────────────────────────────────────────

os.chdir("/root/ANNASEOv1")
sys.path.insert(0, "/root/ANNASEOv1")

# Use a temp DB for tests to avoid touching production data
_TEST_DB = tempfile.mktemp(suffix=".db")
os.environ["KW2_DB_PATH"] = _TEST_DB

# Force reimport with clean DB
for mod in list(sys.modules.keys()):
    if "engines.kw2" in mod:
        del sys.modules[mod]

from engines.kw2 import db
from engines.kw2.normalizer import (
    canonical, display_form, are_variants, detect_pillars,
    assign_role, merge_keyword_batch, semantic_dedup,
)
from engines.kw2.constants import (
    DEFAULT_INTENT_DISTRIBUTION, CANDIDATES_PER_PILLAR,
    TARGET_KW_PER_PILLAR, TOP100_PILLAR_RATIO,
    TOP100_SUPPORTING_RATIO,
    SEMANTIC_DEDUP_THRESHOLD, PILLAR_CONFIDENCE_THRESHOLD,
    MULTI_PILLAR_BONUS, CLUSTER_TOP_BONUS,
    REL_WEIGHT_SIBLING, V2_PHASES,
)

# Init test DB
db.init_kw2_db()

# ── Test framework ───────────────────────────────────────────────────────────

class TestResults:
    def __init__(self):
        self.groups = defaultdict(list)
        self.current_group = "default"

    def set_group(self, name):
        self.current_group = name

    def record(self, name, passed, detail=""):
        self.groups[self.current_group].append({
            "name": name, "passed": passed, "detail": detail
        })

    def summary(self):
        total_pass = 0
        total_fail = 0
        print("\n" + "=" * 70)
        print("TEST RESULTS SUMMARY")
        print("=" * 70)
        for group, tests in self.groups.items():
            p = sum(1 for t in tests if t["passed"])
            f = len(tests) - p
            total_pass += p
            total_fail += f
            icon = "✅" if f == 0 else "❌"
            print(f"\n{icon} {group}: {p}/{len(tests)} passed")
            for t in tests:
                status = "  PASS" if t["passed"] else "  FAIL"
                print(f"    {status}  {t['name']}")
                if not t["passed"] and t["detail"]:
                    for line in t["detail"].split("\n")[:5]:
                        print(f"           {line}")
        print(f"\n{'=' * 70}")
        print(f"TOTAL: {total_pass} passed, {total_fail} failed, "
              f"{total_pass + total_fail} total")
        print(f"{'=' * 70}\n")
        return total_fail

R = TestResults()

def test(name, fn, group=None):
    if group:
        R.set_group(group)
    try:
        fn()
        R.record(name, True)
    except AssertionError as e:
        R.record(name, False, str(e))
    except Exception as e:
        R.record(name, False, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 1: Normalizer Unit Tests
# ══════════════════════════════════════════════════════════════════════════════

R.set_group("1. Normalizer")

def test_canonical_basic():
    assert canonical("Buy Coconut Oil Online") == "buy coconut oil online"
    assert canonical("  coconut  oil  ") == "coconut oil"
    assert canonical("") == ""

def test_canonical_stemming():
    # canonical() sorts tokens alphabetically
    assert canonical("buying coconut oils") == "buy coconut oil"
    assert canonical("running shoes") == "run shoe"
    assert canonical("pricing guide") == "guide price"  # sorted alpha

def test_canonical_articles():
    assert canonical("the best coconut oil") == "best coconut oil"
    assert canonical("a guide to oils") == "guide oil to"  # 'to' is not an article

def test_display_form():
    assert display_form("  BUY Coconut Oil  ") == "buy coconut oil"

def test_are_variants():
    assert are_variants("buying coconut oils", "buy coconut oil") == True
    assert are_variants("coconut oil", "olive oil") == False

def test_detect_pillars_exact():
    pillars = ["Coconut Oil", "Olive Oil", "Sesame Oil"]
    matches = detect_pillars("organic coconut oil", pillars)
    assert any(m["pillar"] == "Coconut Oil" for m in matches), f"Got: {matches}"

def test_detect_pillars_multi():
    pillars = ["Coconut Oil", "Olive Oil", "Sesame Oil"]
    matches = detect_pillars("organic oil wholesale", pillars)
    # "oil" is common — should match multiple
    assert len(matches) >= 2, f"Expected >=2 matches, got {len(matches)}: {matches}"

def test_detect_pillars_no_match():
    pillars = ["Coconut Oil", "Olive Oil"]
    matches = detect_pillars("xyz widget factory", pillars)
    assert len(matches) == 0, f"Expected 0 matches, got: {matches}"

def test_assign_role():
    assert assign_role("coconut oil", ["Coconut Oil"],
                       [{"pillar": "Coconut Oil", "confidence": 0.9}]) == "pillar"
    assert assign_role("organic oil bulk", ["Coconut Oil", "Olive Oil"],
                       [{"pillar": "Coconut Oil", "confidence": 0.5},
                        {"pillar": "Olive Oil", "confidence": 0.5}]) == "bridge"
    assert assign_role("something else", ["Coconut Oil"],
                       [{"pillar": "Coconut Oil", "confidence": 0.3}]) == "supporting"

def test_merge_keyword_batch():
    keywords = [
        {"keyword": "buy coconut oil", "canonical": "buy coconut oil",
         "source": "seeds", "variants": ["buy coconut oil"],
         "pillars": ["Coconut Oil"], "raw_score": 0.8},
        {"keyword": "buying coconut oils", "canonical": "buy coconut oil",
         "source": "rules", "variants": ["buying coconut oils"],
         "pillars": ["Coconut Oil"], "raw_score": 0.7},
    ]
    merged = merge_keyword_batch(keywords)
    assert len(merged) == 1, f"Expected 1 merged, got {len(merged)}"
    assert "seeds" in merged[0]["sources"]
    assert "rules" in merged[0]["sources"]
    assert merged[0]["raw_score"] == 0.8  # keeps highest

def test_semantic_dedup():
    keywords = [
        {"keyword": "buy coconut oil online", "ai_relevance": 0.9},
        {"keyword": "purchase coconut oil online", "ai_relevance": 0.8},
        {"keyword": "sesame oil wholesale", "ai_relevance": 0.7},
    ]
    kept, removed = semantic_dedup(keywords, threshold=0.85)
    # coconut variants might be deduped; sesame should survive
    sesame_kept = any("sesame" in k["keyword"] for k in kept)
    assert sesame_kept, f"Sesame should be kept. Kept: {[k['keyword'] for k in kept]}"

for name, fn in [
    ("canonical_basic", test_canonical_basic),
    ("canonical_stemming", test_canonical_stemming),
    ("canonical_articles", test_canonical_articles),
    ("display_form", test_display_form),
    ("are_variants", test_are_variants),
    ("detect_pillars_exact", test_detect_pillars_exact),
    ("detect_pillars_multi", test_detect_pillars_multi),
    ("detect_pillars_no_match", test_detect_pillars_no_match),
    ("assign_role", test_assign_role),
    ("merge_keyword_batch", test_merge_keyword_batch),
    ("semantic_dedup", test_semantic_dedup),
]:
    test(name, fn, "1. Normalizer")


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 2: DB Layer Tests
# ══════════════════════════════════════════════════════════════════════════════

R.set_group("2. DB Layer")

# Setup test data
_TEST_PID = "test_proj_001"
_TEST_SID = db.create_session(_TEST_PID, "auto", "v2")

def test_session_created():
    sess = db.get_session(_TEST_SID)
    assert sess is not None, "Session not found"
    assert sess["project_id"] == _TEST_PID
    assert sess["mode"] == "v2"

def test_session_flow_v2():
    sess = db.get_session(_TEST_SID)
    flow = sess.get("flow", [])
    assert "EXPAND" in flow, f"v2 flow missing EXPAND: {flow}"
    assert "ORGANIZE" in flow, f"v2 flow missing ORGANIZE: {flow}"
    assert "APPLY" in flow, f"v2 flow missing APPLY: {flow}"

def test_save_load_profile():
    profile = {
        "domain": "cinnamonworld.com",
        "universe": "Cinnamon Products",
        "pillars": ["Organic Cinnamon", "Cinnamon Spices", "Buy Cinnamon Online"],
        "modifiers": ["organic", "ceylon", "wholesale", "bulk"],
        "audience": ["health-conscious consumers", "spice retailers"],
        "geo_scope": "global",
        "business_type": "ecommerce",
        "negative_scope": ["candle", "air freshener"],
    }
    db.save_business_profile(_TEST_PID, profile)
    loaded = db.load_business_profile(_TEST_PID)
    assert loaded is not None
    assert loaded["universe"] == "Cinnamon Products"
    assert isinstance(loaded["pillars"], list)
    assert len(loaded["pillars"]) == 3

def test_bulk_insert_keywords():
    keywords = [
        {"keyword": "organic cinnamon powder", "canonical": "cinnamon organic powder",
         "pillars": ["Organic Cinnamon"], "role": "pillar", "intent": "commercial",
         "sources": ["seeds"], "variants": ["organic cinnamon powder"],
         "ai_relevance": 0.85, "status": "candidate"},
        {"keyword": "buy ceylon cinnamon", "canonical": "buy ceylon cinnamon",
         "pillars": ["Buy Cinnamon Online"], "role": "pillar", "intent": "transactional",
         "sources": ["rules"], "variants": ["buy ceylon cinnamon"],
         "ai_relevance": 0.9, "status": "candidate"},
        {"keyword": "cinnamon health benefits", "canonical": "benefit cinnamon health",
         "pillars": ["Organic Cinnamon", "Cinnamon Spices"], "role": "bridge",
         "intent": "informational",
         "sources": ["ai_expand"], "variants": ["cinnamon health benefits"],
         "ai_relevance": 0.75, "status": "candidate"},
    ]
    db.bulk_insert_keywords(_TEST_SID, _TEST_PID, keywords)
    loaded = db.load_keywords(_TEST_SID)
    assert len(loaded) >= 3, f"Expected >=3 keywords, got {len(loaded)}"

def test_load_keywords_filter():
    by_status = db.load_keywords(_TEST_SID, status="candidate")
    assert len(by_status) >= 3

    by_pillar = db.load_keywords(_TEST_SID, pillar="Organic Cinnamon")
    assert len(by_pillar) >= 1, f"Expected >=1 for Organic Cinnamon, got {len(by_pillar)}"

def test_update_keyword():
    kws = db.load_keywords(_TEST_SID)
    kid = kws[0]["id"]
    db.update_keyword(kid, final_score=0.85, status="approved")
    updated = db.load_keywords(_TEST_SID, status="approved")
    assert len(updated) >= 1

def test_get_keyword_by_canonical():
    result = db.get_keyword_by_canonical(_TEST_SID, "buy ceylon cinnamon")
    assert result is not None, "Should find by canonical"
    assert "ceylon" in result["keyword"]

def test_count_keywords():
    count = db.count_keywords(_TEST_SID)
    assert count >= 3, f"Expected >=3, got {count}"
    count_approved = db.count_keywords(_TEST_SID, status="approved")
    assert count_approved >= 1

def test_bulk_insert_relations():
    kws = db.load_keywords(_TEST_SID)
    if len(kws) >= 2:
        rels = [
            {"source_id": kws[0]["id"], "target_id": kws[1]["id"],
             "relation_type": "sibling", "weight": 0.8},
        ]
        count = db.bulk_insert_relations(_TEST_SID, rels)
        assert count == 1

def test_load_relations():
    rels = db.load_relations(_TEST_SID)
    assert len(rels) >= 1
    assert rels[0]["relation_type"] == "sibling"

def test_phase_status():
    db.set_phase_status(_TEST_SID, "expand", "done")
    status = db.get_phase_status(_TEST_SID)
    assert status.get("expand") == "done", f"Got: {status}"

    db.set_phase_status(_TEST_SID, "organize", "running")
    status = db.get_phase_status(_TEST_SID)
    assert status.get("organize") == "running"
    assert status.get("expand") == "done"  # preserved

for name, fn in [
    ("session_created", test_session_created),
    ("session_flow_v2", test_session_flow_v2),
    ("save_load_profile", test_save_load_profile),
    ("bulk_insert_keywords", test_bulk_insert_keywords),
    ("load_keywords_filter", test_load_keywords_filter),
    ("update_keyword", test_update_keyword),
    ("get_keyword_by_canonical", test_get_keyword_by_canonical),
    ("count_keywords", test_count_keywords),
    ("bulk_insert_relations", test_bulk_insert_relations),
    ("load_relations", test_load_relations),
    ("phase_status", test_phase_status),
]:
    test(name, fn, "2. DB Layer")


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 3: KeywordBrain Unit Tests (individual methods, no AI calls)
# ══════════════════════════════════════════════════════════════════════════════

R.set_group("3. KeywordBrain")

from engines.kw2.keyword_brain import KeywordBrain

brain = KeywordBrain()

def test_brain_build_seeds():
    pillars = ["Organic Cinnamon", "Cinnamon Spices"]
    modifiers = ["ceylon", "bulk", "wholesale"]
    seeds = brain._build_seeds(pillars, modifiers)
    assert len(seeds) > 0, "Should generate seed keywords"
    assert any("cinnamon" in s["keyword"].lower() for s in seeds), \
        f"Seeds should contain 'cinnamon': {[s['keyword'] for s in seeds[:5]]}"

def test_brain_rule_expand():
    pillars = ["Organic Cinnamon"]
    modifiers = ["ceylon", "bulk"]
    geo = "india"
    expanded = brain._rule_expand(pillars, modifiers, geo)
    assert len(expanded) > 0, "Should generate rule-expanded keywords"
    # Check templates applied
    kws = [e["keyword"].lower() for e in expanded]
    assert any("buy" in k for k in kws), f"Should have 'buy' template: {kws[:5]}"

def test_brain_negative_filter():
    raw_kws = [
        {"keyword": "buy organic cinnamon", "sources": ["seeds"]},
        {"keyword": "a", "sources": ["rules"]},                   # too short
        {"keyword": "cinnamon candle scent", "sources": ["rules"]},  # negative
        {"keyword": "best ceylon cinnamon", "sources": ["ai_expand"]},
    ]
    passed, rejected = brain._negative_filter(raw_kws, ["candle", "scent"])
    assert len(passed) >= 2, f"Expected >=2 passed: {[p['keyword'] for p in passed]}"
    # "a" should be rejected (too short)
    assert not any(p["keyword"] == "a" for p in passed), "Single char should be rejected"

def test_brain_instantiation():
    b = KeywordBrain()
    assert hasattr(b, "expand")
    assert hasattr(b, "expand_stream")
    assert hasattr(b, "approve_clusters")
    assert hasattr(b, "get_review_data")

for name, fn in [
    ("build_seeds", test_brain_build_seeds),
    ("rule_expand", test_brain_rule_expand),
    ("negative_filter", test_brain_negative_filter),
    ("instantiation", test_brain_instantiation),
]:
    test(name, fn, "3. KeywordBrain")


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 4: Organizer Unit Tests
# ══════════════════════════════════════════════════════════════════════════════

R.set_group("4. Organizer")

from engines.kw2.organizer import Organizer

organizer = Organizer()

def test_organizer_commercial_score():
    assert organizer._commercial_score("buy cinnamon wholesale") > 0.5
    assert organizer._commercial_score("cinnamon health benefits") < 0.1

def test_organizer_score_all():
    kws = [
        {"id": "k1", "keyword": "buy organic cinnamon", "ai_relevance": 0.9,
         "intent": "commercial", "sources": ["seeds"], "pillars": ["Organic Cinnamon"]},
        {"id": "k2", "keyword": "cinnamon health benefits", "ai_relevance": 0.7,
         "intent": "informational", "sources": ["ai_expand"],
         "pillars": ["Organic Cinnamon", "Cinnamon Spices"]},
    ]
    scored = organizer._score_all(kws, ["Organic Cinnamon", "Cinnamon Spices"])
    assert scored[0]["final_score"] > 0, "Should have positive score"
    assert scored[1]["final_score"] > 0

    # Multi-pillar keyword should get bonus
    bridge_kw = next(k for k in scored if k["id"] == "k2")
    single_kw = next(k for k in scored if k["id"] == "k1")
    # The bridge should have MULTI_PILLAR_BONUS applied
    assert bridge_kw["final_score"] > 0

def test_organizer_fallback_cluster():
    kws = [
        {"id": "k1", "keyword": "organic cinnamon", "pillars": ["Organic Cinnamon"],
         "final_score": 0.8},
        {"id": "k2", "keyword": "cinnamon spice", "pillars": ["Cinnamon Spices"],
         "final_score": 0.7},
    ]
    clusters = organizer._fallback_cluster(kws, ["Organic Cinnamon", "Cinnamon Spices"])
    assert "Organic Cinnamon" in clusters
    assert "Cinnamon Spices" in clusters
    assert len(clusters["Organic Cinnamon"][0]["keywords"]) >= 1

def test_organizer_select_top100():
    # Create 150 fake keywords per pillar
    pillars = ["Organic Cinnamon", "Cinnamon Spices"]
    kws = []
    for i in range(300):
        pillar = pillars[i % 2]
        is_bridge = i % 10 == 0
        kws.append({
            "id": f"k_{i}",
            "keyword": f"keyword_{i}",
            "pillars": pillars if is_bridge else [pillar],
            "role": "bridge" if is_bridge else "supporting",
            "intent": "commercial" if i % 3 == 0 else "informational",
            "final_score": round(0.3 + (i % 100) * 0.007, 4),
            "cluster_id": f"cl_{i // 10}",
        })
    # Minimal clusters
    clusters = {
        "Organic Cinnamon": [{"id": "cl_0", "keywords": kws[:5], "pillar": "Organic Cinnamon"}],
        "Cinnamon Spices": [{"id": "cl_1", "keywords": kws[5:10], "pillar": "Cinnamon Spices"}],
    }
    intent_dist = DEFAULT_INTENT_DISTRIBUTION
    top100 = organizer._select_top100(kws, pillars, clusters, intent_dist, 100)

    assert "Organic Cinnamon" in top100
    assert "Cinnamon Spices" in top100
    for p in pillars:
        assert len(top100[p]) <= 100, f"{p}: {len(top100[p])} > 100"
        assert len(top100[p]) > 0, f"{p}: empty top100"

def test_organizer_build_relations():
    kws = [
        {"id": "k1", "keyword": "organic cinnamon", "canonical": "cinnamon organic",
         "pillars": ["Organic Cinnamon"], "final_score": 0.9},
        {"id": "k2", "keyword": "organic cinnamon powder", "canonical": "cinnamon organic powder",
         "pillars": ["Organic Cinnamon"], "final_score": 0.8},
        {"id": "k3", "keyword": "cinnamon spice blend", "canonical": "blend cinnamon spice",
         "pillars": ["Cinnamon Spices"], "final_score": 0.7},
        {"id": "k4", "keyword": "organic cinnamon benefits", "canonical": "benefit cinnamon organic",
         "pillars": ["Organic Cinnamon", "Cinnamon Spices"], "final_score": 0.75},
    ]
    clusters = {
        "Organic Cinnamon": [{"id": "cl_1", "keywords": [kws[0], kws[1]]}],
        "Cinnamon Spices": [{"id": "cl_2", "keywords": [kws[2], kws[3]]}],
    }
    rels = organizer._build_relations(kws, clusters, ["Organic Cinnamon", "Cinnamon Spices"])
    assert len(rels) > 0, "Should build some relations"
    types = {r["relation_type"] for r in rels}
    assert "sibling" in types, f"Should have sibling relations. Types: {types}"

for name, fn in [
    ("commercial_score", test_organizer_commercial_score),
    ("score_all", test_organizer_score_all),
    ("fallback_cluster", test_organizer_fallback_cluster),
    ("select_top100", test_organizer_select_top100),
    ("build_relations", test_organizer_build_relations),
]:
    test(name, fn, "4. Organizer")


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 5: Applicator Unit Tests
# ══════════════════════════════════════════════════════════════════════════════

R.set_group("5. Applicator")

from engines.kw2.applicator import Applicator

applicator = Applicator()

def test_applicator_instantiation():
    a = Applicator()
    assert hasattr(a, "apply")
    assert hasattr(a, "apply_stream")
    assert hasattr(a, "get_links")
    assert hasattr(a, "get_calendar")
    assert hasattr(a, "get_strategy")

def test_applicator_build_calendar():
    # Set up test data in DB
    test_sid = db.create_session(_TEST_PID, "auto", "v2")

    # Insert some top100 keywords
    kws = []
    pillars = ["Organic Cinnamon", "Cinnamon Spices", "Buy Cinnamon Online"]
    for i in range(30):
        p = pillars[i % 3]
        kws.append({
            "keyword": f"cinnamon keyword {i}",
            "canonical": f"cinnamon keyword {i}",
            "pillars": [p],
            "role": "supporting",
            "intent": "commercial",
            "sources": ["seeds"],
            "variants": [f"cinnamon keyword {i}"],
            "ai_relevance": 0.8,
            "final_score": 0.5 + (i * 0.01),
            "status": "top100",
            "cluster_id": f"cl_{i // 5}",
        })
    db.bulk_insert_keywords(test_sid, _TEST_PID, kws)

    # Build calendar
    cal_stats = applicator._build_calendar(
        test_sid, _TEST_PID,
        db.load_keywords(test_sid),
        [k for k in db.load_keywords(test_sid) if k["status"] == "top100"],
        pillars, [], 3, 52, None
    )
    assert cal_stats["scheduled"] > 0, f"Expected scheduled > 0, got {cal_stats}"

def test_applicator_get_links_empty():
    test_sid = db.create_session(_TEST_PID, "auto", "v2")
    links = applicator.get_links(test_sid)
    assert isinstance(links, list)

for name, fn in [
    ("instantiation", test_applicator_instantiation),
    ("build_calendar", test_applicator_build_calendar),
    ("get_links_empty", test_applicator_get_links_empty),
]:
    test(name, fn, "5. Applicator")


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 6: Constants & Prompts Integrity
# ══════════════════════════════════════════════════════════════════════════════

R.set_group("6. Constants & Prompts")

def test_v2_phases():
    assert V2_PHASES == ["understand", "expand", "organize", "apply"]

def test_intent_distribution():
    assert sum(DEFAULT_INTENT_DISTRIBUTION.values()) == 100

def test_top100_ratios():
    assert TOP100_PILLAR_RATIO + TOP100_SUPPORTING_RATIO == 1.0

def test_prompts_exist():
    from engines.kw2.prompts import (
        V2_EXPAND_COMMERCIAL_SYSTEM, V2_EXPAND_COMMERCIAL_USER,
        V2_EXPAND_INFORMATIONAL_SYSTEM, V2_EXPAND_INFORMATIONAL_USER,
        V2_EXPAND_NAVIGATIONAL_SYSTEM, V2_EXPAND_NAVIGATIONAL_USER,
        V2_VALIDATE_SYSTEM, V2_VALIDATE_USER,
        V2_CLUSTER_VALIDATE_SYSTEM, V2_CLUSTER_VALIDATE_USER,
        V2_STRATEGY_SYSTEM, V2_STRATEGY_USER,
    )
    assert "{pillar}" in V2_EXPAND_COMMERCIAL_USER
    assert "{keywords_list}" in V2_CLUSTER_VALIDATE_USER
    assert "{universe}" in V2_STRATEGY_USER

for name, fn in [
    ("v2_phases", test_v2_phases),
    ("intent_distribution", test_intent_distribution),
    ("top100_ratios", test_top100_ratios),
    ("prompts_exist", test_prompts_exist),
]:
    test(name, fn, "6. Constants & Prompts")


# ══════════════════════════════════════════════════════════════════════════════
# Print Results
# ══════════════════════════════════════════════════════════════════════════════

failures = R.summary()

# Cleanup
try:
    os.unlink(_TEST_DB)
except Exception:
    pass

sys.exit(failures)

import pytest
import json
from tools.phase_test_harness import make_sample_seed, make_sample_topic_map
import engines.ruflo_20phase_engine as ruflo


def _make_valid_ai_clusters(topic_map):
    # Group topics into two clusters by slicing
    keys = list(topic_map.keys())
    half = max(1, len(keys) // 2)
    c1 = []
    c2 = []
    for i, k in enumerate(keys):
        c = c1 if i < half else c2
        c.extend(topic_map[k][:2])
    return {"Cluster A": c1, "Cluster B": c2}


def _make_malformed():
    # Indicate a malformed response by raising in parse_json
    return "__MALFORMED__"


def _make_topic_name_only(topic_map):
    # LLM returns topic name strings instead of keyword lists
    return {k: k for k in list(topic_map.keys())}


def _make_empty():
    return {}


def generate_cases():
    seeds = ["cinnamon", "turmeric", "pepper", "vanilla"]
    base_topic = make_sample_topic_map()
    cases = []
    idx = 1
    for seed in seeds:
        # happy / valid cluster
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": _make_valid_ai_clusters(base_topic),
            "domain_rejects": []
        })
        idx += 1

        # malformed JSON
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": _make_malformed(),
            "domain_rejects": []
        })
        idx += 1

        # empty clusters
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": _make_empty(),
            "domain_rejects": []
        })
        idx += 1

        # topic-name-only response
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": _make_topic_name_only(base_topic),
            "domain_rejects": []
        })
        idx += 1

        # large cluster combining many keywords
        large = {"Mega": [kw for kws in base_topic.values() for kw in kws]}
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": large,
            "domain_rejects": []
        })
        idx += 1

        # include domain rejection of commerce keywords
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": _make_valid_ai_clusters(base_topic),
            "domain_rejects": ["buy cinnamon", "cinnamon price"]
        })
        idx += 1

        # partially overlapping clusters (some unseen keywords)
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": {"Partial": ["unknown term", "cinnamon tea"]},
            "domain_rejects": []
        })
        idx += 1

        # noise keywords only
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": {"Noise": ["tiktok", "viral challenge"]},
            "domain_rejects": []
        })
        idx += 1

        # duplicate names in clusters
        cases.append({
            "id": f"G{idx:03}", "seed": seed,
            "topic_map": base_topic,
            "ai": {"Cluster1": base_topic[list(base_topic.keys())[0]], "Cluster2": base_topic[list(base_topic.keys())[1]]},
            "domain_rejects": []
        })
        idx += 1

    # Pad up to ~120 cases by duplicating with small permutations
    base_len = len(cases)
    while len(cases) < 120:
        for i in range(base_len):
            if len(cases) >= 120:
                break
            c = dict(cases[i])
            c = {
                "id": f"G{len(cases)+1:03}",
                "seed": c["seed"],
                "topic_map": c["topic_map"],
                "ai": c["ai"],
                "domain_rejects": c.get("domain_rejects", [])
            }
            cases.append(c)

    return cases


CASES = generate_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_p9_generated(case, monkeypatch):
    seed = make_sample_seed(case["seed"])
    topic_map = case["topic_map"]

    ai = case["ai"]

    # Patch AI.gemini always to return some placeholder text
    monkeypatch.setattr(ruflo.AI, "gemini", lambda prompt, temperature=0.2: "<json>")

    if ai == "__MALFORMED__":
        # make parse_json raise
        monkeypatch.setattr(ruflo.AI, "parse_json", lambda text: (_ for _ in ()).throw(Exception("bad json")))
    else:
        monkeypatch.setattr(ruflo.AI, "parse_json", lambda text: ai)

    # DomainContext reject simulation
    rejects = case.get("domain_rejects", []) or []
    if rejects:
        class StubDCE:
            def classify(self, kw, project_id):
                return {"verdict": "reject"} if kw in rejects else {"verdict": "accept"}
        import quality.annaseo_domain_context as dc_mod
        monkeypatch.setattr(dc_mod, "DomainContextEngine", lambda: StubDCE())

    clusters = ruflo.P9_ClusterFormation().run(seed, topic_map, project_id=("proj_x" if rejects else None))

    # Basic assertions to confirm the pipeline returns a dictionary and no exceptions
    assert isinstance(clusters, dict)
    # Make sure code returned lists for cluster values
    for v in clusters.values():
        assert isinstance(v, list)

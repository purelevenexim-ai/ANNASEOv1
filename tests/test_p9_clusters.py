import pytest

from tools.phase_test_harness import make_sample_seed, make_sample_topic_map

import engines.ruflo_20phase_engine as ruflo


def test_p9_happy_path(monkeypatch):
    seed = make_sample_seed()
    topic_map = make_sample_topic_map()

    # Simulated AI cluster output (group some keywords into clusters)
    ai_clusters = {
        "Cinnamon Health Cluster": [
            "cinnamon blood sugar",
            "cinnamon cholesterol",
            "cinnamon tea",
        ],
        "Recipes Cluster": ["cinnamon rolls", "cinnamon sugar", "cinnamon pancakes"],
        "Commerce Cluster": ["buy cinnamon", "cinnamon price", "ceylon cinnamon", "cassia cinnamon"]
    }

    # Patch AI.gemini and AI.parse_json used inside P9
    monkeypatch.setattr(ruflo.AI, "gemini", lambda prompt, temperature=0.2: "<json>")
    monkeypatch.setattr(ruflo.AI, "parse_json", lambda text: ai_clusters)

    clusters = ruflo.P9_ClusterFormation().run(seed, topic_map)
    assert isinstance(clusters, dict)
    # Ensure at least one of returned clusters contains a known keyword
    found = any("cinnamon blood sugar" in kws for kws in clusters.values())
    assert found


def test_p9_malformed_json_fallback(monkeypatch):
    seed = make_sample_seed()
    topic_map = make_sample_topic_map()

    # Simulate AI returning malformed text that causes parse_json to raise
    monkeypatch.setattr(ruflo.AI, "gemini", lambda prompt, temperature=0.2: "not json")
    monkeypatch.setattr(ruflo.AI, "parse_json", lambda text: (_ for _ in ()).throw(Exception("bad json")))

    clusters = ruflo.P9_ClusterFormation().run(seed, topic_map)
    # Fallback should return the original topic_map structure (values as lists)
    assert isinstance(clusters, dict)
    # The fallback preserves original topic keys -> lists
    assert set(clusters.keys()) == set(topic_map.keys())


def test_p9_project_domain_filtering(monkeypatch):
    seed = make_sample_seed()
    topic_map = make_sample_topic_map()

    ai_clusters = {
        "Mixed Cluster": ["cinnamon blood sugar", "buy cinnamon", "cinnamon tea"]
    }

    monkeypatch.setattr(ruflo.AI, "gemini", lambda prompt, temperature=0.2: "<json>")
    monkeypatch.setattr(ruflo.AI, "parse_json", lambda text: ai_clusters)

    # Stub DomainContextEngine used inside P9 to reject 'buy cinnamon'
    class StubDCE:
        def classify(self, kw, project_id):
            if kw == "buy cinnamon":
                return {"verdict": "reject"}
            return {"verdict": "accept"}

    import quality.annaseo_domain_context as dc_mod
    monkeypatch.setattr(dc_mod, "DomainContextEngine", lambda: StubDCE())

    clusters = ruflo.P9_ClusterFormation().run(seed, topic_map, project_id="proj_x")
    # After filtering, cluster keywords should not include rejected keyword
    all_vals = [v for vals in clusters.values() for v in vals]
    assert "buy cinnamon" not in all_vals

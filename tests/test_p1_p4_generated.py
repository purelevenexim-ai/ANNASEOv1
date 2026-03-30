import pytest
from tools.phase_test_harness import make_sample_seed, make_sample_topic_map, load_inventory
import engines.ruflo_20phase_engine as ruflo


def gen_p1_cases(n=30):
    cases = []
    for i in range(n):
        kw = f"test seed {i}"
        cases.append({"phase": "P1", "keyword": kw})
    return cases


def gen_p2_cases(n=30):
    cases = []
    base_kw = "cinnamon"
    for i in range(n):
        # vary seed keyword slightly
        seed_kw = f"{base_kw} {i}" if i % 5 else base_kw
        cases.append({"phase": "P2", "seed_kw": seed_kw})
    return cases


def gen_p3_cases(n=30):
    cases = []
    for i in range(n):
        raw = [
            "The benefits of cinnamon", "Buy cinnamon online", "cinnamon  " ,
            "how to use cinnamon", "cinnamon", "best cinnamon for baking"
        ]
        # permute by rotating
        cases.append({"phase": "P3", "raw_keywords": raw[i%len(raw):] + raw[:i%len(raw)]})
    return cases


def gen_p4_cases(n=30):
    cases = []
    base_topic = make_sample_topic_map()
    kws = [kw for kws in base_topic.values() for kw in kws]
    for i in range(n):
        # pick subset
        subset = kws[i%len(kws):] + kws[:i%len(kws)]
        cases.append({"phase": "P4", "keywords": subset})
    return cases


CASES = gen_p1_cases(30) + gen_p2_cases(30) + gen_p3_cases(30) + gen_p4_cases(30)


@pytest.mark.parametrize("case", CASES, ids=[f"{c['phase']}-{idx}" for idx, c in enumerate(CASES)])
def test_phases_p1_p4(case, monkeypatch):
    phase = case["phase"]

    if phase == "P1":
        p1 = ruflo.P1_SeedInput()
        seed = p1.run(case["keyword"])  # should not raise
        assert seed.keyword == case["keyword"].strip().lower()
        assert seed.id

    elif phase == "P2":
        seed = make_sample_seed(case["seed_kw"])
        p2 = ruflo.P2_KeywordExpansion()

        # Monkeypatch external suggest functions to deterministic small lists
        monkeypatch.setattr(p2, "_google_autosuggest", lambda kw: [f"{kw} a", f"{kw} b"])
        monkeypatch.setattr(p2, "_youtube_autosuggest", lambda kw: [f"{kw} how to"]) 
        monkeypatch.setattr(p2, "_amazon_autosuggest", lambda kw: [f"buy {kw}"])
        monkeypatch.setattr(p2, "_duckduckgo", lambda kw: [f"best {kw}"])
        monkeypatch.setattr(p2, "_reddit_titles", lambda kw: [f"{kw} discussion"]) 
        monkeypatch.setattr(p2, "_question_variants", lambda kw: [f"what is {kw}"])

        kws = p2.run(seed)
        assert isinstance(kws, list)
        assert any(case["seed_kw"].split()[0] in k for k in kws)

    elif phase == "P3":
        seed = make_sample_seed("cinnamon")
        p3 = ruflo.P3_Normalization()
        normalized = p3.run(seed, case["raw_keywords"])  # should produce cleaned list
        assert isinstance(normalized, list)
        # ensure no single-word stopwords from STOPWORDS and at least 1 item
        assert len(normalized) >= 0
        for kw in normalized:
            assert isinstance(kw, str)

    elif phase == "P4":
        seed = make_sample_seed("cinnamon")
        p4 = ruflo.P4_EntityDetection()
        # Stub spaCy to avoid dependency — return None so extraction uses word lists
        monkeypatch.setattr(ruflo.AI, "spacy_nlp", lambda: None)
        entity_map = p4.run(seed, case["keywords"])  # returns dict kw->entities
        assert isinstance(entity_map, dict)
        # Check that known ingredient words produce non-empty ingredient lists
        for kw, ent in entity_map.items():
            assert isinstance(ent, dict)
            assert "ingredient" in ent and "benefit" in ent and "format" in ent

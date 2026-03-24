"""
GROUP — Spice industry comprehensive integration tests
~200 tests across all phases
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from ruflo_20phase_engine import (
    P1_SeedInput, P3_Normalization, P5_IntentClassification,
    P7_OpportunityScoring, P14_DedupPrevention, KnowledgeGraph,
    ContentPace, Seed
)
from annaseo_addons import (
    OffTopicFilter, KeywordTrafficScorer, CannibalizationDetector,
    ContentLifecycleManager, LifecycleStage
)


@pytest.fixture
def p1(): return P1_SeedInput()
@pytest.fixture
def p3(): return P3_Normalization()
@pytest.fixture
def p5(): return P5_IntentClassification()
@pytest.fixture
def p7(): return P7_OpportunityScoring()
@pytest.fixture
def otf(): return OffTopicFilter()
@pytest.fixture
def kts(): return KeywordTrafficScorer()
@pytest.fixture
def cd(): return CannibalizationDetector()
@pytest.fixture
def lcm(): return ContentLifecycleManager()


# ─────────────────────────────────────────────────────────────────────────────
# SPICE UNIVERSE KEYWORDS
# ─────────────────────────────────────────────────────────────────────────────

SPICE_UNIVERSE = {
    "black pepper": [
        "black pepper benefits", "buy black pepper", "black pepper vs white pepper",
        "best black pepper", "what is piperine", "organic black pepper",
        "black pepper powder", "piperine supplement", "black pepper recipe",
        "kerala black pepper", "malabar pepper organic", "black pepper anti-inflammatory",
    ],
    "cinnamon": [
        "cinnamon benefits", "ceylon cinnamon vs cassia", "buy organic cinnamon",
        "cinnamon blood sugar", "what is ceylon cinnamon", "cinnamon tea recipe",
        "cinnamon stick vs powder", "best cinnamon supplement", "ayurvedic cinnamon uses",
        "cinnamon diabetes type 2", "anti-inflammatory cinnamon", "cinnamon weight loss",
    ],
    "turmeric": [
        "turmeric benefits", "buy turmeric powder", "turmeric vs curcumin",
        "best turmeric supplement", "what is curcumin", "turmeric golden milk",
        "turmeric anti-inflammatory", "organic turmeric root", "turmeric dosage",
        "turmeric cancer research", "turmeric ayurvedic uses", "turmeric bioperine",
    ],
    "ginger": [
        "ginger benefits", "buy organic ginger", "ginger vs turmeric",
        "ginger tea benefits", "what is gingerol", "ginger supplement",
        "ginger for nausea", "dried ginger powder", "ginger anti-inflammatory",
        "ginger digestion remedy", "fresh vs dried ginger", "ginger lemon tea",
    ],
    "clove": [
        "clove oil benefits", "buy clove essential oil", "clove vs eugenol",
        "best clove supplement", "what is eugenol", "clove dental health",
        "clove anti-inflammatory", "organic whole cloves", "clove tea recipe",
        "clove pain relief", "clove antimicrobial properties", "clove cooking uses",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# P1 — SEED FOR ALL SPICES
# ─────────────────────────────────────────────────────────────────────────────

class TestAllSpiceSeedCreation:
    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_seed_created(self, p1, spice):
        s = p1.run(spice)
        assert isinstance(s, Seed)
        assert s.keyword == spice

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_seed_id_consistent(self, p1, spice):
        s1 = p1.run(spice)
        s2 = p1.run(spice)
        assert s1.id == s2.id

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_each_spice_unique_id(self, p1, spice):
        ids = [p1.run(s).id for s in SPICE_UNIVERSE.keys()]
        assert len(set(ids)) == len(SPICE_UNIVERSE)


# ─────────────────────────────────────────────────────────────────────────────
# P3 — NORMALIZE ALL SPICE KEYWORDS
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeAllSpices:
    @pytest.mark.parametrize("spice,kws", list(SPICE_UNIVERSE.items()))
    def test_normalize_spice_keywords(self, p3, p1, spice, kws):
        s = p1.run(spice)
        result = p3.run(s, kws)
        assert isinstance(result, list)
        assert all(kw == kw.lower() for kw in result)
        assert all(kw == kw.strip() for kw in result)
        assert len(result) == len(set(result))

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_no_duplicates_after_normalize(self, p3, p1, spice):
        kws = SPICE_UNIVERSE[spice]
        s = p1.run(spice)
        result = p3.run(s, kws)
        assert len(result) == len(set(result))


# ─────────────────────────────────────────────────────────────────────────────
# P5 — INTENT FOR ALL SPICES
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentAllSpices:
    @pytest.mark.parametrize("spice,kws", list(SPICE_UNIVERSE.items()))
    def test_all_keywords_get_intent(self, p5, p1, spice, kws):
        s = p1.run(spice)
        result = p5.run(s, kws)
        assert len(result) == len(kws)
        valid_intents = {"transactional", "commercial", "comparison",
                         "informational", "navigational"}
        for kw, intent in result.items():
            assert intent in valid_intents

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_buy_keywords_transactional(self, p5, p1, spice):
        s = p1.run(spice)
        kw = f"buy organic {spice}"
        result = p5.run(s, [kw])
        assert result[kw] == "transactional"

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_vs_keywords_comparison(self, p5, p1, spice):
        s = p1.run(spice)
        kw = f"{spice} vs ginger"
        result = p5.run(s, [kw])
        assert result[kw] == "comparison"

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_what_is_informational(self, p5, p1, spice):
        s = p1.run(spice)
        kw = f"what is {spice}"
        result = p5.run(s, [kw])
        assert result[kw] == "informational"

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_best_is_commercial(self, p5, p1, spice):
        s = p1.run(spice)
        kw = f"best {spice} supplement"
        result = p5.run(s, [kw])
        assert result[kw] == "commercial"


# ─────────────────────────────────────────────────────────────────────────────
# OffTopicFilter — ALL SPICES
# ─────────────────────────────────────────────────────────────────────────────

class TestOffTopicAllSpices:
    @pytest.mark.parametrize("spice,kws", list(SPICE_UNIVERSE.items()))
    def test_no_clean_keywords_killed(self, otf, spice, kws):
        # None of the clean spice keywords should be killed
        killed = [kw for kw in kws if otf.is_global_kill(kw)]
        assert killed == [], f"Clean keywords killed for {spice}: {killed}"

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_social_keywords_killed(self, otf, spice):
        social_kws = [f"{spice} meme", f"{spice} viral", f"{spice} tiktok"]
        for kw in social_kws:
            assert otf.is_global_kill(kw) is True, f"'{kw}' should be killed"

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_anti_inflammatory_never_killed(self, otf, spice):
        kw = f"{spice} anti-inflammatory properties"
        assert otf.is_global_kill(kw) is False


# ─────────────────────────────────────────────────────────────────────────────
# KeywordTrafficScorer — ALL SPICES
# ─────────────────────────────────────────────────────────────────────────────

class TestTrafficScorerAllSpices:
    @pytest.mark.parametrize("spice,kws", list(SPICE_UNIVERSE.items()))
    def test_all_keywords_scored(self, kts, spice, kws):
        for kw in kws:
            result = kts.score(kw, volume=100, difficulty=30)
            score = result.opportunity_score
            assert isinstance(score, (int, float))
            assert 0 <= score <= 100, f"Score out of range for '{kw}': {score}"


# ─────────────────────────────────────────────────────────────────────────────
# ContentLifecycleManager — ALL SPICES
# ─────────────────────────────────────────────────────────────────────────────

class TestLifecycleAllSpices:
    @pytest.mark.parametrize("spice,kws", list(SPICE_UNIVERSE.items()))
    def test_register_all_spice_articles(self, lcm, spice, kws):
        for i, kw in enumerate(kws):
            lcm.register(f"{spice}_{i:03d}", kw)
        # All registered
        registered = [id_ for id_ in lcm._lifecycles if id_.startswith(spice)]
        assert len(registered) == len(kws)

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_ranking_updates_for_spice(self, lcm, spice):
        lcm.register(f"{spice}_001", f"{spice} health benefits")
        lcm.update_ranking(f"{spice}_001", new_rank=5)
        lc = lcm._lifecycles[f"{spice}_001"]
        assert lc.current_rank == 5

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_lifecycle_report_for_spice(self, lcm, spice):
        for i in range(3):
            lcm.register(f"{spice}_{i}", f"{spice} keyword {i}")
        report = lcm.report()
        assert isinstance(report, dict)


# ─────────────────────────────────────────────────────────────────────────────
# FULL PIPELINE INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipelineIntegration:
    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_p1_p3_p5_pipeline(self, p1, p3, p5, spice):
        s = p1.run(spice)
        kws = SPICE_UNIVERSE[spice]
        normalized = p3.run(s, kws)
        intents = p5.run(s, normalized)
        assert all(intent in {"transactional", "commercial", "comparison",
                               "informational", "navigational"}
                   for intent in intents.values())

    @pytest.mark.parametrize("spice", list(SPICE_UNIVERSE.keys()))
    def test_p7_scores_all_spice_keywords(self, p1, p3, p5, p7, spice):
        s = p1.run(spice)
        kws = SPICE_UNIVERSE[spice]
        normalized = p3.run(s, kws)
        intent_map = p5.run(s, normalized)
        serp_map = {kw: {"kd_estimate": 40} for kw in normalized}
        scores = p7.run(s, normalized, intent_map, serp_map)
        assert all(0 <= v <= 100 for v in scores.values())

    def test_all_spice_seeds_unique_ids(self, p1):
        ids = {p1.run(spice).id for spice in SPICE_UNIVERSE.keys()}
        assert len(ids) == len(SPICE_UNIVERSE)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
GROUP — P4 Entity Detection
~120 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P4_EntityDetection, Seed


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p4(): return P4_EntityDetection()

@pytest.fixture
def seed(p1): return p1.run("black pepper")


# ─────────────────────────────────────────────────────────────────────────────
# BASIC STRUCTURE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestP4ReturnStructure:
    def test_returns_dict(self, p4, seed):
        result = p4.run(seed, ["black pepper benefits"])
        assert isinstance(result, dict)

    def test_keys_match_input(self, p4, seed):
        kws = ["black pepper", "pepper oil", "piperine capsule"]
        result = p4.run(seed, kws)
        for kw in kws:
            assert kw in result

    def test_each_value_has_ingredient_key(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert "ingredient" in result["black pepper"]

    def test_each_value_has_benefit_key(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert "benefit" in result["black pepper"]

    def test_each_value_has_format_key(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert "format" in result["black pepper"]

    def test_each_value_has_spacy_key(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert "spacy" in result["black pepper"]

    def test_ingredient_is_list(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert isinstance(result["black pepper"]["ingredient"], list)

    def test_benefit_is_list(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert isinstance(result["black pepper"]["benefit"], list)

    def test_format_is_list(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert isinstance(result["black pepper"]["format"], list)

    def test_spacy_is_list(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert isinstance(result["black pepper"]["spacy"], list)

    def test_empty_keyword_list_returns_empty_dict(self, p4, seed):
        result = p4.run(seed, [])
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# INGREDIENT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestP4IngredientDetection:
    def test_pepper_detected_as_ingredient(self, p4, seed):
        result = p4.run(seed, ["black pepper benefits"])
        assert "pepper" in result["black pepper benefits"]["ingredient"]

    def test_cinnamon_detected(self, p4, seed):
        result = p4.run(seed, ["cinnamon tea benefits"])
        assert "cinnamon" in result["cinnamon tea benefits"]["ingredient"]

    def test_turmeric_detected(self, p4, seed):
        result = p4.run(seed, ["turmeric milk recipe"])
        assert "turmeric" in result["turmeric milk recipe"]["ingredient"]

    def test_ginger_detected(self, p4, seed):
        result = p4.run(seed, ["ginger lemon tea"])
        assert "ginger" in result["ginger lemon tea"]["ingredient"]

    def test_cardamom_detected(self, p4, seed):
        result = p4.run(seed, ["cardamom pods benefits"])
        assert "cardamom" in result["cardamom pods benefits"]["ingredient"]

    def test_clove_detected(self, p4, seed):
        result = p4.run(seed, ["clove oil uses"])
        assert "clove" in result["clove oil uses"]["ingredient"]

    def test_cumin_detected(self, p4, seed):
        result = p4.run(seed, ["cumin seeds health"])
        assert "cumin" in result["cumin seeds health"]["ingredient"]

    def test_coriander_detected(self, p4, seed):
        result = p4.run(seed, ["coriander powder recipe"])
        assert "coriander" in result["coriander powder recipe"]["ingredient"]

    def test_nutmeg_detected(self, p4, seed):
        result = p4.run(seed, ["nutmeg benefits"])
        assert "nutmeg" in result["nutmeg benefits"]["ingredient"]

    def test_fenugreek_detected(self, p4, seed):
        result = p4.run(seed, ["fenugreek seeds health"])
        assert "fenugreek" in result["fenugreek seeds health"]["ingredient"]

    def test_basil_detected(self, p4, seed):
        result = p4.run(seed, ["basil leaves recipe"])
        assert "basil" in result["basil leaves recipe"]["ingredient"]

    def test_no_ingredient_in_generic_keyword(self, p4, seed):
        result = p4.run(seed, ["buy spices online"])
        assert result["buy spices online"]["ingredient"] == []

    def test_multiple_ingredients_in_one_keyword(self, p4, seed):
        result = p4.run(seed, ["turmeric ginger tea"])
        ingredients = result["turmeric ginger tea"]["ingredient"]
        assert "turmeric" in ingredients and "ginger" in ingredients

    def test_anise_detected(self, p4, seed):
        result = p4.run(seed, ["anise seed uses"])
        assert "anise" in result["anise seed uses"]["ingredient"]


# ─────────────────────────────────────────────────────────────────────────────
# BENEFIT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestP4BenefitDetection:
    def test_digestion_benefit_detected(self, p4, seed):
        result = p4.run(seed, ["black pepper for digestion"])
        assert "digestion" in result["black pepper for digestion"]["benefit"]

    def test_inflammation_benefit_detected(self, p4, seed):
        result = p4.run(seed, ["black pepper inflammation study"])
        assert "inflammation" in result["black pepper inflammation study"]["benefit"]

    def test_immune_benefit_detected(self, p4, seed):
        result = p4.run(seed, ["pepper immune booster"])
        assert "immune" in result["pepper immune booster"]["benefit"]

    def test_cholesterol_benefit_detected(self, p4, seed):
        result = p4.run(seed, ["turmeric cholesterol benefits"])
        assert "cholesterol" in result["turmeric cholesterol benefits"]["benefit"]

    def test_antioxidant_benefit_detected(self, p4, seed):
        result = p4.run(seed, ["black pepper antioxidant effects"])
        assert "antioxidant" in result["black pepper antioxidant effects"]["benefit"]

    def test_anti_inflammatory_benefit_detected(self, p4, seed):
        result = p4.run(seed, ["ginger anti-inflammatory properties"])
        assert "anti-inflammatory" in result["ginger anti-inflammatory properties"]["benefit"]

    def test_blood_sugar_detected(self, p4, seed):
        result = p4.run(seed, ["cinnamon blood sugar control"])
        assert "blood sugar" in result["cinnamon blood sugar control"]["benefit"]

    def test_weight_loss_detected(self, p4, seed):
        result = p4.run(seed, ["black pepper weight loss tips"])
        assert "weight loss" in result["black pepper weight loss tips"]["benefit"]

    def test_diabetes_detected(self, p4, seed):
        result = p4.run(seed, ["cinnamon diabetes type 2"])
        assert "diabetes" in result["cinnamon diabetes type 2"]["benefit"]

    def test_no_benefit_for_commercial_keyword(self, p4, seed):
        result = p4.run(seed, ["buy black pepper online"])
        assert result["buy black pepper online"]["benefit"] == []

    def test_cancer_detected(self, p4, seed):
        result = p4.run(seed, ["black pepper cancer research"])
        assert "cancer" in result["black pepper cancer research"]["benefit"]


# ─────────────────────────────────────────────────────────────────────────────
# FORMAT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestP4FormatDetection:
    def test_capsule_detected(self, p4, seed):
        result = p4.run(seed, ["piperine capsule supplement"])
        assert "capsule" in result["piperine capsule supplement"]["format"]

    def test_powder_detected(self, p4, seed):
        result = p4.run(seed, ["black pepper powder uses"])
        assert "powder" in result["black pepper powder uses"]["format"]

    def test_oil_detected(self, p4, seed):
        result = p4.run(seed, ["clove oil benefits"])
        assert "oil" in result["clove oil benefits"]["format"]

    def test_tea_detected(self, p4, seed):
        result = p4.run(seed, ["ginger tea recipe"])
        assert "tea" in result["ginger tea recipe"]["format"]

    def test_extract_detected(self, p4, seed):
        result = p4.run(seed, ["black pepper extract study"])
        assert "extract" in result["black pepper extract study"]["format"]

    def test_supplement_detected(self, p4, seed):
        result = p4.run(seed, ["turmeric supplement dosage"])
        assert "supplement" in result["turmeric supplement dosage"]["format"]

    def test_whole_detected(self, p4, seed):
        result = p4.run(seed, ["black pepper whole vs ground"])
        assert "whole" in result["black pepper whole vs ground"]["format"]

    def test_ground_detected(self, p4, seed):
        result = p4.run(seed, ["ground black pepper storage"])
        assert "ground" in result["ground black pepper storage"]["format"]

    def test_seed_format_detected(self, p4, seed):
        result = p4.run(seed, ["fenugreek seed benefits"])
        assert "seed" in result["fenugreek seed benefits"]["format"]

    def test_no_format_for_abstract_keyword(self, p4, seed):
        result = p4.run(seed, ["black pepper history"])
        assert result["black pepper history"]["format"] == []

    def test_leaf_detected(self, p4, seed):
        result = p4.run(seed, ["basil leaf uses"])
        assert "leaf" in result["basil leaf uses"]["format"]

    def test_bark_detected(self, p4, seed):
        result = p4.run(seed, ["cinnamon bark extract"])
        assert "bark" in result["cinnamon bark extract"]["format"]

    def test_stick_detected(self, p4, seed):
        result = p4.run(seed, ["cinnamon stick tea"])
        assert "stick" in result["cinnamon stick tea"]["format"]

    def test_raw_detected(self, p4, seed):
        result = p4.run(seed, ["raw ginger benefits"])
        assert "raw" in result["raw ginger benefits"]["format"]


# ─────────────────────────────────────────────────────────────────────────────
# BATCH PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

class TestP4BatchProcessing:
    def test_processes_large_batch(self, p4, seed):
        kws = [f"black pepper use {i}" for i in range(50)]
        result = p4.run(seed, kws)
        assert len(result) == 50

    def test_all_keywords_present_in_result(self, p4, seed):
        kws = ["black pepper", "cinnamon tea", "turmeric milk", "ginger oil"]
        result = p4.run(seed, kws)
        for kw in kws:
            assert kw in result

    @pytest.mark.parametrize("kw", [
        "black pepper capsule",
        "turmeric powder benefits",
        "cinnamon tea digestion",
        "ginger anti-inflammatory",
        "clove oil extract",
    ])
    def test_structured_keywords_have_entities(self, p4, seed, kw):
        result = p4.run(seed, [kw])
        entity_data = result[kw]
        has_entity = (
            bool(entity_data["ingredient"]) or
            bool(entity_data["benefit"]) or
            bool(entity_data["format"])
        )
        assert has_entity, f"No entity detected for '{kw}'"

    def test_single_keyword(self, p4, seed):
        result = p4.run(seed, ["black pepper"])
        assert "black pepper" in result

    def test_different_seeds_independent(self, p1, p4):
        s1 = p1.run("cinnamon")
        s2 = p1.run("turmeric")
        r1 = p4.run(s1, ["cinnamon tea"])
        r2 = p4.run(s2, ["turmeric milk"])
        assert "cinnamon tea" in r1
        assert "turmeric milk" in r2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

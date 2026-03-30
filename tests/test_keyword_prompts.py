import json
from tools import keyword_prompts as kp


def test_render_functions_returns_str():
    s = kp.render_seed_expansion("cinnamon", industry="food_spices", region="India")
    assert isinstance(s, str) and len(s) > 0

    c = kp.render_clustering_prompt("cinnamon", ["cinnamon benefits","buy cinnamon","cinnamon tourism"], n_clusters=3)
    assert isinstance(c, str) and "Return ONLY valid JSON" in c

    p = kp.render_priority_prompt(["cinnamon benefits","buy cinnamon"])
    assert isinstance(p, str) and "Return ONLY valid JSON" in p


def test_priority_prompt_json_example_schema():
    # Ensure the priority template instructs JSON output (we won't call an LLM here)
    prompt = kp.render_priority_prompt(["a","b"]) 
    assert "Return ONLY valid JSON" in prompt

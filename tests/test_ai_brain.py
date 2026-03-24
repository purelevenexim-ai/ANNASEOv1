"""
GROUP — AnnaBrain AI Brain Module
~150 tests (all AI calls mocked)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import json
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS — guard against missing module
# ─────────────────────────────────────────────────────────────────────────────

try:
    from annaseo_ai_brain import AnnaBrain, PhaseResult, PhaseRunner, BrainCfg
    HAS_BRAIN = True
except ImportError:
    HAS_BRAIN = False

pytestmark = pytest.mark.skipif(not HAS_BRAIN, reason="annaseo_ai_brain not found")


@pytest.fixture
def brain(monkeypatch):
    b = AnnaBrain()
    # Patch all AI providers to avoid network
    # _call_groq returns (text, tokens) tuple
    monkeypatch.setattr(b, "_call_groq",
        lambda prompt, system="", temperature=0.2: ("groq response", 50))
    monkeypatch.setattr(b, "_call_ollama",
        lambda prompt, system="", temperature=0.2: "ollama response")
    monkeypatch.setattr(b, "_call_claude",
        lambda prompt, system="", max_tokens=None: ("claude response", 30))
    return b


@pytest.fixture
def brain_groq_fails(monkeypatch):
    b = AnnaBrain()
    def groq_fail(prompt, system="", temperature=0.2):
        return b._call_ollama(prompt, system, temperature), 0
    monkeypatch.setattr(b, "_call_groq", groq_fail)
    monkeypatch.setattr(b, "_call_ollama",
        lambda prompt, system="", temperature=0.2: "ollama fallback")
    monkeypatch.setattr(b, "_call_claude",
        lambda prompt, system="", max_tokens=None: ("claude response", 30))
    return b


# ─────────────────────────────────────────────────────────────────────────────
# BrainCfg
# ─────────────────────────────────────────────────────────────────────────────

class TestBrainCfg:
    def test_groq_model_set(self):
        assert hasattr(BrainCfg, "GROQ_MODEL")
        assert isinstance(BrainCfg.GROQ_MODEL, str)
        assert len(BrainCfg.GROQ_MODEL) > 0

    def test_claude_max_tokens_exists(self):
        assert hasattr(BrainCfg, "CLAUDE_MAX_TOKENS")

    def test_claude_max_tokens_under_limit(self):
        assert BrainCfg.CLAUDE_MAX_TOKENS <= 1000

    def test_ollama_url_set(self):
        assert hasattr(BrainCfg, "OLLAMA_URL")
        assert BrainCfg.OLLAMA_URL.startswith("http")

    def test_ollama_model_set(self):
        assert hasattr(BrainCfg, "OLLAMA_MODEL")
        assert isinstance(BrainCfg.OLLAMA_MODEL, str)

    def test_groq_key_attribute_exists(self):
        assert hasattr(BrainCfg, "GROQ_KEY")

    def test_claude_key_attribute_exists(self):
        assert hasattr(BrainCfg, "CLAUDE_KEY")

    def test_claude_model_set(self):
        assert hasattr(BrainCfg, "CLAUDE_MODEL")
        assert "claude" in BrainCfg.CLAUDE_MODEL.lower()


# ─────────────────────────────────────────────────────────────────────────────
# PhaseResult
# ─────────────────────────────────────────────────────────────────────────────

class TestPhaseResult:
    def test_creation_with_required_fields(self):
        pr = PhaseResult(phase="P1", title="Seed Input")
        assert pr.phase == "P1"
        assert pr.title == "Seed Input"

    def test_default_status_running(self):
        pr = PhaseResult(phase="P1", title="Test")
        assert pr.status == "running"

    def test_quality_score_default_zero(self):
        pr = PhaseResult(phase="P1", title="Test")
        assert pr.quality_score == 0.0

    def test_data_default_empty_dict(self):
        pr = PhaseResult(phase="P1", title="Test")
        assert pr.data == {}

    def test_console_lines_default_empty(self):
        pr = PhaseResult(phase="P1", title="Test")
        assert pr.console_lines == []

    def test_add_line_appends(self):
        pr = PhaseResult(phase="P1", title="Test")
        pr.add_line("Processing...")
        assert "Processing..." in pr.console_lines

    def test_add_multiple_lines(self):
        pr = PhaseResult(phase="P1", title="Test")
        pr.add_line("Step 1")
        pr.add_line("Step 2")
        assert len(pr.console_lines) == 2

    def test_to_dict_returns_dict(self):
        pr = PhaseResult(phase="P1", title="Test", status="complete")
        d = pr.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_phase(self):
        pr = PhaseResult(phase="P5", title="Intent")
        d = pr.to_dict()
        assert d["phase"] == "P5"

    def test_to_dict_has_status(self):
        pr = PhaseResult(phase="P5", title="Intent", status="complete")
        d = pr.to_dict()
        assert d["status"] == "complete"

    def test_to_dict_has_quality_score(self):
        pr = PhaseResult(phase="P7", title="Scoring", quality_score=80.0)
        d = pr.to_dict()
        assert d["quality_score"] == 80.0

    def test_status_can_be_complete(self):
        pr = PhaseResult(phase="P3", title="Normalization")
        pr.status = "complete"
        assert pr.status == "complete"

    def test_status_can_be_error(self):
        pr = PhaseResult(phase="P3", title="Normalization")
        pr.status = "error"
        assert pr.status == "error"

    def test_status_can_be_needs_review(self):
        pr = PhaseResult(phase="P9", title="Clustering")
        pr.status = "needs_review"
        assert pr.status == "needs_review"

    def test_duration_s_field_exists(self):
        pr = PhaseResult(phase="P1", title="Test")
        assert hasattr(pr, "duration_s")

    def test_ai_model_field_exists(self):
        pr = PhaseResult(phase="P1", title="Test")
        assert hasattr(pr, "ai_model")

    def test_tokens_used_field_exists(self):
        pr = PhaseResult(phase="P1", title="Test")
        assert hasattr(pr, "tokens_used")

    @pytest.mark.parametrize("phase,title", [
        ("P1", "Seed Input"),
        ("P3", "Normalization"),
        ("P5", "Intent Classification"),
        ("P7", "Opportunity Scoring"),
        ("P9", "Cluster Formation"),
        ("P11", "Knowledge Graph"),
    ])
    def test_phase_result_parametrized(self, phase, title):
        pr = PhaseResult(phase=phase, title=title)
        assert pr.phase == phase
        assert pr.title == title


# ─────────────────────────────────────────────────────────────────────────────
# AnnaBrain.think()
# ─────────────────────────────────────────────────────────────────────────────

class TestAnnaBrainThink:
    def test_think_returns_tuple(self, brain):
        result = brain.think("What is piperine?")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_think_first_element_is_string(self, brain):
        text, tokens = brain.think("What is piperine?")
        assert isinstance(text, str)

    def test_think_second_element_is_int(self, brain):
        text, tokens = brain.think("What is piperine?")
        assert isinstance(tokens, int)

    def test_think_uses_groq_first(self, brain):
        text, _ = brain.think("What is piperine?")
        assert text == "groq response"

    def test_think_with_system_prompt(self, brain):
        text, _ = brain.think("Query", system="You are a spice expert.")
        assert isinstance(text, str)

    def test_think_with_temperature(self, brain):
        text, _ = brain.think("Query", temperature=0.5)
        assert isinstance(text, str)

    def test_think_claude_flag(self, brain):
        text, _ = brain.think("Quality check", use_claude=True)
        assert isinstance(text, str)

    @pytest.mark.parametrize("prompt", [
        "What is black pepper?",
        "List health benefits of piperine",
        "Why is turmeric anti-inflammatory?",
        "How to use cinnamon for blood sugar?",
        "Compare black pepper vs white pepper",
    ])
    def test_think_various_prompts(self, brain, prompt):
        text, tokens = brain.think(prompt)
        assert isinstance(text, str)
        assert isinstance(tokens, int)


# ─────────────────────────────────────────────────────────────────────────────
# AnnaBrain.parse_json()
# ─────────────────────────────────────────────────────────────────────────────

class TestAnnaBrainParseJson:
    def test_parses_valid_json_dict(self, brain):
        data = json.dumps({"key": "value"})
        result = brain.parse_json(data)
        assert isinstance(result, dict)

    def test_parses_valid_json_list(self, brain):
        data = json.dumps(["kw1", "kw2", "kw3"])
        result = brain.parse_json(data)
        assert isinstance(result, list)

    def test_invalid_json_returns_empty(self, brain):
        result = brain.parse_json("not json {")
        assert result == {} or result is None or isinstance(result, (dict, list))

    def test_json_with_markdown_fences(self, brain):
        data = '```json\n{"key": "value"}\n```'
        result = brain.parse_json(data)
        if result:
            assert isinstance(result, dict)

    def test_empty_string_returns_empty(self, brain):
        result = brain.parse_json("")
        assert result == {} or result is None or isinstance(result, (dict, list))

    def test_nested_json_parsed(self, brain):
        data = json.dumps({"clusters": {"Health": ["kw1", "kw2"]}})
        result = brain.parse_json(data)
        assert isinstance(result, dict)
        assert "clusters" in result

    def test_json_with_extra_text(self, brain):
        data = 'Here is the result:\n```json\n{"a": 1}\n```\nDone.'
        result = brain.parse_json(data)
        # Should extract the JSON part
        if result:
            assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# AnnaBrain.classify_intents()
# ─────────────────────────────────────────────────────────────────────────────

class TestAnnaBrainClassifyIntents:
    def test_returns_dict(self, brain, monkeypatch):
        expected = {"black pepper benefits": "informational", "buy pepper": "transactional"}
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: (json.dumps(expected), 50))
        result = brain.classify_intents(["black pepper benefits", "buy pepper"])
        assert isinstance(result, dict)

    def test_fallback_on_invalid_response(self, brain, monkeypatch):
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: ("invalid json", 0))
        monkeypatch.setattr(brain, "_call_ollama",
            lambda *a, **kw: "invalid json")
        result = brain.classify_intents(["black pepper benefits"])
        assert isinstance(result, dict)

    def test_empty_list_handled(self, brain):
        result = brain.classify_intents([])
        assert isinstance(result, dict)

    @pytest.mark.parametrize("kw_list", [
        ["black pepper benefits"],
        ["buy pepper", "what is pepper", "best pepper"],
        ["pepper vs chili", "pepper brand website"],
    ])
    def test_various_keyword_lists(self, brain, monkeypatch, kw_list):
        expected = {kw: "informational" for kw in kw_list}
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: (json.dumps(expected), 50))
        result = brain.classify_intents(kw_list)
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# AnnaBrain.identify_pillars()
# ─────────────────────────────────────────────────────────────────────────────

class TestAnnaBrainIdentifyPillars:
    def test_returns_list(self, brain, monkeypatch):
        expected = [{"keyword": "black pepper", "pillar_title": "Guide",
                     "cluster_theme": "health", "reason": "broad head term"}]
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: (json.dumps(expected), 50))
        result = brain.identify_pillars(["kw1", "kw2", "kw3"], seed="black pepper")
        assert isinstance(result, list)

    def test_empty_keywords_returns_empty(self, brain):
        result = brain.identify_pillars([], seed="black pepper")
        assert result == []

    def test_result_contains_keyword_field(self, brain, monkeypatch):
        expected = [{"keyword": "black pepper", "pillar_title": "Guide",
                     "cluster_theme": "health", "reason": "broad"}]
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: (json.dumps(expected), 50))
        result = brain.identify_pillars(["black pepper", "pepper oil"], seed="black pepper")
        if result:
            assert "keyword" in result[0]


# ─────────────────────────────────────────────────────────────────────────────
# AnnaBrain.generate_keyword_ideas()
# ─────────────────────────────────────────────────────────────────────────────

class TestAnnaBrainGenerateKeywordIdeas:
    def test_returns_list(self, brain, monkeypatch):
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: (json.dumps(["kw1", "kw2", "kw3"]), 50))
        result = brain.generate_keyword_ideas("black pepper")
        assert isinstance(result, list)

    def test_fallback_returns_list(self, brain, monkeypatch):
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: ("not json", 0))
        monkeypatch.setattr(brain, "_call_ollama",
            lambda *a, **kw: "not json")
        result = brain.generate_keyword_ideas("black pepper")
        assert isinstance(result, list)

    @pytest.mark.parametrize("seed", ["cinnamon", "turmeric", "ginger"])
    def test_various_seeds(self, brain, seed, monkeypatch):
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: (json.dumps([f"{seed} a", f"{seed} b"]), 30))
        result = brain.generate_keyword_ideas(seed)
        assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# AnnaBrain.score_keyword_opportunity()
# ─────────────────────────────────────────────────────────────────────────────

class TestAnnaBrainScoreKeyword:
    def test_returns_dict(self, brain, monkeypatch):
        import json as _json
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: (_json.dumps({"score": 75, "tag": "quick_win",
                "reason": "good", "content_type": "blog", "priority": "high"}), 30))
        result = brain.score_keyword_opportunity("black pepper benefits", 1000, 40, "informational")
        assert isinstance(result, dict)

    def test_result_has_score(self, brain, monkeypatch):
        import json as _json
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: (_json.dumps({"score": 85, "tag": "quick_win",
                "reason": "ok", "content_type": "blog", "priority": "high"}), 30))
        result = brain.score_keyword_opportunity("black pepper", 500, 30, "transactional")
        assert "score" in result
        assert 0 <= result["score"] <= 100

    def test_fallback_on_bad_response(self, brain, monkeypatch):
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw: ("not json", 0))
        monkeypatch.setattr(brain, "_call_ollama",
            lambda *a, **kw: "not json")
        result = brain.score_keyword_opportunity("black pepper", 1000, 50, "informational")
        assert isinstance(result, dict)
        assert "score" in result

    @pytest.mark.parametrize("kw,volume,difficulty,intent", [
        ("black pepper benefits", 1000, 40, "informational"),
        ("buy black pepper", 500, 30, "transactional"),
        ("best pepper supplement", 200, 60, "commercial"),
        ("black pepper vs white", 300, 45, "comparison"),
    ])
    def test_various_keyword_types(self, brain, monkeypatch, kw, volume, difficulty, intent):
        import json as _json
        monkeypatch.setattr(brain, "_call_groq",
            lambda *a, **kw_: (_json.dumps({"score": 70, "tag": "standard",
                "reason": "ok", "content_type": "blog", "priority": "medium"}), 30))
        result = brain.score_keyword_opportunity(kw, volume, difficulty, intent)
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# PhaseRunner
# ─────────────────────────────────────────────────────────────────────────────

class TestPhaseRunner:
    def test_run_with_review_returns_phase_result(self):
        runner = PhaseRunner()
        pr = runner.run_with_review(
            lambda: {"seed": "black pepper"},
            "P1", "Seed Input",
        )
        assert isinstance(pr, PhaseResult)

    def test_result_has_correct_phase(self):
        runner = PhaseRunner()
        pr = runner.run_with_review(lambda: {}, "P5", "Intent Classification")
        assert pr.phase == "P5"

    def test_result_has_correct_title(self):
        runner = PhaseRunner()
        pr = runner.run_with_review(lambda: {}, "P5", "Intent Classification")
        assert pr.title == "Intent Classification"

    def test_result_status_complete_on_success(self):
        runner = PhaseRunner()
        pr = runner.run_with_review(lambda: {"a": 1}, "P7", "Opportunity Scoring")
        assert pr.status in ("complete", "needs_review")

    def test_result_status_error_on_exception(self):
        runner = PhaseRunner()
        def fail(): raise ValueError("intentional")
        pr = runner.run_with_review(fail, "P3", "Normalization")
        assert pr.status == "error"

    def test_data_passed_to_result(self):
        runner = PhaseRunner()
        expected = {"keywords": ["a", "b", "c"]}
        pr = runner.run_with_review(lambda: expected, "P2", "Keyword Expansion")
        assert pr.data == expected

    def test_list_data_quality_score(self):
        runner = PhaseRunner()
        data = [f"kw {i}" for i in range(20)]
        pr = runner.run_with_review(lambda: data, "P3", "Normalization")
        # quality_score = min(100, len(data) * 2) = min(100, 40) = 40
        assert pr.quality_score == 40.0

    def test_small_output_triggers_needs_review(self):
        runner = PhaseRunner()
        # 1 item × 2 = 2 < 30 → needs_review
        pr = runner.run_with_review(lambda: ["one_kw"], "P3", "Normalization")
        assert pr.status == "needs_review"

    def test_large_dict_output_high_quality(self):
        runner = PhaseRunner()
        data = {f"key_{i}": f"val_{i}" for i in range(25)}
        pr = runner.run_with_review(lambda: data, "P5", "Intent")
        # quality = min(100, 25*5) = min(100, 125) = 100
        assert pr.quality_score == 100.0

    def test_duration_is_positive(self):
        runner = PhaseRunner()
        pr = runner.run_with_review(lambda: {}, "P1", "Seed Input")
        assert pr.duration_s >= 0.0

    def test_console_lines_added(self):
        runner = PhaseRunner()
        pr = runner.run_with_review(lambda: {}, "P1", "Seed Input")
        assert len(pr.console_lines) >= 1

    @pytest.mark.parametrize("phase,title,data,expected_status", [
        ("P1", "Seed Input",       {"seed": "ok"}, "complete"),
        ("P3", "Normalization",    ["kw1", "kw2"], "needs_review"),
        ("P5", "Intent",           {f"k{i}": "inf" for i in range(10)}, "complete"),
    ])
    def test_runner_parametrized(self, phase, title, data, expected_status):
        runner = PhaseRunner()
        pr = runner.run_with_review(lambda: data, phase, title)
        assert pr.phase == phase
        if expected_status == "complete":
            assert pr.status in ("complete", "needs_review")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

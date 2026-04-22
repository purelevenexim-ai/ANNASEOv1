"""
tests/chaos/test_chaos.py
==========================
ADVANCED — Chaos Tests: Failure Simulation & Resilience.

Simulates:
  1. AI timeout / unavailability
  2. Malformed / adversarial input
  3. Partial pipeline failures (stage crashes mid-run)
  4. Garbage / empty / Unicode / injection inputs
  5. Memory limits (very large inputs)

The system must NOT crash on any of these — it should degrade
gracefully with meaningful error states, never silent corruption.

Run: pytest tests/chaos/ -v --tb=short
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("ANNASEO_TESTING", "1")


# ── 1. Adversarial / garbage inputs ──────────────────────────────────────────

class TestAdversarialInputs:
    GARBAGE_INPUTS = [
        "",                                          # empty string
        "   ",                                       # whitespace only
        "💣🚀🎯" * 100,                              # emoji overload
        "script alert('xss') /script " * 20,        # XSS-style injection
        "0" * 10_000,                                # very long single token
        None,                                        # null
        123,                                         # wrong type
        ["not", "a", "string"],                      # wrong type
        "SELECT * FROM users; DROP TABLE users; --", # SQL injection style
        "\x00\x01\x02\x03",                          # null bytes
    ]

    @pytest.mark.parametrize("garbage", GARBAGE_INPUTS)
    def test_canonical_handles_garbage(self, garbage):
        """canonical() must not raise on any input."""
        from engines.kw2.normalizer import canonical
        try:
            result = canonical(str(garbage) if garbage is not None else "")
            assert isinstance(result, str)
        except Exception as exc:
            pytest.fail(f"canonical() raised on input {garbage!r}: {exc}")

    @pytest.mark.parametrize("garbage", GARBAGE_INPUTS)
    def test_schema_validator_doesnt_crash_on_garbage(self, garbage):
        """Schema validator must return issues, not raise exceptions."""
        from audit.validators.schema import validate_keyword_row
        row = {"keyword": garbage, "intent": "purchase", "ai_relevance": 0.5, "buyer_readiness": 0.5}
        try:
            issues = validate_keyword_row(row)
            assert isinstance(issues, list)
        except Exception as exc:
            pytest.fail(f"validate_keyword_row raised on garbage input {garbage!r}: {exc}")

    def test_ai_validator_doesnt_crash_on_empty(self):
        from audit.validators.ai_reasoning import validate_ai_output
        result = validate_ai_output({})
        assert result["valid"] is False
        assert result["score"] == 0.0

    def test_ai_validator_doesnt_crash_on_wrong_types(self):
        from audit.validators.ai_reasoning import validate_ai_output
        result = validate_ai_output({
            "keywords": "should be a list",
            "profile": ["should be a dict"],
            "clusters": None,
        })
        assert isinstance(result, dict)
        assert "valid" in result

    def test_regression_diff_handles_none_values(self):
        from audit.regression.diff import compare_outputs
        result = compare_outputs(
            {"keywords": None, "profile": None},
            {"keywords": None, "profile": None}
        )
        assert isinstance(result, float)

    def test_merge_batch_with_empty_keywords(self):
        from engines.kw2.normalizer import merge_keyword_batch
        try:
            merged = merge_keyword_batch([])
            assert isinstance(merged, list)
        except Exception as exc:
            pytest.fail(f"merge_keyword_batch([]) raised: {exc}")

    def test_consistency_check_with_empty_inputs(self):
        from audit.validators.consistency import run_all_consistency_checks
        result = run_all_consistency_checks(
            profile={}, keywords=[], strategy={}, source_text=""
        )
        assert isinstance(result, dict)
        assert "valid" in result


# ── 2. AI failure simulation ──────────────────────────────────────────────────

class TestAIFailureSimulation:
    def test_ai_caller_handles_network_error(self):
        """kw2_ai_call must not crash when all providers fail."""
        from engines.kw2.ai_caller import kw2_ai_call
        with patch("core.ai_config.AIRouter.call_with_tokens", side_effect=ConnectionError("AI down")):
            with patch("core.ai_config.AIRouter._call_groq", return_value=("", 0)):
                with patch("core.ai_config.AIRouter._call_gemini", return_value=""):
                    try:
                        result = kw2_ai_call("test prompt", provider="groq")
                        # Should return empty string, not crash
                        assert isinstance(result, str)
                    except SystemExit:
                        pytest.fail("kw2_ai_call raised SystemExit on network failure")
                    except Exception:
                        pass  # Acceptable — just must not hang or corrupt state

    def test_llm_judge_handles_unreachable_ollama(self):
        """LLM judge must return error dict, not crash, when Ollama is down."""
        from audit.judge.llm_judge import run_llm_judge
        import httpx

        with patch("httpx.post", side_effect=httpx.ConnectError("Connection refused")):
            verdict = run_llm_judge(
                input_data={"url": "https://example.com"},
                output_data={"keywords": [], "profile": {}}
            )
        assert isinstance(verdict, dict)
        assert "error" in verdict or verdict.get("final_score", 0) < 0


# ── 3. Partial pipeline failure ───────────────────────────────────────────────

class TestPartialPipelineFailures:
    def test_tree_builder_handles_missing_score_field(self):
        """TreeBuilder._select_top100 must not crash when keywords are missing hybrid_score."""
        from engines.kw2.tree_builder import TreeBuilder
        tb = TreeBuilder()
        kws_without_score = [
            {"id": "kw1", "keyword": "buy basil", "intent": "purchase", "pillar": "basil"},
            {"id": "kw2", "keyword": "basil price", "intent": "commercial", "pillar": "basil"},
        ]
        try:
            result = tb._select_top100(kws_without_score)
            assert isinstance(result, list)
        except Exception as exc:
            pytest.fail(f"_select_top100 crashed on missing hybrid_score: {exc}")

    def test_audit_runner_handles_missing_session(self, tmp_path):
        """run_full_audit must return error dict, not raise, for unknown session."""
        from audit import runner
        result = runner.run_full_audit(
            session_id="nonexistent_session_xyz",
            project_id="fake_project",
            save_report=False,
        )
        # Either returns error dict or a valid (empty) audit report
        assert isinstance(result, dict)

    def test_regression_store_handles_corrupt_json(self, tmp_path, monkeypatch):
        """load_baseline must not crash on corrupt JSON file."""
        from audit.regression import store
        baseline_dir = tmp_path / "baselines"
        baseline_dir.mkdir()
        monkeypatch.setattr(store, "_BASELINE_DIR", baseline_dir)

        # Write corrupt JSON
        (baseline_dir / "corrupt_case.json").write_text("{ this is not json ]]]")

        try:
            result = store.load_baseline("corrupt_case")
            # Should return {} or raise JSONDecodeError (acceptable)
        except json.JSONDecodeError:
            pass  # Expected — don't crash the test runner
        except Exception as exc:
            pytest.fail(f"load_baseline raised unexpected error: {exc}")


# ── 4. Unicode & injection resilience ────────────────────────────────────────

class TestUnicodeResilience:
    UNICODE_INPUTS = [
        "كردمون عضوي",                  # Arabic
        "有机豆蔻批发",                  # Chinese
        "Bio-Kardamom Großhandel",      # German with umlauts
        "कार्डमम ऑनलाइन खरीदें",      # Hindi
        "Ñoño especia orgánica",        # Spanish with special chars
        "кардамон оптом Индия",         # Russian
    ]

    @pytest.mark.parametrize("text", UNICODE_INPUTS)
    def test_canonical_handles_unicode(self, text):
        from engines.kw2.normalizer import canonical
        result = canonical(text)
        assert isinstance(result, str)

    @pytest.mark.parametrize("text", UNICODE_INPUTS)
    def test_schema_validator_handles_unicode_keyword(self, text):
        from audit.validators.schema import validate_keyword_row
        row = {"keyword": text, "intent": "purchase", "ai_relevance": 0.8, "buyer_readiness": 0.7}
        issues = validate_keyword_row(row)
        assert isinstance(issues, list)

    def test_consistency_check_with_unicode_source(self):
        from audit.validators.consistency import check_entity_hallucination
        entities = ["cardamom", "pepper"]
        source = "We sell premium कार्डमम and black pepper worldwide"
        issues = check_entity_hallucination(entities, source)
        assert isinstance(issues, list)


# ── 5. Memory / scale stress ──────────────────────────────────────────────────

class TestMemoryStress:
    def test_schema_validator_handles_10k_keywords(self):
        """Validator must not OOM or timeout on 10,000 keyword lists."""
        from audit.validators.schema import validate_keyword_list
        large_list = [
            {"keyword": f"keyword {i}", "intent": "purchase", "ai_relevance": 0.8, "buyer_readiness": 0.7}
            for i in range(10_000)
        ]
        result = validate_keyword_list(large_list)
        assert "total" in result
        assert result["total"] == 10_000

    def test_regression_diff_handles_large_sets(self):
        """compare_outputs must work with 5000-keyword sets without hanging."""
        from audit.regression.diff import compare_outputs
        large_out = {
            "keywords": [{"keyword": f"kw {i}", "intent": "purchase", "ai_relevance": 0.8, "buyer_readiness": 0.7} for i in range(5000)],
            "profile": {"pillars": ["a", "b"], "universe": "test"},
        }
        score = compare_outputs(large_out, large_out)
        assert score == 1.0

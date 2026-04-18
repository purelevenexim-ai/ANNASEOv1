import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from unittest.mock import patch

_HTML = """<h1>Test Article</h1>
<h2>Section One</h2>
<p>Some content about spices here with enough words to form a meaningful section.</p>
<h2>Section Two</h2>
<p>More content covering additional details about the topic for testing purposes only.</p>"""


def test_pipeline_runs_when_score_is_90():
    """Pipeline must NOT skip humanization when auditor score >= 90."""
    humanize_calls = []

    def mock_humanize_section(section_html, keyword, **kwargs):
        humanize_calls.append(section_html)
        return {"success": True, "html": "<p>Humanized text.</p>", "provider": "mock", "tokens": 10}

    with patch("engines.humanize.pipeline.analyze_ai_signals") as mock_audit, \
         patch("engines.humanize.pipeline.humanize_section", side_effect=mock_humanize_section), \
         patch("engines.humanize.pipeline.extract_seo_anchors") as mock_lock, \
         patch("engines.humanize.pipeline.validate_seo_preservation") as mock_seo, \
         patch("engines.humanize.pipeline.normalize_keyword_density", side_effect=lambda h, k, **kw: h), \
         patch("engines.humanize.pipeline.validate_editorial", return_value={"score": 95, "issues": []}):

        mock_audit.return_value = {
            "score": 90, "signals": [], "signal_count": 0,
            "deductions": 10, "word_count": 50, "summary": "ok",
        }
        mock_lock.return_value = {"links": [], "kw_density": 1.0, "keyword_positions": []}
        mock_seo.return_value = {"passed": True, "issues": []}

        from engines.humanize.pipeline import run_humanize_pipeline
        result = run_humanize_pipeline(_HTML, keyword="spices", skip_judge=True)

    assert result["success"] is True
    assert len(humanize_calls) > 0, (
        f"humanize_section was never called (called {len(humanize_calls)}x). "
        "The score-based skip gate is still active."
    )


def test_ollama_max_ctx_is_4096():
    """OLLAMA_MAX_CTX must be 4096 — 2048 is too small for humanize prompts."""
    from core.ai_config import AICfg
    assert AICfg.OLLAMA_MAX_CTX == 4096, (
        f"OLLAMA_MAX_CTX is {AICfg.OLLAMA_MAX_CTX}, expected 4096. "
        "A humanize prompt is ~1000-1500 tokens; 2048 leaves almost no output budget."
    )


def test_ollama_prompt_trim_removes_outline_and_caps_section():
    """The trimming logic that the Ollama adapter applies must:
    1. Strip the ARTICLE OUTLINE block (saves ~100 tokens for small models)
    2. Truncate SECTION TO REWRITE body to 2000 chars
    """
    from engines.humanize.humanizer import build_humanize_prompt

    long_outline = [f"Section heading number {i} about a topic" for i in range(20)]
    long_section = "<p>" + ("word " * 800) + "</p>"  # ~800 words

    prompt = build_humanize_prompt(
        section_html=long_section,
        keyword="spices",
        outline=long_outline,
    )

    assert "ARTICLE OUTLINE" in prompt, "Precondition: prompt must contain outline"
    assert "SECTION TO REWRITE:" in prompt, "Precondition: prompt must contain section"
    assert "━━━ CRITICAL RULES ━━━" in prompt, "Precondition: prompt must contain rules anchor"

    # Apply the trimming (same logic as the adapter)
    _p = prompt
    _o = _p.find("ARTICLE OUTLINE")
    _r = _p.find("━━━ CRITICAL RULES ━━━")
    if 0 < _o < _r:
        _p = _p[:_o] + _p[_r:]

    _m = "SECTION TO REWRITE:"
    _i = _p.find(_m)
    if _i >= 0:
        _head = _p[:_i + len(_m)]
        _body = _p[_i + len(_m):]
        _p = _head + _body[:2000] + "\n\nReturn ONLY the rewritten HTML."

    assert "ARTICLE OUTLINE" not in _p, "Outline block must be removed"

    _sec_start = _p.find("SECTION TO REWRITE:") + len("SECTION TO REWRITE:")
    _sec_tail = _p[_sec_start:]
    assert len(_sec_tail) <= 2060, (
        f"Section tail is {len(_sec_tail)} chars — should be ≤2060 (2000 content + closing)"
    )

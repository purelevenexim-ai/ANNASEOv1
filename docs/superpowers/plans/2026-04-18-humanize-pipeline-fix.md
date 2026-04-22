# Humanize Pipeline Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Step 9 (Humanize) so it always runs on AI-drafted articles and works correctly when Ollama is selected as the provider.

**Architecture:** Three targeted changes — (1) remove the score-based skip gate in `pipeline.py`, (2) raise `OLLAMA_MAX_CTX` from 2048 to 4096 in `ai_config.py`, and (3) add prompt trimming inside the `ollama` branch of `_HumanizeRouterAdapter` in `content_generation_engine.py`. No new abstractions or interface changes.

**Tech Stack:** Python 3.12, pytest, Ollama proxy at `http://172.235.16.165:8080` (mistral:7b-instruct-q4_K_M)

**Spec:** `docs/superpowers/specs/2026-04-18-humanize-pipeline-fix-design.md`

---

### Task 1: Tests + remove the skip gate (`pipeline.py`)

**Files:**
- Create: `tests/test_humanize_pipeline.py`
- Modify: `engines/humanize/pipeline.py` (remove lines ~105–117)

- [ ] **Step 1: Create the test file with a failing test for the skip gate**

Create `tests/test_humanize_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run to confirm it fails (skip gate still in place)**

```bash
cd /root/ANNASEOv1 && python -m pytest tests/test_humanize_pipeline.py::test_pipeline_runs_when_score_is_90 -v
```

Expected: **FAIL** — `AssertionError: humanize_section was never called`

- [ ] **Step 3: Remove the skip gate block from pipeline.py**

In `engines/humanize/pipeline.py`, delete the block starting at the line `if original_score >= 90 and section_index is None:` through the closing `}` of the return statement (currently lines ~105–117). The block looks like:

```python
    if original_score >= 90 and section_index is None:
        progress("done", 0, 0, f"Content already scores {original_score}/100 — no humanization needed")
        return {
            "success": True,
            "humanized_html": html,
            "original_score": original_score,
            "final_score": original_score,
            "judge_score": None,
            "sections_processed": 0,
            "sections_total": 0,
            "details": {"skipped": True, "reason": "Content already scores 90+"},
            "tokens_used": 0,
            "elapsed_seconds": round(time.time() - start_time, 1),
        }
```

Delete the entire block. The next non-blank line after it should be `# ── Step 2: Extract SEO anchors to protect`.

- [ ] **Step 4: Run test to confirm it passes**

```bash
cd /root/ANNASEOv1 && python -m pytest tests/test_humanize_pipeline.py::test_pipeline_runs_when_score_is_90 -v
```

Expected: **PASS**

- [ ] **Step 5: Commit**

```bash
cd /root/ANNASEOv1 && git add engines/humanize/pipeline.py tests/test_humanize_pipeline.py
git commit -m "fix(humanize): remove score-based skip gate — always humanize fresh drafts

The rule-based auditor checks only 7 surface heuristics. AI-drafted content
routinely scores 90+ without being human-readable. Removing the gate ensures
every draft goes through the full section-by-section humanization pass."
```

---

### Task 2: Raise Ollama context window (`ai_config.py`)

**Files:**
- Modify: `core/ai_config.py` (line ~49 and ~336)
- Modify: `tests/test_humanize_pipeline.py` (add one test)

- [ ] **Step 1: Write failing test for OLLAMA_MAX_CTX**

Add to `tests/test_humanize_pipeline.py`:

```python
def test_ollama_max_ctx_is_4096():
    """OLLAMA_MAX_CTX must be 4096 — 2048 is too small for humanize prompts."""
    from core.ai_config import AICfg
    assert AICfg.OLLAMA_MAX_CTX == 4096, (
        f"OLLAMA_MAX_CTX is {AICfg.OLLAMA_MAX_CTX}, expected 4096. "
        "A humanize prompt is ~1000–1500 tokens; 2048 leaves almost no output budget."
    )
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /root/ANNASEOv1 && python -m pytest tests/test_humanize_pipeline.py::test_ollama_max_ctx_is_4096 -v
```

Expected: **FAIL** — `AssertionError: OLLAMA_MAX_CTX is 2048, expected 4096`

- [ ] **Step 3: Update OLLAMA_MAX_CTX in ai_config.py**

In `core/ai_config.py`, line ~49:

```python
# BEFORE:
    OLLAMA_MAX_CTX  = 2048 # max context tokens — do not exceed (memory limit)

# AFTER:
    OLLAMA_MAX_CTX  = 4096 # context for humanize prompts; verify proxy /health before raising further
```

Also update the stale comment in `_call_ollama()` at ~line 336 (inside the docstring):

```python
# BEFORE:
        # - num_ctx capped at 2048 (proxy memory limit)

# AFTER:
        # - num_ctx set via AICfg.OLLAMA_MAX_CTX (verify proxy memory if raising above 4096)
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
cd /root/ANNASEOv1 && python -m pytest tests/test_humanize_pipeline.py::test_ollama_max_ctx_is_4096 -v
```

Expected: **PASS**

- [ ] **Step 5: Commit**

```bash
cd /root/ANNASEOv1 && git add core/ai_config.py tests/test_humanize_pipeline.py
git commit -m "fix(ollama): raise OLLAMA_MAX_CTX 2048→4096 for humanize section prompts

With 4096 context and ~900-1000 token input, Ollama has ~3000 tokens of output
budget — sufficient for rewriting sections of up to 500 words."
```

---

### Task 3: Add Ollama prompt trimming (`content_generation_engine.py`)

**Files:**
- Modify: `engines/content_generation_engine.py` (~line 3503–3533, Ollama adapter case)
- Modify: `tests/test_humanize_pipeline.py` (add trimming logic test)

- [ ] **Step 1: Write test verifying the trimming logic**

Add to `tests/test_humanize_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run test to confirm it passes (logic is correct)**

```bash
cd /root/ANNASEOv1 && python -m pytest tests/test_humanize_pipeline.py::test_ollama_prompt_trim_removes_outline_and_caps_section -v
```

Expected: **PASS** (this validates the trimming logic in isolation)

- [ ] **Step 3: Add the trimming to the Ollama adapter in content_generation_engine.py**

Find the `elif provider in ("ollama",):` branch inside `_HumanizeRouterAdapter.call_with_tokens()` (~line 3503). Locate the existing `_payload` dict construction and the `_hreq.post(...)` call. Replace that section with:

```python
                        elif provider in ("ollama",):
                            if not AIRouter._ollama_check_health():
                                _step_log("warn", "[Humanize] ollama unhealthy — skipping", 9)
                                continue
                            import requests as _hreq
                            from core.ai_config import AICfg as _AICfg
                            # Trim prompt for Ollama: strip outline block + cap section at 2000 chars
                            _ollama_prompt = prompt
                            _outline_start = _ollama_prompt.find("ARTICLE OUTLINE")
                            _rules_start = _ollama_prompt.find("━━━ CRITICAL RULES ━━━")
                            if 0 < _outline_start < _rules_start:
                                _ollama_prompt = _ollama_prompt[:_outline_start] + _ollama_prompt[_rules_start:]
                            _sec_marker = "SECTION TO REWRITE:"
                            _sec_idx = _ollama_prompt.find(_sec_marker)
                            if _sec_idx >= 0:
                                _head = _ollama_prompt[:_sec_idx + len(_sec_marker)]
                                _body = _ollama_prompt[_sec_idx + len(_sec_marker):]
                                _ollama_prompt = _head + _body[:2000] + "\n\nReturn ONLY the rewritten HTML."
                            _payload = {
                                "model": _AICfg.OLLAMA_MODEL,
                                "prompt": _ollama_prompt,
                                "stream": False,
                                "options": {"temperature": temperature, "num_ctx": _AICfg.OLLAMA_MAX_CTX},
                            }
                            if system:
                                _payload["system"] = system
                            acquired = AIRouter._ollama_sem.acquire(blocking=True, timeout=3)
                            if not acquired:
                                _step_log("warn", "[Humanize] ollama busy — skipping", 9)
                                continue
                            try:
                                r = _hreq.post(f"{_AICfg.OLLAMA_URL}/api/generate", json=_payload, timeout=60)
                                if r.ok:
                                    import re as _re
                                    text = r.json().get("response", "").strip()
                                    text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
                                    if text:
                                        _step_log("info", f"[Humanize] ollama succeeded ({len(text)} chars)", 9)
                                        return text, 0
                                _step_log("warn", f"[Humanize] ollama returned empty/error ({r.status_code})", 9)
                            finally:
                                AIRouter._ollama_sem.release()
```

- [ ] **Step 4: Run all humanize tests**

```bash
cd /root/ANNASEOv1 && python -m pytest tests/test_humanize_pipeline.py -v
```

Expected: All **3 tests PASS**

- [ ] **Step 5: Commit**

```bash
cd /root/ANNASEOv1 && git add engines/content_generation_engine.py tests/test_humanize_pipeline.py
git commit -m "fix(humanize): trim prompt in Ollama adapter — strip outline + cap section at 2000 chars

Reduces Ollama input from ~1200-1500 tokens to ~800-1000 tokens, leaving
~3000 tokens of output budget with the new 4096 context window."
```

---

### Task 4: Live test with Ollama

**Files:**
- Temporarily modify: `engines/content_generation_engine.py` line ~560 (revert after test)

- [ ] **Step 1: Verify Ollama proxy is healthy**

```bash
curl -s http://172.235.16.165:8080/health | python3 -m json.tool
```

Expected: `"status": "ok"` and `"circuit_breaker": {"open": false}`. If down or circuit open, **stop** — do not proceed until proxy is healthy.

- [ ] **Step 2: Confirm proxy accepts num_ctx=4096**

```bash
curl -s -X POST http://172.235.16.165:8080/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral:7b-instruct-q4_K_M","prompt":"Rewrite this in a human voice: AI-generated content is crucial for businesses.","stream":false,"options":{"num_ctx":4096,"temperature":0.5}}' \
  | python3 -m json.tool | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK:', d.get('response','')[:100])"
```

Expected: `OK: <some rewritten text>`. If 503 or empty: the proxy rejects 4096 — revert `OLLAMA_MAX_CTX` to 3072 and retry.

- [ ] **Step 3: Temporarily change default humanize chain to Ollama-only**

In `engines/content_generation_engine.py`, find line ~560:
```python
    humanize:     StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_deepseek",    "gemini_paid"))
```

Change to:
```python
    humanize:     StepAIConfig = field(default_factory=lambda: StepAIConfig("ollama",          "skip",           "skip"))
```

- [ ] **Step 4: Find a real article ID in the database**

```bash
cd /root/ANNASEOv1 && python3 -c "
import sqlite3, sys
conn = sqlite3.connect('annaseo.db')
# Find table name
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
print('Tables:', tables)
# Try content_blogs first
for tbl in ['content_blogs', 'articles', 'blogs']:
    if tbl in tables:
        try:
            rows = conn.execute(f\"SELECT id, keyword, LENGTH(draft_html) len FROM {tbl} WHERE draft_html IS NOT NULL AND draft_html != '' ORDER BY created_at DESC LIMIT 5\").fetchall()
            print(f'Table {tbl}:')
            for r in rows: print(' ', r)
        except Exception as e:
            print(f'  {tbl}: {e}')
conn.close()
"
```

Note the article `id` and `keyword` for Step 5.

- [ ] **Step 5: Run live humanization test**

```bash
cd /root/ANNASEOv1 && python3 - <<'EOF'
import sys, os, logging
sys.path.insert(0, '.')
sys.path.insert(0, 'engines')

logging.basicConfig(level=logging.INFO, format='%(name)s — %(message)s')

# Grab a real article from DB
import sqlite3
conn = sqlite3.connect('annaseo.db')
# Replace 'content_blogs' and column names if needed based on Step 4 output
row = conn.execute("SELECT id, keyword, draft_html FROM content_blogs WHERE draft_html IS NOT NULL AND draft_html != '' ORDER BY created_at DESC LIMIT 1").fetchone()
conn.close()

if not row:
    print("ERROR: No article found in DB")
    sys.exit(1)

article_id, keyword, html = row
print(f"Testing article ID={article_id}, keyword='{keyword}', length={len(html)} chars")

from engines.humanize.pipeline import run_humanize_pipeline

def on_progress(step, current, total, detail, extra):
    print(f"  [{step}] {detail}")

result = run_humanize_pipeline(
    html=html,
    keyword=keyword,
    tone="natural",
    style="conversational",
    on_progress=on_progress,
    skip_judge=True,
    max_sections=3,  # limit to 3 sections for speed
)

print(f"\n=== RESULT ===")
print(f"Success:    {result['success']}")
print(f"Score:      {result['original_score']} → {result['final_score']}")
print(f"Sections:   {result['sections_processed']}/{result['sections_total']}")
print(f"Tokens:     {result['tokens_used']}")
print(f"Time:       {result['elapsed_seconds']}s")
if not result['success']:
    print(f"Error:      {result.get('details', {})}")
EOF
```

Expected output:
- Progress lines showing `[humanizing] [N%] Section N/N: ...`
- `[section_done] ✓ <heading> — ai_router (N tok)` for each section
- Final: `Success: True`, `Score: 90 → <new_score>`, `Sections: 3/3`

If Ollama calls succeed, you'll see `[Humanize] ollama succeeded (N chars)` in server logs.

- [ ] **Step 6: Revert the test chain to production default**

In `engines/content_generation_engine.py`, restore line ~560:
```python
    humanize:     StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_deepseek",    "gemini_paid"))
```

- [ ] **Step 7: Run full test suite to confirm no regressions**

```bash
cd /root/ANNASEOv1 && python -m pytest tests/test_humanize_pipeline.py -v
```

Expected: All **3 tests PASS**

- [ ] **Step 8: Commit the revert**

```bash
cd /root/ANNASEOv1 && git add engines/content_generation_engine.py
git commit -m "chore: revert test-only ollama-only humanize chain to production default

Production chain restored to or_gemini_flash → or_deepseek → gemini_paid.
Users select Ollama via the step dropdown in the UI when desired."
```

---

## Summary

After all tasks complete:

| Fix | File | Status |
|-----|------|--------|
| Skip gate removed | `engines/humanize/pipeline.py` | ✅ |
| Ollama context raised 2048→4096 | `core/ai_config.py` | ✅ |
| Prompt trimming for Ollama | `engines/content_generation_engine.py` | ✅ |
| Tests covering all three | `tests/test_humanize_pipeline.py` | ✅ |

To use Ollama in production: select **Ollama** in the Step 9 (Humanize) provider dropdown in the UI. The pipeline will automatically use the trimmed prompt and 4096-token context.

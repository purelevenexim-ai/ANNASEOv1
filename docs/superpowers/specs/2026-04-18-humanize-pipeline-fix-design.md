# Humanize Pipeline Fix — Design Spec
**Date:** 2026-04-18  
**Status:** Approved  
**Scope:** Option A — Targeted patch

---

## Problem

Step 9 (Humanize) skips humanization on the majority of AI-drafted articles due to three independent bugs:

1. **False-positive skip gate** — `pipeline.py` returns early when the rule-based auditor scores `≥ 90/100`. The auditor only checks 7 heuristic patterns (forbidden words, generic transitions, formulaic headings, sentence uniformity, paragraph uniformity, tautological conclusion, vocabulary diversity). AI content written to avoid these 7 patterns scores 90+ and never gets humanized, even though it was just written by an LLM.

2. **Ollama absent from default humanize chain** — The code default chain for Step 9 is `or_gemini_flash → or_deepseek → gemini_paid`. Ollama is not in the default, but users can add it via the step-provider dropdowns in the UI. Bug 2 is **not fixed by a code change** — it is user-configurable. Changes 2 and 3 below take effect whenever a user selects Ollama in the chain.

3. **Ollama context too small** — `OLLAMA_MAX_CTX = 2048` tokens. A humanize prompt (instructions + section HTML) uses ~1000–1500 tokens, leaving only 500–1000 tokens for the output. Sections of 200–500 words need ~300–700 output tokens — the window is too tight and responses get silently truncated.

---

## Solution — Three Targeted Changes

### Change 1: Remove the skip gate (`pipeline.py`)

**Remove** the entire early-return block (currently lines ~105–117):

```python
# REMOVE THIS:
if original_score >= 90 and section_index is None:
    progress("done", 0, 0, f"Content already scores {original_score}/100 — no humanization needed")
    return { ... }
```

The auditor score becomes informational only — shown in logs, written to step details, but never used to gate execution. Every fresh AI draft runs through the full section-by-section humanization pass.

**Note:** A prior bugfix already added `"judge_score": None` to this return dict. That entire block is removed, making the prior fix moot (it will be removed with the block).

**Why safe:** If a section genuinely needs no changes, the LLM returns it unchanged. The cost of over-running is one Ollama call per section; the cost of under-running is unhumanized articles reaching production.

### Change 2: Raise Ollama context (`ai_config.py`)

```python
# BEFORE:
OLLAMA_MAX_CTX = 2048  # max context tokens — do not exceed (memory limit)

# AFTER:
OLLAMA_MAX_CTX = 4096  # raised after proxy memory verification (see Testing Plan)
```

Update the adjacent comment accordingly.

**Scope clarification:** Three other call sites in the codebase hardcode `num_ctx: 2048` as integer literals and do NOT read `AICfg.OLLAMA_MAX_CTX`:
- `content_generation_engine.py` — `_ollama_sync()` at ~line 5574 (used for non-humanize steps)
- `ruflo_20phase_engine.py` — at ~line 454
- `services/seo_brief_generator.py` — at ~line 395

These are **out of scope** for this fix. Only the humanize adapter (`_HumanizeRouterAdapter`) reads `AICfg.OLLAMA_MAX_CTX` at runtime, so Change 2 correctly fixes the context for humanization without touching other call sites.

**Token arithmetic (4096 context):**
- Input (prompt trimmed per Change 3): ~800–1000 tokens
- Output budget: ~3000–3200 tokens ≈ 2250–2400 words (at ~0.75 words/token)
- Adequate for sections of 200–500 words

**Prerequisite:** Verify the Ollama proxy server (`172.235.16.165:8080`) can handle 4096 context without OOM errors before deploying. Check `/health` endpoint for memory status, or run a test request with `num_ctx=4096` and confirm no 503 circuit-breaker response. Add this to the Testing Plan below.

### Change 3: Trim prompt in Ollama adapter (`content_generation_engine.py`)

Inside `_HumanizeRouterAdapter.call_with_tokens()`, **inside the `elif provider in ("ollama",):` branch only** (currently ~line 3503), create a trimmed copy of `prompt` before building `_payload`. Do not modify `prompt` at the top of `call_with_tokens()` — that would degrade Gemini/OpenRouter calls which benefit from full context.

Pseudocode:

```python
elif provider in ("ollama",):
    # Trim prompt for Ollama's smaller context window
    _ollama_prompt = prompt
    # 1. Strip ARTICLE OUTLINE block (small models ignore multi-section context)
    _outline_start = _ollama_prompt.find("ARTICLE OUTLINE")
    _rules_start = _ollama_prompt.find("━━━ CRITICAL RULES ━━━")
    if 0 < _outline_start < _rules_start:
        _ollama_prompt = _ollama_prompt[:_outline_start] + _ollama_prompt[_rules_start:]
    # 2. Truncate section content from 4000 → 2000 chars
    _sec_marker = "SECTION TO REWRITE:"
    _sec_idx = _ollama_prompt.find(_sec_marker)
    if _sec_idx >= 0:
        _head = _ollama_prompt[:_sec_idx + len(_sec_marker)]
        _body = _ollama_prompt[_sec_idx + len(_sec_marker):]
        _ollama_prompt = _head + _body[:2000] + "\n\nReturn ONLY the rewritten HTML."
    # Use _ollama_prompt (not prompt) in _payload below
    _payload = { "model": ..., "prompt": _ollama_prompt, ... }
```

**Why `━━━ CRITICAL RULES ━━━` as the anchor:** The `_MASTER_REWRITE_PROMPT` in `humanizer.py` places the outline block directly before the `━━━ CRITICAL RULES ━━━` delimiter. Using this unique anchor is more robust than counting `\n\n` occurrences.

Token savings:
- Removing outline: ~100 tokens (20 headings × 5 tokens)
- Truncating section 4000→2000 chars: ~300–500 tokens (English prose ~4–5 chars/token)
- Net: prompt drops from ~1200–1500 to ~800–1000 tokens

---

## Testing Plan

1. **Verify proxy memory** — call `GET http://172.235.16.165:8080/health` and confirm `circuit_breaker.open == false` and no memory-degraded status. Make one test request with `num_ctx=4096` to confirm no 503.

2. **Configure test chain** — change the default humanize chain in `content_generation_engine.py` (the `humanize` field of `_DEFAULT_ROUTING`) from `StepAIConfig("or_gemini_flash", "or_deepseek", "gemini_paid")` to `StepAIConfig("ollama", "skip", "skip")`. **This is temporary — revert after testing.**

3. **Trigger humanization** on an existing article with known AI-drafted content.

4. **Verify in logs:**
   - No `"Content already scores X/100 — no humanization needed"` skip
   - `[Humanize] ollama succeeded (N chars)` for each section
   - Final AI score differs from original score

5. **Inspect humanized HTML** to confirm readable quality.

6. **Revert test chain** — restore `StepAIConfig("or_gemini_flash", "or_deepseek", "gemini_paid")` as the code default. In production, Ollama is user-selectable via the step dropdown.

---

## Files Changed

| File | Change |
|------|--------|
| `engines/humanize/pipeline.py` | Remove `original_score >= 90` early-return block entirely |
| `core/ai_config.py` | `OLLAMA_MAX_CTX: 2048 → 4096`; update adjacent comment |
| `engines/content_generation_engine.py` | Trim prompt inside Ollama adapter branch; temporarily change default humanize chain for testing |

**Out of scope:** The three hardcoded `num_ctx: 2048` literals in `_ollama_sync()`, `ruflo_20phase_engine.py`, and `seo_brief_generator.py` — these are separate steps unrelated to humanization and will be addressed separately if needed.

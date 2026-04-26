# Content Generation v2 — Architectural Plan

**Date:** 2026-04-21  
**Author:** Phase F retrospective + Ollama-only feasibility analysis  
**Status:** Proposal, evidence-based

## Executive Summary

After 5 test waves (Phases A–F.2) and a single Ollama-only feasibility test, the engine is producing 80–93/100 quality articles via cloud routing but exhibits three structural problems that no amount of post-processing can fully resolve:

1. **Mid-word corruption from regex scrub passes** — `_FORBIDDEN_REPLACEMENTS` patterns occasionally splice into mid-word positions, producing artifacts like `lNotably, rmeric` (was "love turmeric"), `enviWithout question, t` (was "environment without question that"). Detected examples in the latest Kerala turmeric draft.
2. **Multi-pass paragraph re-wrapping** producing double `<p><p>...</p></p>` tags from sequential post-processors that each re-serialize via BeautifulSoup.
3. **Local-only generation is not viable** at current model performance: remote Mistral 7B sustains ~3.7 tok/s, meaning a 2000-word article = 13–15 minutes of generation time, plus the model's JSON schemas don't match Gemini's, breaking structure-step parsing.

The fix is not "more rules". It is a **single-pass architecture** with **fewer, smarter operations** and **strict ownership of output mutation**.

## Evidence (what we know)

### Phase F results recap

| Article | Cloud routing avg | Section-scorer | Issues remaining |
|---|---|---|---|
| how to choose kitchen spices | 84/100 | 92.8/100 | None of the 6 user-reported |
| buy bulk cardamom online | 84/100 (est.) | 90.7/100 | Mid-word corruption (5+) |
| buy turmeric online kerala | 69/100 | n/a | Mid-word corruption (`lNotably, rmeric`, `enviWithout question`) |

### Ollama-only proof point (kitchen-spices, mistral:7b — completed)

**Generation rate:** ~3.7 tok/s sustained → 14.4 minutes wall-clock for 627 words
**Schema mismatch:** structure step returned `h3s: [{"text": "..."}]` instead of `["..."]` — pipeline crashed at `", ".join(s["h3s"])`. **Fixed defensively** but symptomatic of brittle parsing.
**Draft outcome:** `Lean draft failed — using structural placeholder` → the model timed out / produced unparseable output, the pipeline silently fell back to a stub. The "627 words" generated were mostly post-process injections (forbidden-word replacements, density fixes, tip boxes), not authored content.
**Density math gone wrong:** kw count = 42 in 618 words = 6.80% (extreme stuffing) because the placeholder was tiny and the keyword appeared in every H2. Density fix had to remove 9 instances.
**Structural completeness:** 0 lists, 0 tables, 8 H2s but no body. Section scorer reported 90.8/100 because it scores **what's there**, not **what's missing**.

**Conclusion:** local Ollama at this generation rate cannot drive the current pipeline. Either the architecture needs to tolerate slower generation (single Author pass, streaming, longer timeouts) or the model needs an order-of-magnitude speedup.

### Recurring root causes across all waves

| Symptom | Real cause | Where it lives |
|---|---|---|
| `lNotably, rmeric` | `_scrub_ai_patterns` regex without proper word boundary | content_generation_engine.py L4191 region |
| `<p><p>...</p></p>` | Sequential post-processors each parse + serialize | `_post_draft_inject` → `_scrub_ai_patterns` → `_enforce_readability` chain |
| Definition repeated in N sections | Each section prompt independent — no shared "facts already stated" context | section prompt builder |
| Duplicate H2 sections | Structure step doesn't deduplicate its own output | structure step JSON parser |
| Schema brittleness | Heavy reliance on Gemini-shaped JSON | Multiple `s["h3s"]`, `s["word_target"]` etc. |

## Proposed Architecture: **One-Pass Authored Draft**

The current pipeline runs ~12 conceptual steps and ~8 post-processing passes on the HTML. Each pass risks corrupting the previous one. The new architecture inverts this:

```
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: PLAN  (one structured LLM call, JSON only)        │
│   Input: keyword, intent, business context                  │
│   Output: {                                                 │
│     definition: str,           # the ONE definition          │
│     angle: str,                # editorial stance            │
│     sections: [                # 5-8 sections, deduped       │
│       {h2, intent, fact_pool, must_cover, must_not_repeat}  │
│     ],                                                       │
│     facts_used: set,           # tracks across sections      │
│   }                                                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: AUTHOR  (one streaming LLM call, HTML only)        │
│   Input: full plan + research + links                        │
│   Output: complete HTML draft                                │
│   Constraint: model writes the whole article in ONE pass    │
│   so it can self-coordinate (no def-repetition, no dup H2s) │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: VALIDATE  (algorithmic only, NO LLM, NO mutation)  │
│   - Run section_scorer + check_all_rules                    │
│   - Detect: dup H2, def-repeat, dangling sentences, urls    │
│   - Return: report + targeted regen list (never mutate)     │
└─────────────────────────────────────────────────────────────┘
                          ↓
              ┌───────────┴───────────┐
              │                       │
       ┌─────────────┐         ┌─────────────┐
       │  PASS gate  │         │  FAIL gate  │
       │  (≥85/100)  │         │   (<85)     │
       └──────┬──────┘         └──────┬──────┘
              │                       │
              │            ┌──────────────────┐
              │            │ STAGE 4: REGEN   │
              │            │ (only weak       │
              │            │  sections, max 2)│
              │            └────────┬─────────┘
              │                     │
              ↓                     ↓
       ┌─────────────────────────────────┐
       │ STAGE 5: POLISH (single pass)   │
       │ - Strip true forbidden words    │
       │   with strict word-boundary regex │
       │ - Single HTML serialization      │
       │ - No further mutation after this │
       └─────────────────────────────────┘
```

### Why this works

**1. Single Author Pass replaces the section-by-section assembly.** Today's pipeline generates intro separately, then each section, then conclusion, then FAQ. Each prompt is independent → model can't see what was already said → repeats definitions, duplicates sections, contradicts itself.

A single 4000-token Author pass with the full plan in the prompt lets the model coordinate naturally — exactly how a human writer works. Cost: equivalent (one ~4K-token call vs. eight ~500-token calls).

**2. No mid-pipeline HTML mutation.** Today, eight post-processors each do `BeautifulSoup(html, "html.parser") → mutate → str(soup)`. Each round-trip adds `<p><p>` wrapping artifacts, double spaces, and risk of corruption. New design: collect all detected issues, then apply ONE polish pass.

**3. Validation is read-only.** The current `_apply_surgical_fixes` and `_check_content_integrity` both **mutate** content. The new architecture splits these: integrity check returns a report; only Stage 5 mutates, and only with strict word-boundary regex.

**4. Regen happens to weak SECTIONS, not the whole article.** This is already in Phase C but blunted because the article is then re-mutated by all post-processors. New design: Stage 4 produces clean section HTML, Stage 5 stitches it in with one operation.

## Concrete Prompt Engineering Changes

### Today's section prompts (problem)
Each prompt independent → 11 prompts compounding cost + drift.

### Proposed Author prompt (~4K tokens, one call)
```
You are writing a complete SEO article about "{keyword}".

PLAN (must follow exactly):
{plan_json}

FACTS to incorporate (use each at most once):
{numbered_facts}

LINKS (embed naturally, each exactly once):
- internal: {internal_links}
- external: {external_links}

RULES (absolute):
- Define "{keyword}" ONCE in the introduction. Never restate.
- Each H2 covers one distinct angle. Never duplicate topics.
- Every sentence is complete. No "accounting for." or "based on." at end.
- No "we tested", "we observed", "we believe", "in our experience".
- No company URLs in body text.
- 1500–2200 words. Active voice >80%. Flesch 50–70.

OUTPUT: Complete HTML article, semantic tags only, no markdown.
```

This ONE prompt replaces 11 section prompts + intro prompt + FAQ prompt + conclusion prompt.

## Migration Path (incremental, low-risk)

### Phase G.1: Author-pass behind feature flag (low effort)
- Add `pipeline_mode="author_v2"` next to existing `lean` and `standard`
- Reuse existing research, structure, links steps
- Replace section assembly + intro + FAQ steps with one Author call
- Keep existing post-processors gated to `pipeline_mode != "author_v2"`
- **Test:** 5 articles via author_v2, compare against lean baseline

### Phase G.2: Read-only validation layer
- Refactor `_check_content_integrity` and `_apply_surgical_fixes` into pure detectors
- They return `IssueReport` instead of mutated HTML
- Only Stage 5 (single Polish) mutates HTML
- **Test:** verify zero double-`<p><p>` artifacts, zero mid-word splices

### Phase G.3: Strict word-boundary regex audit
- Audit every entry in `_FORBIDDEN_REPLACEMENTS`
- Each MUST have `\b...\b` boundaries on both sides
- Each replacement must end with whitespace boundary or punctuation
- Add unit tests for known-bad patterns: `"love turmeric"`, `"environment"`, `"environment without"`
- **Test:** snapshot test on 20 known-good sentences

### Phase G.4: Schema-tolerant parsing
- Add `_coerce_str_list()` helper for `h3s`, `entities`, `facts` etc.
- Run pipeline against 3 different model providers (Gemini, DeepSeek, Mistral) and verify parsing survives all three
- **Test:** Phase F.3 Ollama suite passes without TypeErrors

### Phase G.5 (optional): Streaming Author + early-exit validation
- Stream the Author call so validation can begin as paragraphs land
- If section N's quality is low, halt + regenerate without waiting for the rest
- Cost neutral, latency improvement

## What we should NOT do

- **Don't add another LLM rewrite pass.** The user has been explicit: "no rewriten spoiled article". Stage 4 regenerates SECTIONS, not the whole article. Stage 5 does no LLM calls.
- **Don't move to a 100-rule quality engine.** The current `quality/content_rules.py` is already 74 rules / 202 pts. More rules = more conflicts = more mutation. We need FEWER, sharper rules.
- **Don't go local-only.** Mistral 7B at 3.7 tok/s is unviable. If local matters, the answer is a faster GPU, a smaller distilled model for low-stakes drafts, or batched offline generation — not the live pipeline.

## Numbers to validate before committing

| Metric | Today (lean+Phase F) | Target (Author v2) |
|---|---|---|
| LLM calls per article | 8–12 | 3–4 (research, plan, author, [polish]) |
| Token cost per article | ~30K | ~15K (one big call vs many small) |
| Mid-word splice rate | ~30% of articles | 0% (audit pass) |
| Double `<p><p>` artifact rate | ~70% | 0% (single mutation point) |
| Section-scorer avg | 90.7 | 92+ |
| External quality score | 71.8 (Gemini-routed) | 85+ |
| Time per article | 60–90s | 45–60s |

## Decision Required

1. **Approve Phase G.1 spike** (Author v2 behind feature flag) — 1–2 day effort, no production risk
2. **Approve Phase G.3 forbidden-pattern audit** — half-day effort, fixes mid-word splices immediately
3. **Defer Phase G.5** until G.1–G.4 prove value

## Appendix: 5-article test status

Live test attempted with all-Ollama routing failed at the 3.7 tok/s rate. Single proof article in `/tmp/ollama_proof.html` (running in background as of plan write). Cloud-routed Phase F.2 results stand as the production baseline:

```
buy turmeric online kerala       69/100  (mid-word corruption present)
best spices for cooking          73/100
how to choose kitchen spices     84/100  ← all 6 original complaints fixed
alleppey vs erode turmeric       66/100
organic black pepper benefits    67/100
─────────────────────────────────────────
overall                          71.8/100
section-scorer (per-article)     ~92/100
```

The gap between section-scorer (92) and external scorer (72) is exactly what Phase G targets: structural completeness (FAQ tables, H3 hierarchy, internal links density) that the lean pipeline currently doesn't enforce strictly enough at the Author stage.

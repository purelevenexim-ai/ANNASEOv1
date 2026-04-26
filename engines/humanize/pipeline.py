"""
Humanization pipeline — orchestrates the full editorial flow:
1. Audit for AI signals
2. Lock SEO anchors
3. Split into sections
4. Structural deduplication (if >20 sections)
5. Humanize each section (anti-AI, anti-keyword-stuffing, human voice)
6. Reassemble
7. Editorial validation (fake authority, keyword stuffing, robotic phrasing)
8. Keyword density normalization (rule-based, no LLM)
9. Editorial rewrite pass (full-article LLM pass for human-grade quality)
10. Validate SEO preservation
11. Rule-based score
12. LLM Judge (optional — skipped by default in pipeline S9)
13. Targeted fix pass (if judge < 78)
14. Final score

Supports streaming progress via a queue and pause/stop controls.
"""
import json
import logging
import re
import time
from typing import Dict, Optional, Callable

from engines.humanize.splitter import split_into_sections, reassemble_sections, depattern_sections
from engines.humanize.auditor import analyze_ai_signals
from engines.humanize.semantic_lock import extract_seo_anchors, validate_seo_preservation
from engines.humanize.humanizer import humanize_section, humanize_targeted
from engines.humanize.restructurer import deduplicate_and_collapse, RESTRUCTURE_THRESHOLD
from engines.humanize.judge import llm_judge
from engines.humanize.editorial import (
    detect_redundancy,
    validate_editorial,
    editorial_rewrite,
    normalize_keyword_density,
)
from engines.humanize.interrupter import apply_cognitive_interruptions, apply_burstiness_fix
from engines.humanize.story_injector import inject_micro_story
from engines.humanize.humanization_v2 import apply_humanization_v2, V2Config
from engines.humanize.humanization_bandit import _bandit

log = logging.getLogger("annaseo.humanize")

DETECTOR_TARGET_AI_SCORE = 40


def _infer_persona(keyword: str) -> str:
    """Return a lightweight persona string based on keyword category.

    Deterministic — no LLM call. Covers common SEO niches; returns empty
    string for anything that doesn't match (safe fallback).
    """
    kw = keyword.lower()
    # Check more specific categories first to avoid false matches
    if any(w in kw for w in ["dog", "cat", "pet", "puppy", "kitten", "vet", "animal"]):
        return "a veterinary technician and long-time pet owner"
    if any(w in kw for w in ["recipe", "cook", "food", "meal", "dish", "bake", "kitchen"]):
        return "a home cook who has made this dozens of times and knows the real shortcuts"
    if any(w in kw for w in ["supplement", "vitamin", "protein", "fitness", "workout", "gym"]):
        return "a certified personal trainer who recommends evidence-based products"
    if any(w in kw for w in ["spice", "herb", "seasoning", "pepper", "cardamom", "cinnamon", "clove", "turmeric"]):
        return "a culinary professional with 15 years sourcing and tasting specialty ingredients"
    if any(w in kw for w in ["hair", "skin", "beauty", "serum", "moistur", "shampoo", "conditioner"]):
        return "a licensed esthetician who tests products on real clients"
    if any(w in kw for w in ["seo", "marketing", "content", "blog", "keyword", "traffic", "ranking"]):
        return "a digital marketing strategist who has run hundreds of SEO campaigns"
    if any(w in kw for w in ["invest", "stock", "finance", "budget", "saving", "money", "crypto"]):
        return "a certified financial planner who writes for a general audience"
    if any(w in kw for w in ["travel", "hotel", "flight", "destination", "trip", "vacation"]):
        return "a frequent traveler who books 20+ trips a year and shares honest reviews"
    return ""


def run_humanize_pipeline(
    html: str,
    keyword: str,
    tone: str = "natural",
    style: str = "conversational",
    persona: str = "",
    on_progress: Optional[Callable] = None,
    section_index: Optional[int] = None,
    control: Optional[Dict] = None,
    ai_router=None,
    skip_judge: bool = False,
    max_sections: int = 0,
) -> Dict:
    """Run the full humanization pipeline.

    Args:
        html: Original article HTML
        keyword: Target SEO keyword
        tone: natural|conversational|expert|narrative|direct
        style: conversational|academic|journalistic|casual
        persona: Optional writer persona description
        on_progress: Callback(step, current, total, detail, extra)
        section_index: If set, only humanize this one section (0-indexed)
        control: Dict with 'paused' and 'stopped' booleans for external control

    Returns: {
        success, humanized_html, original_score, final_score,
        sections_processed, sections_total, details, tokens_used, error
    }
    """
    start_time = time.time()
    total_tokens = 0
    ctl = control or {}

    # Reset Gemini quota flag at start of each pipeline run (may have reset overnight)
    try:
        from core.ai_config import AIRouter
        AIRouter._gemini_quota_exhausted = False
    except Exception:
        pass

    def _check_stopped():
        return ctl.get("stopped", False)

    def _wait_if_paused():
        while ctl.get("paused", False) and not ctl.get("stopped", False):
            time.sleep(0.5)

    def progress(step, current=0, total=0, detail="", **extra):
        if on_progress:
            on_progress(step, current, total, detail, extra)

    # ── Step 1: Audit original for AI signals ─────────────────────────────
    progress("analyzing", 0, 1, "Scanning for AI patterns...")
    original_audit = analyze_ai_signals(html)
    original_score = original_audit["score"]
    progress("analyzed", 1, 1,
             f"AI score: {original_score}/100 — {len(original_audit.get('signals', []))} signals found",
             score=original_score,
             ai_score=original_audit.get("ai_score"),
             risk_level=original_audit.get("risk_level"),
             signals=original_audit.get("signals", []))

    if _check_stopped():
        return _stopped_result(html, original_score, start_time)

    # ── Step 2: Extract SEO anchors to protect ────────────────────────────
    progress("locking", 0, 1, "Locking SEO elements...")
    seo_anchors = extract_seo_anchors(html, keyword)
    progress("locked", 1, 1,
             f"Locked {len(seo_anchors['links'])} links, keyword density {seo_anchors['kw_density']}%")

    # ── Step 3: Split into sections ───────────────────────────────────────
    sections = split_into_sections(html)
    total_sections = len(sections)
    progress("split", 0, 0, f"Split into {total_sections} sections")

    if total_sections == 0:
        progress("error", 0, 0, "No sections found in content")
        return {
            "success": False, "humanized_html": html,
            "original_score": original_score, "final_score": original_score,
            "sections_processed": 0, "sections_total": 0,
            "details": {"error": "No sections found in content"},
            "tokens_used": 0, "elapsed_seconds": round(time.time() - start_time, 1),
        }

    # ── Step 4: Structural deduplication (only for over-segmented articles) ──
    if section_index is None and total_sections > RESTRUCTURE_THRESHOLD:
        progress("restructuring", 0, 1,
                 f"Merging duplicate sections ({total_sections} → target 6–15)...")
        sections = deduplicate_and_collapse(sections, keyword, ai_router=ai_router)
        new_total = len(sections)
        progress("restructured", 1, 1,
                 f"Structure collapsed: {total_sections} → {new_total} sections",
                 original_count=total_sections, new_count=new_total)
        total_sections = new_total

    if _check_stopped():
        return _stopped_result(html, original_score, start_time)

    # Filter to specific section if requested
    if section_index is not None:
        if 0 <= section_index < total_sections:
            target_sections = [sections[section_index]]
        else:
            progress("error", 0, 0, f"Section index {section_index} out of range")
            return {
                "success": False, "humanized_html": html,
                "original_score": original_score, "final_score": original_score,
                "sections_processed": 0, "sections_total": total_sections,
                "details": {"error": f"Section index {section_index} out of range (0-{total_sections-1})"},
                "tokens_used": 0, "elapsed_seconds": round(time.time() - start_time, 1),
            }
    else:
        target_sections = sections

    # Cap sections if max_sections is set (prevents very long articles from timing out)
    if max_sections and max_sections > 0 and len(target_sections) > max_sections:
        progress("capped", 0, 0,
                 f"Capping at {max_sections} sections (article has {len(target_sections)} sections)")
        target_sections = target_sections[:max_sections]

    # Build article outline (all headings) for global context injection into each section rewrite
    article_outline = [s.get("heading", "") for s in sections if s.get("heading")]

    # Auto-infer persona when caller did not supply one
    if not persona:
        persona = _infer_persona(keyword)
        if persona:
            log.debug("Auto-persona inferred: %s", persona[:80])

    # Select V2 config via bandit BEFORE section loop (one config per article run)
    try:
        _v2_config, _v2_arm_idx = _bandit.select()
    except Exception:
        _v2_config, _v2_arm_idx = V2Config(), 1  # safe fallback: balanced arm

    # ── Step 5: Humanize each section ─────────────────────────────────────
    ai_signal_texts = [s["detail"] for s in original_audit.get("signals", [])]
    sections_processed = 0
    section_details = []
    _section_format_cycle = ["", "qa", "bullets", "story", "comparison", "stat_lead"]

    for i, section in enumerate(target_sections):
        if _check_stopped():
            progress("stopped", i, len(target_sections), "Stopped by user")
            break

        _wait_if_paused()

        sec_idx = section["index"]
        heading = section.get("heading", "") or "Introduction"
        pct = round((i / len(target_sections)) * 100)
        progress("humanizing", i + 1, len(target_sections),
                 f"[{pct}%] Section {i+1}/{len(target_sections)}: {heading[:50]}",
                 section_index=sec_idx, heading=heading)

        # Find links in this section
        section_links = [l for l in seo_anchors["links"] if l["full"] in section["content"]]

        # Rotate section format hints — skip format for first section (intro) and last section (conclusion)
        _is_edge = (i == 0 or i == len(target_sections) - 1)
        section_fmt = "" if _is_edge else _section_format_cycle[i % len(_section_format_cycle)]

        result = humanize_section(
            section["content"],
            keyword,
            tone=tone,
            style=style,
            persona=persona,
            ai_signals=ai_signal_texts,
            links=section_links,
            outline=article_outline,
            ai_router=ai_router,
            section_format=section_fmt,
        )

        provider = result.get("provider", "none")
        tokens = result.get("tokens", 0)

        if result["success"]:
            sections[sec_idx]["content"] = result["html"]
            sections_processed += 1
            total_tokens += tokens
            progress("section_done", i + 1, len(target_sections),
                     f"✓ {heading[:40]} — {provider} ({tokens} tok)",
                     section_index=sec_idx, heading=heading, provider=provider, tokens=tokens)
        else:
            err = result.get("error", "Unknown error")
            # Check for rate limit signals
            is_rate_limit = any(w in err.lower() for w in ["rate limit", "429", "quota", "too many"])
            progress("section_failed", i + 1, len(target_sections),
                     f"✗ {heading[:40]} — {err[:80]}",
                     section_index=sec_idx, heading=heading, error=err,
                     rate_limited=is_rate_limit, provider=provider)
            section_details.append({
                "index": sec_idx, "heading": heading,
                "success": False, "error": err, "rate_limited": is_rate_limit,
            })
            continue

        section_details.append({
            "index": sec_idx, "heading": heading,
            "success": True, "provider": provider, "tokens": tokens,
        })

    if _check_stopped():
        return _stopped_result(html, original_score, start_time, sections_processed, total_sections)

    # ── Step 5: Reassemble ────────────────────────────────────────────────
    try:
        sections = depattern_sections(sections)
        progress("depattern_sections", 1, 1, "✓ Section openings and cadence de-patterned")
    except Exception as e:
        log.warning("Section de-patterning failed (non-fatal): %s", e)
    progress("assembling", 0, 1, "Reassembling article...")
    humanized_html = reassemble_sections(sections)

    # ── Step 5.1: Burstiness fix (deterministic, no LLM) ─────────────────
    if not _check_stopped():
        try:
            humanized_html = apply_burstiness_fix(humanized_html)
            progress("burstiness", 1, 1, "✓ Sentence burstiness applied")
        except Exception as e:
            log.warning("Burstiness fix failed (non-fatal): %s", e)

    # ── Step 5.2: Cognitive interruptions + micro-story (optional) ───────
    if not _check_stopped() and section_index is None:
        try:
            humanized_html = apply_cognitive_interruptions(humanized_html)
            progress("interruptions", 1, 1, "✓ Cognitive interruptions injected")
        except Exception as e:
            log.warning("Interruption injection failed (non-fatal): %s", e)
        try:
            humanized_html = inject_micro_story(humanized_html, keyword, ai_router=ai_router)
            progress("micro_story", 1, 1, "✓ Micro-story pass done")
        except Exception as e:
            log.warning("Micro-story injection failed (non-fatal): %s", e)

    # ── Step 5.3: Humanization V2 — structure chaos / noise / persona drift ──
    if not _check_stopped():
        try:
            humanized_html = apply_humanization_v2(
                humanized_html,
                config=_v2_config,
                detector_metrics=original_audit.get("detector_metrics", {}),
            )
            arm_name = _v2_config.__class__.__name__
            try:
                from engines.humanize.humanization_bandit import _ARM_NAMES
                arm_name = _ARM_NAMES[_v2_arm_idx]
            except Exception:
                pass
            progress(
                "v2_mutation",
                1,
                1,
                f"✓ Humanization V2 applied (arm: {arm_name})",
                original_ai_score=original_audit.get("ai_score"),
            )
        except Exception as e:
            log.warning("Humanization V2 failed (non-fatal): %s", e)

    # ── Step 5.5: Keyword density normalization (rule-based, no LLM) ────
    if not _check_stopped():
        _wait_if_paused()
        progress("editorial_kw", 0, 1, "Normalizing keyword density...")
        try:
            humanized_html = normalize_keyword_density(
                humanized_html, keyword, max_density=1.8, min_density=0.8, min_occurrences=3
            )
            progress("editorial_kw", 1, 1, "✓ Keyword density normalized")
        except Exception as e:
            log.warning("Keyword density normalization failed: %s", e)
            progress("editorial_kw", 1, 1, f"⚠ KW density pass skipped: {str(e)[:60]}")

    # ── Step 5.7: Editorial validation (rule-based, no LLM) ─────────────
    editorial_val = {}
    if not _check_stopped():
        _wait_if_paused()
        progress("editorial_validate", 0, 1, "Running editorial validation...")
        try:
            editorial_val = validate_editorial(humanized_html, keyword)
            ed_score = editorial_val.get("score", 100)
            ed_issues = editorial_val.get("issues", [])
            issue_summary = "; ".join(
                f"{cat}: {len(items)}" for cat, items in ed_issues.items() if items
            ) if isinstance(ed_issues, dict) else str(len(ed_issues))
            progress("editorial_validate", 1, 1,
                     f"Editorial score: {ed_score}/100 — {issue_summary}"[:120])
        except Exception as e:
            log.warning("Editorial validation failed: %s", e)
            editorial_val = {"score": 100, "issues": {}}
            progress("editorial_validate", 1, 1, f"⚠ Editorial validation skipped: {str(e)[:60]}")

    # ── Step 5.9: Editorial rewrite (LLM pass — if score < 70) ──────────
    EDITORIAL_THRESHOLD = 70
    ed_score = editorial_val.get("score", 100)
    if (ed_score < EDITORIAL_THRESHOLD
            and section_index is None
            and not _check_stopped()):
        _wait_if_paused()
        progress("editorial_rewrite", 0, 1,
                 f"Editorial rewrite needed (score {ed_score}/100)...")
        try:
            rewrite_result = editorial_rewrite(
                humanized_html, keyword, editorial_val, ai_router=ai_router
            )
            if rewrite_result.get("success"):
                humanized_html = rewrite_result["html"]
                total_tokens += rewrite_result.get("tokens", 0)
                progress("editorial_rewrite", 1, 1,
                         f"✓ Editorial rewrite complete ({rewrite_result.get('tokens', 0)} tok)")
            else:
                progress("editorial_rewrite", 1, 1,
                         f"⚠ Editorial rewrite failed: {rewrite_result.get('error', '')[:60]}")
        except Exception as e:
            log.warning("Editorial rewrite failed: %s", e)
            progress("editorial_rewrite", 1, 1, f"⚠ Editorial rewrite skipped: {str(e)[:60]}")

    # ── Step 6: Validate SEO preservation ─────────────────────────────────
    progress("validating", 0, 1, "Checking SEO preservation...")
    seo_check = validate_seo_preservation(seo_anchors, humanized_html)
    if seo_check["passed"]:
        progress("validated", 1, 1, "✓ SEO elements preserved")
    else:
        progress("seo_warning", 1, 1,
                 f"⚠ SEO issues: {'; '.join(seo_check.get('issues', [])[:3])}",
                 issues=seo_check.get("issues", []))
        # If keyword density dropped, restore it
        if any("keyword density" in (iss or "").lower() for iss in seo_check.get("issues", [])):
            try:
                humanized_html = normalize_keyword_density(
                    humanized_html, keyword, max_density=1.8, min_density=0.8, min_occurrences=3
                )
                log.info("Post-SEO-validation: re-applied keyword density floor")
            except Exception as e:
                log.warning("Post-validation density fix failed: %s", e)

    # ── Step 7: Rule-based score (fast heuristic) ────────────────────────
    progress("scoring", 0, 1, "Computing rule-based score...")
    final_audit = analyze_ai_signals(humanized_html)
    rule_score = final_audit["score"]

    # ── Step 8: LLM Judge — multi-dimensional quality scoring ─────────────
    judge_result = {}
    judge_score = 0
    if not skip_judge and section_index is None and not _check_stopped():
        progress("judging", 0, 1, "Running quality judge (LLM evaluation)...")
        judge_result = llm_judge(humanized_html, keyword, ai_router=ai_router)
        judge_score = judge_result.get("total", 0)
        judge_issues = judge_result.get("issues", [])
        judge_worst = judge_result.get("worst_sections", [])
        judge_breakdown = judge_result.get("breakdown", {})

        if judge_result.get("error"):
            progress("judged", 1, 1,
                     f"Judge failed ({judge_result['error'][:50]}) — using rule score {rule_score}/100",
                     score=rule_score, error=judge_result["error"])
            judge_score = rule_score
        else:
            issues_preview = "; ".join(judge_issues[:2])
            progress("judged", 1, 1,
                     f"Judge score: {judge_score}/100 — {issues_preview[:80]}",
                     score=judge_score, breakdown=judge_breakdown,
                     issues=judge_issues, worst_sections=judge_worst)

        # ── Step 9: Targeted fix pass (only if quality below threshold) ───
        JUDGE_TARGET = 78
        if judge_score and judge_score < JUDGE_TARGET and judge_issues and not _check_stopped():
            _wait_if_paused()

            # Find the sections that match the worst-section headings
            worst_set = {h.lower().strip() for h in judge_worst}
            sections_to_fix = [
                s for s in sections
                if s.get("heading", "").lower().strip() in worst_set
            ]
            # Also fix first section if no worst sections matched (always improve intro)
            if not sections_to_fix and sections:
                sections_to_fix = sections[:1]
            # Cap at 5 sections max
            sections_to_fix = sections_to_fix[:5]

            fixed_count = 0
            progress("iterating", 0, len(sections_to_fix),
                     f"Targeted fix on {len(sections_to_fix)} weakest sections...")

            for fix_i, fix_sec in enumerate(sections_to_fix):
                if _check_stopped():
                    break
                _wait_if_paused()

                fix_result = humanize_targeted(
                    fix_sec["content"],
                    keyword,
                    issues=judge_issues,
                    tone=tone,
                    ai_router=ai_router,
                )
                if fix_result["success"]:
                    # Update section content in place
                    sections[fix_sec["index"]]["content"] = fix_result["html"]
                    total_tokens += fix_result.get("tokens", 0)
                    fixed_count += 1
                    progress("iterating", fix_i + 1, len(sections_to_fix),
                             f"Fixed: {fix_sec.get('heading', '')[:40]}",
                             section_index=fix_sec["index"])

            if fixed_count > 0:
                try:
                    sections = depattern_sections(sections)
                except Exception as e:
                    log.warning("Post-fix section de-patterning failed (non-fatal): %s", e)
                # Reassemble with fixes applied
                humanized_html = reassemble_sections(sections)
                progress("iterated", fixed_count, len(sections_to_fix),
                         f"Fixed {fixed_count} sections — reassembling",
                         fixed=fixed_count)

    # ── Step 10: Final keyword density safety net ─────────────────────────
    try:
        _final_text = re.sub(r"<[^>]+>", " ", humanized_html)
        _final_wc = len(_final_text.split())
        _final_kw_count = _final_text.lower().count(keyword.lower())
        _final_kw_words = len(keyword.split())
        _final_density = (_final_kw_count * _final_kw_words / _final_wc * 100) if _final_wc > 100 else 999
        if _final_density < 0.8:
            humanized_html = normalize_keyword_density(
                humanized_html, keyword, max_density=1.8, min_density=0.8, min_occurrences=3
            )
            log.info(f"Final density safety net: restored from {_final_density:.2f}%")
    except Exception as e:
        log.warning("Final density check failed: %s", e)

    # ── Step 11: Final reassembly score ──────────────────────────────────
    final_audit = analyze_ai_signals(humanized_html)
    final_score = final_audit["score"]

    # ── Step 11.5: Detector validation gate — one stronger safe pass if needed ──
    final_ai_score = final_audit.get("ai_score", 100)
    detector_retry_applied = False
    if (
        section_index is None
        and not _check_stopped()
        and final_ai_score > DETECTOR_TARGET_AI_SCORE
    ):
        _wait_if_paused()
        progress(
            "detector_validate",
            0,
            1,
            f"Detector score {final_ai_score}/100 above target {DETECTOR_TARGET_AI_SCORE} — applying stronger safe pass...",
            ai_score=final_ai_score,
            target=DETECTOR_TARGET_AI_SCORE,
        )
        retry_config = V2Config(
            structure_chaos=min(0.55, _v2_config.structure_chaos + 0.12),
            cognitive_noise=min(0.40, _v2_config.cognitive_noise + 0.10),
            persona_drift=min(0.40, _v2_config.persona_drift + 0.08),
            micro_human_signals=min(0.30, getattr(_v2_config, "micro_human_signals", 0.18) + 0.08),
            seed=(getattr(_v2_config, "seed", 0) or 0) + 101,
        )
        try:
            candidate_html = apply_humanization_v2(
                humanized_html,
                config=retry_config,
                detector_metrics=final_audit.get("detector_metrics", {}),
            )
            try:
                candidate_html = normalize_keyword_density(
                    candidate_html, keyword, max_density=1.8, min_density=0.8, min_occurrences=3
                )
            except Exception as e:
                log.warning("Detector retry density normalization failed: %s", e)

            candidate_audit = analyze_ai_signals(candidate_html)
            candidate_ai_score = candidate_audit.get("ai_score", final_ai_score)
            candidate_rule_score = candidate_audit["score"]

            # Accept only genuine detector improvement. Small rule-score drops are tolerable
            # if the detector score improves materially.
            if candidate_ai_score < final_ai_score and candidate_rule_score >= max(final_score - 8, 0):
                humanized_html = candidate_html
                final_audit = candidate_audit
                final_score = candidate_rule_score
                final_ai_score = candidate_ai_score
                detector_retry_applied = True
                progress(
                    "detector_validate",
                    1,
                    1,
                    f"✓ Detector safe pass accepted ({final_ai_score}/100)",
                    ai_score=final_ai_score,
                )
            else:
                progress(
                    "detector_validate",
                    1,
                    1,
                    f"No detector gain from safe pass ({candidate_ai_score}/100) — keeping prior version",
                    ai_score=final_ai_score,
                )
        except Exception as e:
            log.warning("Detector validation pass failed (non-fatal): %s", e)
            progress("detector_validate", 1, 1, f"⚠ Detector pass skipped: {str(e)[:60]}")

    # Update bandit with the final AI-detection score (only for full article runs)
    if section_index is None:
        try:
            _bandit.update(_v2_arm_idx, final_score)
        except Exception as e:
            log.debug("Bandit update failed (non-fatal): %s", e)

    elapsed = round(time.time() - start_time, 1)
    improvement = final_score - original_score
    progress("done", sections_processed, len(target_sections),
             f"Score: {original_score} → {final_score} (+{improvement}) | Judge: {judge_score}/100 | {elapsed}s",
             original_score=original_score, final_score=final_score,
             original_ai_score=original_audit.get("ai_score"),
             final_ai_score=final_audit.get("ai_score"),
             detector_retry_applied=detector_retry_applied,
             judge_score=judge_score, elapsed=elapsed)

    return {
        "success": True,
        "humanized_html": humanized_html,
        "original_score": original_score,
        "final_score": final_score,
        "judge_score": judge_score,
        "sections_processed": sections_processed,
        "sections_total": total_sections,
        "seo_preserved": seo_check["passed"],
        "seo_issues": seo_check.get("issues", []),
        "details": {
            "sections": section_details,
            "original_signals": original_audit.get("signals", []),
            "final_signals": final_audit.get("signals", []),
            "original_detector_metrics": original_audit.get("detector_metrics", {}),
            "final_detector_metrics": final_audit.get("detector_metrics", {}),
            "original_detector_scores": original_audit.get("detector_scores", {}),
            "final_detector_scores": final_audit.get("detector_scores", {}),
            "detector_retry_applied": detector_retry_applied,
            "judge": judge_result,
        },
        "tokens_used": total_tokens,
        "elapsed_seconds": elapsed,
    }


def _stopped_result(html, original_score, start_time, processed=0, total=0):
    return {
        "success": False,
        "humanized_html": html,
        "original_score": original_score,
        "final_score": original_score,
        "sections_processed": processed,
        "sections_total": total,
        "details": {"stopped": True},
        "tokens_used": 0,
        "elapsed_seconds": round(time.time() - start_time, 1),
    }

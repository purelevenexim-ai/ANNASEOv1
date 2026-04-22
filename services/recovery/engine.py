"""
Recovery Engine — orchestrates section-level issue detection,
classification, and targeted AI fixes.

Flow:
1. Split article HTML into sections (by H2)
2. Detect issues in each section
3. For failing sections: classify → build prompt → AI fix → re-validate
4. Reassemble fixed sections into full article
5. Max 2 passes per section, max N total AI calls

This replaces the old _step12_quality_loop (5-pass full-article rewrite)
and _step10_redevelop (single-pass full-article polish) with precision
section-level surgery.
"""
import re
import logging
from typing import Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .detector import detect_section_issues, score_section
from .classifier import classify_issues
from .strategy import build_recovery_prompt
from .fixer import fix_section

log = logging.getLogger(__name__)


@dataclass
class SectionResult:
    """Result for a single section after recovery."""
    index: int
    heading: str
    original_html: str
    final_html: str
    original_score: int
    final_score: int
    issues_found: List[Dict] = field(default_factory=list)
    issues_remaining: List[Dict] = field(default_factory=list)
    passes: int = 0
    fixed: bool = False


@dataclass
class RecoveryResult:
    """Full recovery result for the article."""
    sections: List[SectionResult] = field(default_factory=list)
    total_ai_calls: int = 0
    sections_fixed: int = 0
    sections_skipped: int = 0
    article_html: str = ""


def split_by_h2(html: str) -> List[Tuple[str, str]]:
    """Split article HTML into sections by H2 boundaries.

    Returns list of (heading_text, section_html) tuples.
    The first section (before any H2) is labeled "intro".
    """
    # Find all H2 positions
    h2_pattern = re.compile(r"(<h2[^>]*>.*?</h2>)", re.I | re.S)
    h2_matches = list(h2_pattern.finditer(html))

    if not h2_matches:
        return [("full_article", html)]

    sections = []

    # Intro (before first H2)
    intro = html[: h2_matches[0].start()].strip()
    if intro:
        sections.append(("intro", intro))

    # Each H2 section
    for i, match in enumerate(h2_matches):
        start = match.start()
        end = h2_matches[i + 1].start() if i + 1 < len(h2_matches) else len(html)
        section_html = html[start:end].strip()

        # Extract heading text
        heading = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        sections.append((heading, section_html))

    return sections


def reassemble_sections(sections: List[Tuple[str, str]]) -> str:
    """Reassemble sections into full article HTML."""
    return "\n\n".join(html for _, html in sections)


class RecoveryEngine:
    """Orchestrates section-level recovery.

    Usage:
        engine = RecoveryEngine(
            keyword="best coffee makers",
            quality_rules=blueprint.quality_rules,
            generation_rules=blueprint.generation_rules,
            recovery_rules=blueprint.recovery_rules,
        )
        result = await engine.recover(article_html, ai_call=pipeline._call_ai_raw)
    """

    def __init__(
        self,
        keyword: str,
        quality_rules: Dict,
        generation_rules: Dict,
        recovery_rules: Dict,
    ):
        self.keyword = keyword
        self.quality_rules = quality_rules
        self.generation_rules = generation_rules
        self.recovery_rules = recovery_rules

        self.max_passes = recovery_rules.get("max_passes", 2)
        self.max_total_calls = recovery_rules.get("max_total_recovery_calls", 6)
        self.score_threshold = recovery_rules.get("section_score_threshold", 70)

    async def recover(
        self,
        article_html: str,
        ai_call: Callable,
        *,
        on_progress: Optional[Callable] = None,
        contract_failures_by_heading: Optional[Dict[str, List[Dict]]] = None,
    ) -> RecoveryResult:
        """Run section-level recovery on the article.

        Args:
            article_html: Full article HTML
            ai_call: Async callable(prompt, temperature, max_tokens) -> str
            on_progress: Optional callback(section_idx, total, detail)
            contract_failures_by_heading: Pre-computed contract failures from validate
                step, keyed by section heading text. Each value is a list of failure
                dicts with 'type' and 'detail' keys. These are injected as additional
                issues for the relevant sections so recovery can fix them directly.

        Returns:
            RecoveryResult with fixed article and per-section details
        """
        sections = split_by_h2(article_html)
        result = RecoveryResult()
        total_calls = 0
        cfbh = contract_failures_by_heading or {}

        # Build "other sections" text for repetition detection
        all_text = re.sub(r"<[^>]+>", " ", article_html)

        for idx, (heading, section_html) in enumerate(sections):
            # Build "other sections" text (exclude current section)
            section_text = re.sub(r"<[^>]+>", " ", section_html)
            other_text = all_text.replace(section_text, "", 1)

            # Detect issues
            issues = detect_section_issues(
                section_html,
                self.keyword,
                self.quality_rules,
                self.generation_rules,
                other_sections_text=other_text,
            )

            # Inject pre-computed contract failures from the validate step.
            # These are high-priority structural gaps (missing table, buyer guidance,
            # pros/cons, etc.) that detect_section_issues may not surface directly.
            contract_extra = cfbh.get(heading, [])
            for cf in contract_extra:
                issues.append({
                    "type": cf.get("type", "contract_failure"),
                    "detail": cf.get("detail", ""),
                    "severity": "high",
                    "source": "contract",
                })

            section_score = score_section(issues)

            sec_result = SectionResult(
                index=idx,
                heading=heading,
                original_html=section_html,
                final_html=section_html,
                original_score=section_score,
                final_score=section_score,
                issues_found=issues,
            )

            # Skip if section passes threshold
            if section_score >= self.score_threshold:
                sec_result.issues_remaining = []
                result.sections.append(sec_result)
                result.sections_skipped += 1
                if on_progress:
                    on_progress(idx, len(sections), f"Section '{heading}' OK (score {section_score})")
                continue

            # Skip intro sections (usually short by design)
            if heading == "intro" and len(section_text.split()) < 80:
                result.sections.append(sec_result)
                result.sections_skipped += 1
                continue

            # Check call budget
            if total_calls >= self.max_total_calls:
                log.info(f"Recovery: call budget exhausted ({total_calls}/{self.max_total_calls})")
                sec_result.issues_remaining = issues
                result.sections.append(sec_result)
                continue

            # Recovery passes
            current_html = section_html
            current_issues = issues

            for pass_num in range(1, self.max_passes + 1):
                if total_calls >= self.max_total_calls:
                    break

                # Classify issues
                classified = classify_issues(current_issues, self.recovery_rules)

                # Build targeted prompt
                prompt = build_recovery_prompt(
                    section_html=current_html,
                    section_heading=heading,
                    classified_issues=classified,
                    keyword=self.keyword,
                    generation_rules=self.generation_rules,
                )

                # Call AI
                if on_progress:
                    on_progress(idx, len(sections),
                                f"Fixing '{heading}' (pass {pass_num}, {len(classified)} issues)")

                fixed = await fix_section(
                    prompt=prompt,
                    ai_call=ai_call,
                    original_html=current_html,
                )
                total_calls += 1

                if not fixed:
                    log.info(f"Recovery: section '{heading}' pass {pass_num} — fix rejected")
                    continue

                # Re-detect issues on fixed version
                fixed_text = re.sub(r"<[^>]+>", " ", fixed)
                other_text_updated = all_text.replace(section_text, fixed_text, 1)
                new_issues = detect_section_issues(
                    fixed,
                    self.keyword,
                    self.quality_rules,
                    self.generation_rules,
                    other_sections_text=other_text_updated,
                )
                new_score = score_section(new_issues)

                # Accept only if improvement
                if new_score > section_score or len(new_issues) < len(current_issues):
                    current_html = fixed
                    current_issues = new_issues
                    section_score = new_score
                    log.info(f"Recovery: section '{heading}' improved to {new_score} (pass {pass_num})")

                    if not new_issues or new_score >= self.score_threshold:
                        break
                else:
                    log.info(f"Recovery: section '{heading}' pass {pass_num} — no improvement ({new_score} ≤ {sec_result.original_score})")

            sec_result.final_html = current_html
            sec_result.final_score = section_score
            sec_result.issues_remaining = current_issues
            sec_result.passes = min(pass_num, self.max_passes) if current_html != section_html else 0
            sec_result.fixed = current_html != section_html

            if sec_result.fixed:
                result.sections_fixed += 1
                # Update all_text with the fixed section for subsequent repetition checks
                all_text = all_text.replace(
                    re.sub(r"<[^>]+>", " ", section_html),
                    re.sub(r"<[^>]+>", " ", current_html),
                    1,
                )

            result.sections.append(sec_result)

        # Reassemble
        final_sections = [(sr.heading, sr.final_html) for sr in result.sections]
        result.article_html = reassemble_sections(final_sections)
        result.total_ai_calls = total_calls

        log.info(
            f"Recovery complete: {result.sections_fixed} fixed, "
            f"{result.sections_skipped} skipped, {total_calls} AI calls"
        )

        return result

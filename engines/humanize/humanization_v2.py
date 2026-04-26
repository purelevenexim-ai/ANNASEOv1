"""
Humanization V2 — post-processing layer that changes the statistical shape of text.

Runs AFTER section humanization + reassembly, BEFORE editorial/keyword steps.
Deterministic via seed. Non-fatal — always returns original html on any error.

Layers:
  1. Structure Chaos  — split overlong paragraphs at sentence boundaries
  2. Cognitive Noise  — insert short pivot phrases between paragraphs
  3. Persona Drift    — prefix body paragraphs with rotating opener phrases

Design rules:
  * No sentence truncation — all original words preserved
  * Noise is a SEPARATE <p> element, never appended inside an existing paragraph
  * Safe to run zero or more times (idempotent if probabilities are low)
"""
import re
import random
import logging
from dataclasses import dataclass, field
from typing import List, Tuple

log = logging.getLogger("annaseo.humanize.v2")

# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class V2Config:
    structure_chaos: float = 0.30   # probability a long paragraph gets split
    cognitive_noise: float = 0.20   # probability a noise phrase is inserted after a paragraph
    persona_drift: float = 0.25     # fraction of body paragraphs prefixed with an opener
    micro_human_signals: float = 0.18  # probability of conversational/opinion inserts
    seed: int = 0


# ── Phrase banks ─────────────────────────────────────────────────────────────

_NOISE_PHRASES: List[str] = [
    "That\u2019s where it gets complicated.",
    "Most people miss this part.",
    "And this matters more than it seems.",
    "Not obvious at first — but important.",
    "Here\u2019s where it gets interesting.",
    "Worth slowing down here.",
    "This is the bit that actually matters.",
    "There\u2019s a real trade-off here.",
    "Honestly, this surprised me too.",
    "The detail most guides gloss over.",
    "Here\u2019s the catch though.",
    "This changes how you think about everything else.",
]

_PERSONA_BANKS: List[List[str]] = [
    # practical / direct
    ["In practice,", "From experience,", "The short answer is:", "Real talk —", "Practically speaking,"],
    # narrative / story
    ["Here\u2019s what actually happens:", "Think about it this way:", "Picture it like this:", "Here\u2019s a real example:", "The way I see it,"],
    # analytical / expert
    ["The key thing to understand is", "Worth noting here:", "The underlying reason is", "What the data actually shows:", "From a technical standpoint,"],
]

_MICRO_HUMAN_PHRASES: List[str] = [
    "Here\u2019s the thing:",
    "Most people don\u2019t notice this at first.",
    "In practice, this is where the difference shows up.",
    "That sounds simple, but it changes the decision quite a bit.",
    "If you compare them side by side, this becomes obvious fast.",
    "This is usually the point where buyers start reading more carefully.",
    "I\u2019d pay attention to this part.",
    "That\u2019s the part that tends to get oversimplified.",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

_BLOCK_TAGS_RE = re.compile(r'<(ul|ol|table|pre|code|blockquote|figure)[^>]*>', re.I)


def _paragraph_word_count(inner_html: str) -> int:
    return len(re.sub(r'<[^>]+>', ' ', inner_html).split())


def _find_split_point(text: str) -> int:
    """Find the best sentence-boundary split index in the middle third of `text`.

    Returns character index of the space after a sentence-ending period, or -1.
    All original words are preserved — no truncation.
    """
    n = len(text)
    lo = n // 3
    hi = 2 * n // 3
    # Walk forward from lo looking for '. ' followed by an uppercase letter
    for i in range(lo, hi):
        if text[i] == '.' and i + 2 < n and text[i + 1] == ' ' and text[i + 2].isupper():
            return i + 2  # split AFTER '. '
    # Fallback: any '. ' gap in the middle third
    for i in range(lo, hi):
        if text[i] == '.' and i + 1 < n and text[i + 1] == ' ':
            return i + 2
    return -1


# ── Layer 1: Structure Chaos ─────────────────────────────────────────────────

def inject_structure_chaos(html: str, config: V2Config, rng: random.Random) -> str:
    """Split overlong paragraphs at sentence boundaries in their middle third.

    Safe: every original word is preserved.  No truncation ever happens.
    Skips paragraphs that contain block-level child elements (ul, ol, table, etc.)
    """
    para_re = re.compile(r'(<p[^>]*>)(.*?)(</p>)', re.DOTALL | re.IGNORECASE)
    matches = list(para_re.finditer(html))
    if not matches:
        return html

    # Work from end → start so earlier string positions stay valid
    for m in reversed(matches):
        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)

        # Skip if paragraph contains nested block elements
        if _BLOCK_TAGS_RE.search(inner):
            continue

        wc = _paragraph_word_count(inner)
        if wc < 60:
            continue

        if rng.random() >= config.structure_chaos:
            continue

        # Extract plain text for split-point detection
        plain = re.sub(r'<[^>]+>', '', inner)
        split_idx = _find_split_point(plain)
        if split_idx < 0:
            continue

        # Map plain-text split index back to HTML inner string
        # Strategy: count non-tag chars until we reach split_idx, then cut
        char_count = 0
        html_split = None
        in_tag = False
        for ci, ch in enumerate(inner):
            if ch == '<':
                in_tag = True
            elif ch == '>':
                in_tag = False
                continue
            if not in_tag:
                char_count += 1
                if char_count == split_idx:
                    html_split = ci + 1  # cut after this character in the HTML string
                    break

        if html_split is None:
            continue

        part1 = inner[:html_split].rstrip()
        part2 = inner[html_split:].lstrip()
        if not part2.strip():
            continue

        replacement = f"{open_tag}{part1}{close_tag}\n{open_tag}{part2}{close_tag}"
        html = html[:m.start()] + replacement + html[m.end():]

    return html


# ── Layer 2: Cognitive Noise ─────────────────────────────────────────────────

def inject_cognitive_noise(html: str, config: V2Config, rng: random.Random) -> str:
    """Insert short pivot phrases as separate <p><em>…</em></p> elements BETWEEN paragraphs.

    Noise is never appended inside an existing paragraph — it's a new element added
    after the closing </p> tag. Skips first and last two paragraphs.
    """
    # Collect all </p> end positions
    close_positions: List[Tuple[int, int]] = []
    for m in re.finditer(r'</p>', html, re.IGNORECASE):
        close_positions.append((m.start(), m.end()))

    if len(close_positions) <= 4:
        return html

    # Exclude first and last two paragraph closings
    eligible = close_positions[1:-2]

    phrases = _NOISE_PHRASES[:]
    rng.shuffle(phrases)
    phrase_iter = iter(phrases)

    # Process from end → start
    for start, end in reversed(eligible):
        if rng.random() >= config.cognitive_noise:
            continue
        try:
            phrase = next(phrase_iter)
        except StopIteration:
            break
        insertion = f"\n<p><em>{phrase}</em></p>"
        html = html[:end] + insertion + html[end:]

    return html


# ── Layer 3: Persona Drift ────────────────────────────────────────────────────

def inject_persona_drift(html: str, config: V2Config, rng: random.Random) -> str:
    """Prefix a fraction of body <p> tags with rotating persona opener phrases.

    Uses 3 rotating phrase banks so successive sections feel like slightly
    different voices. Skips first and last two paragraphs.
    """
    para_re = re.compile(r'(<p(?:\s[^>]*)?>)', re.IGNORECASE)
    matches = list(para_re.finditer(html))

    if len(matches) <= 4:
        return html

    eligible = matches[1:-2]  # skip first and last two
    total_eligible = len(eligible)
    target_count = max(1, round(total_eligible * config.persona_drift))

    # Evenly space the chosen paragraphs
    step = max(1, total_eligible // target_count)
    chosen_indices = list(range(0, total_eligible, step))[:target_count]

    bank_cycle = list(range(len(_PERSONA_BANKS)))
    rng.shuffle(bank_cycle)

    # Process from end → start
    for ci, ei in reversed(list(enumerate(chosen_indices))):
        m = eligible[ei]
        bank_idx = bank_cycle[ci % len(bank_cycle)]
        bank = _PERSONA_BANKS[bank_idx]
        phrase = rng.choice(bank)
        # Insert the phrase just after the opening <p> tag
        insert_pos = m.end()
        html = html[:insert_pos] + phrase + " " + html[insert_pos:]

    return html


# ── Layer 4: Micro Human Signals ────────────────────────────────────────────

def inject_micro_human_signals(
    html: str,
    config: V2Config,
    rng: random.Random,
    detector_metrics: dict | None = None,
) -> str:
    """Insert sparse conversational/opinion phrases into body paragraphs.

    This is deliberately conservative. It only activates when detector metrics
    suggest the article is overly uniform or lacks human stance signals.
    """
    detector_metrics = detector_metrics or {}
    opener_ratio = float(detector_metrics.get("top_sentence_opener_ratio", 0.0) or 0.0)
    hedge_count = int(detector_metrics.get("hedge_opinion_count", 0) or 0)
    first_person_count = int(detector_metrics.get("first_person_count", 0) or 0)

    should_activate = opener_ratio > 0.10 or hedge_count < 5 or first_person_count < 2
    if not should_activate:
        return html

    para_re = re.compile(r'(<p[^>]*>)(.*?)(</p>)', re.DOTALL | re.IGNORECASE)
    matches = list(para_re.finditer(html))
    if len(matches) <= 4:
        return html

    eligible = []
    for m in matches[1:-2]:
        inner = m.group(2)
        plain = re.sub(r'<[^>]+>', ' ', inner).strip()
        if len(plain.split()) < 28:
            continue
        # Skip if the paragraph already looks conversational.
        if re.match(r'\s*(Here\u2019s|Here\'s|In practice|Most people|If you|I\u2019d|I\'d)', plain, re.I):
            continue
        eligible.append(m)

    if not eligible:
        return html

    target_count = max(1, round(len(eligible) * config.micro_human_signals))
    chosen = rng.sample(eligible, k=min(target_count, len(eligible)))

    for m in reversed(chosen):
        phrase = rng.choice(_MICRO_HUMAN_PHRASES)
        insert_pos = m.end(1)
        html = html[:insert_pos] + phrase + " " + html[insert_pos:]

    return html


# ── Orchestrator ──────────────────────────────────────────────────────────────

def apply_humanization_v2(
    html: str,
    config: "V2Config | None" = None,
    seed: int = 0,
    detector_metrics: dict | None = None,
) -> str:
    """Apply all Humanization V2 layers in sequence.

    Safe to call on any HTML string.  Returns the original html unchanged if any
    unhandled exception occurs.

    Args:
        html:   Article HTML (post-section-humanization, pre-editorial)
        config: V2Config instance; defaults to V2Config() if None
        seed:   RNG seed for reproducibility (overrides config.seed if non-zero)

    Returns:
        Mutated HTML string with structural and stylistic variation added.
    """
    if not html or not html.strip():
        return html

    if config is None:
        config = V2Config()

    effective_seed = seed if seed != 0 else config.seed
    rng = random.Random(effective_seed)

    try:
        html = inject_structure_chaos(html, config, rng)
    except Exception as e:  # pragma: no cover
        log.warning("V2 structure_chaos failed (non-fatal): %s", e)

    try:
        html = inject_cognitive_noise(html, config, rng)
    except Exception as e:  # pragma: no cover
        log.warning("V2 cognitive_noise failed (non-fatal): %s", e)

    try:
        html = inject_persona_drift(html, config, rng)
    except Exception as e:  # pragma: no cover
        log.warning("V2 persona_drift failed (non-fatal): %s", e)

    try:
        html = inject_micro_human_signals(html, config, rng, detector_metrics=detector_metrics)
    except Exception as e:  # pragma: no cover
        log.warning("V2 micro_human_signals failed (non-fatal): %s", e)

    return html

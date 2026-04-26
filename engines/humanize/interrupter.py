"""
Cognitive interruption injector — breaks smooth AI flow with pivot sentences.
Deterministic — no LLM call.
"""
import re
import random
from typing import List

_INTERRUPTIONS: List[str] = [
    "That\u2019s where it gets interesting.",
    "Here\u2019s the thing though.",
    "And this is the part most guides skip.",
    "Worth pausing here for a second.",
    "This matters more than it sounds.",
    "Small detail \u2014 but it matters.",
    "Not obvious at first. But important.",
    "There\u2019s a catch here.",
    "This changes things.",
    "Let\u2019s back up for a moment.",
    "Honestly?",
    "Here\u2019s the real issue.",
    "And this is where most people get it wrong.",
    "Pay attention to this part.",
    "Actually \u2014 this surprised me.",
]
_MIN_PARA_WORDS = 40
_DENSITY_PER_1000W = 1.5


def apply_cognitive_interruptions(html: str, seed: int = 0) -> str:
    """Insert short pivot sentences to break smooth AI-style flow.

    Targets long paragraphs only, spacing interruptions evenly.
    Deterministic via seed.
    """
    rng = random.Random(seed)
    text_only = re.sub(r"<[^>]+>", " ", html)
    word_count = len(text_only.split())
    if word_count < 300:
        return html

    target_count = max(2, round(word_count / 1000 * _DENSITY_PER_1000W))

    # Collect positions of paragraphs that are long enough to interrupt
    eligible: List[int] = []
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE):
        pw = len(re.sub(r"<[^>]+>", " ", m.group(1)).split())
        if pw >= _MIN_PARA_WORDS:
            eligible.append(m.start())

    # Avoid very first and very last paragraph
    if len(eligible) > 3:
        eligible = eligible[2:-1]
    elif len(eligible) > 1:
        eligible = eligible[1:-1]
    else:
        return html

    if not eligible:
        return html

    # Spread chosen positions evenly
    step = max(1, len(eligible) // target_count)
    chosen = sorted(
        [eligible[i] for i in range(0, len(eligible), step)][:target_count],
        reverse=True,  # modify from the end so earlier positions stay valid
    )

    phrases = _INTERRUPTIONS[:]
    rng.shuffle(phrases)
    phrase_iter = iter(phrases)

    for pos in chosen:
        try:
            phrase = next(phrase_iter)
        except StopIteration:
            break
        html = html[:pos] + f"<p><em>{phrase}</em></p>\n" + html[pos:]

    return html


def apply_burstiness_fix(html: str) -> str:
    """Split uniformly-long paragraphs to create sentence-length variety (burstiness).

    Only splits paragraphs that are significantly above median length.
    Deterministic — no LLM call.
    """
    para_pat = re.compile(r"(<p[^>]*>)(.*?)(</p>)", re.DOTALL | re.IGNORECASE)
    paragraphs = para_pat.findall(html)
    if not paragraphs:
        return html

    lengths = [len(re.sub(r"<[^>]+>", " ", p[1]).split()) for p in paragraphs]
    sorted_lengths = sorted(lengths)
    mid = len(sorted_lengths) // 2
    median_len = sorted_lengths[mid] if sorted_lengths else 40
    threshold = max(80, int(median_len * 1.8))

    for open_tag, content, close_tag in paragraphs:
        words = re.sub(r"<[^>]+>", " ", content).split()
        wc = len(words)
        if wc <= threshold:
            continue

        # Try to split at a conjunction first
        split_idx = None
        search_start = max(20, wc // 3)
        search_end = min(wc - 5, wc * 2 // 3)
        for idx in range(search_start, search_end):
            if words[idx].lower().rstrip(",:;") in {
                "but", "and", "so", "yet", "however", "although",
                "while", "because", "since", "though",
            }:
                split_idx = idx
                break

        # Fall back to a mid-sentence comma split
        if split_idx is None:
            mid_w = wc // 2
            for idx in range(max(0, mid_w - 8), min(wc, mid_w + 8)):
                if words[idx].endswith(","):
                    split_idx = idx + 1
                    break

        if split_idx is None or split_idx >= wc - 5:
            continue

        part1 = " ".join(words[:split_idx]).rstrip(",")
        part2 = " ".join(words[split_idx:])
        if len(part2.split()) < 10:
            continue

        original_full = open_tag + content + close_tag
        replacement = f"{open_tag}{part1}.{close_tag}\n{open_tag}{part2}{close_tag}"
        html = html.replace(original_full, replacement, 1)

    return html

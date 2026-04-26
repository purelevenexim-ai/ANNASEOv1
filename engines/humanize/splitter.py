"""
Content splitter — breaks HTML articles into semantic sections for
section-by-section humanization without losing structure.
"""
import re
from typing import List, Dict


_SECTION_DEPATTERN_PREFIXES = [
    "Here is the practical angle:",
    "The useful detail is this:",
    "This is where it changes:",
    "What matters most here is simple:",
    "A more grounded way to look at it is this:",
]


def _strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text)


def _find_middle_sentence_split(text: str) -> int:
    n = len(text)
    if n < 120:
        return -1
    lo = n // 3
    hi = (2 * n) // 3
    for i in range(lo, hi):
        if text[i] in ".!?" and i + 1 < n and text[i + 1] == " ":
            return i + 2
    return -1


def _split_html_at_plain_index(inner_html: str, plain_index: int) -> tuple[str, str] | tuple[None, None]:
    char_count = 0
    in_tag = False
    html_split = None
    for idx, ch in enumerate(inner_html):
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
            continue
        if not in_tag:
            char_count += 1
            if char_count == plain_index:
                html_split = idx + 1
                break
    if html_split is None:
        return None, None
    return inner_html[:html_split].rstrip(), inner_html[html_split:].lstrip()


def split_into_sections(html: str) -> List[Dict]:
    """Split HTML content into sections by headings.

    Returns list of dicts: {index, heading, tag, content, word_count}
    """
    # Split on h1-h3 headings
    pattern = r'(<h[1-3][^>]*>.*?</h[1-3]>)'
    parts = re.split(pattern, html, flags=re.I | re.S)

    sections = []
    current_heading = ""
    current_tag = ""
    current_content = ""

    for part in parts:
        heading_match = re.match(r'<(h[1-3])[^>]*>(.*?)</\1>', part, re.I | re.S)
        if heading_match:
            # Save previous section
            if current_content.strip():
                word_count = len(re.sub(r'<[^>]+>', '', current_content).split())
                sections.append({
                    "index": len(sections),
                    "heading": current_heading,
                    "tag": current_tag,
                    "content": current_content.strip(),
                    "word_count": word_count,
                })
            current_heading = re.sub(r'<[^>]+>', '', heading_match.group(2)).strip()
            current_tag = heading_match.group(1).lower()
            current_content = part  # include the heading in the section
        else:
            current_content += part

    # Last section
    if current_content.strip():
        word_count = len(re.sub(r'<[^>]+>', '', current_content).split())
        sections.append({
            "index": len(sections),
            "heading": current_heading,
            "tag": current_tag,
            "content": current_content.strip(),
            "word_count": word_count,
        })

    return sections


def reassemble_sections(sections: List[Dict]) -> str:
    """Reassemble sections back into a single HTML string."""
    return "\n\n".join(s["content"] for s in sections)


def depattern_sections(sections: List[Dict]) -> List[Dict]:
    """Reduce repetitive section openings and overly uniform first-paragraph cadence.

    Safe, deterministic, and HTML-preserving.
    """
    if len(sections) < 3:
        return sections

    first_words = []
    first_para_lengths = []
    first_para_meta = []
    para_re = re.compile(r'(<p[^>]*>)(.*?)(</p>)', re.I | re.S)

    for section in sections:
        content = section.get("content", "")
        body = re.sub(r'^\s*<h[1-3][^>]*>.*?</h[1-3]>\s*', '', content, count=1, flags=re.I | re.S)
        match = para_re.search(body)
        if not match:
            first_words.append("")
            first_para_lengths.append(0)
            first_para_meta.append(None)
            continue
        plain = _strip_html(match.group(2)).strip()
        words = plain.split()
        first_words.append(words[0].lower() if words else "")
        first_para_lengths.append(len(words))
        first_para_meta.append({"plain": plain, "inner": match.group(2)})

    opener_counts = {}
    for word in first_words:
        if word:
            opener_counts[word] = opener_counts.get(word, 0) + 1

    for idx, section in enumerate(sections):
        content = section.get("content", "")
        body_match = re.match(r'^(\s*<h[1-3][^>]*>.*?</h[1-3]>\s*)(.*)$', content, re.I | re.S)
        if body_match:
            heading_html, body_html = body_match.group(1), body_match.group(2)
        else:
            heading_html, body_html = "", content

        para_match = para_re.search(body_html)
        if not para_match:
            continue

        open_tag, inner_html, close_tag = para_match.group(1), para_match.group(2), para_match.group(3)
        plain = _strip_html(inner_html).strip()
        words = plain.split()
        if not words:
            continue

        first_word = words[0].lower()
        repeated_opener = opener_counts.get(first_word, 0) > 1
        consecutive_repeat = idx > 0 and first_word and first_word == first_words[idx - 1]
        if (repeated_opener or consecutive_repeat) and not re.match(r'^(Here|This|What|A|In)\b', plain, re.I):
            prefix = _SECTION_DEPATTERN_PREFIXES[idx % len(_SECTION_DEPATTERN_PREFIXES)]
            new_inner = f"{prefix} {inner_html.lstrip()}"
            body_html = body_html[:para_match.start()] + f"{open_tag}{new_inner}{close_tag}" + body_html[para_match.end():]

            # refresh match data after mutation for cadence split
            para_match = para_re.search(body_html)
            open_tag, inner_html, close_tag = para_match.group(1), para_match.group(2), para_match.group(3)
            plain = _strip_html(inner_html).strip()
            words = plain.split()

        similar_length_count = sum(1 for value in first_para_lengths if value and abs(value - len(words)) <= 6)
        if len(words) >= 60 and similar_length_count >= 3:
            split_idx = _find_middle_sentence_split(plain)
            if split_idx > 0:
                part1, part2 = _split_html_at_plain_index(inner_html, split_idx)
                if part1 and part2:
                    replacement = f"{open_tag}{part1}{close_tag}\n{open_tag}{part2}{close_tag}"
                    body_html = body_html[:para_match.start()] + replacement + body_html[para_match.end():]

        section["content"] = f"{heading_html}{body_html}".strip()
        section["word_count"] = len(_strip_html(section["content"]).split())

    return sections

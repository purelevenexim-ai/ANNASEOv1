"""
Content splitter — breaks HTML articles into semantic sections for
section-by-section humanization without losing structure.
"""
import re
from typing import List, Dict


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

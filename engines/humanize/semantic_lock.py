"""
Semantic lock — preserves SEO-critical elements during humanization.
Extracts and re-injects: keyword placements, internal links, schema markup,
heading hierarchy, and meta-relevant phrases.
"""
import re
from typing import Dict, List, Tuple


def extract_seo_anchors(html: str, keyword: str) -> Dict:
    """Extract all SEO-critical elements that must survive humanization."""

    # Internal links (preserve href + anchor text)
    links = []
    for m in re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        links.append({"href": m.group(1), "text": re.sub(r'<[^>]+>', '', m.group(2)).strip(), "full": m.group(0)})

    # Headings (preserve hierarchy)
    headings = []
    for m in re.finditer(r'<(h[1-6])[^>]*>(.*?)</\1>', html, re.I | re.S):
        headings.append({"tag": m.group(1), "text": re.sub(r'<[^>]+>', '', m.group(2)).strip()})

    # Keyword in first 100 words (must remain)
    text = re.sub(r'<[^>]+>', ' ', html)
    first_100 = ' '.join(text.split()[:100])
    kw_in_intro = keyword.lower() in first_100.lower()

    # Keyword density
    text_lower = text.lower()
    kw_count = text_lower.count(keyword.lower())
    word_count = len(text.split())
    kw_density = (kw_count / word_count * 100) if word_count > 0 else 0

    # Schema/structured data
    schemas = re.findall(r'<script\s+type=["\']application/ld\+json["\']>.*?</script>', html, re.I | re.S)

    return {
        "links": links,
        "headings": headings,
        "keyword": keyword,
        "kw_in_intro": kw_in_intro,
        "kw_count": kw_count,
        "kw_density": round(kw_density, 2),
        "word_count": word_count,
        "schemas": schemas,
    }


def validate_seo_preservation(original_anchors: Dict, new_html: str) -> Dict:
    """Check that humanized content preserves all SEO-critical elements."""
    new_anchors = extract_seo_anchors(new_html, original_anchors["keyword"])
    issues = []

    # Check links preserved
    orig_hrefs = {l["href"] for l in original_anchors["links"]}
    new_hrefs = {l["href"] for l in new_anchors["links"]}
    missing_links = orig_hrefs - new_hrefs
    if missing_links:
        issues.append(f"Missing {len(missing_links)} internal links: {', '.join(list(missing_links)[:3])}")

    # Check keyword density didn't drop too much
    orig_density = original_anchors["kw_density"]
    new_density = new_anchors["kw_density"]
    if orig_density > 0 and new_density < orig_density * 0.5:
        issues.append(f"Keyword density dropped from {orig_density}% to {new_density}%")

    # Check keyword still in intro
    if original_anchors["kw_in_intro"] and not new_anchors["kw_in_intro"]:
        issues.append("Keyword removed from introduction (first 100 words)")

    # Check heading count preserved
    if len(new_anchors["headings"]) < len(original_anchors["headings"]) * 0.7:
        issues.append(f"Lost headings: {len(original_anchors['headings'])} → {len(new_anchors['headings'])}")

    # Check word count didn't shrink too much
    if new_anchors["word_count"] < original_anchors["word_count"] * 0.7:
        issues.append(f"Word count dropped significantly: {original_anchors['word_count']} → {new_anchors['word_count']}")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "original": original_anchors,
        "new": new_anchors,
    }

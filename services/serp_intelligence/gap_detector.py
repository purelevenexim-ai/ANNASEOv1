def detect_gaps(parsed_pages, pattern_info):
    gaps = []

    if not parsed_pages:
        gaps.append("No competitors available for SERP analysis")
        return gaps

    avg_words = pattern_info.get("avg_word_count", 0)
    if avg_words < 1200:
        gaps.append("SERP top pages are thin; opportunity for depth")

    common = set([h.lower() for h in pattern_info.get("common_headings", [])])
    required = {"pricing", "features", "comparison", "benefits", "how to"}
    lacks = [x for x in required if x not in common]
    for e in lacks:
        gaps.append(f"Missing common section: {e}")

    long_format = any(p.get("word_count", 0) > 1800 for p in (parsed_pages or []))
    if not long_format:
        gaps.append("No long-form top result; long-form may outperform")

    if not any(p.get("has_schema") for p in (parsed_pages or [])):
        gaps.append("No structured data in top pages; schema is a quick differentiator")

    return gaps[:20]

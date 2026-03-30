from collections import Counter


def analyze_pages(parsed_pages):
    parsed = [p for p in parsed_pages if p]
    if not parsed:
        return {
            "avg_word_count": 0,
            "common_headings": [],
            "content_types": [],
            "avg_sections": 0,
        }

    word_counts = [p.get("word_count", 0) for p in parsed]
    sections = [p.get("num_sections", 0) for p in parsed]
    headings = []
    for p in parsed:
        headings.extend(p.get("headings", []))

    heading_freq = Counter([h.lower() for h in headings])
    common_headings = [h for h,c in heading_freq.most_common(10)]

    content_types = Counter([p.get("content_type", "article") for p in parsed])
    content_types = [t for t,_ in content_types.most_common(5)]

    return {
        "avg_word_count": sum(word_counts)/len(word_counts),
        "common_headings": common_headings,
        "content_types": content_types,
        "avg_sections": sum(sections)/len(sections),
    }

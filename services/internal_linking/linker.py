from typing import Dict, List


def plan_links(content_pieces: List[Dict]) -> Dict:
    """Simple internal linking plan based on content piece slugs."""
    if not content_pieces:
        return {"pillars": [], "links": []}

    pillars = [p.get("slug") for p in content_pieces if p.get("is_pillar")]
    if not pillars:
        pillars = [p.get("slug") for p in content_pieces[:1] if p.get("slug")]

    links = []
    for piece in content_pieces:
        source = piece.get("slug")
        if not source:
            continue
        for target in pillars:
            if target and target != source:
                links.append({"source": source, "target": target, "type": "pillar_support", "strength": 0.75})

    return {"pillars": pillars[:5], "links": links[:50]}

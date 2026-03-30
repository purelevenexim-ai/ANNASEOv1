from typing import Dict, Any, List


def predict_ranking_probability(serp_strength: float, content_depth: float, backlinks_score: float):
    score = serp_strength * 0.4 + content_depth * 0.3 + backlinks_score * 0.3
    if score > 0.75:
        return "high"
    if score > 0.5:
        return "medium"
    return "low"


class ScoringEngine:
    def run(self, serp_data: Dict[str, Any], link_data: Dict[str, Any], content_pieces: List[Dict[str, Any]]):
        if not content_pieces:
            return []

        avg_words = 0
        if isinstance(content_pieces, list) and content_pieces:
            wc = [int(p.get("word_count", 0)) for p in content_pieces if isinstance(p.get("word_count", 0), (int, float))]
            avg_words = sum(wc) / (len(wc) or 1)

        serp_strength = 0.5
        if serp_data and isinstance(serp_data, dict):
            key = next(iter(serp_data.get("serp_map", {})), None)
            serp_strength = serp_data.get("serp_map", {}).get(key, {}).get("authority", 0.5) if key else 0.5

        link_score = 0.5
        if link_data and isinstance(link_data, dict):
            link_score = min(1.0, max(0.1, len(link_data.get("links", [])) / 10.0))

        results = []
        for piece in content_pieces:
            slug = piece.get("slug", "")
            depth = min(1.0, (piece.get("word_count", 0) / 2000))
            rank_prob = predict_ranking_probability(serp_strength, depth, link_score)
            results.append({"slug": slug, "authority": link_score, "rank_probability": rank_prob})

        return results

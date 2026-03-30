from typing import Any, Dict, List


def extract_features(pages: List[Dict[str, Any]], your_site: Dict[str, Any] = None) -> Dict[str, float]:
    """Extract ranking features from a list of competitor pages."""
    if not pages:
        return {
            "avg_word_count": 0.0,
            "avg_headings": 0.0,
            "competition_score": 0.0,
            "number_of_pages": 0,
        }

    total_word_count = 0
    total_headings = 0
    total_score = 0.0

    for p in pages:
        total_word_count += float(p.get("word_count", 0) or 0)
        total_headings += len(p.get("headings", []) or [])
        total_score += float(p.get("score", 0) or 0)

    n = len(pages)
    return {
        "avg_word_count": total_word_count / n,
        "avg_headings": total_headings / n,
        "competition_score": total_score / n,
        "number_of_pages": n,
    }


def compute_difficulty(features: Dict[str, float], your_site: Dict[str, Any] = None) -> int:
    score = 0.0

    if features.get("avg_word_count", 0) > 2000:
        score += 30.0
    if features.get("avg_word_count", 0) > 1500:
        score += 15.0

    if features.get("avg_headings", 0) > 15:
        score += 30.0
    if features.get("avg_headings", 0) > 10:
        score += 15.0

    score += features.get("competition_score", 0.0)

    # Mix in domain authority signal if available
    if your_site and isinstance(your_site.get("domain_authority"), (int, float)):
        da = float(your_site.get("domain_authority", 0))
        score = max(score - (da / 2.0), 0.0)

    return min(int(score), 100)


def compute_probability(features: Dict[str, float]) -> int:
    base = 100.0
    penalty = features.get("competition_score", 0.0)

    if features.get("number_of_pages", 0) > 10:
        penalty += 10
    if features.get("avg_word_count", 0) > 2500:
        penalty += 5

    probability = base - penalty
    return max(min(int(probability), 100), 0)


def compute_opportunity(probability: int, difficulty: int) -> int:
    return max(min(int((probability * 0.6) + ((100 - difficulty) * 0.4)), 100), 0)


def make_decision(opportunity: int) -> str:
    if opportunity > 70:
        return "GO"
    if opportunity > 40:
        return "MEDIUM"
    return "SKIP"


def predict_ranking(pages: List[Dict[str, Any]], your_site: Dict[str, Any] = None) -> Dict[str, Any]:
    features = extract_features(pages, your_site=your_site)
    difficulty = compute_difficulty(features)
    probability = compute_probability(features)
    opportunity = compute_opportunity(probability, difficulty)
    decision = make_decision(opportunity)

    return {
        "features": features,
        "difficulty": difficulty,
        "probability": probability,
        "opportunity": opportunity,
        "decision": decision,
    }

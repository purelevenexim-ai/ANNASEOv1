def empty_strategy():
    return {
        "audience": {},
        "angles": [],
        "outline": [],
        "links": [],
        "scores": {},
    }


def normalize_strategy(result_json: dict) -> dict:
    if not result_json or not isinstance(result_json, dict):
        return empty_strategy()

    strategy = result_json.get("strategy") if isinstance(result_json.get("strategy"), dict) else {}

    # fallback is intentionally robust but normalized in strict contract
    audience = (
        strategy.get("audience")
        or result_json.get("audience")
        or result_json.get("market_analysis")
        or {}
    )

    angles = (
        strategy.get("angles")
        or result_json.get("angles")
        or result_json.get("content_angles")
        or []
    )

    outline = (
        strategy.get("outline")
        or result_json.get("outline")
        or result_json.get("article_outline")
        or []
    )

    links = (
        strategy.get("links")
        or result_json.get("links")
        or result_json.get("internal_link_map")
        or []
    )

    scores = (
        strategy.get("scores")
        or result_json.get("scores")
        or result_json.get("seo_scores")
        or result_json.get("scoring")
        or {}
    )

    normalized = {
        "audience": audience if isinstance(audience, dict) else {},
        "angles": angles if isinstance(angles, list) else [],
        "outline": outline if isinstance(outline, list) else [],
        "links": links if isinstance(links, list) else [],
        "scores": scores if isinstance(scores, dict) else {},
    }

    return normalized

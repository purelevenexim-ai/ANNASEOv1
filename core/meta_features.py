

def extract_meta_features(strategy: dict, serp_data: dict = None):
    serp_data = serp_data or {}
    title = strategy.get("title", "") if isinstance(strategy, dict) else ""

    return {
        "content_depth": strategy.get("word_count", 0) if isinstance(strategy, dict) else 0,
        "format": strategy.get("type", "standard") if isinstance(strategy, dict) else "standard",
        "has_comparison": "vs" in title.lower(),
        "has_numbers": any(char.isdigit() for char in title),
        "serp_has_listicles": float(serp_data.get("listicle_ratio", 0.0)),
        "serp_has_videos": float(serp_data.get("video_ratio", 0.0)),
        "intent": strategy.get("intent", "all") if isinstance(strategy, dict) else "all",
    }

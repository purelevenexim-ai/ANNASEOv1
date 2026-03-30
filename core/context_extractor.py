

def extract_context(strategy: dict, keyword_data: dict = None):
    keyword_data = keyword_data or {}

    niche = strategy.get("niche") or keyword_data.get("category") or "general"
    country = keyword_data.get("country") or strategy.get("country") or "global"
    intent = strategy.get("intent") or keyword_data.get("intent") or "all"

    return {
        "niche": niche,
        "country": country,
        "intent": intent,
    }

from urllib.parse import urlparse
from typing import List, Dict, Any


def extract_competitors(serp_data: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    competitors = []
    if not serp_data:
        return competitors

    results = serp_data.get("organic_results") or serp_data.get("results") or []
    for item in results[:limit]:
        title = item.get("title") or item.get("name") or ""
        url = item.get("link") or item.get("url") or ""
        snippet = item.get("snippet") or item.get("description") or item.get("snippet_text") or ""
        domain = ""
        try:
            if url:
                parsed = urlparse(url)
                domain = parsed.netloc or ""
        except Exception:
            domain = ""

        competitors.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "domain": domain,
            "content_freshness": "fresh",
        })

    return competitors

import os, re, logging
import requests
from urllib.parse import urlencode

log = logging.getLogger("serp.scraper")

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


def _parse_duckduckgo(html):
    result = []
    # fast extraction using regex heuristics for a stable fallback
    blocks = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.I)
    for i, (url, title) in enumerate(blocks[:15], start=1):
        result.append({"position": i, "url": url, "title": re.sub('<[^<]+?>', '', title).strip(), "snippet": ""})
    return result


def _normalize_serp_to_list(serp_json, limit=10):
    results = []
    if not serp_json:
        return results
    organic = serp_json.get("organic_results") or serp_json.get("results") or []
    for idx, item in enumerate(organic[:limit], start=1):
        results.append({
            "position": idx,
            "url": item.get("link") or item.get("url") or item.get("url_post_processed") or "",
            "title": item.get("title") or item.get("name") or "",
            "snippet": item.get("snippet") or item.get("description") or "",
        })
    return results


def fetch_serp_results(keyword, limit=10):
    if not keyword:
        return []

    # Prefer centralized SERPEngine when available (DB-backed cache + provider).
    try:
        from engines.serp import SERPEngine
        serp_engine = SERPEngine()
        data = serp_engine.get_serp(keyword)
        lst = _normalize_serp_to_list(data, limit=limit)
        if lst:
            return lst[:limit]
    except Exception:
        # If SERPEngine or DB not available, fall back to provider/scraper below
        pass

    # Try direct SerpAPI HTTP if key available
    if SERPAPI_KEY:
        try:
            params = {
                "engine": "google",
                "q": keyword,
                "api_key": SERPAPI_KEY,
                "num": limit,
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return _normalize_serp_to_list(data, limit=limit)
        except Exception as exc:
            log.warning("SerpAPI failed, fallback to DuckDuckGo: %s", exc)

    # Fallback scraper (DuckDuckGo lite)
    try:
        params = {"q": keyword}
        url = f"https://lite.duckduckgo.com/lite?{urlencode(params)}"
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        outcome = _parse_duckduckgo(r.text)
        return outcome[:limit]
    except Exception as exc:
        log.error("SERP fallback scraper error: %s", exc)
        return []

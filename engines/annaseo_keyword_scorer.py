"""
engines/annaseo_keyword_scorer.py
KeywordScoringEngine — estimates KD and volume from free SERP signals.
Falls back to DataForSEO if DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD are set.
"""
from __future__ import annotations
import os, json, time, logging, re
from typing import List, Callable, Optional
import requests as _req

log = logging.getLogger("annaseo.keyword_scorer")

BIG_BRAND_DOMAINS = [
    "wikipedia.org", "amazon.", "flipkart.", "healthline.com",
    "webmd.com", "nhs.uk", ".gov.", ".edu.", "youtube.com",
    "reddit.com", "nykaa.com",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


class KeywordScoringEngine:
    """Score keywords using free SERP signals or DataForSEO (if configured)."""

    def score_batch(self, keywords: List[dict],
                    on_progress: Optional[Callable] = None) -> List[dict]:
        """Score keywords in-place. Each dict needs 'keyword' and 'relevance_score'.
        Returns same list with difficulty, volume_estimate, opportunity_score, score_signals updated."""
        if os.getenv("DATAFORSEO_LOGIN") and os.getenv("DATAFORSEO_PASSWORD"):
            return self._dataforseo_score(keywords, on_progress)
        return self._free_score(keywords, on_progress)

    # ── Free scoring ──────────────────────────────────────────────────────────

    def _free_score(self, keywords: List[dict],
                    on_progress: Optional[Callable] = None) -> List[dict]:
        for i, kw_item in enumerate(keywords):
            try:
                signals = self._score_one_free(kw_item["keyword"])
            except Exception as e:
                log.warning(f"[Scorer] Error scoring '{kw_item['keyword']}': {e}")
                signals = {"kd": 50, "volume": 20, "serp_score": 50,
                           "brand_score": 50, "title_score": 50, "autosuggest_vol": 20}
            kw_item["difficulty"] = signals["kd"]
            kw_item["volume_estimate"] = signals["volume"]
            rel = kw_item.get("relevance_score", 50) / 100
            vol_n = min(signals["volume"] / 1000, 1.0)
            kd_n = signals["kd"] / 100
            kw_item["opportunity_score"] = round(vol_n * (1 - kd_n) * rel * 100, 1)
            kw_item["score_signals"] = json.dumps(signals)
            if on_progress:
                on_progress(i + 1, len(keywords))
            time.sleep(0.5)  # rate-limit to avoid blocks
        return keywords

    def _score_one_free(self, keyword: str) -> dict:
        autosuggest_vol = self._autosuggest_volume(keyword)
        serp_html, serp_count = self._fetch_duckduckgo(keyword)
        serp_score = self._serp_count_to_score(serp_count)
        brand_score = self._big_brand_score_from_html(serp_html, keyword)
        title_score = self._exact_title_score_from_html(serp_html, keyword)
        kd = round(serp_score * 0.35 + brand_score * 0.35 + title_score * 0.30)
        return {
            "kd": kd, "volume": autosuggest_vol,
            "serp_score": serp_score, "brand_score": brand_score,
            "title_score": title_score, "autosuggest_vol": autosuggest_vol,
        }

    def _fetch_duckduckgo(self, keyword: str) -> tuple:
        """Fetch DuckDuckGo HTML search results. Returns (html, result_count)."""
        try:
            r = _req.get(
                "https://html.duckduckgo.com/html/",
                params={"q": keyword},
                headers=HEADERS,
                timeout=8,
            )
            if not r.ok:
                return "", 0
            html = r.text
            # Parse result count from "About X results" text
            m = re.search(r"About ([\d,]+) results", html)
            count = int(m.group(1).replace(",", "")) if m else 500_000
            return html, count
        except Exception as e:
            log.debug(f"[Scorer] DDG fetch failed: {e}")
            return "", 500_000

    def _serp_count_to_score(self, count: int) -> int:
        """Map result count to 0-100 KD signal."""
        if count < 100_000:    return 20
        if count < 1_000_000:  return 45
        if count < 10_000_000: return 65
        return 85

    def _big_brand_score_from_html(self, html: str, keyword: str) -> int:
        """Count big-brand domains in DDG top results and map to 0-100 score."""
        count = sum(1 for domain in BIG_BRAND_DOMAINS if domain in html[:8000])
        return self._brand_count_to_score(count)

    def _brand_count_to_score(self, count: int) -> int:
        if count == 0: return 10
        if count == 1: return 30
        if count <= 3: return 55
        return 80

    def _exact_title_score_from_html(self, html: str, keyword: str) -> int:
        """Count pages with keyword in result title links in DDG results."""
        titles = re.findall(r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
        kl = keyword.lower()
        count = sum(1 for t in titles if kl in t.lower())
        return self._title_count_to_score(count)

    def _title_count_to_score(self, count: int) -> int:
        if count == 0: return 10
        if count <= 2: return 35
        if count <= 5: return 60
        return 80

    def _autosuggest_volume(self, keyword: str) -> int:
        """Estimate monthly volume from Google Autosuggest position."""
        words = keyword.split()
        if len(words) < 2:
            return 30
        prefix = " ".join(words[:-1])
        try:
            r = _req.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "q": prefix},
                headers=HEADERS,
                timeout=5,
            )
            if r.ok:
                data = r.json()
                suggestions = data[1] if len(data) > 1 else []
                kl = keyword.lower()
                for i, s in enumerate(suggestions[:10]):
                    if kl in str(s).lower() or str(s).lower() in kl:
                        if i < 3:  return 600
                        if i < 7:  return 250
                        return 80
        except Exception as e:
            log.debug(f"[Scorer] Autosuggest failed: {e}")
        return 30

    # ── Testable bucket methods (exposed for unit tests) ─────────────────────

    def _serp_result_score(self, keyword: str) -> int:
        _, count = self._fetch_duckduckgo(keyword)
        return self._serp_count_to_score(count)

    def _big_brand_score(self, keyword: str) -> int:
        html, _ = self._fetch_duckduckgo(keyword)
        return self._big_brand_score_from_html(html, keyword)

    def _exact_title_score(self, keyword: str) -> int:
        html, _ = self._fetch_duckduckgo(keyword)
        return self._exact_title_score_from_html(html, keyword)

    # ── DataForSEO fallback ───────────────────────────────────────────────────

    def _dataforseo_score(self, keywords: List[dict],
                          on_progress: Optional[Callable] = None) -> List[dict]:
        import base64
        login = os.getenv("DATAFORSEO_LOGIN")
        pwd = os.getenv("DATAFORSEO_PASSWORD")
        token = base64.b64encode(f"{login}:{pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        kw_list = [k["keyword"] for k in keywords]
        batches = [kw_list[i:i+100] for i in range(0, len(kw_list), 100)]
        kw_map = {}
        for batch in batches[:5]:
            try:
                r = _req.post(
                    "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live",
                    headers=headers,
                    json=[{"keywords": batch, "language_name": "English", "location_code": 2356}],
                    timeout=30,
                )
                if r.ok:
                    for task in r.json().get("tasks", []):
                        for item in task.get("result", []) or []:
                            kw_map[item.get("keyword", "")] = {
                                "vol": item.get("search_volume", 0) or 0,
                                "kd": item.get("competition_index", 50) or 50,
                            }
            except Exception as e:
                log.warning(f"[Scorer] DataForSEO batch failed: {e}")
        for i, kw_item in enumerate(keywords):
            data = kw_map.get(kw_item["keyword"], {"vol": 30, "kd": 50})
            kw_item["difficulty"] = data["kd"]
            kw_item["volume_estimate"] = data["vol"]
            rel = kw_item.get("relevance_score", 50) / 100
            vol_n = min(data["vol"] / 1000, 1.0)
            kd_n = data["kd"] / 100
            kw_item["opportunity_score"] = round(vol_n * (1 - kd_n) * rel * 100, 1)
            kw_item["score_signals"] = json.dumps({"source": "dataforseo", **data})
            if on_progress:
                on_progress(i + 1, len(keywords))
        return keywords

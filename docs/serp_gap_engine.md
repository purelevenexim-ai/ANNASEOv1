# SERP Gap Engine — Implementation Guide

Purpose
-------
Turn keywords into real, data-backed strategy inputs by extracting competitor signals and detecting missing topics competitors ignore.

Overview
--------
Keyword → SERP → Competitor Extraction → Content Analysis → Gap Detection → Strategy Input

1) engines/serp_engine.py — fetch + cache

```py
import os
import requests
from services.db import get_serp_cache, save_serp_cache

SERP_API_KEY = os.getenv('SERP_API_KEY')

class SERPEngine:
    def fetch_serp(self, keyword):
        cached = get_serp_cache(keyword)
        if cached:
            return cached

        url = 'https://serpapi.com/search'
        params = {'q': keyword, 'api_key': SERP_API_KEY, 'engine': 'google', 'num': 10}

        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        results = [
            {'title': r.get('title'), 'url': r.get('link'), 'snippet': r.get('snippet')}
            for r in data.get('organic_results', [])[:10]
        ]

        save_serp_cache(keyword, results)
        return results
```

Notes:
- Respect SerpAPI rate limits and costs. Add batching and circuit-breakers.
- Persist only aggregated SERP signals to `serp_cache`; keep raw SERP ephemeral.

2) services/content_analyzer.py — extract content signals

```py
import requests
from bs4 import BeautifulSoup

class ContentAnalyzer:
    def analyze(self, url):
        try:
            html = requests.get(url, timeout=10).text
            soup = BeautifulSoup(html, 'html.parser')

            headings = [h.text.strip() for h in soup.find_all(['h1','h2','h3'])]
            word_count = len(soup.get_text().split())

            return {'word_count': word_count, 'headings': headings[:20]}

        except Exception:
            return {'word_count': 0, 'headings': []}
```

3) services/gap_engine.py — detect missing topics

```py
class GapEngine:
    def find_gaps(self, serp_results, keyword):
        all_headings = []
        for page in serp_results:
            all_headings.extend(page.get('headings', []))

        all_headings = [h.lower() for h in all_headings]

        gaps = []
        expected_topics = ['price','cost','best time','itinerary','tips','safety']

        for topic in expected_topics:
            if not any(topic in h for h in all_headings):
                gaps.append(topic)

        return gaps
```

4) Integration (enrich keywords)

```py
from engines.serp_engine import SERPEngine
from services.content_analyzer import ContentAnalyzer
from services.gap_engine import GapEngine

serp = SERPEngine()
analyzer = ContentAnalyzer()
gap_engine = GapEngine()

def enrich_keyword(keyword):
    results = serp.fetch_serp(keyword)

    enriched = []
    for r in results:
        analysis = analyzer.analyze(r['url'])
        r.update(analysis)
        enriched.append(r)

    gaps = gap_engine.find_gaps(enriched, keyword)

    return {'serp': enriched, 'gaps': gaps}
```

5) ContextBuilder integration
- Add `serp_insights` to the `strategy_context` JSON returned by `ContextBuilder`:

```json
"serp_insights": {
  "top_competitors": [...],
  "avg_word_count": 1200,
  "missing_topics": ["safety","price"]
}
```

Production considerations
- SERP quotas, batching, and per-project budgets
- Geo-specific SERPs (use region parameter)
- Cache TTL and eviction (24–72h default)
- Cost controls and circuit-breakers

Tests
- Unit tests for `ContentAnalyzer.analyze` and `GapEngine.find_gaps` using small HTML fixtures.
- Integration test for `SERPEngine.fetch_serp` using recorded fixture responses.

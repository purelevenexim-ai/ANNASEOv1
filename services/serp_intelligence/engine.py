import logging
from typing import List, Dict

import services.serp_intelligence.scraper as scraper
import services.serp_intelligence.parser as parser
from services.serp_intelligence.analyzer import analyze_pages
from services.serp_intelligence.gap_detector import detect_gaps
from services.serp_intelligence.scorer import compute_win_probability

log = logging.getLogger("serp.engine")


class SERPIntelligenceEngine:
    def __init__(self, max_results: int = 8, max_pages: int = 5):
        self.max_results = max_results
        self.max_pages = max_pages

    def run(self, keyword_clusters: List[Dict]) -> Dict:
        if not keyword_clusters:
            return {
                "serp_summary": {},
                "competitors": [],
                "content_patterns": {},
                "weaknesses": [],
                "gaps": [],
                "win_probability": 0.0,
                "recommended_angles": [],
            }

        serp_collection = []
        all_parsed_pages = []

        for cluster in keyword_clusters:
            keyword = cluster.get("primary_keyword") or (cluster.get("keywords") or [None])[0]
            if not keyword:
                continue

            serp = scraper.fetch_serp_results(keyword, limit=self.max_results)
            serp_collection.append({"keyword": keyword, "results": serp})

            for item in serp[: self.max_pages]:
                parsed = parser.parse_page(item.get("url"))
                if parsed:
                    merged = {**item, **parsed}
                    all_parsed_pages.append(merged)

        analyzer = analyze_pages(all_parsed_pages)
        gaps = detect_gaps(all_parsed_pages, analyzer)
        score_data = compute_win_probability({"avg_kd": 0.5}, gaps, analyzer)

        recommended_angles = []
        if any("pricing" in g for g in gaps):
            recommended_angles.append("Add pricing breakdown")
        if any("long-form" in g for g in gaps) or analyzer.get("avg_word_count", 0) < 2000:
            recommended_angles.append("Focus on long-form 2200+ article")
        if any("structured data" in g for g in gaps):
            recommended_angles.append("Add JSON-LD schema for FAQ/product")

        weaknesses = [g for g in gaps if "Missing" in g or "No" in g]

        return {
            "serp_summary": {
                "top_keywords": [c["keyword"] for c in serp_collection],
                "num_checked": len(serp_collection),
                "avg_word_count": analyzer.get("avg_word_count", 0),
                "avg_sections": analyzer.get("avg_sections", 0),
            },
            "competitors": [r for c in serp_collection for r in c["results"]],
            "content_patterns": analyzer,
            "weaknesses": weaknesses,
            "gaps": gaps,
            **score_data,
            "win_probability": score_data.get("win_probability", 0.0),
            "recommended_angles": list(dict.fromkeys(recommended_angles)),
        }

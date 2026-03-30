from typing import List, Dict, Any
from services.llm_parser import parse_llm_json
from services.ranking_monitor import RankingMonitor


class ContentFixGenerator:
    def __init__(self, llm_client=None):
        self.llm = llm_client

    def build_prompt(self, keyword: str, root_causes: List[str], gaps: List[str], competitor_insights: List[Dict[str, Any]]) -> str:
        comp_summary = "\n".join([f"- {c.get('url')} headings={len(c.get('headings', []))} wc={c.get('word_count', 'N/A')}" for c in competitor_insights[:5]])
        return f"""
You are an AI SEO content optimizer.

Keyword: {keyword}

Root causes: {', '.join(root_causes)}
Missing gaps: {', '.join(gaps)}
Competitor insights:
{comp_summary}

Produce JSON ONLY with structure:
{{
  "sections_to_add": [{{"heading": "", "content": "", "reason": ""}}],
  "sections_to_update": [{{"heading": "", "improved_content": "", "reason": ""}}],
  "title_suggestion": "",
  "meta_description": ""
}}
"""

    def parse_response(self, text: str) -> Dict:
        parsed, err = parse_llm_json(text)
        if err or not isinstance(parsed, dict):
            return {
                "sections_to_add": [],
                "sections_to_update": [],
                "title_suggestion": "",
                "meta_description": ""
            }
        return parsed

    def generate_fix(self, keyword: str, root_causes: List[str], gaps: List[str], competitor_insights: List[Dict[str, Any]], current_content: str = "") -> Dict:
        if not self.llm:
            # fallback dumb generator
            return {
                "sections_to_add": [
                    {"heading": "New section: why this matters", "content": "Add detailed comparison section.", "reason": "Competitor coverage"}
                ],
                "sections_to_update": [],
                "title_suggestion": f"{keyword} - Updated Guide",
                "meta_description": f"Improve your article with missing keywords: {', '.join(gaps[:5])}."
            }

        prompt = self.build_prompt(keyword, root_causes, gaps, competitor_insights)
        ret = self.llm.generate(prompt)
        if isinstance(ret, tuple) and len(ret) == 2:
            text, tokens = ret
            # token tracking for content fix can be added to DB/logging later
        else:
            text = ret
            tokens = 0
        return self.parse_response(text)

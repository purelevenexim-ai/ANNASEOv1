import json
from engines.ruflo_final_strategy_engine import RankingMonitor, FinalStrategyEngine
from services.strategy_schema import load_strategy_schema


def test_ranking_monitor_diagnose_drop():
    rm = RankingMonitor()
    db = __import__('main').get_db()
    result = rm.diagnose_drop(db, project_id="test-project", keyword="test", target_url="http://example.com", content_data={"content": "x"})
    assert result["keyword"] == "test"
    assert "drop_analysis" in result
    assert "serp_context" in result


class DummyLLMClient:
    def __init__(self):
        self.attempts = 0

    def generate(self, system_prompt, user_prompt, temperature=0.2, top_p=0.9, max_tokens=4000):
        self.attempts += 1
        if self.attempts == 1:
            return "This is invalid JSON output", 50
        strategy = {
            "strategy_meta": {"project_id": "p1", "generated_at": "2026-01-01T00:00:00Z", "execution_mode": "single_call"},
            "market_analysis": {"target_audience": ["tech buyers"], "search_intent_types": ["informational"], "pain_points": ["slow site"]},
            "keyword_strategy": {"primary_keywords": [{"keyword": "cloud seo", "intent": "informational", "difficulty": 25, "priority": 3}], "secondary_keywords": [], "long_tail_keywords": []},
            "content_strategy": {"pillar_pages": [{"title": "Cloud SEO", "target_keyword": "cloud seo", "search_intent": "informational", "outline": ["Intro"]}], "cluster_topics": []},
            "authority_strategy": {"backlink_plan": ["guest posts"], "topical_depth": ["authority content"]},
            "execution_plan": {"phases": [{"phase_name": "phase1", "tasks": [{"task_name": "create outline", "priority": 1}]}]}
        }
        return json.dumps(strategy), 120


def test_final_strategy_engine_retry_and_validate():
    llm = DummyLLMClient()
    engine = FinalStrategyEngine(llm_client=llm)
    payload = {
        "project": {"project_id": "p1"},
        "keyword_universe": [],
        "gsc_data": {},
        "serp_data": {},
        "competitors": [],
        "strategy_meta": {"project_id": "p1", "generated_at": "2026-01-01T00:00:00Z", "execution_mode": "single_call"}
    }
    out = engine.run(payload)

    assert out["success"] is True
    assert out["data"]["strategy_meta"]["execution_mode"] == "single_call"
    assert llm.attempts == 2

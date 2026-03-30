import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from engines.ruflo_final_strategy_engine import FinalStrategyEngine
from engines.serp import SERPEngine


DATABASE_URL = os.getenv("DATABASE_URL")


@pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")
def test_serp_engine_upserts_cache():
    engine = create_engine(DATABASE_URL)
    serp = SERPEngine(db_engine=engine)
    q = f"test-serp-{uuid.uuid4().hex[:8]}"
    data = serp.get_serp(q)
    # basic sanity: provider returns a dict and call does not raise
    assert isinstance(data, dict)
    # second call should also succeed (cache/no-cache path)
    data2 = serp.get_serp(q)
    assert isinstance(data2, dict)


def test_final_engine_wrapper_with_dummy():
    class DummyLLM:
        def generate(self, system_prompt=None, user_prompt=None, temperature=0.2, top_p=0.9, max_tokens=4000):
            return ('{"strategy_meta": {"project_id": "p", "generated_at": "2026-01-01", "execution_mode":"single_call"}, "market_analysis": {"target_audience": [], "search_intent_types": [], "pain_points": []}, "keyword_strategy": {"primary_keywords": [], "secondary_keywords": [], "long_tail_keywords": []}, "content_strategy": {"pillar_pages": [], "cluster_topics": []}, "authority_strategy": {"backlink_plan": [], "topical_depth": []}, "execution_plan": {"phases": [{"phase_name":"p","tasks":[{"task_name":"t","priority":1}]}]} }', 10)

    fse = FinalStrategyEngine(DummyLLM())
    out = fse._call_strategy_model("prompt", max_tokens=100)
    assert isinstance(out, tuple)
    assert isinstance(out[0], str)
    assert isinstance(out[1], int)

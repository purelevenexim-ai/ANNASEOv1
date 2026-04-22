import json
import os
import sqlite3
from unittest.mock import patch


def _set_test_db(tmp_path):
    db_path = str(tmp_path / "kw2_intel_brand.db")
    os.environ["ANNASEO_DB"] = db_path
    from engines.kw2.db import init_kw2_db
    init_kw2_db(db_path)
    return db_path


def test_init_kw2_db_adds_expansion_provenance_columns(tmp_path):
    db_path = _set_test_db(tmp_path)
    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(kw2_intelligence_questions)").fetchall()]
    conn.close()

    assert "expansion_dimension_name" in cols
    assert "expansion_dimension_value" in cols


def test_load_business_profile_decodes_nested_manual_input(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2.db import get_conn, load_business_profile

    nested_manual = json.dumps(json.dumps({"domain": "https://pureleven.com", "brand_name": "Pureleven"}))
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO kw2_business_profile
               (id, project_id, domain, universe, pillars, product_catalog, modifiers,
                audience, intent_signals, geo_scope, business_type, negative_scope,
                confidence_score, raw_ai_json, manual_input, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (
                "bp_test",
                "proj_brand_decode",
                "pureleven.com",
                "Indian Spices",
                json.dumps(["cardamom"]),
                json.dumps(["Green Cardamom"]),
                json.dumps([]),
                json.dumps(["Cooking"]),
                json.dumps([]),
                "India",
                "Ecommerce",
                json.dumps([]),
                0.0,
                "",
                nested_manual,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    profile = load_business_profile("proj_brand_decode")
    assert isinstance(profile["manual_input"], dict)
    assert profile["manual_input"]["brand_name"] == "Pureleven"


def test_discover_dimensions_uses_brand_fallback_from_domain(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2.db import save_business_profile
    from engines.kw2.expansion_engine import ExpansionEngine

    save_business_profile("proj_brand_dims", {
        "domain": "pureleven.com",
        "universe": "Indian Spices",
        "pillars": ["cardamom", "clove"],
        "product_catalog": ["Green Cardamom"],
        "modifiers": ["organic"],
        "audience": ["Cooking", "Restaurants"],
        "intent_signals": ["buy"],
        "geo_scope": "India",
        "business_type": "Ecommerce",
        "negative_scope": [],
        "manual_input": {"domain": "https://pureleven.com/"},
    })

    with patch("engines.kw2.expansion_engine.kw2_ai_call", return_value=""):
        result = ExpansionEngine().discover_dimensions("proj_brand_dims", "sess_brand_dims")

    assert "brand_name" in result["dimensions"]
    assert result["dimensions"]["brand_name"] == ["Pureleven"]
    assert "audience" in result["dimensions"]
    assert "product" in result["dimensions"]


def test_run_auto_discovers_dimensions_and_persists_provenance(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2 import db
    from engines.kw2.expansion_engine import ExpansionEngine

    session_id = db.create_session("proj_expand_brand")
    db.save_business_profile("proj_expand_brand", {
        "domain": "pureleven.com",
        "universe": "Indian Spices",
        "pillars": ["cardamom"],
        "product_catalog": ["Green Cardamom"],
        "modifiers": [],
        "audience": ["Cooking"],
        "intent_signals": [],
        "geo_scope": "India",
        "business_type": "Ecommerce",
        "negative_scope": [],
        "manual_input": {"domain": "https://pureleven.com/"},
    })

    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO kw2_intelligence_questions
               (id, session_id, project_id, module_code, question, created_at)
               VALUES (?,?,?,?,?,datetime('now'))""",
            ("qi_seed", session_id, "proj_expand_brand", "Q3", "Where can I buy cardamom online?"),
        )
        conn.commit()
    finally:
        conn.close()

    def _mock_ai_call(*args, **kwargs):
        if kwargs.get("task") == "expansion_discover":
            return ""
        if kwargs.get("task") == "expansion_expand" and "EXPANSION DIMENSION: brand_name" in args[0]:
            return json.dumps({
                "expanded_questions": [
                    {
                        "question": "Where can I buy Pureleven cardamom online?",
                        "dimension_applied": "brand_name",
                        "dimension_value": "Pureleven",
                    }
                ]
            })
        return json.dumps({"expanded_questions": []})

    with patch("engines.kw2.expansion_engine.kw2_ai_call", side_effect=_mock_ai_call):
        result = ExpansionEngine().run("proj_expand_brand", session_id, max_depth=1, max_per_node=1, max_total=5)

    assert result["questions_created"] == 1

    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT question, expansion_dimension_name, expansion_dimension_value, data_source
               FROM kw2_intelligence_questions
               WHERE session_id=? AND expansion_depth=1""",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["question"] == "Where can I buy Pureleven cardamom online?"
    assert row["expansion_dimension_name"] == "brand_name"
    assert row["expansion_dimension_value"] == "Pureleven"
    assert row["data_source"] == "ai_expansion"
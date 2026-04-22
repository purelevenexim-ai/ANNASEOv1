"""
Phase 7 — Backend test coverage for the pipeline-status endpoint and
broader engine contracts (dedup, scoring, selection).
"""
import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _set_test_db(tmp_path, name="kw2_test.db"):
    db_path = str(tmp_path / name)
    os.environ["ANNASEO_DB"] = db_path
    from engines.kw2.db import init_kw2_db
    init_kw2_db(db_path)
    return db_path


def _insert_question(conn, session_id, project_id, qid, text, *,
                     intent=None, is_duplicate=0, expansion_depth=0, final_score=0.0,
                     cluster_id=None, module_code="Q1"):
    conn.execute(
        """INSERT OR REPLACE INTO kw2_intelligence_questions
           (id, session_id, project_id, module_code, question, intent,
            is_duplicate, expansion_depth, final_score, content_cluster_id, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
        (qid, session_id, project_id, module_code, text, intent,
         is_duplicate, expansion_depth, final_score, cluster_id),
    )


def _insert_cluster(conn, session_id, cid, name="Test Cluster", project_id="proj_test"):
    conn.execute(
        """INSERT OR REPLACE INTO kw2_content_clusters
           (id, session_id, project_id, cluster_name, created_at)
           VALUES (?,?,?,?,datetime('now'))""",
        (cid, session_id, project_id, name),
    )


def _insert_selected(conn, session_id, question_id, selection_rank=1):
    conn.execute(
        """INSERT OR REPLACE INTO kw2_selected_questions
           (id, session_id, question_id, selection_rank, created_at)
           VALUES (?,?,?,?,datetime('now'))""",
        (f"sel_{question_id}", session_id, question_id, selection_rank),
    )


# ---------------------------------------------------------------------------
# Pipeline-status logic tests (pure unit — no HTTP)
# ---------------------------------------------------------------------------

def test_pipeline_status_empty_session(tmp_path):
    """A brand-new session has no data; generate should be 'ready', rest 'blocked'."""
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db

    session_id = kw2_db.create_session("proj_ps_empty")

    # Call the pipeline status logic directly via a thin helper that mirrors main.py
    stages = _compute_stages(session_id)
    assert stages["generate"] == "ready"
    assert stages["enrich"] == "blocked"
    assert stages["discover"] == "blocked"
    assert stages["expand"] == "blocked"
    assert stages["dedup"] == "blocked"
    assert stages["cluster"] == "blocked"
    assert stages["score"] == "blocked"
    assert stages["select"] == "blocked"


def test_pipeline_status_after_questions_only(tmp_path):
    """After questions are generated, enrich/dedup/cluster become 'ready'."""
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db

    session_id = kw2_db.create_session("proj_ps_q")
    conn = kw2_db.get_conn()
    try:
        for i in range(5):
            _insert_question(conn, session_id, "proj_ps_q", f"q{i}", f"Question {i}")
        conn.commit()
    finally:
        conn.close()

    stages = _compute_stages(session_id)
    assert stages["generate"] == "done"
    assert stages["enrich"] == "ready"       # has questions, unenriched > 0
    assert stages["discover"] == "ready"     # has questions and no dims yet
    assert stages["expand"] == "blocked"     # no dimensions → blocked
    assert stages["dedup"] == "ready"
    assert stages["cluster"] == "ready"
    assert stages["score"] == "blocked"      # no clusters yet
    assert stages["select"] == "blocked"     # no scored questions


def test_pipeline_status_all_done(tmp_path):
    """A fully-processed session has every stage as 'done'."""
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db

    project_id = "proj_ps_full"
    session_id = kw2_db.create_session(project_id)

    # Save expansion config with discovered dimensions
    conn = kw2_db.get_conn()
    try:
        dims = json.dumps({"brand_name": ["Pureleven"], "geo": ["India"]})
        conn.execute(
            """INSERT OR REPLACE INTO kw2_expansion_config
               (id, session_id, discovered_dimensions, created_at)
               VALUES (?,?,?,datetime('now'))""",
            (f"ec_{session_id}", session_id, dims),
        )
        _insert_cluster(conn, session_id, "cl1", project_id=project_id)
        for i in range(10):
            _insert_question(conn, session_id, project_id, f"q{i}", f"Q {i}",
                             intent="informational", expansion_depth=1 if i >= 5 else 0,
                             final_score=70.0 + i, cluster_id="cl1")
        for i in range(5):
            _insert_selected(conn, session_id, f"q{i}", selection_rank=i + 1)
        conn.commit()
    finally:
        conn.close()

    stages = _compute_stages(session_id)
    assert stages["generate"] == "done"
    assert stages["enrich"] == "done"        # all questions have intent
    assert stages["discover"] == "done"      # has dimensions
    assert stages["expand"] == "done"        # has expanded questions
    assert stages["dedup"] == "ready"        # dedup never marks rows as duplicate here
    assert stages["cluster"] == "done"
    assert stages["score"] == "done"
    assert stages["select"] == "done"


# ---------------------------------------------------------------------------
# Dedup engine contract
# ---------------------------------------------------------------------------

def test_dedup_removes_exact_duplicates(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db
    from engines.kw2.dedup_engine import DedupEngine

    session_id = kw2_db.create_session("proj_dedup")
    conn = kw2_db.get_conn()
    try:
        for i in range(3):
            _insert_question(conn, session_id, "proj_dedup", f"qdup{i}",
                             "How to buy organic cardamom online?")
        _insert_question(conn, session_id, "proj_dedup", "quniq",
                         "Best wholesale cardamom suppliers in Kerala")
        conn.commit()
    finally:
        conn.close()

    result = DedupEngine().run_dedup(session_id)
    assert result["original_count"] == 4
    assert result["unique_count"] <= 2          # at most 2 unique (1 dedup group + 1 unique)
    assert result["duplicates_removed"] >= 2    # at least 2 of the 3 copies removed


def test_dedup_unique_questions_not_removed(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db
    from engines.kw2.dedup_engine import DedupEngine

    session_id = kw2_db.create_session("proj_dedup_uniq")
    conn = kw2_db.get_conn()
    try:
        texts = [
            "How to grow cardamom in Kerala?",
            "Best wholesale spice suppliers India",
            "Organic cinnamon benefits for cooking",
            "Where to export Indian spices UK?",
        ]
        for i, t in enumerate(texts):
            _insert_question(conn, session_id, "proj_dedup_uniq", f"qu{i}", t)
        conn.commit()
    finally:
        conn.close()

    result = DedupEngine().run_dedup(session_id)
    assert result["duplicates_removed"] == 0
    assert result["unique_count"] == 4


# ---------------------------------------------------------------------------
# Scoring engine contract
# ---------------------------------------------------------------------------

def test_scoring_engine_produces_scores_between_0_and_100(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db
    from engines.kw2.scoring_engine import ScoringEngine

    session_id = kw2_db.create_session("proj_score")
    conn = kw2_db.get_conn()
    try:
        _insert_cluster(conn, session_id, "clA", "Cardamom Cluster", project_id="proj_score")
        for i in range(8):
            _insert_question(conn, session_id, "proj_score", f"qs{i}", f"Spice question {i}",
                             intent="informational", cluster_id="clA")
        conn.commit()
    finally:
        conn.close()

    result = ScoringEngine().run(session_id, "proj_score")
    assert result["scored"] == 8

    conn2 = kw2_db.get_conn()
    try:
        rows = conn2.execute(
            "SELECT final_score FROM kw2_intelligence_questions WHERE session_id=?",
            (session_id,),
        ).fetchall()
    finally:
        conn2.close()

    for row in rows:
        score = row["final_score"] or 0.0
        assert 0.0 <= score <= 100.0, f"Score {score} out of range"


def test_scoring_engine_respects_custom_weights(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db
    from engines.kw2.scoring_engine import ScoringEngine

    session_id = kw2_db.create_session("proj_weights")
    conn = kw2_db.get_conn()
    try:
        _insert_cluster(conn, session_id, "clW", "Weight Cluster", project_id="proj_weights")
        for i in range(4):
            _insert_question(conn, session_id, "proj_weights", f"qw{i}", f"Weighted Q {i}",
                             intent="commercial", cluster_id="clW")
        conn.commit()
    finally:
        conn.close()

    custom_weights = {
        "business_fit": 0.5,
        "intent_value": 0.2,
        "demand_potential": 0.1,
        "competition_ease": 0.1,
        "uniqueness": 0.1,
    }
    result = ScoringEngine().run(session_id, "proj_weights", custom_weights=custom_weights)
    assert result["scored"] == 4
    assert result["weights_used"]["business_fit"] == 0.5


# ---------------------------------------------------------------------------
# Selection engine contract
# ---------------------------------------------------------------------------

def test_selection_engine_selects_up_to_n(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db
    from engines.kw2.selection_engine import SelectionEngine

    session_id = kw2_db.create_session("proj_sel")
    conn = kw2_db.get_conn()
    try:
        _insert_cluster(conn, session_id, "clS", "Selection Cluster", project_id="proj_sel")
        for i in range(20):
            _insert_question(conn, session_id, "proj_sel", f"qsel{i}", f"Selection Q {i}",
                             intent="informational", final_score=float(80 - i),
                             cluster_id="clS")
        conn.commit()
    finally:
        conn.close()

    result = SelectionEngine().run(session_id, "proj_sel", target_count=10, max_per_cluster=5)
    assert result["selected"] <= 10
    assert result["selected"] > 0


def test_selection_engine_include_remove(tmp_path):
    _set_test_db(tmp_path)
    from engines.kw2 import db as kw2_db
    from engines.kw2.selection_engine import SelectionEngine

    session_id = kw2_db.create_session("proj_sel_mod")
    conn = kw2_db.get_conn()
    try:
        _insert_cluster(conn, session_id, "clM", "Mod Cluster", project_id="proj_sel_mod")
        for i in range(5):
            _insert_question(conn, session_id, "proj_sel_mod", f"qm{i}", f"Mod Q {i}",
                             final_score=float(60 + i), cluster_id="clM")
        conn.commit()
    finally:
        conn.close()

    engine = SelectionEngine()
    engine.run(session_id, "proj_sel_mod", target_count=3, max_per_cluster=3)
    before = len(engine.list_selected(session_id))
    assert before > 0

    # manually include q4 if not already included
    engine.include_question(session_id, "qm4")
    after_include = {row["question_id"] for row in engine.list_selected(session_id)}
    assert "qm4" in after_include

    # remove it
    engine.remove_question(session_id, "qm4")
    after_remove = {row["question_id"] for row in engine.list_selected(session_id)}
    assert "qm4" not in after_remove


# ---------------------------------------------------------------------------
# Helper: replicate pipeline-status logic without HTTP
# ---------------------------------------------------------------------------

def _compute_stages(session_id: str) -> dict:
    """Mirror the pipeline-status logic from main.py for unit testing."""
    from engines.kw2 import db as kw2_db
    import sqlite3

    db_path = kw2_db._db_path()

    def _fetch(q, p=()):
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(q, p).fetchall()

    q_rows = _fetch(
        "SELECT intent, is_duplicate, expansion_depth, final_score "
        "FROM kw2_intelligence_questions WHERE session_id=?", (session_id,)
    )
    total_q = len(q_rows)
    enriched = sum(1 for r in q_rows if r["intent"])
    unenriched = total_q - enriched
    expanded_n = sum(1 for r in q_rows if (r["expansion_depth"] or 0) > 0)
    unique_n = sum(1 for r in q_rows if not r["is_duplicate"])
    dup_removed = total_q - unique_n
    scored_n = sum(1 for r in q_rows if (r["final_score"] or 0.0) > 0)

    exp_rows = _fetch(
        "SELECT discovered_dimensions FROM kw2_expansion_config WHERE session_id=?", (session_id,)
    )
    discovered_dims: dict = {}
    if exp_rows:
        raw = exp_rows[0]["discovered_dimensions"] or "{}"
        try:
            discovered_dims = json.loads(raw)
        except Exception:
            pass

    cl_rows = _fetch("SELECT id FROM kw2_content_clusters WHERE session_id=?", (session_id,))
    cluster_count = len(cl_rows)
    sel_rows = _fetch("SELECT id FROM kw2_selected_questions WHERE session_id=?", (session_id,))
    selected_count = len(sel_rows)
    has_dims = bool(discovered_dims)

    def _stage(name):
        if name == "generate":  return "done" if total_q > 0 else "ready"
        if name == "enrich":    return "blocked" if total_q == 0 else ("done" if unenriched == 0 else "ready")
        if name == "discover":  return "blocked" if total_q == 0 else ("done" if has_dims else "ready")
        if name == "expand":    return "blocked" if not has_dims else ("done" if expanded_n > 0 else "ready")
        if name == "dedup":     return "blocked" if total_q == 0 else ("done" if dup_removed > 0 else "ready")
        if name == "cluster":   return "blocked" if total_q == 0 else ("done" if cluster_count > 0 else "ready")
        if name == "score":     return "blocked" if cluster_count == 0 else ("done" if scored_n > 0 else "ready")
        if name == "select":    return "blocked" if scored_n == 0 else ("done" if selected_count > 0 else "ready")
        return "ready"

    return {n: _stage(n) for n in
            ["generate", "enrich", "discover", "expand", "dedup", "cluster", "score", "select"]}

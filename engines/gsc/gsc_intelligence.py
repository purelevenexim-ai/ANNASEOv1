"""
GSC Phase 2 — Intelligence Pipeline Orchestrator
Runs the full Phase 2 pipeline in deterministic order:

  1. Embeddings (incremental — only new keywords)
  2. AI Intent Classification (batch LLM + rule pre-filter)
  3. Clustering (HDBSCAN + LLM naming)
  4. Graph Construction (top-K neighbors)
  5. Advanced Scoring (v2 — with confidence + business priority)
  6. Insight Generation (quick wins, money, gaps, linking)
  7. Authority Scoring (per pillar)

Each step depends on previous layers.
"""
import logging
import time

from . import gsc_db
from .gsc_embeddings import generate_embeddings
from .gsc_intent_ai import classify_intents_batch
from .gsc_clustering import cluster_keywords
from .gsc_graph import build_graph
from .gsc_scoring_v2 import rescore_keywords, calculate_authority
from .gsc_insights import generate_insights

log = logging.getLogger(__name__)


def run_pipeline(project_id: str, force_embeddings: bool = False) -> dict:
    """
    Run the full Phase 2 intelligence pipeline.

    Prerequisite: Phase 1 processing must be complete (keywords_processed populated).

    Args:
        project_id: The project to process.
        force_embeddings: If True, re-embed all keywords (not just new ones).

    Returns: Summary dict with results from each step.
    """
    t0 = time.time()
    result = {"project_id": project_id, "steps": {}}

    # Verify prerequisite
    stats = gsc_db.get_stats(project_id)
    if stats["processed_count"] == 0:
        raise ValueError(
            "No processed keywords found. Run Phase 1 processing first "
            "(GSC → Connect & Sync → Process)."
        )

    log.info(f"[GSC P2] Starting Phase 2 pipeline for {project_id} "
             f"({stats['processed_count']} processed keywords)")

    # Step 1: Embeddings
    log.info("[GSC P2] Step 1/7: Generating embeddings...")
    t1 = time.time()
    emb_result = generate_embeddings(project_id, force=force_embeddings)
    result["steps"]["embeddings"] = {**emb_result, "time": round(time.time() - t1, 2)}

    # Step 2: AI Intent Classification
    log.info("[GSC P2] Step 2/7: AI intent classification...")
    t2 = time.time()
    intent_result = classify_intents_batch(project_id)
    result["steps"]["intent"] = {**intent_result, "time": round(time.time() - t2, 2)}

    # Step 3: Clustering
    log.info("[GSC P2] Step 3/7: HDBSCAN clustering...")
    t3 = time.time()
    cluster_result = cluster_keywords(project_id)
    result["steps"]["clustering"] = {**cluster_result, "time": round(time.time() - t3, 2)}

    # Step 4: Graph Construction
    log.info("[GSC P2] Step 4/7: Building keyword graph...")
    t4 = time.time()
    graph_result = build_graph(project_id)
    result["steps"]["graph"] = {**graph_result, "time": round(time.time() - t4, 2)}

    # Step 5: Advanced Scoring
    log.info("[GSC P2] Step 5/7: Rescoring with Phase 2 signals...")
    t5 = time.time()
    score_result = rescore_keywords(project_id)
    result["steps"]["scoring"] = {**score_result, "time": round(time.time() - t5, 2)}

    # Step 6: Insight Generation
    log.info("[GSC P2] Step 6/7: Generating insights...")
    t6 = time.time()
    insight_result = generate_insights(project_id)
    result["steps"]["insights"] = {**insight_result, "time": round(time.time() - t6, 2)}

    # Step 7: Authority Scoring
    log.info("[GSC P2] Step 7/7: Calculating pillar authority...")
    t7 = time.time()
    authority = calculate_authority(project_id)
    gsc_db.save_insights(project_id, "authority", authority)
    result["steps"]["authority"] = {
        "pillars": len(authority),
        "scores": {p: v["authority_score"] for p, v in authority.items()},
        "time": round(time.time() - t7, 2),
    }

    total_time = round(time.time() - t0, 2)
    result["total_time"] = total_time
    result["status"] = "complete"

    log.info(f"[GSC P2] Pipeline complete in {total_time}s")
    return result

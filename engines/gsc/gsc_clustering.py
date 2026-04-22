"""
GSC Phase 2 — Keyword Clustering Engine
Uses HDBSCAN for auto-cluster detection + LLM for cluster naming.

Pipeline:
  1. Load embeddings from DB
  2. Run HDBSCAN (auto-detects cluster count)
  3. Name clusters via LLM (batch: top 10 keywords per cluster)
  4. Store cluster assignments in DB
"""
import json
import re
import logging
import numpy as np
from collections import defaultdict

from core.ai_config import AIRouter
from . import gsc_db
from .gsc_embeddings import load_vectors

log = logging.getLogger(__name__)


def _run_hdbscan(vectors: np.ndarray, min_cluster_size: int = 5) -> np.ndarray:
    """Run HDBSCAN clustering. Returns label array (–1 = noise)."""
    import hdbscan
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(vectors)
    return labels


def _name_clusters_llm(clusters: dict[int, list[str]]) -> dict[int, str]:
    """
    Name clusters using LLM. Sends top 10 keywords per cluster.
    Returns {cluster_id: cluster_name}.
    """
    if not clusters:
        return {}

    # Build prompt for all clusters at once (cheaper than per-cluster)
    parts = []
    for cid, kws in sorted(clusters.items()):
        sample = kws[:10]
        parts.append(f"Cluster {cid}:\n" + "\n".join(f"  - {k}" for k in sample))

    prompt = f"""You are an SEO expert. Name each keyword cluster with a short label (2-4 words max).
Focus on the shared topic/intent of the keywords.

{chr(10).join(parts)}

Return ONLY a JSON object mapping cluster ID to name:
{{"0": "Health Benefits", "1": "Pricing & Bulk", ...}}"""

    text = AIRouter.call(prompt, system="You are an SEO keyword clustering expert. Respond only with valid JSON.", temperature=0.2)
    if not text:
        return {cid: f"Cluster {cid}" for cid in clusters}

    try:
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
        data = json.loads(cleaned)
        result = {}
        for cid in clusters:
            name = data.get(str(cid), f"Cluster {cid}")
            result[cid] = str(name).strip()[:50]
        return result
    except (json.JSONDecodeError, ValueError) as e:
        log.warning(f"[GSC Cluster] LLM naming failed: {e}")
        return {cid: f"Cluster {cid}" for cid in clusters}


def cluster_keywords(project_id: str, min_cluster_size: int = 5) -> dict:
    """
    Full clustering pipeline:
    1. Load embeddings
    2. HDBSCAN
    3. LLM naming
    4. Store in DB
    5. Update processed keywords with cluster info

    Returns: {clusters: N, noise: N, keywords_clustered: N, cluster_names: [...]}
    """
    keywords, vectors = load_vectors(project_id)
    if len(keywords) < min_cluster_size:
        log.warning(f"[GSC Cluster] Too few keywords ({len(keywords)}) for clustering")
        return {"clusters": 0, "noise": 0, "keywords_clustered": 0, "cluster_names": []}

    log.info(f"[GSC Cluster] Clustering {len(keywords)} keywords")
    labels = _run_hdbscan(vectors, min_cluster_size=min_cluster_size)

    # Group keywords by cluster
    cluster_groups: dict[int, list[str]] = defaultdict(list)
    noise_count = 0
    for kw, label in zip(keywords, labels):
        if label == -1:
            noise_count += 1
        else:
            cluster_groups[int(label)].append(kw)

    log.info(f"[GSC Cluster] Found {len(cluster_groups)} clusters, {noise_count} noise keywords")

    # Name clusters via LLM
    cluster_names = _name_clusters_llm(cluster_groups)

    # Map keywords to pillar from processed data
    processed = gsc_db.get_processed_keywords(project_id)
    kw_pillar = {kw["keyword"]: kw.get("pillar", "") for kw in processed}

    # Store in DB
    gsc_db.clear_clusters(project_id)
    db_rows = []
    for cid, kws in cluster_groups.items():
        name = cluster_names.get(cid, f"Cluster {cid}")
        for kw in kws:
            db_rows.append({
                "keyword": kw,
                "cluster_id": cid,
                "cluster_name": name,
                "pillar": kw_pillar.get(kw),
            })
    if db_rows:
        gsc_db.upsert_clusters(project_id, db_rows)

    # Update processed keywords
    updates = [{"keyword": r["keyword"], "cluster_name": r["cluster_name"],
                "cluster_id": r["cluster_id"]} for r in db_rows]
    if updates:
        gsc_db.update_processed_keywords_phase2(project_id, updates)

    names_list = sorted(set(cluster_names.values()))
    log.info(f"[GSC Cluster] Stored {len(db_rows)} cluster assignments")
    return {
        "clusters": len(cluster_groups),
        "noise": noise_count,
        "keywords_clustered": len(db_rows),
        "cluster_names": names_list,
    }

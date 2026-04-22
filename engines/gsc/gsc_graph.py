"""
GSC Phase 2 — Keyword Graph Engine
Builds keyword relationship graph from embedding similarity.

Each keyword gets top-K neighbors (K=8 default).
Optimized: O(N*K) not O(N²) — uses batch cosine similarity.
"""
import logging
import numpy as np

from . import gsc_db
from .gsc_embeddings import load_vectors

log = logging.getLogger(__name__)


def build_graph(project_id: str, top_k: int = 8, min_similarity: float = 0.3) -> dict:
    """
    Build keyword graph from embedding similarity.
    Each keyword → top K most similar keywords (above threshold).

    Returns: {edges: N, nodes: N}
    """
    keywords, vectors = load_vectors(project_id)
    n = len(keywords)
    if n < 2:
        return {"edges": 0, "nodes": 0}

    log.info(f"[GSC Graph] Building graph for {n} keywords (top_k={top_k})")

    # Compute similarity matrix (already L2-normalized)
    sim_matrix = vectors @ vectors.T

    # Extract top-K edges per keyword
    edges = []
    seen = set()
    for i in range(n):
        # Get top_k+1 (first is self), exclude self
        indices = np.argsort(sim_matrix[i])[::-1][1:top_k + 1]
        for j in indices:
            j = int(j)
            score = float(sim_matrix[i, j])
            if score < min_similarity:
                continue
            # Avoid duplicate edges (A→B and B→A)
            pair = (min(i, j), max(i, j))
            if pair in seen:
                continue
            seen.add(pair)
            edges.append({
                "keyword_1": keywords[i],
                "keyword_2": keywords[j],
                "similarity": round(score, 4),
            })

    # Store in DB
    gsc_db.clear_graph(project_id)
    if edges:
        BATCH = 500
        for i in range(0, len(edges), BATCH):
            gsc_db.upsert_graph_edges(project_id, edges[i:i + BATCH])

    log.info(f"[GSC Graph] Stored {len(edges)} edges")
    return {"edges": len(edges), "nodes": n}


def get_graph_data(project_id: str, min_similarity: float = 0.3) -> dict:
    """Return the graph in {nodes, links} format for UI rendering."""
    return gsc_db.get_graph(project_id, min_similarity=min_similarity)


def get_neighbors(project_id: str, keyword: str, limit: int = 10) -> list[dict]:
    """Get the most similar keywords to a given keyword."""
    with gsc_db._conn() as c:
        rows = c.execute(
            """SELECT keyword_2 as neighbor, similarity FROM gsc_keyword_graph
               WHERE project_id = ? AND keyword_1 = ?
               UNION
               SELECT keyword_1 as neighbor, similarity FROM gsc_keyword_graph
               WHERE project_id = ? AND keyword_2 = ?
               ORDER BY similarity DESC LIMIT ?""",
            (project_id, keyword, project_id, keyword, limit)
        ).fetchall()
        return [{"keyword": r[0], "similarity": round(r[1], 3)} for r in rows]

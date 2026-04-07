"""
kw2 Phase 4b — Semantic Keyword Clustering.

Uses sentence-transformers (all-MiniLM-L6-v2) for embeddings.
Greedy centroid algorithm: no predefined K, dynamic cluster count.
"""
import json
import logging
import numpy as np

from engines.kw2.constants import (
    EMBEDDING_MODEL, CLUSTER_SIMILARITY_THRESHOLD, CLUSTER_NAME_MIN_SIZE,
)
from engines.kw2.prompts import CLUSTER_NAME_SYSTEM, CLUSTER_NAME_USER
from engines.kw2.ai_caller import kw2_ai_call
from engines.kw2 import db

log = logging.getLogger("kw2.clusterer")

# Lazy-loaded model
_model = None


def _get_model():
    """Lazy-load sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL)
        log.info(f"Loaded embedding model: {EMBEDDING_MODEL}")
    return _model


class KeywordClusterer:
    """Phase 4b: Cluster validated keywords using semantic embeddings."""

    def cluster(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
    ) -> dict:
        """
        Cluster all scored keywords by pillar using greedy centroid.

        Returns: {clusters_total, by_pillar, keywords_clustered, avg_cluster_size}
        """
        keywords = db.load_validated_keywords(session_id)
        if not keywords:
            return {"clusters_total": 0, "by_pillar": {}, "keywords_clustered": 0}

        # Group by pillar
        by_pillar: dict[str, list[dict]] = {}
        for kw in keywords:
            pillar = kw.get("pillar", "general")
            by_pillar.setdefault(pillar, []).append(kw)

        total_clusters = 0
        pillar_stats = {}
        all_cluster_records = []

        model = _get_model()

        for pillar, pillar_kws in by_pillar.items():
            if not pillar_kws:
                continue

            # Sort by final_score desc
            pillar_kws.sort(key=lambda x: x.get("final_score", 0), reverse=True)

            # Encode keywords
            texts = [kw["keyword"] for kw in pillar_kws]
            embeddings = model.encode(texts, show_progress_bar=False)

            # Greedy centroid clustering
            clusters = self._greedy_centroid(embeddings, pillar_kws)

            # Name clusters + persist
            for cluster_idx, cluster_data in enumerate(clusters):
                cluster_kws = cluster_data["keywords"]
                cluster_embs = cluster_data["embeddings"]

                # Representative = highest final_score
                rep = max(cluster_kws, key=lambda x: x.get("final_score", 0))

                # Name via AI only for large clusters
                if len(cluster_kws) > CLUSTER_NAME_MIN_SIZE:
                    top5 = [kw["keyword"] for kw in cluster_kws[:5]]
                    name = self._ai_name_cluster(top5, ai_provider)
                else:
                    name = rep["keyword"]

                # Build cluster record
                keyword_ids = [kw["id"] for kw in cluster_kws]
                avg_score = sum(kw.get("final_score", 0) for kw in cluster_kws) / len(cluster_kws)

                all_cluster_records.append({
                    "pillar": pillar,
                    "cluster_name": name,
                    "keyword_ids": keyword_ids,
                    "top_keyword": rep["keyword"],
                    "avg_score": round(avg_score, 4),
                })

                # Update keywords with cluster name
                conn = db.get_conn()
                try:
                    for kid in keyword_ids:
                        conn.execute(
                            "UPDATE kw2_validated_keywords SET cluster=? WHERE id=?",
                            (name, kid),
                        )
                    conn.commit()
                finally:
                    conn.close()

            total_clusters += len(clusters)
            pillar_stats[pillar] = len(clusters)

        # Bulk insert cluster records
        conn = db.get_conn()
        now = db._now()
        try:
            for rec in all_cluster_records:
                conn.execute(
                    """INSERT INTO kw2_clusters
                       (id, session_id, project_id, pillar, cluster_name, keyword_ids, top_keyword, avg_score, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (db._uid("cl_"), session_id, project_id,
                     rec["pillar"], rec["cluster_name"],
                     json.dumps(rec["keyword_ids"]),
                     rec["top_keyword"], rec["avg_score"], now),
                )
            conn.commit()
        finally:
            conn.close()

        db.update_session(session_id, phase4_done=1)

        clustered_count = sum(len(by_pillar[p]) for p in by_pillar)
        avg_size = clustered_count / total_clusters if total_clusters > 0 else 0

        return {
            "clusters_total": total_clusters,
            "by_pillar": pillar_stats,
            "keywords_clustered": clustered_count,
            "avg_cluster_size": round(avg_size, 1),
        }

    def _greedy_centroid(self, embeddings: np.ndarray, keywords: list[dict]) -> list[dict]:
        """
        Greedy centroid clustering.

        For each keyword (sorted by score desc):
          - Compute cosine sim to all existing cluster centroids
          - If max sim > threshold → join that cluster, update centroid
          - Else → new cluster
        """
        clusters = []

        for i, emb in enumerate(embeddings):
            best_sim = -1.0
            best_idx = -1

            for j, cluster in enumerate(clusters):
                sim = self._cosine_sim(emb, cluster["centroid"])
                if sim > best_sim:
                    best_sim = sim
                    best_idx = j

            if best_sim >= CLUSTER_SIMILARITY_THRESHOLD and best_idx >= 0:
                # Join existing cluster
                cluster = clusters[best_idx]
                cluster["keywords"].append(keywords[i])
                cluster["embeddings"].append(emb)
                # Update centroid (running average)
                cluster["centroid"] = np.mean(cluster["embeddings"], axis=0)
            else:
                # New cluster
                clusters.append({
                    "keywords": [keywords[i]],
                    "embeddings": [emb],
                    "centroid": emb.copy(),
                })

        return clusters

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _ai_name_cluster(self, keywords: list[str], provider: str) -> str:
        """Get AI-generated 2-4 word cluster name."""
        try:
            prompt = CLUSTER_NAME_USER.format(keywords_list=", ".join(keywords))
            name = kw2_ai_call(prompt, CLUSTER_NAME_SYSTEM, provider=provider)
            name = name.strip().strip('"\'').strip()
            if name and len(name.split()) <= 6:
                return name
        except Exception as e:
            log.warning(f"Cluster naming failed: {e}")
        return keywords[0] if keywords else "Unnamed"

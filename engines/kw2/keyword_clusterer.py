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
        # Load profile for business-aware cluster naming
        profile = db.load_business_profile(project_id) or {}
        universe = profile.get("universe", "Business")
        btype = profile.get("business_type", "")
        self._biz_context = f"{universe} ({btype})" if btype else universe

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

            # A6: Collect clusters needing AI names — batch all in 1 call at the end
            _clusters_for_ai: list[tuple[int, list[str], dict]] = []

            # Name clusters + persist
            pending_records = []
            for cluster_idx, cluster_data in enumerate(clusters):
                cluster_kws = cluster_data["keywords"]

                # Representative = highest final_score
                rep = max(cluster_kws, key=lambda x: x.get("final_score", 0))

                keyword_ids = [kw["id"] for kw in cluster_kws]
                avg_score = sum(kw.get("final_score", 0) for kw in cluster_kws) / len(cluster_kws)

                pending_records.append({
                    "pillar": pillar,
                    "cluster_name": None,   # filled after batch naming
                    "keyword_ids": keyword_ids,
                    "top_keyword": rep["keyword"],
                    "avg_score": round(avg_score, 4),
                    "rep_keyword": rep["keyword"],
                    "needs_ai": len(cluster_kws) > CLUSTER_NAME_MIN_SIZE,
                    "top5": [kw["keyword"] for kw in cluster_kws[:5]],
                })

            # A6: Single-batch AI call for all large clusters in this pillar
            ai_needs = [(i, r) for i, r in enumerate(pending_records) if r["needs_ai"]]
            if ai_needs:
                batch_names = self._ai_batch_name_clusters(
                    [(r["top5"], r["rep_keyword"]) for (_, r) in ai_needs], ai_provider
                )
                for list_idx, (rec_idx, rec) in enumerate(ai_needs):
                    rec["cluster_name"] = batch_names[list_idx] if list_idx < len(batch_names) else rec["rep_keyword"]

            # Fill remaining (small clusters) with rep keyword
            for rec in pending_records:
                if rec["cluster_name"] is None:
                    rec["cluster_name"] = rec["rep_keyword"]

            # Update keyword cluster assignment + build final records
            conn = db.get_conn()
            try:
                for rec in pending_records:
                    name = rec["cluster_name"]
                    for kid in rec["keyword_ids"]:
                        conn.execute(
                            "UPDATE kw2_validated_keywords SET cluster=? WHERE id=?",
                            (name, kid),
                        )
                conn.commit()
            finally:
                conn.close()

            for rec in pending_records:
                all_cluster_records.append({
                    "pillar": rec["pillar"],
                    "cluster_name": rec["cluster_name"],
                    "keyword_ids": rec["keyword_ids"],
                    "top_keyword": rec["top_keyword"],
                    "avg_score": rec["avg_score"],
                })

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

    def _ai_batch_name_clusters(
        self, clusters: list[tuple[list[str], str]], provider: str
    ) -> list[str]:
        """
        A6: Name ALL clusters needing AI in a SINGLE call (replaces N individual calls).

        clusters: list of (top5_keywords, fallback_rep_keyword)
        Returns: list of names in same order; falls back to rep_keyword on parse error.
        """
        if not clusters:
            return []

        fallbacks = [rep for (_, rep) in clusters]

        # Build compact batch prompt
        lines = []
        for i, (top5, _) in enumerate(clusters, 1):
            lines.append(f"{i}. {', '.join(top5[:4])}")
        batch_input = "\n".join(lines)

        system = (
            "You are an SEO strategist. Name keyword clusters with 2-4 words each. "
            "Return ONLY a JSON array of strings, one name per cluster, in order. "
            "No explanation. Only the JSON array."
        )
        biz_ctx = getattr(self, "_biz_context", "Business")
        prompt = (
            f"Business: {biz_ctx}\n\n"
            f"Name these {len(clusters)} keyword clusters (2-4 words each).\n"
            f"Use terminology relevant to this business.\n\n"
            f"{batch_input}\n\n"
            f"Return JSON array: [\"Name 1\", \"Name 2\", ...]"
        )

        try:
            raw = kw2_ai_call(prompt, system, provider=provider, max_tokens=400)
            from engines.kw2.ai_caller import kw2_extract_json
            result = kw2_extract_json(raw)
            if isinstance(result, list):
                names = []
                for i, name in enumerate(result):
                    name = str(name).strip().strip('"\'')
                    if name and len(name.split()) <= 6:
                        names.append(name)
                    else:
                        names.append(fallbacks[i] if i < len(fallbacks) else "Unnamed")
                # Pad with fallbacks if AI returned fewer names
                while len(names) < len(clusters):
                    names.append(fallbacks[len(names)])
                return names[:len(clusters)]
        except Exception as e:
            log.warning(f"[A6] Batch cluster naming failed: {e}")

        return fallbacks

    def _ai_name_cluster(self, keywords: list[str], provider: str) -> str:
        """Legacy single-cluster naming — kept for backward compatibility."""
        names = self._ai_batch_name_clusters([(keywords, keywords[0])], provider)
        return names[0] if names else (keywords[0] if keywords else "Unnamed")

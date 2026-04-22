"""
kw2 Deduplication Engine — Phase 6.

Three-pass deduplication:
1. Exact/near-exact: Levenshtein distance < threshold → mark as duplicate
2. Semantic: embedding cosine similarity > threshold → mark as duplicate
3. AI clustering: group unique questions into content topic clusters

After dedup, clusters are saved to kw2_content_clusters and
each question's content_cluster_id is updated.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2 import db
from engines.kw2.constants import EMBEDDING_MODEL

log = logging.getLogger("kw2.dedup_engine")

# Lazy-loaded embedding model — shared across calls within a process lifetime
_embed_model: Optional[object] = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
            log.info("[DedupEngine] Loaded embedding model: %s", EMBEDDING_MODEL)
        except Exception as exc:
            log.warning("[DedupEngine] Embedding model unavailable (%s) — semantic pass skipped", exc)
    return _embed_model


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors."""
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

CLUSTER_SYSTEM = (
    "You are a content taxonomist organising questions into topic clusters. "
    "Output ONLY valid JSON with no markdown fences."
)

CLUSTER_PROMPT = """BUSINESS: {universe}

QUESTIONS ({count} total post-dedup):
{questions_json}

Group these questions into logical content topic clusters.
Each cluster represents a coherent content publishing area.

Rules:
- Only create clusters relevant to this specific business
- No catch-all "other" cluster
- Each cluster: minimum 3 questions, maximum {max_per_cluster}
- Maximum {max_clusters} clusters
- Assign every question to exactly one cluster

Return ONLY this JSON:
{{
  "clusters": [
    {{
      "cluster_name": "",
      "description": "",
      "pillar": "",
      "question_ids": []
    }}
  ]
}}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


def _levenshtein_ratio(a: str, b: str) -> float:
    """Simple normalised Levenshtein similarity (0–1, higher = more similar)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    # DP matrix
    try:
        dp = list(range(lb + 1))
        for i in range(1, la + 1):
            prev = dp[:]
            dp[0] = i
            for j in range(1, lb + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev[j - 1] + cost)
        dist = dp[lb]
        return 1.0 - dist / max(la, lb)
    except Exception:
        return 0.0


class DedupEngine:
    """Phase 6: Deduplicate questions and cluster into content topics."""

    def run_dedup(
        self, session_id: str, threshold: float = 0.75,
        semantic_threshold: float = 0.82,
    ) -> dict:
        """
        Mark near-duplicate questions using two passes:
        1. Levenshtein similarity > threshold  (fast string match)
        2. Embedding cosine similarity > semantic_threshold  (semantic match)
        Lower-scored duplicates are flagged with is_duplicate=1.
        Returns counts of duplicates found.
        """
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT id, question, final_score FROM kw2_intelligence_questions
                   WHERE session_id=? AND is_duplicate=0
                   ORDER BY final_score DESC""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        questions = [dict(r) for r in rows]
        seen: list[dict] = []
        duplicates: list[tuple[str, str]] = []  # (dup_id, original_id)

        # Pass 1 — Levenshtein (string-level)
        for q in questions:
            text = (q.get("question") or "").lower().strip()
            found_dup = False
            for prev in seen:
                prev_text = (prev.get("question") or "").lower().strip()
                sim = _levenshtein_ratio(text, prev_text)
                if sim >= threshold:
                    duplicates.append((q["id"], prev["id"]))
                    found_dup = True
                    break
            if not found_dup:
                seen.append(q)

        lev_removed = len(duplicates)

        # Pass 2 — Semantic (embedding cosine similarity)
        semantic_removed = 0
        model = _get_embed_model()
        if model is not None and len(seen) > 1:
            try:
                texts = [(q.get("question") or "").strip() for q in seen]
                embeddings: np.ndarray = model.encode(
                    texts, batch_size=64, show_progress_bar=False,
                    convert_to_numpy=True, normalize_embeddings=True,
                )
                # Lower-triangular pairwise similarity scan (O(n²) but n≤500 is fine)
                sem_dups: list[tuple[str, str]] = []
                sem_dup_ids: set[str] = set()
                for i in range(1, len(seen)):
                    if seen[i]["id"] in sem_dup_ids:
                        continue
                    for j in range(i):
                        if seen[j]["id"] in sem_dup_ids:
                            continue
                        # Embeddings are L2-normalised → dot == cosine
                        sim = float(np.dot(embeddings[i], embeddings[j]))
                        if sim >= semantic_threshold:
                            sem_dups.append((seen[i]["id"], seen[j]["id"]))
                            sem_dup_ids.add(seen[i]["id"])
                            semantic_removed += 1
                            break
                duplicates.extend(sem_dups)
                # Remove semantic dups from seen list
                seen = [q for q in seen if q["id"] not in sem_dup_ids]
            except Exception as exc:
                log.warning("[DedupEngine] Semantic pass failed: %s", exc)

        if duplicates:
            conn = db.get_conn()
            try:
                for dup_id, orig_id in duplicates:
                    conn.execute(
                        "UPDATE kw2_intelligence_questions SET is_duplicate=1, duplicate_of=? WHERE id=?",
                        (orig_id, dup_id),
                    )
                conn.commit()
            finally:
                conn.close()

        log.info(
            "[DedupEngine] session=%s lev_removed=%d semantic_removed=%d unique=%d",
            session_id, lev_removed, semantic_removed, len(seen),
        )
        return {
            "original_count": len(questions),
            "unique_count": len(seen),
            "duplicates_removed": len(duplicates),
            "levenshtein_removed": lev_removed,
            "semantic_removed": semantic_removed,
        }

    def run_clustering(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
        max_clusters: int = 30,
        max_per_cluster: int = 200,
        batch_size: int = 200,
    ) -> dict:
        """
        Cluster non-duplicate questions into topic clusters via AI.
        Saves clusters to kw2_content_clusters and updates each question's
        content_cluster_id.
        """
        profile = db.load_business_profile(project_id)
        universe = (profile.get("universe", "") if profile else "") or "Business"

        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT id, question, module_code FROM kw2_intelligence_questions
                   WHERE session_id=? AND is_duplicate=0
                   ORDER BY business_relevance DESC, final_score DESC
                   LIMIT ?""",
                (session_id, batch_size),
            ).fetchall()
        finally:
            conn.close()

        questions = [dict(r) for r in rows]
        if not questions:
            return {"clusters_created": 0, "questions_clustered": 0}

        questions_json = json.dumps(
            [{"id": q["id"], "question": q["question"]} for q in questions],
            ensure_ascii=False,
        )

        prompt = CLUSTER_PROMPT.format(
            universe=universe,
            count=len(questions),
            questions_json=questions_json[:6000],
            max_per_cluster=max_per_cluster,
            max_clusters=max_clusters,
        )

        resp = kw2_ai_call(
            prompt, CLUSTER_SYSTEM, provider=ai_provider, temperature=0.3,
            session_id=session_id, project_id=project_id, task="dedup_cluster",
        )
        result = kw2_extract_json(resp)
        clusters = []
        if isinstance(result, dict):
            clusters = result.get("clusters", [])
        if not isinstance(clusters, list):
            clusters = []

        # Fallback: embedding-based K-means clustering when AI fails
        if not clusters:
            clusters = self._embedding_cluster_fallback(questions, max_clusters, universe)

        # Delete old clusters for this session
        conn = db.get_conn()
        try:
            conn.execute(
                "DELETE FROM kw2_content_clusters WHERE session_id=?", (session_id,)
            )
            conn.commit()
        finally:
            conn.close()

        clusters_created = 0
        questions_clustered = 0

        for cluster in clusters:
            if not isinstance(cluster, dict) or not cluster.get("cluster_name"):
                continue
            cluster_id = _uid("cc_")
            q_ids = cluster.get("question_ids", [])
            if not isinstance(q_ids, list):
                q_ids = []

            # Determine intent mix from question modules
            question_count = len(q_ids)
            conn = db.get_conn()
            try:
                conn.execute(
                    """INSERT INTO kw2_content_clusters
                       (id, session_id, project_id, cluster_name, description,
                        pillar, question_count, status, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        cluster_id, session_id, project_id,
                        str(cluster.get("cluster_name", ""))[:200],
                        str(cluster.get("description", ""))[:500],
                        str(cluster.get("pillar", ""))[:100],
                        question_count,
                        "active",
                        _now(),
                    ),
                )
                # Update each question's cluster reference
                for qid in q_ids:
                    conn.execute(
                        "UPDATE kw2_intelligence_questions SET content_cluster_id=? WHERE id=? AND session_id=?",
                        (cluster_id, qid, session_id),
                    )
                conn.commit()
            finally:
                conn.close()

            clusters_created += 1
            questions_clustered += question_count

        log.info(
            "[DedupEngine] Created %d clusters for %d questions",
            clusters_created, questions_clustered,
        )
        return {
            "clusters_created": clusters_created,
            "questions_clustered": questions_clustered,
        }

    def _embedding_cluster_fallback(
        self, questions: list[dict], max_clusters: int, universe: str,
    ) -> list[dict]:
        """
        Fallback clustering using K-means on sentence embeddings.
        Returns cluster dicts in the same format as AI clustering output.
        """
        model = _get_embed_model()
        if model is None or len(questions) < 3:
            return []

        try:
            from sklearn.cluster import KMeans

            texts = [(q.get("question") or "").strip() for q in questions]
            embeddings = model.encode(
                texts, batch_size=64, show_progress_bar=False,
                convert_to_numpy=True, normalize_embeddings=True,
            )

            n_clusters = min(max_clusters, max(2, len(questions) // 5))
            km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = km.fit_predict(embeddings)

            # Group questions by cluster label
            groups: dict[int, list[dict]] = {}
            for q, label in zip(questions, labels):
                groups.setdefault(int(label), []).append(q)

            clusters = []
            for label, members in sorted(groups.items()):
                if len(members) < 2:
                    continue
                # Pick the shortest question as a rough cluster name
                rep = min(members, key=lambda q: len(q.get("question", "")))
                name = (rep.get("question") or f"Cluster {label + 1}")[:100]
                clusters.append({
                    "cluster_name": name,
                    "description": f"Auto-clustered group of {len(members)} related questions",
                    "pillar": universe[:100],
                    "question_ids": [m["id"] for m in members],
                })

            log.info("[DedupEngine] Embedding fallback created %d clusters", len(clusters))
            return clusters
        except ImportError:
            log.warning("[DedupEngine] sklearn not installed — embedding clustering skipped")
            return []
        except Exception as exc:
            log.warning("[DedupEngine] Embedding cluster fallback failed: %s", exc)
            return []

    def list_clusters(self, session_id: str, hide_empty: bool = True) -> list[dict]:
        conn = db.get_conn()
        try:
            conds = ["session_id=?"]
            params: list = [session_id]
            if hide_empty:
                conds.append("question_count > 0")
            rows = conn.execute(
                f"""SELECT * FROM kw2_content_clusters
                   WHERE {' AND '.join(conds)} ORDER BY question_count DESC""",
                params,
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["name"] = d.get("cluster_name", "")
                result.append(d)
            return result
        finally:
            conn.close()

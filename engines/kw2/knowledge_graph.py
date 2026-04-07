"""
kw2 Phase 6 — Knowledge Graph Builder.

Ported from P11_KnowledgeGraph. Builds edges (keyword→keyword,
keyword→pillar, pillar→universe) and persists to kw2_graph_edges.
"""
import logging
from engines.kw2 import db

log = logging.getLogger("kw2.graph")


class KnowledgeGraphBuilder:
    """Phase 6: Build SEO knowledge graph from clusters + tree."""

    def build(self, project_id: str, session_id: str) -> dict:
        """
        Build knowledge graph edges from validated keywords,
        clusters, and tree nodes. Persist to kw2_graph_edges.

        Returns summary dict.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")

        universe = profile.get("universe", "Business")
        pillars = profile.get("pillars", [])

        keywords = db.load_validated_keywords(session_id)
        if not keywords:
            return {"edges": 0}

        conn = db.get_conn()
        try:
            # Load clusters
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?", (session_id,)
            ).fetchall()

            # Clear existing edges
            conn.execute(
                "DELETE FROM kw2_graph_edges WHERE session_id=?", (session_id,)
            )

            now = db._now()
            edges = []

            # Build keyword→cluster edges
            kw_by_cluster: dict[str, list[dict]] = {}
            for kw in keywords:
                cl = kw.get("cluster", "unclustered")
                kw_by_cluster.setdefault(cl, []).append(kw)

            # Build cluster name→pillar map
            cluster_pillar: dict[str, str] = {}
            for cr in cluster_rows:
                crd = dict(cr)
                cluster_pillar[crd.get("cluster_name", "")] = crd.get("pillar", "")

            # Keyword → cluster (cluster membership)
            for cluster_name, ckws in kw_by_cluster.items():
                for kw in ckws:
                    edges.append((
                        db._uid("ge_"), session_id, project_id,
                        kw["keyword"], cluster_name,
                        "keyword_to_cluster", 1.0, now,
                    ))

            # Keyword → keyword (within cluster: sibling edges)
            for cluster_name, ckws in kw_by_cluster.items():
                sorted_kws = sorted(ckws, key=lambda x: x.get("final_score", 0), reverse=True)
                for i in range(len(sorted_kws)):
                    for j in range(i + 1, min(i + 4, len(sorted_kws))):
                        edges.append((
                            db._uid("ge_"), session_id, project_id,
                            sorted_kws[i]["keyword"], sorted_kws[j]["keyword"],
                            "sibling", 0.8, now,
                        ))

            # Cluster → pillar
            for cluster_name, pillar in cluster_pillar.items():
                if pillar:
                    edges.append((
                        db._uid("ge_"), session_id, project_id,
                        cluster_name, pillar,
                        "cluster_to_pillar", 1.0, now,
                    ))

            # Pillar → universe
            for pillar in pillars:
                edges.append((
                    db._uid("ge_"), session_id, project_id,
                    pillar, universe,
                    "pillar_to_universe", 1.0, now,
                ))

            # Cross-cluster edges (top keyword of one cluster → top keyword of another)
            top_per_cluster = {}
            for cluster_name, ckws in kw_by_cluster.items():
                if ckws:
                    best = max(ckws, key=lambda x: x.get("final_score", 0))
                    top_per_cluster[cluster_name] = best

            cluster_names = list(top_per_cluster.keys())
            for i in range(len(cluster_names)):
                for j in range(i + 1, len(cluster_names)):
                    c1, c2 = cluster_names[i], cluster_names[j]
                    p1 = cluster_pillar.get(c1, "")
                    p2 = cluster_pillar.get(c2, "")
                    # Only cross-link between different pillars
                    if p1 and p2 and p1 != p2:
                        kw1 = top_per_cluster[c1]["keyword"]
                        kw2 = top_per_cluster[c2]["keyword"]
                        edges.append((
                            db._uid("ge_"), session_id, project_id,
                            kw1, kw2,
                            "cross_cluster", 0.5, now,
                        ))

            # Bulk insert edges
            conn.executemany(
                """INSERT INTO kw2_graph_edges
                   (id, session_id, project_id, from_node, to_node, edge_type, weight, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                edges,
            )
            conn.commit()

            db.update_session(session_id, phase6_done=1)
            log.info(f"[Phase6] Knowledge graph built: {len(edges)} edges for {project_id}")

            return {
                "edges": len(edges),
                "pillars": len(pillars),
                "clusters": len(cluster_rows),
                "keywords": len(keywords),
            }
        finally:
            conn.close()

    def get_graph(self, session_id: str) -> dict:
        """Return graph edges grouped by type."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM kw2_graph_edges WHERE session_id=?", (session_id,)
            ).fetchall()
            result: dict[str, list[dict]] = {}
            for r in rows:
                d = dict(r)
                etype = d.get("edge_type", "unknown")
                result.setdefault(etype, []).append({
                    "from": d["from_node"],
                    "to": d["to_node"],
                    "weight": d.get("weight", 1.0),
                })
            return result
        finally:
            conn.close()

"""
kw2 Phase 7 — Internal Link Map Generator.

Ported from P12_InternalLinking. Generates internal link suggestions
across 6 link types and persists to kw2_internal_links.
"""
import logging
from engines.kw2 import db

log = logging.getLogger("kw2.linker")

INTENT_CTA = {
    "purchase": "buy",
    "transactional": "buy",
    "commercial": "compare",
    "informational": "learn more about",
    "local": "find near you",
    "comparison": "compare",
    "wholesale": "order",
}


class InternalLinker:
    """Phase 7: Generate internal link map from tree + graph."""

    def build(self, project_id: str, session_id: str) -> dict:
        """
        Generate internal link suggestions. Persists to kw2_internal_links.

        Link types:
        - keyword_to_pillar: every keyword page → its pillar page
        - sibling: adjacent keywords in same cluster
        - cross_cluster: top keywords across different pillars
        - cluster_to_pillar: cluster landing → pillar landing
        - pillar_to_product: pillar → main product page
        - location: location-based hub→spoke linking

        Returns summary dict.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")

        universe = profile.get("universe", "Business")
        pillars = profile.get("pillars", [])
        domain = profile.get("domain", "")

        keywords = db.load_validated_keywords(session_id)
        if not keywords:
            return {"links": 0}

        conn = db.get_conn()
        try:
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?", (session_id,)
            ).fetchall()

            # Clear existing links
            conn.execute(
                "DELETE FROM kw2_internal_links WHERE session_id=?", (session_id,)
            )

            now = db._now()
            links = []

            # Group keywords by pillar and cluster
            kw_by_pillar: dict[str, list[dict]] = {}
            kw_by_cluster: dict[str, list[dict]] = {}
            for kw in keywords:
                p = kw.get("pillar", "general")
                c = kw.get("cluster", "unclustered")
                kw_by_pillar.setdefault(p, []).append(kw)
                kw_by_cluster.setdefault(c, []).append(kw)

            def _slug(text: str) -> str:
                return text.lower().strip().replace(" ", "-").replace("'", "")

            # 1. Keyword → pillar links
            for pillar in pillars:
                pillar_url = f"/{_slug(universe)}/{_slug(pillar)}"
                pkws = kw_by_pillar.get(pillar, [])
                for kw in pkws:
                    kw_url = f"/{_slug(universe)}/{_slug(kw['keyword'])}"
                    intent = kw.get("intent", "informational")
                    links.append((
                        db._uid("il_"), session_id, project_id,
                        kw_url, pillar_url,
                        pillar, "body",
                        intent, "keyword_to_pillar", now,
                    ))

            # 2. Sibling links (within same cluster)
            for cluster_name, ckws in kw_by_cluster.items():
                sorted_kws = sorted(ckws, key=lambda x: x.get("final_score", 0), reverse=True)
                for i in range(len(sorted_kws)):
                    kw_url = f"/{_slug(universe)}/{_slug(sorted_kws[i]['keyword'])}"
                    # Link to previous
                    if i > 0:
                        prev_url = f"/{_slug(universe)}/{_slug(sorted_kws[i-1]['keyword'])}"
                        links.append((
                            db._uid("il_"), session_id, project_id,
                            kw_url, prev_url,
                            sorted_kws[i - 1]["keyword"], "related-section",
                            "", "sibling", now,
                        ))
                    # Link to next
                    if i < len(sorted_kws) - 1:
                        next_url = f"/{_slug(universe)}/{_slug(sorted_kws[i+1]['keyword'])}"
                        links.append((
                            db._uid("il_"), session_id, project_id,
                            kw_url, next_url,
                            sorted_kws[i + 1]["keyword"], "related-section",
                            "", "sibling", now,
                        ))

            # 3. Cluster → pillar links
            cluster_pillar_map: dict[str, str] = {}
            for cr in cluster_rows:
                crd = dict(cr)
                cn = crd.get("cluster_name", "")
                cp = crd.get("pillar", "")
                cluster_pillar_map[cn] = cp
                if cp:
                    pillar_url = f"/{_slug(universe)}/{_slug(cp)}"
                    links.append((
                        db._uid("il_"), session_id, project_id,
                        f"/{_slug(universe)}/cluster/{_slug(cn)}", pillar_url,
                        cp, "navigation",
                        "", "cluster_to_pillar", now,
                    ))

            # 4. Pillar → product (main CTA link)
            product_url = f"/{_slug(universe)}/products"
            for pillar in pillars:
                pillar_url = f"/{_slug(universe)}/{_slug(pillar)}"
                # Determine dominant intent for this pillar
                pkws = kw_by_pillar.get(pillar, [])
                intents = [kw.get("intent", "informational") for kw in pkws]
                dominant = max(set(intents), key=intents.count) if intents else "informational"
                cta = INTENT_CTA.get(dominant, "learn more about")
                links.append((
                    db._uid("il_"), session_id, project_id,
                    pillar_url, product_url,
                    f"{cta} {universe}", "conclusion",
                    dominant, "pillar_to_product", now,
                ))

            # 5. Cross-cluster authority links (high-score → low-score across pillars)
            top_per_cluster: dict[str, dict] = {}
            for cn, ckws in kw_by_cluster.items():
                if ckws:
                    top_per_cluster[cn] = max(ckws, key=lambda x: x.get("final_score", 0))

            cross_count = 0
            sorted_clusters = sorted(
                top_per_cluster.items(),
                key=lambda x: x[1].get("final_score", 0),
                reverse=True,
            )
            for i, (c1, kw1) in enumerate(sorted_clusters):
                if cross_count >= 30:
                    break
                for j in range(len(sorted_clusters) - 1, i, -1):
                    c2, kw2 = sorted_clusters[j]
                    p1 = cluster_pillar_map.get(c1, "")
                    p2 = cluster_pillar_map.get(c2, "")
                    if p1 and p2 and p1 != p2:
                        url1 = f"/{_slug(universe)}/{_slug(kw1['keyword'])}"
                        url2 = f"/{_slug(universe)}/{_slug(kw2['keyword'])}"
                        links.append((
                            db._uid("il_"), session_id, project_id,
                            url1, url2,
                            kw2["keyword"], "body",
                            "", "cross_cluster", now,
                        ))
                        cross_count += 1
                        break

            # 6. Location links (if geo data exists)
            geo = profile.get("geo_scope", "")
            if geo:
                loc_kws = [kw for kw in keywords if "near" in kw["keyword"].lower() or geo.lower() in kw["keyword"].lower()]
                hub_url = f"/{_slug(universe)}/{_slug(geo)}"
                for kw in loc_kws[:15]:
                    kw_url = f"/{_slug(universe)}/{_slug(kw['keyword'])}"
                    links.append((
                        db._uid("il_"), session_id, project_id,
                        hub_url, kw_url,
                        kw["keyword"], "body",
                        "local", "location", now,
                    ))

            # Bulk insert
            conn.executemany(
                """INSERT INTO kw2_internal_links
                   (id, session_id, project_id, from_page, to_page,
                    anchor_text, placement, intent, link_type, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                links,
            )
            conn.commit()

            db.update_session(session_id, phase7_done=1)
            log.info(f"[Phase7] Internal link map: {len(links)} links for {project_id}")

            # Summarize by type
            type_counts: dict[str, int] = {}
            for lnk in links:
                lt = lnk[8] if len(lnk) > 8 else "unknown"
                type_counts[lt] = type_counts.get(lt, 0) + 1

            return {"links": len(links), "by_type": type_counts}
        finally:
            conn.close()

    def get_links(self, session_id: str, link_type: str | None = None) -> list[dict]:
        """Return internal links, optionally filtered by link_type."""
        conn = db.get_conn()
        try:
            if link_type:
                rows = conn.execute(
                    "SELECT * FROM kw2_internal_links WHERE session_id=? AND link_type=?",
                    (session_id, link_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kw2_internal_links WHERE session_id=?",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

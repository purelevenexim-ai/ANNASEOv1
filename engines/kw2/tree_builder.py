"""
kw2 Phase 5 — Tree Builder + Top 100 Selection.

Builds a content tree: universe → pillar → cluster → keyword
Selects balanced top 100 using CATEGORY_CAPS.
Maps keywords to page types (product, category, b2b, local, blog).
Provides lazy AI explanation per keyword.
"""
import json
import logging

from engines.kw2.constants import CATEGORY_CAPS, NEGATIVE_PATTERNS
from engines.kw2.prompts import KEYWORD_EXPLAIN_SYSTEM, KEYWORD_EXPLAIN_USER
from engines.kw2.ai_caller import kw2_ai_call
from engines.kw2 import db

log = logging.getLogger("kw2.tree")


class TreeBuilder:
    """Phase 5: Build keyword content tree + balanced top-100 selection."""

    def build_tree(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
    ) -> dict:
        """
        Build the full tree: universe → pillars → clusters → keywords.
        Selects balanced top 100. Persists to kw2_tree_nodes.

        Returns nested tree dict.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")

        universe_name = profile.get("universe", "Business")
        pillars = profile.get("pillars", [])

        # Load clusters
        conn = db.get_conn()
        try:
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?", (session_id,)
            ).fetchall()
        finally:
            conn.close()

        # Load keywords
        keywords = db.load_validated_keywords(session_id)
        if not keywords:
            return {"universe": {"name": universe_name, "pillars": []}}

        # Select balanced top 100
        top100 = self._select_top100(keywords)
        top100_ids = {kw["id"] for kw in top100}

        # Phase-5 quality spot-check: flag any top-20 that slip past negative scope
        negative_scope = profile.get("negative_scope", [])
        if isinstance(negative_scope, str):
            try:
                negative_scope = json.loads(negative_scope) if negative_scope else []
            except Exception:
                negative_scope = []
        self._spot_check_top20(top100[:20], negative_scope, session_id)

        # Map pages for top100
        for kw in top100:
            kw["mapped_page"] = self._map_page(kw["keyword"], kw.get("intent", ""))

        # Update mapped_page in DB
        conn = db.get_conn()
        try:
            for kw in top100:
                conn.execute(
                    "UPDATE kw2_validated_keywords SET mapped_page=? WHERE id=?",
                    (kw["mapped_page"], kw["id"]),
                )
            conn.commit()
        finally:
            conn.close()

        # Mark top100 membership on ALL keywords for tree display
        for kw in keywords:
            kw["in_top100"] = kw["id"] in top100_ids
            if not kw.get("mapped_page"):
                kw["mapped_page"] = self._map_page(kw["keyword"], kw.get("intent", ""))

        # Build tree structure from ALL validated keywords (not just top100)
        tree = self._build_tree_structure(
            universe_name, pillars, cluster_rows, keywords, session_id, project_id
        )

        # Update session
        db.update_session(session_id, phase5_done=1, top100_count=len(top100))

        log.info(f"[Phase5] Built tree with {len(top100)} top keywords for {project_id}")
        return tree

    def get_top100(self, session_id: str, pillar: str | None = None) -> list[dict]:
        """Return balanced top 100 keywords (or filtered by pillar)."""
        keywords = db.load_validated_keywords(session_id)
        if pillar:
            keywords = [kw for kw in keywords if kw.get("pillar", "").lower() == pillar.lower()]
        top100 = self._select_top100(keywords)
        return [
            {
                "id": kw["id"],
                "keyword": kw["keyword"],
                "pillar": kw.get("pillar", ""),
                "cluster": kw.get("cluster", ""),
                "intent": kw.get("intent", ""),
                "final_score": kw.get("final_score", 0),
                "mapped_page": kw.get("mapped_page", ""),
                "source": kw.get("source", ""),
                "spot_check_warning": kw.get("spot_check_warning"),
            }
            for kw in top100
        ]

    def get_tree(self, session_id: str) -> dict:
        """Assemble cached tree from kw2_tree_nodes."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM kw2_tree_nodes WHERE session_id=? ORDER BY node_type, score DESC",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return {}

        nodes = [dict(r) for r in rows]
        return self._assemble_nested(nodes, session_id)

    def explain_keyword(self, keyword_id: str, ai_provider: str = "auto") -> str:
        """Lazy-load and cache AI explanation for a keyword."""
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM kw2_validated_keywords WHERE id=?", (keyword_id,)
            ).fetchone()
            if not row:
                return "Keyword not found."

            # Return cached explanation if exists
            existing = row["ai_explanation"]
            if existing:
                return existing

            # Load profile for universe name
            profile = db.load_business_profile(row["project_id"])
            universe = profile.get("universe", "business") if profile else "business"

            prompt = KEYWORD_EXPLAIN_USER.format(
                keyword=row["keyword"],
                universe=universe,
                intent=row["intent"] or "unknown",
                score=row["final_score"] or 0,
            )
            explanation = kw2_ai_call(prompt, KEYWORD_EXPLAIN_SYSTEM, provider=ai_provider)
            explanation = explanation.strip()

            # Cache
            conn.execute(
                "UPDATE kw2_validated_keywords SET ai_explanation=? WHERE id=?",
                (explanation, keyword_id),
            )
            conn.commit()
            return explanation
        finally:
            conn.close()

    def get_dashboard(self, project_id: str, session_id: str) -> dict:
        """Aggregate stats for the kw2 dashboard."""
        session = db.get_session(session_id)
        if not session:
            return {}

        keywords = db.load_validated_keywords(session_id)

        # Category breakdown
        cats = {cat: 0 for cat in CATEGORY_CAPS}
        for kw in keywords:
            cat = self._categorize_keyword(kw["keyword"])
            cats[cat] = cats.get(cat, 0) + 1

        return {
            "session_id": session_id,
            "universe_count": session.get("universe_count", 0),
            "validated_count": session.get("validated_count", 0),
            "top100_count": session.get("top100_count", 0),
            "phase_statuses": {
                f"phase{i}_done": session.get(f"phase{i}_done", 0) for i in range(1, 10)
            },
            "category_breakdown": cats,
        }

    # ── Private helpers ──────────────────────────────────────────────────

    def _spot_check_top20(
        self, top20: list[dict], negative_scope: list[str], session_id: str
    ) -> None:
        """
        Rule-based quality spot-check on the top-20 keywords of the top-100 selection.
        Flags any keyword that matches NEGATIVE_PATTERNS or the session's negative_scope.
        Writes a warning string to kw2_validated_keywords.spot_check_warning (advisory only,
        no keywords are removed).
        """
        if not top20:
            return

        # Build combined negative pattern set
        neg_patterns = set(p.lower() for p in NEGATIVE_PATTERNS)
        neg_patterns.update(p.lower() for p in (negative_scope or []))

        updates = []
        for kw in top20:
            text = kw.get("keyword", "").lower()
            matched = [p for p in neg_patterns if p and p in text]
            if matched:
                reason = f"Contains negative-scope term(s): {', '.join(matched[:3])}"
                updates.append((reason, kw["id"]))
                log.warning(
                    "[Phase5/SpotCheck] Top-20 keyword flagged (warning only): "
                    "'%s' — %s", kw.get("keyword"), reason
                )
            else:
                # Clear any stale warning from a previous run
                updates.append((None, kw["id"]))

        if not updates:
            return

        conn = db.get_conn()
        try:
            conn.executemany(
                "UPDATE kw2_validated_keywords SET spot_check_warning=? WHERE id=?",
                updates,
            )
            conn.commit()
        finally:
            conn.close()

    def _select_top100(self, keywords: list[dict]) -> list[dict]:
        """Select balanced top 100 using CATEGORY_CAPS."""
        keywords.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        counts = {cat: 0 for cat in CATEGORY_CAPS}
        selected = []

        for kw in keywords:
            if len(selected) >= 100:
                break
            cat = self._categorize_keyword(kw["keyword"])
            cap = CATEGORY_CAPS.get(cat, 5)
            if counts[cat] < cap:
                counts[cat] += 1
                selected.append(kw)

        # If we haven't hit 100, fill from remaining (ignore caps)
        if len(selected) < 100:
            selected_ids = {kw["id"] for kw in selected}
            for kw in keywords:
                if len(selected) >= 100:
                    break
                if kw["id"] not in selected_ids:
                    selected.append(kw)

        return selected

    def _categorize_keyword(self, keyword: str) -> str:
        """Map keyword to CATEGORY_CAPS bucket."""
        kw = keyword.lower()
        if ("buy" in kw or "order" in kw or "purchase" in kw) and "wholesale" not in kw and "bulk" not in kw:
            return "purchase"
        if "wholesale" in kw or "bulk" in kw:
            return "wholesale"
        if "price" in kw or "cost" in kw:
            return "price"
        if "best" in kw or " vs " in kw or "compare" in kw or "review" in kw:
            return "comparison"
        if "near me" in kw or "local" in kw:
            return "local"
        return "other"

    def _map_page(self, keyword: str, intent: str) -> str:
        """Rule-based page type mapping."""
        kw = keyword.lower()
        if "wholesale" in kw or "bulk" in kw:
            return "b2b_page"
        if ("buy" in kw or "order" in kw or "purchase" in kw) and "wholesale" not in kw:
            return "product_page"
        if " vs " in kw or "compare" in kw or intent == "comparison":
            return "blog_page"
        if "near me" in kw or intent == "local":
            return "local_page"
        if "price" in kw or "cost" in kw:
            return "category_page"
        return "category_page"

    def _build_tree_structure(
        self, universe_name: str, pillars: list[str],
        cluster_rows: list, top100: list[dict],
        session_id: str, project_id: str,
    ) -> dict:
        """Build tree nodes and persist to DB, return nested dict."""
        def _norm_pillar(value: str) -> str:
            return (value or "").strip().lower()

        now = db._now()
        conn = db.get_conn()
        try:
            # Clear existing tree for this session
            conn.execute("DELETE FROM kw2_tree_nodes WHERE session_id=?", (session_id,))

            # Universe node
            universe_id = db._uid("tn_")
            conn.execute(
                "INSERT INTO kw2_tree_nodes (id, session_id, project_id, node_type, label, parent_id, score, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (universe_id, session_id, project_id, "universe", universe_name, None, 0, now),
            )

            # Group keywords by pillar and keep a stable label per normalized key.
            tree_dict = {"name": universe_name, "type": "universe", "pillars": []}
            pillar_kws: dict[str, list[dict]] = {}
            pillar_label_by_norm: dict[str, str] = {}

            for kw in top100:
                raw_pillar = (kw.get("pillar") or "general").strip()
                norm = _norm_pillar(raw_pillar) or "general"
                pillar_kws.setdefault(norm, []).append(kw)
                if norm not in pillar_label_by_norm:
                    pillar_label_by_norm[norm] = raw_pillar or "general"

            # Preserve profile pillar order first, then append keyword-derived pillars.
            ordered_pillars: list[tuple[str, str]] = []
            seen_norm: set[str] = set()
            for pillar in (pillars or []):
                raw = (pillar or "").strip()
                if not raw:
                    continue
                norm = _norm_pillar(raw)
                if norm in seen_norm:
                    continue
                seen_norm.add(norm)
                ordered_pillars.append((raw, norm))

            for norm, label in pillar_label_by_norm.items():
                if norm not in seen_norm:
                    seen_norm.add(norm)
                    ordered_pillars.append((label, norm))

            has_keyword_pillars = bool(pillar_kws)

            for pillar_label, pillar_norm in ordered_pillars:
                pkws = pillar_kws.get(pillar_norm, [])
                if has_keyword_pillars and not pkws:
                    # Avoid empty display pillars when keyword pillars don't exactly match profile pillars.
                    continue

                pillar_id = db._uid("tn_")
                conn.execute(
                    "INSERT INTO kw2_tree_nodes (id, session_id, project_id, node_type, label, parent_id, score, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (pillar_id, session_id, project_id, "pillar", pillar_label, universe_id, 0, now),
                )

                # Group by cluster
                cluster_kws: dict[str, list[dict]] = {}
                for kw in pkws:
                    cl = kw.get("cluster", "unclustered")
                    cluster_kws.setdefault(cl, []).append(kw)

                pillar_dict = {"name": pillar_label, "type": "pillar", "clusters": []}
                for cluster_name, ckws in cluster_kws.items():
                    cluster_id = db._uid("tn_")
                    conn.execute(
                        "INSERT INTO kw2_tree_nodes (id, session_id, project_id, node_type, label, parent_id, score, created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (cluster_id, session_id, project_id, "cluster", cluster_name, pillar_id, 0, now),
                    )

                    cluster_dict = {"name": cluster_name, "type": "cluster", "keywords": []}
                    for kw in ckws:
                        kw_node_id = db._uid("tn_")
                        conn.execute(
                            "INSERT INTO kw2_tree_nodes (id, session_id, project_id, node_type, label, parent_id, keyword_id, mapped_page, score, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (kw_node_id, session_id, project_id, "keyword", kw["keyword"],
                             cluster_id, kw["id"], kw.get("mapped_page", ""), kw.get("final_score", 0), now),
                        )
                        cluster_dict["keywords"].append({
                            "name": kw["keyword"],
                            "type": "keyword",
                            "intent": kw.get("intent", ""),
                            "score": kw.get("final_score", 0),
                            "mapped_page": kw.get("mapped_page", ""),
                            "top100": kw.get("in_top100", False),
                        })
                    pillar_dict["clusters"].append(cluster_dict)
                tree_dict["pillars"].append(pillar_dict)

            conn.commit()
            return {"universe": tree_dict}
        finally:
            conn.close()

    def _assemble_nested(self, nodes: list[dict], session_id: str = "") -> dict:
        """Reconstruct nested tree dict from flat kw2_tree_nodes rows."""
        # Build intent lookup and top100 set from validated keywords
        intent_map: dict[str, str] = {}
        top100_ids: set[str] = set()
        if session_id:
            conn2 = db.get_conn()
            try:
                rows = conn2.execute(
                    "SELECT id, intent, final_score FROM kw2_validated_keywords "
                    "WHERE session_id=? AND (rejected IS NULL OR rejected != 1)",
                    (session_id,),
                ).fetchall()
                all_kws = [{"id": r["id"], "final_score": r["final_score"] or 0} for r in rows]
                top100 = self._select_top100(all_kws)
                top100_ids = {kw["id"] for kw in top100}
                intent_map = {r["id"]: r["intent"] or "" for r in rows}
            except Exception:
                pass
            finally:
                conn2.close()

        children: dict[str, list] = {}
        root = None

        for n in nodes:
            pid = n.get("parent_id")
            if pid:
                children.setdefault(pid, []).append(n)
            else:
                root = n

        if not root:
            return {}

        def build(node):
            result = {"name": node["label"], "type": node["node_type"]}
            if node["node_type"] == "keyword":
                result["score"] = node.get("score", 0)
                result["mapped_page"] = node.get("mapped_page", "")
                kw_id = node.get("keyword_id", "")
                result["intent"] = intent_map.get(kw_id, "")
                result["top100"] = kw_id in top100_ids
            kids = children.get(node["id"], [])
            if kids:
                key = {
                    "universe": "pillars",
                    "pillar": "clusters",
                    "cluster": "keywords",
                }.get(node["node_type"], "children")
                result[key] = [build(c) for c in kids]
            return result

        return {"universe": build(root)}

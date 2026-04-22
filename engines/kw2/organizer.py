"""
kw2 organizer — Super Phase 3: ORGANIZE.

Unified scoring + deep clustering refinement + relationship graph +
smart top-100 selection per pillar.

Replaces logic from: keyword_scorer.py, keyword_clusterer.py,
tree_builder.py (top-100), knowledge_graph.py.
"""
import json
import logging
import numpy as np
from collections import defaultdict

from engines.kw2 import db
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2.normalizer import canonical as _canonical
from engines.kw2.constants import (
    COMMERCIAL_BOOSTS, INTENT_WEIGHTS,
    EMBEDDING_MODEL, CLUSTER_SIMILARITY_THRESHOLD, CLUSTER_NAME_MIN_SIZE,
    TOP100_PILLAR_RATIO, TOP100_SUPPORTING_RATIO,
    MULTI_PILLAR_BONUS, CLUSTER_TOP_BONUS,
    REL_WEIGHT_SIBLING, REL_WEIGHT_CROSS_CLUSTER,
    REL_WEIGHT_CROSS_PILLAR, REL_WEIGHT_MODIFIER, REL_WEIGHT_VARIANT,
    TARGET_KW_PER_PILLAR, DEFAULT_INTENT_DISTRIBUTION,
)
from engines.kw2.prompts import (
    V2_CLUSTER_VALIDATE_SYSTEM, V2_CLUSTER_VALIDATE_USER,
    CLUSTER_NAME_SYSTEM, CLUSTER_NAME_USER,
)

log = logging.getLogger("kw2.organizer")

# Source → volume signal proxy
SOURCE_VOLUME = {
    "suggest": 0.70,
    "competitor": 0.60,
    "bi_competitor": 0.55,
    "ai_expand": 0.50,
    "rules": 0.40,
    "seeds": 0.35,
    "manual": 0.45,
}

# Lazy-loaded embedding model
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL)
        log.info("Loaded embedding model: %s", EMBEDDING_MODEL)
    return _model


class Organizer:
    """
    Super Phase 3 pipeline:
    1. Score all approved keywords
    2. Re-cluster with score-weighted embeddings
    3. Merge tiny clusters
    4. AI validate cluster boundaries
    5. Build relationship graph
    6. Smart top-100 selection per pillar
    """

    def organize(self, project_id: str, session_id: str,
                 ai_provider: str = "auto") -> dict:
        """Run the full organize pipeline. Returns summary."""
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("Business profile not found — run Phase 1 first")

        # Store business context for cluster naming prompts
        universe = profile.get("universe", "Business")
        btype = profile.get("business_type", "")
        aud = profile.get("audience", [])
        ctx_parts = [f"{universe} ({btype})" if btype else universe]
        if aud:
            ctx_parts.append(f"Audience: {', '.join(str(a) for a in aud[:3])}")
        self._profile_ctx_str = " | ".join(ctx_parts)

        pillars = profile.get("pillars", [])
        if isinstance(pillars, str):
            pillars = json.loads(pillars) if pillars else []

        intent_dist = profile.get("intent_distribution")
        if isinstance(intent_dist, str):
            intent_dist = json.loads(intent_dist) if intent_dist else None
        intent_dist = intent_dist or DEFAULT_INTENT_DISTRIBUTION

        target_per_pillar = profile.get("target_kw_count") or TARGET_KW_PER_PILLAR

        # Load approved keywords (from expand phase review)
        keywords = db.load_keywords(session_id, status="approved")
        if not keywords:
            # Also try 'candidate' if none approved yet (allow running without review)
            keywords = db.load_keywords(session_id, status="candidate")
        if not keywords:
            return {"error": "No keywords to organize", "scored": 0}

        log.info("organize: %d keywords, %d pillars", len(keywords), len(pillars))

        # Step 1: Score
        scored = self._score_all(keywords, pillars)
        log.info("organize: scored %d keywords", len(scored))

        # Step 2: Re-cluster with embeddings
        clusters = self._recluster(scored, pillars, ai_provider)
        log.info("organize: %d clusters", sum(len(v) for v in clusters.values()))

        # Step 3: Merge tiny clusters
        clusters = self._merge_tiny(clusters)

        # Step 4: AI validate cluster boundaries
        clusters = self._validate_clusters(clusters, ai_provider)

        # Step 5: Build relationship graph
        relations = self._build_relations(scored, clusters, pillars)
        log.info("organize: %d relations", len(relations))

        # Apply relationship bonus to scores
        self._apply_relation_bonus(scored, relations)

        # Step 6: Smart top-100 selection per pillar
        top100 = self._select_top100(scored, pillars, clusters,
                                     intent_dist, target_per_pillar)
        log.info("organize: %d top-100 across %d pillars",
                 sum(len(v) for v in top100.values()), len(top100))

        # Persist everything
        self._persist(session_id, project_id, scored, clusters, relations, top100)

        # Summary stats
        pillar_stats = {}
        for p in pillars:
            p_kws = [k for k in scored if p in k.get("pillars", [])]
            pillar_stats[p] = {
                "total": len(p_kws),
                "top100": len(top100.get(p, [])),
                "clusters": len(clusters.get(p, [])),
            }

        return {
            "scored": len(scored),
            "total_relations": len(relations),
            "pillar_stats": pillar_stats,
            "top100_total": sum(len(v) for v in top100.values()),
        }

    def organize_stream(self, project_id: str, session_id: str,
                        ai_provider: str = "auto"):
        """SSE generator for organize progress."""
        profile = db.load_business_profile(project_id)
        if not profile:
            yield _sse("error", {"message": "Business profile not found"})
            return

        pillars = profile.get("pillars", [])
        if isinstance(pillars, str):
            pillars = json.loads(pillars) if pillars else []

        intent_dist = profile.get("intent_distribution")
        if isinstance(intent_dist, str):
            intent_dist = json.loads(intent_dist) if intent_dist else None
        intent_dist = intent_dist or DEFAULT_INTENT_DISTRIBUTION
        target_per_pillar = profile.get("target_kw_count") or TARGET_KW_PER_PILLAR

        keywords = db.load_keywords(session_id, status="approved")
        if not keywords:
            keywords = db.load_keywords(session_id, status="candidate")
        if not keywords:
            yield _sse("error", {"message": "No keywords to organize"})
            return

        yield _sse("step", {"name": "scoring", "status": "running",
                            "total": len(keywords)})
        scored = self._score_all(keywords, pillars)
        yield _sse("step", {"name": "scoring", "status": "done",
                            "scored": len(scored)})

        yield _sse("step", {"name": "clustering", "status": "running"})
        clusters = self._recluster(scored, pillars, ai_provider)
        clusters = self._merge_tiny(clusters)
        cluster_count = sum(len(v) for v in clusters.values())
        yield _sse("step", {"name": "clustering", "status": "done",
                            "clusters": cluster_count})

        yield _sse("step", {"name": "cluster_validation", "status": "running"})
        clusters = self._validate_clusters(clusters, ai_provider)
        yield _sse("step", {"name": "cluster_validation", "status": "done"})

        yield _sse("step", {"name": "relations", "status": "running"})
        relations = self._build_relations(scored, clusters, pillars)
        self._apply_relation_bonus(scored, relations)
        yield _sse("step", {"name": "relations", "status": "done",
                            "count": len(relations)})

        yield _sse("step", {"name": "top100", "status": "running"})
        top100 = self._select_top100(scored, pillars, clusters,
                                     intent_dist, target_per_pillar)
        yield _sse("step", {"name": "top100", "status": "done",
                            "total": sum(len(v) for v in top100.values())})

        yield _sse("step", {"name": "persist", "status": "running"})
        self._persist(session_id, project_id, scored, clusters, relations, top100)
        yield _sse("step", {"name": "persist", "status": "done"})

        yield _sse("done", {
            "scored": len(scored),
            "total_relations": len(relations),
            "top100_total": sum(len(v) for v in top100.values()),
        })

    # ── Step 1: Score ─────────────────────────────────────────────────────

    def _score_all(self, keywords: list[dict],
                   pillars: list[str]) -> list[dict]:
        """Compute final_score with v2 bonuses."""
        for kw in keywords:
            ai_rel = float(kw.get("ai_relevance") or 0)
            intent = kw.get("intent", "unknown")
            sources = kw.get("sources", [])
            if isinstance(sources, str):
                sources = [sources]

            intent_weight = INTENT_WEIGHTS.get(intent, 0.3)

            # Volume signal: best source
            vol = max((SOURCE_VOLUME.get(s, 0.35) for s in sources), default=0.35)

            # Commercial boost
            commercial = self._commercial_score(kw["keyword"].lower())

            # Multi-pillar bonus
            kw_pillars = kw.get("pillars", [])
            multi_bonus = MULTI_PILLAR_BONUS if len(kw_pillars) > 1 else 0.0

            final = (
                (ai_rel * 0.30)
                + (intent_weight * 0.25)
                + (vol * 0.20)
                + (commercial * 0.15)
                + multi_bonus
            )
            kw["final_score"] = round(final, 4)
            kw["commercial_score"] = round(commercial, 4)

        return keywords

    def _commercial_score(self, keyword: str) -> float:
        total = 0.0
        for token, boost in COMMERCIAL_BOOSTS.items():
            if token in keyword:
                total += boost
        return min(total / 35.0, 1.0)

    # ── Step 2: Re-cluster ───────────────────────────────────────────────

    def _recluster(self, keywords: list[dict], pillars: list[str],
                   ai_provider: str) -> dict[str, list[dict]]:
        """Re-cluster keywords per pillar using embeddings."""
        by_pillar: dict[str, list[dict]] = defaultdict(list)
        for kw in keywords:
            for p in kw.get("pillars", []):
                by_pillar[p].append(kw)

        result: dict[str, list[dict]] = {}

        try:
            model = _get_model()
        except Exception:
            log.warning("Embedding model unavailable, using fallback clustering")
            return self._fallback_cluster(keywords, pillars)

        for pillar, p_kws in by_pillar.items():
            if not p_kws:
                continue

            p_kws.sort(key=lambda x: x.get("final_score", 0), reverse=True)
            texts = [kw["keyword"] for kw in p_kws]
            embeddings = model.encode(texts, show_progress_bar=False)

            clusters = self._greedy_centroid(embeddings, p_kws, pillar, ai_provider)
            result[pillar] = clusters

        return result

    def _greedy_centroid(self, embeddings, keywords: list[dict],
                         pillar: str, ai_provider: str) -> list[dict]:
        """Greedy centroid clustering with score-weighted centroids."""
        if len(keywords) == 0:
            return []

        threshold = CLUSTER_SIMILARITY_THRESHOLD
        clusters: list[dict] = []

        for i, kw in enumerate(keywords):
            emb = embeddings[i]
            best_sim = -1
            best_idx = -1

            for ci, cl in enumerate(clusters):
                sim = float(np.dot(emb, cl["centroid"]) / (
                    np.linalg.norm(emb) * np.linalg.norm(cl["centroid"]) + 1e-9
                ))
                if sim > best_sim:
                    best_sim = sim
                    best_idx = ci

            if best_sim >= threshold and best_idx >= 0:
                cl = clusters[best_idx]
                cl["keywords"].append(kw)
                cl["embeddings"].append(emb)
                # Score-weighted centroid update
                score = kw.get("final_score", 0.5)
                total_weight = cl.get("total_weight", 1.0) + score
                cl["centroid"] = (
                    cl["centroid"] * cl.get("total_weight", 1.0) + emb * score
                ) / total_weight
                cl["total_weight"] = total_weight
            else:
                clusters.append({
                    "keywords": [kw],
                    "embeddings": [emb],
                    "centroid": emb.copy(),
                    "total_weight": kw.get("final_score", 0.5),
                    "pillar": pillar,
                })

        # Name clusters
        for cl in clusters:
            texts = [k["keyword"] for k in cl["keywords"]]
            if len(texts) >= CLUSTER_NAME_MIN_SIZE:
                cl["name"] = self._ai_name_cluster(texts, ai_provider)
            else:
                cl["name"] = texts[0] if texts else "Cluster"
            cl["id"] = db._uid("cl_")

        # Drop embeddings before returning
        for cl in clusters:
            del cl["embeddings"]
            del cl["centroid"]
            del cl["total_weight"]

        return clusters

    def _fallback_cluster(self, keywords: list[dict],
                          pillars: list[str]) -> dict[str, list[dict]]:
        """Simple pillar-based clustering when embeddings unavailable."""
        result: dict[str, list[dict]] = {}
        for p in pillars:
            p_kws = [k for k in keywords if p in k.get("pillars", [])]
            if p_kws:
                result[p] = [{"id": db._uid("cl_"), "name": p,
                              "keywords": p_kws, "pillar": p}]
        return result

    def _ai_name_cluster(self, keywords: list[str],
                         ai_provider: str) -> str:
        biz_ctx = getattr(self, "_profile_ctx_str", "Business")
        prompt = CLUSTER_NAME_USER.format(
            keywords_list=", ".join(keywords[:20]),
            business_context=biz_ctx,
        )
        try:
            name = kw2_ai_call(prompt, CLUSTER_NAME_SYSTEM, provider=ai_provider)
            name = name.strip().strip('"').strip("'")
            if len(name) > 60:
                name = name[:60]
            return name or keywords[0]
        except Exception:
            return keywords[0]

    # ── Step 3: Merge tiny clusters ──────────────────────────────────────

    def _merge_tiny(self, clusters: dict[str, list[dict]],
                    min_size: int = 3) -> dict[str, list[dict]]:
        """Merge clusters with < min_size keywords into nearest neighbor."""
        for pillar, cls in clusters.items():
            if len(cls) <= 1:
                continue

            tiny = [c for c in cls if len(c["keywords"]) < min_size]
            big = [c for c in cls if len(c["keywords"]) >= min_size]

            if not big:
                # All tiny — keep the largest and merge rest into it
                big = [max(cls, key=lambda c: len(c["keywords"]))]
                tiny = [c for c in cls if c["id"] != big[0]["id"]]

            for tc in tiny:
                # Merge into first big cluster (simple heuristic)
                big[0]["keywords"].extend(tc["keywords"])
                log.debug("Merged tiny cluster '%s' (%d kws) into '%s'",
                          tc["name"], len(tc["keywords"]), big[0]["name"])

            clusters[pillar] = big

        return clusters

    # ── Step 4: AI validate clusters ─────────────────────────────────────

    def _validate_clusters(self, clusters: dict[str, list[dict]],
                           ai_provider: str) -> dict[str, list[dict]]:
        """AI validates cluster boundaries, splits if needed."""
        for pillar, cls in clusters.items():
            new_cls = []
            for cl in cls:
                if len(cl["keywords"]) < 5:
                    new_cls.append(cl)
                    continue

                kw_list = "\n".join(
                    f"- {k['keyword']}" for k in cl["keywords"][:30]
                )
                prompt = V2_CLUSTER_VALIDATE_USER.format(
                    cluster_name=cl["name"], keywords_list=kw_list
                )
                try:
                    raw = kw2_ai_call(prompt, V2_CLUSTER_VALIDATE_SYSTEM,
                                      provider=ai_provider)
                    result = kw2_extract_json(raw)
                    if not result:
                        new_cls.append(cl)
                        continue

                    # kw2_extract_json may return a list; unwrap first element
                    if isinstance(result, list):
                        result = result[0] if result else {}
                    if not isinstance(result, dict):
                        new_cls.append(cl)
                        continue

                    # Better name?
                    better_name = result.get("name", cl["name"])
                    if better_name:
                        cl["name"] = better_name

                    # Handle outliers
                    outliers = set(result.get("outliers", []))
                    if outliers:
                        cl["keywords"] = [
                            k for k in cl["keywords"]
                            if k["keyword"] not in outliers
                        ]

                    # Handle splits
                    subs = result.get("sub_clusters", [])
                    if not result.get("valid", True) and subs:
                        kw_map = {k["keyword"]: k for k in cl["keywords"]}
                        for sub in subs:
                            sub_kws = [
                                kw_map[kn] for kn in sub.get("keywords", [])
                                if kn in kw_map
                            ]
                            if sub_kws:
                                new_cls.append({
                                    "id": db._uid("cl_"),
                                    "name": sub.get("name", "Sub Cluster"),
                                    "keywords": sub_kws,
                                    "pillar": pillar,
                                })
                        # Add remaining (not in any sub-cluster)
                        used = set()
                        for sub in subs:
                            used.update(sub.get("keywords", []))
                        remaining = [
                            k for k in cl["keywords"]
                            if k["keyword"] not in used
                        ]
                        if remaining:
                            new_cls.append({
                                "id": cl["id"],
                                "name": cl["name"],
                                "keywords": remaining,
                                "pillar": pillar,
                            })
                    else:
                        new_cls.append(cl)

                except Exception as e:
                    log.warning("Cluster validation failed for '%s': %s",
                                cl["name"], e)
                    new_cls.append(cl)

            clusters[pillar] = new_cls

        return clusters

    # ── Step 5: Relationship graph ───────────────────────────────────────

    def _build_relations(self, keywords: list[dict],
                         clusters: dict[str, list[dict]],
                         pillars: list[str]) -> list[dict]:
        """Build relationship edges between keywords."""
        relations = []
        kw_by_id = {k["id"]: k for k in keywords}

        # Index: cluster_id → keyword ids
        cluster_kws: dict[str, list[str]] = {}
        kw_cluster: dict[str, str] = {}
        for pillar, cls in clusters.items():
            for cl in cls:
                cid = cl["id"]
                for k in cl["keywords"]:
                    cluster_kws.setdefault(cid, []).append(k["id"])
                    kw_cluster[k["id"]] = cid

        # 1. Sibling edges (within cluster, top keywords)
        for cid, kid_list in cluster_kws.items():
            sorted_kids = sorted(
                kid_list,
                key=lambda kid: kw_by_id.get(kid, {}).get("final_score", 0),
                reverse=True,
            )
            for i in range(min(len(sorted_kids), 10)):
                for j in range(i + 1, min(i + 4, len(sorted_kids))):
                    relations.append({
                        "source_id": sorted_kids[i],
                        "target_id": sorted_kids[j],
                        "relation_type": "sibling",
                        "weight": REL_WEIGHT_SIBLING,
                    })

        # 2. Cross-cluster edges (top keyword per cluster → top of neighboring clusters)
        for pillar, cls in clusters.items():
            tops = []
            for cl in cls:
                if cl["keywords"]:
                    best = max(cl["keywords"],
                               key=lambda k: k.get("final_score", 0))
                    tops.append(best)
            for i in range(len(tops)):
                for j in range(i + 1, len(tops)):
                    relations.append({
                        "source_id": tops[i]["id"],
                        "target_id": tops[j]["id"],
                        "relation_type": "cross_cluster",
                        "weight": REL_WEIGHT_CROSS_CLUSTER,
                    })

        # 3. Cross-pillar edges (bridge keywords connect pillars)
        bridge_kws = [k for k in keywords if len(k.get("pillars", [])) > 1]
        pillar_top: dict[str, list[dict]] = defaultdict(list)
        for k in keywords:
            for p in k.get("pillars", []):
                pillar_top[p].append(k)
        for p in pillar_top:
            pillar_top[p].sort(
                key=lambda x: x.get("final_score", 0), reverse=True
            )
            pillar_top[p] = pillar_top[p][:5]  # top 5 per pillar

        for bk in bridge_kws:
            for p in bk.get("pillars", []):
                for top_kw in pillar_top.get(p, [])[:3]:
                    if top_kw["id"] != bk["id"]:
                        relations.append({
                            "source_id": bk["id"],
                            "target_id": top_kw["id"],
                            "relation_type": "cross_pillar",
                            "weight": REL_WEIGHT_CROSS_PILLAR,
                        })

        # 4. Modifier edges (semantic parent detection via shared stems)
        kw_canonicals = {k["id"]: k.get("canonical", "") for k in keywords}
        for k1 in keywords:
            c1_tokens = set(k1.get("canonical", "").split())
            if len(c1_tokens) < 2:
                continue
            for k2 in keywords:
                if k1["id"] >= k2["id"]:
                    continue
                c2_tokens = set(k2.get("canonical", "").split())
                if c2_tokens and c2_tokens < c1_tokens:
                    # k2 is a subset of k1 → k2 modifies/extends k1
                    relations.append({
                        "source_id": k2["id"],
                        "target_id": k1["id"],
                        "relation_type": "modifier",
                        "weight": REL_WEIGHT_MODIFIER,
                    })

        # 5. Variant edges (same canonical)
        canon_groups: dict[str, list[str]] = defaultdict(list)
        for k in keywords:
            canon_groups[k.get("canonical", "")].append(k["id"])
        for canon, ids in canon_groups.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        relations.append({
                            "source_id": ids[i],
                            "target_id": ids[j],
                            "relation_type": "variant",
                            "weight": REL_WEIGHT_VARIANT,
                        })

        return relations

    def _apply_relation_bonus(self, keywords: list[dict],
                              relations: list[dict]) -> None:
        """Boost scores based on relationship centrality."""
        # Count connections per keyword
        connection_count: dict[str, float] = defaultdict(float)
        for r in relations:
            connection_count[r["source_id"]] += r["weight"]
            connection_count[r["target_id"]] += r["weight"]

        if not connection_count:
            return

        max_conn = max(connection_count.values())
        if max_conn == 0:
            return

        for kw in keywords:
            conn_score = connection_count.get(kw["id"], 0) / max_conn
            # Relationship bonus: up to 5% based on centrality
            kw["final_score"] = round(
                kw.get("final_score", 0) + (conn_score * 0.05), 4
            )

    # ── Step 6: Smart top-100 selection ──────────────────────────────────

    def _select_top100(self, keywords: list[dict], pillars: list[str],
                       clusters: dict[str, list[dict]],
                       intent_dist: dict, target_per_pillar: int,
                       ) -> dict[str, list[dict]]:
        """
        Select top keywords per pillar:
        - 60% pillar-specific (unique to this pillar)
        - 40% supporting (shared with other pillars, bridge keywords)
        - Ensure cluster coverage: at least 1 from each cluster
        - Ensure intent diversity: respect intent_distribution
        """
        pillar_target = int(target_per_pillar * TOP100_PILLAR_RATIO)
        support_target = int(target_per_pillar * TOP100_SUPPORTING_RATIO)

        result: dict[str, list[dict]] = {}

        for pillar in pillars:
            p_kws = [k for k in keywords if pillar in k.get("pillars", [])]
            if not p_kws:
                result[pillar] = []
                continue

            p_kws.sort(key=lambda x: x.get("final_score", 0), reverse=True)

            # Split: pillar-specific vs bridge
            exclusive = [k for k in p_kws if len(k.get("pillars", [])) == 1]
            shared = [k for k in p_kws if len(k.get("pillars", [])) > 1]

            selected: list[dict] = []
            selected_ids: set[str] = set()

            # Phase A: Ensure cluster coverage (1 per cluster)
            pillar_clusters = clusters.get(pillar, [])
            for cl in pillar_clusters:
                if cl["keywords"]:
                    best = max(cl["keywords"],
                               key=lambda k: k.get("final_score", 0))
                    if best["id"] not in selected_ids:
                        selected.append(best)
                        selected_ids.add(best["id"])

            # Phase B: Fill pillar-specific slots
            for kw in exclusive:
                if len(selected) >= pillar_target + support_target:
                    break
                if kw["id"] not in selected_ids:
                    selected.append(kw)
                    selected_ids.add(kw["id"])
                if len([s for s in selected if len(s.get("pillars", [])) == 1]) >= pillar_target:
                    break

            # Phase C: Fill supporting slots
            for kw in shared:
                if len(selected) >= pillar_target + support_target:
                    break
                if kw["id"] not in selected_ids:
                    selected.append(kw)
                    selected_ids.add(kw["id"])

            # Phase D: Intent diversity check
            selected = self._ensure_intent_diversity(
                selected, p_kws, selected_ids, intent_dist,
                pillar_target + support_target
            )

            # Mark cluster-top bonus
            cluster_top_ids = set()
            for cl in pillar_clusters:
                if cl["keywords"]:
                    best = max(cl["keywords"],
                               key=lambda k: k.get("final_score", 0))
                    cluster_top_ids.add(best["id"])
            for kw in selected:
                if kw["id"] in cluster_top_ids:
                    kw["final_score"] = round(
                        kw.get("final_score", 0) + CLUSTER_TOP_BONUS, 4
                    )

            # Final sort
            selected.sort(key=lambda x: x.get("final_score", 0), reverse=True)
            result[pillar] = selected[:pillar_target + support_target]

        return result

    def _ensure_intent_diversity(self, selected: list[dict],
                                 all_kws: list[dict],
                                 selected_ids: set[str],
                                 intent_dist: dict,
                                 target: int) -> list[dict]:
        """Swap in keywords to meet intent distribution targets."""
        if not intent_dist or len(selected) < 5:
            return selected

        # Count current intent distribution
        intent_counts: dict[str, int] = defaultdict(int)
        for k in selected:
            intent = k.get("intent", "commercial")
            intent_counts[intent] += 1

        total = len(selected)
        for intent_name, pct in intent_dist.items():
            desired = max(1, int(total * pct / 100))
            current = intent_counts.get(intent_name, 0)

            if current < desired:
                # Find keywords of this intent not yet selected
                candidates = [
                    k for k in all_kws
                    if k.get("intent") == intent_name
                    and k["id"] not in selected_ids
                ]
                candidates.sort(key=lambda x: x.get("final_score", 0),
                                reverse=True)

                needed = desired - current
                for c in candidates[:needed]:
                    if len(selected) < target:
                        selected.append(c)
                        selected_ids.add(c["id"])
                    else:
                        # Swap out the lowest-scoring keyword of a different intent
                        others = [
                            (i, s) for i, s in enumerate(selected)
                            if s.get("intent") != intent_name
                        ]
                        if others:
                            others.sort(key=lambda x: x[1].get("final_score", 0))
                            swap_idx = others[0][0]
                            selected_ids.discard(selected[swap_idx]["id"])
                            selected[swap_idx] = c
                            selected_ids.add(c["id"])

        return selected

    # ── Persist ──────────────────────────────────────────────────────────

    def _persist(self, session_id: str, project_id: str,
                 keywords: list[dict],
                 clusters: dict[str, list[dict]],
                 relations: list[dict],
                 top100: dict[str, list[dict]]) -> None:
        """Write scores, clusters, relations, and top-100 to DB."""
        # Build top100 id set
        top_ids = set()
        for p, kws in top100.items():
            for k in kws:
                top_ids.add(k["id"])

        # Update keyword scores + cluster_id + top100 status
        cluster_id_map: dict[str, str] = {}
        for pillar, cls in clusters.items():
            for cl in cls:
                for k in cl["keywords"]:
                    cluster_id_map[k["id"]] = cl["id"]

        for kw in keywords:
            in_top = kw["id"] in top_ids
            db.update_keyword(kw["id"],
                              final_score=kw.get("final_score", 0),
                              commercial_score=kw.get("commercial_score", 0),
                              cluster_id=cluster_id_map.get(kw["id"], ""),
                              status="top100" if in_top else kw.get("status", "approved"),
                              metadata={**(kw.get("metadata") or {}),
                                        "in_top100": in_top})

        # Persist clusters
        conn = db.get_conn()
        try:
            conn.execute(
                "DELETE FROM kw2_clusters WHERE session_id=?", (session_id,)
            )
            now = db._now()
            for pillar, cls in clusters.items():
                for cl in cls:
                    kw_count = len(cl["keywords"])
                    conn.execute(
                        "INSERT INTO kw2_clusters (id, session_id, project_id, "
                        "pillar, cluster_name, keyword_count, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (cl["id"], session_id, project_id, pillar,
                         cl["name"], kw_count, now),
                    )
            conn.commit()
        finally:
            conn.close()

        # Persist relations
        db.delete_relations(session_id)
        db.bulk_insert_relations(session_id, relations)

        # Update session phase
        db.set_phase_status(session_id, "organize", "done")
        db.update_session(session_id, current_phase="apply",
                          top100_count=len(top_ids))

    # ── Read helpers ─────────────────────────────────────────────────────

    def get_graph_data(self, session_id: str) -> dict:
        """Return keyword graph data for visualization (nodes + edges)."""
        keywords = db.load_keywords(session_id)
        relations = db.load_relations(session_id)

        nodes = []
        for kw in keywords:
            nodes.append({
                "id": kw["id"],
                "keyword": kw["keyword"],
                "pillars": kw.get("pillars", []),
                "role": kw.get("role", "supporting"),
                "intent": kw.get("intent", ""),
                "score": kw.get("final_score", 0),
                "cluster_id": kw.get("cluster_id", ""),
                "in_top100": kw.get("status") == "top100",
            })

        edges = []
        for r in relations:
            edges.append({
                "source": r["source_id"],
                "target": r["target_id"],
                "type": r["relation_type"],
                "weight": r["weight"],
            })

        return {"nodes": nodes, "edges": edges}

    def get_top100(self, session_id: str,
                   pillar: str | None = None) -> list[dict]:
        """Return top-100 keywords, optionally filtered by pillar."""
        keywords = db.load_keywords(session_id, status="top100",
                                    pillar=pillar)
        return [
            {
                "id": kw["id"],
                "keyword": kw["keyword"],
                "pillars": kw.get("pillars", []),
                "role": kw.get("role", ""),
                "intent": kw.get("intent", ""),
                "final_score": kw.get("final_score", 0),
                "cluster_id": kw.get("cluster_id", ""),
                "mapped_page": kw.get("mapped_page", ""),
            }
            for kw in keywords
        ]

    def get_organize_summary(self, session_id: str) -> dict:
        """Summary data for the organize phase UI."""
        all_kws = db.load_keywords(session_id)
        top100 = [k for k in all_kws if k.get("status") == "top100"]
        relations = db.load_relations(session_id)

        conn = db.get_conn()
        try:
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        clusters = [dict(r) for r in cluster_rows]

        # Intent distribution in top100
        intent_counts: dict[str, int] = defaultdict(int)
        for k in top100:
            intent_counts[k.get("intent", "unknown")] += 1

        # Pillar breakdown
        pillar_stats: dict[str, dict] = {}
        for k in top100:
            for p in k.get("pillars", []):
                if p not in pillar_stats:
                    pillar_stats[p] = {"count": 0, "avg_score": 0,
                                       "pillar_specific": 0, "bridge": 0}
                pillar_stats[p]["count"] += 1
                if len(k.get("pillars", [])) == 1:
                    pillar_stats[p]["pillar_specific"] += 1
                else:
                    pillar_stats[p]["bridge"] += 1

        for p, stats in pillar_stats.items():
            p_scores = [
                k.get("final_score", 0) for k in top100
                if p in k.get("pillars", [])
            ]
            stats["avg_score"] = round(
                sum(p_scores) / len(p_scores), 4
            ) if p_scores else 0

        return {
            "total_keywords": len(all_kws),
            "top100_count": len(top100),
            "total_relations": len(relations),
            "total_clusters": len(clusters),
            "intent_distribution": dict(intent_counts),
            "pillar_stats": pillar_stats,
            "clusters": [
                {"id": c["id"], "name": c.get("cluster_name", ""),
                 "pillar": c.get("pillar", ""),
                 "keyword_count": c.get("keyword_count", 0)}
                for c in clusters
            ],
        }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

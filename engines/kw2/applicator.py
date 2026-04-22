"""
kw2 applicator — Super Phase 4: APPLY.

Unified internal links + content calendar + AI strategy generation.
Replaces logic from: internal_linker.py, content_calendar.py, strategy_engine.py.
"""
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from engines.kw2 import db
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2.prompts import (
    V2_STRATEGY_SYSTEM, V2_STRATEGY_USER,
)

log = logging.getLogger("kw2.applicator")

INTENT_CTA = {
    "purchase": "buy",
    "transactional": "buy",
    "commercial": "compare",
    "informational": "learn more about",
    "navigational": "find",
    "local": "find near you",
    "comparison": "compare",
    "wholesale": "order",
    "research": "learn about",
}


class Applicator:
    """
    Super Phase 4 pipeline:
    1. Generate internal links from relationship graph
    2. Build content calendar with cluster-aware scheduling
    3. Generate AI strategy document
    """

    def apply(self, project_id: str, session_id: str,
              ai_provider: str = "auto",
              blogs_per_week: int = 3,
              duration_weeks: int = 52,
              start_date: str | None = None) -> dict:
        """Run all three apply steps. Returns combined summary."""
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("Business profile not found — run Phase 1 first")

        pillars = profile.get("pillars", [])
        if isinstance(pillars, str):
            pillars = json.loads(pillars) if pillars else []
        universe = profile.get("universe", "Business")
        domain = profile.get("domain", "")

        # Load organized data
        keywords = db.load_keywords(session_id)
        top100 = [k for k in keywords if k.get("status") == "top100"]
        relations = db.load_relations(session_id)

        if not keywords:
            return {"error": "No keywords to apply"}

        conn = db.get_conn()
        try:
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        clusters = [dict(r) for r in cluster_rows]

        # Step 1: Internal links
        link_stats = self._build_links(
            session_id, project_id, keywords, top100,
            relations, pillars, clusters, universe, domain
        )

        # Step 2: Content calendar
        cal_stats = self._build_calendar(
            session_id, project_id, keywords, top100,
            pillars, clusters, blogs_per_week, duration_weeks, start_date
        )

        # Step 3: Strategy
        strategy = self._generate_strategy(
            session_id, project_id, profile, keywords, top100, relations,
            clusters, link_stats, cal_stats, ai_provider
        )

        # Update session
        db.set_phase_status(session_id, "apply", "done")
        db.update_session(session_id, strategy_json=json.dumps(strategy))

        return {
            "links": link_stats,
            "calendar": cal_stats,
            "strategy_generated": bool(strategy),
        }

    def apply_stream(self, project_id: str, session_id: str,
                     ai_provider: str = "auto",
                     blogs_per_week: int = 3,
                     duration_weeks: int = 52,
                     start_date: str | None = None):
        """SSE generator for apply progress."""
        profile = db.load_business_profile(project_id)
        if not profile:
            yield _sse("error", {"message": "Business profile not found"})
            return

        pillars = profile.get("pillars", [])
        if isinstance(pillars, str):
            pillars = json.loads(pillars) if pillars else []
        universe = profile.get("universe", "Business")
        domain = profile.get("domain", "")

        keywords = db.load_keywords(session_id)
        top100 = [k for k in keywords if k.get("status") == "top100"]
        relations = db.load_relations(session_id)

        if not keywords:
            yield _sse("error", {"message": "No keywords to apply"})
            return

        conn = db.get_conn()
        try:
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        clusters = [dict(r) for r in cluster_rows]

        yield _sse("step", {"name": "links", "status": "running"})
        link_stats = self._build_links(
            session_id, project_id, keywords, top100,
            relations, pillars, clusters, universe, domain
        )
        yield _sse("step", {"name": "links", "status": "done",
                            "count": link_stats.get("total", 0)})

        yield _sse("step", {"name": "calendar", "status": "running"})
        cal_stats = self._build_calendar(
            session_id, project_id, keywords, top100,
            pillars, clusters, blogs_per_week, duration_weeks, start_date
        )
        yield _sse("step", {"name": "calendar", "status": "done",
                            "scheduled": cal_stats.get("scheduled", 0)})

        yield _sse("step", {"name": "strategy", "status": "running"})
        strategy = self._generate_strategy(
            session_id, project_id, profile, keywords, top100, relations,
            clusters, link_stats, cal_stats, ai_provider
        )
        yield _sse("step", {"name": "strategy", "status": "done"})

        db.set_phase_status(session_id, "apply", "done")
        db.update_session(session_id, strategy_json=json.dumps(strategy))

        yield _sse("done", {
            "links": link_stats.get("total", 0),
            "calendar": cal_stats.get("scheduled", 0),
            "strategy": bool(strategy),
        })

    # ── Step 1: Internal Links ───────────────────────────────────────────

    def _build_links(self, session_id: str, project_id: str,
                     keywords: list[dict], top100: list[dict],
                     relations: list[dict], pillars: list[str],
                     clusters: list[dict], universe: str,
                     domain: str) -> dict:
        """Generate internal link suggestions from relationships."""
        conn = db.get_conn()
        try:
            conn.execute(
                "DELETE FROM kw2_internal_links WHERE session_id=?",
                (session_id,),
            )

            now = db._now()
            links = []
            kw_by_id = {k["id"]: k for k in keywords}

            def _slug(text: str) -> str:
                return text.lower().strip().replace(" ", "-").replace("'", "")

            # 1. Keyword → pillar links (every top100 → its pillar page)
            for kw in top100:
                for pillar in kw.get("pillars", []):
                    pillar_url = f"/{_slug(universe)}/{_slug(pillar)}"
                    kw_url = f"{pillar_url}/{_slug(kw['keyword'])}"
                    cta = INTENT_CTA.get(kw.get("intent", ""), "explore")
                    anchor = f"{cta} {kw['keyword']}"
                    intent = kw.get("intent", "informational")
                    links.append((
                        db._uid("lk_"), session_id, project_id,
                        kw_url, pillar_url, anchor,
                        "body", intent,
                        "keyword_to_pillar",
                        now,
                    ))

            # 2. Relationship-driven links (from graph edges)
            for rel in relations:
                src = kw_by_id.get(rel.get("source_id"))
                tgt = kw_by_id.get(rel.get("target_id"))
                if not src or not tgt:
                    continue
                # Only link top100 keywords to keep it actionable
                if src.get("status") != "top100" and tgt.get("status") != "top100":
                    continue

                rel_type = rel.get("relation_type", "sibling")
                weight = float(rel.get("weight", 0.5))

                src_pillar = (src.get("pillars") or [""])[0]
                tgt_pillar = (tgt.get("pillars") or [""])[0]
                src_url = f"/{_slug(universe)}/{_slug(src_pillar)}/{_slug(src['keyword'])}"
                tgt_url = f"/{_slug(universe)}/{_slug(tgt_pillar)}/{_slug(tgt['keyword'])}"

                if rel_type == "cross_pillar":
                    anchor = f"Related: {tgt['keyword']}"
                    link_type = "cross_pillar"
                elif rel_type == "sibling":
                    anchor = f"See also: {tgt['keyword']}"
                    link_type = "sibling"
                elif rel_type == "cross_cluster":
                    anchor = f"Explore: {tgt['keyword']}"
                    link_type = "cross_cluster"
                else:
                    anchor = tgt["keyword"]
                    link_type = rel_type

                links.append((
                    db._uid("lk_"), session_id, project_id,
                    src_url, tgt_url, anchor,
                    "body", "",
                    link_type, now,
                ))

            # 3. Cluster landing → pillar landing
            for cl in clusters:
                pillar = cl.get("pillar", "")
                if pillar:
                    cl_name = cl.get("cluster_name", "")
                    pillar_url = f"/{_slug(universe)}/{_slug(pillar)}"
                    cl_url = f"{pillar_url}/{_slug(cl_name)}"
                    links.append((
                        db._uid("lk_"), session_id, project_id,
                        cl_url, pillar_url, f"Back to {pillar}",
                        "navigation", "",
                        "cluster_to_pillar", now,
                    ))

            conn.executemany(
                """INSERT INTO kw2_internal_links
                   (id, session_id, project_id, from_page, to_page,
                    anchor_text, placement, intent, link_type, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                links,
            )
            conn.commit()

            # Stats by type
            type_counts: dict[str, int] = defaultdict(int)
            for link in links:
                type_counts[link[6]] += 1

            return {"total": len(links), "by_type": dict(type_counts)}
        finally:
            conn.close()

    # ── Step 2: Content Calendar ─────────────────────────────────────────

    def _build_calendar(self, session_id: str, project_id: str,
                        keywords: list[dict], top100: list[dict],
                        pillars: list[str], clusters: list[dict],
                        blogs_per_week: int, duration_weeks: int,
                        start_date: str | None) -> dict:
        """Build cluster-aware content calendar."""
        conn = db.get_conn()
        try:
            conn.execute(
                "DELETE FROM kw2_calendar WHERE session_id=?", (session_id,)
            )

            articles = []

            # Pillar pages first
            for pillar in pillars:
                p_kws = [k for k in top100 if pillar in k.get("pillars", [])]
                avg_score = (
                    sum(k.get("final_score", 0) for k in p_kws) / len(p_kws)
                    if p_kws else 0
                )
                articles.append({
                    "keyword": pillar,
                    "pillar": pillar,
                    "cluster": pillar,
                    "score": avg_score,
                    "article_type": "pillar",
                    "title": f"{pillar} — Complete Guide",
                    "is_pillar": True,
                })

            # Cluster-coherent ordering: group top100 by cluster within pillar
            cluster_map: dict[str, str] = {}
            for cl in clusters:
                cluster_map[cl["id"]] = cl.get("cluster_name", "")

            for pillar in pillars:
                p_kws = [k for k in top100 if pillar in k.get("pillars", [])]
                # Group by cluster
                by_cluster: dict[str, list[dict]] = defaultdict(list)
                for kw in p_kws:
                    cid = kw.get("cluster_id", "unclustered")
                    by_cluster[cid].append(kw)

                # Within each cluster, sort by score
                for cid, ckws in by_cluster.items():
                    ckws.sort(key=lambda x: x.get("final_score", 0), reverse=True)
                    for kw in ckws:
                        articles.append({
                            "keyword": kw["keyword"],
                            "pillar": pillar,
                            "cluster": cluster_map.get(cid, cid),
                            "score": kw.get("final_score", 0),
                            "article_type": "topic",
                            "title": kw["keyword"].title(),
                            "is_pillar": False,
                        })

            # Round-robin across pillars
            pillar_articles = [a for a in articles if a.get("is_pillar")]
            topic_articles = [a for a in articles if not a.get("is_pillar")]

            by_pillar: dict[str, list[dict]] = defaultdict(list)
            for art in topic_articles:
                by_pillar[art.get("pillar", "_none")].append(art)

            interleaved = list(pillar_articles)
            queues = list(by_pillar.values())
            idx = 0
            while queues:
                q = queues[idx % len(queues)]
                if q:
                    interleaved.append(q.pop(0))
                if not q:
                    queues.pop(idx % len(queues))
                    if not queues:
                        break
                    idx = idx % len(queues)
                else:
                    idx += 1

            # Assign dates
            start = (datetime.fromisoformat(start_date) if start_date
                     else datetime.now(timezone.utc))
            total_slots = blogs_per_week * duration_weeks
            for i, art in enumerate(interleaved):
                if i >= total_slots:
                    break
                week_num = i // blogs_per_week
                day_offset = (i % blogs_per_week) * (7 // max(blogs_per_week, 1))
                pub_date = start + timedelta(weeks=week_num, days=day_offset)
                art["scheduled_date"] = pub_date.strftime("%Y-%m-%d")

            calendar = [a for a in interleaved if "scheduled_date" in a]
            calendar.sort(key=lambda x: x["scheduled_date"])

            # Persist
            now = db._now()
            conn.executemany(
                """INSERT INTO kw2_calendar
                   (id, session_id, project_id, keyword, pillar, cluster,
                    scheduled_date, status, article_type, score, title, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        db._uid("cal_"), session_id, project_id,
                        a["keyword"], a.get("pillar", ""), a.get("cluster", ""),
                        a["scheduled_date"], "scheduled",
                        a.get("article_type", "topic"),
                        a.get("score", 0), a.get("title", a["keyword"]),
                        now,
                    )
                    for a in calendar
                ],
            )
            conn.commit()

            return {
                "scheduled": len(calendar),
                "weeks": duration_weeks,
                "blogs_per_week": blogs_per_week,
                "start_date": start.strftime("%Y-%m-%d"),
            }
        finally:
            conn.close()

    # ── Step 3: Strategy ─────────────────────────────────────────────────

    def _generate_strategy(self, session_id: str, project_id: str,
                           profile: dict, keywords: list[dict],
                           top100: list[dict], relations: list[dict],
                           clusters: list[dict], link_stats: dict,
                           cal_stats: dict, ai_provider: str) -> dict:
        """Generate AI strategy document with relationship insights."""
        pillars = profile.get("pillars", [])
        if isinstance(pillars, str):
            pillars = json.loads(pillars) if pillars else []
        universe = profile.get("universe", "Business")

        # Build context
        top_kws = sorted(top100, key=lambda k: k.get("final_score", 0),
                         reverse=True)[:30]
        kw_summary = "\n".join(
            f"- {k['keyword']} (score={k.get('final_score', 0):.2f}, "
            f"intent={k.get('intent', '')}, role={k.get('role', '')})"
            for k in top_kws
        )

        cluster_summary = "\n".join(
            f"- {c.get('cluster_name', '')}: {c.get('keyword_count', 0)} keywords ({c.get('pillar', '')})"
            for c in clusters[:20]
        )

        bridge_kws = [k for k in top100 if len(k.get("pillars", [])) > 1]
        bridge_summary = ", ".join(k["keyword"] for k in bridge_kws[:15])

        # Relationship stats
        rel_types: dict[str, int] = defaultdict(int)
        for r in relations:
            rel_types[r.get("relation_type", "unknown")] += 1
        rel_stats = ", ".join(f"{t}: {c}" for t, c in rel_types.items())

        audience = profile.get("audience", [])
        audience_str = ", ".join(audience) if isinstance(audience, list) else str(audience)

        cal_range = f"{cal_stats.get('scheduled', 0)} articles over {cal_stats.get('weeks', 52)} weeks"

        prompt = V2_STRATEGY_USER.format(
            universe=universe,
            business_type=profile.get("business_type", "unknown"),
            pillars=", ".join(pillars),
            usp=profile.get("usp", ""),
            target_locations=", ".join(profile.get("target_locations", [])),
            business_locations=", ".join(profile.get("business_locations", [])),
            languages=", ".join(profile.get("languages", [])),
            cultural_context=", ".join(profile.get("cultural_context", [])),
            customer_voice=(profile.get("customer_reviews", "") or "")[:300],
            kw_count=len(top_kws),
            top_keywords=kw_summary,
            cluster_count=len(clusters),
            clusters=cluster_summary,
            bridge_keywords=bridge_summary or "None",
            rel_stats=rel_stats or "None",
            link_count=link_stats.get("total", 0),
            calendar_range=cal_range,
            audience=audience_str,
            geo_scope=profile.get("geo_scope", "unknown"),
        )

        try:
            response = kw2_ai_call(prompt, V2_STRATEGY_SYSTEM,
                                   provider=ai_provider, temperature=0.4)
            strategy = kw2_extract_json(response)
        except Exception as e:
            log.warning("Strategy generation failed: %s", e)
            strategy = None

        if not strategy or not isinstance(strategy, dict):
            strategy = {
                "executive_summary": "Strategy generation requires manual review.",
                "pillar_strategies": [],
                "quick_wins": [k["keyword"] for k in top_kws[:10]],
                "content_priorities": [],
                "link_building_plan": "",
                "competitive_gaps": [],
                "timeline": {},
            }

        defaults = {
            "executive_summary": "",
            "pillar_strategies": [],
            "quick_wins": [],
            "content_priorities": [],
            "link_building_plan": "",
            "competitive_gaps": [],
            "timeline": {},
        }
        for k, v in defaults.items():
            if k not in strategy:
                strategy[k] = v

        return strategy

    # ── Read helpers ─────────────────────────────────────────────────────

    def get_links(self, session_id: str,
                  link_type: str | None = None) -> list[dict]:
        """Return internal link suggestions."""
        conn = db.get_conn()
        try:
            query = "SELECT * FROM kw2_internal_links WHERE session_id=?"
            params: list = [session_id]
            if link_type:
                query += " AND link_type=?"
                params.append(link_type)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_calendar(self, session_id: str,
                     pillar: str | None = None) -> list[dict]:
        """Return calendar entries."""
        conn = db.get_conn()
        try:
            if pillar:
                rows = conn.execute(
                    "SELECT * FROM kw2_calendar WHERE session_id=? AND pillar=? "
                    "ORDER BY scheduled_date",
                    (session_id, pillar),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kw2_calendar WHERE session_id=? "
                    "ORDER BY scheduled_date",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_strategy(self, session_id: str) -> dict | None:
        """Load cached strategy."""
        session = db.get_session(session_id)
        if not session:
            return None
        raw = session.get("strategy_json", "")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def update_calendar_entry(self, entry_id: str, **kwargs) -> None:
        """Update a calendar entry (reschedule, change status)."""
        if not kwargs:
            return
        conn = db.get_conn()
        try:
            cols = ", ".join(f"{k}=?" for k in kwargs)
            vals = list(kwargs.values()) + [entry_id]
            conn.execute(f"UPDATE kw2_calendar SET {cols} WHERE id=?", vals)
            conn.commit()
        finally:
            conn.close()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

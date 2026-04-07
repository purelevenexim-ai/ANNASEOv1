"""
kw2 Phase 8 — Content Calendar.

Ported from P13_ContentCalendar. Creates publish schedule
from tree + clusters, with seasonal awareness and inter-pillar
round-robin scheduling. Persists to kw2_calendar.
"""
import logging
from datetime import datetime, timezone, timedelta

from engines.kw2 import db

log = logging.getLogger("kw2.calendar")


class ContentCalendar:
    """Phase 8: Build publishing schedule from tree."""

    def build(
        self,
        project_id: str,
        session_id: str,
        blogs_per_week: int = 3,
        duration_weeks: int = 52,
        start_date: str | None = None,
        seasonal_overrides: dict | None = None,
    ) -> dict:
        """
        Build content calendar. Schedules pillar pages first,
        then round-robin topics across pillars.

        Args:
            blogs_per_week: how many articles per week
            duration_weeks: total weeks to schedule across
            start_date: ISO date string, defaults to today
            seasonal_overrides: dict mapping cluster substring → deadline ISO date

        Returns summary dict.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")

        pillars = profile.get("pillars", [])
        universe = profile.get("universe", "Business")
        keywords = db.load_validated_keywords(session_id)
        if not keywords:
            return {"scheduled": 0}

        conn = db.get_conn()
        try:
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?", (session_id,)
            ).fetchall()

            # Clear existing calendar
            conn.execute(
                "DELETE FROM kw2_calendar WHERE session_id=?", (session_id,)
            )

            # Flatten articles: pillar pages + keyword articles
            articles = self._flatten_articles(pillars, keywords, cluster_rows)

            # Schedule with round-robin
            start = datetime.fromisoformat(start_date) if start_date else datetime.now(timezone.utc)
            calendar = self._schedule(
                articles, blogs_per_week, duration_weeks, start, seasonal_overrides or {}
            )

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

            db.update_session(session_id, phase8_done=1)
            log.info(f"[Phase8] Calendar built: {len(calendar)} articles for {project_id}")

            return {
                "scheduled": len(calendar),
                "weeks": duration_weeks,
                "blogs_per_week": blogs_per_week,
                "start_date": start.strftime("%Y-%m-%d"),
            }
        finally:
            conn.close()

    def get_calendar(self, session_id: str, pillar: str | None = None) -> list[dict]:
        """Return calendar entries, optionally filtered by pillar."""
        conn = db.get_conn()
        try:
            if pillar:
                rows = conn.execute(
                    "SELECT * FROM kw2_calendar WHERE session_id=? AND pillar=? ORDER BY scheduled_date",
                    (session_id, pillar),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kw2_calendar WHERE session_id=? ORDER BY scheduled_date",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_entry(self, entry_id: str, **kwargs):
        """Update a calendar entry (e.g. reschedule, change status)."""
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

    # ── Private helpers ──────────────────────────────────────────────────

    def _flatten_articles(
        self, pillars: list[str], keywords: list[dict], cluster_rows: list
    ) -> list[dict]:
        """Build article list: pillar pages first, then keyword articles."""
        articles = []

        # Pillar pages (always scheduled first)
        for pillar in pillars:
            pillar_kws = [kw for kw in keywords if kw.get("pillar", "") == pillar]
            avg_score = (
                sum(kw.get("final_score", 0) for kw in pillar_kws) / len(pillar_kws)
                if pillar_kws else 0
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

        # Keyword topic articles (sorted by score within each pillar)
        for kw in sorted(keywords, key=lambda x: x.get("final_score", 0), reverse=True):
            articles.append({
                "keyword": kw["keyword"],
                "pillar": kw.get("pillar", ""),
                "cluster": kw.get("cluster", ""),
                "score": kw.get("final_score", 0),
                "article_type": "topic",
                "title": kw["keyword"].title(),
                "is_pillar": False,
            })

        return articles

    def _schedule(
        self,
        articles: list[dict],
        blogs_per_week: int,
        duration_weeks: int,
        start: datetime,
        seasonal: dict,
    ) -> list[dict]:
        """
        Schedule articles with inter-pillar round-robin.
        Pillar pages first, then topics interleaved across pillars.
        """
        # Separate pillar pages and topics
        pillar_articles = [a for a in articles if a.get("is_pillar")]
        topic_articles = [a for a in articles if not a.get("is_pillar")]

        # Round-robin topics across pillars
        by_pillar: dict[str, list[dict]] = {}
        for art in topic_articles:
            p = art.get("pillar", "_none")
            by_pillar.setdefault(p, []).append(art)

        interleaved = list(pillar_articles)  # pillars first
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
        total_slots = blogs_per_week * duration_weeks
        calendar = []
        for i, art in enumerate(interleaved):
            if i >= total_slots:
                break
            # Spread evenly across the week
            week_num = i // blogs_per_week
            day_offset = (i % blogs_per_week) * (7 // max(blogs_per_week, 1))
            pub_date = start + timedelta(weeks=week_num, days=day_offset)
            art["scheduled_date"] = pub_date.strftime("%Y-%m-%d")

        # Apply seasonal overrides
        for art in interleaved:
            if "scheduled_date" not in art:
                continue
            for pattern, deadline_str in seasonal.items():
                cluster = art.get("cluster", "")
                if pattern.lower() in cluster.lower():
                    try:
                        deadline = datetime.fromisoformat(deadline_str)
                        new_date = deadline - timedelta(weeks=6)
                        if new_date >= start:
                            art["scheduled_date"] = new_date.strftime("%Y-%m-%d")
                            art["seasonal_event"] = pattern
                    except (ValueError, TypeError):
                        pass

        calendar = [a for a in interleaved if "scheduled_date" in a]
        calendar.sort(key=lambda x: x["scheduled_date"])
        return calendar

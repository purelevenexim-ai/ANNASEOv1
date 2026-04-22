"""
kw2 Phase 8 — Content Calendar.

Ported from P13_ContentCalendar. Creates publish schedule
from tree + clusters, with seasonal awareness and inter-pillar
round-robin scheduling. Persists to kw2_calendar.
"""
import hashlib
import logging
from datetime import datetime, timezone, timedelta

from engines.kw2 import db

log = logging.getLogger("kw2.calendar")


# ── Title templates per intent (deterministic rotation via keyword hash) ──────

_TRANSACTIONAL_TEMPLATES = [
    "{kw} — Complete Buyer's Guide ({year})",
    "Where to Buy {kw}: Pricing, Options & Tips",
    "{kw} — Pricing Guide & Best Deals",
    "How to Buy {kw} the Smart Way",
    "{kw}: Sourcing Guide for Quality & Value",
    "Your Guide to Buying {kw} in {year}",
    "{kw} — What to Look for Before You Buy",
    "Top Sources for {kw}: Price & Quality Compared",
]

_COMMERCIAL_TEMPLATES = [
    "{kw} — Honest Reviews & Expert Picks ({year})",
    "{kw}: Side-by-Side Comparison Guide",
    "How to Choose the Right {kw} for Your Needs",
    "{kw} — What the Experts Recommend",
    "Choosing {kw}: Features, Quality & Value Compared",
    "{kw} Comparison: Which Option is Worth It?",
]

_INFORMATIONAL_TEMPLATES = [
    "{kw} — Benefits, Uses & What You Should Know",
    "The Complete Guide to {kw}",
    "Everything You Need to Know About {kw}",
    "{kw}: Facts, Benefits & Practical Tips",
    "Understanding {kw} — A Practical Guide",
    "{kw} Explained: Uses, Benefits & More",
]

_GENERIC_TEMPLATES = [
    "{kw} — A Complete Guide ({year})",
    "Everything You Need to Know About {kw}",
    "{kw}: Tips, Insights & Expert Advice",
    "The Essential Guide to {kw}",
    "Your Complete {kw} Resource ({year})",
    "{kw} — What You Need to Know",
]


def _generate_title(keyword: str, intent: str) -> str:
    """Generate a varied, natural title from keyword + intent.

    Uses a deterministic hash of the keyword to select a template,
    ensuring the same keyword always gets the same title but different
    keywords rotate through templates.
    """
    kw_lower = keyword.lower().strip()
    year = datetime.now().year
    intent = (intent or "").lower().strip()

    # Question keywords are already good titles
    if kw_lower.startswith(("how ", "what ", "why ", "when ", "where ", "which ", "can ", "does ", "is ")):
        return keyword.capitalize()

    # Strip leading "buy" / "best" from the keyword for title insertion
    # to avoid awkward titles like "How to Buy Buy Organic Spices"
    kw_clean = keyword
    for prefix in ("buy ", "best ", "top ", "cheap "):
        if kw_lower.startswith(prefix):
            kw_clean = keyword[len(prefix):]
            break

    kw_title = kw_clean.strip().title()

    # Pick template pool based on intent
    if intent in ("transactional", "purchase", "purchase|transactional"):
        pool = _TRANSACTIONAL_TEMPLATES
    elif intent in ("commercial", "comparison"):
        pool = _COMMERCIAL_TEMPLATES
    elif intent == "informational":
        pool = _INFORMATIONAL_TEMPLATES
    else:
        pool = _GENERIC_TEMPLATES

    # Deterministic selection: hash keyword to pick template index
    idx = int(hashlib.md5(kw_lower.encode()).hexdigest(), 16) % len(pool)
    template = pool[idx]

    return template.format(kw=kw_title, year=year)


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
        pillar_quotas: dict | None = None,
    ) -> dict:
        """
        Build content calendar. Schedules pillar pages first,
        then round-robin topics across pillars.

        Args:
            blogs_per_week: how many articles per week (used if pillar_quotas not set)
            duration_weeks: total weeks to schedule across
            start_date: ISO date string, defaults to today
            seasonal_overrides: dict mapping cluster substring → deadline ISO date
            pillar_quotas: optional dict {pillar_name: blogs_per_week} for per-pillar control

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

        # Extract business context for smarter scheduling
        _mi = profile.get("manual_input") or {}
        target_locations = profile.get("target_locations") or _mi.get("target_locations") or []
        cultural_context = profile.get("cultural_context") or _mi.get("cultural_context") or []
        # Build cultural terms set for keyword matching
        cultural_terms = set()
        for c in cultural_context:
            cultural_terms.update(w.lower() for w in c.split() if len(w) >= 2)
        location_terms = set()
        for loc in target_locations:
            location_terms.update(w.lower() for w in loc.split() if len(w) >= 3)

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
            articles = self._flatten_articles(
                pillars, keywords, cluster_rows,
                cultural_terms=cultural_terms, location_terms=location_terms,
            )

            # Schedule with round-robin or per-pillar quotas
            start = datetime.fromisoformat(start_date) if start_date else datetime.now(timezone.utc)
            # If pillar_quotas provided, derive effective blogs_per_week from sum
            effective_bpw = blogs_per_week
            if pillar_quotas and isinstance(pillar_quotas, dict):
                total_quota = sum(v for v in pillar_quotas.values() if isinstance(v, (int, float)) and v > 0)
                if total_quota > 0:
                    effective_bpw = int(total_quota)
            calendar = self._schedule(
                articles, effective_bpw, duration_weeks, start,
                seasonal_overrides or {}, pillar_quotas=pillar_quotas or {},
            )

            # Persist
            now = db._now()
            conn.executemany(
                """INSERT INTO kw2_calendar
                   (id, session_id, project_id, keyword, pillar, cluster,
                    scheduled_date, status, article_type, score, title, source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        db._uid("cal_"), session_id, project_id,
                        a["keyword"], a.get("pillar", ""), a.get("cluster", ""),
                        a["scheduled_date"], "scheduled",
                        a.get("article_type", "topic"),
                        a.get("score", 0), a.get("title", a["keyword"]),
                        a.get("source", "keyword"),
                        now,
                    )
                    for a in calendar
                ],
            )
            conn.commit()

            db.update_session(session_id, phase8_done=1)
            log.info(f"[Phase8] Calendar built: {len(calendar)} articles for {project_id}")

            # Build per-pillar summary
            by_pillar: dict[str, int] = {}
            for a in calendar:
                p = a.get("pillar") or "General"
                by_pillar[p] = by_pillar.get(p, 0) + 1

            return {
                "scheduled": len(calendar),
                "weeks": duration_weeks,
                "blogs_per_week": effective_bpw,
                "start_date": start.strftime("%Y-%m-%d"),
                "by_pillar": [{"pillar": p, "count": c} for p, c in sorted(by_pillar.items(), key=lambda x: -x[1])],
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
        self, pillars: list[str], keywords: list[dict], cluster_rows: list,
        cultural_terms: set | None = None, location_terms: set | None = None,
    ) -> list[dict]:
        """Build article list: pillar pages first, then keyword articles.
        Tags articles with geo/cultural flags for smarter scheduling."""
        articles = []
        cultural_terms = cultural_terms or set()
        location_terms = location_terms or set()

        # Pillar pages (always scheduled first)
        for pillar in pillars:
            pillar_kws = [kw for kw in keywords if kw.get("pillar", "") == pillar]
            avg_score = (
                sum(kw.get("final_score", 0) for kw in pillar_kws) / len(pillar_kws)
                if pillar_kws else 0
            )
            # Smarter pillar title based on keyword count
            kw_count = len(pillar_kws)
            if kw_count > 10:
                title = f"The Ultimate Guide to {pillar}"
            elif kw_count > 5:
                title = f"{pillar}: Everything You Need to Know"
            else:
                title = f"{pillar} — Complete Guide"
            articles.append({
                "keyword": pillar,
                "pillar": pillar,
                "cluster": pillar,
                "score": avg_score,
                "article_type": "pillar",
                "title": title,
                "is_pillar": True,
            })

        # Keyword topic articles (sorted by score within each pillar)
        for kw in sorted(keywords, key=lambda x: x.get("final_score", 0), reverse=True):
            kw_lower = kw["keyword"].lower()
            kw_words = set(kw_lower.split())
            # Boost score for geo-targeted and culturally relevant keywords
            geo_match = bool(location_terms and kw_words & location_terms)
            cultural_match = bool(cultural_terms and kw_words & cultural_terms)
            score_boost = 0.0
            if geo_match:
                score_boost += 3.0  # geo-targeted content scheduled earlier
            if cultural_match:
                score_boost += 2.0  # culturally relevant content prioritized

            # Generate a meaningful title from keyword + intent
            intent = (kw.get("intent") or "").lower()
            cluster_name = kw.get("cluster", "")
            kw_title = _generate_title(kw["keyword"], intent)

            articles.append({
                "keyword": kw["keyword"],
                "pillar": kw.get("pillar", ""),
                "cluster": cluster_name,
                "score": kw.get("final_score", 0) + score_boost,
                "article_type": "topic",
                "title": kw_title,
                "is_pillar": False,
                "is_geo": geo_match,
                "is_cultural": cultural_match,
            })

        return articles

    def _schedule(
        self,
        articles: list[dict],
        blogs_per_week: int,
        duration_weeks: int,
        start: datetime,
        seasonal: dict,
        pillar_quotas: dict | None = None,
    ) -> list[dict]:
        """
        Schedule articles with inter-pillar round-robin or per-pillar quotas.
        Pillar pages first, then topics interleaved across pillars.
        """
        # Separate pillar pages and topics
        pillar_articles = [a for a in articles if a.get("is_pillar")]
        topic_articles = [a for a in articles if not a.get("is_pillar")]

        # Group topic articles by pillar (sorted by score desc)
        by_pillar: dict[str, list[dict]] = {}
        for art in topic_articles:
            p = art.get("pillar", "_none")
            by_pillar.setdefault(p, []).append(art)
        for q in by_pillar.values():
            q.sort(key=lambda a: a.get("score", 0), reverse=True)

        interleaved = list(pillar_articles)  # pillars first

        if pillar_quotas and isinstance(pillar_quotas, dict):
            # Per-pillar quota scheduling: each week, pick N articles per pillar
            total_slots = blogs_per_week * duration_weeks
            slot_count = 0
            week = 0
            while slot_count < total_slots and week < duration_weeks:
                # Each week: for each pillar with a quota, pull that many articles
                pillar_names = list(by_pillar.keys())
                for p_name in pillar_names:
                    quota = int(pillar_quotas.get(p_name, 0))
                    if quota <= 0:
                        # Pillar not given a quota → include in leftover round-robin
                        continue
                    q = by_pillar.get(p_name, [])
                    for _ in range(quota):
                        if q and slot_count < total_slots:
                            interleaved.append(q.pop(0))
                            slot_count += 1
                # Leftover pillars (no explicit quota) get allocated remainder of the week
                remainder_slots = blogs_per_week - sum(
                    min(int(pillar_quotas.get(p, 0)), len(by_pillar.get(p, [])))
                    for p in pillar_names
                    if int(pillar_quotas.get(p, 0)) > 0
                )
                leftover_pillars = [p for p in pillar_names if int(pillar_quotas.get(p, 0)) == 0]
                lp_idx = 0
                while remainder_slots > 0 and leftover_pillars and slot_count < total_slots:
                    p_name = leftover_pillars[lp_idx % len(leftover_pillars)]
                    q = by_pillar.get(p_name, [])
                    if q:
                        interleaved.append(q.pop(0))
                        slot_count += 1
                        remainder_slots -= 1
                    leftover_pillars_nonempty = [p for p in leftover_pillars if by_pillar.get(p)]
                    if not leftover_pillars_nonempty:
                        break
                    lp_idx += 1
                week += 1
                # Stop early if all pillar queues empty
                if all(not q for q in by_pillar.values()):
                    break
        else:
            # Default: round-robin across pillars
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

    def build_from_strategy(
        self,
        project_id: str,
        session_id: str,
        strategy: dict,
        start_date: str | None = None,
    ) -> dict:
        """
        Rebuild the content calendar from Phase 9 strategy + intelligence questions.

        Sources (in priority order):
        1. strategy weekly_plan  — AI-crafted articles with real titles
        2. intelligence questions — scored research questions → additional blog ideas
        3. remaining validated keywords — not yet covered

        Falls back to the regular keyword-based build() if strategy is empty.
        """
        weekly_plan = strategy.get("weekly_plan", [])

        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile.")

        start = datetime.fromisoformat(start_date) if start_date else datetime.now(timezone.utc)
        articles = []

        # ── Source 1: Strategy weekly_plan ───────────────────────────────
        strategy_week_count = 0
        if weekly_plan:
            for week_entry in weekly_plan:
                if not isinstance(week_entry, dict):
                    continue
                week_num = week_entry.get("week", 1)
                focus_pillar = week_entry.get("focus_pillar", "General")
                week_articles = week_entry.get("articles", [])
                strategy_week_count = max(strategy_week_count, week_num)

                for idx, art in enumerate(week_articles):
                    if isinstance(art, str):
                        title = art
                        keyword = art
                        intent = ""
                        page_type = "blog_page"
                    elif isinstance(art, dict):
                        title = art.get("title", art.get("keyword", ""))
                        keyword = art.get("primary_keyword", art.get("target_keyword", art.get("keyword", title)))
                        intent = art.get("intent", "")
                        page_type = art.get("page_type", "blog_page")
                    else:
                        continue
                    if not title:
                        continue
                    day_offset = min(idx * 2, 6)
                    pub_date = start + timedelta(weeks=week_num - 1, days=day_offset)
                    articles.append({
                        "keyword": keyword,
                        "pillar": focus_pillar,
                        "cluster": "",
                        "score": max(100 - week_num, 10),
                        "article_type": "pillar" if page_type in ("pillar_page", "pillar") else "topic",
                        "title": title,
                        "scheduled_date": pub_date.strftime("%Y-%m-%d"),
                        "source": "strategy",
                    })
        else:
            log.info("[Phase8] No weekly_plan — using keyword-based titles")

        # ── Source 2: Intelligence questions → additional blog ideas ─────
        covered = {a["keyword"].lower() for a in articles} | {a["title"].lower() for a in articles}
        iq_articles = []
        try:
            conn = db.get_conn()
            try:
                q_rows = conn.execute(
                    """SELECT question, content_type, intent, final_score, expansion_dimension_name, expansion_dimension_value
                       FROM kw2_intelligence_questions
                       WHERE session_id=? AND is_duplicate=0 AND final_score > 0
                       ORDER BY final_score DESC LIMIT 300""",
                    (session_id,),
                ).fetchall()
            finally:
                conn.close()

            intent_title_map = {
                "transactional": "— Buy Guide & Best Sources",
                "commercial": "— Reviews & Top Picks",
                "informational": "",
            }
            for q in q_rows:
                q_text = (q["question"] or "").strip()
                if not q_text or len(q_text) < 10:
                    continue
                q_lower = q_text.lower()
                # Skip if already covered
                if any(q_lower in c or c in q_lower for c in covered):
                    continue
                intent = (q.get("intent") or "informational").lower()
                suffix = intent_title_map.get(intent, "")
                # Questions that start with How/Why/What/Which make great blog titles as-is
                if q_text[0:3].lower() in ("how", "why", "wha", "whi", "whe", "can", "do ", "is ", "are", "bes", "top"):
                    title = q_text.rstrip("?") + "?"
                else:
                    title = f"{q_text}{' ' + suffix if suffix else ''}"
                pillar = q.get("expansion_dimension_value") or profile.get("pillars", ["General"])[0] if profile.get("pillars") else "General"
                iq_articles.append({
                    "keyword": q_text,
                    "pillar": pillar,
                    "cluster": q.get("content_type", ""),
                    "score": float(q.get("final_score") or 0),
                    "article_type": "topic",
                    "title": title,
                    "source": "intelligence",
                })
                covered.add(q_lower)
        except Exception as exc:
            log.warning("[Phase8] Could not load intelligence questions: %s", exc)

        # Schedule intelligence question articles after the strategy window
        iq_start_week = strategy_week_count
        for iq_idx, iq in enumerate(sorted(iq_articles, key=lambda x: -x["score"])):
            week_offset = iq_idx // 3
            day_offset = (iq_idx % 3) * 2
            pub_date = start + timedelta(weeks=iq_start_week + week_offset, days=day_offset)
            iq["scheduled_date"] = pub_date.strftime("%Y-%m-%d")
            articles.append(iq)

        # ── Source 3: Remaining validated keywords ────────────────────────
        extra_keywords = db.load_validated_keywords(session_id)
        extra_start_week = iq_start_week + max(len(iq_articles) // 3, 0)
        extra_idx = 0
        for kw in sorted(extra_keywords, key=lambda x: x.get("final_score", 0), reverse=True):
            kw_text = kw.get("keyword", "")
            if not kw_text or kw_text.lower() in covered:
                continue
            intent = (kw.get("intent") or "").lower()
            kw_title = _generate_title(kw_text, intent)
            week_offset = extra_idx // 3
            day_offset = (extra_idx % 3) * 2
            pub_date = start + timedelta(weeks=extra_start_week + week_offset, days=day_offset)
            articles.append({
                "keyword": kw_text,
                "pillar": kw.get("pillar", ""),
                "cluster": kw.get("cluster", ""),
                "score": kw.get("final_score", 0),
                "article_type": "topic",
                "title": kw_title,
                "scheduled_date": pub_date.strftime("%Y-%m-%d"),
                "source": "keywords",
            })
            covered.add(kw_text.lower())
            extra_idx += 1

        # Fallback: if no strategy and no intelligence, use keyword build
        if not articles:
            log.info("[Phase8] No sources produced articles, falling back to keyword build")
            return self.build(project_id, session_id, start_date=start_date)

        articles.sort(key=lambda a: a["scheduled_date"])

        # Persist to kw2_calendar (replacing old entries)
        conn = db.get_conn()
        try:
            conn.execute("DELETE FROM kw2_calendar WHERE session_id=?", (session_id,))
            now = db._now()
            conn.executemany(
                """INSERT INTO kw2_calendar
                   (id, session_id, project_id, keyword, pillar, cluster,
                    scheduled_date, status, article_type, score, title, source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        db._uid("cal_"), session_id, project_id,
                        a["keyword"], a.get("pillar", ""), a.get("cluster", ""),
                        a["scheduled_date"], "scheduled",
                        a.get("article_type", "topic"),
                        a.get("score", 0), a["title"],
                        a.get("source", "keyword"), now,
                    )
                    for a in articles
                ],
            )
            conn.commit()
            db.update_session(session_id, phase8_done=1)
            n_strat = sum(1 for a in articles if a.get("source") == "strategy")
            n_iq = sum(1 for a in articles if a.get("source") == "intelligence")
            n_kw = sum(1 for a in articles if a.get("source") == "keywords")
            log.info(
                "[Phase8] Calendar rebuilt: %d total (%d strategy, %d intelligence, %d keywords)",
                len(articles), n_strat, n_iq, n_kw,
            )
        finally:
            conn.close()

        return {
            "scheduled": len(articles),
            "from_strategy": n_strat,
            "from_intelligence": n_iq,
            "from_keywords": n_kw,
            "start_date": start.strftime("%Y-%m-%d"),
        }

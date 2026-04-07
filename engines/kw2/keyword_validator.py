"""
kw2 Phase 3 — AI Keyword Validation Layer.

4-pass pipeline:
  Pass 1: Rule filter (instant) — negative patterns + garbage ratio
  Pass 2: AI batch validation (25/batch, ThreadPoolExecutor, early stop at 400)
  Pass 3: Semantic dedup (TF-IDF cosine > 0.85)
  Pass 4: Category balance (enforce CATEGORY_CAPS percentages)
"""
import json
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from engines.kw2.constants import (
    NEGATIVE_PATTERNS, GARBAGE_WORDS, COMMERCIAL_BOOSTS,
    VALIDATION_BATCH_SIZE, VALIDATION_TARGET_COUNT, CATEGORY_CAPS,
)
from engines.kw2.prompts import VALIDATE_SYSTEM, VALIDATE_USER
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2 import db

log = logging.getLogger("kw2.validator")

# In-memory cache: md5(keyword+universe) → validation result
_validation_cache: dict[str, dict] = {}


class KeywordValidator:
    """Phase 3: Validate keyword universe via rules + AI + dedup + balance."""

    def validate(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
    ) -> dict:
        """Synchronous validation — returns summary stats."""
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")

        raw_items = db.load_universe_items(session_id, status="raw")
        if not raw_items:
            return {"accepted": 0, "rejected": 0, "message": "No raw keywords to validate"}

        universe = profile.get("universe", "")
        pillars = profile.get("pillars", [])
        negative_scope = profile.get("negative_scope", [])

        # Pass 1: Rule filter
        rule_passed, rule_rejected = self._rule_filter(raw_items, negative_scope)
        db.update_universe_status([r["id"] for r in rule_rejected], "rejected", "rule_filter")

        # Pass 2: AI validation
        accepted, ai_rejected = self._ai_validate(
            rule_passed, universe, pillars, negative_scope, ai_provider
        )
        db.update_universe_status([r["id"] for r in ai_rejected], "rejected", "ai_low_relevance")
        db.update_universe_status([a["id"] for a in accepted], "accepted")

        # Insert accepted into validated_keywords table
        validated_items = [
            {
                "keyword": a["keyword"],
                "pillar": a.get("pillar", ""),
                "ai_relevance": a.get("ai_relevance", 0.0),
                "intent": a.get("intent", ""),
                "buyer_readiness": a.get("buyer_readiness", 0.0),
                "source": a.get("source", ""),
            }
            for a in accepted
        ]
        db.bulk_insert_validated(session_id, project_id, validated_items)

        # Pass 3: Semantic dedup
        before_dedup = len(accepted)
        dedup_removed = self._semantic_dedup(session_id)

        # Pass 4: Category balance
        balance_removed = self._category_balance(session_id)

        final_count = before_dedup - dedup_removed - balance_removed
        db.update_session(session_id, phase3_done=1, validated_count=final_count)

        result = {
            "accepted": final_count,
            "rule_rejected": len(rule_rejected),
            "ai_rejected": len(ai_rejected),
            "deduped": dedup_removed,
            "balance_dropped": balance_removed,
            "total_rejected": len(rule_rejected) + len(ai_rejected) + dedup_removed + balance_removed,
        }
        log.info(f"[Phase3] Validated {final_count} keywords for {project_id}")
        return result

    def validate_stream(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
    ):
        """SSE generator for validation progress."""
        profile = db.load_business_profile(project_id)
        if not profile:
            yield f'data: {json.dumps({"type": "error", "msg": "No business profile."})}\n\n'
            return

        raw_items = db.load_universe_items(session_id, status="raw")
        if not raw_items:
            yield f'data: {json.dumps({"type": "complete", "validated": 0})}\n\n'
            return

        universe = profile.get("universe", "")
        pillars = profile.get("pillars", [])
        negative_scope = profile.get("negative_scope", [])

        # Pass 1
        rule_passed, rule_rejected = self._rule_filter(raw_items, negative_scope)
        db.update_universe_status([r["id"] for r in rule_rejected], "rejected", "rule_filter")
        yield f'data: {json.dumps({"type": "phase", "name": "rule_filter", "rejected": len(rule_rejected), "remaining": len(rule_passed)})}\n\n'

        # Pass 2 — with batch progress
        accepted = []
        ai_rejected = []
        batches = [rule_passed[i:i+VALIDATION_BATCH_SIZE] for i in range(0, len(rule_passed), VALIDATION_BATCH_SIZE)]
        total_batches = len(batches)

        for batch_num, batch in enumerate(batches, 1):
            if len(accepted) >= VALIDATION_TARGET_COUNT:
                break
            batch_accepted, batch_rejected = self._validate_batch(
                batch, universe, pillars, negative_scope, ai_provider
            )
            accepted.extend(batch_accepted)
            ai_rejected.extend(batch_rejected)
            yield f'data: {json.dumps({"type": "phase", "name": "ai_batch", "batch": batch_num, "total_batches": total_batches, "accepted_so_far": len(accepted)})}\n\n'

        db.update_universe_status([r["id"] for r in ai_rejected], "rejected", "ai_low_relevance")
        db.update_universe_status([a["id"] for a in accepted], "accepted")

        validated_items = [
            {"keyword": a["keyword"], "pillar": a.get("pillar", ""),
             "ai_relevance": a.get("ai_relevance", 0.0), "intent": a.get("intent", ""),
             "buyer_readiness": a.get("buyer_readiness", 0.0), "source": a.get("source", "")}
            for a in accepted
        ]
        db.bulk_insert_validated(session_id, project_id, validated_items)

        # Pass 3
        dedup_removed = self._semantic_dedup(session_id)
        yield f'data: {json.dumps({"type": "phase", "name": "dedup", "removed": dedup_removed})}\n\n'

        # Pass 4
        balance_removed = self._category_balance(session_id)
        yield f'data: {json.dumps({"type": "phase", "name": "balance", "removed": balance_removed})}\n\n'

        final_count = len(accepted) - dedup_removed - balance_removed
        db.update_session(session_id, phase3_done=1, validated_count=final_count)

        yield f'data: {json.dumps({"type": "complete", "validated": final_count, "total_rejected": len(rule_rejected) + len(ai_rejected) + dedup_removed + balance_removed})}\n\n'

    # ── Pass 1: Rule filter ──────────────────────────────────────────────

    def _rule_filter(self, items: list[dict], negative_scope: list[str]) -> tuple[list[dict], list[dict]]:
        neg_set = set(p.lower() for p in NEGATIVE_PATTERNS)
        neg_set.update(p.lower() for p in (negative_scope or []))

        passed = []
        rejected = []
        for item in items:
            kw = item["keyword"].lower()
            words = kw.split()

            # Min 2 words
            if len(words) < 2:
                item["reject_reason"] = "too_short"
                rejected.append(item)
                continue

            # Negative pattern hit
            hit = False
            for neg in neg_set:
                if neg in kw:
                    item["reject_reason"] = f"negative:{neg}"
                    rejected.append(item)
                    hit = True
                    break
            if hit:
                continue

            # Garbage ratio
            garbage_count = sum(1 for w in words if w in GARBAGE_WORDS)
            if len(words) > 0 and garbage_count / len(words) > 0.5:
                item["reject_reason"] = "garbage_ratio"
                rejected.append(item)
                continue

            passed.append(item)
        return passed, rejected

    # ── Pass 2: AI validation ────────────────────────────────────────────

    def _ai_validate(
        self, items: list[dict], universe: str, pillars: list[str],
        negative_scope: list[str], provider: str,
    ) -> tuple[list[dict], list[dict]]:
        """AI batch validation with priority sort + early stop + parallel."""
        # Priority sort: commercial keywords first
        items.sort(key=lambda x: self._commercial_priority(x["keyword"]), reverse=True)

        batches = [items[i:i+VALIDATION_BATCH_SIZE] for i in range(0, len(items), VALIDATION_BATCH_SIZE)]
        accepted = []
        rejected = []

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {}
            for batch in batches:
                if len(accepted) >= VALIDATION_TARGET_COUNT:
                    break
                f = pool.submit(self._validate_batch, batch, universe, pillars, negative_scope, provider)
                futures[f] = batch

            for future in as_completed(futures):
                if len(accepted) >= VALIDATION_TARGET_COUNT:
                    break
                batch_accepted, batch_rejected = future.result()
                accepted.extend(batch_accepted)
                rejected.extend(batch_rejected)

        return accepted, rejected

    def _validate_batch(
        self, batch: list[dict], universe: str, pillars: list[str],
        negative_scope: list[str], provider: str,
    ) -> tuple[list[dict], list[dict]]:
        """Validate a single batch of keywords via AI."""
        # Check cache first
        uncached = []
        cached_accepted = []
        cached_rejected = []

        for item in batch:
            cache_key = hashlib.md5(f"{item['keyword']}|{universe}".encode()).hexdigest()
            cached = _validation_cache.get(cache_key)
            if cached:
                item.update(cached)
                if cached.get("ai_relevance", 0) >= 0.7 and cached.get("intent") != "informational":
                    cached_accepted.append(item)
                else:
                    cached_rejected.append(item)
            else:
                uncached.append(item)

        if not uncached:
            return cached_accepted, cached_rejected

        # AI call
        keywords_list = "\n".join(f"- {it['keyword']}" for it in uncached)
        prompt = VALIDATE_USER.format(
            universe=universe,
            pillars_str=", ".join(pillars),
            negative_scope_str=", ".join(negative_scope[:15]),
            n=len(uncached),
            keywords_list=keywords_list,
        )

        response = kw2_ai_call(prompt, VALIDATE_SYSTEM, provider=provider)
        results = kw2_extract_json(response)

        accepted = list(cached_accepted)
        rejected = list(cached_rejected)

        if results and isinstance(results, list):
            # Build lookup from AI results
            ai_map = {}
            for r in results:
                if isinstance(r, dict) and "keyword" in r:
                    ai_map[r["keyword"].lower().strip()] = r

            for item in uncached:
                kw_lower = item["keyword"].lower().strip()
                ai_result = ai_map.get(kw_lower, {})
                relevance = float(ai_result.get("relevance", 0.5))
                intent = ai_result.get("intent", "unknown")
                readiness = float(ai_result.get("buyer_readiness", 0.5))

                item["ai_relevance"] = relevance
                item["intent"] = intent
                item["buyer_readiness"] = readiness

                # Cache result
                cache_key = hashlib.md5(f"{item['keyword']}|{universe}".encode()).hexdigest()
                _validation_cache[cache_key] = {
                    "ai_relevance": relevance, "intent": intent, "buyer_readiness": readiness,
                }

                if relevance >= 0.7 and intent != "informational":
                    accepted.append(item)
                else:
                    item["reject_reason"] = f"ai:relevance={relevance},intent={intent}"
                    rejected.append(item)
        else:
            # AI failed — accept all with neutral score
            log.warning("[Phase3] AI validation returned no parseable results, accepting batch with neutral scores")
            for item in uncached:
                item["ai_relevance"] = 0.5
                item["intent"] = "unknown"
                item["buyer_readiness"] = 0.5
                accepted.append(item)

        return accepted, rejected

    def _commercial_priority(self, keyword: str) -> float:
        """Score keyword by commercial signal presence for priority sorting."""
        kw_lower = keyword.lower()
        score = 0.0
        for token, boost in COMMERCIAL_BOOSTS.items():
            if token in kw_lower:
                score += boost
        return score

    # ── Pass 3: Semantic dedup ───────────────────────────────────────────

    def _semantic_dedup(self, session_id: str) -> int:
        """TF-IDF cosine dedup on validated keywords. Returns count of removed items."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            log.warning("scikit-learn not available, skipping semantic dedup")
            return 0

        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT id, keyword, ai_relevance FROM kw2_validated_keywords WHERE session_id=? ORDER BY ai_relevance DESC",
                (session_id,),
            ).fetchall()

            if len(rows) < 2:
                return 0

            keywords = [r["keyword"] for r in rows]
            ids = [r["id"] for r in rows]
            scores = [r["ai_relevance"] for r in rows]

            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform(keywords)
            sim_matrix = cosine_similarity(tfidf_matrix)

            to_remove = set()
            for i in range(len(keywords)):
                if i in to_remove:
                    continue
                for j in range(i + 1, len(keywords)):
                    if j in to_remove:
                        continue
                    if sim_matrix[i][j] > 0.85:
                        # Remove the one with lower score
                        if scores[j] <= scores[i]:
                            to_remove.add(j)
                        else:
                            to_remove.add(i)

            if to_remove:
                remove_ids = [ids[i] for i in to_remove]
                conn.executemany(
                    "DELETE FROM kw2_validated_keywords WHERE id=?",
                    [(rid,) for rid in remove_ids],
                )
                conn.commit()

            return len(to_remove)
        finally:
            conn.close()

    # ── Pass 4: Category balance ─────────────────────────────────────────

    def _category_balance(self, session_id: str) -> int:
        """Enforce CATEGORY_CAPS percentages. Returns count of removed items."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT id, keyword, intent, ai_relevance FROM kw2_validated_keywords WHERE session_id=? ORDER BY ai_relevance DESC",
                (session_id,),
            ).fetchall()

            total = len(rows)
            if total == 0:
                return 0

            # Bin keywords into categories
            bins: dict[str, list] = {cat: [] for cat in CATEGORY_CAPS}
            for r in rows:
                cat = self._categorize(r["keyword"], r["intent"])
                bins[cat].append(r)

            # Compute max allowed per category
            to_remove = []
            for cat, cap_pct in CATEGORY_CAPS.items():
                max_allowed = max(1, int(total * cap_pct / 100))
                excess = bins[cat][max_allowed:]
                to_remove.extend(r["id"] for r in excess)

            if to_remove:
                conn.executemany(
                    "DELETE FROM kw2_validated_keywords WHERE id=?",
                    [(rid,) for rid in to_remove],
                )
                conn.commit()

            return len(to_remove)
        finally:
            conn.close()

    def _categorize(self, keyword: str, intent: str) -> str:
        """Map keyword to CATEGORY_CAPS category."""
        kw = keyword.lower()
        if ("buy" in kw or "order" in kw or "purchase" in kw) and not ("wholesale" in kw or "bulk" in kw):
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

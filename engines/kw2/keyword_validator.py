"""
kw2 Phase 3 — AI Keyword Validation Layer (v2).

6-pass pipeline:
  Pass 1: Rule filter (instant) — negative patterns + garbage ratio
  Pass 2: Pre-score (instant) — structural/commercial/intent scoring 0-100
  Pass 3: Per-pillar AI batch validation (80/batch, Semaphore(2), early stop)
  Pass 4: Semantic dedup (TF-IDF cosine > 0.85)
  Pass 5: Category balance (enforce CATEGORY_CAPS percentages)
"""
import json
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from engines.kw2.constants import (
    NEGATIVE_PATTERNS, GARBAGE_WORDS, COMMERCIAL_BOOSTS,
    VALIDATION_BATCH_SIZE, CATEGORY_CAPS,
    PRE_SCORE_THRESHOLD, MAX_PER_PILLAR_AI,
    EARLY_STOP_WINDOW, EARLY_STOP_MIN_RATE, AI_CONCURRENCY,
    RULE_SCORE_INTENT, RULE_SCORE_MODIFIER_PREMIUM, RULE_SCORE_MODIFIER_GENERIC,
)
from engines.kw2.prompts import VALIDATE_SYSTEM, VALIDATE_USER
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2 import db

log = logging.getLogger("kw2.validator")

# In-memory cache: md5(keyword+universe) → validation result
_validation_cache: dict[str, dict] = {}


class KeywordValidator:
    """Phase 3: Validate keyword universe via rules + pre-score + per-pillar AI + dedup + balance."""

    # ── Pre-Score Engine ─────────────────────────────────────────────────

    def _pre_score(self, keyword: str, pillars: list[str]) -> float:
        """
        Compute a 0-100 structural score WITHOUT any AI calls.
        Components:
          - word_count: 0-10 (2-5 words optimal)
          - commercial_signal: 0-25 (COMMERCIAL_BOOSTS + RULE_SCORE_INTENT)
          - modifier_premium: 0-15 (premium modifiers)
          - pillar_relevance: 0-25 (contains a pillar word)
          - length_bonus: 0-10 (penalize too short/long)
          - modifier_generic: 0-5
          - penalties: 0 to -20
        """
        kw = keyword.lower()
        words = kw.split()
        wc = len(words)
        score = 0.0

        # Word count: 2-5 words is ideal
        if wc < 2:
            return 0  # already caught by rule filter, belt-and-suspenders
        elif 2 <= wc <= 5:
            score += 10
        elif wc <= 7:
            score += 6
        else:
            score += 2

        # Commercial signal (max 25)
        comm = 0.0
        for token, boost in COMMERCIAL_BOOSTS.items():
            if token in kw:
                comm += boost
        for token, boost in RULE_SCORE_INTENT.items():
            if token in kw:
                comm += boost * 0.5  # half-weight to avoid double-counting
        score += min(comm, 25)

        # Modifier premium (max 15)
        mod = 0.0
        for token, boost in RULE_SCORE_MODIFIER_PREMIUM.items():
            if token in kw:
                mod += boost
        score += min(mod, 15)

        # Modifier generic (max 5)
        gen = 0.0
        for token, boost in RULE_SCORE_MODIFIER_GENERIC.items():
            if token in kw:
                gen += boost
        score += min(gen, 5)

        # Pillar relevance (max 25)
        pillar_hit = False
        for p in pillars:
            p_lower = p.lower()
            if p_lower in kw or any(pw in kw for pw in p_lower.split()):
                pillar_hit = True
                score += 25
                break
        if not pillar_hit:
            # Partial: check if any pillar word is a substring
            for p in pillars:
                for pw in p.lower().split():
                    if len(pw) > 3 and pw in kw:
                        score += 12
                        pillar_hit = True
                        break
                if pillar_hit:
                    break

        # Length bonus (max 10)
        char_len = len(keyword)
        if 10 <= char_len <= 50:
            score += 10
        elif char_len < 10:
            score += 4
        else:
            score += 2

        # Penalties
        garbage_count = sum(1 for w in words if w in GARBAGE_WORDS)
        if wc > 0 and garbage_count / wc > 0.3:
            score -= 10
        if wc > 8:
            score -= 10

        return max(0, min(100, score))

    def _rule_classify_intent(self, keyword: str) -> tuple[str, float, float] | None:
        """
        Fast rule-based intent classifier using COMMERCIAL_BOOSTS.
        Returns (intent, buyer_readiness, ai_relevance) when confidence is high enough,
        or None when the AI should decide.

        Thresholds based on COMMERCIAL_BOOSTS values (max single token = 35):
          - Total boost >= 50 → very strong transactional (e.g. "buy wholesale bulk")
          - Total boost 25-49 → transactional
          - Total boost 12-24 → commercial (medium confidence)
          - Below 12 → None (let AI decide)

        Readiness is graded by specificity:
          - Very high specificity (4-6 words, 2+ commercial signals) → 0.82-0.88
          - Standard transactional → 0.70-0.80
          - Commercial (navigational/comparative) → 0.55-0.68
        This prevents all transactional keywords getting an identical 0.85 score.
        """
        kw = keyword.lower()
        words = kw.split()
        wc = len(words)

        # Count distinct commercial signal tokens matched
        matched_tokens = [tok for tok, _ in COMMERCIAL_BOOSTS.items() if tok in kw]
        total = sum(COMMERCIAL_BOOSTS[tok] for tok in matched_tokens)

        if total >= 25:
            # Grade readiness by word count and signal density
            signal_count = len(matched_tokens)
            if signal_count >= 3 and 4 <= wc <= 7:
                # Very specific multi-signal query (e.g. "buy bulk organic spices wholesale")
                readiness = min(0.88, 0.75 + signal_count * 0.04 + (wc - 3) * 0.01)
            elif signal_count >= 2 and wc >= 4:
                readiness = min(0.82, 0.72 + signal_count * 0.03 + (wc - 3) * 0.01)
            elif wc >= 4:
                readiness = 0.75
            elif wc == 3:
                readiness = 0.70
            else:
                # Very short transactional (e.g. "buy spices") — generic, lower specificity
                readiness = 0.65
            # AI relevance tracks readiness but slightly lower to preserve variance
            ai_rel = round(readiness * 0.92, 2)
            return ("transactional", round(readiness, 2), ai_rel)

        if total >= 12:
            return ("commercial", 0.60, 0.70)
        return None

    def _assign_pillar(self, keyword: str, pillars: list[str]) -> str:
        """Assign keyword to its best-matching pillar."""
        kw = keyword.lower()
        best_pillar = ""
        best_score = 0
        for p in pillars:
            p_lower = p.lower()
            s = 0
            if p_lower in kw:
                s = len(p_lower) * 2
            else:
                for pw in p_lower.split():
                    if pw in kw:
                        s += len(pw)
            if s > best_score:
                best_score = s
                best_pillar = p
        return best_pillar or (pillars[0] if pillars else "")

    # ── Main validate (sync) ────────────────────────────────────────────

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

        # Store profile context for downstream prompt enrichment
        self._profile_ctx = profile

        # Pass 1: Rule filter
        rule_passed, rule_rejected = self._rule_filter(raw_items, negative_scope)
        db.update_universe_status([r["id"] for r in rule_rejected], "rejected", "rule_filter")

        # Pass 2: Pre-score + trim
        scored = []
        prescore_rejected = []
        for item in rule_passed:
            ps = self._pre_score(item["keyword"], pillars)
            item["pre_score"] = ps
            item["pillar"] = item.get("pillar") or self._assign_pillar(item["keyword"], pillars)
            if ps >= PRE_SCORE_THRESHOLD:
                scored.append(item)
            else:
                item["reject_reason"] = f"prescore:{ps}"
                prescore_rejected.append(item)
        db.update_universe_status([r["id"] for r in prescore_rejected], "rejected", "prescore_low")

        # Sort by pre-score desc, trim per pillar
        scored.sort(key=lambda x: x["pre_score"], reverse=True)
        pillar_groups = {}
        for item in scored:
            p = item.get("pillar", "")
            p_key = p.strip().lower() if p.strip() else ""
            pillar_groups.setdefault(p_key, []).append(item)
        trimmed = []
        for p_key, items in pillar_groups.items():
            trimmed.extend(items[:MAX_PER_PILLAR_AI])

        # Pass 2.5: Rule-based intent pre-classification — bypass AI for high-confidence keywords
        rule_classified = []
        needs_ai = []
        for item in trimmed:
            classification = self._rule_classify_intent(item["keyword"])
            if classification:
                intent, buyer_readiness, ai_relevance = classification
                item["intent"] = intent
                item["buyer_readiness"] = buyer_readiness
                item["ai_relevance"] = ai_relevance
                item["rule_classified"] = True
                rule_classified.append(item)
            else:
                needs_ai.append(item)
        log.info(f"[Phase3] Rule-classified {len(rule_classified)} keywords, {len(needs_ai)} sent to AI")

        # Pass 3: AI validation (per-pillar) — only for keywords that need it
        accepted, ai_rejected = self._ai_validate(
            needs_ai, universe, pillars, negative_scope, ai_provider
        )
        accepted = rule_classified + accepted
        db.update_universe_status([r["id"] for r in ai_rejected], "rejected", "ai_low_relevance")
        db.update_universe_status([a["id"] for a in accepted], "accepted")

        validated_items = []
        for a in accepted:
            pre = float(a.get("pre_score", 0))
            ai_rel = float(a.get("ai_relevance", 0))
            combined = round(pre * 0.5 + ai_rel * 50 * 0.5, 1)
            validated_items.append({
                "keyword": a["keyword"],
                "pillar": a.get("pillar", ""),
                "ai_relevance": ai_rel,
                "intent": a.get("intent", ""),
                "buyer_readiness": a.get("buyer_readiness", 0.0),
                "source": a.get("source", ""),
                "commercial_score": pre,
                "final_score": combined,
            })
        db.bulk_insert_validated(session_id, project_id, validated_items)

        # Pass 4: Semantic dedup
        before_dedup = len(accepted)
        dedup_removed = self._semantic_dedup(session_id)

        # Pass 5: Category balance
        balance_removed = self._category_balance(session_id)

        final_count = before_dedup - dedup_removed - balance_removed
        db.update_session(session_id, phase3_done=1, validated_count=final_count)

        result = {
            "accepted": final_count,
            "rule_rejected": len(rule_rejected),
            "prescore_rejected": len(prescore_rejected),
            "ai_rejected": len(ai_rejected),
            "deduped": dedup_removed,
            "balance_dropped": balance_removed,
            "total_rejected": len(rule_rejected) + len(prescore_rejected) + len(ai_rejected) + dedup_removed + balance_removed,
        }
        log.info(f"[Phase3] Validated {final_count} keywords for {project_id}")
        return result

    # ── Main validate_stream (SSE) ──────────────────────────────────────

    def validate_stream(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
    ):
        """SSE generator for validation progress with per-pillar events."""
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

        # Store profile context for downstream prompt enrichment
        self._profile_ctx = profile

        import time as _time
        _t0 = _time.monotonic()

        # Pass 1: Rule filter
        rule_passed, rule_rejected = self._rule_filter(raw_items, negative_scope)
        db.update_universe_status([r["id"] for r in rule_rejected], "rejected", "rule_filter")
        _elapsed = round((_time.monotonic() - _t0) * 1000)
        _samples = [r["keyword"] for r in rule_rejected[:3]]
        yield f'data: {json.dumps({"type": "phase", "name": "rule_filter", "rejected": len(rule_rejected), "remaining": len(rule_passed), "elapsed_ms": _elapsed, "samples_rejected": _samples})}\n\n'

        # Pass 2: Pre-score
        scored = []
        prescore_rejected = []
        for item in rule_passed:
            ps = self._pre_score(item["keyword"], pillars)
            item["pre_score"] = ps
            item["pillar"] = item.get("pillar") or self._assign_pillar(item["keyword"], pillars)
            if ps >= PRE_SCORE_THRESHOLD:
                scored.append(item)
            else:
                item["reject_reason"] = f"prescore:{ps}"
                prescore_rejected.append(item)
        db.update_universe_status([r["id"] for r in prescore_rejected], "rejected", "prescore_low")
        _elapsed = round((_time.monotonic() - _t0) * 1000)
        _ps_samples = [f"{r['keyword']} ({r['pre_score']:.0f})" for r in sorted(prescore_rejected, key=lambda x: x.get('pre_score', 0))[:3]]
        yield f'data: {json.dumps({"type": "phase", "name": "prescore", "rejected": len(prescore_rejected), "remaining": len(scored), "threshold": PRE_SCORE_THRESHOLD, "elapsed_ms": _elapsed, "samples_rejected": _ps_samples})}\n\n'

        # Sort + trim per pillar
        scored.sort(key=lambda x: x["pre_score"], reverse=True)
        pillar_canonical = {}  # lowercase key -> display name (merges case variants)
        pillar_groups = {}
        for item in scored:
            p = item.get("pillar", "")
            p_key = p.strip().lower() if p.strip() else ""
            if p_key not in pillar_canonical:
                # Title-case for consistent display: "kerala spices" -> "Kerala Spices"
                pillar_canonical[p_key] = " ".join(w.capitalize() for w in p_key.split()) if p_key else p
            pillar_groups.setdefault(p_key, []).append(item)

        pillar_summary = {pillar_canonical.get(p, p): len(items) for p, items in pillar_groups.items()}
        yield f'data: {json.dumps({"type": "pillar_summary", "pillars": pillar_summary})}\n\n'

        # Pass 2.5: Rule-based intent pre-classification — bypass AI for high-confidence keywords
        rule_classified_stream: list[dict] = []
        for p_key in pillar_groups:
            needs_ai_items = []
            for item in pillar_groups[p_key]:
                classification = self._rule_classify_intent(item["keyword"])
                if classification:
                    intent, buyer_readiness, ai_relevance = classification
                    item["intent"] = intent
                    item["buyer_readiness"] = buyer_readiness
                    item["ai_relevance"] = ai_relevance
                    item["rule_classified"] = True
                    rule_classified_stream.append(item)
                else:
                    needs_ai_items.append(item)
            pillar_groups[p_key] = needs_ai_items
        _elapsed = round((_time.monotonic() - _t0) * 1000)
        yield f'data: {json.dumps({"type": "phase", "name": "rule_classify", "classified": len(rule_classified_stream), "sent_to_ai": sum(len(v) for v in pillar_groups.values()), "elapsed_ms": _elapsed})}\n\n'

        # A7: Pass 3 — Parallel pillar AI validation
        # Each pillar's batches run in its own thread (max AI_CONCURRENCY pillars at once).
        # Results are collected per-pillar then streamed sequentially so SSE stays ordered.
        yield f'data: {json.dumps({"type": "phase", "name": "ai_start", "pillars": len(pillar_groups), "concurrency": min(len(pillar_groups), AI_CONCURRENCY)})}\n\n'

        def _validate_pillar_all_batches(p_key: str, pillar_items: list[dict]) -> tuple[str, list, list, list]:
            """Run all batches for one pillar. Returns (p_key, accepted, rejected, events)."""
            items_for_ai = pillar_items[:MAX_PER_PILLAR_AI]
            batches = [items_for_ai[i:i+VALIDATION_BATCH_SIZE] for i in range(0, len(items_for_ai), VALIDATION_BATCH_SIZE)]
            total_batches = len(batches)
            pillar_accepted: list[dict] = []
            pillar_rejected: list[dict] = []
            events: list[str] = []
            pillar_name = pillar_canonical.get(p_key, p_key)

            events.append(f'data: {json.dumps({"type": "pillar_start", "pillar": pillar_name, "total_keywords": len(items_for_ai), "total_batches": total_batches})}\n\n')

            recent_rates = []
            for batch_num, batch in enumerate(batches, 1):
                batch_accepted, batch_rejected = self._validate_batch(
                    batch, universe, pillars, negative_scope, ai_provider
                )
                pillar_accepted.extend(batch_accepted)
                pillar_rejected.extend(batch_rejected)

                rate = len(batch_accepted) / max(len(batch), 1)
                recent_rates.append(rate)
                _batch_samples = [a["keyword"] for a in batch_accepted[:2]]
                events.append(f'data: {json.dumps({"type": "pillar_batch", "pillar": pillar_name, "batch": batch_num, "total_batches": total_batches, "batch_accepted": len(batch_accepted), "pillar_accepted": len(pillar_accepted), "rate": round(rate, 2), "remaining_batches": total_batches - batch_num, "samples": _batch_samples})}\n\n')

                if len(recent_rates) >= EARLY_STOP_WINDOW:
                    window = recent_rates[-EARLY_STOP_WINDOW:]
                    avg_rate = sum(window) / len(window)
                    if avg_rate < EARLY_STOP_MIN_RATE:
                        log.info(f"[Phase3] Early stop for pillar '{pillar_name}': avg {avg_rate:.2f}")
                        events.append(f'data: {json.dumps({"type": "pillar_early_stop", "pillar": pillar_name, "avg_rate": round(avg_rate, 2), "batches_done": batch_num})}\n\n')
                        break

            events.append(f'data: {json.dumps({"type": "pillar_complete", "pillar": pillar_name, "accepted": len(pillar_accepted), "rejected": len(pillar_rejected)})}\n\n')
            return p_key, pillar_accepted, pillar_rejected, events

        all_accepted = list(rule_classified_stream)  # start with rule-classified
        all_ai_rejected = []
        pillar_results: dict[str, tuple] = {}

        with ThreadPoolExecutor(max_workers=min(len(pillar_groups), AI_CONCURRENCY)) as _pool:
            _fut_map = {
                _pool.submit(_validate_pillar_all_batches, p_key, items): p_key
                for p_key, items in pillar_groups.items()
            }
            for _fut in as_completed(_fut_map):
                p_key_done = _fut_map[_fut]
                try:
                    pillar_results[p_key_done] = _fut.result()
                except Exception as _e:
                    log.warning(f"[Phase3] Pillar validation error for '{p_key_done}': {_e}")
                    pillar_results[p_key_done] = (p_key_done, [], [], [])

        # Stream in original pillar order (SSE must be ordered)
        for p_key in pillar_groups:
            if p_key not in pillar_results:
                continue
            _, pillar_accepted, pillar_rejected, events = pillar_results[p_key]
            for ev in events:
                _elapsed = round((_time.monotonic() - _t0) * 1000)
                yield ev
            all_accepted.extend(pillar_accepted)
            all_ai_rejected.extend(pillar_rejected)

        db.update_universe_status([r["id"] for r in all_ai_rejected], "rejected", "ai_low_relevance")
        db.update_universe_status([a["id"] for a in all_accepted], "accepted")

        validated_items = []
        for a in all_accepted:
            pre = float(a.get("pre_score", 0))
            ai_rel = float(a.get("ai_relevance", 0))
            combined = round(pre * 0.5 + ai_rel * 50 * 0.5, 1)
            validated_items.append({
                "keyword": a["keyword"], "pillar": a.get("pillar", ""),
                "ai_relevance": ai_rel, "intent": a.get("intent", ""),
                "buyer_readiness": a.get("buyer_readiness", 0.0), "source": a.get("source", ""),
                "commercial_score": pre,
                "final_score": combined,
            })
        db.bulk_insert_validated(session_id, project_id, validated_items)

        _elapsed = round((_time.monotonic() - _t0) * 1000)
        yield f'data: {json.dumps({"type": "phase", "name": "ai_batch", "accepted": len(all_accepted), "rejected": len(all_ai_rejected), "elapsed_ms": _elapsed})}\n\n'

        # Pass 4: Dedup
        dedup_removed = self._semantic_dedup(session_id)
        _elapsed = round((_time.monotonic() - _t0) * 1000)
        yield f'data: {json.dumps({"type": "phase", "name": "dedup", "removed": dedup_removed, "remaining": len(all_accepted) - dedup_removed, "elapsed_ms": _elapsed})}\n\n'

        # Pass 5: Balance
        balance_removed = self._category_balance(session_id)
        _elapsed = round((_time.monotonic() - _t0) * 1000)
        yield f'data: {json.dumps({"type": "phase", "name": "balance", "removed": balance_removed, "remaining": len(all_accepted) - dedup_removed - balance_removed, "elapsed_ms": _elapsed})}\n\n'

        final_count = len(all_accepted) - dedup_removed - balance_removed
        db.update_session(session_id, phase3_done=1, validated_count=final_count)

        _total_elapsed = round((_time.monotonic() - _t0) * 1000)
        yield f'data: {json.dumps({"type": "complete", "validated": final_count, "total_rejected": len(rule_rejected) + len(prescore_rejected) + len(all_ai_rejected) + dedup_removed + balance_removed, "prescore_rejected": len(prescore_rejected), "elapsed_ms": _total_elapsed})}\n\n'

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
        """AI batch validation with priority sort + early stop + controlled concurrency."""
        # Priority sort: commercial keywords first
        items.sort(key=lambda x: x.get("pre_score", self._commercial_priority(x["keyword"])), reverse=True)

        batches = [items[i:i+VALIDATION_BATCH_SIZE] for i in range(0, len(items), VALIDATION_BATCH_SIZE)]
        accepted = []
        rejected = []

        with ThreadPoolExecutor(max_workers=AI_CONCURRENCY) as pool:
            futures = {}
            for batch in batches:
                f = pool.submit(self._validate_batch, batch, universe, pillars, negative_scope, provider)
                futures[f] = batch

            for future in as_completed(futures):
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
                if cached.get("ai_relevance", 0) >= 0.75 and cached.get("intent") != "informational":
                    cached_accepted.append(item)
                else:
                    cached_rejected.append(item)
            else:
                uncached.append(item)

        if not uncached:
            return cached_accepted, cached_rejected

        # AI call
        keywords_list = "\n".join(f"- {it['keyword']}" for it in uncached)
        _ctx = getattr(self, "_profile_ctx", {}) or {}
        prompt = VALIDATE_USER.format(
            universe=universe,
            pillars_str=", ".join(pillars),
            negative_scope_str=", ".join(negative_scope[:15]),
            target_locations=", ".join(_ctx.get("target_locations", [])),
            business_locations=", ".join(_ctx.get("business_locations", [])),
            cultural_context=", ".join(_ctx.get("cultural_context", [])),
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

                if relevance >= 0.75 and intent != "informational":
                    accepted.append(item)
                else:
                    item["reject_reason"] = f"ai:relevance={relevance},intent={intent}"
                    rejected.append(item)
        else:
            # AI failed — accept all with rule-based intent classification
            log.warning("[Phase3] AI validation returned no parseable results, accepting batch with neutral scores")
            for item in uncached:
                item["ai_relevance"] = 0.5
                item["intent"] = self._rule_intent(item.get("keyword", ""))
                item["buyer_readiness"] = 0.7 if item["intent"] in ("transactional", "commercial") else 0.4
                accepted.append(item)

        return accepted, rejected

    def _rule_intent(self, keyword: str) -> str:
        """Rule-based intent classification fallback when AI is unavailable."""
        kw = keyword.lower()
        # Transactional: clear buy/purchase/order signals
        _TRANSACTIONAL = {"buy ", "purchase", "order ", "shop ", "get ", " deal", "coupon", "discount", " price", " cost", "cheap"}
        if any(t in kw for t in _TRANSACTIONAL):
            return "transactional"
        # Commercial: research-to-buy signals (comparing, wholesale, bulk, supplier)
        _COMMERCIAL = {"best ", "top ", " review", " vs ", "wholesale", "bulk ", "supplier", "distributor", "compare", "export", " brand", "online"}
        if any(c in kw for c in _COMMERCIAL):
            return "commercial"
        # Informational fallback (still included if not filtered by negative_scope)
        _INFORMATIONAL = {"how to", "what is", "why ", "guide", "tutorial", "tips", "benefit", "effect", "history"}
        if any(i in kw for i in _INFORMATIONAL):
            return "informational"
        return "commercial"  # default for product keywords

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
                "SELECT id, keyword, intent, ai_relevance, pillar FROM kw2_validated_keywords WHERE session_id=? ORDER BY ai_relevance DESC",
                (session_id,),
            ).fetchall()

            total = len(rows)
            if total == 0:
                return 0

            # Skip balance for small sets or single-pillar sessions
            unique_pillars = set(r["pillar"] for r in rows if r["pillar"])
            if total < 200 or len(unique_pillars) <= 1:
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

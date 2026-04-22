"""
kw2 keyword_brain — Unified keyword expansion, normalization, multi-pillar
assignment, inline validation, and pre-clustering.

This is the engine for Super Phase 2 (EXPAND + REVIEW).
Replaces the old keyword_generator.py + keyword_validator.py pipeline.
"""
import re
import json
import logging
import hashlib
import time as _time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from collections import defaultdict

from engines.kw2 import db
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2.normalizer import (
    canonical, display_form, detect_pillars, assign_role,
    merge_keyword_batch, semantic_dedup,
)
from engines.kw2.constants import (
    NEGATIVE_PATTERNS, TRANSACTIONAL_TEMPLATES, COMMERCIAL_TEMPLATES,
    LOCAL_TEMPLATES, NAVIGATIONAL_TEMPLATES, GARBAGE_WORDS, VALIDATION_BATCH_SIZE,
    CANDIDATES_PER_PILLAR, SEMANTIC_DEDUP_THRESHOLD,
    PILLAR_CONFIDENCE_THRESHOLD, EMBEDDING_MODEL,
    CLUSTER_SIMILARITY_THRESHOLD, CLUSTER_NAME_MIN_SIZE,
    AI_EXPAND_COMMERCIAL, AI_EXPAND_INFORMATIONAL, AI_EXPAND_NAVIGATIONAL,
    AI_CONCURRENCY,
    SKIP_VALIDATION_SOURCES, SKIP_VALIDATION_MIN_SCORE, SKIP_VALIDATION_RELEVANCE,
    CLUSTER_NAME_BATCH_SIZE, SEED_INTENT_MODIFIERS_EXCLUDE,
)
from engines.kw2.prompts import (
    V2_EXPAND_COMMERCIAL_SYSTEM, V2_EXPAND_COMMERCIAL_USER,
    V2_EXPAND_INFORMATIONAL_SYSTEM, V2_EXPAND_INFORMATIONAL_USER,
    V2_EXPAND_NAVIGATIONAL_SYSTEM, V2_EXPAND_NAVIGATIONAL_USER,
    V2_VALIDATE_SYSTEM, V2_VALIDATE_USER,
    CLUSTER_NAME_SYSTEM, CLUSTER_NAME_USER,
    BATCH_CLUSTER_NAME_SYSTEM, BATCH_CLUSTER_NAME_USER,
)

log = logging.getLogger("kw2.brain")

# In-memory validation cache (keyword|universe → AI result)
_validation_cache: dict[str, dict] = {}

# ── Expand safety limits ─────────────────────────────────────────────────
MAX_RAW_KEYWORDS = 5000           # Hard cap on raw keywords before filtering
EXPAND_TIMEOUT_SECONDS = 300      # 5 min total timeout for the expand pipeline
VALIDATION_FUTURE_TIMEOUT = 120   # Per-batch validation timeout (seconds)


class _CancelToken:
    """Lightweight cooperative cancellation signal for expand pipelines."""
    def __init__(self):
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

# ── Intent normalization: 7+ raw AI values → 3 canonical ─────────────────
INTENT_MAP = {
    "purchase": "commercial",
    "transactional": "commercial",
    "commercial": "commercial",
    "comparison": "commercial",
    "buying": "commercial",
    "research": "informational",
    "informational": "informational",
    "educational": "informational",
    "how-to": "informational",
    "local": "navigational",
    "brand": "navigational",
    "navigational": "navigational",
}


def _normalize_intent(raw_intent: str) -> str:
    """Map raw AI intent labels to 3 canonical intents."""
    return INTENT_MAP.get(raw_intent.lower().strip(), "informational")


class _ExpandCancelled(Exception):
    """Raised when expand is cancelled (client disconnect)."""
    pass


class _ExpandTimeout(Exception):
    """Raised when expand exceeds time budget."""
    pass


class KeywordBrain:
    """
    Unified expansion pipeline:
    1. Generate keywords from multiple layers (seeds, rules, suggest, competitor, BI, AI expand)
    2. Normalize + merge variants
    3. Negative filter
    4. Multi-pillar assignment + role detection
    5. Inline AI validation (no global cap, all intents accepted)
    6. Semantic dedup
    7. Pre-cluster for review
    8. Write to kw2_keywords table
    """

    def expand(self, project_id: str, session_id: str,
               competitor_urls: list[str] | None = None,
               ai_provider: str = "auto") -> dict:
        """Run the full expansion pipeline synchronously. Returns summary stats."""
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("Business profile not found — run Phase 1 first")

        pillars = profile.get("pillars", [])
        if isinstance(pillars, str):
            pillars = json.loads(pillars) if pillars else []
        modifiers = profile.get("modifiers", [])
        if isinstance(modifiers, str):
            modifiers = json.loads(modifiers) if modifiers else []
        negative_scope = profile.get("negative_scope", [])
        if isinstance(negative_scope, str):
            negative_scope = json.loads(negative_scope) if negative_scope else []
        universe = profile.get("universe", "")
        geo = profile.get("geo_scope", "") or ""

        # Store profile context for downstream prompt enrichment
        self._profile_ctx = profile

        log.info("brain.expand: %d pillars, universe=%s", len(pillars), universe)

        # Step 1: Generate raw keywords from all layers
        raw = []
        raw += self._build_seeds(pillars, modifiers)
        raw += self._rule_expand(pillars, modifiers, geo)
        raw += self._google_suggest(pillars)
        if competitor_urls:
            raw += self._competitor_keywords(competitor_urls, pillars)
        raw += self._bi_competitor_keywords(session_id, pillars)
        raw += self._ai_expand_all_intents(pillars, modifiers, universe, geo, ai_provider)

        log.info("brain: %d raw keywords generated", len(raw))

        # Step 2: Negative filter
        passed, rejected = self._negative_filter(raw, negative_scope)
        log.info("brain: %d passed filter, %d rejected", len(passed), len(rejected))

        # Step 3: Normalize + merge variants
        merged = merge_keyword_batch(passed)
        log.info("brain: %d after merge (from %d passed)", len(merged), len(passed))

        # Step 4: Multi-pillar assignment + role detection
        for kw in merged:
            if not kw.get("pillars"):
                matches = detect_pillars(kw["keyword"], pillars,
                                         threshold=PILLAR_CONFIDENCE_THRESHOLD)
                kw["pillars"] = [m["pillar"] for m in matches]
                if not kw["pillars"] and pillars:
                    # Orphan — assign to first pillar as fallback
                    kw["pillars"] = [pillars[0]]
            kw["role"] = assign_role(kw["keyword"], pillars, [
                {"pillar": p, "confidence": 0.5} for p in kw["pillars"]
            ])

        # Step 5: Inline AI validation (no global cap)
        validated, val_rejected = self._validate_all(
            merged, universe, pillars, negative_scope, ai_provider
        )
        log.info("brain: %d validated, %d validation-rejected",
                 len(validated), len(val_rejected))

        # Step 6: Semantic dedup
        kept, deduped = semantic_dedup(
            validated, threshold=SEMANTIC_DEDUP_THRESHOLD, score_key="ai_relevance"
        )
        log.info("brain: %d after semantic dedup (removed %d)", len(kept), len(deduped))

        # Step 7: Pre-cluster
        clusters = self._pre_cluster(kept, ai_provider)
        log.info("brain: %d clusters formed", len(clusters))

        # Step 8: Assign cluster_ids and write to DB
        cluster_map = {}
        for cl in clusters:
            for kw_canon in cl["keyword_canonicals"]:
                cluster_map[kw_canon] = cl["cluster_id"]

        for kw in kept:
            kw["cluster_id"] = cluster_map.get(kw["canonical"], "")
            kw["status"] = "candidate"

        # Write keywords
        db.bulk_insert_keywords(session_id, project_id, kept)

        # Write rejected (for audit trail)
        for r in rejected + val_rejected + deduped:
            r["status"] = "rejected"
            r.setdefault("canonical", canonical(r.get("keyword", "")))
            r.setdefault("pillars", [])
            r.setdefault("sources", r.get("sources", []))
            r.setdefault("variants", [])
        db.bulk_insert_keywords(session_id, project_id,
                                rejected + val_rejected + deduped)

        # Write clusters
        for cl in clusters:
            cl_kws = [k for k in kept if k.get("cluster_id") == cl["cluster_id"]]
            kw_ids = [k.get("id", "") for k in cl_kws]
            # Determine pillar for this cluster (most common pillar among its keywords)
            pillar_counts: dict[str, int] = defaultdict(int)
            for k in cl_kws:
                for p in k.get("pillars", []):
                    pillar_counts[p] += 1
            main_pillar = max(pillar_counts, key=pillar_counts.get) if pillar_counts else ""

            conn = db.get_conn()
            try:
                conn.execute(
                    """INSERT INTO kw2_clusters
                       (id, session_id, project_id, pillar, cluster_name, keyword_ids,
                        top_keyword, avg_score, keyword_count, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (cl["cluster_id"], session_id, project_id,
                     main_pillar, cl["name"],
                     json.dumps(kw_ids),
                     cl.get("top_keyword", ""),
                     cl.get("avg_score", 0.0),
                     len(cl_kws),
                     db._now()),
                )
                conn.commit()
            finally:
                conn.close()

        # Update session
        db.set_phase_status(session_id, "expand", "review_pending")
        db.update_session(session_id,
                          universe_count=len(kept),
                          current_phase="expand_review")

        # Per-pillar stats (case-insensitive comparison)
        pillar_stats = {}
        for p in pillars:
            p_lower = p.lower()
            p_kws = [k for k in kept
                      if any(pp.lower() == p_lower for pp in k.get("pillars", []))]
            pillar_stats[p] = len(p_kws)

        return {
            "total_generated": len(raw),
            "after_filter": len(passed),
            "after_merge": len(merged),
            "validated": len(validated),
            "after_dedup": len(kept),
            "rejected": len(rejected) + len(val_rejected) + len(deduped),
            "clusters": len(clusters),
            "pillar_stats": pillar_stats,
        }

    def expand_stream(self, project_id: str, session_id: str,
                      competitor_urls: list[str] | None = None,
                      ai_provider: str = "auto",
                      cancel: _CancelToken | None = None):
        """SSE generator yielding progress events during expansion."""
        if cancel is None:
            cancel = _CancelToken()
        start_time = _time.time()

        def _check_budget():
            """Raise if time budget exhausted or cancelled."""
            if cancel.cancelled:
                raise _ExpandCancelled("Client disconnected")
            elapsed = _time.time() - start_time
            if elapsed > EXPAND_TIMEOUT_SECONDS:
                raise _ExpandTimeout(f"Expand exceeded {EXPAND_TIMEOUT_SECONDS}s budget ({elapsed:.0f}s elapsed)")

        profile = db.load_business_profile(project_id)
        if not profile:
            yield _sse("error", {"message": "Business profile not found"})
            return

        pillars = profile.get("pillars", [])
        if isinstance(pillars, str):
            pillars = json.loads(pillars) if pillars else []
        modifiers = profile.get("modifiers", [])
        if isinstance(modifiers, str):
            modifiers = json.loads(modifiers) if modifiers else []
        negative_scope = profile.get("negative_scope", [])
        if isinstance(negative_scope, str):
            negative_scope = json.loads(negative_scope) if negative_scope else []
        universe = profile.get("universe", "")
        geo = profile.get("geo_scope", "") or ""

        # Store profile context for downstream prompt enrichment
        self._profile_ctx = profile

        raw = []

        try:
            # Layer 1: Seeds
            _check_budget()
            yield _sse("layer", {"name": "seeds", "status": "running"})
            seeds = self._build_seeds(pillars, modifiers)
            raw += seeds
            yield _sse("layer", {"name": "seeds", "status": "done", "count": len(seeds)})

            # Layer 2: Rules
            _check_budget()
            yield _sse("layer", {"name": "rules", "status": "running"})
            rules = self._rule_expand(pillars, modifiers, geo)
            raw += rules
            yield _sse("layer", {"name": "rules", "status": "done", "count": len(rules)})

            # Layer 3: Google Suggest
            _check_budget()
            yield _sse("layer", {"name": "suggest", "status": "running"})
            suggest = self._google_suggest(pillars)
            raw += suggest
            yield _sse("layer", {"name": "suggest", "status": "done", "count": len(suggest)})

            # Layer 4: Competitor
            if competitor_urls:
                _check_budget()
                yield _sse("layer", {"name": "competitor", "status": "running"})
                comp = self._competitor_keywords(competitor_urls, pillars)
                raw += comp
                yield _sse("layer", {"name": "competitor", "status": "done", "count": len(comp)})

            # Layer 5: BI Competitor
            _check_budget()
            yield _sse("layer", {"name": "bi_competitor", "status": "running"})
            bi_comp = self._bi_competitor_keywords(session_id, pillars)
            raw += bi_comp
            yield _sse("layer", {"name": "bi_competitor", "status": "done", "count": len(bi_comp)})

            # Backpressure guard: cap raw keywords before expensive AI expand (B52)
            if len(raw) > MAX_RAW_KEYWORDS:
                log.warning("raw keyword count %d exceeds cap %d — skipping AI expand layer",
                            len(raw), MAX_RAW_KEYWORDS)
                yield _sse("layer", {"name": "ai_expand", "status": "skipped",
                                      "reason": f"Raw count ({len(raw)}) exceeds cap ({MAX_RAW_KEYWORDS})"})
            else:
                # Layer 6: AI Expand (3 intents)
                _check_budget()
                yield _sse("layer", {"name": "ai_expand", "status": "running"})
                ai_kws = self._ai_expand_all_intents(pillars, modifiers, universe, geo, ai_provider)
                raw += ai_kws
                yield _sse("layer", {"name": "ai_expand", "status": "done", "count": len(ai_kws)})

            # Processing stages
            _check_budget()
            yield _sse("stage", {"name": "filter", "status": "running"})
            passed, rejected = self._negative_filter(raw, negative_scope)
            yield _sse("stage", {"name": "filter", "status": "done",
                                  "passed": len(passed), "rejected": len(rejected)})

            _check_budget()
            yield _sse("stage", {"name": "normalize", "status": "running"})
            merged = merge_keyword_batch(passed)
            yield _sse("stage", {"name": "normalize", "status": "done", "count": len(merged)})

            _check_budget()
            yield _sse("stage", {"name": "pillar_assign", "status": "running"})
            for kw in merged:
                if not kw.get("pillars"):
                    matches = detect_pillars(kw["keyword"], pillars,
                                             threshold=PILLAR_CONFIDENCE_THRESHOLD)
                    kw["pillars"] = [m["pillar"] for m in matches]
                    if not kw["pillars"] and pillars:
                        kw["pillars"] = [pillars[0]]
                kw["role"] = assign_role(kw["keyword"], pillars, [
                    {"pillar": p, "confidence": 0.5} for p in kw["pillars"]
                ])
            bridge_count = sum(1 for k in merged if k.get("role") == "bridge")
            yield _sse("stage", {"name": "pillar_assign", "status": "done",
                                  "bridges": bridge_count})

            _check_budget()
            yield _sse("stage", {"name": "validate", "status": "running"})
            validated, val_rejected = self._validate_all(
                merged, universe, pillars, negative_scope, ai_provider,
                cancel=cancel,
            )
            yield _sse("stage", {"name": "validate", "status": "done",
                                  "validated": len(validated), "rejected": len(val_rejected)})

            _check_budget()
            yield _sse("stage", {"name": "dedup", "status": "running"})
            kept, deduped = semantic_dedup(
                validated, threshold=SEMANTIC_DEDUP_THRESHOLD, score_key="ai_relevance"
            )
            yield _sse("stage", {"name": "dedup", "status": "done",
                                  "kept": len(kept), "removed": len(deduped)})

            _check_budget()
            yield _sse("stage", {"name": "cluster", "status": "running"})
            clusters = self._pre_cluster(kept, ai_provider)
            yield _sse("stage", {"name": "cluster", "status": "done",
                                  "clusters": len(clusters)})

        except _ExpandCancelled:
            log.info("expand cancelled (client disconnect) for session %s", session_id)
            yield _sse("error", {"message": "Expand cancelled — client disconnected",
                                  "recoverable": True})
            return
        except _ExpandTimeout as exc:
            log.warning("expand timed out for session %s: %s", session_id, exc)
            yield _sse("error", {"message": str(exc), "recoverable": True,
                                  "elapsed": round(_time.time() - start_time)})
            return

        # Write to DB (same as expand())
        cluster_map = {}
        for cl in clusters:
            for kw_canon in cl["keyword_canonicals"]:
                cluster_map[kw_canon] = cl["cluster_id"]
        for kw in kept:
            kw["cluster_id"] = cluster_map.get(kw["canonical"], "")
            kw["status"] = "candidate"

        db.bulk_insert_keywords(session_id, project_id, kept)

        for r in rejected + val_rejected + deduped:
            r["status"] = "rejected"
            r.setdefault("canonical", canonical(r.get("keyword", "")))
            r.setdefault("pillars", [])
            r.setdefault("sources", r.get("sources", []))
            r.setdefault("variants", [])
        db.bulk_insert_keywords(session_id, project_id,
                                rejected + val_rejected + deduped)

        for cl in clusters:
            cl_kws = [k for k in kept if k.get("cluster_id") == cl["cluster_id"]]
            pillar_counts: dict[str, int] = defaultdict(int)
            for k in cl_kws:
                for p in k.get("pillars", []):
                    pillar_counts[p] += 1
            main_pillar = max(pillar_counts, key=pillar_counts.get) if pillar_counts else ""
            conn = db.get_conn()
            try:
                conn.execute(
                    """INSERT INTO kw2_clusters
                       (id, session_id, project_id, pillar, cluster_name, keyword_ids,
                        top_keyword, avg_score, keyword_count, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (cl["cluster_id"], session_id, project_id,
                     main_pillar, cl["name"], json.dumps([]),
                     cl.get("top_keyword", ""), cl.get("avg_score", 0.0),
                     len(cl_kws), db._now()),
                )
                conn.commit()
            finally:
                conn.close()

        db.set_phase_status(session_id, "expand", "review_pending")
        db.update_session(session_id, universe_count=len(kept),
                          current_phase="expand_review")

        pillar_stats = {}
        for p in pillars:
            pillar_stats[p] = sum(1 for k in kept if p in k.get("pillars", []))

        elapsed = round(_time.time() - start_time)
        yield _sse("complete", {
            "total": len(kept),
            "clusters": len(clusters),
            "pillar_stats": pillar_stats,
            "elapsed_seconds": elapsed,
        })

    # ── Generation layers ────────────────────────────────────────────────

    def _build_seeds(self, pillars: list[str], modifiers: list[str]) -> list[dict]:
        """Layer 1: pillar × modifier seed combinations.

        Only QUALIFIER modifiers (organic, wholesale, bulk, premium…) are used as
        seed prefixes. Intent-only words (online, price, buy…) are excluded here
        because they already appear in TRANSACTIONAL_TEMPLATES — using them as
        prefixes produces invalid phrases like 'online cardamom' or 'price black pepper'.
        """
        seeds = []
        # Filter to only qualifier modifiers for seed building
        qualifier_mods = [
            m for m in modifiers
            if m.lower() not in SEED_INTENT_MODIFIERS_EXCLUDE
        ]
        for p in pillars:
            seeds.append({"keyword": p, "source": "seeds", "pillar": p, "raw_score": 80})
            core = _extract_core(p)
            if core != p.lower():
                seeds.append({"keyword": core, "source": "seeds", "pillar": p, "raw_score": 78})
            for m in qualifier_mods:
                seeds.append({"keyword": f"{m} {p}", "source": "seeds", "pillar": p, "raw_score": 70})
                seeds.append({"keyword": f"{p} {m}", "source": "seeds", "pillar": p, "raw_score": 70})
                if core != p.lower():
                    seeds.append({"keyword": f"{m} {core}", "source": "seeds", "pillar": p, "raw_score": 68})
                    seeds.append({"keyword": f"{core} {m}", "source": "seeds", "pillar": p, "raw_score": 68})
        return seeds

    def _rule_expand(self, pillars: list[str], modifiers: list[str],
                     geo: str) -> list[dict]:
        """Layer 2: template-based expansion (transactional + commercial + local)."""
        results = []
        for p in pillars:
            core = _extract_core(p)
            targets = list({p.lower(), core}) if core != p.lower() else [p.lower()]
            for k in targets:
                for tmpl in TRANSACTIONAL_TEMPLATES:
                    results.append({"keyword": tmpl.format(k=k), "source": "rules",
                                    "pillar": p, "raw_score": 65})
                for tmpl in COMMERCIAL_TEMPLATES:
                    alt_pillars = [_extract_core(op) for op in pillars if op != p]
                    alt = alt_pillars[0] if alt_pillars else k
                    results.append({"keyword": tmpl.format(k=k, alt=alt), "source": "rules",
                                    "pillar": p, "raw_score": 58})
                if geo:
                    for tmpl in LOCAL_TEMPLATES:
                        results.append({"keyword": tmpl.format(k=k, loc=geo), "source": "rules",
                                        "pillar": p, "raw_score": 55})
                for tmpl in NAVIGATIONAL_TEMPLATES:
                    results.append({"keyword": tmpl.format(k=k), "source": "rules",
                                    "pillar": p, "raw_score": 50, "intent": "navigational"})
        return results

    def _google_suggest(self, pillars: list[str]) -> list[dict]:
        """Layer 3: Google autosuggest enrichment."""
        results = []
        try:
            from engines.intelligent_crawl_engine import GoogleSuggestEnricher
            enricher = GoogleSuggestEnricher()
            try:
                suggestions = enricher.enrich(pillars)
                for s in (suggestions or []):
                    text = (s if isinstance(s, str)
                            else getattr(s, "keyword", None)
                            or (s.get("keyword", "") if hasattr(s, "get") else str(s)))
                    pillar = (getattr(s, "pillar", "") if not isinstance(s, str)
                              else "")
                    if text and len(text) >= 3:
                        results.append({"keyword": text, "source": "suggest",
                                        "pillar": pillar, "raw_score": 60})
            except Exception as e:
                log.warning("suggest enricher failed: %s", e)
        except ImportError:
            log.warning("GoogleSuggestEnricher not available")
        return results

    def _competitor_keywords(self, urls: list[str],
                             pillars: list[str]) -> list[dict]:
        """Layer 4: competitor website keyword extraction."""
        results = []
        try:
            from engines.intelligent_crawl_engine import SmartCompetitorAnalyzer
            analyzer = SmartCompetitorAnalyzer()
            for url in urls[:4]:
                try:
                    comp_kws = analyzer.analyze_competitor(url, pillars, max_pages=15)
                    for kw in (comp_kws or []):
                        text = kw if isinstance(kw, str) else kw.get("keyword", "")
                        if text:
                            results.append({"keyword": text, "source": "competitor",
                                            "pillar": "", "raw_score": 55})
                except Exception as e:
                    log.warning("competitor analysis failed for %s: %s", url, e)
        except ImportError:
            log.warning("SmartCompetitorAnalyzer not available")
        return results

    def _bi_competitor_keywords(self, session_id: str,
                                pillars: list[str]) -> list[dict]:
        """Layer 5: pre-analyzed competitor keywords from BI stage."""
        results = []
        bi_kws = db.get_biz_competitor_keywords(session_id)
        for kw in bi_kws:
            text = kw.get("keyword", "")
            if not text:
                continue
            intent = _normalize_intent(kw.get("intent", "commercial"))
            conf = float(kw.get("confidence", 0.7))
            if intent in ("transactional", "purchase", "commercial"):
                score = 70 * conf
            elif intent == "commercial":
                score = 60 * conf
            else:
                score = 45 * conf
            results.append({"keyword": text, "source": "bi_competitor",
                            "pillar": "", "raw_score": score,
                            "intent": intent})
        return results

    def _ai_expand_all_intents(self, pillars: list[str], modifiers: list[str],
                                universe: str, geo: str,
                                provider: str) -> list[dict]:
        """Layer 6: AI expansion with 3 intent batches per pillar, parallelized."""
        if not pillars:
            return []

        # Guard: empty pillar list would produce no useful keywords
        valid_pillars = [p for p in pillars if p and p.strip()]
        if not valid_pillars:
            log.warning("[AI expand] All pillars are empty/blank — skipping")
            return []

        # Build task list: one entry per (pillar × intent) combination
        intent_specs = [
            ("commercial",    V2_EXPAND_COMMERCIAL_SYSTEM,    V2_EXPAND_COMMERCIAL_USER,    AI_EXPAND_COMMERCIAL),
            ("informational", V2_EXPAND_INFORMATIONAL_SYSTEM, V2_EXPAND_INFORMATIONAL_USER, AI_EXPAND_INFORMATIONAL),
            ("navigational",  V2_EXPAND_NAVIGATIONAL_SYSTEM,  V2_EXPAND_NAVIGATIONAL_USER,  AI_EXPAND_NAVIGATIONAL),
        ]
        tasks = []
        for p in valid_pillars:
            core = _extract_core(p)
            mod_str = ", ".join(modifiers[:10]) if modifiers else "none"
            for intent_label, system, user_tpl, count in intent_specs:
                tasks.append((p, intent_label, system, user_tpl, count, core, mod_str))

        def _run_task(task):
            p, intent_label, system, user_tpl, count, core, mod_str = task
            kws = self._ai_expand_batch(
                system, user_tpl,
                universe=universe, pillar=p, core_term=core,
                modifiers=mod_str, count=count, geo=geo, provider=provider,
            )
            for kw in kws:
                kw["intent"] = _normalize_intent(kw.get("intent", intent_label))
            return kws

        results = []
        # Run all tasks concurrently, capped at AI_CONCURRENCY workers
        with ThreadPoolExecutor(max_workers=AI_CONCURRENCY) as pool:
            futures = [pool.submit(_run_task, t) for t in tasks]
            for f in futures:
                try:
                    results.extend(f.result())
                except Exception as e:
                    log.warning("[AI expand] task failed: %s", e)

        log.info("AI expand (parallel): %d keywords across %d pillars × 3 intents",
                 len(results), len(valid_pillars))
        return results

    def _ai_expand_batch(self, system: str, user_template: str, *,
                          universe: str, pillar: str, core_term: str,
                          modifiers: str, count: int, geo: str,
                          provider: str) -> list[dict]:
        """Single AI call for one intent batch of one pillar."""
        _ctx = getattr(self, "_profile_ctx", {}) or {}
        prompt = user_template.format(
            universe=universe, pillar=pillar, core_term=core_term,
            modifiers=modifiers, count=count, geo=geo or "global",
            target_locations=", ".join(_ctx.get("target_locations", [])),
            business_locations=", ".join(_ctx.get("business_locations", [])),
            languages=", ".join(_ctx.get("languages", [])),
            cultural_context=", ".join(_ctx.get("cultural_context", [])),
            usp=_ctx.get("usp", ""),
            customer_voice=(_ctx.get("customer_reviews", "") or "")[:300],
        )
        response = kw2_ai_call(prompt, system=system, provider=provider)
        if not response:
            return []

        results = []
        for line in response.strip().split("\n"):
            text = re.sub(r"^[\d\.\-\*\•\)]+\s*", "", line).strip()
            text = re.sub(r"[\"']", "", text).strip()
            if text and len(text) >= 4:
                results.append({
                    "keyword": text, "source": "ai_expand",
                    "pillar": pillar, "raw_score": 50,
                })
        return results[:count]

    # ── Filtering ────────────────────────────────────────────────────────

    def _negative_filter(self, keywords: list[dict],
                         negative_scope: list[str]) -> tuple[list[dict], list[dict]]:
        """Hard-reject keywords matching negative patterns."""
        patterns = list(NEGATIVE_PATTERNS)
        for ns in negative_scope:
            if ns and ns.lower() not in [p.lower() for p in patterns]:
                patterns.append(ns.lower())

        passed, rejected = [], []
        for kw in keywords:
            text = kw.get("keyword", "").lower()
            if not text or len(text.split()) < 2:
                kw["reject_reason"] = "too_short"
                rejected.append(kw)
                continue

            # Garbage ratio check
            words = text.split()
            garbage_count = sum(1 for w in words if w in GARBAGE_WORDS)
            if len(words) > 0 and garbage_count / len(words) > 0.5:
                kw["reject_reason"] = "garbage_ratio"
                rejected.append(kw)
                continue

            hit = False
            for pat in patterns:
                if pat.lower() in text:
                    kw["reject_reason"] = f"negative:{pat}"
                    rejected.append(kw)
                    hit = True
                    break
            if not hit:
                passed.append(kw)
        return passed, rejected

    # ── Validation ───────────────────────────────────────────────────────

    def _validate_all(self, keywords: list[dict], universe: str,
                      pillars: list[str], negative_scope: list[str],
                      provider: str, cancel: _CancelToken | None = None) -> tuple[list[dict], list[dict]]:
        """AI validate all keywords — no global cap, all intents accepted.

        Optimization: keywords from rules/seeds with raw_score >= SKIP_VALIDATION_MIN_SCORE
        are pre-approved without AI. Template-generated phrases like 'buy cardamom online'
        are structurally guaranteed to be valid commercial keywords — AI just confirms
        what we already know at significant latency cost.
        """
        if not keywords:
            return [], []

        # Pre-approve high-confidence rule/seed keywords — skip AI for these
        pre_approved: list[dict] = []
        to_validate: list[dict] = []
        for kw in keywords:
            src = kw.get("source", "")
            score = float(kw.get("raw_score", 0))
            if src in SKIP_VALIDATION_SOURCES and score >= SKIP_VALIDATION_MIN_SCORE:
                kw["ai_relevance"] = SKIP_VALIDATION_RELEVANCE
                kw.setdefault("intent",
                              _normalize_intent(kw.get("intent", "commercial")))
                kw.setdefault("buyer_readiness", 0.70)
                pre_approved.append(kw)
            else:
                to_validate.append(kw)

        log.info(
            "brain: pre-approved %d high-score seeds/rules, sending %d to AI validation",
            len(pre_approved), len(to_validate),
        )

        if not to_validate:
            return pre_approved, []

        # Sort by raw_score descending
        sorted_kws = sorted(to_validate, key=lambda k: float(k.get("raw_score", 0)), reverse=True)

        # Batch into chunks
        batches = []
        for i in range(0, len(sorted_kws), VALIDATION_BATCH_SIZE):
            batches.append(sorted_kws[i:i + VALIDATION_BATCH_SIZE])

        validated = []
        rejected = []

        # Process batches with thread pool (2 workers to reduce rate pressure)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = []
            for batch in batches:
                if cancel and cancel.cancelled:
                    log.info("validation cancelled — stopping batch submission")
                    break
                futures.append(pool.submit(
                    self._validate_batch, batch, universe, pillars,
                    negative_scope, provider
                ))
                _time.sleep(3)  # 3s delay between submissions to reduce rate pressure
            for future in futures:
                if cancel and cancel.cancelled:
                    future.cancel()
                    continue
                try:
                    v, r = future.result(timeout=VALIDATION_FUTURE_TIMEOUT)
                    validated.extend(v)
                    rejected.extend(r)
                except FuturesTimeoutError:
                    log.warning("validation batch timed out after %ds — accepting remaining with neutral scores", VALIDATION_FUTURE_TIMEOUT)
                except Exception as e:
                    log.error("validation batch failed: %s", e)

        # Merge pre-approved with AI-validated
        return pre_approved + validated, rejected

    def _validate_batch(self, batch: list[dict], universe: str,
                        pillars: list[str], negative_scope: list[str],
                        provider: str) -> tuple[list[dict], list[dict]]:
        """Validate a single batch via AI."""
        # Check cache first
        uncached = []
        cached_validated = []
        for kw in batch:
            cache_key = hashlib.md5(
                f"{kw['keyword']}|{universe}".encode()
            ).hexdigest()
            if cache_key in _validation_cache:
                cached = _validation_cache[cache_key]
                kw["ai_relevance"] = cached.get("relevance", 0.5)
                kw["intent"] = _normalize_intent(cached.get("intent", kw.get("intent", "")))
                kw["buyer_readiness"] = cached.get("buyer_readiness", 0.0)
                if kw["ai_relevance"] >= 0.3:
                    cached_validated.append(kw)
            else:
                uncached.append(kw)

        if not uncached:
            return cached_validated, []

        # Build prompt
        kw_list = "\n".join(f"- {k['keyword']}" for k in uncached)
        _ctx = getattr(self, "_profile_ctx", {}) or {}
        prompt = V2_VALIDATE_USER.format(
            universe=universe,
            pillars_str=", ".join(pillars),
            negative_scope_str=", ".join(negative_scope[:15]),
            target_locations=", ".join(_ctx.get("target_locations", [])),
            business_locations=", ".join(_ctx.get("business_locations", [])),
            cultural_context=", ".join(_ctx.get("cultural_context", [])),
            keywords_list=kw_list,
        )
        response = kw2_ai_call(prompt, system=V2_VALIDATE_SYSTEM, provider=provider)
        results = kw2_extract_json(response) if response else None

        validated, rejected = list(cached_validated), []

        if isinstance(results, list):
            result_map = {}
            for r in results:
                if isinstance(r, dict) and "keyword" in r:
                    result_map[r["keyword"].lower().strip()] = r

            for kw in uncached:
                match = result_map.get(kw["keyword"].lower().strip())
                if match:
                    kw["ai_relevance"] = float(match.get("relevance", 0.5))
                    kw["intent"] = _normalize_intent(match.get("intent", kw.get("intent", "")))
                    kw["buyer_readiness"] = float(match.get("buyer_readiness", 0.0))
                else:
                    # AI didn't return this keyword — accept with neutral score
                    kw["ai_relevance"] = 0.5
                    if kw.get("intent"):
                        kw["intent"] = _normalize_intent(kw["intent"])

                # Cache result
                cache_key = hashlib.md5(
                    f"{kw['keyword']}|{universe}".encode()
                ).hexdigest()
                _validation_cache[cache_key] = {
                    "relevance": kw["ai_relevance"],
                    "intent": kw.get("intent", ""),
                    "buyer_readiness": kw.get("buyer_readiness", 0.0),
                }

                # Accept threshold: relevance >= 0.3 (much lower than old 0.7 — we keep informational)
                if kw["ai_relevance"] >= 0.3:
                    validated.append(kw)
                else:
                    kw["reject_reason"] = f"low_relevance:{kw['ai_relevance']:.2f}"
                    rejected.append(kw)
        else:
            # AI failed — accept all with neutral scores
            log.warning("AI validation returned non-JSON, accepting batch with neutral scores")
            for kw in uncached:
                kw["ai_relevance"] = 0.5
                validated.append(kw)

        return validated, rejected

    # ── Pre-clustering ───────────────────────────────────────────────────

    def _pre_cluster(self, keywords: list[dict],
                     ai_provider: str) -> list[dict]:
        """Quick embedding-based clustering for review UI."""
        if not keywords:
            return []

        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
        except ImportError:
            log.warning("sentence-transformers not available — skip clustering")
            return self._fallback_cluster(keywords)

        texts = [kw.get("keyword", "") for kw in keywords]
        model = SentenceTransformer(EMBEDDING_MODEL)
        embeddings = model.encode(texts, show_progress_bar=False)

        # Group by primary pillar first, then cluster within each pillar
        pillar_groups: dict[str, list[int]] = defaultdict(list)
        for i, kw in enumerate(keywords):
            primary_pillar = kw.get("pillars", [""])[0] if kw.get("pillars") else ""
            pillar_groups[primary_pillar].append(i)

        all_clusters = []

        for pillar, indices in pillar_groups.items():
            if not indices:
                continue
            p_embeddings = np.array([embeddings[i] for i in indices])
            p_keywords = [keywords[i] for i in indices]

            # Sort by score descending
            scored = sorted(range(len(p_keywords)),
                            key=lambda x: float(p_keywords[x].get("ai_relevance", 0)),
                            reverse=True)

            clusters_local: list[dict] = []
            assigned = set()

            for idx in scored:
                if idx in assigned:
                    continue
                # Start new cluster
                cluster = {"indices": [idx], "centroid": p_embeddings[idx].copy()}
                assigned.add(idx)

                for other in scored:
                    if other in assigned:
                        continue
                    sim = _cosine_sim(cluster["centroid"], p_embeddings[other])
                    if sim >= CLUSTER_SIMILARITY_THRESHOLD:
                        cluster["indices"].append(other)
                        assigned.add(other)
                        # Update centroid
                        vecs = np.array([p_embeddings[i] for i in cluster["indices"]])
                        cluster["centroid"] = vecs.mean(axis=0)

                clusters_local.append(cluster)

            # Convert to output format — collect clusters without names yet
            for cl in clusters_local:
                cl_kws = [p_keywords[i] for i in cl["indices"]]
                cl_kws.sort(key=lambda k: float(k.get("ai_relevance", 0)), reverse=True)
                top_kw = cl_kws[0]["keyword"] if cl_kws else ""
                avg_score = sum(float(k.get("ai_relevance", 0)) for k in cl_kws) / len(cl_kws)

                all_clusters.append({
                    "cluster_id": db._uid("cl_"),
                    "name": top_kw,           # placeholder; batch-named below
                    "top_keyword": top_kw,
                    "avg_score": round(avg_score, 3),
                    "keyword_canonicals": [k["canonical"] for k in cl_kws],
                    "keyword_count": len(cl_kws),
                    "pillar": pillar,
                    "_sample_kws": [k["keyword"] for k in cl_kws[:5]],  # for naming
                })

        # Batch-name all clusters that need AI naming (instead of 1 call per cluster)
        to_name_idx = [
            i for i, cl in enumerate(all_clusters)
            if cl["keyword_count"] >= CLUSTER_NAME_MIN_SIZE
        ]
        if to_name_idx:
            # Process in batches of CLUSTER_NAME_BATCH_SIZE
            for batch_start in range(0, len(to_name_idx), CLUSTER_NAME_BATCH_SIZE):
                batch_idx = to_name_idx[batch_start:batch_start + CLUSTER_NAME_BATCH_SIZE]
                samples = [all_clusters[i]["_sample_kws"] for i in batch_idx]
                names = self._ai_name_clusters_batch(samples, ai_provider)
                for i, cl_idx in enumerate(batch_idx):
                    if i < len(names) and names[i]:
                        all_clusters[cl_idx]["name"] = names[i]

        # Remove internal helper field
        for cl in all_clusters:
            cl.pop("_sample_kws", None)

        return all_clusters

    def _fallback_cluster(self, keywords: list[dict]) -> list[dict]:
        """Simple pillar-based clustering when sentence-transformers unavailable."""
        pillar_groups: dict[str, list[dict]] = defaultdict(list)
        for kw in keywords:
            primary = kw.get("pillars", [""])[0] if kw.get("pillars") else "other"
            pillar_groups[primary].append(kw)

        clusters = []
        for pillar, kws in pillar_groups.items():
            kws.sort(key=lambda k: float(k.get("ai_relevance", 0)), reverse=True)
            clusters.append({
                "cluster_id": db._uid("cl_"),
                "name": pillar or "Uncategorized",
                "top_keyword": kws[0]["keyword"] if kws else "",
                "avg_score": sum(float(k.get("ai_relevance", 0)) for k in kws) / len(kws) if kws else 0,
                "keyword_canonicals": [k["canonical"] for k in kws],
                "keyword_count": len(kws),
                "pillar": pillar,
            })
        return clusters

    def _cluster_business_context(self) -> str:
        """Build short business context string for cluster naming prompts."""
        ctx = getattr(self, "_profile_ctx", {})
        if not ctx:
            return "Business"
        parts = [ctx.get("universe", "Business")]
        btype = ctx.get("business_type", "")
        if btype:
            parts[0] = f"{parts[0]} ({btype})"
        aud = ctx.get("audience", [])
        if aud:
            parts.append(f"Audience: {', '.join(str(a) for a in aud[:3])}")
        return " | ".join(parts)

    def _ai_name_cluster(self, keywords: list[str], provider: str) -> str:
        """AI-generate a 2-4 word cluster name (single call, legacy fallback)."""
        biz_ctx = self._cluster_business_context()
        prompt = CLUSTER_NAME_USER.format(
            keywords_list="\n".join(f"- {k}" for k in keywords),
            business_context=biz_ctx,
        )
        name = kw2_ai_call(prompt, system=CLUSTER_NAME_SYSTEM, provider=provider)
        if name:
            name = name.strip().strip('"').strip("'")
            if 1 <= len(name.split()) <= 6:
                return name
        return keywords[0] if keywords else "Cluster"

    def _ai_name_clusters_batch(self, samples_list: list[list[str]],
                                provider: str) -> list[str]:
        """Name multiple clusters in a single AI call.

        Args:
            samples_list: list of sample-keyword lists, one entry per cluster.
                Each inner list has up to 5 representative keywords.
        Returns:
            list of names (same length as samples_list); falls back to first
            keyword of each sample on parse failure.
        """
        if not samples_list:
            return []

        # Build a numbered block so AI can match order
        lines = []
        for i, sample_kws in enumerate(samples_list, 1):
            kw_str = ", ".join(f'"{k}"' for k in sample_kws[:5])
            lines.append(f"Cluster {i}: {kw_str}")
        clusters_block = "\n".join(lines)

        prompt = BATCH_CLUSTER_NAME_USER.format(
            clusters_block=clusters_block,
            business_context=self._cluster_business_context(),
        )
        response = kw2_ai_call(prompt, system=BATCH_CLUSTER_NAME_SYSTEM, provider=provider)
        result = kw2_extract_json(response) if response else None

        names: list[str] = []
        if isinstance(result, dict) and isinstance(result.get("names"), list):
            for raw_name in result["names"]:
                n = str(raw_name).strip().strip('"').strip("'")
                names.append(n if 1 <= len(n.split()) <= 6 else "")

        # Pad / trim to match input length; fallback = first keyword of each sample
        out: list[str] = []
        for i, sample_kws in enumerate(samples_list):
            fallback = sample_kws[0] if sample_kws else "Cluster"
            name = names[i] if i < len(names) and names[i] else fallback
            out.append(name)
        return out

    # ── Review actions ───────────────────────────────────────────────────

    def approve_clusters(self, session_id: str, project_id: str,
                         approved_cluster_ids: list[str],
                         rejected_cluster_ids: list[str] | None = None) -> dict:
        """Process user's cluster review decisions."""
        keywords = db.load_keywords(session_id, status="candidate")

        approved_count = 0
        rejected_count = 0

        for kw in keywords:
            cid = kw.get("cluster_id", "")
            if cid in approved_cluster_ids:
                db.update_keyword(kw["id"], status="approved")
                approved_count += 1
            elif rejected_cluster_ids and cid in rejected_cluster_ids:
                db.update_keyword(kw["id"], status="rejected",
                                  reject_reason="user_rejected_cluster")
                rejected_count += 1

        db.set_phase_status(session_id, "expand", "done")
        db.update_session(session_id, validated_count=approved_count,
                          current_phase="organize")

        return {"approved": approved_count, "rejected": rejected_count}

    def move_keyword_pillar(self, keyword_id: str, new_pillars: list[str]) -> None:
        """Move a keyword to different pillars (user review action)."""
        db.update_keyword(keyword_id, pillars=new_pillars)

    def add_manual_keyword(self, session_id: str, project_id: str,
                           keyword_text: str, pillars: list[str]) -> dict:
        """Add a manually entered keyword (normalizes + assigns)."""
        canon = canonical(keyword_text)
        existing = db.get_keyword_by_canonical(session_id, canon)
        if existing:
            # Merge pillars
            current_pillars = existing.get("pillars", [])
            for p in pillars:
                if p not in current_pillars:
                    current_pillars.append(p)
            db.update_keyword(existing["id"], pillars=current_pillars)
            return existing

        role = assign_role(keyword_text, pillars, [
            {"pillar": p, "confidence": 0.9} for p in pillars
        ])
        kw_data = {
            "keyword": display_form(keyword_text),
            "canonical": canon,
            "pillars": pillars,
            "role": role,
            "intent": "",
            "sources": ["manual"],
            "variants": [display_form(keyword_text)],
            "ai_relevance": 0.8,
            "status": "candidate",
        }
        db.bulk_insert_keywords(session_id, project_id, [kw_data])
        return kw_data

    def get_review_data(self, session_id: str) -> dict:
        """Get cluster-organized keywords for the review UI."""
        keywords = db.load_keywords(session_id, status="candidate")
        profile = None
        if keywords:
            profile = db.load_business_profile(keywords[0].get("project_id", ""))

        pillars = []
        if profile:
            p = profile.get("pillars", [])
            pillars = json.loads(p) if isinstance(p, str) else p

        # Organize by pillar → cluster
        pillar_data = {}
        for p in pillars:
            p_kws = [k for k in keywords if p in k.get("pillars", [])]
            clusters_in_pillar: dict[str, list] = defaultdict(list)
            for kw in p_kws:
                cid = kw.get("cluster_id", "unclustered")
                clusters_in_pillar[cid].append(kw)

            pillar_data[p] = {
                "total": len(p_kws),
                "clusters": [
                    {
                        "cluster_id": cid,
                        "keywords": sorted(kws, key=lambda k: float(k.get("ai_relevance", 0)), reverse=True),
                        "count": len(kws),
                    }
                    for cid, kws in clusters_in_pillar.items()
                ],
            }

        # Get cluster names
        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT id, cluster_name, pillar FROM kw2_clusters WHERE session_id=?",
                (session_id,),
            ).fetchall()
            cluster_names = {r["id"]: r["cluster_name"] for r in rows}
        finally:
            conn.close()

        for p_name, p_info in pillar_data.items():
            for cl in p_info["clusters"]:
                cl["name"] = cluster_names.get(cl["cluster_id"], "Unclustered")

        return {
            "pillars": pillars,
            "pillar_data": pillar_data,
            "total_keywords": len(keywords),
            "cluster_names": cluster_names,
        }


# ── Helpers ──────────────────────────────────────────────────────────────

def _extract_core(pillar: str) -> str:
    """Extract core product noun from pillar name."""
    noise = re.compile(
        r"\b(\d+\s*(g|gm|kg|ml|l|mm|cm|oz|lb)s?\b|"
        r"free delivery|discount|offer|premium|organic|natural|"
        r"kerala|indian|india|pure|best|quality|"
        r"buy|shop|order|purchase|online|sell|get)\b",
        re.I,
    )
    result = noise.sub("", pillar).strip()
    result = re.sub(r"\s+", " ", result).strip()
    return result.lower() if len(result) >= 3 else pillar.lower()


def _cosine_sim(a, b) -> float:
    """Cosine similarity between two vectors."""
    import numpy as np
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm > 0 else 0.0


def _sse(event: str, data: dict) -> str:
    """Format an SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

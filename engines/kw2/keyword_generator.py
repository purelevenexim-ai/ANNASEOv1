"""
kw2 Phase 2 — Keyword Universe Generator.

5-layer generation pipeline:
  Layer 1: Seeds (pillar × modifier combos)
  Layer 2: Rule expand (transactional templates per seed)
  Layer 3: Google Suggest (autosuggest per pillar)
  Layer 4: Competitor crawl (keywords from competitor sites)
  Layer 5: AI expand (30 buyer-intent keywords per pillar)

Then: negative filter → normalize → dedup → bulk insert.
"""
import concurrent.futures
import json
import logging
import re

from collections import defaultdict
from engines.kw2.constants import (
    NEGATIVE_PATTERNS, TRANSACTIONAL_TEMPLATES, COMMERCIAL_TEMPLATES,
    LOCAL_TEMPLATES, GARBAGE_WORDS,
    AUDIENCE_TEMPLATES, PROBLEM_TEMPLATES, ATTRIBUTE_TEMPLATES,
    COMPARISON_TEMPLATES,
    COMMERCIAL_BOOSTS, RULE_SCORE_MODIFIER_PREMIUM, RULE_SCORE_MODIFIER_GENERIC,
    MAX_RULES_PER_PILLAR, SCORING_GATE_PER_PILLAR, PILLAR_TARGET_COUNT,
)
from engines.kw2.prompts import UNIVERSE_EXPAND_SYSTEM, UNIVERSE_EXPAND_USER
from engines.kw2.ai_caller import kw2_ai_call
from engines.kw2 import db

log = logging.getLogger("kw2.generator")

MIN_LITERAL_ANCHORS_PER_PILLAR = 3


class KeywordUniverseGenerator:
    """Phase 2: Generate a keyword universe from business profile data."""

    def generate(
        self,
        project_id: str,
        session_id: str,
        competitor_urls: list[str] | None = None,
        ai_provider: str = "auto",
    ) -> dict:
        """
        Full synchronous generation — returns summary stats.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError(f"No business profile found for project {project_id}. Run Phase 1 first.")

        pillars = profile.get("pillars", [])
        modifiers = profile.get("modifiers", [])
        negative_scope = profile.get("negative_scope", [])
        universe = profile.get("universe", "")
        geo = profile.get("geo_scope", "")
        audience = profile.get("audience", [])

        # Load deep BI knowledge for context-aware generation
        biz_context = self._load_biz_context(session_id)

        # Store profile context for downstream prompt enrichment
        self._profile_ctx = profile
        self._biz_context = biz_context

        all_keywords = []
        stats = {"seeds": 0, "rules": 0, "suggest": 0, "competitor": 0, "ai_expand": 0,
                 "audience": 0, "attribute": 0, "problem": 0}

        # Layer 1: Seeds
        seeds = self._build_seeds(pillars, modifiers)
        all_keywords.extend(seeds)
        stats["seeds"] = len(seeds)

        # Layer 2: Rule expand
        rule_kws = self._rule_expand(pillars, modifiers, geo)
        all_keywords.extend(rule_kws)
        stats["rules"] = len(rule_kws)

        # Layer 2b: Audience expansion
        audience_kws = self._audience_expand(pillars, audience)
        all_keywords.extend(audience_kws)
        stats["audience"] = len(audience_kws)

        # Layer 2c: Attribute expansion (from BI product intelligence)
        attr_kws = self._attribute_expand(pillars, biz_context)
        all_keywords.extend(attr_kws)
        stats["attribute"] = len(attr_kws)

        # Layer 2d: Problem/trust-based keywords
        problem_kws = self._problem_expand(pillars)
        all_keywords.extend(problem_kws)
        stats["problem"] = len(problem_kws)

        # Layer 3: Google Suggest
        suggest_kws = self._google_suggest(pillars, modifiers)
        all_keywords.extend(suggest_kws)
        stats["suggest"] = len(suggest_kws)

        # Layer 4: Competitor (real-time crawl)
        if competitor_urls:
            comp_kws = self._competitor_keywords(competitor_urls, pillars)
            all_keywords.extend(comp_kws)
            stats["competitor"] = len(comp_kws)

        # Layer 4b: BI pre-analyzed competitor keywords
        bi_comp_kws = self._bi_competitor_keywords(session_id, pillars)
        all_keywords.extend(bi_comp_kws)
        stats["bi_competitor"] = len(bi_comp_kws)

        # Layer 4c: BI strategy priority keywords + goal-based seeds
        strategy_kws = self._bi_strategy_keywords(biz_context, pillars)
        all_keywords.extend(strategy_kws)
        stats["bi_strategy"] = len(strategy_kws)

        # Layer 5: AI expand
        ai_kws = self._ai_expand(pillars, modifiers, universe, ai_provider)
        all_keywords.extend(ai_kws)
        stats["ai_expand"] = len(ai_kws)

        anchor_kws = self._ensure_literal_pillar_anchors(all_keywords, pillars, modifiers)
        if anchor_kws:
            all_keywords.extend(anchor_kws)
            stats["anchor"] = len(anchor_kws)

        # Filter + dedup
        passed, rejected = self._negative_filter(all_keywords, negative_scope)
        unique = self._normalize_dedup(passed)

        # Bulk insert
        db.bulk_insert_universe(session_id, project_id, unique)

        # Also insert rejected items for audit trail
        for r in rejected:
            r["status"] = "rejected"
        db.bulk_insert_universe(session_id, project_id, rejected)

        # Update session
        db.update_session(session_id, phase2_done=1, universe_count=len(unique))

        result = {
            "session_id": session_id,
            "total": len(unique),
            "rejected": len(rejected),
            "sources": stats,
        }
        log.info(f"[Phase2] Generated {len(unique)} keywords ({len(rejected)} rejected) for {project_id}")
        return result

    def generate_stream(
        self,
        project_id: str,
        session_id: str,
        competitor_urls: list[str] | None = None,
        ai_provider: str = "auto",
    ):
        """
        SSE generator — yields progress events per layer.
        Checkpointed: each layer is saved to DB immediately.
        On reconnect, already-saved layers are skipped (fast replay).
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            yield f'data: {json.dumps({"type": "error", "msg": "No business profile. Run Phase 1 first."})}\n\n'
            return

        pillars = profile.get("pillars", [])
        modifiers = profile.get("modifiers", [])
        negative_scope = profile.get("negative_scope", [])
        universe = profile.get("universe", "")
        geo = profile.get("geo_scope", "")
        audience = profile.get("audience", [])

        # Load deep BI knowledge for context-aware generation
        biz_context = self._load_biz_context(session_id)

        # Store profile context for downstream prompt enrichment
        self._profile_ctx = profile
        self._biz_context = biz_context

        # ── Checkpoint: detect which layers already have data in DB ──────────
        existing_sources = db.get_universe_sources(session_id)

        # ── Running dedup: in-memory normalized set across all layers ────────────
        # Prevents cross-layer duplicates from ever reaching the database.
        self._seen_normalized: set[str] = set()
        if existing_sources:
            # On reconnect: rebuild _seen from all keywords already in the DB.
            for _item in db.load_universe_items(session_id):
                _norm = self._normalize(_item.get("keyword", ""))
                if _norm:
                    self._seen_normalized.add(_norm)
            log.info(f"[Phase2] Reconnect: rebuilt dedup set ({len(self._seen_normalized)} existing kws)")

        def _layer(source, generate_fn, *args, **kwargs):
            """Generate a layer only if not already checkpointed. Returns count."""
            if source in existing_sources:
                return existing_sources[source]  # already saved, skip
            kws = generate_fn(*args, **kwargs)
            kws = self._dedup_batch(kws)  # remove cross-layer duplicates before DB insert
            if kws:
                db.bulk_insert_universe(session_id, project_id, kws)
            return len(kws)

        # Layer 1: Seeds
        count = _layer("seeds", self._build_seeds, pillars, modifiers)
        yield f'data: {json.dumps({"type": "progress", "source": "seeds", "count": count, "cached": "seeds" in existing_sources})}\n\n'

        # Layer 2: Rules
        count = _layer("rules", self._rule_expand, pillars, modifiers, geo)
        yield f'data: {json.dumps({"type": "progress", "source": "rules", "count": count, "cached": "rules" in existing_sources})}\n\n'

        # Layer 2b: Audience expansion
        count = _layer("audience", self._audience_expand, pillars, audience)
        if count:
            yield f'data: {json.dumps({"type": "progress", "source": "audience", "count": count, "cached": "audience" in existing_sources})}\n\n'

        # Layer 2c: Attribute expansion
        count = _layer("attribute", self._attribute_expand, pillars, biz_context)
        if count:
            yield f'data: {json.dumps({"type": "progress", "source": "attribute", "count": count, "cached": "attribute" in existing_sources})}\n\n'

        # Layer 2d: Problem/trust keywords
        count = _layer("problem", self._problem_expand, pillars)
        if count:
            yield f'data: {json.dumps({"type": "progress", "source": "problem", "count": count, "cached": "problem" in existing_sources})}\n\n'

        # ── Scoring Gate: trim to top SCORING_GATE_PER_PILLAR per pillar ────────────
        # Runs only when at least one template layer generated fresh keywords.
        # Keeps only the highest-scoring keywords per pillar so real-data layers
        # (Suggest, BI, AI) fill the most valuable remaining slots.
        if any(s not in existing_sources for s in ("seeds", "rules", "audience", "attribute", "problem")):
            _gate_kept, _gate_trimmed = self._scoring_gate(session_id, pillars)
            yield f'data: {json.dumps({"type": "scoring_gate", "kept": _gate_kept, "trimmed": _gate_trimmed})}\n\n'
            log.info(f"[Phase2] Scoring gate: kept {_gate_kept}, trimmed {_gate_trimmed}")

        # Layer 3: Google Suggest — parallel (4 pillars at once, 10s each)
        _sg_pending = [p for p in pillars if f"suggest_{p}" not in existing_sources]
        for p in pillars:  # yield cached results immediately
            if f"suggest_{p}" in existing_sources:
                yield f'data: {json.dumps({"type": "progress", "source": "suggest", "pillar": p, "count": existing_sources[f"suggest_{p}"], "cached": True})}\n\n'
        if _sg_pending:
            _sg_results: dict[str, list] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as _sg_pool:
                _sg_futs = {
                    _sg_pool.submit(self._google_suggest, [p], modifiers): p
                    for p in _sg_pending
                }
                for _fut in concurrent.futures.as_completed(_sg_futs, timeout=90):
                    _sg_pillar = _sg_futs[_fut]
                    try:
                        _sg_results[_sg_pillar] = _fut.result(timeout=15)
                    except Exception:
                        _sg_results[_sg_pillar] = []
            for p in _sg_pending:
                sg_kws = self._dedup_batch(_sg_results.get(p, []))
                if sg_kws:
                    db.bulk_insert_universe(session_id, project_id, sg_kws)
                yield f'data: {json.dumps({"type": "progress", "source": "suggest", "pillar": p, "count": len(sg_kws)})}\n\n'

        # Layer 4: Competitor (one event per URL)
        if competitor_urls:
            for url in competitor_urls[:4]:
                comp_kws = self._dedup_batch(self._competitor_keywords([url], pillars))
                if comp_kws:
                    db.bulk_insert_universe(session_id, project_id, comp_kws)
                yield f'data: {json.dumps({"type": "progress", "source": "competitor", "url": url, "count": len(comp_kws)})}\n\n'

        # Layer 4b: BI pre-analyzed competitor keywords
        bi_comp_kws = self._dedup_batch(self._bi_competitor_keywords(session_id, pillars))
        if bi_comp_kws:
            db.bulk_insert_universe(session_id, project_id, bi_comp_kws)
            yield f'data: {json.dumps({"type": "progress", "source": "bi_competitor", "count": len(bi_comp_kws)})}\n\n'

        # Layer 4c: BI strategy priority keywords + goal-based seeds
        strategy_kws = self._dedup_batch(self._bi_strategy_keywords(biz_context, pillars))
        if strategy_kws:
            db.bulk_insert_universe(session_id, project_id, strategy_kws)
            yield f'data: {json.dumps({"type": "progress", "source": "bi_strategy", "count": len(strategy_kws)})}\n\n'

        # Layer 3b: Enrich modifiers from collected Suggest keywords
        # Pull all suggest keywords saved so far, scan for intent/quality/geo/audience signals
        # and merge into effective_modifiers used by AI expand + later rule layers.
        try:
            from engines.kw2.modifier_extractor import ModifierExtractor
            _suggest_kws_for_mods = db.load_universe_items(session_id, status="raw", source_filter="suggest")
            _suggest_texts = [item.get("keyword", "") for item in _suggest_kws_for_mods if item.get("keyword")]
            if _suggest_texts:
                _me = ModifierExtractor()
                _enriched = _me.to_flat_list(_me.extract(_suggest_texts))
                if _enriched:
                    modifiers = _me.merge_with_profile(_enriched, modifiers)
                    log.info(f"[Phase2] Enriched modifiers from suggest ({len(_suggest_texts)} kws): {modifiers[:8]}")
        except Exception as _e:
            log.warning(f"[Phase2] Modifier enrichment failed (non-fatal): {_e}")

        # Layer 5: AI expand — smart fill-to-target (skip pillars already at PILLAR_TARGET_COUNT)
        # Count per-pillar density of raw (non-trimmed) keywords to decide fill need.
        _all_post_gate = db.load_universe_items(session_id, status="raw")
        _pillar_kw_counts: dict[str, int] = defaultdict(int)
        _pillar_top_kws: dict[str, list[str]] = defaultdict(list)
        for _item in _all_post_gate:
            _p = _item.get("pillar", "")
            _pillar_kw_counts[_p] += 1
            if len(_pillar_top_kws[_p]) < 10:
                _pillar_top_kws[_p].append(_item.get("keyword", ""))

        pending_pillars = []
        for pillar in pillars:
            src_key = f"ai_{pillar}"
            if src_key in existing_sources:
                count = existing_sources[src_key]
                yield f'data: {json.dumps({"type": "progress", "source": "ai_expand", "pillar": pillar, "count": count, "cached": True})}\n\n'
            elif _pillar_kw_counts[pillar] >= PILLAR_TARGET_COUNT:
                log.info(f"[Phase2] AI skip '{pillar[:30]}' \u2014 already {_pillar_kw_counts[pillar]} kws")
                yield f'data: {json.dumps({"type": "progress", "source": "ai_expand", "pillar": pillar, "count": 0, "skipped": True})}\n\n'
            else:
                pending_pillars.append(pillar)

        if pending_pillars:
            _ai_results: dict[str, list] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as _pool:
                _fut_map = {
                    _pool.submit(
                        self._ai_expand, [p], modifiers, universe, ai_provider,
                        max(20, min(60, PILLAR_TARGET_COUNT - _pillar_kw_counts[p])),
                        _pillar_top_kws[p],
                    ): p
                    for p in pending_pillars
                }
                for _fut in concurrent.futures.as_completed(_fut_map, timeout=25):
                    _pillar = _fut_map[_fut]
                    try:
                        _kws = _fut.result(timeout=18)
                    except concurrent.futures.TimeoutError:
                        _kws = []
                        log.warning(f"AI expand timed out for pillar {_pillar}")
                    except Exception as _e:
                        _kws = []
                        log.warning(f"AI expand failed for pillar {_pillar}: {_e}")
                    _ai_results[_pillar] = _kws

            # Dedup + insert + stream in original pillar order
            for pillar in pending_pillars:
                ai_kws = self._dedup_batch(_ai_results.get(pillar, []))
                if ai_kws:
                    db.bulk_insert_universe(session_id, project_id, ai_kws)
                yield f'data: {json.dumps({"type": "progress", "source": "ai_expand", "pillar": pillar, "count": len(ai_kws)})}\n\n'

        _all_pre_filter = db.load_universe_items(session_id, status="raw")
        _anchor_kws = self._dedup_batch(
            self._ensure_literal_pillar_anchors(_all_pre_filter, pillars, modifiers)
        )
        if _anchor_kws:
            db.bulk_insert_universe(session_id, project_id, _anchor_kws)
            yield f'data: {json.dumps({"type": "progress", "source": "anchor", "count": len(_anchor_kws)})}\n\n'

        # Final: load ALL raw items from DB, filter + dedup, update statuses
        all_raw = db.load_universe_items(session_id, status="raw")
        passed, rejected = self._negative_filter(all_raw, negative_scope)
        unique = self._normalize_dedup(passed)

        rejected_ids = [r["id"] for r in rejected if r.get("id")]
        if rejected_ids:
            db.update_universe_status(rejected_ids, "rejected")

        db.update_session(session_id, phase2_done=1, universe_count=len(unique))

        yield f'data: {json.dumps({"type": "complete", "total": len(unique), "rejected": len(rejected)})}\n\n'

    # ── Layer generators ─────────────────────────────────────────────────

    def _build_seeds(self, pillars: list[str], modifiers: list[str]) -> list[dict]:
        """Layer 1: pillar × modifier combos. Also seeds the core (cleaned) term for product pillars."""
        seeds = []
        for p in pillars:
            seeds.append({"keyword": p, "source": "seeds", "pillar": p, "raw_score": 80.0})
            core = self._extract_core_term(p)
            if core.lower() != p.lower():
                seeds.append({"keyword": core, "source": "seeds", "pillar": p, "raw_score": 78.0})
            for m in modifiers:
                seeds.append({"keyword": f"{m} {p}", "source": "seeds", "pillar": p, "raw_score": 70.0})
                seeds.append({"keyword": f"{p} {m}", "source": "seeds", "pillar": p, "raw_score": 70.0})
                if core.lower() != p.lower():
                    seeds.append({"keyword": f"{m} {core}", "source": "seeds", "pillar": p, "raw_score": 68.0})
                    seeds.append({"keyword": f"{core} {m}", "source": "seeds", "pillar": p, "raw_score": 68.0})
        return seeds

    def _rule_expand(self, pillars: list[str], modifiers: list[str], geo: str) -> list[dict]:
        """Layer 2: apply transactional/commercial/local templates using both full name and core term.
        Also crosses modifiers with templates for richer keyword combos."""
        results = []
        for p in pillars:
            core = self._extract_core_term(p)
            # Generate templates for both full pillar name and core term (dedup happens later)
            search_terms = [p] if core.lower() == p.lower() else [p, core]
            for term in search_terms:
                for tmpl in TRANSACTIONAL_TEMPLATES:
                    kw = tmpl.replace("{k}", term)
                    results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 65.0})

            for tmpl in COMMERCIAL_TEMPLATES:
                if "{alt}" in tmpl:
                    for other in pillars:
                        if other != p:
                            other_core = self._extract_core_term(other)
                            kw = tmpl.replace("{k}", core).replace("{alt}", other_core)
                            results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 55.0})
                else:
                    kw = tmpl.replace("{k}", core)
                    results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 60.0})

            locations = [geo] if geo else []
            for loc in locations:
                for tmpl in LOCAL_TEMPLATES:
                    kw = tmpl.replace("{k}", core).replace("{loc}", loc)
                    results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 55.0})

            # Modifier × pillar crossover: apply templates with modifier+pillar combos
            for m in modifiers[:15]:
                m_lower = m.strip().lower()
                if not m_lower:
                    continue
                for term in search_terms:
                    combo = f"{m_lower} {term}"
                    for tmpl in TRANSACTIONAL_TEMPLATES[:6]:
                        kw = tmpl.replace("{k}", combo)
                        results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 58.0})
                    for tmpl in COMMERCIAL_TEMPLATES[:4]:
                        if "{alt}" not in tmpl:
                            kw = tmpl.replace("{k}", combo)
                            results.append({"keyword": kw, "source": "rules", "pillar": p, "raw_score": 55.0})

        # ── Score-and-trim: keep only the best per pillar ────────────────
        return self._score_trim_rules(results)

    def _score_trim_rules(self, rules: list[dict]) -> list[dict]:
        """Score every rule keyword with multi-signal heuristic; keep top N per pillar.

        Scoring signals (higher = better):
          1. Commercial intent (0-35): COMMERCIAL_BOOSTS token matching
          2. Modifier quality (0-20): premium modifiers score higher
          3. Word count (0-20): 3-5 words sweet spot for search volume
          4. Template type (0-10): derived from raw_score tier
          5. Diversity penalty (-8): if 2-word prefix already selected

        This ensures high-intent transactional keywords always survive
        while eliminating weak/redundant template expansions.
        """
        cap = MAX_RULES_PER_PILLAR  # default 50

        for kw_dict in rules:
            kw_lower = kw_dict["keyword"].lower()
            words = kw_lower.split()

            # 1. Commercial intent signal (0-35)
            commercial = 0
            for token, boost in COMMERCIAL_BOOSTS.items():
                if token in kw_lower:
                    commercial = max(commercial, boost)

            # 2. Modifier quality signal (0-20)
            mod_score = 0
            for token, pts in RULE_SCORE_MODIFIER_PREMIUM.items():
                if token in kw_lower:
                    mod_score = max(mod_score, pts)
            if mod_score == 0:
                for token, pts in RULE_SCORE_MODIFIER_GENERIC.items():
                    if token in kw_lower:
                        mod_score = max(mod_score, pts)

            # 3. Word count score (0-20): 3-5 words = 20, 2 or 6 = 12, else 5
            wc = len(words)
            wc_score = 20 if 3 <= wc <= 5 else (12 if wc in (2, 6) else 5)

            # 4. Template type bonus (0-10) based on raw_score tier
            rs = kw_dict.get("raw_score", 55)
            tmpl_score = 10 if rs >= 65 else (7 if rs >= 60 else (6 if rs >= 58 else 5))

            kw_dict["_rule_score"] = commercial + mod_score + wc_score + tmpl_score

        # Group by pillar, sort by score, apply diversity penalty, keep top N
        by_pillar: dict[str, list[dict]] = defaultdict(list)
        for kw_dict in rules:
            by_pillar[kw_dict.get("pillar", "")].append(kw_dict)

        trimmed = []
        for pillar, kws in by_pillar.items():
            kws.sort(key=lambda x: x.get("_rule_score", 0), reverse=True)

            selected: list[dict] = []
            seen_prefixes: set[str] = set()
            for kw_dict in kws:
                if len(selected) >= cap:
                    break
                # Diversity: penalize if 2-word prefix already in selected set
                words = kw_dict["keyword"].lower().split()
                prefix = " ".join(words[:2]) if len(words) >= 2 else words[0] if words else ""
                effective_score = kw_dict["_rule_score"]
                if prefix in seen_prefixes:
                    effective_score -= 8
                # Still accept if score is reasonable even after penalty
                # (we just re-sort by effective score below)
                kw_dict["_effective_score"] = effective_score
                selected.append(kw_dict)
                seen_prefixes.add(prefix)

            # Re-sort selected by effective score and keep top cap
            selected.sort(key=lambda x: x.get("_effective_score", 0), reverse=True)
            for kw_dict in selected[:cap]:
                kw_dict.pop("_rule_score", None)
                kw_dict.pop("_effective_score", None)
                trimmed.append(kw_dict)

        before = len(rules)
        after = len(trimmed)
        if before > after:
            log.info(f"[Phase2] Rule scoring: {before} generated → {after} kept "
                     f"(top {cap}/pillar, {len(by_pillar)} pillars)")
        return trimmed

    def _google_suggest(self, pillars: list[str], modifiers: list[str] | None = None) -> list[dict]:
        """Layer 3: Google Autosuggest using CLEAN core terms only (not full product names).
        Each pillar gets a 10s hard timeout to prevent thread exhaustion."""
        try:
            from engines.intelligent_crawl_engine import GoogleSuggestEnricher
            enricher = GoogleSuggestEnricher()
            results = []
            for p in pillars:
                # Always query the core term — never the full product name with weights/sizes
                core = self._extract_core_term(p)
                if not core or len(core) < 3:
                    continue
                # Deduplicate: if core == pillar (already clean), query once
                queries = [core] if core.lower() == p.lower() else [core]

                for q in queries:
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                            _fut = _ex.submit(enricher.enrich, [q])
                            scored = _fut.result(timeout=10)
                        for sk in scored:
                            kw = getattr(sk, "keyword", str(sk))
                            pillar = self._detect_pillar(kw, pillars)
                            results.append({"keyword": kw, "source": "suggest", "pillar": pillar, "raw_score": 60.0})
                    except concurrent.futures.TimeoutError:
                        log.warning(f"[GSuggest] 10s timeout for '{q}' — skipping")
                    except Exception:
                        pass
            return results
        except Exception as e:
            log.warning(f"Google Suggest failed: {e}")
            return []

    def _competitor_keywords(self, urls: list[str], pillars: list[str]) -> list[dict]:
        """Layer 4: keywords from competitor site crawl."""
        try:
            from engines.intelligent_crawl_engine import SmartCompetitorAnalyzer
            analyzer = SmartCompetitorAnalyzer()
            results = []
            for url in urls[:4]:
                try:
                    scored = analyzer.analyze_competitor(url, pillars, max_pages=15)
                    for sk in scored:
                        kw = getattr(sk, "keyword", str(sk))
                        pillar = self._detect_pillar(kw, pillars)
                        results.append({"keyword": kw, "source": "competitor", "pillar": pillar, "raw_score": 55.0})
                except Exception as e:
                    log.warning(f"Competitor crawl failed for {url}: {e}")
            return results
        except ImportError:
            log.warning("SmartCompetitorAnalyzer not available")
            return []

    def _bi_competitor_keywords(self, session_id: str, pillars: list[str]) -> list[dict]:
        """Layer 4b: pre-analyzed competitor keywords from Business Intelligence stage."""
        try:
            comp_kws = db.get_biz_competitor_keywords(session_id)
            results = []
            for row in comp_kws:
                kw = row.get("keyword", "").strip()
                if not kw:
                    continue
                pillar = self._detect_pillar(kw, pillars)
                # Map BI intent to raw score
                intent = row.get("intent", "commercial")
                score = 70.0 if intent == "transactional" else 60.0 if intent == "commercial" else 45.0
                results.append({
                    "keyword": kw,
                    "source": "bi_competitor",
                    "pillar": pillar,
                    "raw_score": score * float(row.get("confidence", 0.7)),
                })
            log.info(f"Loaded {len(results)} BI competitor keywords for session {session_id}")
            return results
        except Exception as e:
            log.warning(f"Failed to load BI competitor keywords: {e}")
            return []

    def _bi_strategy_keywords(self, biz_context: dict, pillars: list[str]) -> list[dict]:
        """Layer 4c: Seed keywords from BI strategy priorities, goals, and USPs."""
        results = []
        strategy = biz_context.get("seo_strategy", {})

        # Priority keywords from BI strategy (high-value targets identified by AI analysis)
        for kw in strategy.get("priority_keywords", []):
            term = kw if isinstance(kw, str) else (kw.get("keyword", "") if isinstance(kw, dict) else "")
            term = term.strip()
            if term and len(term) > 3:
                pillar = self._detect_pillar(term, pillars)
                results.append({"keyword": term, "source": "bi_strategy", "pillar": pillar, "raw_score": 75.0})

        # Quick wins from BI strategy
        for kw in strategy.get("quick_wins", []):
            term = kw if isinstance(kw, str) else (kw.get("keyword", "") if isinstance(kw, dict) else "")
            term = term.strip()
            if term and len(term) > 3:
                pillar = self._detect_pillar(term, pillars)
                results.append({"keyword": term, "source": "bi_strategy", "pillar": pillar, "raw_score": 72.0})

        # USP-driven keyword combos (e.g., "organic" + pillar)
        usps = biz_context.get("usps", [])
        for usp in usps[:5]:
            usp_clean = str(usp).strip().lower()
            if not usp_clean or len(usp_clean) > 40:
                continue
            for p in pillars[:6]:
                core = self._extract_core_term(p)
                results.append({"keyword": f"{usp_clean} {core}", "source": "bi_strategy", "pillar": p, "raw_score": 62.0})

        # Goal-based seeds (e.g., "buy clove online" if goal is "online sales")
        goals = biz_context.get("goals", [])
        _goal_intents = {
            "sales": ["buy", "order", "shop"],
            "leads": ["get quote", "enquiry", "contact"],
            "brand": ["best", "top rated", "trusted"],
            "export": ["export", "wholesale", "bulk"],
        }
        for goal in goals[:3]:
            goal_lower = str(goal).lower()
            for trigger, prefixes in _goal_intents.items():
                if trigger in goal_lower:
                    for prefix in prefixes:
                        for p in pillars[:4]:
                            core = self._extract_core_term(p)
                            results.append({"keyword": f"{prefix} {core}", "source": "bi_strategy", "pillar": p, "raw_score": 60.0})

        log.info(f"[Phase2] BI strategy seeded {len(results)} keywords")
        return results

    def _audience_expand(self, pillars: list[str], audience: list[str]) -> list[dict]:
        """Layer 2b: Audience-based keyword expansion — pillar × audience segment combos."""
        if not audience:
            return []
        results = []
        for p in pillars:
            core = self._extract_core_term(p)
            for a in audience[:4]:
                a_clean = a.strip().lower()
                if not a_clean:
                    continue
                for tmpl in AUDIENCE_TEMPLATES:
                    kw = tmpl.replace("{k}", core).replace("{a}", a_clean)
                    results.append({"keyword": kw, "source": "audience", "pillar": p, "raw_score": 58.0})
        return results

    def _attribute_expand(self, pillars: list[str], biz_context: dict) -> list[dict]:
        """Layer 2c: Attribute-based expansion using BI product intelligence.
        Uses product attributes (grade, origin, format, packaging) from deep analysis."""
        if not isinstance(biz_context, dict):
            return []
        pi = biz_context.get("product_intelligence", {})
        attrs = pi.get("product_attributes", [])
        quality_markers = pi.get("quality_markers", [])
        comparison_angles = pi.get("product_comparison_angles", [])

        if not attrs and not quality_markers and not comparison_angles:
            return []

        # Terms that describe business roles or commercial channels — NOT product attributes.
        # Using these as {attr} in ATTRIBUTE_TEMPLATES creates garbage like "buy supplier spices".
        _COMMERCIAL_ROLE_TERMS = frozenset({
            "supplier", "suppliers", "manufacturer", "manufacturers", "distributor",
            "distributors", "exporter", "exporters", "wholesaler", "wholesalers",
            "retailer", "retailers", "dealer", "dealers", "vendor", "vendors",
            "bulk", "wholesale", "export", "import",
            "first", "original", "real", "genuine", "true", "actual",
            "standard", "normal", "common", "regular", "general", "basic",
        })

        def _is_valid_attribute(val: str) -> bool:
            """Return True only if val is a genuine product attribute (grade, format, origin, type)."""
            v = val.strip().lower()
            # Too short or too long
            if len(v) < 2 or len(v) > 40:
                return False
            # Ignore pure commercial role terms
            if v in _COMMERCIAL_ROLE_TERMS:
                return False
            # Ignore if first word is a commercial role term (e.g. "bulk supplier")
            first_word = v.split()[0]
            if first_word in _COMMERCIAL_ROLE_TERMS:
                return False
            return True

        results = []
        # Attribute × pillar — filtered
        attr_values = []
        for attr in attrs:
            if isinstance(attr, dict):
                val = attr.get("value", "").strip()
                if val and _is_valid_attribute(val):
                    attr_values.append(val.lower())
            elif isinstance(attr, str):
                val = attr.strip()
                if val and _is_valid_attribute(val):
                    attr_values.append(val.lower())

        for p in pillars:
            core = self._extract_core_term(p)
            for attr_val in attr_values[:5]:
                for tmpl in ATTRIBUTE_TEMPLATES:
                    kw = tmpl.replace("{k}", core).replace("{attr}", attr_val)
                    results.append({"keyword": kw, "source": "attribute", "pillar": p, "raw_score": 62.0})

            # Quality markers as modifiers — filter same way
            for qm in quality_markers[:4]:
                qm_clean = qm.strip().lower()
                if qm_clean and _is_valid_attribute(qm_clean):
                    results.append({"keyword": f"{qm_clean} {core}", "source": "attribute", "pillar": p, "raw_score": 60.0})
                    results.append({"keyword": f"buy {qm_clean} {core}", "source": "attribute", "pillar": p, "raw_score": 63.0})

            # Comparison angles
            for angle in comparison_angles[:3]:
                angle_clean = angle.strip().lower()
                if angle_clean:
                    for tmpl in COMPARISON_TEMPLATES:
                        # Try to split "X vs Y" style angles
                        parts = re.split(r'\s+vs\s+|\s+or\s+', angle_clean, maxsplit=1)
                        if len(parts) == 2:
                            kw = tmpl.replace("{k}", parts[0].strip()).replace("{alt}", parts[1].strip())
                        else:
                            kw = tmpl.replace("{k}", core).replace("{alt}", angle_clean)
                        results.append({"keyword": kw, "source": "attribute", "pillar": p, "raw_score": 57.0})

        return results

    def _problem_expand(self, pillars: list[str]) -> list[dict]:
        """Layer 2d: Problem/trust-based keyword expansion — targets buyer pain points."""
        results = []
        for p in pillars:
            core = self._extract_core_term(p)
            for tmpl in PROBLEM_TEMPLATES:
                kw = tmpl.replace("{k}", core)
                results.append({"keyword": kw, "source": "problem", "pillar": p, "raw_score": 56.0})
        return results

    def _load_biz_context(self, session_id: str) -> dict:
        """Load deep BI knowledge synthesis + strategy data for context-aware keyword generation."""
        context = {}
        try:
            biz_intel = db.get_biz_intel(session_id) or {}

            # 1. Product intelligence (existing)
            knowledge_str = biz_intel.get("knowledge_summary", "")
            if knowledge_str:
                parsed = json.loads(knowledge_str)
                if isinstance(parsed, dict):
                    context = parsed

            # 2. SEO Strategy — priority keywords, content recommendations
            seo_str = biz_intel.get("seo_strategy", "")
            if seo_str:
                try:
                    strategy = json.loads(seo_str)
                    if isinstance(strategy, dict):
                        context["seo_strategy"] = strategy
                except Exception:
                    pass

            # 3. Goals, USPs, audience segments from BI profile
            for field in ("goals", "usps", "audience_segments"):
                val = biz_intel.get(field)
                if val:
                    context[field] = val if isinstance(val, list) else [val]

            # 4. Business README from session
            session = db.get_session(session_id) or {}
            readme = session.get("business_readme", "")
            if readme:
                context["business_readme"] = readme[:2000]

        except Exception as e:
            log.warning(f"Failed to load BI context for session {session_id}: {e}")
        return context

    def _ai_expand(
        self,
        pillars: list[str],
        modifiers: list[str],
        universe: str,
        provider: str,
        target_count: int = 40,
        existing_keywords: list[str] | None = None,
    ) -> list[dict]:
        """Layer 5: AI-generated buyer-intent keywords (target_count per pillar)."""
        results = []

        # Build extra context from BI data (if available)
        _biz_ctx = getattr(self, "_biz_context", {}) or {}
        _extra_lines = []
        if _biz_ctx.get("business_readme"):
            _extra_lines.append(f"Business overview: {_biz_ctx['business_readme'][:500]}")
        if _biz_ctx.get("goals"):
            _extra_lines.append(f"Business goals: {', '.join(str(g) for g in _biz_ctx['goals'][:5])}")
        if _biz_ctx.get("usps"):
            _extra_lines.append(f"Unique selling points: {', '.join(str(u) for u in _biz_ctx['usps'][:5])}")
        _strategy = _biz_ctx.get("seo_strategy", {})
        if _strategy.get("priority_keywords"):
            _prio = _strategy["priority_keywords"][:10]
            _prio_str = ", ".join(k if isinstance(k, str) else k.get("keyword", "") for k in _prio)
            _extra_lines.append(f"Priority keywords from analysis: {_prio_str}")
        _extra_ctx = "\n".join(_extra_lines)

        # Build "already have" note to prevent AI duplicating existing keywords
        _existing_note = ""
        if existing_keywords:
            _existing_note = f"Already have these — do NOT repeat: {', '.join(existing_keywords[:10])}"

        for pillar in pillars:
            try:
                core_term = self._extract_core_term(pillar)
                prompt = UNIVERSE_EXPAND_USER.format(
                    universe=universe, pillar=pillar,
                    core_term=core_term,
                    modifiers=", ".join(modifiers[:10]),
                    target_locations=", ".join(self._profile_ctx.get("target_locations", [])),
                    business_locations=", ".join(self._profile_ctx.get("business_locations", [])),
                    languages=", ".join(self._profile_ctx.get("languages", [])),
                    cultural_context=", ".join(self._profile_ctx.get("cultural_context", [])),
                    usp=self._profile_ctx.get("usp", ""),
                    customer_voice=self._profile_ctx.get("customer_reviews", "")[:300],
                    target_count=target_count,
                    existing_kws_note=_existing_note,
                )
                if _extra_ctx:
                    prompt = prompt.rstrip() + "\n\n" + _extra_ctx + "\n"
                response = kw2_ai_call(prompt, UNIVERSE_EXPAND_SYSTEM, provider=provider)
                if not response:
                    continue
                lines = [l.strip() for l in response.strip().split("\n") if l.strip()]
                for line in lines[:target_count]:
                    # Clean numbering/bullets
                    clean = re.sub(r'^[\d\.\-\*\)\]]+\s*', '', line).strip()
                    if clean and len(clean) > 3:
                        results.append({"keyword": clean, "source": "ai_expand", "pillar": pillar, "raw_score": 50.0})
            except Exception as e:
                log.warning(f"AI expand failed for pillar {pillar}: {e}")
        return results

    # ── Filters ──────────────────────────────────────────────────────────

    def _negative_filter(self, keywords: list[dict], negative_scope: list[str]) -> tuple[list[dict], list[dict]]:
        """Hard-reject keywords matching negative patterns."""
        neg_patterns = set(p.lower() for p in (negative_scope or []))
        neg_patterns.update(p.lower() for p in NEGATIVE_PATTERNS)

        passed = []
        rejected = []
        for kw_dict in keywords:
            kw_lower = kw_dict["keyword"].lower()
            hit = False
            for neg in neg_patterns:
                if neg in kw_lower:
                    kw_dict["reject_reason"] = f"negative_pattern:{neg}"
                    rejected.append(kw_dict)
                    hit = True
                    break
            if not hit:
                passed.append(kw_dict)
        return passed, rejected

    def _normalize_dedup(self, keywords: list[dict]) -> list[dict]:
        """Normalize text + exact-match dedup. Keeps first occurrence (highest raw_score first)."""
        # Sort by score desc so dedup keeps highest
        keywords.sort(key=lambda x: x.get("raw_score", 0), reverse=True)

        seen = set()
        unique = []
        for kw_dict in keywords:
            normalized = self._normalize(kw_dict["keyword"])
            if not normalized or len(normalized) < 4:
                continue
            if normalized not in seen:
                seen.add(normalized)
                kw_dict["keyword"] = normalized
                # Normalize pillar casing to Title Case
                if kw_dict.get("pillar"):
                    kw_dict["pillar"] = kw_dict["pillar"].strip().title()
                unique.append(kw_dict)
        return unique

    def _normalize(self, text: str) -> str:
        """Lowercase, strip, collapse whitespace, remove non-alphanumeric except spaces."""
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _dedup_batch(self, keywords: list[dict]) -> list[dict]:
        """Filter a keyword batch against self._seen_normalized.

        Intended to be called before every bulk_insert_universe() call so that
        cross-layer duplicates are eliminated before they hit the database.
        Newly seen normalized forms are added to _seen_normalized in-place.
        Safe if _seen_normalized has not been initialized (returns all keywords).
        """
        seen = getattr(self, "_seen_normalized", None)
        if seen is None:
            return keywords
        result = []
        for kw_dict in keywords:
            norm = self._normalize(kw_dict.get("keyword", ""))
            if norm and len(norm) >= 4 and norm not in seen:
                seen.add(norm)
                result.append(kw_dict)
        return result

    def _scoring_gate(self, session_id: str, pillars: list[str]) -> tuple[int, int]:
        """Load all raw keywords and trim to top SCORING_GATE_PER_PILLAR per pillar.

        Scoring signals (additive, higher = better):
          - Commercial intent (0-35): COMMERCIAL_BOOSTS token matching
          - Word count       (0-20): 3-5 words optimal for search volume
          - Source priority  (0-15): seeds/bi_strategy > rules > audience/attribute > problem
          - Raw score bonus  (0-15): contribution from the per-layer static raw_score field

        Excess keywords are marked status='trimmed' in DB — excluded from all
        subsequent phases but kept for auditing.
        Returns (kept_count, trimmed_count).
        """
        _source_priority = {
            "anchor": 1.0,
            "seeds": 1.0, "bi_strategy": 0.95, "bi_competitor": 0.90,
            "rules": 0.85, "attribute": 0.80, "audience": 0.75, "problem": 0.70,
        }
        all_raw = db.load_universe_items(session_id, status="raw")
        if not all_raw:
            return 0, 0
        for kw_dict in all_raw:
            kw_lower = kw_dict.get("keyword", "").lower()
            words = kw_lower.split()
            commercial = max(
                (boost for token, boost in COMMERCIAL_BOOSTS.items() if token in kw_lower),
                default=0,
            )
            wc = len(words)
            wc_score = 20 if 3 <= wc <= 5 else (12 if wc in (2, 6) else 5)
            sp = _source_priority.get(kw_dict.get("source", ""), 0.5) * 15
            rs_bonus = (kw_dict.get("raw_score", 55) - 50) * 0.5
            kw_dict["_gs"] = commercial + wc_score + sp + rs_bonus

        by_pillar: dict[str, list] = defaultdict(list)
        for kw_dict in all_raw:
            by_pillar[kw_dict.get("pillar", "")].append(kw_dict)

        kept_ids: list[str] = []
        trimmed_ids: list[str] = []
        for kws in by_pillar.values():
            kws.sort(key=lambda x: x.get("_gs", 0), reverse=True)
            for i, kw_dict in enumerate(kws):
                (kept_ids if i < SCORING_GATE_PER_PILLAR else trimmed_ids).append(kw_dict["id"])

        if trimmed_ids:
            db.update_universe_status(trimmed_ids, "trimmed")
        return len(kept_ids), len(trimmed_ids)

    def _ensure_literal_pillar_anchors(
        self,
        keywords: list[dict],
        pillars: list[str],
        modifiers: list[str],
    ) -> list[dict]:
        """Inject a small anchor pack when a pillar has too few literal matches upstream."""
        if not pillars:
            return []

        existing_norms = {
            self._normalize(kw.get("keyword", ""))
            for kw in (keywords or [])
            if kw.get("keyword")
        }

        injected: list[dict] = []
        for pillar in pillars:
            terms = self._pillar_anchor_terms(pillar)
            literal_count = sum(
                1 for kw in (keywords or [])
                if self._keyword_matches_terms(kw.get("keyword", ""), terms)
            )
            if literal_count >= MIN_LITERAL_ANCHORS_PER_PILLAR:
                continue

            needed = MIN_LITERAL_ANCHORS_PER_PILLAR - literal_count
            for candidate in self._build_anchor_pack(pillar, modifiers):
                norm = self._normalize(candidate["keyword"])
                if not norm or norm in existing_norms:
                    continue
                existing_norms.add(norm)
                injected.append(candidate)
                needed -= 1
                if needed <= 0:
                    break

        return injected

    def _build_anchor_pack(self, pillar: str, modifiers: list[str]) -> list[dict]:
        core = self._extract_core_term(pillar)
        ordered_modifiers = self._prioritize_anchor_modifiers(modifiers)

        candidates = [
            pillar,
            f"buy {core}",
            f"{core} online",
            f"{core} wholesale",
        ]
        if core.lower() != pillar.lower():
            candidates.insert(1, core)

        for modifier in ordered_modifiers[:4]:
            candidates.append(f"{modifier} {pillar}")
            candidates.append(f"{pillar} {modifier}")
            if core.lower() != pillar.lower():
                candidates.append(f"{modifier} {core}")
                candidates.append(f"{core} {modifier}")

        seen: set[str] = set()
        anchor_rows: list[dict] = []
        for keyword in candidates:
            norm = self._normalize(keyword)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            anchor_rows.append({
                "keyword": keyword.strip().lower(),
                "source": "anchor",
                "pillar": pillar,
                "raw_score": 82.0,
            })
        return anchor_rows

    def _prioritize_anchor_modifiers(self, modifiers: list[str]) -> list[str]:
        priority = {
            "organic": 0,
            "natural": 1,
            "premium": 2,
            "bulk": 3,
            "wholesale": 4,
            "supplier": 5,
            "online": 6,
            "price": 7,
        }
        unique: list[str] = []
        seen: set[str] = set()
        for modifier in modifiers or []:
            mod = str(modifier).strip().lower()
            if mod and mod not in seen:
                seen.add(mod)
                unique.append(mod)
        return sorted(unique, key=lambda mod: (priority.get(mod, 100), mod))

    def _pillar_anchor_terms(self, pillar: str) -> set[str]:
        terms = {pillar.strip().lower()}
        core = self._extract_core_term(pillar)
        if core:
            terms.add(core.strip().lower())
        return {term for term in terms if len(term) >= 3}

    def _keyword_matches_terms(self, keyword: str, terms: set[str]) -> bool:
        kw_lower = (keyword or "").strip().lower()
        return any(term in kw_lower for term in terms)

    def _extract_core_term(self, pillar: str) -> str:
        """Strip weight, size, geo, promo and quality noise from a product pilar name.
        e.g. 'Kerala Adimali Clove -200gm' -> 'adimali clove'
             'Aromatic True Cinnamon (Ceylon)' -> 'cinnamon ceylon'
             'Premium Cassia Cinnamon - 100g' -> 'cassia cinnamon'
        """
        s = pillar
        # Remove weight/size markers: 200gm, 100g, 8mm, 1kg, 500ml, etc.
        s = re.sub(r'\b\d+\s*(gm|g|kg|ml|l|mm|cm|oz)\b', '', s, flags=re.IGNORECASE)
        # Remove promotional phrases
        s = re.sub(r'\b(free\s*delivery|free\s*ship\w*|offer|discount)\b', '', s, flags=re.IGNORECASE)
        # Remove geo/origin markers
        s = re.sub(r'\b(kerala|indian|india)\b', '', s, flags=re.IGNORECASE)
        # Remove separators and brackets
        s = re.sub(r'[-–—&,\(\)]+', ' ', s)
        # Remove quality/descriptor noise words that add no search signal
        _NOISE = {
            "aromatic", "premium", "true", "finest", "pure", "natural", "organic",
            "fresh", "best", "top", "authentic", "raw", "selected", "handpicked",
            "certified", "bold", "extra", "special", "quality",
            # Commercial role / vague quality adjectives — should not become keyword roots
            "first", "original", "real", "genuine", "choice", "grade",
            "superior", "supreme", "classic", "standard", "traditional",
        }
        words = [w for w in s.split() if w.lower() not in _NOISE and len(w) > 1]
        s = " ".join(words).strip()
        # Collapse whitespace
        s = re.sub(r'\s+', ' ', s).strip().lower()
        # Return cleaned form, fallback to original lowercased if nothing left
        return s if len(s) > 2 else pillar.lower()

    def _detect_pillar(self, keyword: str, pillars: list[str]) -> str:
        """Detect which pillar a keyword belongs to using substring then word-overlap."""
        kw_lower = keyword.lower()
        # 1. Exact substring match
        for p in pillars:
            if p.lower() in kw_lower:
                return p
        # 2. Core-term substring match (only for multi-word cores to avoid false positives)
        for p in pillars:
            core = self._extract_core_term(p).lower()
            if core and " " in core and core in kw_lower:
                return p
        # 3. Word-overlap match — pick pillar with most significant word overlap
        _stop = {"the", "a", "an", "of", "in", "to", "for", "and", "or", "is", "it", "best", "top"}
        kw_words = set(kw_lower.split()) - _stop
        best_p = pillars[0] if pillars else "general"
        best_score = 0
        for p in pillars:
            p_clean = re.sub(r'[-–—&,\(\)\d]', ' ', p.lower())
            p_words = set(p_clean.split()) - _stop
            # Remove pure unit tokens like gm, kg, mm
            p_words = {w for w in p_words if not re.fullmatch(r'\d*(gm|g|kg|ml|mm|cm|oz)', w)}
            overlap = kw_words & p_words
            if overlap:
                score = len(overlap) / max(len(p_words), 1)
                if score > best_score:
                    best_score = score
                    best_p = p
        return best_p

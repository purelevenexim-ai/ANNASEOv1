"""
ruflo_20phase_wired.py
───────────────────────
Drop-in wrapper for ruflo_20phase_engine.py that adds:
  1. RawCollector — stores every phase output for QI scoring
  2. DomainContextEngine — domain filter after P3, pillar validation after P10
  3. MetricsCollector — timing/memory per phase for RSD health scoring

Usage in main.py (replace the old import):
    from engines.ruflo_20phase_wired import WiredRufloOrchestrator as RufloOrchestrator

This file does NOT modify ruflo_20phase_engine.py — it wraps it.
That way the original engine stays clean and testable on its own.
"""

from __future__ import annotations
import sys, os, logging
from pathlib import Path

# Ensure all folders on path
sys.path.insert(0, str(Path(__file__).parent.parent / "quality"))
sys.path.insert(0, str(Path(__file__).parent.parent / "rsd"))
sys.path.insert(0, str(Path(__file__).parent.parent / "modules"))
sys.path.insert(0, str(Path(__file__).parent))

from ruflo_20phase_engine import RufloOrchestrator, ContentPace, Seed

log = logging.getLogger("annaseo.wired_20phase")


class WiredRufloOrchestrator(RufloOrchestrator):
    """
    RufloOrchestrator with RawCollector + DomainContextEngine wired in.
    
    Injection points:
      After P2  → RawCollector.record_phase (raw keywords)
      After P3  → DomainContextEngine.classify_batch (domain filter)
                → RawCollector.record_phase (clean keywords)
      After P10 → DomainContextEngine.validate_pillars (pillar validation)
                → RawCollector.record_phase (pillars)
      All phases → MetricsCollector.observe (timing + memory)
    """

    def __init__(self, project_id: str = "", run_id: str = "", emit_fn=None):
        super().__init__()
        self._project_id = project_id
        self._run_id     = run_id
        self._emit_fn    = emit_fn  # callable(event_type, payload) — thread-safe
        self._collector  = self._load_collector()
        self._dce        = self._load_domain_context()
        self._metrics    = self._load_metrics()

    # ── Lazy loaders (graceful if engines not yet wired) ─────────────────────

    def _load_collector(self):
        try:
            from annaseo_qi_engine import RawCollector
            return RawCollector()
        except Exception as e:
            log.warning(f"[Wired] RawCollector not available: {e}")
            return None

    def _load_domain_context(self):
        try:
            from annaseo_domain_context import DomainContextEngine
            return DomainContextEngine()
        except Exception as e:
            log.warning(f"[Wired] DomainContextEngine not available: {e}")
            return None

    def _load_metrics(self):
        try:
            from annaseo_rsd_engine import MetricsCollector
            return MetricsCollector()
        except Exception as e:
            log.debug(f"[Wired] MetricsCollector not available: {e}")
            return None

    def set_run_context(self, project_id: str, run_id: str):
        """Call before run_seed to attach project/run context."""
        self._project_id = project_id
        self._run_id     = run_id

    def _run_phase(self, name: str, fn, *args, **kwargs):
        """Override: emit phase_log events to SSE stream around each phase."""
        if self._emit_fn:
            try: self._emit_fn("phase_log", {"phase": name, "msg": f"{name} starting..."})
            except Exception: pass
        import time as _t; t0 = _t.time()
        result = super()._run_phase(name, fn, *args, **kwargs)
        elapsed = round(_t.time() - t0, 1)
        if self._emit_fn:
            try:
                if result is not None:
                    count = len(result) if hasattr(result, '__len__') else None
                    msg = f"{name} complete ({elapsed}s)" + (f" — {count} items" if count is not None else "")
                    self._emit_fn("phase_log", {"phase": name, "msg": msg})
                else:
                    self._emit_fn("phase_log", {"phase": name, "msg": f"{name} returned no result ({elapsed}s)", "warn": True})
            except Exception: pass
        return result

    # ── Overridden run_seed with full wiring ──────────────────────────────────

    def run_seed(self, keyword: str, pace: ContentPace = None,
                  language: str = "english", region: str = "India",
                  product_url: str = "", existing_articles=None,
                  generate_articles: bool = False,
                  publish: bool = False,
                  gate_callback=None,
                  project_id: str = "",
                  run_id: str = "") -> dict:
        """
        Full 20-phase pipeline with all wiring enabled.
        Extra kwargs: project_id, run_id (for QI + domain context).
        """
        pid = project_id or self._project_id
        rid = run_id     or self._run_id
        pace = pace or ContentPace()

        # ── P1 Seed ──────────────────────────────────────────────────────────
        seed = self._run_phase("P1", self.p1.run, keyword, language, region, product_url)
        if not seed:
            return {"error": "P1 failed"}

        # ── P2 Expansion ─────────────────────────────────────────────────────
        with self._observe("P2_KeywordExpansion"):
            raw_kws = self._run_phase("P2", self.p2.run, seed)
        if not raw_kws:
            return {"error": "P2 failed"}
        print(f"  P2: {len(raw_kws)} raw keywords from 5 sources")

        # ✦ Record P2 outputs
        self._record("P2_KeywordExpansion", rid, pid,
                     {"count": len(raw_kws)},
                     [(kw, "keyword", {"phase": "P2"}) for kw in raw_kws[:200]])

        # ── P3 Normalization ─────────────────────────────────────────────────
        with self._observe("P3_Normalization"):
            kws = self._run_phase("P3", self.p3.run, seed, raw_kws)
        if not kws:
            return {"error": "P3 failed"}
        print(f"  P3: {len(kws)} clean keywords")

        # ✦ Domain Context filter after P3 (project-isolated)
        if self._dce and pid:
            accepted, rejected, ambiguous = self._dce.classify_batch(kws, pid)
            kws = accepted  # pass only accepted + ambiguous for human review
            if rejected:
                msg = f"[DomainCtx] {len(rejected)} keywords rejected, {len(accepted)} accepted"
                print(f"  {msg}")
                log.info(f"[Wired] Domain filter: {len(rejected)} rejected, {len(accepted)} accepted")
                if self._emit_fn:
                    try: self._emit_fn("phase_log", {"phase": "P3_DomainCtx", "msg": msg})
                    except Exception: pass
            if ambiguous:
                msg2 = f"[DomainCtx] {len(ambiguous)} ambiguous — will surface at Gate 3"
                print(f"  {msg2}")
                if self._emit_fn:
                    try: self._emit_fn("phase_log", {"phase": "P3_DomainCtx", "msg": msg2})
                    except Exception: pass

        # ✦ Record P3 outputs
        self._record("P3_Normalization", rid, pid,
                     {"count": len(kws)},
                     [(kw, "keyword", {"phase": "P3"}) for kw in kws[:200]])

        # ── GATE A: Universe keywords confirmed ───────────────────────────────
        if gate_callback:
            confirmed = gate_callback("universe_keywords",
                                       {"count": len(kws), "sample": kws[:20]})
            if confirmed is None:
                return {"status": "stopped_at_gate_A"}
            kws = confirmed.get("keywords", kws)

        # ── P4–P9 (unchanged from base class) ────────────────────────────────
        with self._observe("P4_EntityDetection"):
            entities = self._run_phase("P4", self.p4.run, seed, kws) or {}

        with self._observe("P5_IntentClassification"):
            intent_map = self._run_phase("P5", self.p5.run, seed, kws) or {}

        with self._observe("P6_SERPIntelligence"):
            serp_map = self._run_phase("P6", self.p6.run, seed, kws) or {}

        with self._observe("P7_OpportunityScoring"):
            scores = self._run_phase("P7", self.p7.run, seed, kws, intent_map, serp_map) or {k: 50.0 for k in kws}

        with self._observe("P8_TopicDetection"):
            topic_map = self._run_phase("P8", self.p8.run, seed, kws, scores) or {}
        print(f"  P8: {len(topic_map)} topics detected")

        with self._observe("P9_ClusterFormation"):
            clusters = self._run_phase("P9", self.p9.run, seed, topic_map) or {}
        print(f"  P9: {len(clusters)} clusters formed")

        # ✦ Record P9 clusters
        self._record("P9_ClusterFormation", rid, pid,
                     {"count": len(clusters)},
                     [(name, "cluster", {"topics": topics[:5]})
                      for name, topics in clusters.items()])

        # ── GATE B: Pillars confirmed ─────────────────────────────────────────
        if gate_callback:
            confirmed = gate_callback("pillars", {"clusters": list(clusters.keys())})
            if confirmed is None:
                return {"status": "stopped_at_gate_B"}
            removed = confirmed.get("removed_clusters", [])
            clusters = {k: v for k, v in clusters.items() if k not in removed}

        # ── P10 Pillar Identification ─────────────────────────────────────────
        with self._observe("P10_PillarIdentification"):
            pillars = self._run_phase("P10", self.p10.run, seed, clusters) or {}

        # ✦ Domain Context — validate pillars (project-isolated)
        if self._dce and pid and pillars:
            valid_pillars, rejected_pillars = self._dce.validate_pillars(pillars, pid)
            if rejected_pillars:
                msg = f"[DomainCtx] {len(rejected_pillars)} pillars rejected by domain filter"
                print(f"  {msg}")
                for rp in rejected_pillars:
                    print(f"    ✗ {rp['pillar_keyword']} — {rp['reason'][:60]}")
                pillars = valid_pillars
                if self._emit_fn:
                    try: self._emit_fn("phase_log", {"phase": "P10_DomainCtx", "msg": msg})
                    except Exception: pass
            msg2 = f"[DomainCtx] {len(pillars)} pillars validated for project {pid}"
            print(f"  {msg2}")
            if self._emit_fn:
                try: self._emit_fn("phase_log", {"phase": "P10_DomainCtx", "msg": msg2})
                except Exception: pass

        # ✦ Record P10 pillars
        self._record("P10_PillarIdentification", rid, pid,
                     {"count": len(pillars)},
                     [(v.get("pillar_keyword", k), "pillar", v)
                      for k, v in pillars.items()])

        # ── P11–P14 (unchanged from base) ─────────────────────────────────────
        graph = self._run_phase("P11", self.p11.run, seed, pillars,
                                 topic_map, intent_map, scores)
        if not graph:
            return {"error": "P11 failed"}

        link_map = self._run_phase("P12", self.p12.run, seed, graph) or {}
        calendar = self._run_phase("P13", self.p13.run, seed, graph, scores, pace) or []
        print(f"  P13: {len(calendar)} articles scheduled")
        cost_preview = pace.summary(len(calendar))
        print(f"  💰 {cost_preview['estimated_cost']} | ⏱ {cost_preview['estimated_time']}")

        # ── GATE C ────────────────────────────────────────────────────────────
        if gate_callback:
            confirmed = gate_callback("content_calendar", {
                "total": len(calendar), "pace": cost_preview, "first_10": calendar[:10]
            })
            if confirmed is None:
                return {"status": "stopped_at_gate_C"}
            if confirmed.get("new_pace"):
                new_pace = ContentPace(**confirmed["new_pace"])
                calendar = self._run_phase("P13", self.p13.run, seed, graph,
                                            scores, new_pace) or calendar

        calendar = self._run_phase("P14", self.p14.run, seed, calendar,
                                    existing_articles) or calendar
        print(f"  P14: {len(calendar)} articles after dedup")

        result = {
            "seed":             seed.__dict__ if hasattr(seed, "__dict__") else str(seed),
            "keyword_count":    len(kws),
            "cluster_count":    len(clusters),
            "topic_count":      len(topic_map),
            "pillar_count":     len(pillars),
            "calendar_count":   len(calendar),
            "calendar_preview": calendar[:5],
            "cost_preview":     cost_preview,
            "_graph":           graph,
            "_link_map":        link_map,
            "_calendar":        calendar,
            "_entities":        entities,
            "_intent_map":      intent_map,
        }

        # ── Content generation (optional) ─────────────────────────────────────
        if generate_articles:
            import json as _json
            print(f"\n  Starting content generation for {len(calendar)} articles...")
            generated = []
            for article in calendar[:10]:
                brief    = self.p15.run(seed, article, entities, link_map, intent_map)
                written  = self.p16.generate(brief, seed)
                optimised= self.p17.optimize(written, brief)
                metadata = self.p18.generate(optimised, brief, seed)
                if publish:
                    pub = self.p19.publish(optimised, metadata, article.get("scheduled_date", ""))
                    optimised["publish_result"] = pub
                generated.append({
                    "article_id": article["article_id"],
                    "title":      brief.get("title", ""),
                    "keyword":    brief.get("keyword", ""),
                    "seo_score":  optimised.get("seo_score", 0),
                })
                # ✦ Record content output
                self._record("P16_ClaudeContent", rid, pid,
                             {"seo_score": optimised.get("seo_score", 0)},
                             [(brief.get("title", ""), "article",
                               {"seo_score": optimised.get("seo_score", 0),
                                "eeat_score": optimised.get("eeat_score", 0),
                                "geo_score": optimised.get("geo_score", 0)})])
            result["generated"] = generated

        # ✦ Trigger QI scoring in background
        if self._collector and rid:
            try:
                from annaseo_qi_engine import QIEngine
                qi = QIEngine()
                import threading
                threading.Thread(
                    target=qi.job_score_run,
                    args=(rid, keyword),
                    daemon=True
                ).start()
            except Exception:
                pass

        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _record(self, phase: str, run_id: str, project_id: str,
                 raw: dict, items: list):
        """Store phase output in QI raw collector (non-blocking)."""
        if not self._collector or not run_id or not project_id:
            return
        try:
            self._collector.record_phase(phase, run_id, project_id, raw, items)
        except Exception as e:
            log.debug(f"[Wired] record_phase failed ({phase}): {e}")

    class _NullCtx:
        """No-op context manager when MetricsCollector unavailable."""
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def _observe(self, phase_name: str):
        if self._metrics:
            try:
                return self._metrics.observe(phase_name)
            except Exception:
                pass
        return self._NullCtx()

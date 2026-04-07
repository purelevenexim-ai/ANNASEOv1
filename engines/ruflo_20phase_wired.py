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
import sys, os, logging, json, sqlite3, time, gc
from pathlib import Path
from dataclasses import asdict, is_dataclass

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

# Ensure all folders on path
sys.path.insert(0, str(Path(__file__).parent.parent / "quality"))
sys.path.insert(0, str(Path(__file__).parent.parent / "rsd"))
sys.path.insert(0, str(Path(__file__).parent.parent / "modules"))
sys.path.insert(0, str(Path(__file__).parent))

from ruflo_20phase_engine import RufloOrchestrator, ContentPace, Seed

log = logging.getLogger("annaseo.wired_20phase")


def _safe_asdict(obj):
    """Safely convert dataclass to dict, handling nested dataclasses."""
    if is_dataclass(obj):
        return asdict(obj)
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    else:
        return str(obj) if obj else {}


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

    def _load_confirmed_pillars_from_db(self, run_id: str) -> tuple[dict, bool]:
        """
        Load confirmed pillars from gate_states table if Gate 2 is already confirmed.
        
        Returns:
            (pillars_dict, is_gate_2_confirmed)
            - pillars_dict: {pillar_name: pillar_data} or {} if not found
            - is_gate_2_confirmed: True if gate_2_confirmed=1 in runs table
        """
        try:
            db_path = Path(__file__).parent.parent / "annaseo.db"
            if not db_path.exists():
                return {}, False
            
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            
            # Check if Gate 2 is confirmed
            run_row = conn.execute(
                "SELECT gate_2_confirmed, pillars_json FROM runs WHERE run_id=?",
                (run_id,)
            ).fetchone()
            
            if not run_row or not run_row["gate_2_confirmed"]:
                conn.close()
                return {}, False
            
            # Load confirmed pillars from gate_states
            gate_row = conn.execute(
                "SELECT customer_input_json FROM gate_states WHERE run_id=? AND gate_number=2",
                (run_id,)
            ).fetchone()
            
            conn.close()
            
            if gate_row and gate_row["customer_input_json"]:
                try:
                    pillars_list = json.loads(gate_row["customer_input_json"])
                    # Convert list of PillarData to dict keyed by pillar_title
                    pillars_dict = {}
                    for p in pillars_list:
                        pillar_title = p.get("pillar_title", p.get("cluster_name", ""))
                        pillars_dict[pillar_title] = p
                    return pillars_dict, True
                except Exception as e:
                    log.warning(f"[Wired] Failed to parse confirmed pillars: {e}")
            
            return {}, True  # Gate 2 confirmed but no pillars found
            
        except Exception as e:
            log.debug(f"[Wired] _load_confirmed_pillars_from_db error: {e}")
            return {}, False

    def _run_phase(self, name: str, fn, *args, **kwargs):
        """Override: emit detailed phase_log events to SSE stream with timing, colors, data counts."""
        # Phase metadata
        phase_colors = {
            "P1": "teal", "P2": "teal", "P3": "teal", "P4": "cyan", "P5": "cyan",
            "P6": "cyan", "P7": "amber", "P8": "amber", "P9": "amber", "P10": "orange",
            "P11": "orange", "P12": "orange", "P13": "blue", "P14": "blue",
            "P15": "purple", "P16": "purple", "P17": "purple", "P18": "purple",
            "P19": "red", "P20": "red",
        }
        
        phase_descriptions = {
            "P1": "Seed Validation", "P2": "Keyword Expansion", "P3": "Normalization",
            "P4": "Entity Detection", "P5": "Intent Classification", "P6": "SERP Analysis",
            "P7": "Opportunity Scoring", "P8": "Topic Detection", "P9": "Cluster Formation",
            "P10": "Pillar Identification", "P11": "Knowledge Graph", "P12": "Internal Links",
            "P13": "Content Calendar", "P14": "Deduplication", "P15": "Blog Suggestions",
            "P16": "Content Generation", "P17": "SEO Optimization", "P18": "Schema Generation",
            "P19": "Publishing", "P20": "Feedback Loop",
        }
        
        color = phase_colors.get(name, "gray")
        description = phase_descriptions.get(name, name)
        
        # Emit start event
        if self._emit_fn:
            try:
                self._emit_fn("phase_log", {
                    "phase": name,
                    "status": "starting",
                    "color": color,
                    "description": description,
                    "msg": f"▶ {description} starting...",
                })
            except Exception:
                pass
        
        # Track timing and memory
        t0 = time.time()
        mem0 = 0
        if _HAS_PSUTIL:
            try:
                process = psutil.Process()
                mem0 = process.memory_info().rss / (1024 * 1024)  # MB
            except Exception:
                pass
        
        # Run phase
        try:
            result = super()._run_phase(name, fn, *args, **kwargs)
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            delta_mem = 0
            if _HAS_PSUTIL:
                try:
                    mem1 = psutil.Process().memory_info().rss / (1024 * 1024)
                    delta_mem = round(mem1 - mem0, 1)
                except Exception:
                    pass
            
            # Emit error event
            if self._emit_fn:
                try:
                    self._emit_fn("phase_log", {
                        "phase": name,
                        "status": "error",
                        "color": "red",
                        "msg": f"✗ {description} failed: {str(e)[:100]}",
                        "elapsed_ms": round(elapsed * 1000),
                        "memory_delta_mb": delta_mem,
                    })
                except Exception:
                    pass
            raise
        
        # Calculate metrics
        elapsed = round(time.time() - t0, 1)
        delta_mem = 0
        if _HAS_PSUTIL:
            try:
                mem1 = psutil.Process().memory_info().rss / (1024 * 1024)
                delta_mem = round(mem1 - mem0, 1)
            except Exception:
                pass

        # GC after heavy phases to reclaim memory
        if name in ("P2", "P3", "P6", "P8", "P9", "P10", "P14"):
            gc.collect()
        
        # Determine output count
        output_count = None
        if result is not None:
            if isinstance(result, (list, dict)):
                output_count = len(result)
            elif hasattr(result, "__len__"):
                try:
                    output_count = len(result)
                except:
                    pass
        
        # Emit completion event
        if self._emit_fn:
            try:
                msg_parts = [f"✓ {description}"]
                if output_count is not None:
                    msg_parts.append(f"{output_count} items")
                msg_parts.append(f"{elapsed}s")

                payload = {
                    "phase": name,
                    "status": "complete",
                    "color": color,
                    "msg": " | ".join(msg_parts),
                    "elapsed_ms": round(elapsed * 1000),
                    "memory_delta_mb": delta_mem,
                    "output_count": output_count,
                }

                # Add data flow hint
                phase_num = int(name[1:]) if name.startswith("P") and len(name) > 1 else None
                if phase_num and phase_num < 20:
                    next_phase = f"P{phase_num + 1}"
                    payload["next_phase"] = next_phase

                # Serialize a result sample so the frontend can show actual data
                try:
                    if isinstance(result, list):
                        payload["result_sample"] = {
                            "type": "list",
                            "items": [str(x) for x in result[:150]],
                        }
                    elif isinstance(result, dict):
                        items = list(result.items())[:100]
                        payload["result_sample"] = {
                            "type": "dict",
                            "items": [[str(k), str(v)] for k, v in items],
                        }
                    elif result is not None:
                        # Dataclass / namedtuple / object
                        _d = None
                        if hasattr(result, '_asdict'):
                            _d = dict(result._asdict())
                        elif hasattr(result, '__dict__'):
                            _d = vars(result)
                        if _d:
                            payload["result_sample"] = {
                                "type": "object",
                                "items": [[str(k), str(v)] for k, v in list(_d.items())[:30]],
                            }
                except Exception:
                    pass

                # ── Structured result_summary per phase (for split-view UI) ──
                try:
                    summary = {}
                    if name == "P1" and result:
                        kw = result.keyword if hasattr(result, 'keyword') else str(result)
                        summary = {"seed_keyword": kw, "validated": True}
                    elif name == "P2" and isinstance(result, list):
                        summary = {"expanded_count": len(result), "sample": [str(k) for k in result[:10]]}
                    elif name == "P3" and isinstance(result, list):
                        summary = {"normalized_count": len(result)}
                    elif name == "P4" and isinstance(result, dict):
                        summary = {"entity_count": len(result)}
                    elif name == "P5" and isinstance(result, dict):
                        intents = {}
                        for v in result.values():
                            intent = v if isinstance(v, str) else str(v)
                            intents[intent] = intents.get(intent, 0) + 1
                        summary = {"classified_count": len(result), "intent_distribution": dict(list(intents.items())[:8])}
                    elif name == "P6" and isinstance(result, dict):
                        summary = {"serp_analyzed_count": len(result)}
                    elif name == "P7" and isinstance(result, dict):
                        scores_list = [v for v in result.values() if isinstance(v, (int, float))]
                        avg_score = round(sum(scores_list) / len(scores_list), 1) if scores_list else 0
                        top_5 = sorted(result.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True)[:5]
                        summary = {"scored_count": len(result), "avg_score": avg_score, "top_5_keywords": [str(k) for k, _ in top_5]}
                    elif name == "P8" and isinstance(result, dict):
                        topics = [{"name": str(k), "size": len(v) if isinstance(v, (list, dict)) else 1} for k, v in list(result.items())[:20]]
                        summary = {"topic_count": len(result), "topics": topics}
                    elif name == "P9" and isinstance(result, dict):
                        clusters = [{"name": str(k), "keyword_count": len(v) if isinstance(v, list) else 1} for k, v in list(result.items())[:20]]
                        summary = {"cluster_count": len(result), "clusters": clusters}
                    elif name == "P10" and isinstance(result, dict):
                        pillar_list = []
                        for k, v in list(result.items())[:20]:
                            pk = v.get("pillar_keyword", k) if isinstance(v, dict) else str(k)
                            cc = len(v.get("clusters", [])) if isinstance(v, dict) else 0
                            kc = v.get("keyword_count", 0) if isinstance(v, dict) else 0
                            pillar_list.append({"name": pk, "cluster_count": cc, "keyword_count": kc})
                        summary = {"pillar_count": len(result), "pillars": pillar_list}
                    elif name == "P11" and isinstance(result, dict):
                        summary = {"graph_nodes": len(result)}
                    elif name == "P12" and isinstance(result, dict):
                        summary = {"link_count": len(result)}
                    elif name == "P13" and isinstance(result, list):
                        dates = [a.get("scheduled_date", "") for a in result if isinstance(a, dict)]
                        dates = sorted([d for d in dates if d])
                        date_range = f"{dates[0]}..{dates[-1]}" if len(dates) >= 2 else (dates[0] if dates else "")
                        summary = {"calendar_entries": len(result), "date_range": date_range}
                    elif name == "P14" and isinstance(result, list):
                        summary = {"deduplicated_count": len(result)}

                    if summary:
                        payload["result_summary"] = summary
                except Exception:
                    pass

                self._emit_fn("phase_log", payload)
            except Exception:
                pass
        
        return result

    # ── Overridden run_seed with full wiring ──────────────────────────────────

    def run_seed(self, keyword: str, pace: ContentPace = None,
                  language: str = "english", region: str = "India",
                  product_url: str = "", existing_articles=None,
                  generate_articles: bool = False,
                  publish: bool = False,
                  gate_callback=None,
                  project_id: str = "",
                  run_id: str = "",
                  max_phase: str = "P14",
                  execution_mode: str = "continuous",
                  group_gate_callback=None,
                  business_locations: list = None,
                  target_locations: list = None) -> dict:
        """
        Full 20-phase pipeline with all wiring enabled.
        Extra kwargs: project_id, run_id (for QI + domain context).
        max_phase: Stop after this phase (default P14). Use "P20" for content gen.
        execution_mode: "continuous" (no pauses) or "step_by_step" (pause between groups).
        group_gate_callback: Called between phase groups in step_by_step mode.
                             Receives (group_name, group_phases, result_so_far).
                             Must return True to continue, None/False to stop.
        """
        # Phase groups for step-by-step mode
        # P10 is in Scoring so user reviews pillars before graph is built
        _phase_groups = [
            ("Collection", ["P1", "P2", "P3"]),
            ("Analysis", ["P4", "P5", "P6"]),
            ("Scoring", ["P7", "P8", "P9", "P10"]),
            ("Structure", ["P11", "P12"]),
            ("Planning", ["P13", "P14"]),
        ]
        _max_phase_num = int(max_phase[1:]) if max_phase.startswith("P") else 14

        def _should_pause_after(phase_name):
            """Check if we should pause after this phase (end of a group in step_by_step mode)."""
            if execution_mode != "step_by_step" or not group_gate_callback:
                return False
            for group_name, phases in _phase_groups:
                if phase_name == phases[-1]:
                    return True
            return False

        def _emit_group_pause(group_name):
            """Emit SSE event for group pause and wait for callback."""
            if self._emit_fn:
                try:
                    self._emit_fn("phase_log", {
                        "phase": f"GROUP_{group_name.upper()}",
                        "status": "paused",
                        "color": "yellow",
                        "description": f"{group_name} group complete",
                        "msg": f"⏸ {group_name} group complete — waiting for continue...",
                    })
                except Exception:
                    pass
        pid = project_id or self._project_id
        rid = run_id     or self._run_id
        pace = pace or ContentPace()

        # ── P1 Seed ──────────────────────────────────────────────────────────
        seed = self._run_phase("P1", self.p1.run, keyword, language, region, product_url,
                               business_locations or [], target_locations or [])
        if not seed:
            return {"error": "P1 failed"}

        # ── P2 Expansion ─────────────────────────────────────────────────────
        # Try P2_Enhanced only when the seed keyword matches a stored pillar.
        # This prevents "ginger" run from pulling "clove/turmeric" pillar data.
        _p2e_kws = None
        if pid:
            try:
                from annaseo_p2_enhanced import P2_Enhanced, _db as _p2e_db
                p2e   = P2_Enhanced()
                _pdb  = _p2e_db()
                _stored_pillars = p2e._load_pillars(_pdb, pid)
                _pdb.close()

                # Seed parts (handles "turmeric, clove" comma syntax)
                _seed_parts = [s.strip().lower() for s in keyword.split(',') if s.strip()]

                # Match: any seed part is contained in or contains a stored pillar
                def _matches(seed_part, pillar):
                    return seed_part in pillar.lower() or pillar.lower() in seed_part

                _seed_matches = _stored_pillars and any(
                    _matches(sp, p) for sp in _seed_parts for p in _stored_pillars
                )

                if _seed_matches:
                    # Emit proper start event for P2
                    _t2 = time.time()
                    if self._emit_fn:
                        try:
                            self._emit_fn("phase_log", {
                                "phase": "P2", "status": "starting", "color": "teal",
                                "description": "Keyword Expansion",
                                "msg": "▶ Keyword Expansion starting (P2 Enhanced — autosuggest + pillars)...",
                            })
                        except Exception: pass

                    _p2e_kws = p2e.run_from_input(pid, language=language, region=region, seed_keyword=keyword)
                    _e2 = round(time.time() - _t2, 1)

                    if _p2e_kws:
                        log.info(f"[Wired] P2_Enhanced returned {len(_p2e_kws)} keywords for {pid}")
                        if self._emit_fn:
                            try:
                                self._emit_fn("phase_log", {
                                    "phase": "P2", "status": "complete", "color": "teal",
                                    "description": "Keyword Expansion",
                                    "msg": f"✓ Keyword Expansion | {len(_p2e_kws)} phrases | {_e2}s",
                                    "elapsed_ms": round(_e2 * 1000),
                                    "output_count": len(_p2e_kws),
                                    "next_phase": "P3",
                                    "result_sample": {
                                        "type": "list",
                                        "items": [str(k) for k in _p2e_kws[:150]],
                                    },
                                })
                            except Exception: pass
                else:
                    log.debug(f"[Wired] P2_Enhanced skipped: seed '{keyword}' not in pillars {_stored_pillars}")
            except Exception as _p2e_err:
                log.debug(f"[Wired] P2_Enhanced skipped: {_p2e_err}")

        if _p2e_kws:
            raw_kws = _p2e_kws
            print(f"  P2: {len(raw_kws)} keywords from pillar+supporting model")
        else:
            # Comma-separated pillars: expand each independently, then combine
            import dataclasses as _dc
            _seed_parts = [s.strip() for s in keyword.split(',') if s.strip()]
            if len(_seed_parts) > 1:
                raw_kws = []
                with self._observe("P2_KeywordExpansion"):
                    for _part in _seed_parts:
                        _sub_seed = _dc.replace(seed, keyword=_part)
                        _part_kws = self._run_phase("P2", self.p2.run, _sub_seed) or []
                        raw_kws.extend(_part_kws)
                        print(f"  P2: '{_part}' → {len(_part_kws)} keywords")
                raw_kws = list(dict.fromkeys(raw_kws))  # dedup, preserve order
                if not raw_kws:
                    return {"error": "P2 failed"}
                print(f"  P2: {len(raw_kws)} total from {len(_seed_parts)} pillars")
            else:
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
                                       {"count": len(kws), "keywords": kws})
            if confirmed is None:
                return {"status": "stopped_at_gate_A"}
            confirmed_kws = confirmed.get("keywords", kws)
            if isinstance(confirmed_kws, list):
                kws = confirmed_kws
            # else: keep original kws (guard against dict/string being passed)

        # ── Step-by-step pause: Collection group (P1-P3) complete ─────────
        if _should_pause_after("P3"):
            _emit_group_pause("Collection")
            gate_action = group_gate_callback("Collection", ["P1", "P2", "P3"], {"keyword_count": len(kws)})
            if gate_action == "stop" or gate_action is False:
                return {"status": "stopped_after_collection", "keyword_count": len(kws)}
            # "skip" means skip Analysis group (P4-P6), go straight to Scoring
            _skip_analysis = (gate_action == "skip")
        else:
            _skip_analysis = False

        # ── P4–P6: Analysis group ────────────────────────────────────────────
        entities = {}
        intent_map = {}
        serp_map = {}
        if not _skip_analysis:
            with self._observe("P4_EntityDetection"):
                entities = self._run_phase("P4", self.p4.run, seed, kws) or {}

            with self._observe("P5_IntentClassification"):
                intent_map = self._run_phase("P5", self.p5.run, seed, kws, entities) or {}

            with self._observe("P6_SERPIntelligence"):
                serp_map = self._run_phase("P6", self.p6.run, seed, kws, emit_fn=self._emit_fn) or {}
        else:
            if self._emit_fn:
                self._emit_fn("phase_log", {"phase": "GROUP_ANALYSIS", "status": "skipped", "color": "grey", "msg": "⏭ Analysis group skipped by user"})

        # ── Step-by-step pause: Analysis group (P4-P6) complete ───────────
        if not _skip_analysis and _should_pause_after("P6"):
            _emit_group_pause("Analysis")
            gate_action = group_gate_callback("Analysis", ["P4", "P5", "P6"], {"entity_count": len(entities), "intent_count": len(intent_map), "serp_count": len(serp_map)})
            if gate_action == "stop" or gate_action is False:
                return {"status": "stopped_after_analysis", "keyword_count": len(kws), "entity_count": len(entities)}
            _skip_scoring = (gate_action == "skip")
        else:
            _skip_scoring = False

        # ── P7-P10: Scoring group ────────────────────────────────────────────
        scores = {}
        topic_map = {}
        clusters = {}
        pillars = {}
        if not _skip_scoring:
            with self._observe("P7_OpportunityScoring"):
                scores = self._run_phase("P7", self.p7.run, seed, kws, intent_map, serp_map, entities) or {k: 50.0 for k in kws}

            with self._observe("P8_TopicDetection"):
                topic_map = self._run_phase("P8", self.p8.run, seed, kws, scores, intent_map, emit_fn=self._emit_fn) or {}
            print(f"  P8: {len(topic_map)} topics detected")

            # ── CHECK: Resume from Gate 2 (skip P9-P10 if confirmed) ──────────────
            confirmed_pillars, gate2_confirmed = self._load_confirmed_pillars_from_db(rid)
        
            if gate2_confirmed and confirmed_pillars:
                # Gate 2 already confirmed — use stored pillars and skip P9-P10
                pillars = confirmed_pillars
                # Build clusters dict from pillar topics so P11 has context
                clusters = {}
                for cname, pdata in pillars.items():
                    clusters[cname] = pdata.get("topics", [])
                msg = f"[Gate 2 Resume] Loaded {len(pillars)} confirmed pillars from DB, skipping P9-P10"
                print(f"  {msg}")
                log.info(msg)
                if self._emit_fn:
                    try:
                        self._emit_fn("phase_log", {"phase": "Gate2Resume", "msg": msg})
                    except Exception:
                        pass
            else:
                # Normal flow: Run P9-P10 to generate pillars
                with self._observe("P9_ClusterFormation"):
                    clusters = self._run_phase("P9", self.p9.run, seed, topic_map, project_id=pid) or {}
                print(f"  P9: {len(clusters)} clusters formed")

                # ✦ Record P9 clusters
                self._record("P9_ClusterFormation", rid, pid,
                             {"count": len(clusters)},
                             [(name, "cluster", {"topics": topics[:5]})
                              for name, topics in clusters.items()])

                # ── GATE B: Pillars confirmed ─────────────────────────────────────
                if gate_callback:
                    confirmed = gate_callback("pillars", {"clusters": list(clusters.keys())})
                    if confirmed is None:
                        return {"status": "stopped_at_gate_B"}
                    removed = confirmed.get("removed_clusters", [])
                    clusters = {k: v for k, v in clusters.items() if k not in removed}

                # ── P10 Pillar Identification ─────────────────────────────────────
                with self._observe("P10_PillarIdentification"):
                    pillars = self._run_phase("P10", self.p10.run, seed, clusters,
                                              scores=scores, topic_map=topic_map, project_id=pid) or {}

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
        else:
            if self._emit_fn:
                self._emit_fn("phase_log", {"phase": "GROUP_SCORING", "status": "skipped", "color": "grey", "msg": "⏭ Scoring group skipped by user"})

        # ── Step-by-step pause: Scoring group (P7-P10) complete ───────────
        if _should_pause_after("P10"):
            _emit_group_pause("Scoring")
            gate_action = group_gate_callback("Scoring", ["P7", "P8", "P9", "P10"], {"topic_count": len(topic_map), "cluster_count": len(clusters), "pillar_count": len(pillars)})
            if gate_action == "stop" or gate_action is False:
                return {"status": "stopped_after_scoring", "keyword_count": len(kws), "topic_count": len(topic_map), "cluster_count": len(clusters), "pillar_count": len(pillars)}
            _skip_structure = (gate_action == "skip")
        else:
            _skip_structure = False

        # ── P11–P12: Structure group ──────────────────────────────────────────
        graph = None
        link_map = {}
        if not _skip_structure:
            graph = self._run_phase("P11", self.p11.run, seed, pillars,
                                     topic_map, intent_map, scores)
            if not graph:
                log.warning("[Pipeline] P11 failed — building minimal graph from pillars")
                if self._emit_fn:
                    try: self._emit_fn("phase_log", {"phase": "P11", "status": "error", "color": "red", "msg": "✗ P11 Knowledge Graph failed — using minimal fallback"})
                    except Exception: pass
                # Build minimal KnowledgeGraph so P12-P14 can still work
                from engines.ruflo_20phase_engine import KnowledgeGraph as KG
                graph = KG(seed=seed.keyword)
                for cname, pdata in pillars.items():
                    graph.pillars[cname] = {
                        "title": pdata.get("pillar_title", cname),
                        "keyword": pdata.get("pillar_keyword", cname),
                        "clusters": {cname: {}}
                    }

            link_map = self._run_phase("P12", self.p12.run, seed, graph, intent_map, scores) or {}
        else:
            if self._emit_fn:
                self._emit_fn("phase_log", {"phase": "GROUP_STRUCTURE", "status": "skipped", "color": "grey", "msg": "⏭ Structure group skipped by user"})

        # ── Step-by-step pause: Structure group (P11-P12) complete ────────
        if not _skip_structure and _should_pause_after("P12"):
            _emit_group_pause("Structure")
            gate_action = group_gate_callback("Structure", ["P11", "P12"], {"pillar_count": len(pillars), "graph_nodes": len(graph) if graph else 0, "link_count": len(link_map)})
            if gate_action == "stop" or gate_action is False:
                return {"status": "stopped_after_structure", "keyword_count": len(kws), "pillar_count": len(pillars)}
            _skip_planning = (gate_action == "skip")
        else:
            _skip_planning = False

        # ── P13-P14: Planning group ───────────────────────────────────────────
        calendar = []
        cost_preview = pace.summary(0) if pace else {}
        if not _skip_planning and graph:
            calendar = self._run_phase("P13", self.p13.run, seed, graph, scores, pace) or []
            print(f"  P13: {len(calendar)} articles scheduled")
            cost_preview = pace.summary(len(calendar))
            print(f"  💰 {cost_preview['estimated_cost']} | ⏱ {cost_preview['estimated_time']}")

            # ── GATE C ────────────────────────────────────────────────────────
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

            # Load existing article titles from DB for P14 dedup
            _existing = existing_articles or []
            if not _existing and pid:
                try:
                    import sqlite3 as _s3
                    _content_db = _s3.connect(str(Path(__file__).parent.parent / "annaseo.db"), check_same_thread=False)
                    _content_db.row_factory = _s3.Row
                    _existing_rows = _content_db.execute(
                        "SELECT keyword FROM content_articles WHERE project_id=? AND status IN ('published','complete','generated')",
                        (pid,)
                    ).fetchall()
                    _existing = [r["keyword"] for r in _existing_rows if r["keyword"]]
                    _content_db.close()
                    if _existing:
                        log.info(f"[P14] Loaded {len(_existing)} existing articles for dedup")
                except Exception as _e:
                    log.warning(f"[P14] Failed to load existing articles: {_e}")

            calendar = self._run_phase("P14", self.p14.run, seed, calendar,
                                        _existing) or calendar
            print(f"  P14: {len(calendar)} articles after dedup")
        else:
            if self._emit_fn and _skip_planning:
                self._emit_fn("phase_log", {"phase": "GROUP_PLANNING", "status": "skipped", "color": "grey", "msg": "⏭ Planning group skipped by user"})

        result = {
            "seed":             seed.__dict__ if hasattr(seed, "__dict__") else str(seed),
            "keyword_count":    len(kws) if kws else 0,
            "cluster_count":    len(clusters) if clusters else 0,
            "topic_count":      len(topic_map) if topic_map else 0,
            "pillar_count":     len(pillars) if pillars else 0,
            "calendar_count":   len(calendar) if calendar else 0,
            "calendar_preview": (calendar or [])[:5],
            "cost_preview":     cost_preview,
            "_graph":           _safe_asdict(graph) if graph and (is_dataclass(graph) or hasattr(graph, '__dataclass_fields__')) else (graph or {}),
            "_link_map":        link_map or {},
            "_calendar":        calendar or [],
            "_entities":        entities or {},
            "_intent_map":      intent_map or {},
        }

        # ── Content generation (optional, only if max_phase allows) ─────────
        if generate_articles and _max_phase_num >= 15:
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

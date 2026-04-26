"""
Strategy V2 — Main Pipeline Orchestrator.

Flow per keyword:
  1. Classify intent (rule-based)
  2. Load KW2 context (if session_id provided)
  3. Generate 5-8 angles (AI)
  4. Generate blueprint per angle (parallel, ThreadPoolExecutor)
  5. Normalise + validate each blueprint
  6. QA score each blueprint
  7. Auto-fix if score < FIX_THRESHOLD (one attempt max)
  8. Save to DB
  9. Return scored results (max 8, sorted by overall score desc)

Designed to be called from a FastAPI background task or SSE stream handler.
"""
import json
import logging
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .intent_classifier import classify_intent
from .angle_generator import generate_angles
from .blueprint_generator import generate_blueprint
from .blueprint_normalizer import normalize_blueprint, validate_blueprint
from .qa_scorer import score_blueprint
from .fix_engine import fix_blueprint

log = logging.getLogger("strategy_v2.pipeline")

FIX_THRESHOLD = 75  # auto-fix if overall score below this
MAX_BLUEPRINTS = 8
MAX_PARALLEL = 4     # generate blueprints in parallel (ThreadPoolExecutor)


# ─────────────────────────────────────────────────────────────────────────────
# KW2 Context Loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_kw2_context(project_id: str, session_id: str, db) -> Optional[dict]:
    """
    Pull enrichment data from kw2 tables if a session_id is provided.
    Returns None if session not found or tables don't exist.
    """
    if not session_id:
        return None
    try:
        cur = db.cursor()

        # Business profile
        cur.execute("""
            SELECT business_type, usp, strategic_direction
            FROM kw2_business_profile WHERE session_id = ? LIMIT 1
        """, (session_id,))
        row = cur.fetchone()
        biz = dict(row) if row else {}

        # Top audience profile for USP
        cur.execute("""
            SELECT usp, target_locations, target_languages, personas
            FROM audience_profiles WHERE project_id = ? LIMIT 1
        """, (project_id,))
        aud_row = cur.fetchone()
        aud = dict(aud_row) if aud_row else {}

        # Pillar keywords
        cur.execute("""
            SELECT DISTINCT pillar FROM kw2_validated_keywords
            WHERE session_id = ? AND pillar != ''
            LIMIT 10
        """, (session_id,))
        pillars = [r[0] for r in cur.fetchall()]

        # Top intelligence questions
        cur.execute("""
            SELECT question_text FROM kw2_intelligence_questions
            WHERE session_id = ? ORDER BY score DESC LIMIT 8
        """, (session_id,))
        questions = [r[0] for r in cur.fetchall()]

        # Competitor gaps from strategy if exists
        cur.execute("""
            SELECT strategy_json FROM kw2_sessions WHERE session_id = ? LIMIT 1
        """, (session_id,))
        strat_row = cur.fetchone()
        competitor_gaps = []
        if strat_row and strat_row[0]:
            try:
                strat = json.loads(strat_row[0]) if isinstance(strat_row[0], str) else strat_row[0]
                competitor_gaps = strat.get("competitor_gaps", [])[:5]
            except Exception:
                pass

        usp = biz.get("usp") or aud.get("usp", "")
        audience_summary = ""
        if aud.get("personas"):
            try:
                personas = json.loads(aud["personas"]) if isinstance(aud["personas"], str) else aud["personas"]
                if isinstance(personas, list) and personas:
                    audience_summary = personas[0] if isinstance(personas[0], str) else str(personas[0])
            except Exception:
                pass

        return {
            "usp": usp,
            "audience_summary": audience_summary,
            "pillars": pillars,
            "top_questions": questions,
            "competitor_gaps": competitor_gaps,
        }
    except Exception as e:
        log.warning(f"[pipeline] Could not load kw2 context for session {session_id}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DB Save
# ─────────────────────────────────────────────────────────────────────────────

def _save_blueprints(db, project_id: str, session_id: str,
                     keyword: str, intent: str, scored_blueprints: list) -> list:
    """
    Persist blueprints to strategy_v2_blueprints table.
    Returns list of row IDs.
    """
    ids = []
    cur = db.cursor()
    for bp, qa in scored_blueprints:
        hook_obj = bp.get("hook", {})
        hook_text = hook_obj.get("text", "") if isinstance(hook_obj, dict) else str(hook_obj)
        story_obj = bp.get("story", {})
        story_text = (story_obj.get("scenario", "") if isinstance(story_obj, dict)
                      else str(story_obj))
        cta_obj = bp.get("cta", {})
        cta_text = cta_obj.get("text", "") if isinstance(cta_obj, dict) else str(cta_obj)

        cur.execute("""
            INSERT INTO strategy_v2_blueprints
            (project_id, session_id, keyword, intent, angle_type,
             title, hook, sections_json, story, cta,
             qa_seo_score, qa_aeo_score, qa_conversion_score,
             qa_depth_score, qa_overall_score,
             qa_gaps_json, qa_fixes_json, status, created_at)
            VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,'draft', datetime('now'))
        """, (
            project_id, session_id or "", keyword, intent,
            bp.get("angle_type", ""),
            bp.get("title", ""),
            hook_text,
            json.dumps(bp.get("sections", [])),
            story_text,
            cta_text,
            qa["seo"], qa["aeo"], qa["conversion"], qa["depth"], qa["overall"],
            json.dumps(qa["gaps"]),
            json.dumps(qa["fixes"]),
        ))
        ids.append(cur.lastrowid)
    db.commit()
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(keyword: str, project_id: str, db,
                 session_id: str = None,
                 on_progress: Callable[[dict], None] = None) -> list:
    """
    Run the full Strategy V2 pipeline for one keyword.

    Args:
        keyword:     The target keyword.
        project_id:  Project identifier.
        db:          Open SQLite connection (caller owns lifecycle).
        session_id:  Optional KW2 session for context enrichment.
        on_progress: Optional callback(dict) for streaming step updates.

    Returns:
        List of dicts: [{blueprint, qa_score, db_id}]
        Sorted by qa_overall_score descending. Max 8.
    """
    def emit(event: dict, console_msg: str = None):
        """Emit progress event + optional console message."""
        if on_progress:
            try:
                on_progress(event)
            except Exception:
                pass
        # Log to server console
        if console_msg:
            log.info(console_msg)

    t_start = time.time()
    
    emit({"step": "classify", "keyword": keyword, "status": "running"},
         f"🔍 [classify] Starting intent classification for '{keyword}'…")

    # Step 1: Intent
    t_intent = time.time()
    intent = classify_intent(keyword)
    intent_elapsed = round(time.time() - t_intent, 2)
    emit({"step": "classify", "keyword": keyword, "intent": intent, "status": "done"},
         f"✓ [classify] Intent: {intent} ({intent_elapsed}s)")

    # Step 2: KW2 context
    t_ctx = time.time()
    kw2_ctx = _load_kw2_context(project_id, session_id, db)
    ctx_elapsed = round(time.time() - t_ctx, 2)
    
    if kw2_ctx:
        pillars = len(kw2_ctx.get("pillars", []))
        emit({"step": "context", "kw2_enriched": True, "pillars": pillars},
             f"✓ [context] KW2 enriched ({pillars} pillars, {ctx_elapsed}s)")
    else:
        emit({"step": "context", "kw2_enriched": False},
             f"⚠ [context] No KW2 enrichment ({ctx_elapsed}s)")

    # Step 3: Angles
    t_angles = time.time()
    emit({"step": "angles", "status": "running"},
         f"🎯 [angles] Generating content angles…")
    
    angles = generate_angles(keyword, intent, kw2_ctx)
    angles_elapsed = round(time.time() - t_angles, 2)
    
    emit({"step": "angles", "count": len(angles), "status": "done"},
         f"✓ [angles] Generated {len(angles)} angles ({angles_elapsed}s)")

    # Step 4: Blueprints (parallel)
    t_bp = time.time()
    emit({"step": "blueprints", "total": len(angles), "status": "running"},
         f"🏗️ [blueprints] Building {len(angles)} blueprints in parallel (max {MAX_PARALLEL} workers)…")
    
    raw_blueprints = []
    bp_errors = []

    def _gen_one(idx_angle):
        idx, angle = idx_angle
        try:
            t = time.time()
            bp = generate_blueprint(keyword, angle, intent, kw2_ctx)
            elapsed = round(time.time() - t, 2)
            return (idx, bp, None, elapsed)
        except Exception as e:
            return (idx, None, str(e), None)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {pool.submit(_gen_one, (i, a)): i for i, a in enumerate(angles)}
        for future in as_completed(futures):
            idx, bp, err, elapsed = future.result()
            if bp:
                raw_blueprints.append(bp)
                title = bp.get("title", "?")
                elapsed_str = f" ({elapsed}s)" if elapsed else ""
                emit({"step": f"blueprint_{idx+1}", "title": title, "status": "done"},
                     f"  ✓ Blueprint {idx+1}: {title}{elapsed_str}")
            else:
                bp_errors.append((idx+1, err))
                emit({"step": f"blueprint_{idx+1}", "status": "error", "error": err},
                     f"  ✗ Blueprint {idx+1}: {err}")

    bp_elapsed = round(time.time() - t_bp, 2)
    emit({"step": "blueprints", "status": "done", "count": len(raw_blueprints)},
         f"✓ [blueprints] {len(raw_blueprints)}/{len(angles)} blueprints generated ({bp_elapsed}s)")

    # Step 5: Normalise + Validate
    t_norm = time.time()
    emit({"step": "normalize", "status": "running"},
         f"🔧 [normalize] Validating {len(raw_blueprints)} blueprints…")
    
    valid_blueprints = []
    rejected = 0
    
    for bp in raw_blueprints:
        bp = normalize_blueprint(bp)
        ok, reason = validate_blueprint(bp)
        if ok:
            valid_blueprints.append(bp)
        else:
            rejected += 1
            title = bp.get('title','?')
            log.info(f"[pipeline] Blueprint rejected ({reason}): {title}")

    if rejected > 0:
        emit({"step": "normalize", "rejected": rejected},
             f"⚠ [normalize] Rejected {rejected} blueprints")

    if not valid_blueprints:
        log.warning(f"[pipeline] No valid blueprints for '{keyword}' — using fallbacks")
        emit({"step": "normalize", "fallback": True},
             f"⚠ [normalize] Using fallback blueprints…")
        from .angle_generator import _fallback_angles
        from .blueprint_generator import _fallback_blueprint
        fallback_angles = _fallback_angles(keyword, intent)
        for a in fallback_angles[:3]:
            bp = _fallback_blueprint(keyword, a)
            valid_blueprints.append(normalize_blueprint(bp))
        emit({},
             f"✓ [normalize] Generated {len(valid_blueprints)} fallback blueprints")
    
    norm_elapsed = round(time.time() - t_norm, 2)
    emit({"step": "normalize", "count": len(valid_blueprints)},
         f"✓ [normalize] {len(valid_blueprints)} blueprints valid ({norm_elapsed}s)")

    # Step 6+7: QA Score + auto-fix
    t_qa = time.time()
    emit({"step": "qa", "count": len(valid_blueprints), "status": "running"},
         f"📊 [qa] Scoring {len(valid_blueprints)} blueprints…")
    
    scored = []
    fixed_count = 0
    
    for i, bp in enumerate(valid_blueprints, 1):
        t_blueprint_qa = time.time()
        qa = score_blueprint(bp)
        qa_elapsed = round(time.time() - t_blueprint_qa, 2)
        
        title = bp.get("title", "?")
        score = round(qa["overall"], 1)
        
        if qa["overall"] < FIX_THRESHOLD:
            emit({"step": "fix", "title": title, "score_before": qa["overall"]},
                 f"  ⚙️ [{i}/{len(valid_blueprints)}] {title}: score {score} < {FIX_THRESHOLD}… attempting fix")
            
            t_fix = time.time()
            bp = fix_blueprint(bp, qa)
            qa = score_blueprint(bp)  # re-score after fix
            fix_elapsed = round(time.time() - t_fix, 2)
            new_score = round(qa["overall"], 1)
            fixed_count += 1
            
            emit({"step": "fix_done", "title": title, "score_before": score, "score_after": new_score},
                 f"  ✓ [{i}/{len(valid_blueprints)}] Fixed: {score} → {new_score} ({fix_elapsed}s)")
        else:
            emit({},
                 f"  ✓ [{i}/{len(valid_blueprints)}] {title}: {score} (no fix needed) ({qa_elapsed}s)")
        
        scored.append((bp, qa))

    if fixed_count > 0:
        emit({}, f"✓ [qa] Fixed {fixed_count}/{len(valid_blueprints)} low-scoring blueprints")

    # Step 8: Sort + cap
    scored.sort(key=lambda x: x[1]["overall"], reverse=True)
    original_count = len(scored)
    scored = scored[:MAX_BLUEPRINTS]
    
    qa_elapsed = round(time.time() - t_qa, 2)
    emit({"step": "qa", "status": "done", "count": len(scored)},
         f"✓ [qa] Top {len(scored)} blueprints selected (from {original_count}) ({qa_elapsed}s)")

    # Step 9: Save
    t_save = time.time()
    emit({"step": "save", "status": "running"},
         f"💾 [save] Persisting {len(scored)} blueprints to database…")
    
    ids = _save_blueprints(db, project_id, session_id, keyword, intent, scored)
    save_elapsed = round(time.time() - t_save, 2)
    emit({"step": "save", "status": "done", "count": len(ids)},
         f"✓ [save] {len(ids)} blueprints saved ({save_elapsed}s)")

    elapsed = round(time.time() - t_start, 1)
    results = []
    for (bp, qa), db_id in zip(scored, ids):
        results.append({
            "id": db_id,
            "keyword": keyword,
            "intent": intent,
            "title": bp.get("title", ""),
            "angle_type": bp.get("angle_type", ""),
            "hook": bp.get("hook", {}).get("text", "") if isinstance(bp.get("hook"), dict) else "",
            "sections": bp.get("sections", []),
            "story": bp.get("story", {}),
            "cta": bp.get("cta", {}),
            "qa_score": qa,
        })

    emit({"step": "done", "keyword": keyword, "blueprints": len(results), "elapsed": elapsed},
         f"✅ [done] '{keyword}' complete — {len(results)} blueprints ({elapsed}s total)")
    
    return results

"""
================================================================================
ANNASEO — QUALITY ENGINE
================================================================================
File        : annaseo_quality_engine.py
Purpose     : Read live result data → score quality → collect user feedback
              → identify patterns in failures → tune the generating algorithms.

The loop
────────
  1. DataStore has results from all engine runs
  2. QualityEngine reads those results after each project completes
  3. Scores each item (keyword, article, cluster, audit) 0–100
  4. Presents low-scoring / flagged items in the RSD dashboard
  5. User marks items: Good ✓ | Bad ✗ | Why (free text reason)
  6. Engine identifies patterns in "Bad" feedback
  7. Generates a TuningInstruction (specific prompt/parameter change)
  8. Applies tuning with same Ruflo approval pipeline
  9. Next run uses tuned engine → results improve

Real example from the requirements
────────────────────────────────────
  Engine output:  pillars = ["cinnamon benefits", "cinnamon tour", "cinnamon recipes"]
  DataStore:      stores as 3 separate pillar_keyword items
  QualityEngine:  scores "cinnamon tour" as 0.2 (low — "tour" is off-topic)
  Dashboard:      shows "cinnamon tour" in review queue
  User action:    marks Bad ✗ — reason: "Tour has nothing to do with spices"
  Pattern engine: "tour" appearing as pillar keyword in spice business = off-topic pattern
  Tuning:         adds "tour" to OffTopicFilter kill list for this project
                  AND tunes the pillar scoring prompt to penalise non-product words

Quality Dimensions per result type
────────────────────────────────────
  pillar_keyword    → relevance to seed, intent match, commercial value
  cluster_name      → coherence, specificity, relation to pillar
  article_body      → E-E-A-T, GEO readiness, readability, originality
  article_title     → keyword presence, clarity, CTR potential
  audit_finding     → severity accuracy, actionability
  ranking_keyword   → tracking validity (is this keyword worth tracking?)

AI Usage (free tools only for scoring, Claude only for tuning verification)
─────────────────────────────────────────────────────────────────────────────
  Gemini 1.5 Flash  → batch quality scoring (free tier)
  Groq              → pattern analysis from feedback (free tier)
  DeepSeek local    → tuning code generation (Ollama, free)
  Claude            → final tuning verification + approval notes only
================================================================================
"""

from __future__ import annotations

import os, json, re, hashlib, logging, sqlite3, time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from annaseo_data_store import DataStore, ResultType, _get_db

log = logging.getLogger("annaseo.quality")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — QUALITY LABELS & MODELS
# ─────────────────────────────────────────────────────────────────────────────

class QualityLabel:
    UNREVIEWED = "unreviewed"
    GOOD       = "good"
    BAD        = "bad"
    IGNORED    = "ignored"   # user says this item doesn't matter


class TuningStatus:
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED  = "applied"
    ROLLED_BACK = "rolled_back"


@dataclass
class QualityScore:
    item_id:       str
    item_type:     str
    item_value:    str
    score:         float         # 0-100
    dimensions:    Dict[str, float]  # per-dimension breakdown
    issues:        List[str]     # what's wrong
    suggestions:   List[str]     # how to improve
    confidence:    float         = 0.8


@dataclass
class UserFeedback:
    feedback_id:   str
    item_id:       str
    project_id:    str
    label:         str           # good | bad | ignored
    reason:        str           # why it's bad (free text from user)
    suggested_fix: str           = ""
    created_at:    str           = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class FeedbackPattern:
    pattern_id:    str
    pattern:       str           # what the pattern is
    item_type:     str           # what type of item this affects
    engine_name:   str           # which engine to tune
    examples:      List[str]     # concrete examples of the problem
    frequency:     int           # how many times seen
    severity:      str           # "critical"|"high"|"medium"|"low"


@dataclass
class TuningInstruction:
    tuning_id:       str
    pattern_id:      str
    title:           str
    description:     str
    engine_name:     str
    tuning_type:     str         # "prompt_edit"|"parameter"|"filter"|"scoring_rule"
    target:          str         # function/prompt/parameter name
    before_value:    str         # what it is now
    after_value:     str         # what it should be
    evidence:        List[str]   # user feedback examples that drove this
    status:          str         = TuningStatus.PENDING
    approved_by:     str         = ""
    approved_at:     str         = ""
    rejection_reason:str         = ""
    applied_at:      str         = ""
    rollback_value:  str         = ""
    created_at:      str         = field(default_factory=lambda: datetime.utcnow().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DATABASE (extends the shared AnnaSEO DB)
# ─────────────────────────────────────────────────────────────────────────────

class QualityDB:
    def __init__(self):
        self._db = _get_db()
        self._init()

    def _init(self):
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS qe_quality_scores (
            item_id       TEXT PRIMARY KEY,
            result_type   TEXT,
            item_type     TEXT,
            item_value    TEXT,
            score         REAL,
            dimensions    TEXT DEFAULT '{}',
            issues        TEXT DEFAULT '[]',
            suggestions   TEXT DEFAULT '[]',
            confidence    REAL DEFAULT 0.8,
            scored_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS qe_user_feedback (
            feedback_id   TEXT PRIMARY KEY,
            item_id       TEXT NOT NULL,
            project_id    TEXT NOT NULL,
            label         TEXT NOT NULL,
            reason        TEXT DEFAULT '',
            suggested_fix TEXT DEFAULT '',
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS qe_feedback_patterns (
            pattern_id    TEXT PRIMARY KEY,
            pattern       TEXT,
            item_type     TEXT,
            engine_name   TEXT,
            examples      TEXT DEFAULT '[]',
            frequency     INTEGER DEFAULT 1,
            severity      TEXT DEFAULT 'medium',
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen     TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS qe_tuning_instructions (
            tuning_id        TEXT PRIMARY KEY,
            pattern_id       TEXT,
            title            TEXT,
            description      TEXT,
            engine_name      TEXT,
            tuning_type      TEXT,
            target           TEXT,
            before_value     TEXT DEFAULT '',
            after_value      TEXT DEFAULT '',
            evidence         TEXT DEFAULT '[]',
            status           TEXT DEFAULT 'pending',
            approved_by      TEXT DEFAULT '',
            approved_at      TEXT DEFAULT '',
            rejection_reason TEXT DEFAULT '',
            applied_at       TEXT DEFAULT '',
            rollback_value   TEXT DEFAULT '',
            created_at       TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_qe_score_item    ON qe_quality_scores(item_id);
        CREATE INDEX IF NOT EXISTS idx_qe_fb_item       ON qe_user_feedback(item_id);
        CREATE INDEX IF NOT EXISTS idx_qe_fb_project    ON qe_user_feedback(project_id);
        CREATE INDEX IF NOT EXISTS idx_qe_fb_label      ON qe_user_feedback(label);
        CREATE INDEX IF NOT EXISTS idx_qe_tuning_status ON qe_tuning_instructions(status);
        """)
        self._db.commit()

    def save_score(self, qs: QualityScore):
        self._db.execute("""
            INSERT OR REPLACE INTO qe_quality_scores
            (item_id, item_type, item_value, score, dimensions, issues, suggestions, confidence)
            VALUES (?,?,?,?,?,?,?,?)
        """, (qs.item_id, qs.item_type, qs.item_value[:500], qs.score,
              json.dumps(qs.dimensions), json.dumps(qs.issues),
              json.dumps(qs.suggestions), qs.confidence))
        self._db.commit()

    def save_feedback(self, fb: UserFeedback):
        self._db.execute("""
            INSERT OR REPLACE INTO qe_user_feedback
            (feedback_id, item_id, project_id, label, reason, suggested_fix)
            VALUES (?,?,?,?,?,?)
        """, (fb.feedback_id, fb.item_id, fb.project_id, fb.label,
              fb.reason, fb.suggested_fix))
        # Update item label in data store
        self._db.execute(
            "UPDATE ds_result_items SET quality_label=?, quality_score=? WHERE item_id=?",
            (fb.label,
             100.0 if fb.label == QualityLabel.GOOD else 0.0 if fb.label == QualityLabel.BAD else None,
             fb.item_id)
        )
        self._db.commit()

    def save_pattern(self, fp: FeedbackPattern):
        self._db.execute("""
            INSERT OR REPLACE INTO qe_feedback_patterns
            (pattern_id, pattern, item_type, engine_name, examples, frequency, severity, last_seen)
            VALUES (?,?,?,?,?,?,?,?)
        """, (fp.pattern_id, fp.pattern, fp.item_type, fp.engine_name,
              json.dumps(fp.examples), fp.frequency, fp.severity,
              datetime.utcnow().isoformat()))
        self._db.commit()

    def save_tuning(self, ti: TuningInstruction):
        self._db.execute("""
            INSERT OR REPLACE INTO qe_tuning_instructions
            (tuning_id, pattern_id, title, description, engine_name, tuning_type,
             target, before_value, after_value, evidence, status, approved_by,
             approved_at, rejection_reason, applied_at, rollback_value)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (ti.tuning_id, ti.pattern_id, ti.title, ti.description,
              ti.engine_name, ti.tuning_type, ti.target,
              ti.before_value[:5000], ti.after_value[:5000],
              json.dumps(ti.evidence), ti.status, ti.approved_by,
              ti.approved_at, ti.rejection_reason, ti.applied_at,
              ti.rollback_value[:5000]))
        self._db.commit()

    def get_bad_feedback(self, project_id: str = None,
                          limit: int = 200) -> List[dict]:
        q = "SELECT f.*, i.item_type, i.item_value, i.result_type FROM qe_user_feedback f JOIN ds_result_items i ON f.item_id=i.item_id WHERE f.label='bad'"
        p = []
        if project_id: q += " AND f.project_id=?"; p.append(project_id)
        q += " ORDER BY f.created_at DESC LIMIT ?"
        p.append(limit)
        return [dict(r) for r in self._db.execute(q, p).fetchall()]

    def get_pending_tunings(self) -> List[dict]:
        return [dict(r) for r in self._db.execute(
            "SELECT * FROM qe_tuning_instructions WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()]

    def get_review_queue(self, project_id: str = None,
                          item_type: str = None, limit: int = 100) -> List[dict]:
        """Items needing human review — low quality score or unreviewed."""
        q = """SELECT i.*, COALESCE(s.score, -1) as quality_score,
                      s.issues, s.suggestions, f.label, f.reason
               FROM ds_result_items i
               LEFT JOIN qe_quality_scores s ON i.item_id = s.item_id
               LEFT JOIN qe_user_feedback f ON i.item_id = f.item_id
               WHERE i.quality_label = 'unreviewed'
                  OR s.score < 60
                  OR i.quality_label = 'bad'"""
        p = []
        if project_id: q += " AND i.project_id=?"; p.append(project_id)
        if item_type:  q += " AND i.item_type=?"; p.append(item_type)
        q += " ORDER BY COALESCE(s.score, 50) ASC LIMIT ?"
        p.append(limit)
        return [dict(r) for r in self._db.execute(q, p).fetchall()]

    def quality_stats(self, project_id: str = None) -> dict:
        p = [project_id] if project_id else []
        where = "WHERE project_id=?" if project_id else ""
        rows = self._db.execute(
            f"SELECT quality_label, COUNT(*) as cnt FROM ds_result_items {where} GROUP BY quality_label", p
        ).fetchall()
        counts = {r["quality_label"]: r["cnt"] for r in rows}
        total  = sum(counts.values())
        good   = counts.get("good", 0)
        bad    = counts.get("bad", 0)
        return {
            "total_items":   total,
            "good":          good,
            "bad":           bad,
            "unreviewed":    counts.get("unreviewed", 0),
            "quality_rate":  round(good / max(good + bad, 1) * 100, 1),
            "pending_tunings": len(self.get_pending_tunings()),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — AI QUALITY SCORER (Gemini, free tier)
# ─────────────────────────────────────────────────────────────────────────────

class AIQualityScorer:
    """
    Uses Gemini 1.5 Flash (free) to score items before human review.
    Pre-flags obvious problems so the review queue surfaces the worst items first.
    """
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    # Scoring rubrics per item type
    RUBRICS = {
        "pillar_keyword": {
            "dimensions": ["business_relevance","search_intent","commercial_value","uniqueness"],
            "prompt_suffix": "Is this a strong pillar keyword for the business? A good pillar keyword should be broad but directly related to the business's products/services."
        },
        "cluster_name": {
            "dimensions": ["coherence","specificity","pillar_relation","content_potential"],
            "prompt_suffix": "Is this a good content cluster name? It should clearly define a content territory."
        },
        "article_body": {
            "dimensions": ["eeat_signals","geo_readiness","readability","originality","factual_density"],
            "prompt_suffix": "Score this article content on E-E-A-T, GEO readiness (AI citation potential), readability, and factual depth."
        },
        "article_title": {
            "dimensions": ["keyword_presence","clarity","ctr_potential","uniqueness"],
            "prompt_suffix": "Is this a strong SEO article title? Should have keyword, be compelling, and avoid being generic."
        },
        "supporting_keyword": {
            "dimensions": ["relevance","search_potential","non_duplicate"],
            "prompt_suffix": "Is this a valid supporting keyword that adds value to the keyword universe?"
        },
    }

    def score_batch(self, items: List[dict], business_context: str = "") -> List[QualityScore]:
        """Score a batch of items. Returns list of QualityScore objects."""
        key = os.getenv("GEMINI_API_KEY", "")
        results = []
        for item in items[:50]:  # cap batch size
            item_type = item.get("item_type", "")
            rubric = self.RUBRICS.get(item_type, self.RUBRICS["pillar_keyword"])
            if key:
                qs = self._gemini_score(item, rubric, business_context)
            else:
                qs = self._rule_score(item)
            results.append(qs)
        return results

    def _gemini_score(self, item: dict, rubric: dict,
                       business_context: str) -> QualityScore:
        key = os.getenv("GEMINI_API_KEY", "")
        dims = rubric["dimensions"]
        dims_str = ", ".join(dims)

        prompt = f"""Score this SEO content item for quality.

Business context: {business_context or "organic spice e-commerce business"}
Item type: {item.get('item_type', '')}
Item value: {item.get('item_value', '')}
Additional data: {json.dumps(json.loads(item.get('item_meta','{}') or '{}'))[:200]}

{rubric['prompt_suffix']}

Score each dimension 0-100:
Dimensions: {dims_str}

Also:
- List up to 3 specific issues (if any)
- List up to 2 suggestions for improvement (if bad)
- Overall score (weighted average)

Return JSON only:
{{"score": 0-100, "dimensions": {{{', '.join(f'"{d}": 0-100' for d in dims)}}}, "issues": [], "suggestions": [], "confidence": 0.0-1.0}}"""

        try:
            import requests as _req
            r = _req.post(
                f"{self.GEMINI_URL}?key={key}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.05, "maxOutputTokens": 300}},
                timeout=12
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                return QualityScore(
                    item_id=item["item_id"],
                    item_type=item.get("item_type", ""),
                    item_value=item.get("item_value", ""),
                    score=float(data.get("score", 50)),
                    dimensions=data.get("dimensions", {}),
                    issues=data.get("issues", []),
                    suggestions=data.get("suggestions", []),
                    confidence=float(data.get("confidence", 0.8))
                )
        except Exception as e:
            log.warning(f"Gemini scoring failed: {e}")
        return self._rule_score(item)

    def _rule_score(self, item: dict) -> QualityScore:
        """Rule-based scoring — no AI needed."""
        value     = str(item.get("item_value", "")).lower()
        item_type = item.get("item_type", "")
        score     = 70.0
        issues    = []

        # Off-topic signals for keyword items
        OFF_TOPIC_WORDS = [
            "tour","hotel","flight","resort","travel","vacation","holiday",
            "game","sport","movie","film","music","song","news","weather",
            "meme","viral","funny","joke","celebrity","actor"
        ]
        QUALITY_SIGNALS = ["benefits","how to","guide","recipe","buy","price","vs",
                           "review","organic","natural","health","best"]

        if item_type in ("pillar_keyword", "supporting_keyword", "cluster_keyword"):
            words = value.split()
            off_hits = [w for w in words if w in OFF_TOPIC_WORDS]
            if off_hits:
                score -= 40
                issues.append(f"Off-topic word detected: {off_hits}")
            quality_hits = sum(1 for q in QUALITY_SIGNALS if q in value)
            score += quality_hits * 5
            if len(words) < 2:
                score -= 10
                issues.append("Too short — good pillar keywords usually have 2-4 words")
            if len(words) > 6:
                score -= 5
                issues.append("Too long for a pillar — better suited as supporting keyword")

        elif item_type == "article_body":
            meta = json.loads(item.get("item_meta", "{}") or "{}")
            seo  = meta.get("seo_score", 0)
            eeat = meta.get("eeat_score", 0)
            geo  = meta.get("geo_score", 0)
            if seo:   score = (seo + eeat + geo) / 3
            if score < 70:
                issues.append(f"Low quality scores: SEO={seo}, E-E-A-T={eeat}, GEO={geo}")

        elif item_type == "article_title":
            if len(value) < 30:
                score -= 15
                issues.append("Title too short (<30 chars)")
            if len(value) > 70:
                score -= 10
                issues.append("Title too long (>70 chars, truncates in SERP)")

        score = max(0, min(100, score))
        return QualityScore(
            item_id=item["item_id"], item_type=item_type,
            item_value=item.get("item_value", ""),
            score=score, dimensions={}, issues=issues, suggestions=[],
            confidence=0.7
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — PATTERN ANALYSER (Groq, free tier)
# ─────────────────────────────────────────────────────────────────────────────

class PatternAnalyser:
    """
    Uses Groq (Llama, free tier) to find patterns in user "Bad" feedback.
    Identifies systematic failures — not just one-off mistakes.

    Example pattern:
      Bad feedback × 5: "tour", "trip", "travel" appearing in pillar keywords
      → Pattern: "Non-product words appear as pillars in spice business universe"
      → Engine: 20phase_engine / P8 pillar detection
      → Tuning: add to OffTopicFilter, tune pillar scoring prompt
    """
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

    def analyse(self, bad_feedback: List[dict],
                 project_context: str = "") -> List[FeedbackPattern]:
        """Find patterns in a list of bad feedback items."""
        if not bad_feedback:
            return []

        key = os.getenv("GROQ_API_KEY", "")
        if key:
            return self._groq_analyse(bad_feedback, project_context)
        return self._rule_patterns(bad_feedback)

    def _groq_analyse(self, feedback: List[dict],
                       context: str) -> List[FeedbackPattern]:
        import requests as _req
        key = os.getenv("GROQ_API_KEY", "")
        feedback_text = "\n".join(
            f"- [{f['item_type']}] '{f['item_value']}' — User said: {f.get('reason','bad')}"
            for f in feedback[:40]
        )
        try:
            r = _req.post(
                self.GROQ_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "max_tokens": 1000,
                      "messages": [{"role": "user", "content": f"""Analyse these user quality complaints about an SEO keyword and content engine.

Business: {context or "organic spice e-commerce"}

Bad feedback items:
{feedback_text}

Find systematic patterns — groups of similar complaints that point to the same underlying algorithm problem.

For each pattern found:
- What is the pattern?
- Which engine/function needs fixing?
- How severe is it?
- What type of tuning is needed?

Return JSON array:
[{{"pattern":"description","item_type":"pillar_keyword|cluster_name|article_body|etc","engine_name":"20phase_engine|content_engine|seo_audit|etc","severity":"critical|high|medium|low","tuning_type":"prompt_edit|parameter|filter|scoring_rule","examples":["example1","example2"]}}]"""}]},
                timeout=20
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
            m = re.search(r'\[.*\]', text, re.DOTALL)
            if m:
                patterns_data = json.loads(m.group(0))
                return [
                    FeedbackPattern(
                        pattern_id=f"pat_{hashlib.md5(p.get('pattern','').encode()).hexdigest()[:10]}",
                        pattern=p.get("pattern", ""),
                        item_type=p.get("item_type", ""),
                        engine_name=p.get("engine_name", "20phase_engine"),
                        examples=p.get("examples", [])[:5],
                        frequency=sum(1 for f in feedback if any(
                            ex.lower() in f.get("item_value","").lower()
                            for ex in p.get("examples",[])
                        )),
                        severity=p.get("severity", "medium"),
                    )
                    for p in patterns_data[:10]
                ]
        except Exception as e:
            log.warning(f"Groq pattern analysis failed: {e}")
        return self._rule_patterns(feedback)

    def _rule_patterns(self, feedback: List[dict]) -> List[FeedbackPattern]:
        """Rule-based pattern detection — no AI needed."""
        from collections import Counter
        type_counts = Counter(f.get("item_type", "") for f in feedback)
        patterns = []

        for item_type, count in type_counts.most_common():
            if count >= 2:
                examples = [f.get("item_value","")[:50] for f in feedback
                            if f.get("item_type") == item_type][:5]
                reasons  = [f.get("reason","") for f in feedback
                            if f.get("item_type") == item_type and f.get("reason")][:3]

                engine = "20phase_engine" if "keyword" in item_type else "content_engine"
                patterns.append(FeedbackPattern(
                    pattern_id=f"pat_rule_{item_type}_{int(time.time())}",
                    pattern=f"Multiple bad {item_type} items: {'; '.join(reasons[:2])}",
                    item_type=item_type,
                    engine_name=engine,
                    examples=examples,
                    frequency=count,
                    severity="high" if count >= 5 else "medium"
                ))
        return patterns


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — TUNING GENERATOR (DeepSeek + Claude verification)
# ─────────────────────────────────────────────────────────────────────────────

class TuningGenerator:
    """
    Converts a FeedbackPattern into a TuningInstruction.
    DeepSeek writes the actual tuning code/prompt change.
    Claude verifies it before it goes to the approval gate.
    """
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    # What each tuning_type means
    TUNING_TYPES = {
        "filter":       "Add word/phrase to OffTopicFilter kill list",
        "prompt_edit":  "Edit the AI prompt for the generating function",
        "parameter":    "Change a numeric parameter (threshold, weight, limit)",
        "scoring_rule": "Add/modify a rule in the scoring system",
    }

    def generate(self, pattern: FeedbackPattern,
                  feedback_items: List[dict]) -> TuningInstruction:
        """Generate a TuningInstruction from a pattern."""
        import requests as _req

        log.info(f"[TuningGen] Generating tuning for: {pattern.pattern[:60]}")
        reasons = [f.get("reason", "") for f in feedback_items
                   if f.get("item_type") == pattern.item_type and f.get("reason")][:5]
        examples_text = ", ".join(f"'{e}'" for e in pattern.examples[:5])

        # Step 1: Gemini decides WHAT to tune
        tuning_spec = self._gemini_spec(pattern, reasons, examples_text)

        # Step 2: DeepSeek generates the exact change
        before_val, after_val = self._deepseek_generate(pattern, tuning_spec, reasons)

        # Step 3: Claude verifies
        claude_notes = self._claude_verify(pattern, tuning_spec, before_val, after_val)

        ti = TuningInstruction(
            tuning_id=f"tune_{pattern.pattern_id}_{int(time.time())}",
            pattern_id=pattern.pattern_id,
            title=tuning_spec.get("title", f"Fix: {pattern.pattern[:60]}"),
            description=tuning_spec.get("description", pattern.pattern),
            engine_name=pattern.engine_name,
            tuning_type=tuning_spec.get("tuning_type", "filter"),
            target=tuning_spec.get("target", "OffTopicFilter"),
            before_value=before_val,
            after_value=after_val,
            evidence=[f"{f.get('item_type','')}: '{f.get('item_value','')}' — {f.get('reason','')}"
                      for f in feedback_items[:5]],
            status=TuningStatus.PENDING
        )
        log.info(f"[TuningGen] Tuning ready: {ti.tuning_id} ({ti.tuning_type} on {ti.target})")
        return ti

    def _gemini_spec(self, pattern: FeedbackPattern,
                      reasons: List[str], examples_text: str) -> dict:
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return {"title": f"Fix: {pattern.pattern[:60]}",
                    "description": pattern.pattern,
                    "tuning_type": "filter",
                    "target": "OffTopicFilter.GLOBAL_KILL"}

        import requests as _req
        try:
            prompt = f"""An SEO keyword/content engine is producing bad results.
Pattern found: {pattern.pattern}
Affects: {pattern.item_type} items in {pattern.engine_name}
Examples of bad output: {examples_text}
User reasons given: {'; '.join(reasons)}

What specific change would fix this?
Options: filter (add to kill list), prompt_edit (change the AI prompt), parameter (change a number), scoring_rule (add/change scoring logic)

Return JSON:
{{"title":"short fix title","description":"what the fix does and why","tuning_type":"filter|prompt_edit|parameter|scoring_rule","target":"exact function or variable name to change","approach":"what specifically to do"}}"""
            r = _req.post(
                f"{self.GEMINI_URL}?key={key}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.1, "maxOutputTokens": 300}},
                timeout=12
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception as e:
            log.warning(f"Gemini spec failed: {e}")

        return {"title": f"Fix: {pattern.pattern[:60]}",
                "description": pattern.pattern,
                "tuning_type": "filter" if "keyword" in pattern.item_type else "prompt_edit",
                "target": "OffTopicFilter.GLOBAL_KILL",
                "approach": f"Add examples to block list: {examples_text}"}

    def _deepseek_generate(self, pattern: FeedbackPattern, spec: dict,
                            reasons: List[str]) -> Tuple[str, str]:
        """DeepSeek generates the before/after values for the tuning."""
        tuning_type = spec.get("tuning_type", "filter")
        target      = spec.get("target", "OffTopicFilter")
        approach    = spec.get("approach", "")

        if tuning_type == "filter":
            # Extract words from examples that should be added to kill list
            kill_words = []
            for ex in pattern.examples:
                words = ex.lower().split()
                # Find the off-topic word (usually single non-seed word)
                kill_words.extend(w for w in words if len(w) > 3 and
                                  w not in ["with","from","for","and","the","that"])
            kill_words = list(dict.fromkeys(kill_words))[:10]  # dedup, max 10
            before = f"# {target} current list (excerpt)"
            after  = f"# {target} — add these words (from user feedback):\n{json.dumps(kill_words, indent=2)}"
            return before, after

        elif tuning_type == "prompt_edit":
            # Ask DeepSeek to write an improved prompt section
            import requests as _req
            try:
                prompt = f"""Improve this SEO scoring prompt to avoid this problem:
Problem: {pattern.pattern}
Examples of bad output: {', '.join(pattern.examples[:3])}
User complaints: {'; '.join(reasons[:3])}
Approach: {approach}

Write a specific instruction to add to the relevant AI prompt that prevents this issue.
Be specific and technical. 3 sentences maximum.
Return only the instruction text, no explanation."""
                r = _req.post(
                    f"{self.OLLAMA_URL}/api/generate",
                    json={"model": "deepseek-r1:7b", "prompt": prompt,
                          "stream": False, "options": {"num_predict": 200}},
                    timeout=60
                )
                if r.ok:
                    new_instruction = r.json().get("response", "").strip()[:500]
                    before = f"# Prompt for {target} (no specific exclusion rule for this case)"
                    after  = f"# Prompt for {target} — add this rule:\n{new_instruction}"
                    return before, after
            except Exception as e:
                log.warning(f"DeepSeek prompt gen failed: {e}")
            return (f"# Current prompt for {target}",
                    f"# Add rule: avoid {', '.join(pattern.examples[:3])}")

        elif tuning_type == "parameter":
            return (f"# Current parameter: {target}",
                    f"# Suggested change based on feedback pattern: {approach}")

        else:
            return (f"# Current scoring rule for {target}",
                    f"# New rule: penalise items matching: {', '.join(pattern.examples[:5])}")

    def _claude_verify(self, pattern: FeedbackPattern, spec: dict,
                        before: str, after: str) -> dict:
        """Claude verifies the tuning is safe before it goes to approval gate."""
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return {"recommendation": "needs_manual_review",
                    "confidence": 0,
                    "approval_notes": "Claude API not set — review manually"}
        try:
            import anthropic, requests as _req
            client = anthropic.Anthropic(api_key=key)
            r = client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
                max_tokens=500,
                messages=[{"role": "user", "content": f"""Review this SEO algorithm tuning before production.

Pattern being fixed: {pattern.pattern}
Tuning type: {spec.get('tuning_type')}
Target: {spec.get('target')}

Before:
{before[:800]}

After (proposed):
{after[:800]}

Is this tuning:
1. Correctly addressing the user's complaint?
2. Safe — won't break other keyword generation?
3. Proportionate — not too aggressive?

Return JSON: {{"recommendation":"approve|reject|needs_changes","confidence":0-100,"concerns":[],"approval_notes":"what the reviewer needs to know"}}"""}]
            )
            text = r.content[0].text.strip()
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception as e:
            log.warning(f"Claude verify failed: {e}")
        return {"recommendation": "needs_manual_review",
                "confidence": 50,
                "concerns": [],
                "approval_notes": "Manual review required"}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — TUNING APPLICATOR (applies approved tunings to engines)
# ─────────────────────────────────────────────────────────────────────────────

class TuningApplicator:
    """
    Applies an approved TuningInstruction to the actual engine code/config.
    Saves rollback state before applying.
    """
    ENGINES_DIR   = Path(os.getenv("ENGINES_DIR", "./"))
    VERSIONS_DIR  = Path(os.getenv("VERSIONS_DIR", "./rsd_versions"))

    ENGINE_FILES = {
        "20phase_engine":        "ruflo_20phase_engine.py",
        "content_engine":        "ruflo_content_engine.py",
        "seo_audit":             "ruflo_seo_audit.py",
        "confirmation_pipeline": "ruflo_confirmation_pipeline.py",
        "publisher":             "ruflo_publisher.py",
        "annaseo_addons":        "annaseo_addons.py",
    }

    def apply(self, ti: TuningInstruction,
               approved_by: str) -> Tuple[bool, str]:
        """Apply a tuning instruction to the engine. Returns (success, message)."""
        self.VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        engine_file = self.ENGINES_DIR / self.ENGINE_FILES.get(ti.engine_name, "")
        if not engine_file.exists():
            return False, f"Engine file not found: {engine_file}"

        # Save rollback snapshot
        original = engine_file.read_text(encoding="utf-8")
        snap = self.VERSIONS_DIR / f"{ti.engine_name}_qe_{ti.tuning_id}_pre.py"
        snap.write_text(original, encoding="utf-8")

        if ti.tuning_type == "filter":
            success, msg = self._apply_filter(ti, engine_file, original)
        elif ti.tuning_type == "prompt_edit":
            success, msg = self._apply_prompt_edit(ti, engine_file, original)
        else:
            # For parameter/scoring_rule: mark as applied but note manual step
            success = True
            msg = f"Tuning recorded. Manual code change required for {ti.tuning_type}: {ti.target}"

        if success:
            # Update DB
            db = QualityDB()
            db._db.execute(
                "UPDATE qe_tuning_instructions SET status='applied', approved_by=?, approved_at=?, applied_at=?, rollback_value=? WHERE tuning_id=?",
                (approved_by, datetime.utcnow().isoformat(),
                 datetime.utcnow().isoformat(), str(snap), ti.tuning_id)
            )
            db._db.commit()
            log.info(f"[TuningApplicator] Applied: {ti.tuning_id} by {approved_by}")
        return success, msg

    def _apply_filter(self, ti: TuningInstruction, engine_file: Path,
                       original: str) -> Tuple[bool, str]:
        """Add words to OffTopicFilter.GLOBAL_KILL in annaseo_addons.py."""
        try:
            # Extract kill words from after_value
            words = re.findall(r'"([a-zA-Z]{3,})"', ti.after_value)
            if not words:
                return False, "No kill words found in tuning after_value"

            # Find the addons file (where OffTopicFilter is defined)
            addons_file = self.ENGINES_DIR / "annaseo_addons.py"
            if not addons_file.exists():
                return False, "annaseo_addons.py not found"

            code = addons_file.read_text(encoding="utf-8")
            # Find GLOBAL_KILL list and add words
            pattern = r'(GLOBAL_KILL\s*=\s*\[)([^\]]*?)(\])'
            m = re.search(pattern, code, re.DOTALL)
            if m:
                existing = m.group(2)
                new_words_str = "\n        " + "\n        ".join(f'"{w}",' for w in words
                                                                   if f'"{w}"' not in existing)
                new_list = m.group(1) + existing.rstrip() + new_words_str + "\n    " + m.group(3)
                new_code = code[:m.start()] + new_list + code[m.end():]
                addons_file.write_text(new_code, encoding="utf-8")
                return True, f"Added {len(words)} words to OffTopicFilter.GLOBAL_KILL: {words}"
            return False, "Could not find GLOBAL_KILL in annaseo_addons.py"
        except Exception as e:
            return False, str(e)

    def _apply_prompt_edit(self, ti: TuningInstruction, engine_file: Path,
                            original: str) -> Tuple[bool, str]:
        """Append instruction to relevant prompt in engine file."""
        try:
            instruction = ti.after_value.replace("# Prompt for", "").split("\n")[-1].strip()
            if not instruction or len(instruction) < 10:
                return False, "No prompt instruction found in after_value"

            # Append as comment and string fragment near relevant function
            target_func = ti.target.split(".")[0]
            insert_marker = f"# QE-TUNE-{ti.tuning_id[:8]}: {instruction}"
            # Find function and inject after def line
            m = re.search(rf"(def {target_func}[^\n]+\n)", original)
            if m:
                new_code = original[:m.end()] + f"    {insert_marker}\n" + original[m.end():]
                engine_file.write_text(new_code, encoding="utf-8")
                return True, f"Prompt instruction added after {target_func}()"
            return False, f"Function {target_func} not found in engine file"
        except Exception as e:
            return False, str(e)

    def rollback(self, tuning_id: str, rolled_back_by: str) -> Tuple[bool, str]:
        """Rollback a tuning to its pre-change state."""
        db = QualityDB()
        row = db._db.execute(
            "SELECT * FROM qe_tuning_instructions WHERE tuning_id=?", (tuning_id,)
        ).fetchone()
        if not row:
            return False, "Tuning not found"
        ti = dict(row)
        snap = Path(ti.get("rollback_value", ""))
        if not snap.exists():
            return False, "Rollback snapshot not found"
        engine_file = self.ENGINES_DIR / self.ENGINE_FILES.get(ti["engine_name"], "")
        if engine_file.exists():
            engine_file.write_text(snap.read_text(encoding="utf-8"), encoding="utf-8")
        db._db.execute(
            "UPDATE qe_tuning_instructions SET status='rolled_back' WHERE tuning_id=?",
            (tuning_id,)
        )
        db._db.commit()
        log.info(f"[TuningApplicator] Rolled back: {tuning_id} by {rolled_back_by}")
        return True, f"Rolled back tuning {tuning_id}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — QUALITY ENGINE (master controller)
# ─────────────────────────────────────────────────────────────────────────────

class QualityEngine:
    """
    Master Quality Engine.
    Called by Ruflo after each project run completes.

    Job types:
      qe_score_project <project_id>    — score all items from this project
      qe_submit_feedback               — record user good/bad label
      qe_analyse_patterns <project_id> — find patterns in bad feedback
      qe_generate_tuning <pattern_id>  — create tuning instruction
      qe_approve_tuning <tuning_id>    — approve and apply tuning
      qe_reject_tuning <tuning_id>     — reject tuning
      qe_rollback_tuning <tuning_id>   — rollback applied tuning
      qe_dashboard                     — full dashboard state
    """

    def __init__(self):
        self._db      = QualityDB()
        self._ds      = DataStore()
        self._scorer  = AIQualityScorer()
        self._pattern = PatternAnalyser()
        self._tuning  = TuningGenerator()
        self._apply   = TuningApplicator()

    # ── Core jobs ─────────────────────────────────────────────────────────────

    def job_score_project(self, project_id: str,
                           business_context: str = "") -> dict:
        """Score all items from a project run. Call after project completes."""
        items = self._ds.get_items(project_id=project_id, label="unreviewed", limit=200)
        log.info(f"[QualityEngine] Scoring {len(items)} items for {project_id}")

        scores = self._scorer.score_batch(items, business_context)
        low_count = 0
        for qs in scores:
            self._db.save_score(qs)
            if qs.score < 60:
                low_count += 1

        # Update overall record quality score
        avg = sum(s.score for s in scores) / max(len(scores), 1)
        records = self._ds.get_records(project_id=project_id, limit=50)
        for rec in records:
            self._ds.set_quality_score(rec["record_id"], avg)

        log.info(f"[QualityEngine] Scored {len(scores)} items, avg={avg:.1f}, low={low_count}")
        return {
            "project_id":   project_id,
            "items_scored": len(scores),
            "avg_score":    round(avg, 1),
            "low_quality":  low_count,
            "needs_review": low_count,
        }

    def job_submit_feedback(self, item_id: str, project_id: str,
                             label: str, reason: str = "",
                             suggested_fix: str = "") -> dict:
        """
        User submits feedback on one item.
        label: "good" | "bad" | "ignored"
        reason: why it's bad (free text — this is the tuning gold)
        """
        fb = UserFeedback(
            feedback_id=f"fb_{hashlib.md5(f'{item_id}{datetime.utcnow().isoformat()}'.encode()).hexdigest()[:12]}",
            item_id=item_id, project_id=project_id,
            label=label, reason=reason, suggested_fix=suggested_fix
        )
        self._db.save_feedback(fb)
        log.info(f"[QualityEngine] Feedback: {label} on {item_id} — {reason[:50]}")

        # Auto-trigger pattern analysis if we have enough bad feedback
        bad_count = len(self._db.get_bad_feedback(project_id, limit=5))
        if bad_count >= 5 and label == "bad":
            log.info("[QualityEngine] 5+ bad items — auto-triggering pattern analysis")

        return {"feedback_id": fb.feedback_id, "label": label, "recorded": True}

    def job_submit_feedback_batch(self, feedbacks: List[dict]) -> dict:
        """Submit multiple feedback items at once."""
        count = 0
        for fb_data in feedbacks:
            self.job_submit_feedback(
                fb_data["item_id"], fb_data["project_id"],
                fb_data["label"], fb_data.get("reason", ""),
                fb_data.get("suggested_fix", "")
            )
            count += 1
        return {"submitted": count}

    def job_analyse_patterns(self, project_id: str = None) -> dict:
        """Find patterns in bad feedback → create FeedbackPattern records."""
        bad_feedback = self._db.get_bad_feedback(project_id, limit=200)
        if not bad_feedback:
            return {"patterns": 0, "message": "No bad feedback yet"}

        # Get business context from project
        business_context = ""

        patterns = self._pattern.analyse(bad_feedback, business_context)
        for p in patterns:
            self._db.save_pattern(p)

        log.info(f"[QualityEngine] Found {len(patterns)} patterns from {len(bad_feedback)} bad items")
        return {
            "patterns_found": len(patterns),
            "bad_items_analysed": len(bad_feedback),
            "pattern_ids": [p.pattern_id for p in patterns]
        }

    def job_generate_tuning(self, pattern_id: str) -> dict:
        """Generate a TuningInstruction for a specific pattern."""
        row = self._db._db.execute(
            "SELECT * FROM qe_feedback_patterns WHERE pattern_id=?", (pattern_id,)
        ).fetchone()
        if not row:
            return {"success": False, "error": "Pattern not found"}

        p = dict(row)
        pattern = FeedbackPattern(
            pattern_id=p["pattern_id"], pattern=p["pattern"],
            item_type=p["item_type"], engine_name=p["engine_name"],
            examples=json.loads(p.get("examples", "[]")),
            frequency=p["frequency"], severity=p["severity"]
        )
        bad_items = self._db.get_bad_feedback(limit=50)
        # Filter to items matching this pattern's type
        relevant = [f for f in bad_items if f.get("item_type") == pattern.item_type][:20]

        ti = self._tuning.generate(pattern, relevant)
        self._db.save_tuning(ti)

        return {
            "success":    True,
            "tuning_id":  ti.tuning_id,
            "title":      ti.title,
            "tuning_type":ti.tuning_type,
            "target":     ti.target,
            "message":    "Tuning instruction created — awaiting manual approval"
        }

    def job_approve_tuning(self, tuning_id: str, approved_by: str,
                            note: str = "") -> dict:
        """Approve and apply a tuning instruction to the engine."""
        row = self._db._db.execute(
            "SELECT * FROM qe_tuning_instructions WHERE tuning_id=?", (tuning_id,)
        ).fetchone()
        if not row:
            return {"success": False, "error": "Tuning not found"}

        ti_data = dict(row)
        ti = TuningInstruction(
            tuning_id=ti_data["tuning_id"], pattern_id=ti_data["pattern_id"],
            title=ti_data["title"], description=ti_data["description"],
            engine_name=ti_data["engine_name"], tuning_type=ti_data["tuning_type"],
            target=ti_data["target"], before_value=ti_data["before_value"],
            after_value=ti_data["after_value"],
            evidence=json.loads(ti_data.get("evidence", "[]"))
        )
        success, msg = self._apply.apply(ti, approved_by)
        return {"success": success, "message": msg, "tuning_id": tuning_id}

    def job_reject_tuning(self, tuning_id: str, rejected_by: str,
                           reason: str) -> dict:
        self._db._db.execute(
            "UPDATE qe_tuning_instructions SET status='rejected', rejection_reason=?, approved_by=?, approved_at=? WHERE tuning_id=?",
            (reason, rejected_by, datetime.utcnow().isoformat(), tuning_id)
        )
        self._db._db.commit()
        log.info(f"[QualityEngine] Tuning rejected: {tuning_id} — {reason}")
        return {"success": True, "message": "Tuning rejected. No engine changes made."}

    def job_rollback_tuning(self, tuning_id: str,
                             rolled_back_by: str) -> dict:
        ok, msg = self._apply.rollback(tuning_id, rolled_back_by)
        return {"success": ok, "message": msg}

    def job_dashboard(self, project_id: str = None) -> dict:
        """Complete state for the Quality tab in Research & Self Development."""
        stats       = self._db.quality_stats(project_id)
        review_queue= self._db.get_review_queue(project_id, limit=50)
        patterns    = [dict(r) for r in self._db._db.execute(
            "SELECT * FROM qe_feedback_patterns ORDER BY frequency DESC LIMIT 20"
        ).fetchall()]
        pending_tunings = self._db.get_pending_tunings()
        applied_tunings = [dict(r) for r in self._db._db.execute(
            "SELECT * FROM qe_tuning_instructions WHERE status='applied' ORDER BY applied_at DESC LIMIT 10"
        ).fetchall()]

        return {
            "quality_stats":     stats,
            "review_queue":      review_queue,
            "patterns":          patterns,
            "pending_tunings":   pending_tunings,
            "applied_tunings":   applied_tunings,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks
    from pydantic import BaseModel as PM
    from typing import Optional as Opt, List as L

    app = FastAPI(title="AnnaSEO Quality Engine",
                  description="Live data quality scoring, user feedback, algorithm tuning")

    qe = QualityEngine()

    class FeedbackBody(PM):
        item_id:       str
        project_id:    str
        label:         str           # "good" | "bad" | "ignored"
        reason:        str = ""      # why bad (this is gold)
        suggested_fix: str = ""

    class FeedbackBatchBody(PM):
        feedbacks: L[FeedbackBody]

    class ApproveBody(PM):
        approved_by: str
        note:        str = ""

    class RejectBody(PM):
        rejected_by: str
        reason:      str

    @app.get("/api/qe/dashboard", tags=["Quality"])
    def dashboard(project_id: Opt[str] = None):
        """Full quality dashboard for Research & Self Development page."""
        return qe.job_dashboard(project_id)

    @app.post("/api/qe/score/{project_id}", tags=["Quality"])
    def score_project(project_id: str, bg: BackgroundTasks,
                       business_context: str = ""):
        """Score all items from a completed project run. Call after project finishes."""
        bg.add_task(qe.job_score_project, project_id, business_context)
        return {"status": "started", "project_id": project_id}

    @app.get("/api/qe/review-queue", tags=["Quality"])
    def review_queue(project_id: Opt[str] = None, item_type: Opt[str] = None, limit: int = 100):
        """Items needing human review — sorted worst first."""
        return qe._db.get_review_queue(project_id, item_type, limit)

    @app.post("/api/qe/feedback", tags=["Quality"])
    def submit_feedback(body: FeedbackBody):
        """Submit quality feedback for one item. This is the core user input."""
        return qe.job_submit_feedback(
            body.item_id, body.project_id, body.label,
            body.reason, body.suggested_fix
        )

    @app.post("/api/qe/feedback/batch", tags=["Quality"])
    def submit_feedback_batch(body: FeedbackBatchBody):
        """Submit feedback for multiple items at once."""
        return qe.job_submit_feedback_batch([f.dict() for f in body.feedbacks])

    @app.post("/api/qe/analyse/{project_id}", tags=["Quality"])
    def analyse_patterns(project_id: str, bg: BackgroundTasks):
        """Find patterns in bad feedback → create tuning instructions."""
        bg.add_task(qe.job_analyse_patterns, project_id)
        return {"status": "started", "project_id": project_id}

    @app.get("/api/qe/patterns", tags=["Quality"])
    def list_patterns():
        return [dict(r) for r in qe._db._db.execute(
            "SELECT * FROM qe_feedback_patterns ORDER BY frequency DESC"
        ).fetchall()]

    @app.post("/api/qe/patterns/{pattern_id}/tuning", tags=["Quality"])
    def generate_tuning(pattern_id: str, bg: BackgroundTasks):
        """Generate a tuning instruction for a pattern."""
        bg.add_task(qe.job_generate_tuning, pattern_id)
        return {"status": "started", "pattern_id": pattern_id,
                "message": "Tuning generation started — needs approval when done"}

    @app.get("/api/qe/tunings", tags=["Quality"])
    def list_tunings(status: Opt[str] = None):
        if status:
            return [dict(r) for r in qe._db._db.execute(
                "SELECT * FROM qe_tuning_instructions WHERE status=? ORDER BY created_at DESC",
                (status,)
            ).fetchall()]
        return [dict(r) for r in qe._db._db.execute(
            "SELECT * FROM qe_tuning_instructions ORDER BY created_at DESC LIMIT 50"
        ).fetchall()]

    @app.post("/api/qe/tunings/{tuning_id}/approve", tags=["Quality"])
    def approve_tuning(tuning_id: str, body: ApproveBody):
        """MANUAL APPROVAL — apply tuning to engine."""
        return qe.job_approve_tuning(tuning_id, body.approved_by, body.note)

    @app.post("/api/qe/tunings/{tuning_id}/reject", tags=["Quality"])
    def reject_tuning(tuning_id: str, body: RejectBody):
        return qe.job_reject_tuning(tuning_id, body.rejected_by, body.reason)

    @app.post("/api/qe/tunings/{tuning_id}/rollback", tags=["Quality"])
    def rollback_tuning(tuning_id: str, rolled_back_by: str = "admin"):
        return qe.job_rollback_tuning(tuning_id, rolled_back_by)

    @app.get("/api/qe/stats", tags=["Quality"])
    def stats(project_id: Opt[str] = None):
        return qe._db.quality_stats(project_id)

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI + DEMO
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
AnnaSEO Quality Engine
─────────────────────────────────────────────────────────────
Live data quality scoring · User feedback · Algorithm tuning

Usage:
  python annaseo_quality_engine.py demo               # full demo with cinnamon tour example
  python annaseo_quality_engine.py score <project_id> # score all items
  python annaseo_quality_engine.py feedback bad <item_id> <project_id> "<reason>"
  python annaseo_quality_engine.py feedback good <item_id> <project_id>
  python annaseo_quality_engine.py analyse <project_id>
  python annaseo_quality_engine.py tunings            # list pending tunings
  python annaseo_quality_engine.py approve <tuning_id> <your_name>
  python annaseo_quality_engine.py rollback <tuning_id>
  python annaseo_quality_engine.py dashboard          # show quality stats
  python annaseo_quality_engine.py api                # start FastAPI on :8006
"""

    if len(sys.argv) < 2: print(HELP); exit(0)
    cmd = sys.argv[1]
    qe  = QualityEngine()

    if cmd == "demo":
        print("\n  DEMO — Cinnamon tour keyword quality feedback")
        print("  " + "─"*50)

        # 1. Store some results (as if 20phase engine just ran)
        from annaseo_data_store import DataStore, ResultType, store_keyword_universe
        print("\n  Step 1: Storing keyword universe results...")
        rid = store_keyword_universe(
            project_id="proj_demo_cinnamon",
            seed="cinnamon",
            pillars=["cinnamon benefits", "cinnamon tour", "buy cinnamon online",
                     "ceylon vs cassia cinnamon", "cinnamon recipes"],
            clusters=[{"name": "Cinnamon Health", "keywords": ["cinnamon diabetes", "cinnamon blood sugar"]}],
            supporting=["organic cinnamon", "cinnamon price per kg"]
        )
        print(f"  Stored record: {rid}")

        # 2. Score items
        print("\n  Step 2: Scoring items for quality...")
        result = qe.job_score_project("proj_demo_cinnamon", "organic spice business")
        print(f"  Items scored: {result['items_scored']}, avg: {result['avg_score']}, low quality: {result['low_quality']}")

        # 3. User marks "cinnamon tour" as bad
        print("\n  Step 3: User marks 'cinnamon tour' as bad...")
        items = DataStore().get_items(project_id="proj_demo_cinnamon", item_type="pillar_keyword")
        tour_item = next((i for i in items if "tour" in i.get("item_value","").lower()), None)
        if tour_item:
            fb_result = qe.job_submit_feedback(
                item_id=tour_item["item_id"],
                project_id="proj_demo_cinnamon",
                label="bad",
                reason="Tour has nothing to do with spices. This is a tourism keyword, not relevant to our cinnamon business.",
                suggested_fix="Remove 'tour' from pillar keywords. Only product/health/recipe keywords should be pillars."
            )
            print(f"  Feedback recorded: {fb_result}")

        # Add more bad feedback to trigger pattern
        for i, (kw, reason) in enumerate([
            ("cinnamon travel guide", "Travel is not related to spices"),
            ("spice tour Kerala", "Tour is tourism, not spice business"),
        ]):
            fake_item_id = f"item_fake_{i}"
            # Insert directly for demo
            db = qe._db._db
            db.execute("""
                INSERT OR IGNORE INTO ds_result_items
                (item_id, record_id, project_id, result_type, item_type, item_value, item_meta)
                VALUES (?,?,?,?,?,?,?)
            """, (fake_item_id, rid, "proj_demo_cinnamon", "keyword_universe",
                  "pillar_keyword", kw, "{}"))
            db.commit()
            qe.job_submit_feedback(fake_item_id, "proj_demo_cinnamon", "bad", reason)

        # 4. Analyse patterns
        print("\n  Step 4: Analysing patterns in bad feedback...")
        pattern_result = qe.job_analyse_patterns("proj_demo_cinnamon")
        print(f"  Patterns found: {pattern_result.get('patterns_found',0)}")

        # 5. Show dashboard
        print("\n  Step 5: Quality dashboard")
        dash = qe.job_dashboard("proj_demo_cinnamon")
        stats = dash["quality_stats"]
        print(f"  Total items:    {stats['total_items']}")
        print(f"  Good:           {stats['good']}")
        print(f"  Bad:            {stats['bad']}")
        print(f"  Quality rate:   {stats['quality_rate']}%")
        print(f"  Review queue:   {len(dash['review_queue'])} items")
        print(f"  Patterns:       {len(dash['patterns'])}")
        print(f"  Pending tunings:{stats['pending_tunings']}")

        print("\n  Demo complete.")
        print("  Next: run 'python annaseo_quality_engine.py api' and open /api/qe/dashboard")

    elif cmd == "score":
        pid = sys.argv[2] if len(sys.argv) > 2 else "proj_001"
        print(json.dumps(qe.job_score_project(pid), indent=2))

    elif cmd == "feedback":
        if len(sys.argv) < 5:
            print("Usage: feedback bad|good <item_id> <project_id> [reason]"); exit(1)
        label, item_id, project_id = sys.argv[2], sys.argv[3], sys.argv[4]
        reason = sys.argv[5] if len(sys.argv) > 5 else ""
        print(json.dumps(qe.job_submit_feedback(item_id, project_id, label, reason), indent=2))

    elif cmd == "analyse":
        pid = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(qe.job_analyse_patterns(pid), indent=2))

    elif cmd == "tunings":
        tunings = qe._db.get_pending_tunings()
        print(f"\n  {len(tunings)} pending tunings:")
        for t in tunings:
            print(f"  [{t['tuning_type']:12}] {t['tuning_id']} — {t['title'][:60]}")

    elif cmd == "approve":
        if len(sys.argv) < 4: print("Usage: approve <tuning_id> <your_name>"); exit(1)
        print(json.dumps(qe.job_approve_tuning(sys.argv[2], sys.argv[3]), indent=2))

    elif cmd == "rollback":
        if len(sys.argv) < 3: print("Usage: rollback <tuning_id>"); exit(1)
        print(json.dumps(qe.job_rollback_tuning(sys.argv[2], "cli_user"), indent=2))

    elif cmd == "dashboard":
        dash = qe.job_dashboard()
        s = dash["quality_stats"]
        print(f"\n  Quality rate: {s['quality_rate']}% | Good: {s['good']} | Bad: {s['bad']} | Unreviewed: {s['unreviewed']}")
        print(f"  Review queue: {len(dash['review_queue'])} items | Pending tunings: {s['pending_tunings']}")

    elif cmd == "api":
        try:
            import uvicorn
            print("Quality Engine API at http://localhost:8006")
            print("Docs at http://localhost:8006/docs")
            uvicorn.run("annaseo_quality_engine:app", host="0.0.0.0", port=8006, reload=True)
        except ImportError:
            print("pip install uvicorn")
    else:
        print(f"Unknown: {cmd}\n{HELP}")

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class QAIssue:
    type: str
    severity: str
    location: str
    issue: str
    impact: str
    fix: str

    def to_dict(self, idx: int) -> Dict[str, Any]:
        return {
            "id": idx,
            "type": self.type,
            "severity": self.severity,
            "location": self.location,
            "issue": self.issue,
            "impact": self.impact,
            "fix": self.fix,
        }


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _has_any(text: str, tokens: List[str]) -> bool:
    l = (text or "").lower()
    return any(t in l for t in tokens)


def evaluate(capture: Dict[str, Any], previous: Dict[str, Any] | None = None) -> Dict[str, Any]:
    issues: List[QAIssue] = []

    scenario = capture.get("scenario", {})
    ui = capture.get("ui", {})
    api = capture.get("api", {})

    # Some endpoints return wrapped payloads like {"session": {...}} or {"profile": {...}}.
    # Normalize here so QA logic stays stable across API response shapes.
    session_payload = api.get("session", {})
    if isinstance(session_payload, dict) and isinstance(session_payload.get("session"), dict):
        session_payload = session_payload.get("session", {})

    profile_payload = api.get("profile", {})
    if isinstance(profile_payload, dict) and isinstance(profile_payload.get("profile"), dict):
        profile_payload = profile_payload.get("profile", {})

    phase9_ok = bool(session_payload.get("phase9_done"))
    strategy_text = (api.get("strategy_text") or "").strip()
    validated = api.get("validated_keywords") or []
    validated_text = "\n".join(validated)

    if not ui.get("business_saved"):
        issues.append(QAIssue("ui", "critical", "Business Analysis", "Business analysis save/analyze did not complete visibly.", "Flow cannot be trusted from step 1 onward.", "Add explicit success toast + persistent phase1_done badge before allowing next step."))

    if not phase9_ok:
        issues.append(QAIssue("backend", "critical", "API", "Phase 9 did not complete successfully.", "Strategy V2 artifact is missing, blocking end-to-end output validation.", "Fix phase9 prerequisite mismatch for kw3 sessions and add CI e2e test for phase5-9 chain."))

    pillar = (scenario.get("pillar") or "").lower()
    modifier_list = [m.lower() for m in (scenario.get("modifiers") or [])]

    clove_count = sum(1 for kw in validated if pillar and pillar in (kw or "").lower())
    if pillar and clove_count == 0:
        issues.append(QAIssue("data_flow", "high", "Keyword V3", f"No validated keywords include pillar '{pillar}'.", "Pillar intent may be dropped before strategy generation.", "Enforce minimum pillar-presence threshold before phase4 completion."))

    for mod in modifier_list:
        mod_count = sum(1 for kw in validated if mod in (kw or "").lower())
        if mod_count == 0:
            issues.append(QAIssue("data_flow", "high", "Keyword V3", f"No validated keywords include modifier '{mod}'.", "Modifier continuity is broken.", "Boost modifier combinations in generation and keep dedicated modifier retention checks in validation."))

    norm = [_norm(k) for k in validated if k]
    dup_count = len(norm) - len(set(norm))
    if dup_count > 0:
        issues.append(QAIssue("ai", "medium", "Keyword V3", f"Detected {dup_count} normalized duplicate validated keywords.", "Dilutes scoring and cluster quality.", "Run normalized dedup pass before phase4 scoring and expose duplicate metrics in UI."))

    transactional = ["buy", "price", "wholesale", "order", "deal", "bulk"]
    commercial = ["best", "top", "quality", "review", "compare"]
    informational = ["benefits", "uses", "how to", "what is", "guide"]
    geo = ["india", "kerala", "near me"]

    if validated and not _has_any(validated_text, transactional):
        issues.append(QAIssue("ai", "medium", "Keyword V3", "Transactional intent coverage appears weak.", "BOFU opportunities may be underrepresented.", "Require minimum transactional quota in approved keyword set."))
    if validated and not _has_any(validated_text, commercial):
        issues.append(QAIssue("ai", "medium", "Keyword V3", "Commercial intent coverage appears weak.", "Comparison/evaluation queries may be missing.", "Inject commercial expansion templates and verify via intent counters."))
    if validated and not _has_any(validated_text, informational):
        issues.append(QAIssue("ai", "medium", "Keyword V3", "Informational intent coverage appears weak.", "TOFU breadth may be incomplete.", "Add informational expansion patterns and require minimum informational coverage."))
    if validated and not _has_any(validated_text, geo):
        issues.append(QAIssue("ai", "medium", "Keyword V3", "Geo intent coverage appears weak.", "Local relevance may be low.", "Add geo variants from business/target locations and validate geo ratio."))

    if phase9_ok and strategy_text:
        if pillar and pillar not in strategy_text.lower():
            issues.append(QAIssue("data_flow", "high", "Strategy V2", f"Strategy text does not reference pillar '{pillar}'.", "Generated plan may not align with selected pillar.", "Force strategy engine to include explicit pillar sections and validation checks."))
        for mod in modifier_list:
            if mod not in strategy_text.lower():
                issues.append(QAIssue("data_flow", "high", "Strategy V2", f"Strategy text does not reference modifier '{mod}'.", "Modifier context is lost in final plan.", "Pass modifiers as mandatory constraints into strategy prompts and output schema."))

        if not _has_any(strategy_text, ["tofu", "top of funnel"]):
            issues.append(QAIssue("ai", "medium", "Strategy V2", "TOFU stage not detected in strategy output.", "Upper-funnel coverage may be incomplete.", "Add explicit funnel template requiring TOFU/MOFU/BOFU sections."))
        if not _has_any(strategy_text, ["mofu", "middle of funnel"]):
            issues.append(QAIssue("ai", "medium", "Strategy V2", "MOFU stage not detected in strategy output.", "Mid-funnel nurturing may be underdeveloped.", "Require MOFU content mapping in weekly plan schema."))
        if not _has_any(strategy_text, ["bofu", "bottom of funnel", "conversion"]):
            issues.append(QAIssue("ai", "medium", "Strategy V2", "BOFU/conversion stage not clearly detected.", "Conversion-oriented output may be weak.", "Require BOFU offers, CTA paths, and conversion KPIs in strategy template."))

    profile_text = "\n".join(
        [
            str(profile_payload.get("domain", "")),
            str(profile_payload.get("manual_input", "")),
            str(profile_payload.get("raw_ai_json", "")),
        ]
    ).lower()
    domain = (scenario.get("domain") or "").lower()
    competitor = (scenario.get("competitor") or "").lower()

    if domain and domain not in profile_text and domain not in (strategy_text or "").lower():
        issues.append(QAIssue("data_flow", "high", "Business Analysis", f"Domain '{domain}' not found in captured profile/strategy artifacts.", "Domain context may be dropped.", "Persist domain on session snapshot and render in downstream phase headers."))

    competitor_host = competitor.replace("https://", "").replace("http://", "").strip("/")
    if competitor_host and competitor_host not in profile_text and competitor_host not in (strategy_text or "").lower():
        issues.append(QAIssue("data_flow", "high", "Business Analysis", f"Competitor '{competitor_host}' not found in captured profile/strategy artifacts.", "Competitor intelligence may not be used.", "Record competitor usage evidence in phase outputs and strategy insights."))

    js_errors = ui.get("console_errors") or []
    if js_errors:
        issues.append(QAIssue("ui", "medium", "UI", f"Detected {len(js_errors)} browser console error(s).", "UI rendering/interaction may be degraded.", "Treat console errors as build blockers and lint for invalid style declarations."))

    if previous:
        prev_score = int(previous.get("score", 0))
        prev_phase9 = False
        try:
            prev_summary = previous.get("summary_json")
            if isinstance(prev_summary, str):
                import json
                prev_summary = json.loads(prev_summary)
            prev_phase9 = bool((prev_summary or {}).get("phase9_done"))
        except Exception:
            prev_phase9 = False

        if prev_phase9 and not phase9_ok:
            issues.append(QAIssue("backend", "critical", "API", "Regression: previous run had phase9 success, current run failed.", "Indicates behavioral regression after deployment.", "Auto-fail deploy on phase9 regression and diff prerequisite snapshots."))
        if prev_score - (100 - len(issues) * 3) >= 15:
            issues.append(QAIssue("performance", "high", "UI", "Regression: QA score dropped significantly vs last run.", "Release quality trend is degrading.", "Publish score deltas and block release when drop exceeds threshold."))

    critical_count = sum(1 for i in issues if i.severity == "critical")
    major_blockers = sum(1 for i in issues if i.severity in {"critical", "high"})

    score = max(0, 100 - (critical_count * 10) - (major_blockers - critical_count) * 5 - (len(issues) - major_blockers) * 2)

    summary = {
        "system_health": "strong" if score >= 85 else "average" if score >= 70 else "poor",
        "data_flow_integrity": "correct" if not any(i.type == "data_flow" for i in issues) else "partial" if phase9_ok else "broken",
        "major_blockers": major_blockers,
        "score": score,
        "phase9_done": phase9_ok,
        "validated_count": len(validated),
        "clove_count": clove_count,
        "modifier_counts": {
            mod: sum(1 for kw in validated if mod in (kw or "").lower())
            for mod in modifier_list
        },
    }

    return {
        "summary": summary,
        "issues": [iss.to_dict(i + 1) for i, iss in enumerate(issues)],
        "score": score,
        "critical_count": critical_count,
        "major_blockers": major_blockers,
    }

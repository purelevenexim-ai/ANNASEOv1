"""
plot_scorer.py — Story Plot Integration Scoring (0-10 scale).

Scores how well a generated article integrates the active R2 narrative plot
and brand story. Returns a granular breakdown across 5 dimensions.

Dimensions (each 0-2 pts, total 10):
  1. Plot thesis presence & echo (do the plot's ideas surface?)
  2. Distribution (is it woven through, or dumped in one section?)
  3. Brand fact integration (snippets used naturally)
  4. Voice consistency (no name-dropping, no forced superlatives)
  5. Conclusion echo (does the ending tie back to the plot?)

Returns:
  {
    "score": float (0-10),
    "breakdown": { dimension: {"score": float, "max": int, "notes": str}, ... },
    "highlights": [{"sentence": str, "reason": str, "kind": "plot"|"snippet"|"brand"}, ...],
    "issues": [str, ...],
  }
"""
from __future__ import annotations
import re
from typing import Dict, Any, List, Optional


_STOP = {
    "the","a","an","and","or","but","is","are","was","were","be","been","being",
    "of","in","on","at","to","from","by","with","as","for","that","this","it",
    "we","you","i","he","she","they","our","your","their","its","not","no","do",
    "does","did","has","have","had","can","will","would","could","should","may",
    "might","also","about","into","then","than","more","most","very","just","so",
    "what","when","where","which","who","why","how","one","two","three",
}


def _tokens(text: str) -> List[str]:
    if not text:
        return []
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in _STOP]


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "")


def _section_texts(html: str) -> List[str]:
    """Split body HTML by H2 sections; return text-only per section."""
    if not html:
        return []
    sections = re.split(r"<h2[^>]*>", html, flags=re.I)
    out = []
    for sec in sections[1:] if len(sections) > 1 else sections:
        text = _strip_html(sec).strip()
        if len(text) > 100:
            out.append(text)
    return out or [_strip_html(html)]


def score_story_plot(
    body_html: str,
    plot: Optional[Dict[str, Any]] = None,
    snippets: Optional[List[Dict[str, Any]]] = None,
    brand_name: str = "",
    founder_name: str = "",
    region: str = "",
) -> Dict[str, Any]:
    """
    Score story-plot integration on a 0-10 scale.
    """
    body_text = _strip_html(body_html).lower()
    sections = _section_texts(body_html)
    breakdown: Dict[str, Dict[str, Any]] = {}
    highlights: List[Dict[str, str]] = []
    issues: List[str] = []

    # ── 1. Plot thesis presence & echo (0-2) ────────────────────────────────
    plot_score = 0.0
    plot_max = 2
    plot_notes = ""
    if plot and plot.get("thesis"):
        thesis_tokens = set(_tokens(plot["thesis"]))
        title_tokens = set(_tokens(plot.get("title", "")))
        # Score: how many distinct thesis tokens land in the body?
        if thesis_tokens:
            hits = sum(1 for t in thesis_tokens if t in body_text)
            ratio = hits / len(thesis_tokens)
            if ratio >= 0.6:
                plot_score = 2.0
                plot_notes = f"Strong: {hits}/{len(thesis_tokens)} thesis tokens woven in"
            elif ratio >= 0.4:
                plot_score = 1.5
                plot_notes = f"Good: {hits}/{len(thesis_tokens)} thesis tokens"
            elif ratio >= 0.2:
                plot_score = 0.8
                plot_notes = f"Weak: only {hits}/{len(thesis_tokens)} thesis tokens"
                issues.append("Plot thesis only weakly present — strengthen integration")
            else:
                plot_score = 0.2
                plot_notes = f"Missing: only {hits}/{len(thesis_tokens)} thesis tokens"
                issues.append("Plot thesis essentially absent from body")
        # Bonus: title tokens echoed
        if title_tokens and any(t in body_text for t in title_tokens):
            plot_score = min(plot_max, plot_score + 0.3)
        # Find example sentences that carry the plot
        for sent in _split_sentences(_strip_html(body_html))[:80]:
            sl = sent.lower()
            hits_s = sum(1 for t in thesis_tokens if t in sl)
            if hits_s >= 3 and len(sent) < 250:
                highlights.append({"sentence": sent, "reason": "plot-thesis-echo", "kind": "plot"})
                if len(highlights) >= 4:
                    break
    else:
        plot_notes = "No active plot configured"
    breakdown["plot_thesis"] = {"score": round(plot_score, 1), "max": plot_max, "notes": plot_notes}

    # ── 2. Distribution (0-2) ────────────────────────────────────────────────
    dist_score = 0.0
    dist_max = 2
    dist_notes = ""
    if plot and plot.get("thesis") and sections:
        thesis_tokens = set(_tokens(plot["thesis"]))
        if thesis_tokens:
            section_hits = []
            for sec in sections:
                sec_l = sec.lower()
                hits = sum(1 for t in thesis_tokens if t in sec_l)
                section_hits.append(hits >= 2)
            sections_with_plot = sum(section_hits)
            total_secs = len(sections)
            ratio = sections_with_plot / max(1, total_secs)
            if sections_with_plot >= 3 and ratio >= 0.4:
                dist_score = 2.0
                dist_notes = f"Excellent: plot in {sections_with_plot}/{total_secs} sections"
            elif sections_with_plot >= 2:
                dist_score = 1.4
                dist_notes = f"Good: plot in {sections_with_plot}/{total_secs} sections"
            elif sections_with_plot == 1:
                dist_score = 0.6
                dist_notes = f"Concentrated: plot in only {sections_with_plot}/{total_secs} section"
                issues.append("Plot is dumped in a single section — distribute across body")
            else:
                dist_score = 0.0
                dist_notes = "Plot not detectable in any section"
                issues.append("Plot completely absent from body sections")
    else:
        dist_notes = "No plot to distribute"
    breakdown["distribution"] = {"score": round(dist_score, 1), "max": dist_max, "notes": dist_notes}

    # ── 3. Brand fact (snippet) integration (0-2) ────────────────────────────
    snip_score = 0.0
    snip_max = 2
    snip_notes = ""
    snips = snippets or []
    if snips:
        used = 0
        for s in snips:
            s_text = (s.get("text") or "").lower()
            s_tokens = _tokens(s_text)[:8]
            if not s_tokens:
                continue
            hits = sum(1 for t in s_tokens if t in body_text)
            if hits >= max(2, len(s_tokens) // 3):
                used += 1
                # find a sentence that demonstrates it
                for sent in _split_sentences(_strip_html(body_html))[:80]:
                    if sum(1 for t in s_tokens if t in sent.lower()) >= 2 and len(sent) < 250:
                        highlights.append({
                            "sentence": sent,
                            "reason": f"snippet:{s.get('kind','fact')}",
                            "kind": "snippet",
                        })
                        break
        ratio = used / len(snips)
        if used >= 3 and ratio >= 0.4:
            snip_score = 2.0
            snip_notes = f"Strong: {used}/{len(snips)} snippets woven in naturally"
        elif used >= 2:
            snip_score = 1.4
            snip_notes = f"Good: {used}/{len(snips)} snippets used"
        elif used == 1:
            snip_score = 0.6
            snip_notes = f"Light: only {used}/{len(snips)} snippet detectable"
            issues.append("Brand snippets are under-used — weave more naturally")
        else:
            snip_notes = "No brand snippets detectable in body"
            issues.append("Brand snippets completely absent")
    else:
        snip_notes = "No snippets configured"
    breakdown["brand_facts"] = {"score": round(snip_score, 1), "max": snip_max, "notes": snip_notes}

    # ── 4. Voice consistency / no-pitch (0-2) ────────────────────────────────
    voice_score = 2.0
    voice_max = 2
    voice_notes = "Clean"
    bad_patterns = [
        (r"\bbest in the world\b", "superlative: 'best in the world'"),
        (r"\bworld[- ]class\b", "superlative: 'world-class'"),
        (r"\bnumber one\b", "superlative: 'number one'"),
        (r"\b#1\b", "superlative: '#1'"),
        (r"\bunmatched\b", "vague claim: 'unmatched'"),
        (r"\bunbeatable\b", "vague claim: 'unbeatable'"),
        (r"\bsecond to none\b", "cliche: 'second to none'"),
        (r"\bonly one of its kind\b", "vague claim"),
    ]
    flags: list[str] = []
    for pat, reason in bad_patterns:
        if re.search(pat, body_text):
            flags.append(reason)
            voice_score -= 0.5
    # Founder name overuse
    if founder_name:
        fcount = body_text.count(founder_name.lower())
        if fcount > 3:
            voice_score -= 0.6
            flags.append(f"Founder name appears {fcount}x — overused")
            issues.append(f"Founder '{founder_name}' mentioned {fcount}x — should be max 1-2")
    # Region-overload (city + state + country in same sentence)
    if region:
        sentences = _split_sentences(_strip_html(body_html))
        for s in sentences[:50]:
            sl = s.lower()
            if "kerala" in sl and "india" in sl and ("wayanad" in sl or "idukki" in sl or "alleppey" in sl):
                voice_score -= 0.4
                flags.append("Geography stacking: city+state+country in one sentence")
                issues.append("Avoid reciting full geography hierarchy in one line")
                break
    voice_score = max(0.0, voice_score)
    if flags:
        voice_notes = f"Issues: {'; '.join(flags[:3])}"
    breakdown["voice_consistency"] = {"score": round(voice_score, 1), "max": voice_max, "notes": voice_notes}

    # ── 5. Conclusion echo (0-2) ────────────────────────────────────────────
    echo_score = 0.0
    echo_max = 2
    echo_notes = ""
    if plot and plot.get("thesis"):
        # Get last 400 chars of body text (the conclusion area)
        clean_body = _strip_html(body_html)
        conclusion = clean_body[-600:].lower() if len(clean_body) > 600 else clean_body.lower()
        thesis_tokens = set(_tokens(plot["thesis"]))
        title_tokens = set(_tokens(plot.get("title", "")))
        all_plot_tokens = thesis_tokens | title_tokens
        if all_plot_tokens:
            hits = sum(1 for t in all_plot_tokens if t in conclusion)
            ratio = hits / len(all_plot_tokens)
            if ratio >= 0.4:
                echo_score = 2.0
                echo_notes = f"Strong conclusion echo ({hits}/{len(all_plot_tokens)} plot tokens)"
            elif ratio >= 0.2:
                echo_score = 1.2
                echo_notes = f"Some conclusion echo ({hits}/{len(all_plot_tokens)} tokens)"
            else:
                echo_score = 0.3
                echo_notes = "Conclusion does not tie back to plot"
                issues.append("Conclusion should echo the plot title or thesis")
    else:
        echo_notes = "No plot to echo"
    breakdown["conclusion_echo"] = {"score": round(echo_score, 1), "max": echo_max, "notes": echo_notes}

    # ── Heuristic highlights (shown when no plot configured) ────────────────
    # Even without bs_plots data, detect narrative-style sentences so the Story
    # tab shows green highlights immediately.
    if not highlights:
        CONFLICT_MARKERS = [
            "most people", "most buyers", "the problem is", "the mistake",
            "many brands", "common mistake", "often overlooked",
            "here\u2019s why", "here's why", "what most", "the truth is",
        ]
        RESOLUTION_MARKERS = [
            "the difference is", "here\u2019s how", "here's how",
            "the solution", "the answer", "the key is", "what sets",
            "this is why", "that\u2019s why", "that's why",
        ]
        AUTHORITY_MARKERS = [
            "according to", "research shows", "studies suggest",
            "experts say", "traditionally", "for centuries",
            "scientifically", "certified",
        ]
        HOOK_MARKERS = [
            "imagine", "picture this", "consider this", "you\u2019ve probably",
            "you've probably", "have you ever", "when you smell",
        ]
        all_sentences = _split_sentences(_strip_html(body_html))
        for sent in all_sentences[:120]:
            sl = sent.lower()
            if len(sent) < 30 or len(sent) > 300:
                continue
            for m in CONFLICT_MARKERS:
                if m in sl:
                    highlights.append({"sentence": sent, "reason": "narrative-conflict", "kind": "plot"})
                    break
            else:
                for m in RESOLUTION_MARKERS:
                    if m in sl:
                        highlights.append({"sentence": sent, "reason": "narrative-resolution", "kind": "plot"})
                        break
                else:
                    for m in HOOK_MARKERS:
                        if m in sl:
                            highlights.append({"sentence": sent, "reason": "narrative-hook", "kind": "plot"})
                            break
                    else:
                        for m in AUTHORITY_MARKERS:
                            if m in sl:
                                highlights.append({"sentence": sent, "reason": "authority-signal", "kind": "snippet"})
                                break
            if len(highlights) >= 8:
                break

    # ── Total ───────────────────────────────────────────────────────────────
    total = sum(b["score"] for b in breakdown.values())
    return {
        "score": round(total, 1),
        "max": 10,
        "breakdown": breakdown,
        "highlights": highlights[:8],
        "issues": issues,
    }

"""
AI-ness auditor — detects signals that make content look AI-generated.
Uses the same forbidden vocabulary and pattern rules from the review system.
"""
import re
import math
from typing import Dict, List, Tuple
from collections import Counter


# ── Forbidden AI vocabulary (Google SpamBrain signals) ────────────────────────
FORBIDDEN_WORDS = [
    "delve", "crucial", "multifaceted", "landscape", "tapestry", "nuanced",
    "robust", "myriad", "paradigm", "holistic", "pivotal", "leverage",
    "foster", "encompass", "embark", "unleash", "realm", "moreover",
    "furthermore", "additionally", "in conclusion", "it is worth noting",
    "it's important to note", "in today's world", "in the realm of",
    "dive into", "navigating the", "comprehensive guide",
]

# ── Formulaic heading patterns ─────────────────────────────────────────────────
FORMULAIC_HEADING_PATTERNS = [
    r"^understanding\s",
    r"^benefits\s+of\s",
    r"^overview\s+of\s",
    r"^introduction\s+to\s",
    r"^the\s+importance\s+of\s",
    r"^exploring\s",
    r"^a\s+comprehensive\s",
    r"^key\s+(?:factors|considerations|aspects)\s",
]

# ── Generic transition starters ────────────────────────────────────────────────
GENERIC_TRANSITIONS = [
    "furthermore,", "moreover,", "additionally,", "in conclusion,",
    "it is worth noting", "it's important to note", "in today's world",
    "when it comes to", "in the realm of", "it goes without saying",
]


def analyze_ai_signals(html: str) -> Dict:
    """Analyze content for AI-generated signals. Returns a score 0-100 and details."""
    text = re.sub(r'<[^>]+>', ' ', html).strip()
    text_lower = text.lower()
    words = text.split()
    word_count = len(words)

    if word_count < 20:
        return {"score": 100, "signals": [], "summary": "Content too short to analyze"}

    signals = []
    deductions = 0

    # 1. Forbidden vocabulary scan
    forbidden_found = []
    for fw in FORBIDDEN_WORDS:
        count = text_lower.count(fw.lower())
        if count > 0:
            forbidden_found.append({"word": fw, "count": count})
    if forbidden_found:
        deduction = min(len(forbidden_found) * 5, 30)
        deductions += deduction
        signals.append({
            "type": "forbidden_vocabulary",
            "severity": "high" if len(forbidden_found) > 3 else "medium",
            "detail": f"Found {len(forbidden_found)} AI vocabulary words: {', '.join(f['word'] for f in forbidden_found[:8])}",
            "items": forbidden_found,
            "deduction": deduction,
        })

    # 2. Generic transitions
    transitions_found = []
    sentences = re.split(r'[.!?]+', text_lower)
    for sent in sentences:
        sent = sent.strip()
        for gt in GENERIC_TRANSITIONS:
            if sent.startswith(gt):
                transitions_found.append(gt)
    if len(transitions_found) > 2:
        deduction = min((len(transitions_found) - 2) * 5, 20)
        deductions += deduction
        signals.append({
            "type": "generic_transitions",
            "severity": "medium",
            "detail": f"Found {len(transitions_found)} generic transitions (max 2 acceptable): {', '.join(transitions_found[:6])}",
            "deduction": deduction,
        })

    # 3. Formulaic headings
    headings = re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.I | re.S)
    formulaic = []
    for h in headings:
        h_clean = re.sub(r'<[^>]+>', '', h).strip().lower()
        for pat in FORMULAIC_HEADING_PATTERNS:
            if re.match(pat, h_clean, re.I):
                formulaic.append(h_clean)
                break
    if formulaic:
        deduction = min(len(formulaic) * 7, 25)
        deductions += deduction
        signals.append({
            "type": "formulaic_headings",
            "severity": "high",
            "detail": f"{len(formulaic)} formulaic headings: {', '.join(f'"{h}"' for h in formulaic[:5])}",
            "items": formulaic,
            "deduction": deduction,
        })

    # 4. Sentence length uniformity (AI tends to write similar-length sentences)
    sent_lengths = [len(s.split()) for s in sentences if len(s.split()) > 3]
    if len(sent_lengths) > 5:
        avg_len = sum(sent_lengths) / len(sent_lengths)
        variance = sum((l - avg_len) ** 2 for l in sent_lengths) / len(sent_lengths)
        std_dev = math.sqrt(variance)
        cv = std_dev / avg_len if avg_len > 0 else 0
        if cv < 0.25:  # very uniform = likely AI
            deduction = 15
            deductions += deduction
            signals.append({
                "type": "sentence_uniformity",
                "severity": "medium",
                "detail": f"Sentence lengths are very uniform (CV={cv:.2f}). Human writing varies more.",
                "deduction": deduction,
            })

    # 5. Paragraph structure uniformity
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.I | re.S)
    if len(paragraphs) > 4:
        para_lengths = [len(re.sub(r'<[^>]+>', '', p).split()) for p in paragraphs]
        avg_pl = sum(para_lengths) / len(para_lengths) if para_lengths else 0
        if avg_pl > 0:
            para_cv = math.sqrt(sum((l - avg_pl)**2 for l in para_lengths) / len(para_lengths)) / avg_pl
            if para_cv < 0.2:
                deduction = 10
                deductions += deduction
                signals.append({
                    "type": "paragraph_uniformity",
                    "severity": "low",
                    "detail": f"Paragraph lengths are very uniform (CV={para_cv:.2f}). Human writing is more varied.",
                    "deduction": deduction,
                })

    # 6. Tautological conclusion check
    if len(paragraphs) >= 3:
        intro_text = re.sub(r'<[^>]+>', '', paragraphs[0]).lower()
        outro_text = re.sub(r'<[^>]+>', '', paragraphs[-1]).lower()
        intro_words = set(intro_text.split()) - {"the", "a", "an", "is", "are", "in", "of", "to", "and", "for", "with", "this", "that"}
        outro_words = set(outro_text.split()) - {"the", "a", "an", "is", "are", "in", "of", "to", "and", "for", "with", "this", "that"}
        if intro_words and outro_words:
            overlap = len(intro_words & outro_words) / max(len(intro_words), 1)
            if overlap > 0.6:
                deduction = 10
                deductions += deduction
                signals.append({
                    "type": "tautological_conclusion",
                    "severity": "medium",
                    "detail": f"Conclusion repeats {overlap:.0%} of introduction words — lacks new insight.",
                    "deduction": deduction,
                })

    # 7. Vocabulary diversity (type-token ratio)
    if word_count > 50:
        word_tokens = [w.lower().strip('.,!?;:()[]"\'') for w in words if len(w) > 2]
        unique_tokens = set(word_tokens)
        ttr = len(unique_tokens) / len(word_tokens) if word_tokens else 0
        if ttr < 0.35:
            deduction = 10
            deductions += deduction
            signals.append({
                "type": "low_vocabulary_diversity",
                "severity": "medium",
                "detail": f"Type-token ratio {ttr:.2f} is low — content is repetitive.",
                "deduction": deduction,
            })

    score = max(0, 100 - deductions)

    return {
        "score": score,
        "signals": signals,
        "signal_count": len(signals),
        "deductions": deductions,
        "word_count": word_count,
        "summary": (
            "Excellent — reads naturally" if score >= 85 else
            "Good — minor AI signals detected" if score >= 65 else
            "Needs work — multiple AI patterns found" if score >= 40 else
            "High AI detection risk — significant rewriting needed"
        ),
    }

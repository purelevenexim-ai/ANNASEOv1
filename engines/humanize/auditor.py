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

HEDGE_OPINION_MARKERS = [
    "maybe", "perhaps", "might", "probably", "arguably",
    "think", "believe", "feel", "in practice", "from experience",
]

FIRST_PERSON_MARKERS = {"i", "we", "my", "our", "us"}
SECOND_PERSON_MARKERS = {"you", "your"}


def _strip_html(html: str) -> str:
    return re.sub(r'<[^>]+>', ' ', html).strip()


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip().split()) > 2]


def _paragraphs(html: str) -> List[str]:
    return [
        re.sub(r'<[^>]+>', ' ', p).strip()
        for p in re.findall(r'<p[^>]*>(.*?)</p>', html, re.I | re.S)
        if re.sub(r'<[^>]+>', ' ', p).strip()
    ]


def _alpha_tokens(text: str) -> List[str]:
    return re.findall(r"\b[a-zA-Z']+\b", text.lower())


def _repeated_trigram_ratio(tokens: List[str]) -> float:
    if len(tokens) < 3:
        return 0.0
    trigrams = [tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2)]
    counts = Counter(trigrams)
    repeated = sum(count for count in counts.values() if count > 1)
    return repeated / len(trigrams) if trigrams else 0.0


def _compute_detector_metrics(html: str) -> Dict:
    text = _strip_html(html)
    tokens = _alpha_tokens(text)
    sentences = _sentences(text)
    paragraphs = _paragraphs(html)

    sentence_lengths = [len(s.split()) for s in sentences]
    avg_sentence_length = (sum(sentence_lengths) / len(sentence_lengths)) if sentence_lengths else 0.0
    sentence_stddev = math.sqrt(
        sum((length - avg_sentence_length) ** 2 for length in sentence_lengths) / len(sentence_lengths)
    ) if sentence_lengths else 0.0

    openers = [s.split()[0].lower() for s in sentences if s.split()]
    opener_counts = Counter(openers)
    top_opener, top_opener_count = opener_counts.most_common(1)[0] if opener_counts else ("", 0)
    opener_ratio = (top_opener_count / len(openers)) if openers else 0.0

    lexical_diversity = (len(set(tokens)) / len(tokens)) if tokens else 0.0

    para_lengths = [len(p.split()) for p in paragraphs if p.split()]
    para_mean = (sum(para_lengths) / len(para_lengths)) if para_lengths else 0.0
    paragraph_cv = (
        math.sqrt(sum((length - para_mean) ** 2 for length in para_lengths) / len(para_lengths)) / para_mean
    ) if para_lengths and para_mean > 0 else 0.0

    first_person_count = sum(1 for token in tokens if token in FIRST_PERSON_MARKERS)
    second_person_count = sum(1 for token in tokens if token in SECOND_PERSON_MARKERS)
    hedge_opinion_count = sum(text.lower().count(marker) for marker in HEDGE_OPINION_MARKERS)
    trigram_repetition_ratio = _repeated_trigram_ratio(tokens)

    return {
        "word_count": len(text.split()),
        "paragraph_count": len(paragraphs),
        "sentence_count": len(sentences),
        "avg_sentence_length": round(avg_sentence_length, 2),
        "sentence_stddev": round(sentence_stddev, 2),
        "top_sentence_opener": top_opener,
        "top_sentence_opener_ratio": round(opener_ratio, 3),
        "trigram_repetition_ratio": round(trigram_repetition_ratio, 3),
        "lexical_diversity": round(lexical_diversity, 3),
        "paragraph_length_cv": round(paragraph_cv, 3),
        "first_person_count": first_person_count,
        "second_person_count": second_person_count,
        "hedge_opinion_count": hedge_opinion_count,
    }


def _score_detector_variants(metrics: Dict) -> Dict:
    sentence_stddev = metrics["sentence_stddev"]
    lexical_diversity = metrics["lexical_diversity"]
    opener_ratio = metrics["top_sentence_opener_ratio"]
    paragraph_cv = metrics["paragraph_length_cv"]
    hedge_count = metrics["hedge_opinion_count"]
    first_person = metrics["first_person_count"]
    second_person = metrics["second_person_count"]
    trigram_ratio = metrics["trigram_repetition_ratio"]

    gptzero_style = (
        (20 if sentence_stddev < 6 else 0) +
        (20 if lexical_diversity < 0.45 else 0) +
        (15 if opener_ratio > 0.12 else 0) +
        (15 if paragraph_cv < 0.45 else 0) +
        (15 if hedge_count < 5 else 0) +
        (15 if first_person < 2 else 0)
    )
    turnitin_style = (
        (25 if trigram_ratio > 0.05 else 0) +
        (20 if lexical_diversity < 0.45 else 0) +
        (15 if opener_ratio > 0.10 else 0) +
        (15 if sentence_stddev < 6 else 0) +
        (15 if paragraph_cv < 0.45 else 0) +
        (10 if second_person < 3 else 0)
    )
    originality_style = (
        (30 if lexical_diversity < 0.45 else 0) +
        (20 if first_person < 2 else 0) +
        (15 if hedge_count < 5 else 0) +
        (15 if trigram_ratio > 0.05 else 0) +
        (20 if opener_ratio > 0.10 else 0)
    )
    combined_ai_score = round((gptzero_style + turnitin_style + originality_style) / 3)

    if combined_ai_score >= 80:
        risk_level = "high"
    elif combined_ai_score >= 60:
        risk_level = "medium"
    elif combined_ai_score >= 40:
        risk_level = "low"
    else:
        risk_level = "human-like"

    human_quality_score = max(0, 100 - combined_ai_score)
    return {
        "gptzero_style": gptzero_style,
        "turnitin_style": turnitin_style,
        "originality_style": originality_style,
        "combined_ai_score": combined_ai_score,
        "risk_level": risk_level,
        "human_quality_score": human_quality_score,
    }


def _extract_flagged_passages(html: str, metrics: Dict) -> List[Dict]:
    text = _strip_html(html)
    sentences = [s.strip() for s in re.findall(r'[^.!?]+[.!?]?', text) if len(s.strip().split()) >= 5]
    passages: List[Dict] = []
    seen = set()

    top_opener = metrics.get("top_sentence_opener", "")
    opener_ratio = metrics.get("top_sentence_opener_ratio", 0.0)

    def add_passage(snippet: str, issue_type: str, severity: str, reason: str, removable: bool) -> None:
        key = snippet.strip().lower()
        if not snippet or key in seen:
            return
        seen.add(key)
        passages.append({
            "snippet": snippet.strip(),
            "issue_type": issue_type,
            "severity": severity,
            "reason": reason,
            "removable": removable,
        })

    for sentence in sentences:
        lower = sentence.lower()
        forbidden = next((fw for fw in FORBIDDEN_WORDS if fw in lower), None)
        if forbidden:
            add_passage(
                sentence,
                "forbidden_vocabulary",
                "high",
                f"Contains AI-associated phrase '{forbidden}'.",
                True,
            )
            continue

        transition = next((gt for gt in GENERIC_TRANSITIONS if lower.startswith(gt)), None)
        if transition:
            add_passage(
                sentence,
                "generic_transition",
                "medium",
                f"Starts with generic transition '{transition}'.",
                False,
            )
            continue

        if top_opener and opener_ratio > 0.10 and lower.startswith(f"{top_opener} "):
            add_passage(
                sentence,
                "repetitive_opener",
                "medium",
                f"Repeats the common opener '{top_opener}'.",
                False,
            )

    headings = [re.sub(r'<[^>]+>', '', h).strip() for h in re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.I | re.S)]
    for heading in headings:
        h_lower = heading.lower()
        if any(re.match(pattern, h_lower, re.I) for pattern in FORMULAIC_HEADING_PATTERNS):
            add_passage(
                heading,
                "formulaic_heading",
                "high",
                "Formulaic heading pattern that reads templated.",
                True,
            )

    return passages[:12]


def analyze_ai_signals(html: str) -> Dict:
    """Analyze content for AI-generated signals. Returns a score 0-100 and details."""
    text = _strip_html(html)
    text_lower = text.lower()
    words = text.split()
    word_count = len(words)
    detector_metrics = _compute_detector_metrics(html)
    detector_scores = _score_detector_variants(detector_metrics)
    flagged_passages = _extract_flagged_passages(html, detector_metrics)

    if word_count < 20:
        return {
            "score": 100,
            "signals": [],
            "summary": "Content too short to analyze",
            "detector_metrics": detector_metrics,
            "detector_scores": detector_scores,
            "ai_score": detector_scores["combined_ai_score"],
            "risk_level": detector_scores["risk_level"],
            "human_quality_score": detector_scores["human_quality_score"],
            "flagged_passages": flagged_passages,
        }

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

    # 8. Sentence-length burstiness (low variance = AI-flat rhythm)
    if word_count > 100:
        sentence_lengths = [len(s.split()) for s in re.split(r'[.!?]+', re.sub(r'<[^>]+>', ' ', html)) if len(s.split()) >= 4]
        if len(sentence_lengths) >= 5:
            mean_sl = sum(sentence_lengths) / len(sentence_lengths)
            variance = sum((l - mean_sl) ** 2 for l in sentence_lengths) / len(sentence_lengths)
            cv_sl = (variance ** 0.5) / mean_sl if mean_sl > 0 else 0
            if cv_sl < 0.3:
                deduction = 8
                deductions += deduction
                signals.append({
                    "type": "low_sentence_burstiness",
                    "severity": "medium",
                    "detail": f"Sentence-length CV {cv_sl:.2f} is low — all sentences are similar length (AI-flat rhythm).",
                    "deduction": deduction,
                })

    if detector_metrics["top_sentence_opener_ratio"] > 0.10:
        deduction = 8
        deductions += deduction
        signals.append({
            "type": "repeated_sentence_openers",
            "severity": "medium",
            "detail": (
                f"Sentence opener '{detector_metrics['top_sentence_opener']}' repeats in "
                f"{detector_metrics['top_sentence_opener_ratio']:.0%} of sentences."
            ),
            "deduction": deduction,
        })

    if detector_metrics["hedge_opinion_count"] < 3 and detector_metrics["first_person_count"] < 2:
        deduction = 8
        deductions += deduction
        signals.append({
            "type": "low_human_stance",
            "severity": "medium",
            "detail": "Content has very few opinion, hedge, or first-person signals — reads overly neutral and polished.",
            "deduction": deduction,
        })

    score = max(0, 100 - deductions)

    return {
        "score": score,
        "signals": signals,
        "signal_count": len(signals),
        "deductions": deductions,
        "word_count": word_count,
        "detector_metrics": detector_metrics,
        "detector_scores": detector_scores,
        "ai_score": detector_scores["combined_ai_score"],
        "risk_level": detector_scores["risk_level"],
        "human_quality_score": detector_scores["human_quality_score"],
        "flagged_passages": flagged_passages,
        "summary": (
            "Excellent — reads naturally" if score >= 85 else
            "Good — minor AI signals detected" if score >= 65 else
            "Needs work — multiple AI patterns found" if score >= 40 else
            "High AI detection risk — significant rewriting needed"
        ),
    }

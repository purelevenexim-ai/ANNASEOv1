"""
Editorial Engine v3 — Production-grade content quality modules.

Three components:
1. RedundancyKiller — Detects and compresses repeated ideas across sections
2. EditorialValidator — Flags fake authority, unsupported claims, keyword stuffing
3. EditorialRewriter — Full-article editorial pass for human-grade quality
"""
import re
import logging
from typing import Dict, List, Optional
from collections import Counter

log = logging.getLogger("annaseo.humanize.editorial")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. REDUNDANCY KILLER
# ═══════════════════════════════════════════════════════════════════════════════

# Phrases that signal redundant padding
_FILLER_PATTERNS = [
    r"it[''']s\s+important\s+to\s+note\s+that",
    r"it\s+is\s+worth\s+(?:noting|mentioning)\s+that",
    r"this\s+is\s+(?:significant|important)\s+because",
    r"as\s+(?:mentioned|discussed|noted)\s+(?:earlier|above|previously|before)",
    r"(?:in\s+)?conclusion",
    r"to\s+sum(?:marize)?\s+(?:up|it\s+all)",
    r"at\s+the\s+end\s+of\s+the\s+day",
    r"the\s+bottom\s+line\s+is",
    r"all\s+in\s+all",
    r"last\s+but\s+not\s+least",
    r"needless\s+to\s+say",
    r"it\s+goes\s+without\s+saying",
    r"when\s+it\s+comes\s+to",
    r"in\s+(?:today[''']s|the\s+modern)\s+(?:world|era|age|landscape)",
    # AI hook phrases — repetitive paragraph openers flagged in scoring
    r"the\s+real\s+issue\s+is",
    r"and\s+the\s+catch\s+is",
    r"here[''']s\s+the\s+thing",
    r"but\s+here[''']s\s+the\s+thing",
    r"honestly[,\s]+the\s+catch",
    r"here[''']s\s+what[''']s\s+interesting",
    r"the\s+truth\s+is[,\s]",
    r"here[''']s\s+the\s+deal",
    r"let[''']s\s+be\s+honest",
    r"the\s+thing\s+is[,\s]",
]


def detect_redundancy(sections: List[Dict], keyword: str = "") -> Dict:
    """
    Analyze sections for redundant ideas, keyword stuffing, and filler.

    Args:
        sections: List of {content, heading, index} dicts
        keyword: Target SEO keyword

    Returns:
        {
            keyword_density: float,
            keyword_count: int,
            keyword_overuse: bool,
            filler_count: int,
            filler_locations: [{section_index, pattern}],
            repeated_ideas: [{sections: [int, int], similarity: str}],
            compression_targets: [int],  # section indices to compress
        }
    """
    result = {
        "keyword_density": 0.0,
        "keyword_count": 0,
        "keyword_overuse": False,
        "filler_count": 0,
        "filler_locations": [],
        "repeated_ideas": [],
        "compression_targets": [],
    }

    if not sections:
        return result

    # ── Full article text for density calc ──
    all_text = " ".join(
        re.sub(r"<[^>]+>", " ", s.get("content", "")).strip()
        for s in sections
    )
    words = all_text.lower().split()
    word_count = len(words)

    if word_count < 50:
        return result

    # ── Keyword density ──
    if keyword:
        kw_lower = keyword.lower()
        kw_count = all_text.lower().count(kw_lower)
        kw_words = len(kw_lower.split())
        density = (kw_count * kw_words / word_count * 100) if word_count > 0 else 0
        result["keyword_count"] = kw_count
        result["keyword_density"] = round(density, 2)
        result["keyword_overuse"] = density > 2.0 or kw_count > max(8, word_count // 150)

    # ── Filler detection ──
    for si, section in enumerate(sections):
        sec_text = re.sub(r"<[^>]+>", " ", section.get("content", "")).lower()
        for pat in _FILLER_PATTERNS:
            if re.search(pat, sec_text, re.I):
                result["filler_count"] += 1
                result["filler_locations"].append({
                    "section_index": section.get("index", si),
                    "pattern": pat.replace(r"\s+", " ").replace("\\", ""),
                })

    # ── Section similarity (heading-based + content overlap) ──
    sec_key_phrases = []
    for section in sections:
        text = re.sub(r"<[^>]+>", " ", section.get("content", "")).lower()
        # Extract key 3-word phrases (trigrams)
        sec_words = text.split()
        trigrams = set()
        for i in range(len(sec_words) - 2):
            trigram = " ".join(sec_words[i:i+3])
            # Skip trigrams with common stop-words only
            if len(trigram) > 12:
                trigrams.add(trigram)
        sec_key_phrases.append(trigrams)

    # Compare pairs for overlap
    for i in range(len(sec_key_phrases)):
        for j in range(i + 1, len(sec_key_phrases)):
            if not sec_key_phrases[i] or not sec_key_phrases[j]:
                continue
            overlap = sec_key_phrases[i] & sec_key_phrases[j]
            min_size = min(len(sec_key_phrases[i]), len(sec_key_phrases[j]))
            if min_size > 0 and len(overlap) / min_size > 0.15:  # >15% trigram overlap
                result["repeated_ideas"].append({
                    "sections": [sections[i].get("index", i), sections[j].get("index", j)],
                    "similarity": f"{len(overlap)} shared phrases ({round(len(overlap)/min_size*100)}%)",
                })

    # Build compression targets: sections with high filler or redundancy
    filler_sections = set(f["section_index"] for f in result["filler_locations"])
    redundant_sections = set()
    for ri in result["repeated_ideas"]:
        # Second section in each pair is the redundant one
        redundant_sections.add(ri["sections"][1])
    result["compression_targets"] = sorted(filler_sections | redundant_sections)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. EDITORIAL VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════════

# Fake authority patterns — vague claims without named sources
# NOTE: Experience phrases (we tested, in our experience, we found) are ALLOWED
# for E-E-A-T scoring (R36). Only flag truly unsourced vague citations.
_FAKE_AUTHORITY = [
    (r"according\s+to\s+recent\s+(?:research|studies|data)", "Vague citation: name the source or remove"),
    (r"(?<!\w\s)research\s+shows\s+that", "Vague citation: 'research shows' — cite specific research"),
    (r"(?<!\w\s)studies\s+(?:show|suggest|indicate)", "Vague citation: name the study or remove"),
    (r"(?<!\w\s)data\s+(?:shows|suggests|indicates)", "Vague citation: name the data source or remove"),
    (r"evidence\s+suggests", "Vague citation: specify what evidence"),
    (r"experts\s+(?:say|agree|recommend)", "Vague authority: name the expert or remove"),
    (r"our\s+team\s+found\s+that", "Vague: specify who, what was tested, sample size, and when"),
    (r"in\s+our\s+tests\b", "Vague: specify sample size, methodology, and what was tested"),
]
_FORCED_CTA = [
    (r"explore\s+(?:our|mama[''']s|the)\s+(?:wide\s+)?range", "Forced CTA: 'explore our range' — sounds like hidden advertising"),
    (r"contact\s+(?:us|mama|them)\s+directly", "Forced CTA: direct sales pitch breaks editorial tone"),
    (r"visit\s+(?:our|the)\s+(?:website|store|shop)", "Forced CTA: direct sales pitch"),
    (r"order\s+(?:now|today|yours)", "Forced CTA: aggressive sales language"),
    (r"shop\s+(?:now|today|our)", "Forced CTA: sales pitch in editorial content"),
]

# Robotic phrasing patterns
# NOTE: "you might wonder", "picture this", "imagine" are ALLOWED for
# R64 (implicit questions) and R41 (storytelling/engagement) scoring.
_ROBOTIC_PATTERNS = [
    (r"think\s+about\s+it", "Template phrase: 'think about it' — filler"),
    (r"let[''']s\s+face\s+it", "Template phrase: 'let's face it' — cliché"),
    (r"let[''']s\s+(?:dive|explore|look)\s+(?:in|into|at)", "Template phrase: 'let's dive in' — AI cliché"),
    (r"the\s+fact\s+of\s+the\s+matter", "Template phrase: wordy filler"),
    (r"in\s+today[''']s\s+(?:world|era|age|market)", "Template phrase: generic temporal reference"),
    (r"it[''']s\s+no\s+secret\s+that", "Template phrase: filler"),
    (r"there[''']s\s+no\s+denying\s+that", "Template phrase: filler"),
    (r"at\s+its\s+core", "Template phrase: vague abstraction"),
    (r"without\s+further\s+ado", "Template phrase: AI cliché"),
    (r"buckle\s+up", "Template phrase: AI cliché"),
    (r"game[\s-]?changer", "Template phrase: overused"),
    (r"(?:a\s+)?world\s+where", "Template phrase: AI opening cliché"),
    (r"revolutioniz(?:e|ing)", "Template phrase: hyperbolic"),
    (r"unlock(?:ing)?\s+the\s+(?:power|potential|secrets?)", "Template phrase: AI marketing cliché"),
    (r"navigate\s+the\s+(?:complex|ever)", "Template phrase: AI padding"),
    (r"stands?\s+out\s+(?:as\s+a|from\s+the)", "Template phrase: generic praise"),
    (r"it[''']s\s+clear\s+that", "Template phrase: AI filler"),
    (r"the\s+landscape\s+of", "Template phrase: vague abstraction"),
    (r"seamless(?:ly)?", "Template phrase: overused AI adjective"),
    (r"(?:harness|leverage|utilize)\s+the\s+power", "Template phrase: corporate AI cliché"),
    (r"a\s+(?:comprehensive|holistic)\s+(?:approach|guide|overview)", "Template phrase: AI structure cliché"),
    (r"in\s+(?:this|the)\s+(?:ever-evolving|rapidly\s+changing)", "Template phrase: AI temporal cliché"),
]


def validate_editorial(html: str, keyword: str = "") -> Dict:
    """
    Run editorial validation on full article HTML.

    Returns:
        {
            score: int (0-100),
            issues: [{type, severity, detail, line_hint}],
            fake_authority_count: int,
            forced_cta_count: int,
            robotic_count: int,
            keyword_stuffing: bool,
        }
    """
    text = re.sub(r"<[^>]+>", " ", html).strip()
    text_lower = text.lower()
    words = text.split()
    word_count = len(words)

    issues = []
    deductions = 0

    # ── Fake authority check ──
    fake_auth_count = 0
    for pattern, detail in _FAKE_AUTHORITY:
        matches = re.findall(pattern, text_lower)
        if matches:
            fake_auth_count += len(matches)
            issues.append({
                "type": "fake_authority",
                "severity": "high",
                "detail": detail,
                "count": len(matches),
            })
    if fake_auth_count > 0:
        deductions += min(fake_auth_count * 5, 25)

    # ── Forced CTA check ──
    cta_count = 0
    for pattern, detail in _FORCED_CTA:
        matches = re.findall(pattern, text_lower)
        if matches:
            cta_count += len(matches)
            issues.append({
                "type": "forced_cta",
                "severity": "medium",
                "detail": detail,
                "count": len(matches),
            })
    if cta_count > 2:
        deductions += min((cta_count - 1) * 5, 15)

    # ── Robotic phrasing check ──
    robotic_count = 0
    for pattern, detail in _ROBOTIC_PATTERNS:
        matches = re.findall(pattern, text_lower)
        if matches:
            robotic_count += len(matches)
            issues.append({
                "type": "robotic_phrasing",
                "severity": "medium",
                "detail": detail,
                "count": len(matches),
            })
    if robotic_count > 0:
        deductions += min(robotic_count * 3, 20)

    # ── Keyword stuffing check ──
    keyword_stuffing = False
    if keyword and word_count > 100:
        kw_lower = keyword.lower()
        kw_count = text_lower.count(kw_lower)
        kw_words = len(kw_lower.split())
        density = (kw_count * kw_words / word_count * 100) if word_count > 0 else 0
        if density > 2.5 or kw_count > word_count // 100:
            keyword_stuffing = True
            deductions += 15
            issues.append({
                "type": "keyword_stuffing",
                "severity": "critical",
                "detail": f"Keyword '{keyword}' appears {kw_count} times (density {density:.1f}%) — maximum should be {word_count // 200}-{word_count // 150} times",
                "count": kw_count,
            })

    # ── Sentence variety check ──
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.split()) >= 3]
    if len(sentences) > 8:
        lens = [len(s.split()) for s in sentences]
        # Check for runs of 3+ same-length sentences (within 3 words)
        runs = 0
        for i in range(len(lens) - 2):
            if abs(lens[i] - lens[i+1]) <= 3 and abs(lens[i+1] - lens[i+2]) <= 3:
                runs += 1
        if runs > 3:
            deductions += 10
            issues.append({
                "type": "monotonous_rhythm",
                "severity": "medium",
                "detail": f"{runs} groups of 3+ same-length sentences — vary sentence rhythm",
                "count": runs,
            })

    score = max(0, 100 - deductions)

    return {
        "score": score,
        "issues": issues,
        "fake_authority_count": fake_auth_count,
        "forced_cta_count": cta_count,
        "robotic_count": robotic_count,
        "keyword_stuffing": keyword_stuffing,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EDITORIAL REWRITER (LLM-powered full-article pass)
# ═══════════════════════════════════════════════════════════════════════════════

_EDITORIAL_REWRITE_PROMPT = """You are a senior editor at a major publication. This article needs an editorial pass to make it read like real human-written content — NOT AI content, NOT SEO spam.

KEYWORD: {keyword}

━━━ EDITORIAL ISSUES FOUND ━━━
{issues_text}

━━━ MANDATORY FIXES ━━━

1. KEYWORD DENSITY:
   - The keyword "{keyword}" should appear naturally throughout — target 1.0-1.5% density
   - If density is ABOVE 2.0%, reduce excess by replacing some with natural alternatives: pronouns ("these", "this"), partial matches, related terms
   - If density is BELOW 0.8%, do NOT reduce further — SEO requires adequate keyword presence
   - Never remove ALL keyword mentions from any section

2. FAKE AUTHORITY (remove only vague or unsupported claims):
    - Keep named sources and specific observations
    - "research shows" / "studies suggest" / "experts say" → name the source or rewrite directly
    - "according to recent studies" → name the study or remove
    - Keep "we tested" / "in our experience" only when followed by a concrete, specific observation

3. ROBOTIC PHRASING (rewrite ALL of these):
   - "let's dive in" / "let's explore" → delete entirely
   - "in today's world" → delete or be specific about what changed
   - "it's important to note" → just say the thing
   - "needless to say" / "it goes without saying" → delete
   NOTE: Keep these — they score for E-E-A-T and content quality:
   - "you might wonder" / "you may ask" → these are fine, keep as-is (scores implicit questions)
   - "picture this" / "imagine" / "here's what happened" → keep as narrative hooks (scores storytelling)
   - "we tested" / "in our experience" / "we found" → keep with specific follow-up (scores experience)

4. REDUNDANCY:
   - If two sections cover the same idea, merge or cut the weaker one
   - Remove filler paragraphs that don't add new information
   - Compress bloated explanations — say it once, well

5. HUMAN VOICE:
   - Use contractions (don't, it's, won't)
   - Mix sentence lengths dramatically: 4-word punches next to 25-word explanations
   - Include slight opinion: "honestly", "the real issue is", "what most people miss"
   - Start some sentences with "And", "But", "So"
   - Be specific: real prices, real places, real numbers — not vague claims

6. CTA SOFTENING:
   - Remove aggressive sales language ("shop now", "order today", "explore our range")
   - Keep at most 1 natural CTA at the end — make it helpful, not pushy

━━━ RULES ━━━
- Preserve ALL HTML structure, headings, links, tables
- Do NOT add new sections or headings
- Do NOT expand word count — compress by 10-20% if anything
- Output complete HTML article — no commentary, no fences

━━━ ARTICLE ━━━
{article_html}"""


_CHUNK_CHAR_LIMIT = 10_000  # safe per-chunk prompt payload
_CHUNK_TRIGGER = 12_000    # switch to chunked mode above this size


def _split_html_sections(html: str) -> list:
    """Split HTML on <h2> boundaries, grouping sections to stay under _CHUNK_CHAR_LIMIT chars."""
    parts = re.split(r"(?=<h2[\s>])", html, flags=re.IGNORECASE)
    chunks, current = [], ""
    for part in parts:
        if len(current) + len(part) > _CHUNK_CHAR_LIMIT and current:
            chunks.append(current)
            current = part
        else:
            current += part
    if current:
        chunks.append(current)
    return chunks or [html]


def build_editorial_prompt(
    html: str,
    keyword: str,
    validation_result: Dict = None,
) -> str:
    """Build an editorial rewrite prompt from validation issues."""
    issues_text = "(No specific issues — general editorial polish needed)"
    if validation_result and validation_result.get("issues"):
        lines = []
        for issue in validation_result["issues"]:
            severity = issue.get("severity", "medium").upper()
            lines.append(f"[{severity}] {issue['detail']}")
        issues_text = "\n".join(lines)

    # Truncate article for LLM context limits
    article_html = html[:16000]

    return _EDITORIAL_REWRITE_PROMPT.format(
        keyword=keyword,
        issues_text=issues_text,
        article_html=article_html,
    )


def editorial_rewrite(
    html: str,
    keyword: str,
    validation_result: Dict = None,
    ai_router=None,
) -> Dict:
    """
    Run a full-article editorial rewrite pass.
    Articles longer than _CHUNK_TRIGGER chars are automatically chunked by h2 section.

    Returns:
        {success, html, tokens, error}
    """
    if not html or len(html) < 200:
        return {"success": False, "html": html, "tokens": 0, "error": "Article too short"}

    # Auto-delegate to chunked rewrite for long articles to avoid 413 errors
    if len(html) > _CHUNK_TRIGGER:
        return _editorial_rewrite_chunked(html, keyword, validation_result, ai_router)

    return _editorial_rewrite_single(html, keyword, validation_result, ai_router)


def _editorial_rewrite_chunked(
    html: str,
    keyword: str,
    validation_result: Dict = None,
    ai_router=None,
) -> Dict:
    """Rewrite a long article section-by-section to stay under API payload limits."""
    chunks = _split_html_sections(html)
    if len(chunks) == 1:
        # Fell back — article didn't split cleanly; rewrite whole with truncation
        return _editorial_rewrite_single(html, keyword, validation_result, ai_router)

    log.info(f"Editorial chunked rewrite: {len(chunks)} chunks for {len(html)}-char article")
    rewritten_chunks, total_tokens = [], 0
    for i, chunk in enumerate(chunks):
        result = _editorial_rewrite_single(
            chunk, keyword,
            validation_result if i == 0 else None,  # issues only needed on first chunk
            ai_router,
        )
        if result.get("success") and result.get("html"):
            rewritten_chunks.append(result["html"])
            total_tokens += result.get("tokens", 0)
        else:
            log.warning(f"Editorial chunk {i+1}/{len(chunks)} failed — keeping original: {result.get('error')}")
            rewritten_chunks.append(chunk)

    merged = "\n".join(rewritten_chunks)
    orig_wc = len(re.sub(r"<[^>]+>", " ", html).split())
    new_wc  = len(re.sub(r"<[^>]+>", " ", merged).split())
    if new_wc < orig_wc * 0.5:
        return {"success": False, "html": html, "tokens": total_tokens,
                "error": f"Chunked output too short ({new_wc}w vs {orig_wc}w)"}
    return {"success": True, "html": merged, "tokens": total_tokens}


def _editorial_rewrite_single(
    html: str,
    keyword: str,
    validation_result: Dict = None,
    ai_router=None,
) -> Dict:
    """Inner single-chunk rewrite — called by both editorial_rewrite and the chunked variant."""
    prompt = build_editorial_prompt(html, keyword, validation_result)
    try:
        if ai_router is None:
            from core.ai_config import AIRouter
            ai_router = AIRouter
        text, tokens = ai_router.call_with_tokens(
            prompt,
            system="You are a senior publication editor. Return only improved HTML.",
            temperature=0.5,
        )
        if not text or not text.strip():
            return {"success": False, "html": html, "tokens": 0, "error": "Empty response from editorial rewrite"}
        text = re.sub(r"^```(?:html)?\s*", "", text.strip())
        text = re.sub(r"\s*```\s*$", "", text.strip())
        orig_wc = len(re.sub(r"<[^>]+>", " ", html).split())
        new_wc  = len(re.sub(r"<[^>]+>", " ", text).split())
        if new_wc < orig_wc * 0.5:
            log.warning(f"Editorial rewrite too short ({new_wc}w vs {orig_wc}w) — rejected")
            return {"success": False, "html": html, "tokens": tokens,
                    "error": f"Output too short ({new_wc}w vs {orig_wc}w)"}
        return {"success": True, "html": text.strip(), "tokens": tokens}
    except Exception as e:
        log.error(f"Editorial rewrite failed: {e}")
        return {"success": False, "html": html, "tokens": 0, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. KEYWORD DENSITY NORMALIZER (rule-based, no LLM needed)
# ═══════════════════════════════════════════════════════════════════════════════

def _inject_keyword_floor(html: str, keyword: str, needed: int) -> str:
    """
    Re-inject keyword mentions into paragraphs that lack them.
    Targets the longest paragraphs without any mention,
    appending a natural sentence that includes the keyword.
    """
    kw_lower = keyword.lower()
    kw_title = keyword.title()
    paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))
    if not paras:
        return html

    # Find paragraphs WITHOUT keyword (skip first and last)
    candidates = []
    for i, m in enumerate(paras):
        if i < 1 or i >= len(paras) - 1:
            continue
        para_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if kw_lower not in para_text.lower() and len(para_text.split()) >= 20:
            candidates.append((i, len(para_text.split())))

    # Sort by word count descending — inject into longest paragraphs first
    candidates.sort(key=lambda x: x[1], reverse=True)

    templates = [
        f" This is particularly relevant when evaluating {kw_title}.",
        f" The quality of {kw_title} makes a measurable difference here.",
        f" When choosing {kw_title}, this factor matters most.",
        f" This consideration applies directly to {kw_title} purchases.",
        f" For {kw_title} specifically, this point deserves attention.",
    ]

    injected = 0
    for para_index, _ in candidates:
        if injected >= needed:
            break
        paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))
        if para_index < 0 or para_index >= len(paras):
            continue
        m = paras[para_index]
        para_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if kw_lower in para_text.lower() or len(para_text.split()) < 20:
            continue
        para_content = m.group(2)
        insert = templates[injected % len(templates)]
        new_para = m.group(1) + para_content + insert + m.group(3)
        html = html[:m.start()] + new_para + html[m.end():]
        injected += 1

    if injected > 0:
        log.info(f"Keyword floor: injected {injected} mentions of '{keyword}' (density was too low)")
    return html


def normalize_keyword_density(
    html: str,
    keyword: str,
    max_density: float = 1.8,
    min_density: float = 0.8,
    min_occurrences: int = 3,
) -> str:
    """
    Normalize keyword density — both ceiling (reduce excess) and floor (restore if too low).
    Rule-based — no LLM call needed.

    Ceiling: Keeps the first `min_occurrences` and last 1, replaces middle excess.
    Floor: Re-injects keyword into paragraphs that lack it when density is too low.
    """
    if not keyword or not html:
        return html

    kw_lower = keyword.lower()
    text_only = re.sub(r"<[^>]+>", " ", html)
    words = text_only.split()
    word_count = len(words)

    if word_count < 100:
        return html

    kw_count = text_only.lower().count(kw_lower)
    kw_words = len(kw_lower.split())
    density = (kw_count * kw_words / word_count * 100) if word_count > 0 else 0

    # ── FLOOR enforcement: restore keywords if density is too low ─────────
    if density < min_density and kw_count < min_occurrences + 2:
        target_count = max(min_occurrences + 2, int(word_count * min_density / 100 / max(kw_words, 1)))
        needed = target_count - kw_count
        if needed > 0:
            html = _inject_keyword_floor(html, keyword, needed)
            # Recalculate after injection
            text_only = re.sub(r"<[^>]+>", " ", html)
            kw_count = text_only.lower().count(kw_lower)
            density = (kw_count * kw_words / len(text_only.split()) * 100) if len(text_only.split()) > 0 else 0

    # ── CEILING enforcement: reduce if too high ───────────────────────────
    if density <= max_density and kw_count <= max(min_occurrences + 2, word_count // 200):
        return html  # Already acceptable

    # Build natural replacements
    kw_parts = keyword.split()
    replacements = []
    if len(kw_parts) >= 3:
        replacements.extend([
            " ".join(kw_parts[:2]),  # first two words
            " ".join(kw_parts[1:]),  # last words
            "these " + kw_parts[-1] if kw_parts[-1][-1] == "s" else "this",
            "such options",
            "these products",
        ])
    elif len(kw_parts) == 2:
        replacements.extend([
            kw_parts[0],
            kw_parts[1],
            "these",
            "such options",
        ])
    else:
        replacements.extend(["these", "this", "such products", "the right option"])

    # Find all keyword positions (case-insensitive, outside tags)
    positions = []
    _search_text = html.lower()
    _pos = 0
    while True:
        idx = _search_text.find(kw_lower, _pos)
        if idx == -1:
            break
        # Check if inside an HTML tag (rough check)
        last_open = html.rfind("<", 0, idx)
        last_close = html.rfind(">", 0, idx)
        in_tag = last_open > last_close  # inside a tag
        # Check if inside href or alt attr
        in_attr = "href=" in html[max(0, idx-30):idx] or "alt=" in html[max(0, idx-30):idx]
        if not in_tag and not in_attr:
            positions.append(idx)
        _pos = idx + 1

    if len(positions) <= min_occurrences:
        return html

    # Keep first min_occurrences and last 1, replace the rest
    keep_indices = set(range(min_occurrences))
    keep_indices.add(len(positions) - 1)
    replace_positions = [p for i, p in enumerate(positions) if i not in keep_indices]

    # Replace from end to start to preserve positions
    result = html
    rep_idx = 0
    for pos in sorted(replace_positions, reverse=True):
        replacement = replacements[rep_idx % len(replacements)]
        rep_idx += 1
        # Match the original case
        orig = result[pos:pos + len(keyword)]
        if orig[0].isupper():
            replacement = replacement[0].upper() + replacement[1:]
        result = result[:pos] + replacement + result[pos + len(keyword):]

    return result

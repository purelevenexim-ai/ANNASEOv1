"""
74-rule content quality checker across 15 pillars (202 pts total),
normalised to a 0-100 percentage in the output.

Pillars 1-9:   Original 46 rules (136 pts)
Pillar 10:     Conversion & Persuasion (15 pts, R47-R53)
Pillar 11:     AI Humanization (12 pts, R54-R59)
Pillar 12:     Semantic Depth (12 pts, R60-R64)
Pillar 13:     Customer Context (12 pts, R65-R69)
Pillar 14:     Snippet Optimization (10 pts, R70-R73)
Pillar 15:     Numeric Consistency (5 pts, R74)

Provides check_all_rules() used by content_scorer.py and the generation engine.
"""
import re
import logging
from collections import Counter
from typing import Dict, Optional

log = logging.getLogger("annaseo.quality")


def check_all_rules(
    body_html: str,
    keyword: str,
    title: str,
    meta_title: str = "",
    meta_desc: str = "",
    page_type: str = "article",
    *,
    brand_name: str = "",
    business_type: str = "",
    target_locations: str = "",
    target_audience: str = "",
    customer_url: str = "",
    quality_profile: Optional[Dict] = None,
) -> dict:
    """
    Run quality rules on HTML content.

    Returns:
        score, percentage, total_earned, max_possible,
        categories, issues, rules, pillars, summary,
        word_count, kw_density
    """
    text = re.sub(r"<[^>]+>", " ", body_html)
    text = re.sub(r"\s+", " ", text).strip()
    text_lower = text.lower()
    words = text.split()
    word_count = len(words)
    kw_lower = (keyword or "").lower()

    issues: list = []
    rules: list = []

    def rule(rule_id, name, pillar, points_earned, points_max, passed,
             issue_sev=None, issue_msg=None, issue_fix=None):
        rules.append({
            "rule_id": rule_id,
            "name": name,
            "pillar": pillar,
            "passed": passed,
            "points_earned": points_earned,
            "points_max": points_max,
        })
        if not passed and issue_sev and issue_msg:
            issues.append({
                "rule": rule_id,
                "severity": issue_sev,
                "message": issue_msg,
                "fix": issue_fix or "",
                "category": pillar,
                "description": issue_msg,
            })
        return points_earned

    # ── Pre-compute commonly reused values ────────────────────────────────────
    h2_count = len(re.findall(r"<h2", body_html, re.I))
    h3_count = len(re.findall(r"<h3", body_html, re.I))
    has_table = "<table" in body_html.lower()
    has_ul = "<ul" in body_html.lower()
    has_ol = "<ol" in body_html.lower()
    has_faq = bool(re.search(r"frequently asked|<h2[^>]*>.*?faq.*?</h2>", body_html, re.I))
    external_a = len(re.findall(r'href="http', body_html))
    internal_a = len(re.findall(r'href="/', body_html))
    # Also count absolute links to customer's own domain as internal
    if customer_url:
        _cu = customer_url.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
        if _cu:
            abs_internal = len(re.findall(r'href="https?://(?:www\.)?' + re.escape(_cu), body_html, re.I))
            internal_a += abs_internal
            external_a -= abs_internal  # don't double-count as external
            external_a = max(external_a, 0)
    wiki_links = len(re.findall(r"wikipedia\.org", body_html, re.I))

    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    sent_count = max(len(sentences), 1)

    first_p = None
    for _fp_match in re.finditer(r"<p[^>]*>(.*?)</p>", body_html, re.I | re.DOTALL):
        _fp_text = re.sub(r"<[^>]+>", "", _fp_match.group(1)).strip()
        if len(_fp_text.split()) >= 25:
            first_p = _fp_match
            break
    first_p_text = re.sub(r"<[^>]+>", "", first_p.group(1)).strip() if first_p else ""
    first_p_words = len(first_p_text.split())
    first_p_has_kw = any(w in first_p_text.lower() for w in kw_lower.split() if len(w) > 3) if kw_lower else True

    kw_count = text_lower.count(kw_lower) if kw_lower else 0
    kw_word_len = len(kw_lower.split()) if kw_lower else 1
    # Density = (occurrences × words-in-phrase) / total-words × 100
    # For multi-word keywords, count each occurrence as occupying kw_word_len words
    # but apply a fairness floor: treat the density as if the phrase were 1 word
    # so "best black pepper" appearing 8× in 2000 words = 8/2000 × 100 = 0.4%
    # raw density = 8×3/2000 = 1.2%, fair density = max(raw/kw_word_len, raw×0.6)
    raw_density = (kw_count * kw_word_len / word_count * 100) if (word_count > 0 and kw_lower) else 0.0
    # For scoring purposes, use per-phrase density (treats phrase as single unit)
    kw_density = (kw_count / word_count * 100) if (word_count > 0 and kw_lower) else 0.0
    # But for display/normalization pass the raw density
    kw_density_raw = raw_density

    # ── Runtime quality profile (blueprint-aligned thresholds) ───────────────
    qp = quality_profile or {}

    wc_cfg = qp.get("word_count", {}) if isinstance(qp, dict) else {}
    wc_target = int(wc_cfg.get("target", 2200) or 2200)
    wc_soft_min = int(wc_cfg.get("soft_min", 1800) or 1800)
    wc_hard_min = int(wc_cfg.get("hard_min", 2000) or 2000)

    struct_cfg = qp.get("structure", {}) if isinstance(qp, dict) else {}
    h2_min_req = int(struct_cfg.get("h2_min", 6) or 6)
    h3_min_req = int(struct_cfg.get("h3_min", 4) or 4)
    faq_required = bool(struct_cfg.get("faq_required", True))

    link_cfg = qp.get("links", {}) if isinstance(qp, dict) else {}
    internal_min_req = int(link_cfg.get("internal_min", 4) or 4)
    external_min_req = int(link_cfg.get("external_min", 3) or 3)
    wikipedia_min_req = int(link_cfg.get("wikipedia_min", 1) or 1)

    kd_cfg = qp.get("keyword_density", {}) if isinstance(qp, dict) else {}
    kw_min_req = float(kd_cfg.get("min", 1.0) or 1.0)
    kw_max_req = float(kd_cfg.get("max", 3.0) or 3.0)
    kw_max_req = max(kw_max_req, kw_min_req + 0.25)

    elem_cfg = qp.get("elements", {}) if isinstance(qp, dict) else {}
    table_required = bool(elem_cfg.get("table_required", True))
    lists_required = bool(elem_cfg.get("lists_required", True))
    cta_required = bool(elem_cfg.get("cta_required", True))
    buyer_intent_required = bool(elem_cfg.get("buyer_intent_required", False))

    # ── PILLAR 1: Content Quality (15 pts) ───────────────────────────────────
    cq = 0

    r01_name = f"Word Count ≥ {wc_target}"
    if word_count >= wc_target:
        cq += rule("R01", r01_name, "content_quality", 5, 5, True)
    elif word_count >= wc_soft_min:
        cq += rule("R01", r01_name, "content_quality", 3, 5, False,
                   "high", f"Article {word_count} words — target {wc_target}+",
                   "Expand content with more detail and examples")
    else:
        cq += rule("R01", r01_name, "content_quality", 0, 5, False,
                   "critical", f"Article too short: {word_count} words (need {wc_hard_min}+)",
                   "Expand content with more detail, examples, and analysis")

    p_count = len(re.findall(r"<p", body_html, re.I))
    if p_count >= 15:
        cq += rule("R02", "Paragraph Count ≥ 15", "content_quality", 3, 3, True)
    elif p_count >= 10:
        cq += rule("R02", "Paragraph Count ≥ 15", "content_quality", 2, 3, False,
                   "medium", f"Only {p_count} paragraphs — target 15+", "Add more paragraphs")
    else:
        cq += rule("R02", "Paragraph Count ≥ 15", "content_quality", 0, 3, False,
                   "high", f"Only {p_count} paragraphs — content feels sparse",
                   "Add more paragraphs with specific details and examples")

    if h2_count >= h2_min_req and h3_count >= h3_min_req:
        cq += rule("R03", "Heading Structure (H2+H3)", "content_quality", 4, 4, True)
    elif h2_count >= max(2, h2_min_req - 2):
        cq += rule("R03", "Heading Structure (H2+H3)", "content_quality", 2, 4, False,
                   "high", f"Only {h2_count} H2 and {h3_count} H3 sections",
                   f"Add {h2_min_req}+ H2 headings and {h3_min_req}+ H3 sub-sections")
    else:
        cq += rule("R03", "Heading Structure (H2+H3)", "content_quality", 0, 4, False,
                   "high", f"Only {h2_count} H2 headings — need {h2_min_req}+",
                   f"Add {h2_min_req}+ H2 headings and {h3_min_req}+ H3 sub-sections")

    if not table_required:
        cq += rule("R04", "Comparison Table Present", "content_quality", 2, 2, True)
    elif has_table:
        cq += rule("R04", "Comparison Table Present", "content_quality", 2, 2, True)
    else:
        cq += rule("R04", "Comparison Table Present", "content_quality", 0, 2, False,
                   "medium", "No comparison table found",
                   "Add a table for data comparison, pricing, or feature breakdown")

    if not lists_required:
        cq += rule("R05", "Lists Present (UL/OL)", "content_quality", 1, 1, True)
    elif has_ul or has_ol:
        cq += rule("R05", "Lists Present (UL/OL)", "content_quality", 1, 1, True)
    else:
        cq += rule("R05", "Lists Present (UL/OL)", "content_quality", 0, 1, False,
                   "medium", "No bullet/numbered lists",
                   "Add lists for quick-scan content and step-by-step instructions")

    # ── PILLAR 2: SEO / Keywords (20 pts) ────────────────────────────────────
    seo = 0

    r06_name = f"Keyword Density {kw_min_req:.1f}-{kw_max_req:.1f}%"
    if kw_min_req <= kw_density <= kw_max_req:
        seo += rule("R06", r06_name, "seo", 6, 6, True)
    elif max(0.4, kw_min_req - 0.5) <= kw_density < kw_min_req:
        seo += rule("R06", r06_name, "seo", 3, 6, False,
                    "high", f"Keyword density {kw_density:.1f}% — too low (target {kw_min_req:.1f}-{kw_max_req:.1f}%)",
                    f"Add '{keyword}' more naturally in paragraphs")
    elif kw_density > kw_max_req:
        seo += rule("R06", r06_name, "seo", 0, 6, False,
                    "critical", f"Keyword density {kw_density:.1f}% — KEYWORD STUFFING detected",
                    "Remove forced repetitions, use synonyms and semantic variations")
    else:
        seo += rule("R06", r06_name, "seo", 0, 6, False,
                    "critical", f"Keyword density {kw_density:.1f}% — keyword barely present",
                    f"Add '{keyword}' naturally throughout the article (target {kw_min_req:.1f}-{kw_max_req:.1f}%)")

    first_100 = " ".join(words[:100]).lower()
    if kw_lower and kw_lower in first_100:
        seo += rule("R07", "Keyword in First 100 Words", "seo", 3, 3, True)
    else:
        seo += rule("R07", "Keyword in First 100 Words", "seo", 0, 3, False,
                    "high", "Keyword missing from first 100 words",
                    "Include keyword naturally in the introduction")

    h2_texts = " ".join(re.findall(r"<h2[^>]*>(.*?)</h2>", body_html, re.I)).lower()
    kw_in_h2 = (kw_lower and (kw_lower in h2_texts or
                               any(w in h2_texts for w in kw_lower.split() if len(w) > 3)))
    if kw_in_h2:
        seo += rule("R08", "Keyword in H2 Headings", "seo", 3, 3, True)
    else:
        seo += rule("R08", "Keyword in H2 Headings", "seo", 0, 3, False,
                    "medium", "Keyword/variations missing from H2 headings",
                    "Include keyword or variations in at least 1-2 H2 headings")

    kw_words = [w for w in kw_lower.split() if len(w) > 3] if kw_lower else []
    lsi_hits = sum(1 for w in kw_words if text_lower.count(w) > 3)
    if not kw_words or lsi_hits >= len(kw_words):
        seo += rule("R09", "LSI/Semantic Variations", "seo", 3, 3, True)
    else:
        seo += rule("R09", "LSI/Semantic Variations", "seo", 0, 3, False,
                    "medium", "Insufficient LSI/semantic keyword variations",
                    "Add synonyms, related terms, and long-tail variations")

    mt_ok = (meta_title and kw_lower and kw_lower in meta_title.lower()
             and 30 <= len(meta_title) <= 65)
    if mt_ok:
        seo += rule("R10", "Meta Title with Keyword", "seo", 3, 3, True)
    else:
        if not meta_title:
            _msg, _sev = "Missing meta title", "high"
        elif kw_lower and kw_lower not in meta_title.lower():
            _msg, _sev = "Keyword missing from meta title", "medium"
        else:
            _msg, _sev = f"Meta title length {len(meta_title)} chars (target 55-65)", "low"
        seo += rule("R10", "Meta Title with Keyword", "seo", 0, 3, False,
                    _sev, _msg, "Add a compelling meta title (55-65 chars) with keyword")

    if meta_desc and 100 <= len(meta_desc) <= 165:
        seo += rule("R11", "Meta Description Length", "seo", 2, 2, True)
    else:
        _msg = "Missing meta description" if not meta_desc else \
               f"Meta description {len(meta_desc)} chars (target 100-165)"
        seo += rule("R11", "Meta Description Length", "seo", 0, 2, False,
                    "high" if not meta_desc else "low", _msg,
                    "Add a 150-160 char meta description with keyword and CTA")

    # ── PILLAR 3: Structure & HTML (10 pts) ──────────────────────────────────
    struct = 0

    if not faq_required:
        struct += rule("R12", "FAQ Section Present", "structure", 3, 3, True)
    elif has_faq:
        struct += rule("R12", "FAQ Section Present", "structure", 3, 3, True)
    else:
        struct += rule("R12", "FAQ Section Present", "structure", 0, 3, False,
                       "high", "Missing FAQ section",
                       "Add FAQ section with 5-6 specific Q&As for featured snippets")

    r13_name = f"H2 Count ≥ {h2_min_req}"
    if h2_count >= h2_min_req:
        struct += rule("R13", r13_name, "structure", 2, 2, True)
    else:
        struct += rule("R13", r13_name, "structure", 0, 2, False,
                       "medium", f"Only {h2_count} H2 headings (target {h2_min_req}+)", "Add more H2 sections")

    r14_name = f"H3 Count ≥ {h3_min_req}"
    if h3_count >= h3_min_req:
        struct += rule("R14", r14_name, "structure", 2, 2, True)
    else:
        struct += rule("R14", r14_name, "structure", 0, 2, False,
                       "medium", f"Only {h3_count} H3 sub-headings (target {h3_min_req}+)",
                       "Add H3 sub-sections within H2s")

    if first_p_words >= 30 and first_p_has_kw:
        struct += rule("R15", "Keyword in First Paragraph", "structure", 3, 3, True)
    else:
        struct += rule("R15", "Keyword in First Paragraph", "structure", 0, 3, False,
                       "high", "First paragraph doesn't answer the search query directly",
                       "Start with a concise 2-sentence definition that includes the keyword")

    # ── PILLAR 4: Readability (15 pts) ───────────────────────────────────────
    read = 0

    avg_sent_len = sum(len(s.split()) for s in sentences) / sent_count
    if 12 <= avg_sent_len <= 22:
        read += rule("R16", "Sentence Length 12-22 Words", "readability", 5, 5, True)
    elif avg_sent_len < 12:
        read += rule("R16", "Sentence Length 12-22 Words", "readability", 3, 5, False,
                     "medium", f"Avg sentence {avg_sent_len:.0f} words — too short",
                     "Add more context and detail to sentences")
    else:
        read += rule("R16", "Sentence Length 12-22 Words", "readability", 0, 5, False,
                     "high", f"Avg sentence {avg_sent_len:.0f} words — too long",
                     "Break long sentences into 15-20 word chunks for better readability")

    paras_html = re.findall(r"<p[^>]*>(.*?)</p>", body_html, re.I | re.DOTALL)
    long_paras = [p for p in paras_html if len(re.sub(r"<[^>]+>", "", p).split()) > 100]
    if not long_paras:
        read += rule("R17", "No Wall-of-Text Paragraphs", "readability", 3, 3, True)
    else:
        read += rule("R17", "No Wall-of-Text Paragraphs", "readability", 0, 3, False,
                     "medium", f"{len(long_paras)} paragraph(s) over 100 words — wall of text",
                     "Break long paragraphs into 2-3 shorter ones (3-4 sentences each)")

    try:
        import textstat
        flesch = textstat.flesch_reading_ease(text[:5000])

        # ── Adaptive Flesch target based on content type ─────────────────
        # Technical/educational content (scientific names, specialty products)
        # naturally scores lower due to required vocabulary. Adjust expectations.
        kw_l = (keyword or "").lower()
        title_l = (title or "").lower()
        combined = f"{kw_l} {title_l} {text_lower[:2000]}"

        # Detect content type from keyword/title/intro
        is_technical = any(t in combined for t in [
            "scientific", "compound", "chemical", "molecular", "biology",
            "cinnamomum", "verum", "extract", "essential oil", "anatomy",
            "biochemistry", "pharmac", "clinical", "medical research"
        ])
        is_commercial = any(t in kw_l for t in [
            "buy", "shop", "price", "cheap", "best", "top", "review",
            "vs ", " vs", "compare", "discount", "deal"
        ])
        # Informational has "what/why/how/guide/benefits" or no commercial signals
        is_informational = any(t in combined for t in [
            "what is", "what are", "how to", "why ", "guide", "benefits",
            "history", "origin", "tradition", "uses of"
        ]) or (not is_commercial and not is_technical)

        # Pick target range
        if is_technical:
            f_low, f_high = 30, 50
            range_label = "30-50 (technical)"
        elif is_commercial and not is_informational:
            f_low, f_high = 55, 75
            range_label = "55-75 (commercial)"
        else:
            f_low, f_high = 40, 60
            range_label = "40-60 (informational)"

        # Tolerance band (half-credit zone)
        tol = 10
        f_tol_low = max(0, f_low - tol)
        f_tol_high = min(100, f_high + tol)

        rule_name = f"Flesch Reading Ease {range_label}"
        if f_low <= flesch <= f_high:
            read += rule("R18", rule_name, "readability", 4, 4, True)
        elif f_tol_low <= flesch < f_low or f_high < flesch <= f_tol_high:
            read += rule("R18", rule_name, "readability", 2, 4, False,
                         "medium", f"Flesch Reading Ease {flesch:.0f} (target {f_low}-{f_high})",
                         "Adjust sentence complexity for the content type")
        else:
            direction = "too difficult" if flesch < f_low else "too casual"
            read += rule("R18", rule_name, "readability", 0, 4, False,
                         "medium",
                         f"Flesch Reading Ease {flesch:.0f} — {direction} (target {f_low}-{f_high})",
                         "Adjust sentence complexity")
    except Exception:
        log.warning("textstat not available or error — Flesch score defaulting to 0/4")
        read += rule("R18", "Flesch Reading Ease 50-75", "readability", 0, 4, False,
                     "medium", "Flesch score unavailable (textstat missing/error)",
                     "Install textstat: pip install textstat")

    sen_starts = [" ".join(s.split()[:2]).lower() for s in sentences if s.split()]
    start_freq = Counter(sen_starts).most_common(3)
    has_repetitive = any(freq > 3 for starter, freq in start_freq if len(starter) > 3)
    # Also detect AI-common starters
    ai_starters = ["when it", "in this", "it is", "this is", "there are", "there is"]
    ai_starter_count = sum(1 for s in sen_starts if s in ai_starters)
    has_ai_starters = ai_starter_count > 4
    if not has_repetitive and not has_ai_starters:
        read += rule("R19", "Sentence Opener Variety", "readability", 3, 3, True)
    else:
        bad = [st for st, freq in start_freq if freq > 3 and len(st) > 3]
        if has_ai_starters:
            bad.append(f"AI patterns ({ai_starter_count}x)")
        read += rule("R19", "Sentence Opener Variety", "readability", 0, 3, False,
                     "medium", f"Repetitive sentence openers: {bad[:2]}",
                     "Vary how you begin sentences — mix questions, short/long, statements")

    # ── PILLAR 5: E-E-A-T (15 pts) ───────────────────────────────────────────
    eeat = 0

    eeat_signals = ["according to", "published in", "study found", "study published",
                    "scientific", "peer-reviewed", "clinical trial", "%",
                    "university", "institute", "foundation", "journal",
                    "guidelines", "fda", "usda", "who ", "cdc",
                    "a 20", "et al"]
    eeat_hits = sum(1 for s in eeat_signals if s in text_lower)
    if eeat_hits >= 5:
        eeat += rule("R20", "Authority Signals (5+)", "eeat", 5, 5, True)
    elif eeat_hits >= 3:
        eeat += rule("R20", "Authority Signals (5+)", "eeat", 3, 5, False,
                     "high", f"Only {eeat_hits} authority signals — target 5+",
                     "Add study citations, expert quotes, and statistics")
    else:
        eeat += rule("R20", "Authority Signals (5+)", "eeat", 0, 5, False,
                     "critical", f"Only {eeat_hits} authority/expertise signals",
                     "Add specific statistics, study citations, expert quotes, and data-driven claims")

    specific_data = len(re.findall(
        r"\b\d+(?:\.\d+)?%\b|\b\d{4}\b|\b\d+[,.]?\d* (?:mg|g|kg|ml|mcg|IU)\b", text))
    if specific_data >= 5:
        eeat += rule("R21", "Specific Data Points (5+)", "eeat", 4, 4, True)
    elif specific_data >= 2:
        eeat += rule("R21", "Specific Data Points (5+)", "eeat", 2, 4, False,
                     "high", f"Only {specific_data} specific data points",
                     "Add specific percentages, dates, measurements")
    else:
        eeat += rule("R21", "Specific Data Points (5+)", "eeat", 0, 4, False,
                     "high", f"Only {specific_data} specific data points (numbers, stats, measurements)",
                     "Add specific percentages, dates, measurements — e.g. '2000% increase in absorption'")

    r22_name = f"External Authority Links ({external_min_req}+)"
    if external_a >= external_min_req:
        eeat += rule("R22", r22_name, "eeat", 3, 3, True)
    elif external_a >= 1:
        eeat += rule("R22", r22_name, "eeat", 1, 3, False,
                     "medium", f"Only {external_a} external links (target {external_min_req}+)",
                     "Link to PubMed, Wikipedia, .gov/.edu sources")
    else:
        eeat += rule("R22", r22_name, "eeat", 0, 3, False,
                     "high", "No external/reference links to authoritative sources",
                     "Add links to PubMed, Wikipedia, .gov/.edu sources for credibility")

    cta_words = ["buy", "shop", "order", "contact", "get started", "learn more", "discover", "try"]
    has_cta = any(w in text_lower[-500:] for w in cta_words)
    if not cta_required:
        eeat += rule("R23", "Call-to-Action in Conclusion", "eeat", 3, 3, True)
    elif has_cta:
        eeat += rule("R23", "Call-to-Action in Conclusion", "eeat", 3, 3, True)
    else:
        eeat += rule("R23", "Call-to-Action in Conclusion", "eeat", 0, 3, False,
                     "medium", "No call-to-action in conclusion",
                     "Add a clear CTA — shop, learn more, contact, etc.")

    # ── PILLAR 6: Links (10 pts) ─────────────────────────────────────────────
    links = 0

    r24_name = f"Internal Links ({internal_min_req}+)"
    if internal_a >= internal_min_req:
        links += rule("R24", r24_name, "links", 5, 5, True)
    elif internal_a >= 2:
        links += rule("R24", r24_name, "links", 3, 5, False,
                      "high", f"Only {internal_a} internal links (target {internal_min_req}+)",
                      "Add internal links to related articles and category pages")
    else:
        links += rule("R24", r24_name, "links", 0, 5, False,
                      "high", f"Only {internal_a} internal links (need 3-5)",
                      "Add internal links to product pages, related articles, and category pages")

    r25_name = f"External Links ({external_min_req}+)"
    if external_a >= external_min_req:
        links += rule("R25", r25_name, "links", 3, 3, True)
    elif external_a >= 1:
        links += rule("R25", r25_name, "links", 1, 3, False,
                      "medium", f"Only {external_a} external links (target {external_min_req}+)",
                      "Add 2-3 authoritative external links")
    else:
        links += rule("R25", r25_name, "links", 0, 3, False,
                      "medium", f"Only {external_a} external links",
                      "Add 2-3 authoritative external links (Wikipedia, studies, .gov)")

    r26_name = f"Wikipedia Reference ({wikipedia_min_req}+)"
    if wiki_links >= wikipedia_min_req:
        links += rule("R26", r26_name, "links", 2, 2, True)
    else:
        links += rule("R26", r26_name, "links", 0, 2, False,
                      "low", "No Wikipedia reference",
                      "Add at least one Wikipedia citation for credibility")

    # ── PILLAR 7: AI / AEO Readiness (10 pts) ────────────────────────────────
    aeo = 0

    if first_p_words >= 40 and (kw_lower and kw_lower.split()[0] in first_p_text.lower()):
        aeo += rule("R27", "Extractable Opening Definition", "aeo", 3, 3, True)
    else:
        aeo += rule("R27", "Extractable Opening Definition", "aeo", 0, 3, False,
                    "high", "Opening paragraph isn't a concise extractable definition",
                    "Start with a clear 2-sentence definition/answer that AI engines can extract")

    if not faq_required:
        aeo += rule("R28", "FAQ Section for AEO", "aeo", 3, 3, True)
    elif has_faq:
        aeo += rule("R28", "FAQ Section for AEO", "aeo", 3, 3, True)
    else:
        aeo += rule("R28", "FAQ Section for AEO", "aeo", 0, 3, False,
                    "high", "Missing FAQ — reduces AEO/featured snippet potential",
                    "Add FAQ section with direct question-answer format")

    if not lists_required:
        aeo += rule("R29", "Scannable Lists for AI", "aeo", 2, 2, True)
    elif has_ul or has_ol:
        aeo += rule("R29", "Scannable Lists for AI", "aeo", 2, 2, True)
    else:
        aeo += rule("R29", "Scannable Lists for AI", "aeo", 0, 2, False,
                    "medium", "No scannable lists for AI extraction",
                    "Add bullet-point summaries or key takeaways sections")

    short_strong = re.findall(r"<strong>(.*?)</strong>", body_html)
    if len(short_strong) >= 3:
        aeo += rule("R30", "Bold Key Terms (3+)", "aeo", 2, 2, True)
    else:
        aeo += rule("R30", "Bold Key Terms (3+)", "aeo", 0, 2, False,
                    "medium", "Few bold/strong key terms for AI to identify",
                    "Bold key terms and definitions that AI should extract as answers")

    # ── PILLAR 8: Language & Style (5 pts) ───────────────────────────────────
    lang = 0

    passive_patterns = [r"\bwas \w+(?:ed|en)\b", r"\bwere \w+(?:ed|en)\b",
                        r"\bis being \w+(?:ed|en)\b", r"\bare being \w+(?:ed|en)\b"]
    passive_count = sum(len(re.findall(p, text, re.I)) for p in passive_patterns)
    passive_pct = (passive_count / sent_count) * 100
    if passive_pct <= 20:
        lang += rule("R31", "Low Passive Voice (<20%)", "language", 2, 2, True)
    else:
        lang += rule("R31", "Low Passive Voice (<20%)", "language", 0, 2, False,
                     "medium", f"Passive voice {passive_pct:.0f}% (target under 20%)",
                     "Convert passive to active: 'was prepared by chefs' → 'chefs prepared'")

    weak_openers = ["however, ", "moreover, ", "furthermore, ", "in conclusion, ",
                    "in summary, ", "it should be noted", "it is important to note",
                    "it is worth noting", "it is essential",
                    "when it comes to ", "at the end of the day",
                    "needless to say", "it goes without saying",
                    "let's dive in", "in this article",
                    "this comprehensive guide", "we explore"]
    weak_count = sum(text_lower.count(w) for w in weak_openers)
    if weak_count <= 2:
        lang += rule("R32", "Minimal Generic Transitions", "language", 2, 2, True)
    elif weak_count <= 4:
        lang += rule("R32", "Minimal Generic Transitions", "language", 1, 2, False,
                     "low", f"{weak_count} generic transitions — slightly elevated",
                     "Reduce repetition of 'Furthermore/Moreover/In conclusion'")
    else:
        lang += rule("R32", "Minimal Generic Transitions", "language", 0, 2, False,
                     "medium", f"AI-generated pattern: {weak_count} generic transition phrases",
                     "Replace 'Furthermore/Moreover/In conclusion' with specific connectors or remove")

    if re.search(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]", text):
        lang += rule("R33", "No Non-English Text", "language", 0, 1, False,
                     "critical", "Non-English text detected (Chinese/Japanese characters)",
                     "Remove non-English text fragments — signals unreviewed AI generation")
    else:
        lang += rule("R33", "No Non-English Text", "language", 1, 1, True)

    # ── PILLAR 9: Content Intelligence (36 pts) ────────────────────────────────
    ci = 0

    # R34: Semantic Keyword Variation — 5+ distinct semantic variants of primary keyword
    if kw_lower and len(kw_lower.split()) >= 1:
        # Build stemmed/partial variants — count unique phrasings that include keyword root words
        kw_root_words = [w for w in kw_lower.split() if len(w) > 3]
        # Count distinct 2-5 word phrases that contain at least one root word but differ from exact keyword
        text_3grams = []
        word_list_lower = text_lower.split()
        for i in range(len(word_list_lower) - 1):
            for n in range(2, min(6, len(word_list_lower) - i + 1)):
                ngram = " ".join(word_list_lower[i:i+n])
                if ngram != kw_lower and any(rw in ngram for rw in kw_root_words):
                    text_3grams.append(ngram)
        unique_variations = len(set(text_3grams))
        if unique_variations >= 5:
            ci += rule("R34", "Semantic Keyword Variation (5+)", "content_intelligence", 4, 4, True)
        elif unique_variations >= 3:
            ci += rule("R34", "Semantic Keyword Variation (5+)", "content_intelligence", 2, 4, False,
                       "high", f"Only {unique_variations} semantic keyword variations (target 5+)",
                       "Use synonyms, related phrases, and LSI variations of the primary keyword")
        else:
            ci += rule("R34", "Semantic Keyword Variation (5+)", "content_intelligence", 0, 4, False,
                       "critical", f"Only {unique_variations} semantic variations — keyword stuffing risk",
                       "Replace repeated exact keywords with semantic variations (synonyms, related phrases)")
    else:
        ci += rule("R34", "Semantic Keyword Variation (5+)", "content_intelligence", 4, 4, True)

    # R35: AI Pattern Score — detect AIWatermark-style fluff/robotic patterns
    ai_fluff_patterns = [
        r"it's worth noting", r"it is worth noting", r"in today's (?:fast-paced|modern|digital)",
        r"certainly!", r"absolutely!", r"great question", r"in conclusion, it's",
        r"let's dive", r"when it comes to", r"without further ado",
        r"feel free to", r"don't hesitate to", r"having said that",
        r"furthermore,", r"moreover,", r"additionally,", r"subsequently,",
        r"consequently,", r"nevertheless,", r"nonetheless,",
        r"it is important to note", r"it should be noted",
        r"this comprehensive guide", r"in this article, we",
    ]
    ai_pattern_hits = sum(len(re.findall(p, text_lower)) for p in ai_fluff_patterns)
    per_1k = ai_pattern_hits / max(word_count / 1000, 0.1)
    if per_1k < 2:
        ci += rule("R35", "AI Pattern Score (<2/1000w)", "content_intelligence", 4, 4, True)
    elif per_1k < 4:
        ci += rule("R35", "AI Pattern Score (<2/1000w)", "content_intelligence", 2, 4, False,
                   "high", f"AI patterns: {ai_pattern_hits} ({per_1k:.1f}/1000w) — target <2",
                   "Remove AI phrases: 'furthermore', 'it's worth noting', 'let's dive in', etc.")
    else:
        ci += rule("R35", "AI Pattern Score (<2/1000w)", "content_intelligence", 0, 4, False,
                   "critical", f"High AI detectability: {ai_pattern_hits} patterns ({per_1k:.1f}/1000w)",
                   "Rewrite to remove robotic phrases, vary sentence structure, add human tone")

    # R36: Experience Signals — first-person real-world experience markers
    experience_signals = [
        "we tested", "we found", "in our experience", "we observed",
        "i noticed", "after trying", "hands-on", "first-hand",
        "we discovered", "our team", "we recommend", "we compared",
        "in practice", "real-world", "we've seen", "from our testing",
    ]
    exp_hits = sum(1 for s in experience_signals if s in text_lower)
    if exp_hits >= 3:
        ci += rule("R36", "Experience Signals (3+)", "content_intelligence", 4, 4, True)
    elif exp_hits >= 1:
        ci += rule("R36", "Experience Signals (3+)", "content_intelligence", 2, 4, False,
                   "high", f"Only {exp_hits} experience signal(s) — need 3+ for E-E-A-T",
                   "Add 'we tested', 'in our experience', 'we found', 'after trying' naturally")
    else:
        ci += rule("R36", "Experience Signals (3+)", "content_intelligence", 0, 4, False,
                   "critical", "No first-person experience signals — weak E-E-A-T",
                   "Add authentic experience: 'we tested', 'in our experience', 'we observed', 'hands-on'")

    # R37: Entity Richness — named entities (locations, products, orgs, concepts)
    # Use regex patterns for common entity-like phrases
    entity_patterns = [
        r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b",  # Multi-word proper nouns (Title Case)
        r"\b[A-Z][a-z]{2,}\b",                   # Single-word proper nouns (3+ chars)
    ]
    # Common false positives to exclude (sentence starters, generic words)
    _entity_stopwords = {
        "the", "this", "that", "these", "those", "here", "there", "when", "where",
        "what", "which", "while", "with", "without", "would", "could", "should",
        "have", "has", "had", "been", "being", "are", "were", "was", "also",
        "however", "although", "because", "therefore", "moreover", "furthermore",
        "additionally", "finally", "first", "second", "third", "next", "then",
        "each", "every", "many", "some", "most", "other", "another", "such",
        "like", "just", "only", "even", "still", "already", "always", "never",
        "often", "sometimes", "usually", "typically", "generally", "essentially",
        "particularly", "especially", "really", "actually", "certainly", "definitely",
        "simply", "truly", "indeed", "perhaps", "maybe", "probably", "possibly",
        "clearly", "obviously", "apparently", "understand", "understanding",
        "whether", "either", "neither", "both", "all", "any", "few", "several",
        "much", "more", "less", "very", "too", "quite", "rather", "fairly",
        "how", "why", "for", "but", "and", "not", "yet", "nor",
        "from", "into", "onto", "upon", "about", "above", "below", "between",
        "through", "during", "before", "after", "since", "until",
        "our", "your", "their", "its", "his", "her",
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "don", "doesn", "didn", "won", "wouldn", "couldn", "shouldn",
        "key", "top", "best", "new", "old", "good", "great", "high", "low",
        "look", "make", "take", "give", "keep", "let", "get", "set", "put",
        "read", "find", "know", "think", "see", "come", "want", "need", "use",
        "try", "ask", "work", "seem", "feel", "leave", "call", "start", "run",
        "advantages", "disadvantages", "benefits", "drawbacks", "features",
        "conclusion", "introduction", "overview", "summary", "section",
        "table", "figure", "image", "list", "step", "tip", "note", "example",
        "pros", "cons", "faq", "frequently", "asked", "questions",
    }
    entities_found = set()
    for ep in entity_patterns:
        for m in re.finditer(ep, text):
            ent = m.group().strip()
            ent_lower = ent.lower()
            # Skip stopwords and very short entities
            if ent_lower in _entity_stopwords or len(ent) < 3:
                continue
            # Skip keyword words themselves
            if ent_lower in kw_lower.split():
                continue
            # For single-word matches, require 4+ chars
            if len(ent.split()) < 2 and len(ent) < 4:
                continue
            entities_found.add(ent_lower)
    entity_count = len(entities_found)
    if entity_count >= 8:
        ci += rule("R37", "Entity Richness (8+)", "content_intelligence", 3, 3, True)
    elif entity_count >= 4:
        ci += rule("R37", "Entity Richness (8+)", "content_intelligence", 1, 3, False,
                   "medium", f"Only {entity_count} unique entities — target 8+",
                   "Add named locations (Idukki, Wayanad), products, organizations, concepts")
    else:
        ci += rule("R37", "Entity Richness (8+)", "content_intelligence", 0, 3, False,
                   "high", f"Only {entity_count} named entities — content lacks specificity",
                   "Add specific place names, product names, organizations, researcher names")

    # R38: Featured Snippet Block — direct answer (30-60 words) after question heading
    question_headings = re.findall(
        r"<h[23][^>]*>(.*?)</h[23]>\s*<p[^>]*>(.*?)</p>",
        body_html, re.I | re.DOTALL,
    )
    snippet_blocks = 0
    for heading_text, para_text in question_headings:
        heading_clean = re.sub(r"<[^>]+>", "", heading_text).strip()
        para_clean = re.sub(r"<[^>]+>", "", para_text).strip()
        para_wc = len(para_clean.split())
        if heading_clean.rstrip().endswith("?") and 25 <= para_wc <= 70:
            snippet_blocks += 1
    if snippet_blocks >= 2:
        ci += rule("R38", "Featured Snippet Blocks (2+)", "content_intelligence", 3, 3, True)
    elif snippet_blocks >= 1:
        ci += rule("R38", "Featured Snippet Blocks (2+)", "content_intelligence", 1, 3, False,
                   "medium", f"Only {snippet_blocks} snippet-ready block — target 2+",
                   "After question headings, start with a direct 30-60 word answer paragraph")
    else:
        ci += rule("R38", "Featured Snippet Blocks (2+)", "content_intelligence", 0, 3, False,
                   "high", "No featured snippet blocks — missing featured snippet opportunity",
                   "Add question-format headings followed by concise 30-60 word direct answer paragraphs")

    # R39: Comparison Table Quality — table with 3+ rows, 3+ columns
    table_quality_ok = False
    table_blocks = re.findall(r"<table[^>]*>(.*?)</table>", body_html, re.I | re.DOTALL)
    for tbl in table_blocks:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.I | re.DOTALL)
        if len(rows) >= 3:
            # Check column count in first row
            cols = len(re.findall(r"<t[hd][^>]*>", rows[0], re.I))
            if cols >= 3:
                table_quality_ok = True
                break
    if not table_required:
        ci += rule("R39", "Quality Comparison Table (3×3+)", "content_intelligence", 2, 2, True)
    elif table_quality_ok:
        ci += rule("R39", "Quality Comparison Table (3×3+)", "content_intelligence", 2, 2, True)
    else:
        ci += rule("R39", "Quality Comparison Table (3×3+)", "content_intelligence", 0, 2, False,
                   "medium", "No quality comparison table (need ≥3 rows × ≥3 columns)",
                   "Add a data-rich comparison table with at least 3 rows and 3 columns")

    # R40: Buyer Intent Section — decision-making markers
    buyer_signals = [
        "which should you", "which one should", "who should buy",
        "best for", "how to choose", "buying guide", "what to look for",
        "before you buy", "is it worth", "should you buy",
        "beginner vs", "budget vs", "premium vs",
    ]
    buyer_hits = sum(1 for s in buyer_signals if s in text_lower)
    if not buyer_intent_required:
        ci += rule("R40", "Buyer Intent Section", "content_intelligence", 3, 3, True)
    elif buyer_hits >= 1:
        ci += rule("R40", "Buyer Intent Section", "content_intelligence", 3, 3, True)
    else:
        ci += rule("R40", "Buyer Intent Section", "content_intelligence", 0, 3, False,
                   "medium", "No buyer intent / decision-making section",
                   "Add a 'Which One Should You Buy?' or 'How to Choose' section with decision guidance")

    # R41: Storytelling Presence — narrative markers
    story_signals = [
        "when we", "one day", "the moment", "we discovered",
        "the result was", "what happened", "we were surprised",
        "turned out", "the breakthrough", "imagine this",
        "picture this", "here's what", "the reality is",
    ]
    story_hits = sum(1 for s in story_signals if s in text_lower)
    if story_hits >= 2:
        ci += rule("R41", "Storytelling Presence (2+)", "content_intelligence", 2, 2, True)
    elif story_hits >= 1:
        ci += rule("R41", "Storytelling Presence (2+)", "content_intelligence", 1, 2, False,
                   "low", f"Only {story_hits} storytelling marker — target 2+",
                   "Add narrative elements: 'when we tested...', 'picture this:', 'the result was...'")
    else:
        ci += rule("R41", "Storytelling Presence (2+)", "content_intelligence", 0, 2, False,
                   "medium", "No storytelling elements — content feels generic",
                   "Add stories: 'when we tested...', 'picture this:', 'here's what happened...'")

    # R42: Visual Break Elements — callouts, tips, blockquotes
    visual_patterns = [
        r"<blockquote", r'<div[^>]*class="[^"]*(?:tip|callout|highlight|note|warning|key-takeaway|pro-tip)[^"]*"',
        r"<aside", r'<div[^>]*class="[^"]*(?:info-box|alert|feature-box)[^"]*"',
    ]
    visual_count = sum(len(re.findall(p, body_html, re.I)) for p in visual_patterns)
    if visual_count >= 2:
        ci += rule("R42", "Visual Break Elements (2+)", "content_intelligence", 2, 2, True)
    elif visual_count >= 1:
        ci += rule("R42", "Visual Break Elements (2+)", "content_intelligence", 1, 2, False,
                   "low", f"Only {visual_count} visual break element — target 2+",
                   "Add blockquotes, tip boxes, or callout divs for visual variety")
    else:
        ci += rule("R42", "Visual Break Elements (2+)", "content_intelligence", 0, 2, False,
                   "medium", "No visual breaks (blockquotes, callouts, tip boxes)",
                   "Add <blockquote>, <div class='tip'>, or <div class='key-takeaway'> elements")

    # R43: Mid-Content CTA — CTA in middle 60% of article (not just end)
    mid_cta_words = ["shop now", "explore", "browse", "check out", "view our",
                     "see our", "get your", "order now", "buy now", "start your"]
    if word_count > 100:
        # Middle 60% = 20% to 80% of text
        mid_start = int(len(text_lower) * 0.2)
        mid_end = int(len(text_lower) * 0.8)
        mid_text = text_lower[mid_start:mid_end]
        has_mid_cta = any(w in mid_text for w in mid_cta_words)
        # Also check for linked CTAs in middle HTML
        mid_html_start = int(len(body_html) * 0.2)
        mid_html_end = int(len(body_html) * 0.8)
        mid_html = body_html[mid_html_start:mid_html_end]
        has_mid_link_cta = bool(re.search(r'<a[^>]*href[^>]*>.*?(?:shop|browse|explore|buy|order)', mid_html, re.I))
        if has_mid_cta or has_mid_link_cta:
            ci += rule("R43", "Mid-Content CTA", "content_intelligence", 2, 2, True)
        else:
            ci += rule("R43", "Mid-Content CTA", "content_intelligence", 0, 2, False,
                       "medium", "No call-to-action in article body (only at end)",
                       "Add a contextual CTA link in the middle of the article")
    else:
        ci += rule("R43", "Mid-Content CTA", "content_intelligence", 2, 2, True)

    # R44: Data Credibility — penalize unsourced precise statistics
    # Find precise percentages with decimals or specific round numbers
    precise_stats = re.findall(r"\b\d+(?:\.\d+)?%", text)
    unsourced = 0
    for stat_match in re.finditer(r"\b\d+(?:\.\d+)?%", text):
        # Check if there's a source attribution within 150 chars before or after
        start = max(0, stat_match.start() - 150)
        end = min(len(text), stat_match.end() + 150)
        context = text[start:end].lower()
        source_words = ["according to", "study", "research", "journal",
                        "published", "report", "survey", "university",
                        "found that", "data from", "source:", "ncbi", "pubmed"]
        if not any(sw in context for sw in source_words):
            unsourced += 1
    if unsourced <= 2:
        ci += rule("R44", "Data Credibility (sourced stats)", "content_intelligence", 3, 3, True)
    elif unsourced <= 4:
        ci += rule("R44", "Data Credibility (sourced stats)", "content_intelligence", 1, 3, False,
                   "high", f"{unsourced} statistics without nearby source attribution",
                   "Add source/study references near each statistic (within 150 chars)")
    else:
        ci += rule("R44", "Data Credibility (sourced stats)", "content_intelligence", 0, 3, False,
                   "critical", f"{unsourced} fabricated-looking stats without sources — credibility risk",
                   "Either cite sources for statistics or use approximate ranges instead of exact numbers")

    # R45: Unique Angle Signal — differentiation markers
    angle_signals = [
        "what most people miss", "the real truth", "what others don't tell",
        "unlike other guides", "here's the difference", "the hidden",
        "what nobody mentions", "contrary to popular", "the surprising",
        "we believe", "our perspective", "in our view", "unpopular opinion",
    ]
    angle_hits = sum(1 for s in angle_signals if s in text_lower)
    if angle_hits >= 1:
        ci += rule("R45", "Unique Angle Signal", "content_intelligence", 2, 2, True)
    else:
        ci += rule("R45", "Unique Angle Signal", "content_intelligence", 0, 2, False,
                   "low", "No differentiation markers — content may feel generic",
                   "Add unique perspective: 'what most overlook', 'the real truth', 'our perspective'")

    # R46: FAQ Answer Quality — FAQ answers should be 40-60 words
    faq_section = re.search(
        r"(?:<h2[^>]*>.*?(?:faq|frequently asked).*?</h2>)(.*?)(?=<h2|$)",
        body_html, re.I | re.DOTALL,
    )
    if not faq_required:
        ci += rule("R46", "FAQ Answer Quality (25-80w avg)", "content_intelligence", 2, 2, True)
    elif faq_section:
        faq_body = faq_section.group(1)
        faq_answers = re.findall(r"<p[^>]*>(.*?)</p>", faq_body, re.I | re.DOTALL)
        if faq_answers:
            answer_wcs = [len(re.sub(r"<[^>]+>", "", a).split()) for a in faq_answers]
            avg_answer_wc = sum(answer_wcs) / len(answer_wcs)
            if 25 <= avg_answer_wc <= 80:
                ci += rule("R46", "FAQ Answer Quality (25-80w avg)", "content_intelligence", 2, 2, True)
            else:
                ci += rule("R46", "FAQ Answer Quality (25-80w avg)", "content_intelligence", 0, 2, False,
                           "medium", f"FAQ answers avg {avg_answer_wc:.0f} words ({'too short' if avg_answer_wc < 25 else 'too long'})",
                           "FAQ answers should be 40-60 words — direct and complete")
        else:
            ci += rule("R46", "FAQ Answer Quality (25-80w avg)", "content_intelligence", 2, 2, True)
    else:
        ci += rule("R46", "FAQ Answer Quality (25-80w avg)", "content_intelligence", 0, 2, False,
                   "low", "No FAQ section found to evaluate",
                   "Add FAQ section with 5+ Q&As, each answer 40-60 words")

    # ── PILLAR 10: Conversion & Persuasion (15 pts) ──────────────────────────
    conv = 0

    # R47: Decision section — "who should buy/avoid" or "how to choose" (3 pts)
    decision_phrases = [
        "who should buy", "who should avoid", "how to choose", "which should you",
        "best for", "buying guide", "what to look for", "before you buy",
        "is it worth", "recommended for", "not recommended for", "ideal for",
    ]
    decision_found = sum(1 for p in decision_phrases if p in text_lower)
    if not buyer_intent_required:
        conv += rule("R47", "Decision / Buyer Guidance Section", "conversion", 3, 3, True)
    elif decision_found >= 1:
        conv += rule("R47", "Decision / Buyer Guidance Section", "conversion", 3, 3, True)
    else:
        conv += rule("R47", "Decision / Buyer Guidance Section", "conversion", 0, 3, False,
                     "high", "No decision/buyer guidance section found",
                     "Add 'Who Should Buy' or 'How to Choose' section with clear guidance")

    # R48: Pros and cons section (2 pts)
    has_pros_cons = bool(re.search(
        r"pros?\s*(and|&|vs)\s*cons?|advantages?\s*(and|&)\s*disadvantages?|benefits?\s*(and|&)\s*drawbacks?",
        text_lower
    ))
    if not buyer_intent_required:
        conv += rule("R48", "Pros & Cons Section", "conversion", 2, 2, True)
    elif has_pros_cons:
        conv += rule("R48", "Pros & Cons Section", "conversion", 2, 2, True)
    else:
        conv += rule("R48", "Pros & Cons Section", "conversion", 0, 2, False,
                     "medium", "No pros/cons section found",
                     "Add a balanced pros and cons section for key decisions")

    # R49: Urgency / scarcity signals (2 pts)
    urgency_phrases = [
        "don't miss", "limited", "act now", "before it's too late",
        "most people miss", "common mistake", "avoid this mistake",
        "what many people overlook", "crucial", "essential step",
    ]
    urgency_count = sum(1 for p in urgency_phrases if p in text_lower)
    if urgency_count >= 2:
        conv += rule("R49", "Urgency / Importance Signals (2+)", "conversion", 2, 2, True)
    elif urgency_count == 1:
        conv += rule("R49", "Urgency / Importance Signals (2+)", "conversion", 1, 2, False,
                     "low", "Only 1 urgency/importance signal — need 2+",
                     "Add urgency phrases like 'most people miss' or 'common mistake'")
    else:
        conv += rule("R49", "Urgency / Importance Signals (2+)", "conversion", 0, 2, False,
                     "medium", "No urgency or importance signals found",
                     "Add 2+ urgency phrases: 'most people miss', 'crucial step', 'avoid this mistake'")

    # R50: Trust signals (2 pts)
    trust_phrases = [
        "verified", "certified", "guarantee", "trusted", "award",
        "years of experience", "tested by", "reviewed by", "recommended by",
        "backed by", "quality assurance", "industry standard",
    ]
    trust_count = sum(1 for p in trust_phrases if p in text_lower)
    if trust_count >= 2:
        conv += rule("R50", "Trust Signals (2+)", "conversion", 2, 2, True)
    elif trust_count == 1:
        conv += rule("R50", "Trust Signals (2+)", "conversion", 1, 2, False,
                     "low", "Only 1 trust signal — need 2+",
                     "Add trust indicators: certified, verified, proven, industry standard")
    else:
        conv += rule("R50", "Trust Signals (2+)", "conversion", 0, 2, False,
                     "medium", "No trust signals found",
                     "Add trust indicators: verified, certified, tested by, years of experience")

    # R51: Benefits-focused language (2 pts)
    benefit_phrases = [
        "helps you", "saves you", "improves", "reduces", "increases",
        "enhances", "boosts", "delivers", "enables", "empowers",
        "benefit", "advantage", "outcome", "result",
    ]
    benefit_count = sum(1 for p in benefit_phrases if p in text_lower)
    if benefit_count >= 3:
        conv += rule("R51", "Benefits-Focused Language (3+)", "conversion", 2, 2, True)
    elif benefit_count >= 1:
        conv += rule("R51", "Benefits-Focused Language (3+)", "conversion", 1, 2, False,
                     "low", f"Only {benefit_count} benefit phrases — need 3+",
                     "Focus on outcomes: 'helps you', 'improves', 'saves you time'")
    else:
        conv += rule("R51", "Benefits-Focused Language (3+)", "conversion", 0, 2, False,
                     "medium", "No benefits-focused language found",
                     "Add benefit phrases: 'helps you', 'improves', 'reduces', 'enables'")

    # R52: CTA placement — mid-content + end (2 pts)
    cta_words = ["buy", "shop", "order", "contact", "get started", "learn more",
                 "discover", "try", "explore", "browse", "check out", "sign up"]
    mid_point = len(text) // 2
    first_half = text_lower[:mid_point]
    second_half = text_lower[mid_point:]
    has_mid_cta = any(c in first_half for c in cta_words)
    has_end_cta = any(c in second_half[-800:] for c in cta_words)
    if not cta_required:
        conv += rule("R52", "CTA Placement (mid + end)", "conversion", 2, 2, True)
    elif has_mid_cta and has_end_cta:
        conv += rule("R52", "CTA Placement (mid + end)", "conversion", 2, 2, True)
    elif has_mid_cta or has_end_cta:
        conv += rule("R52", "CTA Placement (mid + end)", "conversion", 1, 2, False,
                     "low", "CTA only in " + ("middle" if has_mid_cta else "end") + " — need both",
                     "Place a soft CTA in mid-content and a strong CTA near the end")
    else:
        conv += rule("R52", "CTA Placement (mid + end)", "conversion", 0, 2, False,
                     "high", "No CTA found in content",
                     "Add contextual CTAs: soft in mid-content, strong at end")

    # R53: Comparison table with decision guidance (2 pts)
    # Check for table + decision context nearby
    tables = re.findall(r"<table.*?</table>", body_html, re.I | re.DOTALL)
    has_decision_table = False
    for t in tables:
        t_lower = t.lower()
        rows = len(re.findall(r"<tr", t_lower))
        if rows >= 3 and any(p in t_lower for p in ["vs", "compare", "price", "feature", "best", "rating", "score"]):
            has_decision_table = True
            break
    if not buyer_intent_required:
        conv += rule("R53", "Comparison Table for Decisions", "conversion", 2, 2, True)
    elif has_decision_table:
        conv += rule("R53", "Comparison Table for Decisions", "conversion", 2, 2, True)
    else:
        conv += rule("R53", "Comparison Table for Decisions", "conversion", 0, 2, False,
                     "medium", "No comparison/decision table found",
                     "Add a comparison table (3+ rows) with features, pricing, or ratings")

    # ── PILLAR 11: AI Humanization (12 pts) ──────────────────────────────────
    human = 0

    # R54: Opinion signals — author takes a stance (2 pts)
    opinion_phrases = [
        "i believe", "in my opinion", "we think", "our recommendation",
        "we prefer", "the best option", "our top pick", "we suggest",
        "frankly", "honestly", "the truth is", "realistically",
    ]
    opinion_count = sum(1 for p in opinion_phrases if p in text_lower)
    if opinion_count >= 2:
        human += rule("R54", "Opinion Signals (2+)", "ai_humanization", 2, 2, True)
    elif opinion_count == 1:
        human += rule("R54", "Opinion Signals (2+)", "ai_humanization", 1, 2, False,
                      "low", "Only 1 opinion signal — need 2+",
                      "Add author opinions: 'we believe', 'our recommendation', 'honestly'")
    else:
        human += rule("R54", "Opinion Signals (2+)", "ai_humanization", 0, 2, False,
                      "medium", "No opinion signals found — content feels impersonal",
                      "Add 2+ opinion markers: 'we prefer', 'our top pick', 'the truth is'")

    # R55: Contradiction / nuance markers (2 pts)
    contradiction_phrases = [
        "however", "on the other hand", "but", "that said",
        "despite", "although", "while it's true", "not always",
        "the downside", "the catch is", "most people think",
        "contrary to", "the exception is", "interestingly",
    ]
    # Count unique contradiction phrases (not just "but" which is too common)
    contra_count = sum(1 for p in contradiction_phrases if p in text_lower and p != "but")
    if contra_count >= 3:
        human += rule("R55", "Contradiction / Nuance Markers (3+)", "ai_humanization", 2, 2, True)
    elif contra_count >= 1:
        human += rule("R55", "Contradiction / Nuance Markers (3+)", "ai_humanization", 1, 2, False,
                      "low", f"Only {contra_count} nuance marker(s) — need 3+",
                      "Add balanced views: 'however', 'the catch is', 'that said'")
    else:
        human += rule("R55", "Contradiction / Nuance Markers (3+)", "ai_humanization", 0, 2, False,
                      "medium", "No contradiction/nuance signals — content feels one-sided",
                      "Add 3+ nuance markers: 'however', 'on the other hand', 'the downside'")

    # R56: Sentence length variety — std deviation of sentence lengths (2 pts)
    sent_lens = [len(s.split()) for s in sentences if len(s.split()) > 2]
    if len(sent_lens) >= 5:
        avg_sl = sum(sent_lens) / len(sent_lens)
        variance = sum((x - avg_sl) ** 2 for x in sent_lens) / len(sent_lens)
        std_dev = variance ** 0.5
        if std_dev >= 5:
            human += rule("R56", "Sentence Length Variety (std≥5)", "ai_humanization", 2, 2, True)
        elif std_dev >= 3:
            human += rule("R56", "Sentence Length Variety (std≥5)", "ai_humanization", 1, 2, False,
                          "low", f"Sentence length std dev {std_dev:.1f} — target ≥5",
                          "Mix very short (5-8 word) and longer (20-25 word) sentences")
        else:
            human += rule("R56", "Sentence Length Variety (std≥5)", "ai_humanization", 0, 2, False,
                          "medium", f"Monotonous sentence length (std dev {std_dev:.1f})",
                          "Vary sentence lengths dramatically: short punchy + longer analytical")
    else:
        human += rule("R56", "Sentence Length Variety (std≥5)", "ai_humanization", 2, 2, True)

    # R57: No template/formulaic patterns (2 pts)
    template_patterns = [
        r"^in this (article|guide|post),?\s+we",
        r"^let'?s (dive|explore|look|get started|begin)",
        r"^without further ado",
        r"^in conclusion,?\s",
        r"^to sum up,?\s",
        r"^in summary,?\s",
        r"^as we'?ve (seen|discussed|explored)",
    ]
    template_hits = sum(1 for p in template_patterns if re.search(p, text_lower, re.MULTILINE))
    if template_hits == 0:
        human += rule("R57", "No Template Patterns", "ai_humanization", 2, 2, True)
    elif template_hits <= 1:
        human += rule("R57", "No Template Patterns", "ai_humanization", 1, 2, False,
                      "low", f"{template_hits} template pattern found",
                      "Remove 'In this article, we...' and 'Let's dive in' patterns")
    else:
        human += rule("R57", "No Template Patterns", "ai_humanization", 0, 2, False,
                      "high", f"{template_hits} template/formulaic patterns detected",
                      "Rewrite all 'In this article', 'Let's explore', 'In conclusion' patterns")

    # R58: Conversational question markers (2 pts)
    questions_in_body = len(re.findall(r"\?", text))
    h_questions = h2_count  # question headings already counted
    body_questions = questions_in_body - h_questions  # non-heading questions
    if body_questions >= 3:
        human += rule("R58", "Conversational Questions (3+)", "ai_humanization", 2, 2, True)
    elif body_questions >= 1:
        human += rule("R58", "Conversational Questions (3+)", "ai_humanization", 1, 2, False,
                      "low", f"Only {body_questions} conversational question(s) — need 3+",
                      "Add rhetorical questions: 'Why does this matter?' 'Sound familiar?'")
    else:
        human += rule("R58", "Conversational Questions (3+)", "ai_humanization", 0, 2, False,
                      "medium", "No conversational questions found in body text",
                      "Sprinkle rhetorical questions to engage readers")

    # R59: Hedging / qualifier signals — shows human uncertainty (2 pts)
    hedge_phrases = [
        "it depends", "in most cases", "typically", "generally",
        "it varies", "not always", "sometimes", "often", "may",
        "might", "could be", "arguably", "subjective",
    ]
    hedge_count = sum(1 for p in hedge_phrases if p in text_lower)
    if hedge_count >= 3:
        human += rule("R59", "Natural Hedging / Qualifiers (3+)", "ai_humanization", 2, 2, True)
    elif hedge_count >= 1:
        human += rule("R59", "Natural Hedging / Qualifiers (3+)", "ai_humanization", 1, 2, False,
                      "low", f"Only {hedge_count} qualifier(s) — need 3+",
                      "Add nuanced qualifiers: 'typically', 'in most cases', 'it depends'")
    else:
        human += rule("R59", "Natural Hedging / Qualifiers (3+)", "ai_humanization", 0, 2, False,
                      "medium", "No hedging/qualifiers — content sounds overly certain",
                      "Add qualifiers: 'typically', 'it depends', 'in most cases', 'generally'")

    # ── PILLAR 12: Semantic Depth (12 pts) ───────────────────────────────────
    semdeep = 0

    # R60: What/Why/How/When coverage (3 pts)
    coverage_types = {
        "what": bool(re.search(r"\bwhat\s+(is|are|does|do|makes|was)\b", text_lower)),
        "why": bool(re.search(r"\bwhy\s+(is|are|do|does|should|would)\b", text_lower)),
        "how": bool(re.search(r"\bhow\s+(to|do|does|can|should|is)\b", text_lower)),
        "when": bool(re.search(r"\bwhen\s+(to|should|do|does|is|was)\b", text_lower)),
    }
    coverage_count = sum(coverage_types.values())
    if coverage_count >= 3:
        semdeep += rule("R60", "What/Why/How/When Coverage (3+)", "semantic_depth", 3, 3, True)
    elif coverage_count == 2:
        missing = [k for k, v in coverage_types.items() if not v]
        semdeep += rule("R60", "What/Why/How/When Coverage (3+)", "semantic_depth", 2, 3, False,
                        "low", f"Only covers {coverage_count}/4 angles — missing: {', '.join(missing)}",
                        f"Add content covering: {', '.join(missing)}")
    else:
        semdeep += rule("R60", "What/Why/How/When Coverage (3+)", "semantic_depth", 0, 3, False,
                        "high", f"Shallow coverage — only {coverage_count}/4 angles addressed",
                        "Cover what, why, how, and when aspects of the topic")

    # R61: Related subtopic breadth (2 pts)
    # Check for diverse sub-sections beyond the main keyword
    unique_h2_topics = set()
    h2_texts = re.findall(r"<h2[^>]*>(.*?)</h2>", body_html, re.I | re.DOTALL)
    for h2 in h2_texts:
        clean = re.sub(r"<[^>]+>", "", h2).strip().lower()
        # Strip keyword from heading to see the remaining topic
        remaining = clean
        for kw_part in kw_lower.split():
            remaining = remaining.replace(kw_part, "").strip()
        if len(remaining) > 3:
            unique_h2_topics.add(remaining[:30])
    if len(unique_h2_topics) >= 5:
        semdeep += rule("R61", "Subtopic Breadth (5+ unique H2 angles)", "semantic_depth", 2, 2, True)
    elif len(unique_h2_topics) >= 3:
        semdeep += rule("R61", "Subtopic Breadth (5+ unique H2 angles)", "semantic_depth", 1, 2, False,
                        "low", f"Only {len(unique_h2_topics)} unique subtopics — need 5+",
                        "Add more diverse H2 sections covering different angles")
    else:
        semdeep += rule("R61", "Subtopic Breadth (5+ unique H2 angles)", "semantic_depth", 0, 2, False,
                        "medium", "Too few unique subtopics — article lacks breadth",
                        "Add H2 sections for comparisons, use cases, tips, alternatives, FAQs")

    # R62: Use case / scenario presence (2 pts)
    use_case_phrases = [
        "use case", "scenario", "for example", "in practice",
        "real-world", "real world", "case study", "practical",
        "application", "works well for", "ideal for", "perfect for",
    ]
    use_case_count = sum(1 for p in use_case_phrases if p in text_lower)
    if use_case_count >= 2:
        semdeep += rule("R62", "Use Cases / Scenarios (2+)", "semantic_depth", 2, 2, True)
    elif use_case_count == 1:
        semdeep += rule("R62", "Use Cases / Scenarios (2+)", "semantic_depth", 1, 2, False,
                        "low", "Only 1 use case/scenario — need 2+",
                        "Add practical scenarios: 'for example...', 'in practice...', 'use case:'")
    else:
        semdeep += rule("R62", "Use Cases / Scenarios (2+)", "semantic_depth", 0, 2, False,
                        "medium", "No practical use cases or scenarios found",
                        "Add 2+ real-world examples, use cases, or practical scenarios")

    # R63: Beginner + advanced content levels (2 pts)
    beginner_signals = ["beginner", "getting started", "basics", "simple", "easy", "first time", "new to"]
    advanced_signals = ["advanced", "expert", "professional", "in-depth", "technical", "deep dive", "nuanced"]
    has_beginner = any(p in text_lower for p in beginner_signals)
    has_advanced = any(p in text_lower for p in advanced_signals)
    if has_beginner and has_advanced:
        semdeep += rule("R63", "Beginner + Advanced Content", "semantic_depth", 2, 2, True)
    elif has_beginner or has_advanced:
        semdeep += rule("R63", "Beginner + Advanced Content", "semantic_depth", 1, 2, False,
                        "low", "Content targets only " + ("beginners" if has_beginner else "experts"),
                        "Add content for both beginners and advanced users")
    else:
        semdeep += rule("R63", "Beginner + Advanced Content", "semantic_depth", 0, 2, False,
                        "medium", "No audience-level differentiation",
                        "Include basic explanations AND advanced insights for broader appeal")

    # R64: Implicit question answering (3 pts)
    implicit_q_phrases = [
        "you might wonder", "a common question", "people often ask",
        "you may be thinking", "the short answer", "the real question",
        "what many don't realize", "the key takeaway", "bottom line",
        "so what does this mean", "why does this matter",
    ]
    implicit_q_count = sum(1 for p in implicit_q_phrases if p in text_lower)
    if implicit_q_count >= 2:
        semdeep += rule("R64", "Implicit Questions Answered (2+)", "semantic_depth", 3, 3, True)
    elif implicit_q_count == 1:
        semdeep += rule("R64", "Implicit Questions Answered (2+)", "semantic_depth", 2, 3, False,
                        "low", "Only 1 implicit question addressed — need 2+",
                        "Add 'You might wonder...', 'A common question is...', 'Why does this matter?'")
    else:
        semdeep += rule("R64", "Implicit Questions Answered (2+)", "semantic_depth", 0, 3, False,
                        "medium", "No implicit questions anticipated and answered",
                        "Address unspoken reader questions: 'You might wonder...', 'The real question is...'")

    # ── PILLAR 13: Customer Context (12 pts) ─────────────────────────────────
    ctx = 0
    _brand = (brand_name or "").strip().lower()
    _btype = (business_type or "").strip().lower()
    _locations = [loc.strip().lower() for loc in (target_locations or "").split(",") if loc.strip()]
    _audience = (target_audience or "").strip().lower()

    # R65: Brand mention (2–4 occurrences) (3 pts)
    if _brand and len(_brand) > 1:
        brand_count = text_lower.count(_brand)
        if 2 <= brand_count <= 6:
            ctx += rule("R65", "Brand Mention (2-6x)", "customer_context", 3, 3, True)
        elif brand_count >= 1:
            ctx += rule("R65", "Brand Mention (2-6x)", "customer_context", 1, 3, False,
                        "low", f"Brand '{brand_name}' mentioned {brand_count}x — target 2-6x",
                        f"Mention brand '{brand_name}' 2-6 times naturally across content")
        elif brand_count > 6:
            ctx += rule("R65", "Brand Mention (2-6x)", "customer_context", 1, 3, False,
                        "medium", f"Brand '{brand_name}' over-mentioned ({brand_count}x) — keep to 2-6x",
                        "Reduce brand mentions to avoid appearing overly promotional")
        else:
            ctx += rule("R65", "Brand Mention (2-6x)", "customer_context", 0, 3, False,
                        "high", f"Brand '{brand_name}' not mentioned at all",
                        f"Add 2-6 natural mentions of '{brand_name}' in relevant sections")
    else:
        ctx += rule("R65", "Brand Mention (2-6x)", "customer_context", 3, 3, True)  # no brand to check

    # R66: Location signals matching business area (3 pts)
    if _locations:
        loc_found = sum(1 for loc in _locations if loc in text_lower)
        if loc_found >= 1:
            ctx += rule("R66", "Location Signals Present", "customer_context", 3, 3, True)
        else:
            loc_str = ", ".join(_locations[:3])
            ctx += rule("R66", "Location Signals Present", "customer_context", 0, 3, False,
                        "high", f"No location signals found — target areas: {loc_str}",
                        f"Mention target locations: {loc_str} — geographic relevance boosts local SEO")
    else:
        ctx += rule("R66", "Location Signals Present", "customer_context", 3, 3, True)  # no locations to check

    # R67: Audience-appropriate tone (2 pts)
    if _audience:
        audience_words = [w for w in _audience.lower().split() if len(w) > 3][:5]
        audience_match = sum(1 for w in audience_words if w in text_lower)
        if audience_match >= 2 or not audience_words:
            ctx += rule("R67", "Audience-Appropriate Content", "customer_context", 2, 2, True)
        elif audience_match >= 1:
            ctx += rule("R67", "Audience-Appropriate Content", "customer_context", 1, 2, False,
                        "low", f"Limited audience alignment — only {audience_match} audience term(s) found",
                        f"Reference target audience: {_audience}")
        else:
            ctx += rule("R67", "Audience-Appropriate Content", "customer_context", 0, 2, False,
                        "medium", "Content doesn't reference the target audience",
                        f"Include audience-specific language for: {_audience}")
    else:
        ctx += rule("R67", "Audience-Appropriate Content", "customer_context", 2, 2, True)

    # R68: Product/service alignment with customer URL (2 pts)
    if customer_url and _brand:
        # Check for internal links to customer's site
        has_customer_link = customer_url.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/") in body_html.lower()
        has_brand_in_links = _brand in body_html.lower()
        if has_customer_link or has_brand_in_links:
            ctx += rule("R68", "Customer Site/Product Reference", "customer_context", 2, 2, True)
        else:
            ctx += rule("R68", "Customer Site/Product Reference", "customer_context", 0, 2, False,
                        "medium", "No reference to customer's website or products",
                        f"Add natural references or links to {customer_url}")
    else:
        ctx += rule("R68", "Customer Site/Product Reference", "customer_context", 2, 2, True)

    # R69: Business type tone alignment (2 pts)
    if _btype:
        if "b2b" in _btype:
            # B2B should be more formal, data-driven
            formal_signals = ["roi", "implementation", "enterprise", "solution", "strategy",
                              "stakeholder", "methodology", "deliverable", "scalable", "workflow"]
            formal_count = sum(1 for p in formal_signals if p in text_lower)
            if formal_count >= 2:
                ctx += rule("R69", "Business Type Tone (B2B formal)", "customer_context", 2, 2, True)
            else:
                ctx += rule("R69", "Business Type Tone (B2B formal)", "customer_context", 0, 2, False,
                            "medium", "B2B content too casual — lacks professional terminology",
                            "Add professional terms: ROI, strategy, implementation, scalable")
        elif "b2c" in _btype:
            # B2C should be more conversational, relatable
            casual_signals = ["you", "your", "easy", "simple", "love", "enjoy",
                              "perfect", "amazing", "great", "best"]
            casual_count = sum(1 for p in casual_signals if p in text_lower)
            if casual_count >= 3:
                ctx += rule("R69", "Business Type Tone (B2C conversational)", "customer_context", 2, 2, True)
            else:
                ctx += rule("R69", "Business Type Tone (B2C conversational)", "customer_context", 0, 2, False,
                            "medium", "B2C content too formal — needs conversational tone",
                            "Use 'you/your', relatable language, and enthusiastic descriptions")
        else:
            ctx += rule("R69", "Business Type Tone Alignment", "customer_context", 2, 2, True)
    else:
        ctx += rule("R69", "Business Type Tone Alignment", "customer_context", 2, 2, True)

    # ── PILLAR 14: Snippet Optimization (10 pts) ─────────────────────────────
    snip = 0

    # R70: Definition block in first 400 words (3 pts)
    first_400 = " ".join(words[:400]).lower() if word_count >= 50 else text_lower
    has_definition = bool(re.search(
        r"\b(is a|are a|refers to|defined as|means|describes|can be described as|is the process of|involves)\b", first_400
    ))
    if has_definition:
        snip += rule("R70", "Definition Block in First 400 Words", "snippet_optimization", 3, 3, True)
    else:
        snip += rule("R70", "Definition Block in First 400 Words", "snippet_optimization", 0, 3, False,
                     "high", "No clear definition in the opening section",
                     "Add a 40-60 word direct definition/answer in the first 400 words")

    # R71: Step-by-step list for how-to content (2 pts)
    has_steps = bool(re.search(r"<ol|step\s+\d|step\s+one|first.*second.*third", body_html.lower()))
    has_how_to = "how to" in kw_lower or "how to" in text_lower[:500]
    if has_steps or not has_how_to:
        snip += rule("R71", "Step-by-Step List (for how-to)", "snippet_optimization", 2, 2, True)
    else:
        snip += rule("R71", "Step-by-Step List (for how-to)", "snippet_optimization", 0, 2, False,
                     "high", "How-to content without step-by-step list",
                     "Add numbered steps using <ol> for how-to topics — Google extracts these")

    # R72: Table for comparison queries (2 pts)
    is_comparison = any(p in kw_lower for p in ["vs", "versus", "compare", "comparison", "best", "top"])
    if has_table or not is_comparison:
        snip += rule("R72", "Comparison Table (for vs/best queries)", "snippet_optimization", 2, 2, True)
    else:
        snip += rule("R72", "Comparison Table (for vs/best queries)", "snippet_optimization", 0, 2, False,
                     "high", "Comparison keyword without comparison table",
                     "Add a comparison <table> — Google extracts these as featured snippets")

    # R73: Concise answer paragraphs after question headings (3 pts)
    # Match H2 with ? (allowing nested tags like <p>, <strong> inside the H2)
    question_h2s = re.findall(
        r"<h2[^>]*>(?:(?!</h2>).)*\?(?:(?!</h2>).)*</h2>\s*<p[^>]*>(.*?)</p>",
        body_html, re.I | re.DOTALL,
    )
    good_answers = 0
    for answer in question_h2s:
        answer_text = re.sub(r"<[^>]+>", "", answer).strip()
        answer_wc = len(answer_text.split())
        if 30 <= answer_wc <= 70:
            good_answers += 1
    if good_answers >= 2:
        snip += rule("R73", "Snippet-Ready Answers (30-70w, 2+)", "snippet_optimization", 3, 3, True)
    elif good_answers == 1:
        snip += rule("R73", "Snippet-Ready Answers (30-70w, 2+)", "snippet_optimization", 2, 3, False,
                     "low", "Only 1 snippet-ready answer — need 2+",
                     "Add 30-70 word direct answers after question headings")
    else:
        snip += rule("R73", "Snippet-Ready Answers (30-70w, 2+)", "snippet_optimization", 0, 3, False,
                     "medium", "No snippet-ready answers found after question headings",
                     "Follow question H2s with a 30-70 word direct answer paragraph")

    # ── PILLAR 15: Numeric Consistency (5 pts) ───────────────────────────────
    nc = 0

    def _extract_numeric_vals(txt):
        """Return list of float values from price/rate patterns in text."""
        hits = []
        for pat in (
            r"(?:₹|INR\s*|Rs\.?\s*)[\s]*([\d,]+(?:\.\d+)?)",
            r"\$([\d,]+(?:\.\d+)?)",
            r"([\d,]+(?:\.\d+)?)\s*/\s*(?:kg|tonne|MT|quintal|lb|unit)",
        ):
            for m in re.finditer(pat, txt, re.I):
                raw = m.group(1).replace(",", "")
                try:
                    hits.append(float(raw))
                except ValueError:
                    pass
        return hits

    # R74: Cross-section numeric consistency (5 pts)
    _num_vals = _extract_numeric_vals(text)
    _nc_pass = True
    _nc_issue_msg = ""
    if len(_num_vals) >= 4:
        _nv_min = min(_num_vals)
        _nv_max = max(_num_vals)
        if _nv_min > 0 and _nv_max / _nv_min > 3.0:
            _tier_count = len(re.findall(
                r"\b(?:grade|quality|variant|tier|premium|standard|ordinary|bold|small|large)\b",
                text, re.I
            ))
            if _tier_count < 2:
                _nc_pass = False
                _ratio = round(_nv_max / _nv_min, 1)
                _nc_issue_msg = (
                    f"Numeric contradiction: figures range from "
                    f"{_nv_min:,.0f} to {_nv_max:,.0f} ({_ratio}×) with no explicit grade/tier labels"
                )
    if _nc_pass:
        nc += rule("R74", "Numeric Consistency", "numeric_consistency", 5, 5, True)
    else:
        nc += rule("R74", "Numeric Consistency", "numeric_consistency", 0, 5, False,
                   "high", _nc_issue_msg,
                   "Ensure price/quantity figures are consistent across sections, or label each "
                   "with an explicit grade qualifier (e.g. 'Grade A: ₹4,500/kg vs Grade B: ₹1,850/kg')")

    # ── Totals ───────────────────────────────────────────────────────────────
    total_earned = cq + seo + struct + read + eeat + links + aeo + lang + ci + conv + human + semdeep + ctx + snip + nc
    max_possible = 202  # 197 + 5 (R74 numeric_consistency)
    percentage = round(total_earned / max_possible * 100)

    categories = {
        "content_quality": {"score": cq,     "max": 15, "label": "Content Quality"},
        "seo":             {"score": seo,    "max": 20, "label": "SEO & Keywords"},
        "structure":       {"score": struct, "max": 10, "label": "Structure & HTML"},
        "readability":     {"score": read,   "max": 15, "label": "Readability"},
        "eeat":            {"score": eeat,   "max": 15, "label": "E-E-A-T"},
        "links":           {"score": links,  "max": 10, "label": "Links"},
        "aeo":             {"score": aeo,    "max": 10, "label": "AI/AEO Readiness"},
        "language":        {"score": lang,   "max": 5,  "label": "Language & Style"},
        "content_intelligence": {"score": ci, "max": 36, "label": "Content Intelligence"},
        "conversion":      {"score": conv,   "max": 15, "label": "Conversion & Persuasion"},
        "ai_humanization": {"score": human,  "max": 12, "label": "AI Humanization"},
        "semantic_depth":  {"score": semdeep, "max": 12, "label": "Semantic Depth"},
        "customer_context": {"score": ctx,   "max": 12, "label": "Customer Context"},
        "snippet_optimization": {"score": snip, "max": 10, "label": "Snippet Optimization"},
        "numeric_consistency": {"score": nc,   "max": 5,  "label": "Numeric Consistency"},
    }

    pillars = [
        {
            "name": v["label"],
            "key": k,
            "score": v["score"],
            "max": v["max"],
            "pct": round(v["score"] / v["max"] * 100) if v["max"] else 0,
        }
        for k, v in categories.items()
    ]

    passed_rules = [r for r in rules if r["passed"]]
    failed_rules = [r for r in rules if not r["passed"]]

    grade = (
        "A" if percentage >= 85 else
        "B" if percentage >= 70 else
        "C" if percentage >= 55 else
        "D" if percentage >= 40 else "F"
    )

    summary = {
        "passed_count": len(passed_rules),
        "failed_count": len(failed_rules),
        "total_rules": len(rules),
        "grade": grade,
    }

    return {
        "score": total_earned,
        "percentage": percentage,
        "total_earned": total_earned,
        "max_possible": max_possible,
        "categories": categories,
        "issues": issues,
        "rules": rules,
        "pillars": pillars,
        "summary": summary,
        "word_count": word_count,
        "kw_density": round(kw_density, 2),
        "kw_density_raw": round(kw_density_raw, 2),
    }

"""
Prompt Manager — manages editable instruction blocks for each pipeline step.

Custom prompts are stored in custom_prompts.json at the project root.
The pipeline reads the custom block (if saved) instead of the hardcoded default.
"""
import json
import os
from datetime import datetime, timezone

CUSTOM_PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "..", "custom_prompts.json")
PROMPT_VERSIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "prompt_versions.json")
_MAX_VERSIONS = 10  # per key

# Default instruction blocks per step — these are what appear in the Prompt Editor
# and what the pipeline uses when no custom block has been saved.
PROMPT_KEYS: dict = {
    "step1_research_instructions": {
        "label": "Step 1: Research Instructions",
        "tier": "active_v2",
        "desc": "Instructions for the research/competitor analysis step. Controls what themes, gaps, angles, and facts the AI extracts.",
        "default": """━━━ RESEARCH INSTRUCTIONS ━━━
Analyse the keyword and any crawled competitor pages.

YOU MUST RETURN:
- themes: TOP 5 content themes from ranking pages
- gaps: TOP 3 content gaps missing from competitors
- angles: TOP 3 unique angles we can take
- key_facts: 5+ verifiable facts with sources

QUALITY REQUIREMENTS:
- Be specific — cite actual findings, not generic observations
- Identify what competitors MISS, not just what they cover
- Focus on user intent: what does the searcher really want?
- Look for E-E-A-T signals: what experience/expertise can we add?
- Note any local/regional relevance opportunities

{customer_context}""",
    },
    "step2_structure_rules": {
        "label": "Step 2: Structure Rules",
        "tier": "active_v2",
        "desc": "Injected into structure generation — forbidden heading patterns, required question headings, power words.",
        "default": """\u2501\u2501\u2501 STRUCTURE RULES (MANDATORY) \u2501\u2501\u2501
FORBIDDEN H2 patterns \u2014 these cause automatic content scoring failure:
  \u2717 Any H2 starting with \u201cUnderstanding [X]\u201d
  \u2717 Any H2 starting with \u201cBenefits of [X]\u201d
  \u2717 Any H2 starting with \u201cOverview of [X]\u201d
  \u2717 Any H2 starting with \u201cIntroduction to [X]\u201d
  \u2717 Any H2 starting with \u201cAll You Need to Know About [X]\u201d

REQUIRED \u2014 at least 3 H2s must be question-format:
  \u2713 \u201cWhat Is\u2026?\u201d  \u2713 \u201cHow Do/Does\u2026?\u201d  \u2713 \u201cWhy Does\u2026?\u201d  \u2713 \u201cWhich\u2026Is Best?\u201d

REQUIRED \u2014 H1 must contain one power word:
  best / proven / ultimate / complete / expert guide / essential / definitive

REQUIRED \u2014 H2s must be specific with numbers or concrete details:
  BAD:  \u201cBenefits of Black Pepper\u201d
  GOOD: \u201c5 Clinically-Backed Benefits of Black Pepper for Digestion\u201d

Include "toc_anchors" in JSON with URL-safe IDs matching each H2.

━━━ READABILITY PLANNING (R16-R18 — machine-checked) ━━━
  - Each section word_target should support 3-4 short paragraphs (40-80 words each)
  - Plan for sentence variety: mix short (8-12 word) and medium (18-22 word) sentences
  - Target Flesch Reading Ease 50-75 (professional but accessible, not academic)
  - No paragraph should exceed 80 words (3 sentences max)

━━━ E-E-A-T PLANNING (R20-R23 — machine-checked) ━━━
  - Plan at least 2 sections that will include authority citations ("research shows", "study found", "according to")
  - Plan at least 1 section for a case study or real-world example with specific data
  - Include "authority_note" in each h2_section to indicate what data/citation belongs there
  - Plan CTA placement in conclusion section

━━━ LINK PLACEMENT PLANNING (R24-R26 — machine-checked) ━━━
  - Plan at least 2 sections where internal links (/products/, /guides/) fit naturally
  - Plan at least 2 sections where external authority links (PubMed, .gov, Wikipedia) belong
  - Include "link_slot" in each h2_section: "internal", "external", "wikipedia", or "none"
  - At least 1 section must be earmarked for a Wikipedia reference""",
    },
    "step6_quality_rules": {
        "label": "Step 6: Draft Quality Rules",
        "tier": "active_v2",
        "desc": "Injected into the content drafting prompt — TOC, hook, experience, entities, authority links, etc.",
        "default": """\u2501\u2501\u2501 QUALITY RULES \u2014 ALL MANDATORY \u2501\u2501\u2501

TOC (P3.25 \u2014 CRITICAL): Open the article body with a table of contents:
  <nav class="toc"><ul><li><a href="#section-anchor">Heading</a></li>\u2026</ul></nav>
  Add matching id="section-anchor" attribute to every <h2> tag.

HOOK (P7.61): The very first sentence must open with a question, specific stat, or bold claim.
  BAD:  \u201cBlack pepper is a popular spice.\u201d
  GOOD: \u201cDid you know black pepper boosts curcumin absorption by 2000%?\u201d

EXPERIENCE (G2): Include 2-3 authentic first-person signals:
  \u201cWhen we tested this\u2026\u201d, \u201cIn our experience\u2026\u201d, \u201cI found that\u2026\u201d

ENTITIES (G3): 6+ named entities per 1000 words \u2014 researchers, studies with year+journal, locations, companies.
  Example: \u201cA 2019 study in Critical Reviews in Food Science (Panjab University)\u2026\u201d

DATES (P2.14): Include 2+ specific years/dates: \u201cResearch from 2023\u2026\u201d, \u201cA 2021 Journal of Nutrition study\u2026\u201d

CASE STUDY (P2.17): One real-world example:
  \u201cCase study: [scenario] \u2192 [outcome]\u201d or \u201cIn practice: [example with result]\u201d

AUTHORITY LINKS (P2.12): 2+ external links to PubMed, Wikipedia, .gov, or .edu:
  <a href="https://pubmed.ncbi.nlm.nih.gov/XXXXXXX/" target="_blank" rel="noopener">Study Name (Year)</a>

OBJECTIONS (P7.65): Address one reader doubt:
  \u201cYou might wonder\u2026\u201d / \u201cA common concern is\u2026\u201d / \u201cSome believe X, but research shows Y\u2026\u201d

LIMITATIONS (P6.60): Acknowledge one limitation:
  \u201cHowever, keep in mind\u2026\u201d / \u201cThe caveat here is\u2026\u201d / \u201cImportant to note\u2026\u201d

STORYTELLING (P7.68): 2+ storytelling markers:
  \u201cFor example, imagine\u2026\u201d / \u201cPicture this:\u201d / \u201cWhen we analysed\u2026\u201d

PERSONAL PRONOUNS (P7.66): Use \u201cyou/your/we/our/I\u201d \u2014 5+ total occurrences.

QUESTION HEADINGS (G8): At least 3 H2s must be question-format:
  \u2713 \u201cWhat Is\u2026?\u201d  \u2713 \u201cHow Does\u2026?\u201d  \u2713 \u201cWhy Does\u2026?\u201d  \u2713 \u201cWhich\u2026Is Best?\u201d

LONG-TAIL KEYWORDS (P9.88): 2+ semantic keyword variations with modifiers.

E-E-A-T: One quotable fact per H2 (study name, percentage, year). Active voice >85%.

━━━ MACHINE-CHECKED RULES — EXACT THRESHOLDS ━━━

AUTHORITY SIGNALS (R20 — 5pts, machine-checked):
  Use 5+ of these EXACT phrases in your text (the scorer counts exact string matches):
  ✓ "according to"  ✓ "research shows"  ✓ "study found"  ✓ "study published"
  ✓ "data shows"  ✓ "evidence suggests"  ✓ "published in"  ✓ "scientific"
  ✓ "peer-reviewed"  ✓ "clinical trial"  ✓ "experts say"
  Sprinkle across different sections — e.g.:
    Section 1: "According to a 2024 study published in the Journal of Nutrition..."
    Section 3: "Research shows that regular consumption improves..."
    Section 5: "Data shows a 42% improvement in outcomes..."

DATA POINTS (R21 — 4pts, machine-checked):
  Include 5+ numbers matching these patterns: percentages (42%), 4-digit years (2024), measurements (100mg, 5g, 200ml)
  Example: "A 2023 study reported a 67% improvement using 500mg daily doses"

READABILITY (R16-R18 — 12pts total, machine-checked):
  R16: Average sentence length MUST be 12-22 words. Mix short (8 words) and medium (20 words).
    SHORT: "Black pepper enhances nutrient absorption significantly."
    MEDIUM: "According to a 2023 study published in the Journal of Nutrition, black pepper contains powerful bioactive compounds."
  R17: ZERO paragraphs over 100 words. Keep each <p> tag to 40-80 words (2-3 sentences max).
  R18: Flesch Reading Ease 50-75. Use conversational professional tone, not academic.

SENTENCE OPENERS (R19 — 3pts, machine-checked):
  Never start 4+ sentences with the same 2-word opening. Vary: questions, "When...", "For...", "In 2024...", etc.

INTERNAL LINKS (R24 — 5pts, machine-checked):
  Include 4+ <a href="/..."> internal links (href MUST start with /).

EXTERNAL LINKS (R22/R25 — 6pts, machine-checked):
  Include 3+ <a href="http..."> external links to authoritative sources.

WIKIPEDIA (R26 — 2pts, machine-checked):
  Include at least 1 <a href="...wikipedia.org..."> link.

CTA (R23 — 3pts, machine-checked):
  Last 500 characters must contain one of: buy, shop, order, contact, get started, learn more, discover, try.

━━━ ANTI-KEYWORD-STUFFING (R34 — 4pts, machine-checked) ━━━
  Keyword density MUST stay between 1.0-1.5%. Over 3% = KEYWORD STUFFING penalty.
  Use 5+ semantic variations instead of repeating exact keyword.
  Replace every 3rd keyword mention with a synonym or LSI phrase.

━━━ HUMANIZATION (R35-R36 — 8pts, machine-checked) ━━━
  R35: ZERO AI fluff phrases allowed. No "furthermore", "moreover", "it's worth noting", "let's dive in".
  R36: 3+ experience signals required: "we tested", "in our experience", "we found", "hands-on".
  Write like a knowledgeable human sharing real insights, not an AI summarizing information.

━━━ FORBIDDEN HOOK PHRASES (R47 — automatic deduction) ━━━
  These repetitive AI paragraph-opener patterns are detected and penalised. NEVER use them:
    ✗ "The real issue is..."       ✗ "And the catch is..."
    ✗ "Here's the thing:"         ✗ "But here's the thing"
    ✗ "Honestly, the catch"       ✗ "Here's what's interesting"
    ✗ "The truth is,"             ✗ "Here's the deal"
    ✗ "Let's be honest"           ✗ "The thing is,"
  Use direct declarative statements instead. Start with the fact, not a meta-comment about the fact.""",
    },
    "step7_review_criteria": {
        "label": "Step 7: Review Criteria",
        "tier": "legacy",
        "desc": "16-point evaluation criteria injected into the quality review step.",
        "default": """Evaluate these 35 criteria (all machine-checked — exact thresholds):
1. Keyword relevance and density (1.5-2.5% target, machine-checked R06)
2. Topic coverage completeness (6+ H2 sections? machine-checked R03/R13)
3. Tone: professional, helpful, expert
4. E-E-A-T signals: are 5+ exact authority phrases present? ("according to", "research shows", "study found", "study published", "data shows", "evidence suggests", "published in" — machine-checked R20)
5. Readability: avg sentence length 12-22 words? (machine-checked R16)
6. Grammar and language quality
7. Factual accuracy: are 5+ specific data points present? (percentages, years, measurements — machine-checked R21)
8. CTA in last 500 characters? ("buy", "shop", "contact", "learn more" etc. — machine-checked R23)
9. TOC present? (required: <nav class="toc"> block for articles >1000 words)
10. Hook quality: does the first sentence open with a question, stat, or bold claim?
11. First-person signals: are 2+ authentic "I/we tested/found" statements present?
12. Named entities: are 6+ named entities per 1000 words present?
13. External authority links: are 3+ <a href="http..."> present? (machine-checked R22/R25 — need 3+)
14. Date references: are 2+ specific years cited in the body?
15. Objection addressed: does the article address at least one reader doubt?
16. Limitation acknowledged: does the article acknowledge one limitation or caveat?
17. Internal links: are 4+ <a href="/..."> internal links present? (machine-checked R24 — need 4+)
18. Wikipedia reference: is at least 1 link to wikipedia.org present? (machine-checked R26)
19. Paragraph length: are all paragraphs under 100 words? (machine-checked R17)
20. Sentence opener variety: no 4+ sentences starting with same 2-word opener? (machine-checked R19)
21. Flesch Reading Ease: is score between 50-75? (machine-checked R18)
22. Passive voice: under 20%? (machine-checked R31)
23. Semantic variation: are 5+ keyword variants used instead of exact repetition? (machine-checked R34)
24. AI patterns: fewer than 2 AI fluff phrases per 1000 words? (machine-checked R35)
25. Experience signals: 3+ first-person experience markers? (machine-checked R36)
26. Entity richness: 8+ unique named entities? (machine-checked R37)
27. Featured snippet blocks: 2+ question headings with 30-60 word direct answers? (R38)
28. Comparison table: at least one table with 3+ rows × 3+ columns? (R39)
29. Buyer intent section: decision-making guidance present? (R40)
30. Storytelling: 2+ narrative markers? (R41)
31. Visual breaks: 2+ blockquotes/callouts/tip boxes? (R42)
32. Mid-content CTA: call-to-action in middle of article? (R43)
33. Data credibility: all statistics have source attribution within 150 chars? (R44)
34. Unique angle: differentiation markers present? (R45)
35. FAQ answer quality: answers average 40-60 words? (R46)""",
    },
    "step9_quality_rules": {
        "label": "Step 9: Redevelopment Quality Rules",
        "tier": "legacy",
        "desc": "Quality rules injected into the redevelopment prompt to guide issue-fixing rewrite.",
        "default": """\u2501\u2501\u2501 QUALITY RULES \u2014 ALL MANDATORY \u2501\u2501\u2501

TOC (P3.25 \u2014 CRITICAL): Open the article body with a table of contents:
  <nav class="toc"><ul><li><a href="#section-anchor">Heading</a></li>\u2026</ul></nav>
  Add matching id="section-anchor" attribute to every <h2> tag.

HOOK (P7.61): The very first sentence must open with a question, specific stat, or bold claim.
EXPERIENCE (G2): Include 2-3 authentic first-person signals: \u201cWhen we tested this\u2026\u201d, \u201cIn our experience\u2026\u201d
ENTITIES (G3): 6+ named entities per 1000 words \u2014 researchers, studies with year+journal, locations, companies.
DATES (P2.14): Include 2+ specific years/dates: \u201cResearch from 2023\u2026\u201d, \u201cA 2021 Journal of Nutrition study\u2026\u201d
CASE STUDY (P2.17): One real-world example: \u201cCase study: [scenario] \u2192 [outcome]\u201d
AUTHORITY LINKS (P2.12): 2+ external links to PubMed, Wikipedia, .gov, or .edu
OBJECTIONS (P7.65): Address one reader doubt: \u201cYou might wonder\u2026\u201d / \u201cSome believe X, but research shows Y\u2026\u201d
LIMITATIONS (P6.60): Acknowledge one limitation: \u201cHowever, keep in mind\u2026\u201d / \u201cThe caveat here is\u2026\u201d
STORYTELLING (P7.68): 2+ storytelling markers: \u201cFor example, imagine\u2026\u201d / \u201cWhen we analysed\u2026\u201d
PERSONAL PRONOUNS (P7.66): Use \u201cyou/your/we/our/I\u201d \u2014 5+ total occurrences.
QUESTION HEADINGS (G8): At least 3 H2s must be question-format.
LONG-TAIL KEYWORDS (P9.88): 2+ semantic keyword variations with modifiers.
E-E-A-T: One quotable fact per H2 (study name, percentage, year). Active voice >85%.

━━━ MACHINE-CHECKED RULES — EXACT THRESHOLDS ━━━

AUTHORITY SIGNALS (R20 — 5pts): Use 5+ of these EXACT phrases:
  "according to", "research shows", "study found", "study published",
  "data shows", "evidence suggests", "published in", "scientific",
  "peer-reviewed", "clinical trial", "experts say"

DATA POINTS (R21 — 4pts): Include 5+ of: percentages (42%), years (2024), measurements (100mg).

READABILITY (R16-R18 — 12pts):
  R16: Avg sentence 12-22 words. Mix short (8w) and medium (20w).
  R17: ZERO paragraphs over 100 words. Keep each <p> to 2-3 sentences.
  R18: Flesch 50-75. Professional but not academic.

OPENERS (R19 — 3pts): Never start 4+ sentences with same 2-word opening.

LINKS (R24/R25/R26 — 10pts):
  R24: 4+ internal <a href="/...">. R25: 3+ external <a href="http...">.
  R26: 1+ wikipedia.org link. PRESERVE existing links — do not remove any <a href>.

CTA (R23 — 3pts): Last 500 chars must contain: buy/shop/order/contact/learn more/discover/try.

━━━ CONTENT INTELLIGENCE — MACHINE-CHECKED (R34-R46) ━━━

R34 SEMANTIC VARIATION (4pts): Use 5+ semantic variants of keyword. Density MUST be 1.0-1.5%, NEVER >3%.
R35 AI PATTERNS (4pts): ZERO AI fluff: no "furthermore", "moreover", "it's worth noting", "let's dive in", "when it comes to", "the real issue is", "and the catch is", "here's the thing", "the truth is,", "here's the deal", "let's be honest". <2 per 1000 words.
R36 EXPERIENCE (4pts): 3+ of: "we tested", "we found", "in our experience", "we observed", "hands-on", "we discovered".
R37 ENTITIES (3pts): 8+ named entities (places, products, orgs, researchers). Be specific.
R38 SNIPPET BLOCKS (3pts): 2+ question headings followed by 30-60 word direct answer paragraphs.
R39 TABLE QUALITY (2pts): Table with ≥3 rows × ≥3 columns.
R40 BUYER INTENT (3pts): Include "which should you buy" / "how to choose" / "best for" section.
R41 STORYTELLING (2pts): 2+ narrative markers: "when we", "we discovered", "the result was", "picture this".
R42 VISUAL BREAKS (2pts): 2+ <blockquote> or <div class="tip"> or <div class="key-takeaway">.
R43 MID-CTA (2pts): CTA in middle of article, not just end.
R44 DATA CREDIBILITY (3pts): Every statistic needs source within 150 chars. No fabricated precise numbers.
R45 UNIQUE ANGLE (2pts): "what most people miss" / "the real truth" / "our perspective".
R46 FAQ QUALITY (2pts): FAQ answers 40-60 words each — direct and complete.

PRESERVE existing links — do not remove any <a href>.""",
    },
    "step6_intelligence_rules": {
        "label": "Step 6: Content Intelligence Rules",
        "tier": "active_v2",
        "desc": "Machine-checked content intelligence rules (R34-R46) injected into every section prompt. Controls AI detection, experience signals, entity richness, snippet structure, conversion hooks, and data credibility at generation time — before draft is written.",
        "default": """━━━ PRE-DRAFT CONTENT INTELLIGENCE CONTRACT ━━━

HOOK ENFORCEMENT (intro only):
  The first sentence must open with ONE of these patterns — not a generic topic intro:
    ✓ STAT SHOCK:  "If you're paying ₹500/kg more than your competitor, you're losing margin before you sell."
    ✓ BUYER PAIN:  "Most bulk buyers discover the real cost of cardamom after their first shipment — too late."
    ✓ DIRECT CLAIM: "In Kerala markets, prices can spike 20-40% within a single season."
    ✗ FORBIDDEN:   "The bulk cardamom wholesale price is a significant consideration for businesses..."
    ✗ FORBIDDEN:   "Understanding [topic] is essential for..."
    ✗ FORBIDDEN:   "This guide will provide you with..."

SECTION OUTPUT SHAPE (enforced in Step 7 validation):
  Each section promised a specific artifact in its contract. Deliver it:
    - "Cost Calculator" or "Cost Breakdown" → include FORMULA: Total = Base + Freight + GST + Storage + Loss
    - "Comparison" or "vs" headings → include a <table> with ≥3 rows × ≥3 columns
    - "FAQ" or "Questions" → each answer must be 40-60 words, direct, not padded
    - "Factors" or "Drivers" → explain cause→effect chain, not list of names
  Do NOT write a prose paragraph when the heading promises a calculator, table, or formula.

FACT CONSISTENCY (machine-checked across all sections):
  All numeric claims (prices, percentages, weights, quantities) must be:
    ✓ Consistent — the same metric cannot have contradictory values in different sections
    ✓ Range-sourced — use "₹1,800–₹3,500/kg depending on grade" not "₹2,200/kg exactly"
    ✓ Season-qualified — "during harvest (Oct–Dec) prices dip; off-season prices spike"
  BAD: Intro says ₹1,850–2,050/kg, FAQ answers ₹2,800–4,500/kg for the same grade
  GOOD: Establish ONE unified range in the intro, then explain variation factors in body sections

SEMANTIC VARIATION (R34 — 4pts, machine-checked):
  NEVER repeat the exact keyword phrase more than necessary (target density 1.0-1.5%).
  Use 5+ semantic variations: synonyms, related phrases, LSI terms.

AI PATTERN AVOIDANCE (R35 — 4pts, machine-checked):
  ABSOLUTELY FORBIDDEN phrases — each detected occurrence costs scoring points:
    ✗ "It's worth noting"    ✗ "In today's fast-paced"    ✗ "Let's dive in"
    ✗ "When it comes to"    ✗ "Furthermore,"              ✗ "Moreover,"
    ✗ "Additionally,"       ✗ "It is important to note"  ✗ "This comprehensive guide"
    ✗ "In this article, we" ✗ "The real issue is"        ✗ "Here's the thing:"
    ✗ "The truth is,"       ✗ "Here's the deal"          ✗ "Let's be honest"
    ✗ "significant consideration for businesses"
  Write directly: short declarative statements, opinions, real-world observations.

AUTHORITY INTEGRITY (not fake authority):
  ✗ BAD: "In our experience..." with no backing data
  ✗ BAD: "Research shows that..." with no named source
  ✓ GOOD: "In Kerala auction centers, traders often hold stock to create artificial scarcity."
  ✓ GOOD: "According to Spices Board India data, AAA-grade prices swing 20-40% between harvest and off-season."
  If no named source exists: use industry estimates, approximate ranges, or plain prose without attribution.
  NEVER fabricate: study names, percentages, regulatory approvals, or organization claims.

EXPERIENCE SIGNALS (R36 — 4pts, machine-checked):
  Include 3+ of these EXACT phrases naturally across different sections:
    ✓ "we tested"  ✓ "we found"  ✓ "in our experience"  ✓ "we observed"
    ✓ "after trying"  ✓ "hands-on"  ✓ "first-hand"  ✓ "we discovered"

ENTITY RICHNESS (R37 — 3pts, machine-checked):
  Include 8+ unique named entities — specific place names, organizations, certifications:
    ✓ "Idukki" ✓ "Wayanad" ✓ "Spices Board India" ✓ "Kerala" ✓ "Malabar"

FEATURED SNIPPET BLOCKS (R38 — 3pts, machine-checked):
  After 2+ question-format headings (ending with ?), the VERY NEXT <p> must be
  a direct 30-60 word answer. Do not start with "Yes" or "Great question."

CONVERSION (R43 — 2pts, machine-checked):
  For commercial/buyer-intent content: include a mid-content contextual CTA.
  For FAQ sections: last answer should naturally lead to a next-step action.

DATA CREDIBILITY (R44 — 3pts, machine-checked):
  Every precise statistic (42%, 67.5%) MUST have a source reference within 150 characters.
  Use approximate ranges ("more than half", "typically 20-40%") when no source is available.""",
    },

    "step3_verify_instructions": {
        "label": "Step 3: Verify Structure",
        "tier": "active_v2",
        "desc": "Rules and criteria for verifying/refining the article structure before content generation.",
        "default": """━━━ STRUCTURE VERIFICATION RULES ━━━
Check and fix these critical issues:

H1 RULES:
  ✓ Must contain primary keyword (or close variant)
  ✓ Must include a power word: best, proven, ultimate, complete, expert, essential, definitive
  ✗ Must NOT be generic: "Everything You Need to Know About X"

H2 RULES:
  ✓ Minimum 6 H2 sections for comprehensive coverage
  ✓ At least 3 must be question-format (What/How/Why/Which)
  ✓ Must be specific with numbers or concrete details
  ✗ FORBIDDEN: "Understanding X", "Benefits of X", "Overview of X", "Introduction to X"

STRUCTURE RULES:
  ✓ Must include FAQ section (5+ questions)
  ✓ Must include comparison/decision section
  ✓ Each section must serve a distinct sub-intent
  ✓ Structure must flow: intro → education → comparison → decision → FAQ

{customer_context}""",
    },
    "step4_link_planning": {
        "label": "Step 4: Link Planning",
        "tier": "active_v2",
        "desc": "Rules for planning internal links, external authority links, and Wikipedia references.",
        "default": """━━━ LINK PLANNING RULES ━━━

INTERNAL LINKS (R24 — 5pts):
  ✓ Plan 4+ internal links to related pages on the site
  ✓ Use natural, descriptive anchor text (not "click here")
  ✓ Place links contextually in early + mid content
  ✗ Don't link in every paragraph — space them naturally
  ✗ Don't use keyword-stuffed anchors

EXTERNAL LINKS (R25 — 3pts):
  ✓ Plan 3+ external links to authoritative sources
  ✓ Prefer: government sites (.gov), research (.edu), industry authorities
  ✓ Use specific anchor text describing the source

WIKIPEDIA (R26 — 2pts):
  ✓ Include at least 1 Wikipedia reference for topical authority
  ✓ Link to relevant Wikipedia articles about key concepts

LINK PLACEMENT:
  ✓ Spread links across sections — not clustered in one area
  ✓ Early links (first 1/3) build authority signals
  ✓ Mid-content links support specific claims
  ✓ End links guide next actions

{customer_context}""",
    },
    "step5_reference_rules": {
        "label": "Step 5: Reference & Citation Rules",
        "tier": "active_v2",
        "desc": "Rules for Wikipedia, PubMed, and other reference sources used in the article.",
        "default": """━━━ REFERENCE & CITATION RULES ━━━

AUTHORITY SOURCES:
  ✓ Wikipedia — for general topic definitions and background
  ✓ PubMed / NCBI — for health, science, nutrition claims
  ✓ Government sites (.gov) — for regulations, safety, standards
  ✓ Industry bodies — for market data, certifications
  ✓ Academic journals — for research claims

CITATION QUALITY:
  ✓ Every statistic must have a source within 150 characters (R44)
  ✓ Use specific years: "A 2023 study found..." not "Studies show..."
  ✓ Include journal/publisher names when possible
  ✓ Use real, verifiable sources — no fabricated references

FORMAT:
  ✓ External links open in new tab: target="_blank" rel="noopener"
  ✓ Use descriptive anchor text: "2023 USDA Report" not "source"

{customer_context}""",
    },
    "step10_scoring_rules": {
        "label": "Step 10: Final Scoring",
        "tier": "legacy",
        "desc": "Configuration for the final scoring pass — which rule pillars matter most and minimum thresholds.",
        "default": """━━━ FINAL SCORING CONFIGURATION ━━━

The content is scored across 14 pillars (73 rules, 237 pts):

CRITICAL PILLARS (must score ≥70%):
  - SEO & Keywords (20 pts): density, placement, semantic variations
  - E-E-A-T (15 pts): authority signals, data points, external links
  - Content Intelligence (36 pts): AI patterns, experience, entities, snippets
  - Conversion & Persuasion (15 pts): decision guidance, trust signals, CTAs

IMPORTANT PILLARS (should score ≥60%):
  - Readability (15 pts): sentence length, Flesch score, paragraph length
  - Links (10 pts): internal links, external links, Wikipedia
  - AI Humanization (12 pts): opinions, nuance, sentence variety
  - Semantic Depth (12 pts): what/why/how coverage, use cases, subtopics

SUPPORTING PILLARS:
  - Content Quality (15 pts): word count, paragraphs, headings
  - Structure & HTML (10 pts): FAQ, heading counts, keyword placement
  - AI/AEO Readiness (10 pts): definitions, scannable lists, bold terms
  - Language & Style (5 pts): passive voice, transitions, language
  - Customer Context (12 pts): brand mentions, location, audience alignment
  - Snippet Optimization (10 pts): definitions, steps, comparison tables

MINIMUM QUALITY SCORE: 90%
CRITICAL RULES (must all pass): R20, R24, R25, R26, R34, R35, R36, R44""",
    },
    "step11_quality_loop": {
        "label": "Step 11: Quality Improvement Loop",
        "tier": "legacy",
        "desc": "Instructions for the iterative quality improvement loop — what to fix and how.",
        "default": """━━━ QUALITY IMPROVEMENT LOOP ━━━

This step runs up to 5 improvement passes. Each pass:
1. Scores current content against 73 rules
2. Identifies failed rules sorted by point impact
3. Sends targeted fix instructions to AI
4. Re-scores and keeps only if improved

PRIORITY FIX ORDER:
  1. Critical rules first: R20 (authority), R24 (internal links), R25 (external), R34 (semantic)
  2. Highest point-loss rules next
  3. Customer context rules (brand, location, audience)
  4. Humanization and conversion rules last

FIX STRATEGIES:
  - Low word count → expand with examples, use cases, deeper analysis
  - Missing authority signals → inject "According to...", "Research shows..."
  - AI patterns detected → rewrite with natural tone, vary sentence structure
  - Missing brand/location → weave in brand name and target locations naturally
  - No decision section → add "Who Should Buy" or comparison guidance
  - Missing snippets → add 40-60 word direct answers after question headings

STOP CONDITIONS:
  - Score ≥ 90% AND all critical rules pass
  - 5 passes reached (prevent infinite loop)
  - No improvement in 2 consecutive passes

{customer_context}""",
    },
}


class PromptManager:
    _instance = None

    @classmethod
    def get_instance(cls) -> "PromptManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._custom: dict = {}
        self._versions: dict = {}
        self._reload()

    def _reload(self):
        try:
            if os.path.exists(CUSTOM_PROMPTS_FILE):
                with open(CUSTOM_PROMPTS_FILE, encoding="utf-8") as f:
                    self._custom = json.load(f)
        except Exception:
            self._custom = {}
        try:
            if os.path.exists(PROMPT_VERSIONS_FILE):
                with open(PROMPT_VERSIONS_FILE, encoding="utf-8") as f:
                    self._versions = json.load(f)
        except Exception:
            self._versions = {}

    def _persist(self):
        try:
            with open(CUSTOM_PROMPTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._custom, f, indent=2, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger("annaseo.prompts").warning(f"Could not save custom prompts: {e}")

    def _persist_versions(self):
        try:
            with open(PROMPT_VERSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._versions, f, indent=2, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger("annaseo.prompts").warning(f"Could not save prompt versions: {e}")

    def get(self, key: str) -> str:
        """Return custom prompt block if saved, else the default."""
        if key in self._custom:
            return self._custom[key]
        return PROMPT_KEYS.get(key, {}).get("default", "")

    def set(self, key: str, content: str):
        if key not in PROMPT_KEYS:
            raise ValueError(f"Unknown prompt key: {key!r}")
        # Archive current version before overwriting
        old_content = self._custom.get(key) or PROMPT_KEYS[key]["default"]
        if key not in self._versions:
            self._versions[key] = []
        self._versions[key].append({
            "content": old_content,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "label": f"v{len(self._versions[key]) + 1}",
        })
        # Keep only the last N versions
        self._versions[key] = self._versions[key][-_MAX_VERSIONS:]
        self._persist_versions()
        self._custom[key] = content
        self._persist()

    def reset(self, key: str):
        self._custom.pop(key, None)
        self._persist()

    def get_versions(self, key: str) -> list:
        """Return saved version history for a key (newest first)."""
        return list(reversed(self._versions.get(key, [])))

    def restore_version(self, key: str, version_index: int) -> str:
        """Restore a version by index (0 = newest). Returns the restored content."""
        versions = self.get_versions(key)
        if version_index < 0 or version_index >= len(versions):
            raise ValueError(f"Version index {version_index} out of range")
        content = versions[version_index]["content"]
        self.set(key, content)
        return content

    def has_custom(self, key: str) -> bool:
        return key in self._custom

    def all_prompts(self) -> list:
        return [
            {
                "key": k,
                "label": v["label"],
                "desc": v["desc"],
                "tier": v.get("tier", "active_v2"),
                "content": self.get(k),
                "is_custom": self.has_custom(k),
                "default": v["default"],
            }
            for k, v in PROMPT_KEYS.items()
        ]

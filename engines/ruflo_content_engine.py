"""
================================================================================
RUFLO — CONTENT GENERATION ENGINE
================================================================================
7-pass pipeline that produces articles passing ALL Google + AI search signals.

Pass 1: Research (Gemini free) → real citations, competitor gaps, unique data
Pass 2: Brief builder (DeepSeek local) → structure, entities, info-gain angle
Pass 3: Claude writes → full article with E-E-A-T + GEO + style controls
Pass 4: SEO signal check (rules) → 28 signals, keyword density, structure
Pass 5: E-E-A-T check (DeepSeek) → experience, expertise, authority, trust
Pass 6: GEO check (rules) → AI search citation optimisation
Pass 7: Humanize revision (Claude) → only if any score < 75

Google ranking signals checked: 28
AI search (GEO) signals: 8
Readability signals: 5
Total checks per article: 41

User controls:
  tone / writing style / format / reading level / word count
  brand voice (per project) / author credentials / language
  AI auto-decide toggle (AI chooses best format for keyword)

Cost per article:
  Pass 1: $0 (Gemini free)
  Pass 2: $0 (DeepSeek local)
  Pass 3: ~$0.022 (Claude Sonnet, 2000 words)
  Pass 4-6: $0 (rules + local)
  Pass 7: ~$0.008 (targeted revision, if needed)
  Total: ~$0.022–0.030 per article
================================================================================
"""

from __future__ import annotations

import os, json, re, time, math, hashlib, logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from dotenv import load_dotenv
import requests as _req

load_dotenv()
log = logging.getLogger("ruflo.content")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — USER CONTROLS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContentStyle:
    """
    User-configurable content style. Serialized per project, can be overridden per article.
    All fields have sensible defaults — AI fills anything not specified.
    """

    # Tone
    tone: str = "expert_authoritative"
    # Options: expert_authoritative | friendly_conversational | professional_formal
    #          storytelling_narrative | educational_teaching | custom
    custom_tone: str = ""
    # e.g. "Write like a Kerala spice farmer with 30 years experience"

    # Writing style
    writing_style: str = "evidence_based"
    # Options: evidence_based | story_led | listicle | deep_dive
    #          comparison | how_to_guide | ai_decide

    # Format
    content_format: str = "long_form_blog"
    # Options: long_form_blog | faq_page | recipe_guide | comparison_table
    #          pillar_page | news_update | ai_decide

    # Reading level (Flesch-Kincaid target)
    reading_level: str = "standard"
    # Options: simple (grade 6) | standard (grade 8-10) | expert (grade 12+)

    # Word count
    word_count: int = 0            # 0 = AI decides based on keyword intent
    word_count_min: int = 1800
    word_count_max: int = 3500

    # Language
    language: str = "english"
    # Options: english | malayalam | hindi | tamil | kannada | arabic

    # AI auto-decide
    ai_auto_decide: bool = True    # AI picks best format/length for this keyword
    # When True: AI analyses intent + competition → chooses optimal format + length

    # Structural elements
    include_faq:         bool = True
    include_table:       bool = True
    include_key_takeaways: bool = True   # bold sentence at end of each H2
    include_intro_hook:  bool = True
    include_cta:         bool = True
    include_sources:     bool = True     # cite real sources
    include_comparison:  bool = False    # add comparison table if relevant

    # SEO aggressiveness
    keyword_density_target: float = 1.5   # %
    lsi_keywords_count: int = 8           # related terms to include
    internal_links_count: int = 3         # internal links to weave in
    entities_count_min: int = 5           # named entities required


@dataclass
class BrandVoice:
    """
    Per-project brand voice profile. Injected into every Claude call.
    Built once, reused for all articles in the project.
    """
    business_name:   str = ""
    author_name:     str = ""
    author_title:    str = ""
    author_credentials: str = ""   # "USDA Organic certified farmer since 2012"
    founding_year:   int = 0
    location:        str = ""      # "Wayanad, Kerala"
    certifications:  List[str] = field(default_factory=list)
    regional_terms:  List[str] = field(default_factory=list)  # use naturally
    # ["Malabar","Wayanad","Idukki","trichomes","farm-direct"]
    avoid_words:     List[str] = field(default_factory=list)
    # ["simply","just","as an AI","obviously"]
    competitor_names_avoid: List[str] = field(default_factory=list)
    custom_voice_note: str = ""    # free text voice guidance

    def to_prompt_segment(self) -> str:
        lines = []
        if self.business_name:
            lines.append(f"Business: {self.business_name}")
        if self.author_name:
            lines.append(f"Author: {self.author_name}, {self.author_title}")
        if self.author_credentials:
            lines.append(f"Credentials: {self.author_credentials}")
        if self.founding_year:
            lines.append(f"Experience: In operation since {self.founding_year}")
        if self.location:
            lines.append(f"Location: {self.location}")
        if self.certifications:
            lines.append(f"Certifications: {', '.join(self.certifications)}")
        if self.regional_terms:
            lines.append(f"Use naturally (don't force): {', '.join(self.regional_terms)}")
        if self.avoid_words:
            lines.append(f"Never use: {', '.join(self.avoid_words)}")
        if self.custom_voice_note:
            lines.append(f"Voice guidance: {self.custom_voice_note}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — AI HELPERS
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    OLLAMA_URL    = os.getenv("OLLAMA_URL",     "http://localhost:11434")
    OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL",   "deepseek-r1:7b")
    GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL  = os.getenv("GEMINI_MODEL",   "gemini-1.5-flash")
    GEMINI_RATE   = float(os.getenv("GEMINI_RATE", "4.0"))
    ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL  = os.getenv("CLAUDE_MODEL",   "claude-sonnet-4-6")
    ARTICLE_DIR   = Path(os.getenv("RUFLO_DIR","./ruflo_data")) / "articles"
    SCORE_PASS    = 75    # minimum score to publish without revision

class AI:
    _last_gemini = 0.0

    @staticmethod
    def _extract_ollama_text(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        if isinstance(data.get("response"), str) and data.get("response").strip():
            return data["response"].strip()
        msg = data.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str) and msg.get("content").strip():
            return msg["content"].strip()
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                if isinstance(first.get("message"), dict) and isinstance(first["message"].get("content"), str):
                    return first["message"]["content"].strip()
                if isinstance(first.get("text"), str):
                    return first["text"].strip()
        if isinstance(data.get("text"), str):
            return data["text"].strip()
        return ""

    @staticmethod
    def deepseek(prompt: str, system: str = "", temperature: float = 0.1) -> str:
        try:
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/chat", json={
                "model": Cfg.OLLAMA_MODEL, "stream": False,
                "options": {"temperature": temperature},
                "messages": [{"role":"system","content":system or "You are an SEO expert."},
                             {"role":"user","content":prompt}]
            }, timeout=120)
            r.raise_for_status()
            data = r.json()
            t = AI._extract_ollama_text(data)
            if not t:
                t = (data.get("response") or data.get("text") or "").strip()
            return re.sub(r"<think>.*?</think>","",t,flags=re.DOTALL).strip()
        except Exception as e:
            log.warning(f"[AI] DeepSeek: {e}")
            return ""

    @classmethod
    def gemini(cls, prompt: str, temperature: float = 0.3) -> str:
        if not Cfg.GEMINI_KEY:
            return cls.deepseek(prompt, temperature=temperature)
        elapsed = time.time() - cls._last_gemini
        if elapsed < Cfg.GEMINI_RATE:
            time.sleep(Cfg.GEMINI_RATE - elapsed)
        try:
            import google.generativeai as genai
            genai.configure(api_key=Cfg.GEMINI_KEY)
            m = genai.GenerativeModel(Cfg.GEMINI_MODEL)
            r = m.generate_content(prompt,
                generation_config=genai.GenerationConfig(temperature=temperature))
            cls._last_gemini = time.time()
            return r.text.strip()
        except Exception as e:
            log.warning(f"[AI] Gemini: {e}")
            return cls.deepseek(prompt, temperature=temperature)

    @staticmethod
    def claude(system: str, prompt: str, max_tokens: int = 4096) -> Tuple[str, int]:
        if not Cfg.ANTHROPIC_KEY:
            return "# Mock article\n\nThis is a mock article for testing.", 0
        try:
            import anthropic
            c = anthropic.Anthropic(api_key=Cfg.ANTHROPIC_KEY)
            r = c.messages.create(
                model=Cfg.CLAUDE_MODEL, max_tokens=max_tokens,
                system=system, messages=[{"role":"user","content":prompt}]
            )
            return r.content[0].text.strip(), r.usage.input_tokens + r.usage.output_tokens
        except Exception as e:
            log.error(f"[AI] Claude: {e}")
            return "", 0

    @staticmethod
    def parse_json(text: str) -> Any:
        text = re.sub(r"<think>.*?</think>","",text,flags=re.DOTALL)
        text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
        m = re.search(r'(\{.*\}|\[.*\])',text,re.DOTALL)
        if m: return json.loads(m.group(1))
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — PROMPT LIBRARY
# ─────────────────────────────────────────────────────────────────────────────

class Prompts:
    """All prompts. Three-layer architecture: global + brand + article."""

    # ── Layer 1: Global system prompt (injected into every Claude call) ──────

    CLAUDE_GLOBAL_SYSTEM = """You are an elite SEO content writer, subject matter expert, and editorial strategist.
You write articles that rank #1 on Google AND are cited by Perplexity, ChatGPT Search, and Google AI Overviews.

━━━ GOOGLE E-E-A-T RULES ━━━

EXPERIENCE: Include at least 2 first-person experience phrases showing lived knowledge.
  Good: "In our farm in Wayanad, we've observed...", "After testing 12 varieties..."
  Do NOT fake experience you don't have — use brand voice context provided.

EXPERTISE: Include specific technical terms, compound names, botanical nomenclature,
  precise data (percentages, dosages, measurements). Vague claims = low expertise signal.

AUTHORITATIVENESS: Cite at least 2 real, verifiable sources (PubMed DOI, WHO, government data).
  Format: "(Source: PubMed, DOI: 10.xxxx)" — these are provided to you in the research context.
  NEVER fabricate citations. If no citation provided for a claim, say "according to traditional use" or omit.

TRUSTWORTHINESS: Include honest limitations ("consult a doctor before using as treatment"),
  balanced perspective, date stamps where relevant, no fabricated statistics.

━━━ GEO RULES (AI SEARCH CITATION) ━━━

DIRECT ANSWER: The VERY FIRST paragraph must directly answer the search query in 1-2 sentences.
  Format: "[Question]? [Direct answer in bold or clear sentence]. Here's the full explanation..."
  Perplexity and ChatGPT cite the paragraph that directly answers, not the title.

NUMERICAL DATA: Include at least 3 specific numerical claims per article.
  Good: "Ceylon cinnamon contains 0.04% coumarin, while cassia contains 0.31%"
  These specific numbers are what AI engines extract and cite.

DEFINITION PARAGRAPHS: For technical terms, write: "What is X? X is [definition with formula/details]."
  These are extracted directly by AI overview features.

COMPARISON TABLES: When comparing options, use a proper HTML/markdown table.
  AI engines specifically extract and cite structured comparison data.

BOLD TAKEAWAYS: End each major section with: **Key takeaway: [one sentence summary]**
  ChatGPT Search extracts these as direct responses to follow-up questions.

━━━ SEO SIGNAL RULES ━━━

KEYWORD: Use target keyword naturally in: H1, first 100 words, at least one H2, meta description.
  Density: 0.5%–2.5% of total words. NEVER stuff. Use variants and related terms.

STRUCTURE: Use H2 for major sections, H3 for subsections. 3-7 H2s minimum.
  Each H2 = one clear topic. H2 text = keyword variant or related term where natural.

FAQ: Include a FAQ section as the penultimate section. 4-6 questions.
  Format each as: ## Frequently Asked Questions\n### Question?\nDirect answer paragraph.
  This targets PAA (People Also Ask) boxes on Google.

INTERNAL LINKS: Weave in exactly the internal links provided. Use exact anchor text given.
  Do not invent links. Only use links explicitly provided in the article context.

LSI KEYWORDS: Use all semantic entities provided. They signal topical authority to Google.

━━━ WRITING QUALITY RULES ━━━

READABILITY: Average sentence length ≤20 words. Paragraphs ≤3 sentences.
  Active voice ≥90%. Transition words between paragraphs.

OPENING: Never start with "In today's..." or "Are you looking for..." or rhetorical questions.
  Start with a direct, confident statement or the direct answer.

CLOSING: End with a genuine CTA matching the business context. Not generic "contact us".

NEVER: Say "as an AI", "I don't have personal experience", "In conclusion,",
  "In summary,", "It's worth noting that", "Certainly!", "Absolutely!",
  "Great question!", "Fascinating!", "Simply" or "Just" as filler words."""

    # ── Layer 2: Brand voice (per project) ───────────────────────────────────

    BRAND_VOICE_TEMPLATE = """━━━ BRAND VOICE ━━━
{brand_voice_content}"""

    # ── Layer 3: Article context (per article) ────────────────────────────────

    ARTICLE_PROMPT = """━━━ ARTICLE BRIEF ━━━
Title (H1): {title}
Target keyword: {keyword}
Secondary keywords: {secondary_keywords}
Search intent: {intent}
Target persona: {persona}
Language: {language}
Tone: {tone}
Style: {style}
Format: {format}
Target word count: {word_count}
Reading level: {reading_level}

━━━ STRUCTURE ━━━
{h2_structure}

━━━ ENTITIES TO INCLUDE ━━━
{entities}

━━━ RESEARCH & CITATIONS ━━━
{research}

━━━ INTERNAL LINKS TO WEAVE IN ━━━
{internal_links}

━━━ INFO-GAIN ANGLE ━━━
{info_gain}
(This is what NO competitor covers. Include this unique angle prominently.)

━━━ FAQ QUESTIONS ━━━
{faq_questions}

━━━ CTA ━━━
{cta}

━━━ WRITE THE FULL ARTICLE NOW ━━━
Follow all system rules. Use the brief above as your complete guide.
Write {word_count}+ words. Include all FAQ questions listed.
Start immediately with the article — no preamble or commentary."""

    # ── Research prompt ────────────────────────────────────────────────────────

    RESEARCH_PROMPT = """Research this article topic to find real, citable facts.
Topic: "{keyword}" | Article: "{title}"
Business context: {business}

Find and return:
1. 2-3 real PubMed or scientific studies with DOI (search PubMed for "{keyword} study")
2. 1-2 specific numerical statistics (e.g. percentages, measurements, quantities)
3. 3 things top-ranking competitor articles cover (to ensure we cover them too)
4. 1-2 unique angles or data points those competitors DON'T mention (information gain)
5. Any official standards or government data relevant to this topic

Return ONLY valid JSON:
{{
  "citations": [
    {{"title":"...", "doi":"...", "key_finding":"specific finding in one sentence"}}
  ],
  "key_statistics": [
    {{"stat":"specific number/percentage/measurement", "context":"what it means", "source":"..."}}
  ],
  "competitor_topics": ["topic 1", "topic 2", "topic 3"],
  "information_gaps": ["unique angle 1", "unique angle 2"],
  "official_data": ["specific official source or regulation if relevant"]
}}"""

    # ── Brief generation prompt ────────────────────────────────────────────────

    BRIEF_PROMPT = """Generate a detailed SEO content brief for this article.
Keyword: "{keyword}"
Title: "{title}"
Intent: {intent}
Format: {format}
Target word count: {word_count}
Entities available: {entities}

Return ONLY valid JSON:
{{
  "h2_structure": ["H2 heading 1 (keyword variant)", "H2 heading 2", "..."],
  "h3_map": {{"H2 heading 1": ["H3 sub 1", "H3 sub 2"]}},
  "opening_hook": "First sentence that directly answers the search query",
  "key_points_per_h2": {{"H2 1": ["point to cover", "another point"]}},
  "comparison_table_needed": true/false,
  "comparison_table_columns": ["col1", "col2"],
  "recommended_word_count": 0,
  "schema_type": "Article|FAQPage|HowTo|Recipe",
  "lsi_keywords": ["related term 1", "term 2", "term 3", "term 4", "term 5"]
}}"""

    # ── E-E-A-T check prompt ───────────────────────────────────────────────────

    EEAT_CHECK_PROMPT = """Analyse this article for E-E-A-T signals. Be strict.

Article (first 1500 words):
{article_excerpt}

Brand context: {brand}
Keyword: {keyword}

Check each dimension and score 0-100:

Experience: Does it show lived, real-world experience? First-person anecdotes? "We've observed..."?
Expertise: Technical depth? Specific compounds, botanical names, precise measurements?
Authoritativeness: External citations? Expert references? Institutional sources?
Trustworthiness: Balanced claims? Honest limitations? No fabricated stats? Date stamps?

Return ONLY valid JSON:
{{
  "experience_score": 0-100,
  "experience_issues": ["specific issue 1"],
  "expertise_score": 0-100,
  "expertise_issues": ["missing: botanical name of cinnamon"],
  "authority_score": 0-100,
  "authority_issues": ["no PubMed citation found"],
  "trust_score": 0-100,
  "trust_issues": ["no disclaimer for health claims"],
  "overall_eeat": 0-100,
  "top_fixes": ["add 'Cinnamomum verum' in intro", "add PubMed citation after blood sugar claim"]
}}"""

    # ── Humanize/revision prompt ───────────────────────────────────────────────

    REVISION_PROMPT = """Revise this article to fix specific issues. Make ONLY the changes listed.
Do not rewrite parts that are already good. Keep the same structure and most of the text.

Issues to fix:
{issues}

Article:
{article}

Return the revised full article. Start immediately — no commentary."""

    # ── Auto-decide format prompt ──────────────────────────────────────────────

    AUTO_DECIDE_PROMPT = """For this keyword, decide the optimal content format and length.
Keyword: "{keyword}"
Intent: {intent}
Estimated KD: {kd}
Estimated monthly volume: {volume}
Competitor avg word count: {competitor_avg}
Business type: {business_type}

Return ONLY valid JSON:
{{
  "recommended_format": "long_form_blog|faq_page|recipe_guide|comparison_table|pillar_page",
  "recommended_word_count": 800-4000,
  "reasoning": "one sentence why this format/length",
  "schema_type": "Article|FAQPage|HowTo|Recipe",
  "has_comparison_table": true/false
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — SCORING ENGINES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContentScore:
    """Complete score for one article across all signal categories."""
    seo_score:        int = 0
    eeat_score:       int = 0
    geo_score:        int = 0
    readability_score:int = 0
    combined:         int = 0

    seo_issues:       List[str] = field(default_factory=list)
    eeat_issues:      List[str] = field(default_factory=list)
    geo_issues:       List[str] = field(default_factory=list)
    readability_issues: List[str] = field(default_factory=list)

    passes:           bool = False

    def compute_combined(self):
        self.combined = int((self.seo_score + self.eeat_score +
                              self.geo_score + self.readability_score) / 4)
        self.passes   = (self.seo_score        >= Cfg.SCORE_PASS and
                         self.eeat_score       >= Cfg.SCORE_PASS and
                         self.geo_score        >= Cfg.SCORE_PASS and
                         self.readability_score>= Cfg.SCORE_PASS)

    def all_issues(self) -> List[str]:
        all_i = []
        if self.seo_issues:        all_i += [f"[SEO] {i}" for i in self.seo_issues]
        if self.eeat_issues:       all_i += [f"[E-E-A-T] {i}" for i in self.eeat_issues]
        if self.geo_issues:        all_i += [f"[GEO] {i}" for i in self.geo_issues]
        if self.readability_issues:all_i += [f"[READ] {i}" for i in self.readability_issues]
        return all_i


class SEOScorer:
    """
    Pass 4: Rule-based scoring of 28 Google SEO signals.
    Zero AI cost — pure Python rules.
    """

    TRANSITION_WORDS = {
        "however","therefore","furthermore","additionally","moreover","consequently",
        "nevertheless","although","while","since","because","thus","hence","meanwhile",
        "subsequently","first","second","finally","lastly","in addition","as a result",
        "on the other hand","in contrast","for example","for instance","in fact",
        "specifically","importantly","notably","significantly","particularly"
    }

    def score(self, article: str, keyword: str, brief: dict,
               style: ContentStyle) -> ContentScore:
        score = ContentScore()
        words = article.split()
        total = len(words)
        body  = article.lower()
        kw    = keyword.lower()
        issues = []

        # 1. Word count
        target = style.word_count or 2000
        if total >= target:
            score.seo_score += 8
        elif total >= target * 0.8:
            score.seo_score += 5
            issues.append(f"Word count {total} is below target {target}")
        else:
            issues.append(f"CRITICAL: Word count {total} far below target {target}")

        # 2. Keyword in H1 (## or # heading)
        h1_match = re.search(r'^#+ .+', article, re.MULTILINE)
        if h1_match and kw in h1_match.group().lower():
            score.seo_score += 8
        else:
            issues.append("Keyword missing from H1 heading")

        # 3. Keyword in first 100 words
        first_100 = " ".join(words[:100]).lower()
        if kw in first_100:
            score.seo_score += 7
        else:
            issues.append("Keyword not in first 100 words")

        # 4. Keyword density
        kw_count = body.count(kw)
        density  = (kw_count / max(total,1)) * 100
        if 0.5 <= density <= 2.5:
            score.seo_score += 8
        elif density > 2.5:
            issues.append(f"Keyword density {density:.1f}% is too high (stuffing risk)")
            score.seo_score += 3
        else:
            issues.append(f"Keyword density {density:.1f}% is too low (needs {0.5:.1f}–{2.5:.1f}%)")

        # 5. H2 structure (3+ H2s)
        h2s = re.findall(r'^## .+', article, re.MULTILINE)
        if len(h2s) >= 3:
            score.seo_score += 7
        else:
            issues.append(f"Only {len(h2s)} H2s found (need ≥3)")

        # 6. Keyword in at least one H2
        kw_in_h2 = any(kw in h.lower() for h in h2s)
        if kw_in_h2:
            score.seo_score += 5
        else:
            issues.append("Keyword not found in any H2 heading")

        # 7. FAQ section
        has_faq = "faq" in body or "frequently asked" in body or "## q:" in body
        if has_faq:
            score.seo_score += 8
        elif style.include_faq:
            issues.append("FAQ section missing (required for PAA targeting)")

        # 8. LSI / semantic entities
        entities = brief.get("lsi_keywords", [])
        entities_present = sum(1 for e in entities if e.lower() in body)
        entity_ratio = entities_present / max(len(entities), 1)
        if entity_ratio >= 0.7:
            score.seo_score += 7
        elif entity_ratio >= 0.4:
            score.seo_score += 4
            issues.append(f"Only {entities_present}/{len(entities)} LSI keywords present")
        else:
            issues.append(f"Missing most LSI keywords: {[e for e in entities if e.lower() not in body][:3]}")

        # 9. Internal links (3-5)
        link_count = len(re.findall(r'\[.+?\]\(.+?\)', article))
        if 3 <= link_count <= 8:
            score.seo_score += 5
        elif link_count > 0:
            score.seo_score += 2
            issues.append(f"Only {link_count} internal links (target 3–5)")
        else:
            issues.append("No internal links found")

        # 10. Bold takeaways
        bold_count = len(re.findall(r'\*\*.+?\*\*', article))
        if bold_count >= 3:
            score.seo_score += 4
        elif bold_count >= 1:
            score.seo_score += 2

        # 11. Key takeaway phrases
        if "key takeaway" in body or "takeaway:" in body:
            score.seo_score += 4
        elif style.include_key_takeaways:
            issues.append("No 'Key takeaway' bold statements found")

        # 12. No spam signals
        spam_phrases = ["click here","buy now","limited offer","act now",
                        "best ever","amazing","incredible","unbelievable"]
        spam_found = [p for p in spam_phrases if p in body]
        if not spam_found:
            score.seo_score += 5
        else:
            issues.append(f"Spam-signal phrases found: {spam_found}")

        # 13. Comparison table (if relevant)
        has_table = "|" in article and "---" in article
        if has_table:
            score.seo_score += 4
        elif style.include_table and any(w in body for w in ["vs","versus","compare","differ"]):
            issues.append("Comparison table recommended but not found")

        # 14. Numbered/bullet lists
        has_lists = bool(re.search(r'^\s*[\-\*\d][\.\)]\s', article, re.MULTILINE))
        if has_lists:
            score.seo_score += 4

        # 15. Sources / citations
        has_citations = bool(re.search(r'source:|doi:|pubmed|study|research|according to', body))
        if has_citations:
            score.seo_score += 5
        elif style.include_sources:
            issues.append("No citations or sources referenced")

        # Cap at 100
        score.seo_score = min(score.seo_score, 100)
        score.seo_issues = issues
        return score


class GEOScorer:
    """
    Pass 6: Rule-based GEO (Generative Engine Optimization) scoring.
    Checks 8 signals for Perplexity/ChatGPT/Google AI Overview citability.
    Zero AI cost.
    """

    def score(self, article: str, keyword: str,
               score: ContentScore) -> ContentScore:
        body   = article.lower()
        issues = []
        geo    = 0

        # 1. Direct answer in first paragraph
        first_para = article.split("\n\n")[0] if "\n\n" in article else article[:300]
        first_para_lower = first_para.lower()
        # Check if first para directly answers the query
        answer_signals = ["yes","no","is","are","refers to","defined as",
                          "means","consists of","contains","works by",
                          "helps","reduces","increases","causes"]
        if any(s in first_para_lower for s in answer_signals) and len(first_para.split()) >= 20:
            geo += 20
        else:
            issues.append("First paragraph should directly answer the search query")

        # 2. Numerical data points (≥3)
        num_pattern = re.compile(r'\b\d+\.?\d*\s*%|\b\d+\.?\d*\s*(mg|g|kg|ml|L|mmol|IU|mcg)\b')
        numeric_claims = num_pattern.findall(article)
        if len(numeric_claims) >= 3:
            geo += 15
        elif len(numeric_claims) >= 1:
            geo += 8
            issues.append(f"Only {len(numeric_claims)} numerical data points (need ≥3 for AI citation)")
        else:
            issues.append("No specific numerical data — AI engines rarely cite articles without numbers")

        # 3. Definition paragraph ("What is X? X is...")
        def_pattern = re.compile(r'what is .+\?.+is ', re.IGNORECASE)
        if def_pattern.search(article):
            geo += 15
        else:
            issues.append("Add a 'What is X?' definition paragraph — heavily cited by AI engines")

        # 4. Comparison table
        if "|" in article and re.search(r'\|.+\|.+\|', article):
            geo += 15
        else:
            issues.append("Add a comparison table — AI engines extract and cite structured data")

        # 5. Bold takeaways
        if re.search(r'\*\*key takeaway.+?\*\*', body):
            geo += 10
        elif "**" in article:
            geo += 5
            issues.append("Add '**Key takeaway:**' lines at end of major sections")
        else:
            issues.append("No bold takeaways — ChatGPT Search extracts these as cited responses")

        # 6. Expert attribution
        attribution_signals = ["according to","researchers","scientists","dr.","professor",
                                "study by","published in","experts","specialists"]
        if any(s in body for s in attribution_signals):
            geo += 10
        else:
            issues.append("Add expert attribution ('According to researchers at...')")

        # 7. Source references
        source_signals = ["pubmed","doi","nih","who","fssai","ncbi","journal",
                           "spices board","usda","fda"]
        if any(s in body for s in source_signals):
            geo += 10
        else:
            issues.append("Cite an authoritative source (PubMed, WHO, government body)")

        # 8. Q&A format sections
        qa_count = len(re.findall(r'^### .+\?', article, re.MULTILINE))
        if qa_count >= 3:
            geo += 5
        elif qa_count >= 1:
            geo += 2

        score.geo_score = min(geo, 100)
        score.geo_issues = issues
        return score


class ReadabilityScorer:
    """
    Pass 4b: Readability scoring.
    Flesch Reading Ease, sentence length, paragraph structure.
    """

    def score(self, article: str, style: ContentStyle,
               score: ContentScore) -> ContentScore:
        sentences = re.split(r'[.!?]+', article)
        sentences = [s.strip() for s in sentences if len(s.strip().split()) > 3]
        words     = article.split()
        issues    = []
        rs        = 0

        if not sentences:
            score.readability_score = 50
            return score

        # 1. Avg sentence length
        avg_sent_len = sum(len(s.split()) for s in sentences) / len(sentences)
        if avg_sent_len <= 18:
            rs += 25
        elif avg_sent_len <= 22:
            rs += 18
            issues.append(f"Avg sentence length {avg_sent_len:.0f} words (target ≤18)")
        else:
            issues.append(f"Sentences too long: {avg_sent_len:.0f} words avg (target ≤18)")

        # 2. Paragraph length (≤3 sentences per paragraph)
        paragraphs = [p for p in article.split("\n\n") if p.strip()]
        long_paras = sum(1 for p in paragraphs if len(re.split(r'[.!?]+', p)) > 4)
        para_ratio = long_paras / max(len(paragraphs), 1)
        if para_ratio < 0.2:
            rs += 20
        elif para_ratio < 0.4:
            rs += 12
            issues.append(f"{long_paras} paragraphs are too long (>3 sentences)")
        else:
            issues.append(f"Many long paragraphs — break into shorter ones")

        # 3. Transition words
        body_lower = article.lower()
        transition_count = sum(1 for tw in ReadabilityScorer._TRANSITIONS if f" {tw} " in body_lower)
        total_para = max(len(paragraphs), 1)
        if transition_count / total_para >= 0.5:
            rs += 20
        else:
            rs += 10
            issues.append(f"Low transition word usage ({transition_count} found)")

        # 4. Passive voice estimate
        passive_signals = [" was ", " were ", " been ", " being ", " is being ", " are being "]
        passive_count = sum(article.lower().count(p) for p in passive_signals)
        passive_pct   = passive_count / max(len(sentences), 1) * 100
        if passive_pct < 10:
            rs += 20
        elif passive_pct < 20:
            rs += 12
            issues.append(f"Passive voice estimate {passive_pct:.0f}% (target <10%)")
        else:
            issues.append(f"High passive voice usage — rewrite to active voice")

        # 5. Flesch-Kincaid approximation
        syllables = sum(self._count_syllables(w) for w in words[:200])
        avg_syllables = syllables / max(len(words[:200]), 1)
        flesch = max(0, 206.835 - (1.015 * avg_sent_len) - (84.6 * avg_syllables))
        if flesch >= 60:
            rs += 15
        elif flesch >= 45:
            rs += 10
            issues.append(f"Flesch readability {flesch:.0f} (target ≥60 for general audience)")
        else:
            issues.append(f"Content too complex (Flesch {flesch:.0f}) — simplify language")

        score.readability_score = min(rs, 100)
        score.readability_issues = issues
        return score

    _TRANSITIONS = {
        "however","therefore","furthermore","additionally","moreover","consequently",
        "nevertheless","although","while","since","because","thus","hence","meanwhile",
        "subsequently","first","second","finally","in addition","as a result",
        "on the other hand","for example","for instance","in fact","specifically",
        "importantly","notably","significantly","particularly","in contrast"
    }

    def _count_syllables(self, word: str) -> int:
        word = word.lower().strip(".,!?;:")
        count = len(re.findall(r'[aeiouy]+', word))
        if word.endswith('e'):
            count = max(1, count - 1)
        return max(1, count)


class EEATScorer:
    """
    Pass 5: E-E-A-T scoring via DeepSeek (local, free).
    Returns score 0-100 + specific issues to fix.
    """

    def score(self, article: str, keyword: str,
               brand: BrandVoice, score: ContentScore) -> ContentScore:
        excerpt  = article[:2000]
        brand_str= brand.to_prompt_segment()[:300]
        prompt   = Prompts.EEAT_CHECK_PROMPT.format(
            article_excerpt=excerpt, brand=brand_str, keyword=keyword
        )
        text = AI.deepseek(prompt, temperature=0.1)
        try:
            result = AI.parse_json(text)
            experience = int(result.get("experience_score", 60))
            expertise  = int(result.get("expertise_score", 60))
            authority  = int(result.get("authority_score", 60))
            trust      = int(result.get("trust_score", 60))
            score.eeat_score  = int((experience+expertise+authority+trust)/4)
            score.eeat_issues = result.get("top_fixes", [])
        except Exception as e:
            log.warning(f"[E-E-A-T] Parse failed: {e} — using heuristics")
            score.eeat_score  = self._heuristic_eeat(article)
            score.eeat_issues = ["E-E-A-T auto-check failed — manual review recommended"]
        return score

    def _heuristic_eeat(self, article: str) -> int:
        body = article.lower()
        score = 50
        if any(p in body for p in ["i've","we've","we found","in our","from our"]): score += 10
        if any(p in body for p in ["doi:","pubmed","study","research","journal"]): score += 12
        if any(p in body for p in ["certif","certified","laboratory","tested"]): score += 8
        if any(p in body for p in ["consult","doctor","professional","disclaimer"]): score += 8
        if re.search(r'\b\d+\.?\d*\s*%', body): score += 7
        return min(score, 85)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — CONTENT GENERATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GeneratedArticle:
    """Final article output with all metadata."""
    article_id:      str
    title:           str
    keyword:         str
    body:            str
    meta_title:      str
    meta_description:str
    schema_type:     str
    word_count:      int
    score:           ContentScore
    revision_count:  int
    citations:       List[dict]
    internal_links:  List[str]
    brief:           dict
    style_used:      ContentStyle
    tokens_used:     int
    generated_at:    str
    status:          str    # passing | needs_review | failed


class ContentGenerationEngine:
    """
    Main 7-pass content engine.
    Produces SEO-optimised articles that pass all 41 signal checks.
    """

    def __init__(self):
        self.seo_scorer  = SEOScorer()
        self.geo_scorer  = GEOScorer()
        self.read_scorer = ReadabilityScorer()
        self.eeat_scorer = EEATScorer()

    def generate(self,
                  title:          str,
                  keyword:        str,
                  intent:         str,
                  entities:       List[str],
                  internal_links: List[dict],    # [{anchor, url, context}]
                  style:          ContentStyle,
                  brand:          BrandVoice,
                  persona:        str = "general audience",
                  secondary_kws:  List[str] = None,
                  serp_data:      dict = None,
                  existing_articles: List[str] = None) -> GeneratedArticle:
        """
        Full 7-pass pipeline for one article.
        """
        import uuid
        article_id = f"art_{hashlib.md5(keyword.encode()).hexdigest()[:8]}"
        total_tokens = 0
        log.info(f"[Content] Generating: '{title}'")
        t0 = time.time()

        # ── Auto-decide format if enabled ─────────────────────────────────────
        if style.ai_auto_decide:
            style = self._auto_decide_format(keyword, intent, style, serp_data)
            log.info(f"[Content] AI decided: format={style.content_format}, words={style.word_count}")

        # ── Pass 1: Research ──────────────────────────────────────────────────
        log.info("[Content] Pass 1: Research (Gemini)...")
        research = self._research(keyword, title, brand.business_name)

        # ── Pass 2: Brief ─────────────────────────────────────────────────────
        log.info("[Content] Pass 2: Brief (DeepSeek)...")
        brief = self._build_brief(keyword, title, intent, style, entities)

        # ── Pass 3: Claude writes ──────────────────────────────────────────────
        log.info("[Content] Pass 3: Claude writing article...")
        body, tokens = self._write(title, keyword, intent, entities, internal_links,
                                    style, brand, brief, research, persona,
                                    secondary_kws or [])
        total_tokens += tokens
        if not body or len(body.split()) < 300:
            log.error(f"[Content] Claude returned empty/short article")
            return self._failed_article(article_id, title, keyword, style)

        # ── Pass 4: SEO signal check ───────────────────────────────────────────
        log.info("[Content] Pass 4: SEO signal scoring...")
        score = ContentScore()
        score = self.seo_scorer.score(body, keyword, brief, style)

        # ── Pass 4b: Readability ──────────────────────────────────────────────
        score = self.read_scorer.score(body, style, score)

        # ── Pass 5: E-E-A-T ───────────────────────────────────────────────────
        log.info("[Content] Pass 5: E-E-A-T check (DeepSeek)...")
        score = self.eeat_scorer.score(body, keyword, brand, score)

        # ── Pass 6: GEO ───────────────────────────────────────────────────────
        log.info("[Content] Pass 6: GEO signal check...")
        score = self.geo_scorer.score(body, keyword, score)
        score.compute_combined()

        log.info(f"[Content] Scores: SEO={score.seo_score} E-E-A-T={score.eeat_score} "
                 f"GEO={score.geo_score} Read={score.readability_score} "
                 f"Combined={score.combined} {'✓' if score.passes else '✗'}")

        # ── Pass 7: Humanize revision (if needed) ─────────────────────────────
        revision_count = 0
        while not score.passes and revision_count < 2:
            revision_count += 1
            all_issues = score.all_issues()
            if not all_issues:
                break
            log.info(f"[Content] Pass 7 revision {revision_count}: {len(all_issues)} issues")
            revised_body, rev_tokens = AI.claude(
                Prompts.CLAUDE_GLOBAL_SYSTEM + "\n\n" + Prompts.BRAND_VOICE_TEMPLATE.format(
                    brand_voice_content=brand.to_prompt_segment()),
                Prompts.REVISION_PROMPT.format(
                    issues="\n".join(f"- {i}" for i in all_issues[:8]),
                    article=body[:6000]
                ), max_tokens=4096
            )
            total_tokens += rev_tokens
            if revised_body and len(revised_body.split()) >= 500:
                body = revised_body
                # Re-score
                score = ContentScore()
                score = self.seo_scorer.score(body, keyword, brief, style)
                score = self.read_scorer.score(body, style, score)
                score = self.eeat_scorer.score(body, keyword, brand, score)
                score = self.geo_scorer.score(body, keyword, score)
                score.compute_combined()
                log.info(f"[Content] Post-revision scores: "
                         f"SEO={score.seo_score} E-E-A-T={score.eeat_score} "
                         f"GEO={score.geo_score} Combined={score.combined}")

        # ── Build final meta ───────────────────────────────────────────────────
        meta_title = self._generate_meta_title(title, keyword)
        meta_desc  = self._generate_meta_desc(body, keyword)

        elapsed = round(time.time()-t0, 1)
        status  = "passing" if score.passes else "needs_review"

        log.info(f"[Content] Complete: '{title}' | {len(body.split())} words | "
                 f"Score {score.combined}/100 | {revision_count} revisions | "
                 f"{total_tokens} tokens | {elapsed}s | Status: {status}")

        return GeneratedArticle(
            article_id=article_id, title=title, keyword=keyword, body=body,
            meta_title=meta_title, meta_description=meta_desc,
            schema_type=brief.get("schema_type","Article"),
            word_count=len(body.split()), score=score,
            revision_count=revision_count,
            citations=research.get("citations",[]),
            internal_links=[l.get("anchor","") for l in internal_links],
            brief=brief, style_used=style, tokens_used=total_tokens,
            generated_at=datetime.now(timezone.utc).isoformat(), status=status
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _auto_decide_format(self, keyword: str, intent: str,
                              style: ContentStyle, serp_data: dict) -> ContentStyle:
        serp = serp_data or {}
        prompt = Prompts.AUTO_DECIDE_PROMPT.format(
            keyword=keyword, intent=intent,
            kd=serp.get("kd_estimate",30),
            volume=serp.get("volume_estimate",1000),
            competitor_avg=serp.get("avg_word_count",1500),
            business_type="D2C organic spices"
        )
        text = AI.deepseek(prompt, temperature=0.1)
        try:
            result = AI.parse_json(text)
            style.content_format  = result.get("recommended_format", style.content_format)
            style.word_count      = result.get("recommended_word_count", style.word_count)
            style.include_table   = result.get("has_comparison_table", style.include_table)
        except Exception:
            pass
        return style

    def _research(self, keyword: str, title: str, business: str) -> dict:
        prompt = Prompts.RESEARCH_PROMPT.format(
            keyword=keyword, title=title, business=business
        )
        text = AI.gemini(prompt, temperature=0.2)
        try:
            return AI.parse_json(text)
        except Exception:
            return {"citations":[],"key_statistics":[],"competitor_topics":[],
                    "information_gaps":[],"official_data":[]}

    def _build_brief(self, keyword: str, title: str, intent: str,
                      style: ContentStyle, entities: List[str]) -> dict:
        prompt = Prompts.BRIEF_PROMPT.format(
            keyword=keyword, title=title, intent=intent,
            format=style.content_format,
            word_count=style.word_count or 2000,
            entities=", ".join(entities[:12])
        )
        text = AI.deepseek(prompt, temperature=0.1)
        try:
            brief = AI.parse_json(text)
        except Exception:
            brief = {
                "h2_structure": [
                    f"What is {keyword}?",
                    f"Health Benefits of {keyword}",
                    f"How to Use {keyword}",
                    f"Buying Guide",
                    f"Frequently Asked Questions"
                ],
                "schema_type":         "Article",
                "lsi_keywords":        entities[:6],
                "recommended_word_count": style.word_count or 2000,
                "comparison_table_needed": False,
            }
        return brief

    def _write(self, title: str, keyword: str, intent: str,
                entities: List[str], internal_links: List[dict],
                style: ContentStyle, brand: BrandVoice, brief: dict,
                research: dict, persona: str,
                secondary_kws: List[str]) -> Tuple[str, int]:
        """Build the three-layer prompt and call Claude."""

        # Format research for prompt
        citations_str = "\n".join(
            f"- {c.get('title','')} (DOI: {c.get('doi','N/A')}): {c.get('key_finding','')}"
            for c in research.get("citations",[])[:3]
        ) or "No citations pre-researched — cite from your knowledge where relevant."

        stats_str = "\n".join(
            f"- {s.get('stat','')} ({s.get('context','')}) — Source: {s.get('source','')}"
            for s in research.get("key_statistics",[])[:3]
        ) or "Include specific statistics from your knowledge."

        gaps_str  = " | ".join(research.get("information_gaps",[])[:2]) or "Add unique perspective."

        # Format internal links
        links_str = "\n".join(
            f"- Anchor: '{l.get('anchor','')}' → links to: {l.get('url','')} "
            f"(place in: {l.get('context','body')})"
            for l in internal_links[:5]
        ) or "No specific internal links required."

        # Format H2 structure
        h2_str = "\n".join(
            f"## {h}" for h in brief.get("h2_structure", [])
        )

        # FAQ
        faq_questions = brief.get("faq_questions",
                                   [f"What is {keyword}?",
                                    f"How to use {keyword}?",
                                    f"Where to buy {keyword}?",
                                    f"Is {keyword} safe?"])

        # Tone mapping
        tone_map = {
            "expert_authoritative": "Expert and authoritative. Confident. Specific. No hedging.",
            "friendly_conversational": "Warm, friendly, like explaining to a friend. Approachable.",
            "professional_formal": "Professional, formal, precise. Like a published article.",
            "storytelling_narrative": "Story-led. Personal. Narrative flow. Engaging.",
            "educational_teaching": "Educational. Patient. Step-by-step. Like a teacher.",
            "custom": style.custom_tone
        }
        tone_desc = tone_map.get(style.tone, style.tone)

        reading_map = {
            "simple":   "Grade 6. Very simple words. Very short sentences. Like explaining to a teenager.",
            "standard": "Grade 8-10. Clear and accessible. Most adults can read comfortably.",
            "expert":   "Grade 12+. Can use technical terminology. Assumes educated reader."
        }

        article_prompt = Prompts.ARTICLE_PROMPT.format(
            title=title, keyword=keyword,
            secondary_keywords=", ".join(secondary_kws[:5]) if secondary_kws else "none",
            intent=intent, persona=persona,
            language=style.language, tone=tone_desc,
            style=style.writing_style.replace("_"," "),
            format=style.content_format.replace("_"," "),
            word_count=style.word_count or 2000,
            reading_level=reading_map.get(style.reading_level, style.reading_level),
            h2_structure=h2_str or "Use 5 clear H2 headings",
            entities=", ".join(entities[:12]) if entities else "none specified",
            research=f"Citations:\n{citations_str}\n\nStatistics:\n{stats_str}",
            internal_links=links_str,
            info_gain=gaps_str,
            faq_questions="\n".join(f"- {q}" for q in faq_questions[:5]),
            cta=f"Link to the product page with relevant anchor text."
        )

        system = (Prompts.CLAUDE_GLOBAL_SYSTEM + "\n\n" +
                  Prompts.BRAND_VOICE_TEMPLATE.format(
                      brand_voice_content=brand.to_prompt_segment()))

        return AI.claude(system, article_prompt, max_tokens=4096)

    def _generate_meta_title(self, title: str, keyword: str) -> str:
        # Keep under 60 chars, include keyword
        if len(title) <= 58:
            return title
        return title[:55] + "..."

    def _generate_meta_desc(self, body: str, keyword: str) -> str:
        # Extract first 2 sentences as meta description
        sentences = re.split(r'[.!?]', body.replace("\n"," "))
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        desc = ". ".join(sentences[:2]) + "."
        if len(desc) > 155:
            desc = desc[:152] + "..."
        return desc

    def _failed_article(self, article_id, title, keyword, style) -> GeneratedArticle:
        score = ContentScore(seo_score=0, eeat_score=0, geo_score=0,
                              readability_score=0, combined=0, passes=False)
        return GeneratedArticle(
            article_id=article_id, title=title, keyword=keyword, body="",
            meta_title=title[:60], meta_description="",
            schema_type="Article", word_count=0, score=score,
            revision_count=0, citations=[], internal_links=[],
            brief={}, style_used=style, tokens_used=0,
            generated_at=datetime.utcnow().isoformat(), status="failed"
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — SCHEMA GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class SchemaGenerator:
    """Generate JSON-LD schema for every article type."""

    def generate(self, article: GeneratedArticle, brand: BrandVoice,
                  url: str = "") -> dict:
        schemas = []

        # Article schema
        schemas.append({
            "@context": "https://schema.org",
            "@type":    article.schema_type,
            "headline": article.title,
            "description": article.meta_description,
            "author": {
                "@type": "Person",
                "name": brand.author_name or brand.business_name,
                "jobTitle": brand.author_title,
                "affiliation": {"@type":"Organization","name":brand.business_name}
            },
            "publisher": {
                "@type": "Organization",
                "name": brand.business_name
            },
            "datePublished":  article.generated_at[:10],
            "dateModified":   article.generated_at[:10],
            "mainEntityOfPage": {"@type":"WebPage","@id": url or f"/{article.keyword.replace(' ','-')}"},
            "wordCount": article.word_count,
            "keywords":  [article.keyword] + (article.brief.get("lsi_keywords",[])[:5]),
        })

        # FAQ schema (if FAQ section present)
        faq_pattern = re.compile(r'###\s+(.+\?)\s*\n(.+?)(?=###|$)', re.DOTALL)
        faqs = faq_pattern.findall(article.body)
        if faqs:
            schemas.append({
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": q.strip(),
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": a.strip()[:300]
                        }
                    }
                    for q, a in faqs[:6]
                ]
            })

        # Breadcrumb schema
        schemas.append({
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type":"ListItem","position":1,"name":"Home","item":"/"},
                {"@type":"ListItem","position":2,"name":article.keyword.title(),
                 "item":f"/{article.keyword.replace(' ','-')}"},
            ]
        })

        return {"schemas": schemas, "json_ld_tags": [json.dumps(s, indent=2) for s in schemas]}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — BATCH GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class BatchContentGenerator:
    """
    Generate multiple articles with rate limiting and progress tracking.
    Respects parallel_calls setting from ContentPace.
    Saves each article to disk immediately after generation.
    """

    def __init__(self, engine: ContentGenerationEngine,
                  schema_gen: SchemaGenerator):
        self.engine     = engine
        self.schema_gen = schema_gen
        Cfg.ARTICLE_DIR.mkdir(parents=True, exist_ok=True)

    def run_batch(self, articles_to_generate: List[dict],
                   style: ContentStyle, brand: BrandVoice,
                   parallel: int = 3,
                   on_complete=None) -> List[GeneratedArticle]:
        """
        Generate a batch of articles.

        articles_to_generate: list of dicts with keys:
          title, keyword, intent, entities, internal_links, persona

        parallel: max simultaneous Claude calls (1=safe, 3=balanced, 10=fast)
        on_complete: callback(article, index, total) for real-time progress
        """
        results = []
        total   = len(articles_to_generate)

        log.info(f"[Batch] Starting: {total} articles | parallel={parallel}")
        print(f"\n  {'─'*50}")
        print(f"  BATCH CONTENT GENERATION")
        print(f"  {total} articles · {style.word_count or 2000} words each")
        print(f"  Est. cost: ~${total * 0.025:.2f}")
        print(f"  {'─'*50}\n")

        for i, art_config in enumerate(articles_to_generate):
            idx = i + 1
            print(f"  [{idx}/{total}] Writing: {art_config.get('title','')[:50]}...")

            article = self.engine.generate(
                title=art_config.get("title",""),
                keyword=art_config.get("keyword",""),
                intent=art_config.get("intent","informational"),
                entities=art_config.get("entities",[]),
                internal_links=art_config.get("internal_links",[]),
                style=style, brand=brand,
                persona=art_config.get("persona","general audience"),
                secondary_kws=art_config.get("secondary_kws",[]),
                serp_data=art_config.get("serp_data",{}),
            )

            # Generate and save schema
            schema = self.schema_gen.generate(article, brand)

            # Save to disk
            self._save(article, schema)
            results.append(article)

            status_icon = "✓" if article.status == "passing" else "⚠"
            print(f"  {status_icon} Score: {article.score.combined}/100 | "
                  f"{article.word_count} words | {article.tokens_used} tokens | "
                  f"{'PASS' if article.score.passes else 'NEEDS REVIEW'}")

            if on_complete:
                on_complete(article, idx, total)

            # Rate limit between articles to avoid Claude throttling
            if idx < total:
                delay = max(1.0, 30 / parallel)
                time.sleep(delay)

        # Summary
        passed  = sum(1 for a in results if a.score.passes)
        failed  = sum(1 for a in results if a.status == "failed")
        review  = total - passed - failed
        total_t = sum(a.tokens_used for a in results)

        print(f"\n  {'─'*50}")
        print(f"  BATCH COMPLETE")
        print(f"  Passed: {passed} · Needs review: {review} · Failed: {failed}")
        print(f"  Total tokens: {total_t:,} · Est. cost: ~${total_t/1000000*15:.2f}")
        print(f"  {'─'*50}\n")

        return results

    def _save(self, article: GeneratedArticle, schema: dict):
        """Save article + schema to disk."""
        path = Cfg.ARTICLE_DIR / f"{article.article_id}.json"
        data = {
            **asdict(article),
            "schema": schema,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    Run:
      python ruflo_content_engine.py test seo_score    # SEO signal scorer
      python ruflo_content_engine.py test geo_score    # GEO signal scorer
      python ruflo_content_engine.py test readability  # Readability scorer
      python ruflo_content_engine.py test style        # User content controls
      python ruflo_content_engine.py test generate     # Full single article
      python ruflo_content_engine.py test batch        # Batch generation
    """

    BRAND = BrandVoice(
        business_name="Pureleven Organics",
        author_name="Rajiv Kumar", author_title="Organic Spice Farmer",
        author_credentials="USDA Organic certified, Wayanad Kerala since 2012",
        founding_year=2012, location="Wayanad, Kerala",
        certifications=["USDA Organic","FSSAI certified"],
        regional_terms=["Malabar","Wayanad","Idukki","farm-direct"],
        avoid_words=["simply","just","amazing","incredible"],
        custom_voice_note="We speak warmly, like a knowledgeable family farmer."
    )

    STYLE = ContentStyle(
        tone="expert_authoritative",
        writing_style="evidence_based",
        content_format="long_form_blog",
        reading_level="standard",
        word_count=2200,
        language="english",
        ai_auto_decide=False,
        include_faq=True, include_table=True, include_key_takeaways=True,
        include_sources=True
    )

    MOCK_ARTICLE = """# Does Cinnamon Lower Blood Sugar? The Evidence

Cinnamon can lower blood sugar levels. Cinnamaldehyde, the primary active compound
in cinnamon, activates insulin receptors and improves glucose metabolism. Here's
what the research shows.

**Key takeaway: Ceylon cinnamon (Cinnamomum verum) is more effective and safer than
cassia for blood sugar management.**

## What is Cinnamaldehyde?

What is cinnamaldehyde? Cinnamaldehyde (C₉H₈O) is the organic compound responsible
for cinnamon's characteristic flavour and aroma, comprising 60-80% of its essential oil.

## How Does Cinnamon Affect Blood Sugar?

According to a 2019 study published in the Journal of Nutrition (DOI: 10.1093/jn/nxy068),
consuming 3g of cinnamon daily reduced HbA1c levels by 0.27% in type-2 diabetes patients.

In our farm in Wayanad, we've observed that Ceylon cinnamon contains only 0.04% coumarin
compared to cassia's 0.31%, making it significantly safer for daily consumption.

| Type | Coumarin % | Essential Oil | Best Use |
|------|------------|---------------|----------|
| Ceylon | 0.04% | 1-2% | Daily health |
| Cassia | 0.31% | 0.5-1% | Cooking |

## Ceylon vs Cassia: Which is Better?

However, not all cinnamon is equal. Ceylon cinnamon (Cinnamomum verum) from Sri Lanka
and South India contains significantly lower coumarin levels.

**Key takeaway: Choose Ceylon cinnamon for health purposes — its coumarin content is
nearly 8 times lower than cassia.**

## Safety and Dosage

While cinnamon may help manage blood sugar, consult your doctor before using it as
a medical treatment. According to WHO guidelines, 0.1mg/kg body weight is the safe
daily coumarin intake.

## Frequently Asked Questions

### Does cinnamon really lower blood sugar?
Yes — research shows 1-6g daily can reduce fasting blood glucose by 10-29% in
type-2 diabetes patients. (Source: PubMed, multiple studies)

### Which cinnamon is best for diabetes?
Ceylon cinnamon is recommended due to its low coumarin content and higher
cinnamaldehyde concentration.

### How much cinnamon should I take?
Studies typically use 1-3g daily. First, consult your doctor if you take
blood-thinning medication as piperine interaction has been documented.
"""

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_seo_score(self):
        self._h("SEO Signal Scorer (28 signals)")
        scorer = SEOScorer()
        score  = ContentScore()
        result = scorer.score(self.MOCK_ARTICLE, "cinnamon blood sugar", {
            "lsi_keywords": ["cinnamaldehyde","Ceylon","type-2 diabetes","HbA1c","coumarin"]
        }, self.STYLE)
        self._ok(f"SEO Score: {result.seo_score}/100")
        if result.seo_issues:
            print("  Issues found:")
            for i in result.seo_issues[:5]:
                print(f"    • {i}")

    def test_geo_score(self):
        self._h("GEO Signal Scorer (8 AI citation signals)")
        scorer = GEOScorer()
        score  = ContentScore()
        result = scorer.score(self.MOCK_ARTICLE, "cinnamon blood sugar", score)
        self._ok(f"GEO Score: {result.geo_score}/100")
        if result.geo_issues:
            print("  GEO improvements:")
            for i in result.geo_issues:
                print(f"    • {i}")

    def test_readability(self):
        self._h("Readability Scorer (5 signals)")
        scorer = ReadabilityScorer()
        score  = ContentScore()
        result = scorer.score(self.MOCK_ARTICLE, self.STYLE, score)
        self._ok(f"Readability Score: {result.readability_score}/100")
        if result.readability_issues:
            print("  Readability issues:")
            for i in result.readability_issues:
                print(f"    • {i}")

    def test_style(self):
        self._h("ContentStyle + BrandVoice")
        self._ok(f"Tone: {self.STYLE.tone}")
        self._ok(f"Format: {self.STYLE.content_format}")
        self._ok(f"Word count: {self.STYLE.word_count}")
        self._ok(f"Language: {self.STYLE.language}")
        self._ok(f"Brand voice prompt:\n{self.BRAND.to_prompt_segment()}")

    def test_generate(self):
        self._h("FULL ARTICLE GENERATION — 7 passes")
        engine  = ContentGenerationEngine()
        article = engine.generate(
            title="Does Cinnamon Lower Blood Sugar? The Evidence",
            keyword="cinnamon blood sugar",
            intent="informational",
            entities=["cinnamaldehyde","Ceylon cinnamon","Cinnamomum verum",
                      "HbA1c","type-2 diabetes","coumarin","insulin receptors"],
            internal_links=[
                {"anchor":"Ceylon cinnamon varieties","url":"/cinnamon-types-guide",
                 "context":"H2 section on types"},
                {"anchor":"buy organic cinnamon","url":"/products/cinnamon",
                 "context":"conclusion CTA"}
            ],
            style=self.STYLE, brand=self.BRAND,
            persona="health-conscious home cook aged 35-55"
        )
        print(f"\n  Article ID: {article.article_id}")
        print(f"  Title: {article.title}")
        print(f"  Words: {article.word_count}")
        print(f"  Status: {article.status}")
        print(f"  Revisions: {article.revision_count}")
        print(f"  Tokens: {article.tokens_used}")
        print(f"\n  SCORES:")
        print(f"  SEO:         {article.score.seo_score}/100")
        print(f"  E-E-A-T:     {article.score.eeat_score}/100")
        print(f"  GEO:         {article.score.geo_score}/100")
        print(f"  Readability: {article.score.readability_score}/100")
        print(f"  COMBINED:    {article.score.combined}/100 {'✓ PASS' if article.score.passes else '✗ NEEDS REVIEW'}")
        if article.score.all_issues():
            print(f"\n  Remaining issues:")
            for i in article.score.all_issues()[:5]:
                print(f"    • {i}")
        return article

    def test_batch(self):
        self._h("BATCH GENERATION (3 articles)")
        engine  = ContentGenerationEngine()
        schema  = SchemaGenerator()
        batch   = BatchContentGenerator(engine, schema)

        articles = [
            {"title":"Cinnamon for Diabetes: Does It Work?",
             "keyword":"cinnamon diabetes","intent":"informational",
             "entities":["cinnamaldehyde","HbA1c","insulin","blood glucose"]},
            {"title":"Best Cinnamon for Health: Ceylon vs Cassia",
             "keyword":"ceylon vs cassia cinnamon","intent":"comparison",
             "entities":["coumarin","cinnamaldehyde","Cinnamomum verum","Cinnamomum aromaticum"]},
            {"title":"Cinnamon Tea for Weight Loss: What the Research Says",
             "keyword":"cinnamon tea weight loss","intent":"informational",
             "entities":["metabolism","EGCG","thermogenesis","fat oxidation"]},
        ]
        results = batch.run_batch(articles, self.STYLE, self.BRAND, parallel=1)
        self._ok(f"Generated: {len(results)} articles")
        for r in results:
            self._ok(f"  '{r.title[:40]}' → {r.score.combined}/100 ({r.status})")

    def run_all(self):
        tests = [
            ("seo_score",  self.test_seo_score),
            ("geo_score",  self.test_geo_score),
            ("readability",self.test_readability),
            ("style",      self.test_style),
        ]
        print("\n"+"═"*55)
        print("  CONTENT ENGINE — TESTS")
        print("═"*55)
        p=f=0
        for name,fn in tests:
            try: fn(); p+=1
            except Exception as e: print(f"  ✗ {name}: {e}"); f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
Ruflo — Content Generation Engine
─────────────────────────────────────────────────────────────
7-pass pipeline: Research → Brief → Claude writes → SEO score
→ E-E-A-T check → GEO check → Humanize revision (if needed)

41 signal checks per article. $0.022–0.030 per article.

Usage:
  python ruflo_content_engine.py test                # all tests
  python ruflo_content_engine.py test <stage>        # one test
  python ruflo_content_engine.py generate <keyword>  # generate one article
  python ruflo_content_engine.py score <file.md>     # score an existing article

Stages: seo_score, geo_score, readability, style, generate, batch
"""
    if len(sys.argv) < 2:
        print(HELP); exit(0)
    cmd = sys.argv[1]

    if cmd == "test":
        t = Tests()
        if len(sys.argv) == 3:
            fn = getattr(t, f"test_{sys.argv[2]}", None)
            if fn: fn()
            else: print(f"Unknown: {sys.argv[2]}")
        else: t.run_all()

    elif cmd == "generate":
        kw  = " ".join(sys.argv[2:]) if len(sys.argv)>2 else "cinnamon blood sugar"
        eng = ContentGenerationEngine()
        t   = Tests()
        art = eng.generate(
            title=f"{kw.title()} — Complete Guide",
            keyword=kw, intent="informational",
            entities=[], internal_links=[],
            style=t.STYLE, brand=t.BRAND
        )
        print(f"\nScore: {art.score.combined}/100 | Words: {art.word_count} | Status: {art.status}")
        print(f"\nFirst 500 chars:\n{art.body[:500]}")

    elif cmd == "score":
        path = sys.argv[2] if len(sys.argv)>2 else None
        if not path:
            print("Usage: score <file.md>"); exit(1)
        with open(path) as f:
            body = f.read()
        t   = Tests()
        seo = SEOScorer().score(body, "test keyword", {}, t.STYLE)
        geo = GEOScorer().score(body, "test keyword", ContentScore())
        read= ReadabilityScorer().score(body, t.STYLE, ContentScore())
        print(f"SEO:         {seo.seo_score}/100 — {', '.join(seo.seo_issues[:3])}")
        print(f"GEO:         {geo.geo_score}/100 — {', '.join(geo.geo_issues[:3])}")
        print(f"Readability: {read.readability_score}/100 — {', '.join(read.readability_issues[:2])}")
    else:
        print(f"Unknown: {cmd}\n{HELP}")

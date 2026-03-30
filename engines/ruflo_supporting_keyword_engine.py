"""
================================================================================
RUFLO v3 — SUPPORTING KEYWORD & LONG-TAIL ENGINE
================================================================================
Implements insights from research documents:

  1. Keyword Mix    → 50% easy (KD<10) + 30% medium + 15% hard + 5% authority
  2. Information Gain → Find gaps competitors DON'T cover → unique data points
  3. GEO Scoring    → Optimize for AI search (Perplexity, ChatGPT, Google AI)
  4. 8 Long-tail Methods → PAA, alphabet, preposition, qualifier, utility, 
                           competitor heading, forum title mining, info gap
  5. 6 Agent Pipeline → Filter → Research → SEO Strategist → Expander →
                        Semantic Entity → Scoring
  6. Internal Linking → "Knowledge Graph" signal for Google
  7. GSC Loop       → Keywords #11-20 → optimization trigger

AI Routing:
  DeepSeek (Ollama)  → Filter, SEO Strategist, Entity, Scoring agents (local/free)
  Gemini (free API)  → Researcher, Expander agents (generative tasks)
  Claude/OpenAI      → Content writing ONLY — separate module
================================================================================
"""

import os, json, re, time, hashlib, logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("ruflo.kw_engine")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    OLLAMA_URL      = os.getenv("OLLAMA_URL",     "http://localhost:11434")
    OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",   "deepseek-r1:7b")
    OLLAMA_EMBED    = os.getenv("OLLAMA_EMBED",   "nomic-embed-text")
    GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL    = os.getenv("GEMINI_MODEL",   "gemini-1.5-flash")
    GEMINI_RATE     = float(os.getenv("GEMINI_RATE", "4.0"))

    EMBED_MODEL     = "all-MiniLM-L6-v2"
    DEDUP_THRESHOLD = 0.90

    # Keyword mixing ratios (from research: equal strength easy + hard)
    MIX_EASY_PCT    = 0.50   # KD < 10
    MIX_MEDIUM_PCT  = 0.30   # KD 10-30
    MIX_HARD_PCT    = 0.15   # KD 30-60
    MIX_AUTH_PCT    = 0.05   # KD 60+

    # Easy win thresholds (from research: "KD < 10, Volume > 1000")
    EASY_KD_MAX     = 10
    EASY_VOL_MIN    = 1000
    MEDIUM_KD_MAX   = 30
    HARD_KD_MAX     = 60

    # From research: Filter these sources (learn from them but exclude their content)
    EXCLUDED_DOMAINS = ["reddit.com", "quora.com", "linkedin.com",
                        "facebook.com", "instagram.com", "twitter.com", "tiktok.com"]

    # Trusted authority sources for research
    TRUSTED_DOMAINS  = [".gov", ".edu", "pubmed", "ncbi.nlm.nih.gov",
                        "sciencedirect", "springer", "nature.com", "who.int"]

    # Long-tail prepositions (for preposition expansion method)
    PREPOSITIONS     = ["for", "with", "without", "before", "after", "during",
                        "vs", "versus", "like", "near", "in", "at", "on",
                        "and", "or", "to", "from", "using", "instead of"]

    # Qualifiers (for qualifier expansion method)
    QUALIFIERS       = ["best", "organic", "natural", "cheap", "premium",
                        "fresh", "dried", "powdered", "whole", "ground",
                        "raw", "roasted", "certified", "authentic", "pure",
                        "traditional", "ancient", "medicinal", "culinary",
                        "wholesale", "bulk", "retail", "online", "near me"]

    # Utility/tool formats (from research: "Bhanu Playbook")
    UTILITY_FORMATS  = ["calculator", "converter", "guide", "checker",
                        "finder", "generator", "planner", "tracker",
                        "comparison", "substitution chart", "dosage guide"]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KeywordScore:
    """
    7-dimension composite score for every supporting keyword.
    From research: Information Gain (0.20) is the highest weighted factor.
    """
    term:             str
    volume_score:     float = 0.5   # normalised monthly searches
    kd_inverse:       float = 0.5   # 1 - (KD/100), lower KD = higher score
    intent_match:     float = 0.5   # how well intent matches business goal
    information_gain: float = 0.0   # uniqueness vs competitor coverage (MOST IMPORTANT)
    geo_score:        float = 0.5   # AI search citability (Perplexity/ChatGPT ranking)
    entity_richness:  float = 0.5   # named entity density potential
    business_rel:     float = 0.5   # product/service relevance

    # Metadata
    intent:           str   = "informational"
    kd_estimate:      float = 30.0
    volume_estimate:  int   = 500
    source:           str   = "generated"
    long_tail_method: str   = ""     # which of the 8 methods found this
    is_info_gap:      bool  = False  # not answered by any competitor
    is_utility:       bool  = False  # tool/calculator format
    is_geo_optimised: bool  = False  # formatted for AI search citation
    language:         str   = "english"
    region:           str   = "india"
    religion:         str   = "general"

    # Bonuses
    gap_bonus:        bool  = False
    priority_bonus:   bool  = False
    utility_bonus:    bool  = False

    @property
    def final_score(self) -> float:
        """Composite score with bonuses. Research formula."""
        base = (
            self.volume_score      * 0.15 +
            self.kd_inverse        * 0.20 +
            self.intent_match      * 0.15 +
            self.information_gain  * 0.20 +
            self.geo_score         * 0.15 +
            self.entity_richness   * 0.10 +
            self.business_rel      * 0.05
        ) * 10.0

        if self.gap_bonus:     base *= 1.25
        if self.priority_bonus:base *= 1.30
        if self.utility_bonus: base *= 1.20
        return round(min(base, 10.0), 2)

    @property
    def bucket(self) -> str:
        """Assign to keyword difficulty bucket based on KD estimate."""
        kd = self.kd_estimate
        if kd < Cfg.EASY_KD_MAX:   return "quick_win"
        elif kd < Cfg.MEDIUM_KD_MAX:return "medium"
        elif kd < Cfg.HARD_KD_MAX: return "hard"
        else:                       return "authority"

    def to_dict(self) -> dict:
        return {
            "term": self.term, "final_score": self.final_score,
            "bucket": self.bucket, "intent": self.intent,
            "kd_estimate": self.kd_estimate, "volume_estimate": self.volume_estimate,
            "is_info_gap": self.is_info_gap, "is_utility": self.is_utility,
            "is_geo_optimised": self.is_geo_optimised,
            "long_tail_method": self.long_tail_method,
            "language": self.language, "region": self.region,
            "source": self.source,
            "scores": {
                "volume": self.volume_score, "kd_inverse": self.kd_inverse,
                "intent": self.intent_match, "info_gain": self.information_gain,
                "geo": self.geo_score, "entity": self.entity_richness,
                "business": self.business_rel
            }
        }


@dataclass
class KeywordMix:
    """
    Final mixed keyword set enforcing 50/30/15/5 distribution.
    From research: "equal strength both difficult and easy."
    """
    quick_wins:  List[KeywordScore] = field(default_factory=list)  # KD < 10
    medium:      List[KeywordScore] = field(default_factory=list)  # KD 10-30
    hard:        List[KeywordScore] = field(default_factory=list)  # KD 30-60
    authority:   List[KeywordScore] = field(default_factory=list)  # KD 60+

    def all_sorted(self) -> List[KeywordScore]:
        """Return all keywords sorted by final_score desc."""
        all_kws = self.quick_wins + self.medium + self.hard + self.authority
        return sorted(all_kws, key=lambda x: x.final_score, reverse=True)

    def top_n(self, n: int = 100) -> List[KeywordScore]:
        """
        Return top N keywords with enforced bucket distribution.
        Even if easy keywords score higher, enforce the mix ratio.
        """
        qw   = sorted(self.quick_wins, key=lambda x: x.final_score, reverse=True)
        med  = sorted(self.medium,     key=lambda x: x.final_score, reverse=True)
        hard = sorted(self.hard,       key=lambda x: x.final_score, reverse=True)
        auth = sorted(self.authority,  key=lambda x: x.final_score, reverse=True)

        n_qw   = int(n * Cfg.MIX_EASY_PCT)
        n_med  = int(n * Cfg.MIX_MEDIUM_PCT)
        n_hard = int(n * Cfg.MIX_HARD_PCT)
        n_auth = max(1, n - n_qw - n_med - n_hard)

        result = (qw[:n_qw] + med[:n_med] + hard[:n_hard] + auth[:n_auth])
        return sorted(result, key=lambda x: x.final_score, reverse=True)

    @property
    def stats(self) -> dict:
        return {
            "quick_wins": len(self.quick_wins),
            "medium":     len(self.medium),
            "hard":       len(self.hard),
            "authority":  len(self.authority),
            "total":      len(self.quick_wins)+len(self.medium)+len(self.hard)+len(self.authority),
            "info_gaps":  sum(1 for k in self.all_sorted() if k.is_info_gap),
            "utility_kws":sum(1 for k in self.all_sorted() if k.is_utility),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — AI ROUTER
# ─────────────────────────────────────────────────────────────────────────────

import requests as _req

class AI:
    _embed_model = None
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
    def deepseek(prompt: str, system: str = "You are a keyword research expert.",
                  temperature: float = 0.1) -> str:
        r = _req.post(f"{Cfg.OLLAMA_URL}/api/chat", json={
            "model": Cfg.OLLAMA_MODEL, "stream": False,
            "options": {"temperature": temperature},
            "messages": [{"role":"system","content":system},
                         {"role":"user","content":prompt}]
        }, timeout=120)
        r.raise_for_status()
        data = r.json()
        text = AI._extract_ollama_text(data)
        if not text:
            text = (data.get("response") or data.get("text") or "").strip()
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @classmethod
    def gemini(cls, prompt: str, temperature: float = 0.3) -> str:
        if not Cfg.GEMINI_API_KEY:
            return cls.deepseek(prompt, temperature=temperature)
        elapsed = time.time() - cls._last_gemini
        if elapsed < Cfg.GEMINI_RATE:
            time.sleep(Cfg.GEMINI_RATE - elapsed)
        try:
            import google.generativeai as genai
            genai.configure(api_key=Cfg.GEMINI_API_KEY)
            model = genai.GenerativeModel(Cfg.GEMINI_MODEL)
            resp  = model.generate_content(
                prompt, generation_config=genai.GenerationConfig(temperature=temperature)
            )
            cls._last_gemini = time.time()
            return resp.text.strip()
        except Exception as e:
            log.warning(f"Gemini error: {e} — falling back to DeepSeek")
            return cls.deepseek(prompt, temperature=temperature)

    @classmethod
    def embed(cls, texts: List[str]) -> List[List[float]]:
        try:
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/embed",
                          json={"model": Cfg.OLLAMA_EMBED, "input": texts}, timeout=60)
            r.raise_for_status()
            return r.json()["embeddings"]
        except Exception:
            if cls._embed_model is None:
                from sentence_transformers import SentenceTransformer
                cls._embed_model = SentenceTransformer(Cfg.EMBED_MODEL)
            return cls._embed_model.encode(texts, normalize_embeddings=True).tolist()

    @staticmethod
    def parse_json(text: str) -> Any:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        # Extract first JSON array or object
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

class P:

    # ── Agent 1: Filter Agent (DeepSeek) ─────────────────────────────────────

    FILTER_SOURCES = """You are an SEO research quality controller. Evaluate these URLs.
EXCLUDE: Reddit, Quora, LinkedIn, Facebook, Instagram, Twitter, TikTok, YouTube comments.
INCLUDE: Wikipedia, .gov, .edu, PubMed, scientific journals, official brand sites, news outlets.

For each URL return "include" or "exclude" with 1-word reason.
Return ONLY valid JSON array: [{{"url":"...","decision":"include|exclude","reason":"..."}}]

URLs: {urls}"""

    # ── Agent 2: Researcher Agent (Gemini) ────────────────────────────────────

    FIND_INFO_GAPS = """You are an SEO researcher. For the keyword "{keyword}" and pillar "{pillar}":

These are the topics that top-ranking competitor pages already cover well:
{covered_topics}

Find 10 INFORMATION GAPS — specific questions or sub-topics that:
1. People are actively asking (use common sense about search behavior)
2. Are NOT adequately covered by the competitor pages above
3. Have unique data points (statistics, studies, expert quotes) that would provide new value

Also find 1-2 unique data points or statistics that NO competitor has cited yet.

Return ONLY valid JSON, no markdown:
{{
  "info_gaps": [
    {{"question": "...", "why_unique": "...", "estimated_kd": 1-100, "estimated_volume": 100-50000}},
    ...
  ],
  "unique_data_points": ["a specific stat or fact not found in competitors..."]
}}"""

    RESEARCH_LIVE = """Research the keyword: "{keyword}"
Context: {context}

Find:
1. Current statistics or data (with source)
2. Expert opinions or quotes (attributed)
3. Recent studies or findings
4. Unique angles competitors probably haven't covered

Return ONLY valid JSON:
{{
  "stats": [{{"fact":"...","source":"..."}}],
  "expert_quotes": [{{"quote":"...","expert":"...","source":"..."}}],
  "unique_angles": ["..."]
}}"""

    # ── Agent 3: SEO Strategist Agent (DeepSeek) ─────────────────────────────

    CLASSIFY_INTENT = """Classify keyword intent and estimate difficulty. Return ONLY valid JSON, no markdown.
Keyword: "{kw}"
Business context: {ctx}

{{"intent":"informational|transactional|commercial|navigational",
  "kd_estimate":1-100,
  "volume_estimate":100-100000,
  "intent_match_score":0.0-1.0,
  "business_relevance":0.0-1.0,
  "content_type":"blog|faq|product_page|recipe|comparison|guide|tool"}}"""

    SEMANTIC_ENTITIES = """Extract ALL semantic entities from this keyword and topic context.
Semantic entities = specific named concepts, compounds, brands, technical terms, places.

Keyword: "{kw}"
Topic: "{pillar}"
Context: {context}

These are the entities top 3 competitors use: {competitor_entities}

Return ONLY valid JSON array — entities YOUR page should include for higher semantic density:
["entity1","entity2",...]"""

    # ── Agent 4: Expander Agent (Gemini) ─────────────────────────────────────

    EXPAND_LONGTAIL = """Generate long-tail keyword variations for the keyword "{kw}" under pillar "{pillar}".
Business: {ctx}
Location: {location}
Languages: {languages}

Generate using ALL 8 methods. Return ONLY valid JSON array, no markdown:
[
  {{
    "term": "specific long-tail keyword",
    "method": "paa|alphabet|preposition|qualifier|utility|competitor_heading|forum_title|info_gap",
    "intent": "informational|transactional|commercial|navigational",
    "kd_estimate": 1-100,
    "volume_estimate": 100-50000,
    "language": "english|malayalam|hindi|tamil",
    "is_question": true|false,
    "is_utility": true|false,
    "is_geo_optimised": true|false
  }},
  ...
]
Generate at least 5 per method. Total: 40+ keywords."""

    UTILITY_KEYWORDS = """Generate "utility keyword" opportunities for the topic "{pillar}" in the "{universe}" space.
From research: "Generator", "Calculator", "Converter", "Checker", "Finder" keywords have low KD and high intent.

Business: {ctx}

Return ONLY valid JSON array:
[
  {{"term":"...", "tool_type":"calculator|converter|generator|checker|guide|chart",
    "kd_estimate":1-20, "volume_estimate":500-10000,
    "tool_description":"what this free tool would do"}}
]"""

    # ── Agent 5: Semantic Entity Agent (DeepSeek) ─────────────────────────────

    ENTITY_DENSITY = """Analyze entity coverage for keyword "{kw}".

These entities appear in top 3 competitors: {competitor_entities}
Our content would cover these entities: {our_entities}

Score entity richness (0-1): how many MORE or BETTER entities would our content have vs competitors?
Also rate GEO score: how likely is AI search (Perplexity/ChatGPT) to cite this content?

Return ONLY valid JSON:
{{"entity_richness_score":0.0-1.0,"geo_score":0.0-1.0,
  "missing_entities":["..."],"geo_tips":["..."]}}"""

    # ── Agent 6: Scoring Agent (DeepSeek) ────────────────────────────────────

    FINAL_SCORE = """Score this keyword. Return ONLY valid JSON, no markdown.
Keyword: "{kw}"
Intent: {intent}, KD estimate: {kd}, Volume estimate: {vol}
Business: {ctx}
Is information gap: {is_gap}
Is utility keyword: {is_utility}

{{
  "volume_score":0.0-1.0,
  "kd_inverse":0.0-1.0,
  "intent_match":0.0-1.0,
  "information_gain":0.0-1.0,
  "geo_score":0.0-1.0,
  "entity_richness":0.0-1.0,
  "business_rel":0.0-1.0,
  "reasoning":"one sentence"
}}"""

    # ── GSC Optimization Loop ────────────────────────────────────────────────

    OPTIMIZE_RANKING = """A webpage is ranking #11-20 for keyword "{kw}".
Current page title: "{title}"
Current meta description: "{meta_desc}"

From research: these pages need to be updated to include:
1. More entity-rich content
2. Better FAQ sections answering PAA questions
3. Information gain (unique data point)
4. Better internal linking

Suggest specific updates:
Return ONLY valid JSON:
{{
  "new_title":"...",
  "new_meta":"...",
  "add_faq_questions":["...","..."],
  "add_entities":["..."],
  "add_internal_links":["related page topic..."],
  "information_gain_suggestion":"specific unique angle to add"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — AGENT 1: FILTER AGENT
# ─────────────────────────────────────────────────────────────────────────────

class FilterAgent:
    """
    From research: "Exclusion of Social Noise — Professional SEOs explicitly
    exclude Reddit, Quora, LinkedIn to ensure AI isn't learning from unverified
    forum posts."
    
    BUT: We DO extract question titles from forums as keyword signals.
    We exclude the content, not the questions.
    """

    def filter_urls(self, urls: List[str]) -> Tuple[List[str], List[str]]:
        """Returns (included_urls, excluded_urls)."""
        included, excluded = [], []
        for url in urls:
            if any(d in url for d in Cfg.EXCLUDED_DOMAINS):
                excluded.append(url)
            else:
                included.append(url)
        log.info(f"[Filter] Included: {len(included)}, Excluded: {len(excluded)}")
        return included, excluded

    def extract_forum_questions(self, urls: List[str]) -> List[str]:
        """
        From excluded forum URLs — extract question titles ONLY (not body content).
        Forum titles are goldmine keyword signals.
        """
        from bs4 import BeautifulSoup
        questions = []
        forum_urls = [u for u in urls if any(d in u for d in Cfg.EXCLUDED_DOMAINS)]

        for url in forum_urls[:10]:
            try:
                r    = _req.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
                soup = BeautifulSoup(r.text, "html.parser")
                # Extract only titles/headlines — not body text
                title = soup.title.string.strip() if soup.title else ""
                h1    = [h.get_text(strip=True) for h in soup.find_all("h1")][:3]
                if title:
                    questions.append(title)
                questions.extend(h1)
                time.sleep(0.5)
            except Exception:
                pass

        return [q for q in questions if "?" in q or len(q.split()) > 4]

    def is_trusted_source(self, url: str) -> bool:
        return any(d in url for d in Cfg.TRUSTED_DOMAINS)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — AGENT 2: RESEARCHER AGENT
# ─────────────────────────────────────────────────────────────────────────────

class ResearcherAgent:
    """
    From research: "Find Information Gaps — questions people are asking that
    top-ranking pages haven't answered yet."
    Uses Gemini for live web research.
    """

    def find_information_gaps(self, keyword: str, pillar: str,
                               covered_topics: List[str]) -> dict:
        """
        Core "Information Gain" finder.
        From research: "Google rewards content that adds new information."
        """
        prompt = P.FIND_INFO_GAPS.format(
            keyword=keyword, pillar=pillar,
            covered_topics="\n".join(f"- {t}" for t in covered_topics[:30])
        )
        try:
            text   = AI.gemini(prompt, temperature=0.3)
            result = AI.parse_json(text)
            return result
        except Exception as e:
            log.warning(f"Info gap finding failed for '{keyword}': {e}")
            return {"info_gaps": [], "unique_data_points": []}

    def research_keyword(self, keyword: str, context: str) -> dict:
        """Find unique stats, quotes, angles for a keyword."""
        prompt = P.RESEARCH_LIVE.format(keyword=keyword, context=context)
        try:
            text   = AI.gemini(prompt, temperature=0.2)
            return AI.parse_json(text)
        except Exception as e:
            log.warning(f"Research failed for '{keyword}': {e}")
            return {"stats": [], "expert_quotes": [], "unique_angles": []}

    def scrape_paa(self, keyword: str) -> List[str]:
        """
        Scrape People Also Ask questions for a keyword.
        These are real questions Google users ask — direct keyword opportunities.
        """
        from bs4 import BeautifulSoup
        questions = []
        try:
            r = _req.get(
                "https://html.duckduckgo.com/html/",
                params={"q": f"{keyword} questions"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=10
            )
            soup = BeautifulSoup(r.text, "html.parser")
            # Extract question-format results
            for result in soup.select(".result__title"):
                text = result.get_text(strip=True)
                if "?" in text or text.lower().startswith(("how","what","why","when","does","is","can")):
                    questions.append(text)
        except Exception as e:
            log.debug(f"PAA scrape failed: {e}")

        # Also use Gemini to generate likely PAA questions
        try:
            prompt = f"""Generate 15 "People Also Ask" style questions that Google shows for "{keyword}".
These should be real questions people search for. Return ONLY a JSON array of question strings."""
            text  = AI.gemini(prompt, temperature=0.4)
            ai_qs = AI.parse_json(text)
            if isinstance(ai_qs, list):
                questions.extend(ai_qs)
        except Exception:
            pass

        return list(set(q for q in questions if len(q) > 10))[:20]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — AGENT 3: SEO STRATEGIST AGENT
# ─────────────────────────────────────────────────────────────────────────────

class SeoStrategistAgent:
    """
    From research: "Analyzes the SERP for a keyword. Identifies Intent
    and dictates required word count and heading structure."
    Uses DeepSeek (local) for classification.
    """

    # Quick rule-based intent (zero AI cost for obvious cases)
    TRANSACTIONAL = ["buy","price","purchase","order","shop","cheap","discount",
                     "sale","wholesale","bulk","shipping","delivery","cost"]
    COMMERCIAL    = ["best","top","review","compare","vs","versus","alternative",
                     "recommendation","which","ranking","rated"]
    INFORMATIONAL = ["how","what","why","when","where","does","is","are","can",
                     "benefits","uses","difference","meaning","definition","guide"]

    def classify(self, kw: str, ctx: dict) -> dict:
        """Classify keyword and estimate KD/volume using DeepSeek."""
        kl = kw.lower()
        # Fast rule-based first
        if any(w in kl for w in self.TRANSACTIONAL):
            quick_intent = "transactional"
        elif any(w in kl for w in self.COMMERCIAL):
            quick_intent = "commercial"
        elif any(w in kl for w in self.INFORMATIONAL):
            quick_intent = "informational"
        else:
            quick_intent = None

        try:
            text   = AI.deepseek(P.CLASSIFY_INTENT.format(kw=kw, ctx=json.dumps(ctx)[:200]))
            result = AI.parse_json(text)
            return result
        except Exception:
            # Fallback: estimates based on keyword characteristics
            return {
                "intent":              quick_intent or "informational",
                "kd_estimate":         self._estimate_kd(kw),
                "volume_estimate":     self._estimate_volume(kw),
                "intent_match_score":  0.7,
                "business_relevance":  0.6,
                "content_type":        "blog"
            }

    def _estimate_kd(self, kw: str) -> float:
        """Heuristic KD estimate when no API available."""
        words = len(kw.split())
        # Long-tail = lower difficulty generally
        if words >= 5: return 5.0
        if words == 4: return 12.0
        if words == 3: return 25.0
        if words == 2: return 45.0
        return 65.0

    def _estimate_volume(self, kw: str) -> int:
        """Heuristic volume estimate."""
        words = len(kw.split())
        if words >= 5: return 200
        if words == 4: return 800
        if words == 3: return 2000
        if words == 2: return 8000
        return 25000


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — AGENT 4: EXPANDER AGENT (8 LONG-TAIL METHODS)
# ─────────────────────────────────────────────────────────────────────────────

class ExpanderAgent:
    """
    8 long-tail methods from research + practical SEO.
    Uses Gemini for AI generation, free scraping for everything else.
    """

    # ── Method 1: PAA (People Also Ask) ──────────────────────────────────────

    def method_paa(self, kw: str) -> List[dict]:
        """Extract question-format keywords from PAA boxes."""
        researcher = ResearcherAgent()
        questions  = researcher.scrape_paa(kw)
        return [{"term": q, "method": "paa", "is_question": True,
                 "kd_estimate": 5.0, "volume_estimate": 300}
                for q in questions]

    # ── Method 2: Alphabet Expansion ─────────────────────────────────────────

    def method_alphabet(self, kw: str) -> List[dict]:
        """
        Google autocomplete with a-z prefix/suffix.
        From research: "Generates 200+ variations per keyword."
        """
        results = []
        for char in list("abcdefghijklmnopqrstuvwxyz") + [""]:
            query = f"{kw} {char}".strip() if char else kw
            try:
                r = _req.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client": "firefox", "q": query},
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=5
                )
                if r.ok:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 1:
                        for s in data[1]:
                            results.append({"term": str(s).lower(), "method": "alphabet",
                                            "is_question": "?" in str(s),
                                            "kd_estimate": 8.0, "volume_estimate": 400})
                time.sleep(0.25)
            except Exception:
                continue
        return results

    # ── Method 3: Preposition Expansion ──────────────────────────────────────

    def method_preposition(self, kw: str, context: str = "") -> List[dict]:
        """
        Add prepositions: for, with, without, before, after, during, vs...
        Creates high-intent comparison and use-case keywords.
        """
        results = []
        for prep in Cfg.PREPOSITIONS:
            term = f"{kw} {prep}"
            results.append({"term": term, "method": "preposition",
                             "is_question": False, "kd_estimate": 7.0, "volume_estimate": 300})
        # Also generate reverse: "prep kw"
        for prep in ["how to use", "when to use", "best way to use", "why use"]:
            results.append({"term": f"{prep} {kw}", "method": "preposition",
                             "is_question": False, "kd_estimate": 5.0, "volume_estimate": 400})
        return results

    # ── Method 4: Qualifier Expansion ────────────────────────────────────────

    def method_qualifier(self, kw: str) -> List[dict]:
        """
        Add qualifiers: best, organic, cheap, premium, fresh, whole...
        Creates product-specific long-tail keywords.
        """
        results = []
        for qual in Cfg.QUALIFIERS:
            for term in [f"best {qual} {kw}", f"{qual} {kw}", f"{kw} {qual}"]:
                results.append({"term": term.strip(), "method": "qualifier",
                                 "is_question": False, "kd_estimate": 6.0,
                                 "volume_estimate": 250})
        return results

    # ── Method 5: Utility / Tool Keywords ────────────────────────────────────

    def method_utility(self, kw: str, pillar: str, ctx: dict) -> List[dict]:
        """
        From research: "Bhanu Playbook — build free tools for utility keywords.
        AI [Task] Generator, Free [Industry] Calculator."
        Each tool page can rank #1 for 2000+ searches.
        """
        # Rule-based utility keywords
        rule_based = []
        for fmt in Cfg.UTILITY_FORMATS:
            rule_based.append({"term": f"{kw} {fmt}", "method": "utility",
                                "is_question": False, "is_utility": True,
                                "kd_estimate": 5.0, "volume_estimate": 800,
                                "tool_description": f"Free {fmt} for {kw}"})

        # AI-generated utility ideas (Gemini)
        try:
            text  = AI.gemini(P.UTILITY_KEYWORDS.format(
                pillar=pillar, universe=kw, ctx=json.dumps(ctx)[:200]
            ), temperature=0.4)
            ai_items = AI.parse_json(text)
            if isinstance(ai_items, list):
                for item in ai_items:
                    item["method"] = "utility"
                    item["is_utility"] = True
                    rule_based.append(item)
        except Exception as e:
            log.debug(f"Utility AI generation failed: {e}")

        return rule_based

    # ── Method 6: Competitor Heading Mining ──────────────────────────────────

    def method_competitor_headings(self, competitor_pages: List[dict]) -> List[dict]:
        """
        From research: "Crawl top 10 ranking pages. Extract all H2/H3 headings.
        These are proven keyword targets that already rank."
        Uses already-crawled SERP pages — no extra HTTP calls.
        """
        results = []
        for page in competitor_pages:
            for h in page.get("h2", []) + page.get("h3", []):
                if len(h.split()) >= 3:
                    results.append({"term": h.lower().strip(), "method": "competitor_heading",
                                    "is_question": "?" in h, "source_url": page.get("url",""),
                                    "kd_estimate": 18.0, "volume_estimate": 600})
        return results

    # ── Method 7: Forum Title Mining ─────────────────────────────────────────

    def method_forum_titles(self, forum_questions: List[str]) -> List[dict]:
        """
        From research: "Filter OUT Reddit/Quora posts BUT extract their titles —
        question titles = keyword gold."
        """
        return [{"term": q.lower().strip().rstrip("?"), "method": "forum_title",
                 "is_question": True, "kd_estimate": 4.0, "volume_estimate": 200}
                for q in forum_questions if len(q.split()) >= 4]

    # ── Method 8: Information Gap Keywords ───────────────────────────────────

    def method_info_gaps(self, gap_data: dict) -> List[dict]:
        """
        From research: "Information Gain — Google rewards content that adds new
        information. Find questions top pages DON'T answer."
        Highest-scoring keywords because they have no direct competition.
        """
        results = []
        for gap in gap_data.get("info_gaps", []):
            results.append({
                "term":            gap.get("question","").lower().rstrip("?"),
                "method":          "info_gap",
                "is_question":     True,
                "is_info_gap":     True,
                "why_unique":      gap.get("why_unique",""),
                "kd_estimate":     gap.get("estimated_kd", 5),
                "volume_estimate": gap.get("estimated_volume", 300),
            })
        return results

    # ── AI Batch Expansion ────────────────────────────────────────────────────

    def gemini_expand_all(self, kw: str, pillar: str, ctx: dict,
                           languages: List[str], location: str) -> List[dict]:
        """Use Gemini to generate 40+ long-tail variations across all 8 methods."""
        try:
            text  = AI.gemini(P.EXPAND_LONGTAIL.format(
                kw=kw, pillar=pillar, ctx=json.dumps(ctx)[:300],
                location=location, languages=", ".join(languages)
            ), temperature=0.4)
            items = AI.parse_json(text)
            if isinstance(items, list):
                return items
        except Exception as e:
            log.warning(f"Gemini expansion failed for '{kw}': {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — AGENT 5: SEMANTIC ENTITY AGENT
# ─────────────────────────────────────────────────────────────────────────────

class SemanticEntityAgent:
    """
    From research: "Analyze the Top 3 ranking competitors and identify the
    Entities they all use, then ensure your article has a HIGHER density
    of those entities."
    
    Also calculates GEO score — how likely AI search engines will cite this.
    """

    def extract_competitor_entities(self, competitor_pages: List[dict]) -> List[str]:
        """Extract entities that appear across multiple competitor pages."""
        all_text = " ".join([
            " ".join(p.get("h1",[])) + " " +
            " ".join(p.get("h2",[])) + " " +
            p.get("meta","")
            for p in competitor_pages[:5]
        ])

        # Named entity extraction: capitalized words, technical terms
        entities = list(set(re.findall(
            r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', all_text
        )))[:30]

        # Supplement with DeepSeek entity extraction
        if all_text:
            try:
                text = AI.deepseek(
                    f"Extract the 20 most important named entities (compounds, brands, places, "
                    f"technical terms) from this text. Return ONLY a JSON array of strings.\n"
                    f"Text: {all_text[:500]}",
                    temperature=0.0
                )
                ai_entities = AI.parse_json(text)
                if isinstance(ai_entities, list):
                    entities = list(set(entities + ai_entities))[:40]
            except Exception:
                pass

        return entities

    def score_entity_richness(self, kw: str, pillar: str,
                               competitor_entities: List[str],
                               context: str = "") -> Tuple[float, float]:
        """
        Returns (entity_richness_score, geo_score).
        Both 0.0-1.0.
        """
        try:
            text   = AI.deepseek(P.ENTITY_DENSITY.format(
                kw=kw, pillar=pillar,
                competitor_entities=", ".join(competitor_entities[:15]),
                our_entities=", ".join(competitor_entities[:10])   # assume we cover all
            ))
            result = AI.parse_json(text)
            return (float(result.get("entity_richness_score", 0.5)),
                    float(result.get("geo_score", 0.5)))
        except Exception:
            # Default: longer-tail keywords have more specific entities → higher richness
            word_count = len(kw.split())
            return (min(word_count / 8, 1.0), 0.5)

    def geo_score_keyword(self, kw: str, intent: str) -> float:
        """
        From research: "Ranking for AI Search requires optimizing for
        Perplexity, ChatGPT Search, Google AI Overviews."
        
        High GEO score:
        - Question format (AI engines love Q&A)
        - Definition keywords ("what is X")
        - Data/statistics keywords
        - Comparison keywords
        """
        kl = kw.lower()
        score = 0.5

        # Question format — highest GEO signal
        if kw.strip().endswith("?") or kl.startswith(("what","how","why","when","does","is","can")):
            score += 0.2

        # Definition keywords
        if any(w in kl for w in ["what is","definition","meaning","explained"]):
            score += 0.15

        # Data/comparison keywords
        if any(w in kl for w in ["percentage","statistics","data","study","research","compare","vs"]):
            score += 0.15

        # Specific/technical terms = more citable
        if len(kw.split()) >= 4:
            score += 0.1

        return min(score, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — AGENT 6: SCORING AGENT
# ─────────────────────────────────────────────────────────────────────────────

class ScoringAgent:
    """
    Final scoring for every keyword.
    Enforces 50/30/15/5 bucket distribution.
    """

    def score_keyword(self, kw_data: dict, ctx: dict,
                       entity_agent: SemanticEntityAgent,
                       competitor_entities: List[str],
                       is_priority: bool = False) -> KeywordScore:
        """Score one keyword across all 7 dimensions."""
        term  = kw_data.get("term","")
        intent= kw_data.get("intent","informational")
        kd    = float(kw_data.get("kd_estimate", 30))
        vol   = int(kw_data.get("volume_estimate", 500))
        is_gap= kw_data.get("is_info_gap", False)
        is_util=kw_data.get("is_utility", False)

        # 1. Volume score (log scale normalised 0-1)
        import math
        vol_score = min(math.log10(max(vol, 10)) / 5.0, 1.0)

        # 2. KD inverse (lower KD = higher score)
        kd_inv = 1.0 - (min(kd, 100) / 100.0)

        # 3. Intent match
        intent_map = {"transactional": 0.9, "commercial": 0.8,
                      "informational": 0.7, "navigational": 0.4}
        intent_score = intent_map.get(intent, 0.6)

        # 4. Information gain — key factor from research
        info_gain = 0.8 if is_gap else 0.3

        # 5. GEO score
        geo = entity_agent.geo_score_keyword(term, intent)

        # 6. Entity richness
        ent_rich, geo_deep = entity_agent.score_entity_richness(
            term, ctx.get("industry",""), competitor_entities
        )
        geo = max(geo, geo_deep)

        # 7. Business relevance (use DeepSeek — small task)
        biz_rel = 0.7  # default
        try:
            text    = AI.deepseek(
                f"Rate relevance of keyword '{term}' for business: {json.dumps(ctx)[:150]}. "
                f"Return ONLY a number 0.0-1.0.",
                temperature=0.0
            )
            biz_rel = float(re.search(r'0?\.\d+|[01]', text).group())
        except Exception:
            pass

        ks = KeywordScore(
            term=term, volume_score=vol_score, kd_inverse=kd_inv,
            intent_match=intent_score, information_gain=info_gain,
            geo_score=geo, entity_richness=ent_rich, business_rel=biz_rel,
            intent=intent, kd_estimate=kd, volume_estimate=vol,
            source=kw_data.get("source","generated"),
            long_tail_method=kw_data.get("method",""),
            is_info_gap=is_gap, is_utility=is_util,
            is_geo_optimised=geo > 0.7,
            language=kw_data.get("language","english"),
            region=kw_data.get("region","india"),
            gap_bonus=is_gap, priority_bonus=is_priority, utility_bonus=is_util
        )
        return ks

    def build_mix(self, all_scores: List[KeywordScore]) -> KeywordMix:
        """Sort keywords into 4 buckets. Enforce 50/30/15/5 distribution."""
        mix = KeywordMix()
        for ks in all_scores:
            if ks.bucket == "quick_win": mix.quick_wins.append(ks)
            elif ks.bucket == "medium":  mix.medium.append(ks)
            elif ks.bucket == "hard":    mix.hard.append(ks)
            else:                        mix.authority.append(ks)
        # Sort each bucket by score
        mix.quick_wins.sort(key=lambda x: x.final_score, reverse=True)
        mix.medium.sort(    key=lambda x: x.final_score, reverse=True)
        mix.hard.sort(      key=lambda x: x.final_score, reverse=True)
        mix.authority.sort( key=lambda x: x.final_score, reverse=True)
        return mix


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — GSC OPTIMIZATION LOOP
# ─────────────────────────────────────────────────────────────────────────────

class GscOptimizer:
    """
    From research: "Use Google Search Console API to find keywords ranking
    at #11-20. Trigger an Optimization Agent to re-research and update those
    specific posts to push them into the top 3."
    
    This is the fastest path to #1 — pages already ranking #11-20 need
    only small updates to jump to top 3.
    """

    def analyze_ranking_opportunity(self, keyword: str, current_rank: int,
                                     page_title: str, meta_desc: str,
                                     ctx: dict) -> dict:
        """
        Generate specific optimization suggestions for a near-ranking page.
        Uses DeepSeek (local).
        """
        if current_rank > 20:
            return {"skip": True, "reason": "Ranking too low for optimization"}

        try:
            text   = AI.deepseek(P.OPTIMIZE_RANKING.format(
                kw=keyword, title=page_title, meta_desc=meta_desc
            ), temperature=0.2)
            result = AI.parse_json(text)
            result["current_rank"]    = current_rank
            result["keyword"]         = keyword
            result["opportunity"]     = "high" if current_rank <= 15 else "medium"
            result["priority_action"] = "Update page within 7 days" if current_rank <= 15 else "Schedule update"
            return result
        except Exception as e:
            return {"error": str(e), "keyword": keyword, "current_rank": current_rank}

    def simulate_gsc_data(self, keywords: List[str]) -> List[dict]:
        """
        Simulate GSC data for testing.
        In production: connect to real Google Search Console API.
        """
        import random
        return [
            {"keyword": kw, "rank": random.randint(5, 25),
             "impressions": random.randint(100, 5000),
             "clicks": random.randint(5, 200),
             "ctr": round(random.uniform(0.01, 0.08), 3)}
            for kw in keywords
        ]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — MAIN SUPPORTING KEYWORD ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class SupportingKeywordEngine:
    """
    Main orchestrator for the 6-agent supporting keyword pipeline.

    Input:  pillar keyword + universe keyword + business context + competitor pages
    Output: KeywordMix — 4 buckets of scored, mixed keywords ready for content plan

    Pipeline:
      FilterAgent → ResearcherAgent → SeoStrategistAgent → ExpanderAgent
      → SemanticEntityAgent → ScoringAgent → KeywordMix
    """

    def __init__(self):
        self.filter     = FilterAgent()
        self.researcher = ResearcherAgent()
        self.strategist = SeoStrategistAgent()
        self.expander   = ExpanderAgent()
        self.entity     = SemanticEntityAgent()
        self.scorer     = ScoringAgent()
        self.gsc        = GscOptimizer()

    def run(self, pillar: str, universe: str, ctx: dict,
             competitor_pages: List[dict] = None,
             priority_keywords: List[str] = None,
             languages: List[str] = None,
             location: str = "India",
             top_n: int = 100) -> dict:
        """
        Full 6-agent supporting keyword pipeline.
        
        Args:
          pillar:            e.g. "black pepper health benefits"
          universe:          e.g. "black pepper"
          ctx:               business context dict
          competitor_pages:  list of dicts from SERP scraper
          priority_keywords: user-marked high-priority keywords
          languages:         e.g. ["english","malayalam","hindi"]
          top_n:             final keyword count (default 100)
        """
        t0      = time.time()
        comp_p  = competitor_pages or []
        prio_s  = set(k.lower() for k in (priority_keywords or []))
        langs   = languages or ["english"]
        log.info(f"[KW Engine] Starting — pillar: '{pillar}', universe: '{universe}'")
        steps   = []

        # ── Step 1: Filter competitor URLs ────────────────────────────────────
        t = time.time()
        all_urls    = [p.get("url","") for p in comp_p]
        incl, excl  = self.filter.filter_urls(all_urls)
        forum_qs    = self.filter.extract_forum_questions(all_urls)
        steps.append({"step":"filter","ms":int((time.time()-t)*1000),
                      "included":len(incl),"excluded":len(excl),"forum_questions":len(forum_qs)})
        log.info(f"[Filter] {len(incl)} sources included, {len(excl)} excluded, {len(forum_qs)} forum questions")

        # ── Step 2: Extract competitor entities + topics ───────────────────────
        t = time.time()
        competitor_entities = self.entity.extract_competitor_entities(comp_p)
        covered_topics      = []
        for p in comp_p[:10]:
            covered_topics.extend(p.get("h2",[]) + p.get("h3",[]))
        covered_topics = list(set(covered_topics))[:40]
        steps.append({"step":"entities","ms":int((time.time()-t)*1000),
                      "entities":len(competitor_entities),"covered_topics":len(covered_topics)})

        # ── Step 3: Research — find information gaps ───────────────────────────
        t = time.time()
        gap_data    = self.researcher.find_information_gaps(pillar, universe, covered_topics)
        paa_qs      = self.researcher.scrape_paa(pillar)
        steps.append({"step":"research","ms":int((time.time()-t)*1000),
                      "info_gaps":len(gap_data.get("info_gaps",[])),"paa":len(paa_qs)})
        log.info(f"[Research] {len(gap_data.get('info_gaps',[]))} info gaps, {len(paa_qs)} PAA questions")

        # ── Step 4: Long-tail expansion (all 8 methods) ───────────────────────
        t = time.time()
        raw_kws: List[dict] = []

        # Method 1: PAA
        raw_kws.extend(self.expander.method_paa(pillar))
        log.info(f"[Method 1 PAA] {len(raw_kws)} so far")

        # Method 2: Alphabet expansion
        alpha_kws = self.expander.method_alphabet(pillar)
        raw_kws.extend(alpha_kws)
        log.info(f"[Method 2 Alphabet] +{len(alpha_kws)} keywords")

        # Method 3: Preposition expansion
        prep_kws  = self.expander.method_preposition(pillar)
        raw_kws.extend(prep_kws)

        # Method 4: Qualifier expansion
        qual_kws  = self.expander.method_qualifier(universe)
        raw_kws.extend(qual_kws)

        # Method 5: Utility keywords (Bhanu Playbook)
        util_kws  = self.expander.method_utility(pillar, universe, ctx)
        raw_kws.extend(util_kws)
        log.info(f"[Method 5 Utility] +{len(util_kws)} tool keywords")

        # Method 6: Competitor headings
        comp_head = self.expander.method_competitor_headings(comp_p)
        raw_kws.extend(comp_head)
        log.info(f"[Method 6 Competitor Headings] +{len(comp_head)} keywords")

        # Method 7: Forum title mining
        forum_kws = self.expander.method_forum_titles(forum_qs)
        raw_kws.extend(forum_kws)

        # Method 8: Information gap keywords
        gap_kws   = self.expander.method_info_gaps(gap_data)
        raw_kws.extend(gap_kws)
        log.info(f"[Method 8 Info Gaps] +{len(gap_kws)} gap keywords")

        # Gemini batch expansion (covers all 8 methods in one call)
        gemini_kws = self.expander.gemini_expand_all(pillar, universe, ctx, langs, location)
        raw_kws.extend(gemini_kws)
        log.info(f"[Gemini Expansion] +{len(gemini_kws)} AI-generated keywords")

        # PAA questions as keywords
        for q in paa_qs:
            raw_kws.append({"term": q.lower().rstrip("?"), "method": "paa",
                             "is_question": True, "kd_estimate": 5.0, "volume_estimate": 300})

        steps.append({"step":"expansion","ms":int((time.time()-t)*1000),
                      "raw_count":len(raw_kws)})
        log.info(f"[Expansion] Total raw: {len(raw_kws)} keywords")

        # ── Step 5: Deduplication ──────────────────────────────────────────────
        t = time.time()
        seen, deduped = set(), []
        for item in raw_kws:
            term = item.get("term","").lower().strip()
            if not term or len(term) < 4:
                continue
            h = hashlib.md5(term.encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                item["term"] = term
                deduped.append(item)
        steps.append({"step":"dedup","ms":int((time.time()-t)*1000),
                      "before":len(raw_kws),"after":len(deduped)})
        log.info(f"[Dedup] {len(raw_kws)} → {len(deduped)}")

        # Semantic dedup on English keywords
        english_only = [i for i in deduped if i.get("language","english") == "english"]
        if len(english_only) > 10:
            try:
                import numpy as np
                from sklearn.metrics.pairwise import cosine_similarity
                terms = [i["term"] for i in english_only]
                emb   = np.array(AI.embed(terms))
                sim   = cosine_similarity(emb)
                keep  = set(range(len(terms)))
                for i in range(len(terms)):
                    for j in range(i+1, len(terms)):
                        if j in keep and sim[i][j] >= Cfg.DEDUP_THRESHOLD:
                            keep.discard(j)
                kept_terms = set(terms[i] for i in keep)
                deduped    = [i for i in deduped
                              if i.get("language","english") != "english"
                              or i["term"] in kept_terms]
                log.info(f"[Semantic Dedup] {len(english_only)} → {len(kept_terms)} English keywords")
            except Exception as e:
                log.warning(f"Semantic dedup failed: {e}")

        # ── Step 6: SEO Strategy classification ───────────────────────────────
        t = time.time()
        classified = []
        for item in deduped:
            classified_item = self.strategist.classify(item["term"], ctx)
            item.update(classified_item)
            classified.append(item)
        steps.append({"step":"classify","ms":int((time.time()-t)*1000),
                      "classified":len(classified)})

        # ── Step 7: Score all keywords ─────────────────────────────────────────
        t = time.time()
        all_scores: List[KeywordScore] = []
        for item in classified:
            is_prio = item.get("term","") in prio_s
            ks = self.scorer.score_keyword(item, ctx, self.entity,
                                            competitor_entities, is_prio)
            all_scores.append(ks)
        steps.append({"step":"scoring","ms":int((time.time()-t)*1000),
                      "scored":len(all_scores)})
        log.info(f"[Scoring] Scored {len(all_scores)} keywords")

        # ── Step 8: Build keyword mix ──────────────────────────────────────────
        mix      = self.scorer.build_mix(all_scores)
        top_mix  = mix.top_n(top_n)

        # ── Step 9: GSC optimization loop (simulated) ─────────────────────────
        gsc_data      = self.gsc.simulate_gsc_data([k.term for k in top_mix[:20]])
        opportunities = [g for g in gsc_data if 11 <= g["rank"] <= 20]
        gsc_recs      = []
        for opp in opportunities[:5]:
            rec = self.gsc.analyze_ranking_opportunity(
                opp["keyword"], opp["rank"], f"{opp['keyword']} guide",
                f"Learn about {opp['keyword']}", ctx
            )
            gsc_recs.append(rec)

        total_ms = int((time.time()-t0)*1000)
        log.info(f"[KW Engine] Complete. {mix.stats['total']} keywords, "
                 f"{mix.stats['info_gaps']} info gaps, {mix.stats['utility_kws']} utility. "
                 f"Total: {total_ms}ms")

        return {
            "pillar":             pillar,
            "universe":           universe,
            "keyword_mix":        mix,
            "top_keywords":       [k.to_dict() for k in top_mix],
            "quick_wins":         [k.to_dict() for k in mix.quick_wins[:20]],
            "info_gaps":          [k.to_dict() for k in all_scores if k.is_info_gap],
            "utility_keywords":   [k.to_dict() for k in all_scores if k.is_utility],
            "competitor_entities":competitor_entities[:20],
            "covered_topics":     covered_topics[:20],
            "info_gap_data":      gap_data,
            "gsc_opportunities":  gsc_recs,
            "steps":              steps,
            "stats": {**mix.stats,
                      "total_ms": total_ms,
                      "quick_win_pct": round(len(mix.quick_wins)/max(mix.stats["total"],1)*100,1),
                      "medium_pct":    round(len(mix.medium)/max(mix.stats["total"],1)*100,1),
                      "hard_pct":      round(len(mix.hard)/max(mix.stats["total"],1)*100,1),
                      "authority_pct": round(len(mix.authority)/max(mix.stats["total"],1)*100,1),
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — INTEGRATION WITH RUFLO v3 UNIVERSE PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def add_supporting_keywords_to_universe(universe_result: dict,
                                         project_ctx: dict,
                                         languages: List[str] = None) -> dict:
    """
    Integrates this engine into Ruflo v3's universe tree.
    Called AFTER pillars are identified — runs the supporting keyword engine
    for each pillar in the universe.
    """
    engine  = SupportingKeywordEngine()
    tree    = universe_result.get("universe_tree", {})
    universe= tree.get("universe","")
    pillars = tree.get("pillars", [])

    enhanced_pillars = []
    for pillar in pillars:
        log.info(f"[Integration] Running supporting KW engine for pillar: {pillar['name']}")
        result = engine.run(
            pillar=pillar["name"],
            universe=universe,
            ctx=project_ctx,
            competitor_pages=[],   # inject real SERP pages in production
            languages=languages or ["english"],
            top_n=50   # 50 supporting keywords per pillar
        )
        pillar["supporting_keyword_engine"] = {
            "top_50":        result["top_keywords"],
            "quick_wins":    result["quick_wins"],
            "info_gaps":     result["info_gaps"],
            "utility_kws":   result["utility_keywords"],
            "stats":         result["stats"],
            "gsc_loop":      result["gsc_opportunities"],
        }
        enhanced_pillars.append(pillar)

    tree["pillars"] = enhanced_pillars
    universe_result["universe_tree"] = tree
    return universe_result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — TEST SUITE
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    CTX = {"business_name":"PureSpice Organics","industry":"Organic Spices",
           "business_type":"D2C","target_location":"Wayanad, Kerala",
           "target_audience":["Home cooks","Health buyers","Exporters"]}

    MOCK_COMP_PAGES = [
        {"url":"https://healthline.com/black-pepper", "h1":["Black Pepper Benefits"],
         "h2":["Health Benefits","Nutrition Facts","Uses in Cooking","Side Effects"],
         "h3":["Antioxidants","Anti-inflammatory","Digestion"],
         "meta":"Discover the health benefits of black pepper..."},
        {"url":"https://medicalnewstoday.com/pepper", "h1":["Black Pepper: What to Know"],
         "h2":["Nutritional profile","Health benefits","How to use","Risks"],
         "h3":["Piperine","Blood sugar","Cholesterol"],
         "meta":"Black pepper is a common spice with health benefits..."},
    ]

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_filter(self):
        self._h("Filter Agent")
        agent  = FilterAgent()
        urls   = ["https://reddit.com/r/cooking/black-pepper",
                  "https://pubmed.ncbi.nlm.nih.gov/piperine",
                  "https://quora.com/what-is-black-pepper",
                  "https://who.int/spices",
                  "https://linkedin.com/black-pepper-post"]
        incl, excl = agent.filter_urls(urls)
        self._ok(f"Included: {incl}")
        self._ok(f"Excluded: {excl}")
        assert len(excl) == 3, "Should exclude Reddit, Quora, LinkedIn"

    def test_methods_all_8(self):
        self._h("All 8 Long-tail Methods")
        expander = ExpanderAgent()

        m1 = expander.method_paa("black pepper")
        self._ok(f"Method 1 PAA: {len(m1)} questions")

        m3 = expander.method_preposition("black pepper")
        self._ok(f"Method 3 Preposition: {len(m3)} keywords — {[k['term'] for k in m3[:3]]}")

        m4 = expander.method_qualifier("black pepper")
        self._ok(f"Method 4 Qualifier: {len(m4)} keywords")

        m5 = expander.method_utility("black pepper health", "black pepper", self.CTX)
        self._ok(f"Method 5 Utility: {len(m5)} tool keywords — {[k['term'] for k in m5[:3]]}")

        m6 = expander.method_competitor_headings(self.MOCK_COMP_PAGES)
        self._ok(f"Method 6 Competitor Headings: {len(m6)} keywords — {[k['term'] for k in m6[:3]]}")

        gap_data = {"info_gaps": [
            {"question": "does black pepper affect drug absorption", "why_unique": "medical angle", "estimated_kd": 6, "estimated_volume": 800}
        ]}
        m8 = expander.method_info_gaps(gap_data)
        self._ok(f"Method 8 Info Gap: {len(m8)} keywords — {[k['term'] for k in m8]}")

    def test_scoring(self):
        self._h("Keyword Scoring — 7 dimensions")
        entity_agent = SemanticEntityAgent()
        scorer       = ScoringAgent()
        test_kws     = [
            {"term":"does black pepper affect drug absorption","method":"info_gap",
             "is_info_gap":True,"kd_estimate":6,"volume_estimate":800,
             "intent":"informational","language":"english"},
            {"term":"buy organic black pepper Kerala","method":"qualifier",
             "kd_estimate":8,"volume_estimate":1200,"intent":"transactional","language":"english"},
            {"term":"black pepper health benefits","method":"competitor_heading",
             "kd_estimate":35,"volume_estimate":18000,"intent":"informational","language":"english"},
            {"term":"black pepper calculator","method":"utility",
             "is_utility":True,"kd_estimate":4,"volume_estimate":600,
             "intent":"informational","language":"english"},
        ]
        comp_entities = ["Piperine","Piper nigrum","cinnamaldehyde","bioavailability"]
        scores = []
        for kw_data in test_kws:
            ks = scorer.score_keyword(kw_data, self.CTX, entity_agent, comp_entities)
            scores.append(ks)
            self._ok(f"'{ks.term}' → score:{ks.final_score}, bucket:{ks.bucket}, geo:{ks.geo_score:.2f}")

        mix = scorer.build_mix(scores)
        self._ok(f"Mix stats: {mix.stats}")

    def test_mix_enforcement(self):
        self._h("Keyword Mix Enforcement (50/30/15/5)")
        import random
        # Create 200 fake keywords with different KDs
        all_kws = []
        entity_agent = SemanticEntityAgent()
        for i in range(200):
            kd = random.choice([3,5,7,15,20,25,40,50,70,80])
            ks = KeywordScore(term=f"keyword {i}", kd_estimate=kd,
                              volume_estimate=random.randint(100,10000))
            all_kws.append(ks)
        scorer = ScoringAgent()
        mix    = scorer.build_mix(all_kws)
        top100 = mix.top_n(100)
        qw   = sum(1 for k in top100 if k.bucket == "quick_win")
        med  = sum(1 for k in top100 if k.bucket == "medium")
        hard = sum(1 for k in top100 if k.bucket == "hard")
        auth = sum(1 for k in top100 if k.bucket == "authority")
        self._ok(f"Top 100 distribution: quick_win={qw}, medium={med}, hard={hard}, authority={auth}")
        self._ok(f"Ratios: {qw}%/{med}%/{hard}%/{auth}% (target 50/30/15/5)")

    def test_info_gain(self):
        self._h("Information Gain Finder")
        researcher = ResearcherAgent()
        covered    = ["health benefits","nutrition facts","how to use","side effects",
                      "recipes","cooking tips","storing pepper","black pepper in food"]
        gaps       = researcher.find_information_gaps("black pepper", "black pepper health benefits", covered)
        self._ok(f"Info gaps found: {len(gaps.get('info_gaps',[]))}")
        for g in gaps.get("info_gaps",[])[:3]:
            self._ok(f"  Gap: {g.get('question','')} — {g.get('why_unique','')[:50]}")
        self._ok(f"Unique data points: {gaps.get('unique_data_points',[])[:2]}")

    def test_geo_scoring(self):
        self._h("GEO Scoring (AI Search Optimization)")
        entity_agent = SemanticEntityAgent()
        test_kws     = [
            ("what is piperine in black pepper",          "informational"),
            ("black pepper vs white pepper",              "informational"),
            ("buy black pepper",                          "transactional"),
            ("piperine percentage in black pepper study", "informational"),
        ]
        for kw, intent in test_kws:
            geo = entity_agent.geo_score_keyword(kw, intent)
            self._ok(f"'{kw}' → GEO score: {geo:.2f} {'(high — AI will cite)' if geo > 0.7 else ''}")

    def test_gsc_loop(self):
        self._h("GSC Optimization Loop (#11-20 → #1)")
        gsc  = GscOptimizer()
        data = gsc.simulate_gsc_data(["black pepper benefits","buy organic black pepper",
                                       "piperine absorption","black pepper for cough"])
        self._ok(f"GSC data: {data}")
        opps = [d for d in data if 11 <= d["rank"] <= 20]
        self._ok(f"Optimization opportunities (ranking #11-20): {len(opps)}")
        for opp in opps[:2]:
            rec = gsc.analyze_ranking_opportunity(
                opp["keyword"], opp["rank"], "Black Pepper Guide", "Learn about black pepper...",
                self.CTX
            )
            self._ok(f"  '{opp['keyword']}' at #{opp['rank']} → {rec.get('priority_action','?')}")

    def test_full_engine(self):
        self._h("FULL SUPPORTING KEYWORD ENGINE")
        engine = SupportingKeywordEngine()
        result = engine.run(
            pillar="black pepper health benefits",
            universe="black pepper",
            ctx=self.CTX,
            competitor_pages=self.MOCK_COMP_PAGES,
            priority_keywords=["black pepper piperine benefits","buy organic black pepper Kerala"],
            languages=["english","malayalam"],
            location="Wayanad, Kerala",
            top_n=50
        )
        self._ok(f"Stats: {result['stats']}")
        self._ok(f"Quick wins: {[k['term'] for k in result['quick_wins'][:3]]}")
        self._ok(f"Info gaps: {[k['term'] for k in result['info_gaps'][:3]]}")
        self._ok(f"Utility keywords: {[k['term'] for k in result['utility_keywords'][:3]]}")
        self._ok(f"GSC opportunities: {len(result['gsc_opportunities'])}")
        print(f"\n  Top 5 keywords by score:")
        for k in result["top_keywords"][:5]:
            print(f"    [{k['bucket']}] {k['term']} — score:{k['final_score']}, kd:{k['kd_estimate']}, gap:{k['is_info_gap']}")
        return result

    def run_all(self):
        tests = [
            ("filter",      self.test_filter),
            ("methods",     self.test_methods_all_8),
            ("scoring",     self.test_scoring),
            ("mix",         self.test_mix_enforcement),
            ("info_gain",   self.test_info_gain),
            ("geo",         self.test_geo_scoring),
            ("gsc",         self.test_gsc_loop),
        ]
        print("\n" + "═"*55)
        print("  SUPPORTING KEYWORD ENGINE — STAGE TESTS")
        print("═"*55)
        p = f = 0
        for name, fn in tests:
            try:
                fn()
                p += 1
            except Exception as e:
                print(f"  ✗ {name}: {e}")
                f += 1
        print("\n" + "═"*55)
        print(f"  {p} passed / {f} failed")
        print("═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 15 — CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
Ruflo — Supporting Keyword & Long-tail Engine
─────────────────────────────────────────────────────
Implements:
  • 50/30/15/5 keyword mix (easy/medium/hard/authority)
  • 8 long-tail methods (PAA, alphabet, preposition, qualifier, utility,
    competitor headings, forum titles, information gaps)
  • Information Gain scoring (most important ranking factor)
  • GEO scoring (AI search optimization — Perplexity/ChatGPT)
  • 6-agent pipeline (Filter → Research → Strategist → Expander → Entity → Score)
  • GSC optimization loop (#11-20 → push to #1)

Usage:
  python ruflo_supporting_keyword_engine.py test              # all tests
  python ruflo_supporting_keyword_engine.py test <stage>      # one test
  python ruflo_supporting_keyword_engine.py run <pillar>      # run engine on a pillar
  python ruflo_supporting_keyword_engine.py full              # full engine test

Stages: filter, methods, scoring, mix, info_gain, geo, gsc
"""
    if len(sys.argv) < 2:
        print(HELP); sys.exit(0)
    cmd = sys.argv[1]

    if cmd == "test":
        t = Tests()
        if len(sys.argv) == 3:
            fn = getattr(t, f"test_{sys.argv[2]}", None)
            if fn: fn()
            else:  print(f"Unknown: {sys.argv[2]}")
        else:
            t.run_all()

    elif cmd == "run":
        pillar = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "black pepper health benefits"
        engine = SupportingKeywordEngine()
        result = engine.run(pillar=pillar, universe=pillar.split()[0],
                            ctx={"business_name":"Demo","industry":"Spices"},
                            top_n=50)
        print(f"\nStats: {json.dumps(result['stats'], indent=2)}")
        print(f"\nTop 10:")
        for k in result["top_keywords"][:10]:
            print(f"  [{k['bucket']:10}] {k['term'][:50]:50} score:{k['final_score']}")

    elif cmd == "full":
        Tests().test_full_engine()

    else:
        print(f"Unknown: {cmd}\n{HELP}")

"""
================================================================================
RUFLO — STRATEGY DEVELOPMENT ENGINE
================================================================================
Business-agnostic strategy engine that thinks like a human strategist.

Key innovation: Audience Intelligence Engine
  "Who buys spices?" → home cooks → wives at home → "best masala for fish curry"
  "Who else?"        → restaurants → bulk buyers → "wholesale pepper Kerala"
  "Who else?"        → Christians → Christmas bakers → "Christmas cake cinnamon"
  "Who else?"        → Muslims → Malabar cooks → "halal biryani masala Moplah"

Context Engine: Location × Religion × Language = unique keyword clusters
  Christian × Malabar × Malayalam = "Kerala Christmas plum cake karuvapatta"
  Muslim × Malabar × English      = "Malabar chicken masala halal recipe"
  Hindu × Wayanad × Malayalam     = "Wayanad ജൈവ കുരുമുളക് Ayurveda"

Works for ANY business: spice brand, hospital, tourism, SaaS, real estate.
Industry determines the entire strategy template, persona chains, content type.

AI routing:
  DeepSeek (Ollama) → audience chain expansion, intent classification, scoring
  Gemini (free)     → persona elaboration, context keyword generation
  Claude Sonnet     → final strategy synthesis (called once)
================================================================================
"""

import os, json, re, time, logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv
import requests as _req

load_dotenv()
log = logging.getLogger("ruflo.strategy_dev")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — ENUMS & CONFIG
# ─────────────────────────────────────────────────────────────────────────────

class Industry(str, Enum):
    FOOD_SPICES   = "food_spices"
    HEALTHCARE    = "healthcare"
    TOURISM       = "tourism"
    ECOMMERCE     = "ecommerce"
    EDUCATION     = "education"
    REAL_ESTATE   = "real_estate"
    RESTAURANT    = "restaurant"
    FASHION       = "fashion"
    TECH_SAAS     = "tech_saas"
    WELLNESS      = "wellness"
    AGRICULTURE   = "agriculture"
    GENERAL       = "general"

class Religion(str, Enum):
    HINDU     = "hindu"
    MUSLIM    = "muslim"
    CHRISTIAN = "christian"
    GENERAL   = "general"
    ALL       = "all"

class Language(str, Enum):
    ENGLISH   = "english"
    MALAYALAM = "malayalam"
    HINDI     = "hindi"
    TAMIL     = "tamil"
    KANNADA   = "kannada"
    TELUGU    = "telugu"
    ARABIC    = "arabic"

class GeoLevel(str, Enum):
    GLOBAL      = "global"
    NATIONAL    = "national"
    SOUTH_INDIA = "south_india"
    KERALA      = "kerala"
    MALABAR     = "malabar"
    WAYANAD     = "wayanad"
    KOCHI       = "kochi"
    KOZHIKODE   = "kozhikode"
    THRISSUR    = "thrissur"
    KOTTAYAM    = "kottayam"
    CUSTOM      = "custom"


class Cfg:
    OLLAMA_URL     = os.getenv("OLLAMA_URL",     "http://172.235.16.165:11434")
    OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL",   "deepseek-r1:7b")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL   = os.getenv("GEMINI_MODEL",   "gemini-1.5-flash")
    GEMINI_RATE    = float(os.getenv("GEMINI_RATE", "4.0"))
    GROQ_API_KEY   = os.getenv("GROQ_API_KEY",   "")
    GROQ_MODEL     = os.getenv("GROQ_MODEL",     "llama-3.3-70b-instruct")
    ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL   = os.getenv("CLAUDE_MODEL",   "claude-sonnet-4-6")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — USER INPUT MODEL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UserInput:
    """Everything the user provides in the onboarding form."""

    # Business identity
    business_name:   str
    website_url:     str
    industry:        Industry
    business_type:   str               # B2C / B2B / D2C / Service
    usp:             str               # unique selling proposition
    products:        List[str]         # ["Black Pepper","Cardamom","Masala Mix"]
    competitor_urls: List[str]

    # Target audience (multi-select)
    target_locations:  List[GeoLevel]  # [GeoLevel.KERALA, GeoLevel.MALABAR]
    target_religions:  List[Religion]  # [Religion.MUSLIM, Religion.CHRISTIAN]
    target_languages:  List[Language]  # [Language.ENGLISH, Language.MALAYALAM]
    audience_personas: List[str]       # ["Home cooks","Restaurant owners"]

    # Optional power inputs
    ad_copy:          str = ""         # existing ad copy to mirror
    customer_reviews: List[str] = field(default_factory=list)
    faq_list:         List[str] = field(default_factory=list)
    seasonal_events:  List[str] = field(default_factory=list)  # ["Christmas","Onam","Eid"]
    custom_regions:   List[str] = field(default_factory=list)  # ["Thrissur","Kozhikode"]
    pillars:          List[dict] = field(default_factory=list)
    supporting_keywords: List[str] = field(default_factory=list)
    intent_focus:     str = "transactional"
    customer_url:     str = ""

    # Intent focus
    primary_intent:   str = "awareness"  # awareness/consideration/purchase/retention


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — AI HELPERS
# ─────────────────────────────────────────────────────────────────────────────

class AI:
    _embed_model = None

    @staticmethod
    def deepseek(prompt: str, system: str = "You are a strategic marketing expert.",
                  temperature: float = 0.2) -> str:
        """Ollama/DeepSeek via central AIRouter — no retry."""
        try:
            from core.ai_config import AIRouter
            return AIRouter._call_ollama(prompt, system, temperature)
        except ImportError:
            pass
        return ""

    @staticmethod
    def gemini(prompt: str, temperature: float = 0.4) -> str:
        """Routes through central AIRouter (Groq → Ollama → Gemini, no retry)."""
        try:
            from core.ai_config import AIRouter
            text, _ = AIRouter.call(prompt, temperature=temperature)
            return text
        except ImportError:
            pass
        return ""

    @staticmethod
    def groq(prompt: str, temperature: float = 0.25) -> str:
        """Routes through central AIRouter (Groq → Ollama → Gemini, no retry)."""
        try:
            from core.ai_config import AIRouter
            text, _ = AIRouter.call(prompt, temperature=temperature)
            return text
        except ImportError:
            pass
        return ""

    @staticmethod
    def claude(system: str, prompt: str, max_tokens: int = 3000) -> Tuple[str, int]:
        if not Cfg.ANTHROPIC_KEY:
            log.warning("No ANTHROPIC_API_KEY")
            return '{"error":"no key"}', 0
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=Cfg.ANTHROPIC_KEY)
            r = client.messages.create(
                model=Cfg.CLAUDE_MODEL, max_tokens=max_tokens,
                system=system,
                messages=[{"role":"user","content":prompt}]
            )
            return r.content[0].text.strip(), r.usage.input_tokens + r.usage.output_tokens
        except Exception as e:
            log.error(f"Claude error: {e}")
            return '{"error":"' + str(e) + '"}', 0

    @staticmethod
    def parse_json(text: str) -> Any:
        text = re.sub(r"<think>.*?</think>","",text,flags=re.DOTALL)
        text = re.sub(r"```(?:json)?","",text).strip().rstrip("`").strip()
        m = re.search(r'(\{.*\}|\[.*\])',text,re.DOTALL)
        if m:
            return json.loads(m.group(1))
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — INDUSTRY TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

INDUSTRY_TEMPLATES: Dict[Industry, dict] = {

    Industry.FOOD_SPICES: {
        "content_types": ["recipe","how_to","product","comparison","health","blog"],
        "schema_priority": ["Recipe","Product","FAQPage","HowTo","Article"],
        "persona_seeds": [
            "home cooks", "restaurant owners", "spice dealers",
            "Ayurvedic practitioners", "export buyers", "gift buyers",
            "health-conscious buyers", "NRI families"
        ],
        "keyword_modifiers": [
            "recipe", "benefits", "buy", "organic", "price", "uses",
            "substitute", "storage", "fresh", "wholesale", "farm direct"
        ],
        "seasonal_peaks": {
            "Christmas":  ["baking spices","cake spice","cinnamon","cardamom","cloves"],
            "Onam":       ["sadya spices","sambar powder","curry leaves"],
            "Eid":        ["biryani masala","halal spices","Malabar masala"],
            "Diwali":     ["mithai spices","sweets masala","cardamom"],
            "Harvest":    ["new crop pepper","fresh cardamom","first flush"],
        },
        "religion_content": {
            Religion.CHRISTIAN: [
                "Christmas plum cake spice mix",
                "Kerala Christmas cake {product} recipe",
                "Christmas baking spice set Kerala",
                "Lent-friendly {product} dishes",
            ],
            Religion.MUSLIM: [
                "Malabar {product} chicken masala halal",
                "Eid biryani spice mix with {product}",
                "halal certified {product} Kerala",
                "Ramadan {product} recipes",
                "Moplah {product} recipe traditional",
            ],
            Religion.HINDU: [
                "Onam sadya {product} recipe",
                "{product} in Ayurveda benefits",
                "satvik cooking with {product}",
                "Vishu {product} festival recipe",
                "trikatu {product} Ayurvedic",
            ],
        },
        "region_content": {
            GeoLevel.MALABAR:  ["Malabar {product}","Kozhikode style {product}","Moplah {product}"],
            GeoLevel.WAYANAD:  ["Wayanad {product} farm direct","Wayanad organic {product}"],
            GeoLevel.KOTTAYAM: ["Kottayam duck curry {product}","Syrian Christian {product} recipe"],
            GeoLevel.THRISSUR: ["Thrissur {product} traditional","Thrissur festival {product}"],
        },
        "intent_flow": ["informational","comparison","commercial","transactional"],
    },

    Industry.HEALTHCARE: {
        "content_types": ["symptom_guide","treatment_info","doctor_profile",
                          "patient_story","cost_guide","faq","procedure_explainer"],
        "schema_priority": ["MedicalWebPage","Physician","MedicalProcedure","FAQPage","Article"],
        "persona_seeds": [
            "patients seeking diagnosis", "family caregivers",
            "medical tourists", "NRI patients", "corporate health",
            "senior citizens", "chronic disease patients", "new parents"
        ],
        "keyword_modifiers": [
            "symptoms", "treatment", "cost", "doctor", "specialist",
            "hospital", "surgery", "recovery", "best", "how to"
        ],
        "religion_content": {
            Religion.MUSLIM: [
                "halal food during hospital stay {location}",
                "prayer facilities {hospital_name}",
                "Arabic speaking doctors Kerala hospital",
            ],
            Religion.HINDU: [
                "Ayurvedic integrative care {specialty}",
                "yoga after {procedure} recovery",
            ],
            Religion.CHRISTIAN: [
                "chaplaincy services hospital Kerala",
                "faith-based counselling {location}",
            ],
        },
        "region_content": {
            GeoLevel.KERALA:  ["best {specialty} hospital Kerala","Kerala medical tourism"],
            GeoLevel.NATIONAL:["top {specialty} doctors India","affordable {procedure} India"],
        },
        "intent_flow": ["informational","consideration","comparison","appointment"],
        "eeat_critical": True,  # E-E-A-T is especially important for healthcare
    },

    Industry.TOURISM: {
        "content_types": ["travel_guide","itinerary","hotel_review",
                          "activity_guide","food_guide","packing_list"],
        "schema_priority": ["TouristAttraction","Hotel","FAQPage","HowTo","Article"],
        "persona_seeds": [
            "honeymoon couples", "family travellers", "solo travellers",
            "adventure seekers", "pilgrims", "NRI visiting home",
            "corporate retreats", "photography enthusiasts"
        ],
        "keyword_modifiers": [
            "package", "itinerary", "hotel", "homestay", "guide",
            "places to visit", "things to do", "weather", "how to reach"
        ],
        "religion_content": {
            Religion.MUSLIM: [
                "halal food {destination}","Muslim friendly hotels {destination}",
                "prayer room availability {destination}",
            ],
            Religion.HINDU: [
                "temple tour {destination}","pilgrimage {destination}",
                "Onam celebration {destination}",
            ],
            Religion.CHRISTIAN: [
                "church visit {destination}","Christmas celebration {destination}",
                "Good Friday {destination}",
            ],
        },
        "intent_flow": ["inspiration","planning","booking","post_visit"],
    },

    # Add more industries as needed — each gets its own template
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — AUDIENCE INTELLIGENCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class AudienceIntelligenceEngine:
    """
    The core innovation. Chains of "Who buys this? Who else? Who else?"
    until all buyer personas are mapped, each with their search behaviour.

    Example chain for spices:
      Home cooks → wives at home → "best masala for fish curry"
      Home cooks → health-conscious → "organic black pepper benefits"
      Restaurant owners → bulk buyers → "wholesale pepper Kerala"
      Christian families → Christmas bakers → "Christmas cake cinnamon Kerala"
    """

    PERSONA_CHAIN_PROMPT = """You are a consumer behaviour expert. Think deeply about WHO buys {product} from {business}.

Start with the most obvious buyers, then keep asking "who else?" until you find 
non-obvious but real audience segments.

For each persona, think:
- Who exactly are they? (be specific, not generic)
- When do they buy? (occasion, season, need)
- Why do they buy? (motivation, pain point)
- How do they search? (exact search queries, language they use)
- What else do they buy at the same time? (supporting keywords)

Context:
- Industry: {industry}
- Locations: {locations}
- Religions: {religions}
- Languages: {languages}
- USP: {usp}

Go beyond the obvious. Think about:
- Festival and seasonal buyers
- Religious community-specific needs
- Regional food culture variations
- Professional vs home users
- Gift buyers
- NRI/diaspora buyers

Return ONLY valid JSON:
{{
  "persona_chains": [
    {{
      "persona_name": "specific name e.g. Kerala Christian Christmas Baker",
      "who_exactly": "wives in Kerala Christian families who bake plum cake every December",
      "when_they_buy": "November–December, before Christmas",
      "why_they_buy": "need authentic spices for traditional Kerala Christmas plum cake",
      "search_queries": [
        "Christmas cake cinnamon powder Kerala",
        "Kerala plum cake spices list",
        "best cinnamon for Christmas cake"
      ],
      "language": "english|malayalam|hindi|tamil",
      "religion": "hindu|muslim|christian|general",
      "region": "specific region",
      "supporting_keywords": ["related things they also search"],
      "content_ideas": ["what article/page would convert this persona"],
      "purchase_intent": "high|medium|low",
      "seasonal_peak": "month or event name",
      "reach_channel": "Google|Instagram|Facebook|WhatsApp|YouTube"
    }}
  ],
  "total_personas": 0,
  "key_insight": "the non-obvious persona most competitors are missing"
}}

Generate at least 10 personas. Go deep and specific."""

    SEARCH_LANGUAGE_PROMPT = """For the persona "{persona_name}" who searches in {language}:

Convert these search queries into natural {language} search terms that a real person would type.
Not a translation — think about how a {persona_name} would ACTUALLY search in {language}.

Queries to convert: {queries}

Return ONLY valid JSON array:
[
  {{"english": "original query", "native": "natural {language} version", "notes": "why this phrasing"}}
]"""

    SUPPORTING_KEYWORDS_PROMPT = """For someone who is searching for "{main_keyword}", what ELSE do they also search for?
Think about the complete purchase journey and related topics.

Business: {business} · Industry: {industry}
Persona: {persona}

Return ONLY valid JSON array of supporting keyword strings (50 keywords):
["keyword1","keyword2",...]"""

    def __init__(self):
        self._last_gemini = 0.0

    def discover_personas(self, user_input: UserInput, product: str) -> List[dict]:
        """
        Core chain-of-thought persona discovery.
        Finds ALL buyer types including non-obvious ones.
        """
        prompt = self.PERSONA_CHAIN_PROMPT.format(
            product=product,
            business=f"{user_input.business_name} — {user_input.usp}",
            industry=user_input.industry.value,
            locations=", ".join(l.value for l in user_input.target_locations),
            religions=", ".join(r.value for r in user_input.target_religions),
            languages=", ".join(l.value for l in user_input.target_languages),
            usp=user_input.usp
        )
        log.info(f"[Audience] Discovering personas for: {product}")
        text = AI.gemini(prompt, temperature=0.5)
        try:
            result = AI.parse_json(text)
            chains = result.get("persona_chains", [])
            insight= result.get("key_insight","")
            log.info(f"[Audience] Found {len(chains)} personas. Insight: {insight[:80]}")
            return chains
        except Exception as e:
            log.warning(f"Persona chain parse failed: {e}")
            return self._fallback_personas(user_input, product)

    def get_native_language_keywords(self, persona: dict,
                                      language: Language) -> List[dict]:
        """Generate natural-language search queries in target language."""
        if language == Language.ENGLISH:
            return [{"english": q, "native": q, "notes": "primary language"}
                    for q in persona.get("search_queries",[])]

        prompt = self.SEARCH_LANGUAGE_PROMPT.format(
            persona_name=persona.get("persona_name",""),
            language=language.value,
            queries=json.dumps(persona.get("search_queries",[])[:10])
        )
        text = AI.gemini(prompt, temperature=0.3)
        try:
            return AI.parse_json(text)
        except Exception:
            return [{"english": q, "native": q, "notes": "translation pending"}
                    for q in persona.get("search_queries",[])]

    def get_supporting_keywords(self, main_keyword: str, persona: dict,
                                 user_input: UserInput) -> List[str]:
        """What else does this persona search for around the same purchase?"""
        prompt = self.SUPPORTING_KEYWORDS_PROMPT.format(
            main_keyword=main_keyword,
            business=user_input.business_name,
            industry=user_input.industry.value,
            persona=persona.get("persona_name","")
        )
        text = AI.gemini(prompt, temperature=0.4)
        try:
            result = AI.parse_json(text)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def _fallback_personas(self, user_input: UserInput, product: str) -> List[dict]:
        """Fallback when AI fails — returns seed personas from industry template."""
        template = INDUSTRY_TEMPLATES.get(user_input.industry, {})
        seeds    = template.get("persona_seeds", ["general buyers"])
        # Use industry keyword modifiers to build sensible fallback search queries.
        mods = template.get("keyword_modifiers", [])
        if not mods:
            mods = ["buy", "price", "uses"]

        def make_queries(p):
            # Return up to three modifier-augmented queries, plus the plain product.
            qs = [f"{p}"]
            for m in mods[:3]:
                qs.append(f"{p} {m}")
            return qs

        return [
            {"persona_name": s,
             "search_queries": make_queries(product),
             "language": "english", "religion": "general", "region": "india",
             "supporting_keywords": [], "purchase_intent": "medium",
             "who_exactly": s, "when_they_buy": "anytime",
             "why_they_buy": "need the product", "content_ideas": [f"{product} guide"],
             "seasonal_peak": "", "reach_channel": "Google"}
            for s in seeds
        ]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — CONTEXT ENGINE (Location × Religion × Language)
# ─────────────────────────────────────────────────────────────────────────────

class ContextEngine:
    """
    Multiplies context dimensions to generate unique keyword clusters.

    Christian × Malabar × Malayalam → Christmas plum cake spice mix Kerala
    Muslim × Malabar × English      → Malabar chicken masala halal recipe
    Hindu × Wayanad × Hindi         → Wayanad organic kali mirch Ayurvedic
    """

    CONTEXT_EXPAND_PROMPT = """Generate specific SEO keywords for this exact audience segment:

Product: {product}
Religion context: {religion}
Location context: {location}
Language: {language}
Persona: {persona}
Industry: {industry}
Business: {business}

Think about:
- What this specific community would search for around {product}
- Their specific cultural/religious occasions and needs
- Natural language they use (not translations — natural search behaviour)
- Seasonal and festival-specific keywords
- Regional variations and preferences

Return ONLY valid JSON array:
[
  {{
    "term": "exact keyword or phrase",
    "intent": "informational|transactional|commercial|navigational",
    "language": "english|malayalam|hindi|tamil",
    "occasion": "always|Christmas|Onam|Eid|Diwali|harvest|etc",
    "content_type": "blog|recipe|product|faq|guide",
    "kd_estimate": 1-100,
    "why_unique": "why this keyword is specific to this context"
  }}
]
Generate 30+ keywords. Be specific and cultural — not generic."""

    def generate_context_cluster(self, product: str, religion: Religion,
                                  location: GeoLevel, language: Language,
                                  persona: dict, user_input: UserInput) -> List[dict]:
        """
        Generate keywords for one specific context intersection.
        """
        log.info(f"[Context] {product} × {religion.value} × {location.value} × {language.value}")

        # First: template-based keywords (fast, no AI)
        template_kws = self._template_keywords(product, religion, location, user_input.industry)

        # Then: AI expansion (richer, more specific)
        prompt = self.CONTEXT_EXPAND_PROMPT.format(
            product=product,
            religion=religion.value,
            location=location.value,
            language=language.value,
            persona=persona.get("persona_name","general"),
            industry=user_input.industry.value,
            business=user_input.business_name
        )
        text = AI.gemini(prompt, temperature=0.5)
        try:
            ai_kws = AI.parse_json(text)
            if isinstance(ai_kws, list):
                return template_kws + ai_kws
        except Exception as e:
            log.warning(f"Context AI failed: {e}")
        return template_kws

    def _template_keywords(self, product: str, religion: Religion,
                            location: GeoLevel, industry: Industry) -> List[dict]:
        """Fast template-based context keywords."""
        template = INDUSTRY_TEMPLATES.get(industry, {})
        kws = []

        # Religion-based templates
        rel_templates = template.get("religion_content", {}).get(religion, [])
        for t in rel_templates:
            kw = t.format(product=product, location=location.value)
            kws.append({"term": kw, "intent": "informational", "language": "english",
                        "occasion": "religious", "content_type": "blog",
                        "kd_estimate": 5, "why_unique": f"{religion.value} context"})

        # Region-based templates
        reg_templates = template.get("region_content", {}).get(location, [])
        for t in reg_templates:
            kw = t.format(product=product)
            kws.append({"term": kw, "intent": "commercial", "language": "english",
                        "occasion": "always", "content_type": "product",
                        "kd_estimate": 7, "why_unique": f"{location.value} region"})

        return kws

    def get_seasonal_keywords(self, product: str, events: List[str],
                               user_input: UserInput) -> Dict[str, List[dict]]:
        """Generate seasonal keyword clusters for each festival/event."""
        template = INDUSTRY_TEMPLATES.get(user_input.industry, {})
        seasonal = template.get("seasonal_peaks", {})
        result   = {}

        for event in events:
            event_kws = seasonal.get(event, [])
            result[event] = []
            for kw_template in event_kws:
                result[event].append({
                    "term": f"{product} {kw_template}" if "{" not in kw_template else kw_template.format(product=product),
                    "intent": "commercial", "occasion": event,
                    "kd_estimate": 4, "content_type": "blog"
                })
            # AI expansion for this event
            prompt = f"""Generate 15 SEO keywords for selling {product} during {event}.
Business: {user_input.business_name} in {', '.join(l.value for l in user_input.target_locations)}.
Target: {', '.join(user_input.target_languages[0].value if user_input.target_languages else 'english')}.
Return ONLY a JSON array of keyword strings."""
            try:
                text = AI.gemini(prompt, temperature=0.5)
                ai_event = AI.parse_json(text)
                if isinstance(ai_event, list):
                    result[event].extend([{"term": k, "occasion": event,
                                            "kd_estimate": 5, "intent": "commercial"}
                                           for k in ai_event])
            except Exception:
                pass

        return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — WEBSITE & COMPETITOR INTELLIGENCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class BusinessIntelligenceEngine:
    """
    Engine 1: Crawls own website + competitors.
    Extracts: existing keywords, blog topics, product categories,
              ad copy patterns, content gaps.
    """
    from bs4 import BeautifulSoup

    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RufloBot/3.0)"}

    def crawl_business(self, url: str) -> dict:
        """Crawl own website — extract current keyword footprint."""
        from bs4 import BeautifulSoup
        log.info(f"[BI] Crawling own site: {url}")
        result = {
            "url": url, "pages": [], "existing_keywords": [],
            "blog_topics": [], "product_names": [], "meta_keywords": []
        }
        try:
            r    = _req.get(url, headers=self.HEADERS, timeout=12)
            soup = BeautifulSoup(r.text, "html.parser")

            # Product names from navigation / headings
            for h in soup.find_all(["h1","h2","h3"]):
                text = h.get_text(strip=True)
                if len(text) > 3:
                    result["product_names"].append(text)

            # Blog topics from links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(w in href for w in ["blog","post","article","news"]):
                    result["blog_topics"].append(a.get_text(strip=True))

            # Title and meta
            if soup.title:
                result["existing_keywords"].append(soup.title.string)
            meta_kw = soup.find("meta", {"name":"keywords"})
            if meta_kw and meta_kw.get("content"):
                result["meta_keywords"] = meta_kw["content"].split(",")

            result["pages"].append({"url": url, "title": soup.title.string if soup.title else ""})

        except Exception as e:
            log.warning(f"Own site crawl failed: {e}")
        return result

    def crawl_competitor(self, url: str) -> dict:
        """Crawl competitor — extract their keyword and content strategy."""
        from bs4 import BeautifulSoup
        log.info(f"[BI] Crawling competitor: {url}")
        result = {"url": url, "headings": [], "blog_topics": [],
                  "product_categories": [], "ad_keywords": []}
        try:
            r    = _req.get(url, headers=self.HEADERS, timeout=12)
            soup = BeautifulSoup(r.text, "html.parser")
            result["headings"]  = [h.get_text(strip=True) for h in soup.find_all(["h1","h2"])][:20]
            result["blog_topics"] = [a.get_text(strip=True) for a in soup.find_all("a", href=True)
                                     if "blog" in a.get("href","")][:15]
        except Exception as e:
            log.warning(f"Competitor crawl failed {url}: {e}")
        return result

    def extract_from_reviews(self, reviews: List[str]) -> List[str]:
        """Extract natural-language keywords from customer reviews."""
        if not reviews:
            return []
        combined = " ".join(reviews)
        prompt = f"""Extract the most important SEO keywords and phrases from these customer reviews.
Focus on: how customers describe the product, what they love, what problems it solved, what they compared it to.
These become natural-language long-tail keywords.
Return ONLY a JSON array of keyword strings (30 keywords):
Reviews: {combined[:2000]}"""
        try:
            text = AI.gemini(prompt, temperature=0.3)
            return AI.parse_json(text)
        except Exception:
            return []

    def extract_from_ad_copy(self, ad_copy: str) -> dict:
        """Extract winning angles from paid ad copy — mirror into organic."""
        if not ad_copy:
            return {}
        prompt = f"""Analyse this ad copy and extract:
1. Key value propositions (what's working in paid)
2. Emotional hooks
3. Keywords used
4. Content angles to mirror in organic SEO

Ad copy: {ad_copy[:1000]}

Return ONLY valid JSON:
{{"value_props": [...], "emotional_hooks": [...], "keywords": [...], "organic_angles": [...]}}"""
        try:
            text = AI.gemini(prompt, temperature=0.2)
            return AI.parse_json(text)
        except Exception:
            return {}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — STRATEGY SYNTHESIS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class StrategySynthesisEngine:
    """
    Collects all data from engines 1–4 and feeds to Claude for
    the final coherent strategy. Industry-aware output format.
    """

    STRATEGY_SYSTEM = """You are the world's best digital marketing strategist with deep expertise 
in content-led SEO for Indian businesses.

You understand:
- How Indian consumers search differently by religion, region, and language
- Festival and seasonal buying patterns in India
- How to rank for vernacular keywords (Malayalam, Hindi, Tamil)
- E-E-A-T requirements for different industries
- Information Gain theory — unique content beats repeated content
- The difference between a spice brand strategy and a hospital strategy

You produce strategies that are:
- Hyper-specific to the audience (not generic "create good content" advice)
- Culturally intelligent (festival timing, regional preferences, religious context)
- Sequenced for maximum velocity (easy wins first, hard keywords later)
- Multilingual (English + native language content plan)

Always respond in valid JSON only."""

    STRATEGY_PROMPT = """Create a complete 12-month content and keyword strategy for:

BUSINESS: {business_name} — {industry}
USP: {usp}
TYPE: {business_type}

PERSONAS FOUND ({persona_count} total — top 5 shown):
{personas_json}

CONTEXT CLUSTERS ({context_count} total — top examples):
{context_json}

SEASONAL OPPORTUNITIES:
{seasonal_json}

COMPETITOR GAPS:
{competitor_json}

REVIEW-BASED KEYWORDS:
{review_kws}

PILLARS INPUT:
{pillars_json}

SUPPORTING KEYWORDS:
{supporting_json}

INTENT FOCUS: {intent_focus}
CUSTOMER URL: {customer_url}

TARGET CONFIGURATION:
Locations: {locations}
Religions: {religions}
Languages: {languages}
Products: {products}

Now think step by step:

STEP 1: Which personas have the highest unmet need and lowest competition?
STEP 2: Which context intersections (religion × location) have NO content from competitors?
STEP 3: What is the exact content sequence for the first 90 days?
STEP 4: Which languages need their own content plan?
STEP 5: What is the seasonal content calendar?
STEP 6: What are the top 5 "information gain" articles — unique content no competitor has?

Return ONLY valid JSON:
{{
  "strategy_summary": {{
    "headline": "one-sentence strategy",
    "biggest_opportunity": "most underserved persona + context",
    "why_we_win": "our specific advantage vs competitors",
    "12_month_traffic_prediction": "realistic estimate"
  }},
  "priority_personas": [
    {{
      "persona": "name",
      "why_priority": "reason",
      "first_3_articles": ["title 1", "title 2", "title 3"],
      "language": "primary language",
      "channel": "Google|Instagram|YouTube"
    }}
  ],
  "universe_seeds": [
    {{
      "product": "product/topic name",
      "search_volume_category": "high|medium|low",
      "personas_served": ["persona 1", "persona 2"],
      "pillar_keyword": "main pillar keyword",
      "religion_clusters": {{"christian": [...], "muslim": [...], "hindu": [...]}},
      "language_clusters": {{"english": [...], "malayalam": [...], "hindi": [...]}},
      "seasonal_clusters": {{"event_name": [...]}}
    }}
  ],
  "90_day_plan": [
    {{
      "week": 1,
      "articles": [
        {{
          "title": "exact title",
          "keyword": "target keyword",
          "persona": "who this serves",
          "religion": "if specific",
          "language": "english|malayalam|etc",
          "why_week_1": "strategic reason",
          "content_type": "blog|recipe|guide|faq",
          "kd_estimate": 0,
          "info_gap": true
        }}
      ]
    }}
  ],
  "language_plan": {{
    "english": {{"article_count": 0, "priority_topics": [...]}},
    "malayalam": {{"article_count": 0, "priority_topics": [...]}},
    "hindi": {{"article_count": 0, "priority_topics": [...]}}
  }},
  "seasonal_calendar": [
    {{
      "event": "name",
      "publish_by": "weeks before event",
      "articles": ["article titles"],
      "keywords": ["seasonal keywords"]
    }}
  ],
  "top_5_information_gain": [
    {{
      "title": "article title",
      "keyword": "target keyword",
      "what_competitors_miss": "what no competitor has written",
      "unique_angle": "our specific advantage",
      "kd_estimate": 0,
      "est_traffic": 0
    }}
  ],
  "industry_specific": {{
    "schema_priority": ["schema types in order"],
    "content_guidelines": ["industry-specific rules"],
    "eeat_requirements": ["how to demonstrate expertise"]
  }}
}}"""

    def synthesize(self, user_input: UserInput, personas: List[dict],
                   context_clusters: List[dict], seasonal: dict,
                   competitor_data: List[dict], review_kws: List[str]) -> Tuple[dict, int]:
        """Feed all data to Claude for final strategy."""
        prompt = self.STRATEGY_PROMPT.format(
            business_name=user_input.business_name,
            industry=user_input.industry.value,
            usp=user_input.usp,
            business_type=user_input.business_type,
            persona_count=len(personas),
            personas_json=json.dumps(personas[:5], indent=2)[:2000],
            context_count=len(context_clusters),
            context_json=json.dumps(context_clusters[:10], indent=2)[:1500],
            seasonal_json=json.dumps(seasonal, indent=2)[:800],
            competitor_json=json.dumps([{"url":c["url"],"headings":c.get("headings",[])[:5]}
                                         for c in competitor_data[:3]])[:800],
            review_kws=json.dumps(review_kws[:20]),
            pillars_json=json.dumps(getattr(user_input, 'pillars', [])[:10], indent=2),
            supporting_json=json.dumps(getattr(user_input, 'supporting_keywords', [])[:20], indent=2),
            intent_focus=getattr(user_input, 'intent_focus', 'transactional'),
            customer_url=getattr(user_input, 'customer_url', ''),
            locations=", ".join(l.value for l in user_input.target_locations),
            religions=", ".join(r.value for r in user_input.target_religions),
            languages=", ".join(l.value for l in user_input.target_languages),
            products=", ".join(user_input.products)
        )
        # Prefer Groq for final strategy, with Gemini/DeepSeek fallback.
        text = AI.groq(prompt, temperature=0.25)
        if not text or text.lower().strip().startswith('{"error"'):
            text = AI.gemini(prompt, temperature=0.3)
        if not text:
            text = AI.deepseek(prompt, temperature=0.2)
        try:
            parsed = AI.parse_json(text)
            if isinstance(parsed, dict):
                return parsed, 0
            return {"strategy": parsed}, 0
        except Exception:
            return {"error": "parse_failed", "raw": text[:1000]}, 0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class StrategyDevelopmentEngine:
    """
    Main orchestrator. Takes UserInput → runs all engines → returns complete strategy.

    6-engine pipeline:
      1. Business Intelligence  → crawl website + competitors
      2. Audience Intelligence  → persona chain discovery
      3. Context Engine         → location × religion × language clusters
      4. Seasonal Engine        → festival and event keyword clusters
      5. Keyword Engine         → scores, dedup, supporting keywords
      6. Strategy Synthesis     → Claude final strategy
    """

    def __init__(self):
        self.bi      = BusinessIntelligenceEngine()
        self.audience= AudienceIntelligenceEngine()
        self.context = ContextEngine()
        self.synth   = StrategySynthesisEngine()

    def run(self, user_input: UserInput) -> dict:
        """Full pipeline. Returns complete strategy dict."""
        t0 = time.time()
        log.info(f"[Strategy] Starting for: {user_input.business_name}")
        steps_log = []

        # ── Engine 1: Business Intelligence ─────────────────────────────────
        t = time.time()
        own_site = self.bi.crawl_business(user_input.website_url)
        competitors = [self.bi.crawl_competitor(u) for u in user_input.competitor_urls[:3]]
        review_kws  = self.bi.extract_from_reviews(user_input.customer_reviews)
        ad_intel    = self.bi.extract_from_ad_copy(user_input.ad_copy)
        steps_log.append({"step":"business_intelligence","ms":int((time.time()-t)*1000),
                           "own_pages":len(own_site.get("pages",[])),
                           "competitors":len(competitors),"review_kws":len(review_kws)})

        # ── Engine 2: Audience Intelligence ──────────────────────────────────
        t = time.time()
        all_personas = []
        for product in user_input.products[:5]:  # top 5 products
            personas = self.audience.discover_personas(user_input, product)
            all_personas.extend(personas)
        # Deduplicate persona names
        seen_p, unique_personas = set(), []
        for p in all_personas:
            name = p.get("persona_name","")
            if name not in seen_p:
                seen_p.add(name)
                unique_personas.append(p)
        steps_log.append({"step":"audience_intelligence","ms":int((time.time()-t)*1000),
                           "personas_found":len(unique_personas)})
        log.info(f"[Strategy] {len(unique_personas)} unique personas discovered")

        # ── Engine 3: Context Engine ──────────────────────────────────────────
        t = time.time()
        all_context_clusters = []
        # Generate for each relevant intersection (limit combinations)
        for product in user_input.products[:3]:
            for religion in user_input.target_religions[:3]:
                for location in user_input.target_locations[:3]:
                    lang = user_input.target_languages[0] if user_input.target_languages else Language.ENGLISH
                    persona = unique_personas[0] if unique_personas else {}
                    cluster = self.context.generate_context_cluster(
                        product, religion, location, lang, persona, user_input
                    )
                    all_context_clusters.extend(cluster)
                    time.sleep(0.5)  # rate limit Gemini
        steps_log.append({"step":"context_engine","ms":int((time.time()-t)*1000),
                           "context_keywords":len(all_context_clusters)})

        # ── Engine 4: Seasonal Keywords ───────────────────────────────────────
        t = time.time()
        seasonal_events = user_input.seasonal_events or []
        # Auto-detect seasonal events from religion selection
        if Religion.CHRISTIAN in user_input.target_religions:
            seasonal_events.extend(["Christmas","Easter","Good Friday"])
        if Religion.MUSLIM in user_input.target_religions:
            seasonal_events.extend(["Eid","Ramadan"])
        if Religion.HINDU in user_input.target_religions:
            seasonal_events.extend(["Onam","Diwali","Vishu"])
        seasonal_events = list(set(seasonal_events))

        seasonal_kws = {}
        for product in user_input.products[:2]:
            seasonal_kws[product] = self.context.get_seasonal_keywords(
                product, seasonal_events[:5], user_input
            )
        steps_log.append({"step":"seasonal_engine","ms":int((time.time()-t)*1000),
                           "events":len(seasonal_events)})

        # ── Engine 5: Supporting Keywords (per persona) ───────────────────────
        t = time.time()
        supporting_all = []
        for persona in unique_personas[:5]:
            for query in persona.get("search_queries",[])[:3]:
                supp = self.audience.get_supporting_keywords(query, persona, user_input)
                supporting_all.extend(supp)
        steps_log.append({"step":"supporting_keywords","ms":int((time.time()-t)*1000),
                           "supporting":len(supporting_all)})

        # ── Engine 6: Claude Strategy Synthesis ───────────────────────────────
        t = time.time()
        log.info("[Strategy] Synthesizing with Claude...")
        strategy_text, tokens = self.synth.synthesize(
            user_input, unique_personas, all_context_clusters,
            seasonal_kws, competitors, review_kws + ad_intel.get("keywords",[])
        )
        try:
            strategy = AI.parse_json(strategy_text)
        except Exception as e:
            log.warning(f"Strategy parse failed: {e}")
            # `strategy_text` may be a dict (already parsed) or other type — guard slicing
            try:
                raw_preview = strategy_text[:500] if isinstance(strategy_text, (str, bytes)) else json.dumps(strategy_text)[:500]
            except Exception:
                raw_preview = str(strategy_text)[:500]
            strategy = {"error": "parse_failed", "raw": raw_preview}
        steps_log.append({"step":"claude_synthesis","ms":int((time.time()-t)*1000),
                           "tokens":tokens})

        total_ms = int((time.time()-t0)*1000)
        log.info(f"[Strategy] Complete. {total_ms}ms, {tokens} tokens used.")

        return {
            "business":           user_input.business_name,
            "industry":           user_input.industry.value,
            "status":             "completed",
            "strategy":           strategy,
            "personas":           unique_personas,
            "context_clusters":   all_context_clusters[:50],
            "seasonal_keywords":  seasonal_kws,
            "supporting_keywords":supporting_all[:100],
            "review_keywords":    review_kws,
            "ad_intelligence":    ad_intel,
            "steps_log":          steps_log,
            "total_ms":           total_ms,
            "claude_tokens":      tokens,
            "generated_at":       datetime.now(timezone.utc).isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — TESTS
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    Run:
      python ruflo_strategy_dev_engine.py test audience   # persona chain
      python ruflo_strategy_dev_engine.py test context    # context clusters
      python ruflo_strategy_dev_engine.py test seasonal   # seasonal keywords
      python ruflo_strategy_dev_engine.py test pureleven  # full spice brand
      python ruflo_strategy_dev_engine.py test hospital   # healthcare example
    """

    PURELEVEN = UserInput(
        business_name="Pureleven Organics",
        website_url="https://example.com",
        industry=Industry.FOOD_SPICES,
        business_type="D2C",
        usp="single-origin organic spices from Wayanad Kerala, no preservatives, farm-direct delivery",
        products=["Black Pepper","Cardamom","Cinnamon","Clove","Masala Mix"],
        competitor_urls=["https://en.wikipedia.org/wiki/Black_pepper"],
        target_locations=[GeoLevel.KERALA, GeoLevel.MALABAR, GeoLevel.NATIONAL],
        target_religions=[Religion.HINDU, Religion.MUSLIM, Religion.CHRISTIAN],
        target_languages=[Language.ENGLISH, Language.MALAYALAM, Language.HINDI],
        audience_personas=["Home cooks","Restaurant owners","Ayurveda practitioners"],
        customer_reviews=[
            "Best organic pepper I've used. No artificial smell, pure Wayanad quality.",
            "Ordered for Christmas cake, the cinnamon was perfect. Will order again.",
            "Excellent for biryani. My husband said this is the best masala.",
        ],
        seasonal_events=["Christmas","Onam","Eid","Diwali"],
        ad_copy="Pure. Organic. Straight from Wayanad farms to your kitchen. No middlemen.",
    )

    HOSPITAL = UserInput(
        business_name="Kerala Care Hospital",
        website_url="https://example-hospital.com",
        industry=Industry.HEALTHCARE,
        business_type="B2C",
        usp="NABH-accredited multi-speciality hospital, 24/7 emergency, Ayurvedic integrative care",
        products=["Orthopaedics","Cardiology","Oncology","Gynaecology","Ayurvedic Integration"],
        competitor_urls=[],
        target_locations=[GeoLevel.KERALA, GeoLevel.NATIONAL],
        target_religions=[Religion.ALL],
        target_languages=[Language.ENGLISH, Language.MALAYALAM, Language.ARABIC],
        audience_personas=["Patients","Family caregivers","Medical tourists","NRI patients"],
        customer_reviews=[],
        seasonal_events=[],
    )

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_audience(self):
        self._h("Audience Intelligence Engine — Black Pepper personas")
        engine = AudienceIntelligenceEngine()
        personas = engine.discover_personas(self.PURELEVEN, "Black Pepper")
        self._ok(f"Personas discovered: {len(personas)}")
        for p in personas[:4]:
            self._ok(f"  [{p.get('religion','?')} | {p.get('region','?')}] {p.get('persona_name','')}")
            self._ok(f"    Searches: {p.get('search_queries',['?'])[:2]}")
            self._ok(f"    Seasonal: {p.get('seasonal_peak','always')}")

    def test_context(self):
        self._h("Context Engine — Christian × Malabar × Malayalam")
        engine  = ContextEngine()
        persona = {"persona_name":"Kerala Christian Christmas Baker","search_queries":[
            "Christmas cake cinnamon powder Kerala",
            "Kerala plum cake spice list",
        ]}
        cluster = engine.generate_context_cluster(
            "Cinnamon", Religion.CHRISTIAN, GeoLevel.MALABAR,
            Language.MALAYALAM, persona, self.PURELEVEN
        )
        self._ok(f"Context keywords: {len(cluster)}")
        for k in cluster[:5]:
            self._ok(f"  [{k.get('occasion','?')}] {k.get('term','')} — {k.get('why_unique','')[:40]}")

    def test_seasonal(self):
        self._h("Seasonal Keywords — Christmas + Onam")
        engine  = ContextEngine()
        seasonal= engine.get_seasonal_keywords("Cinnamon", ["Christmas","Onam"], self.PURELEVEN)
        for event, kws in seasonal.items():
            self._ok(f"{event}: {len(kws)} keywords")
            for k in kws[:3]:
                self._ok(f"  {k.get('term','') if isinstance(k,dict) else k}")

    def test_pureleven(self):
        self._h("FULL STRATEGY — Pureleven Spices")
        engine = StrategyDevelopmentEngine()
        result = engine.run(self.PURELEVEN)

        strategy = result.get("strategy", {})
        self._ok(f"Status: {result['status']}")
        self._ok(f"Total duration: {result['total_ms']}ms")
        self._ok(f"Personas: {len(result['personas'])}")
        self._ok(f"Context clusters: {len(result['context_clusters'])}")
        self._ok(f"Supporting keywords: {len(result['supporting_keywords'])}")
        self._ok(f"Claude tokens: {result['claude_tokens']}")

        if strategy.get("strategy_summary"):
            s = strategy["strategy_summary"]
            self._ok(f"\nStrategy headline: {s.get('headline','?')}")
            self._ok(f"Biggest opportunity: {s.get('biggest_opportunity','?')}")
            self._ok(f"12-month prediction: {s.get('12_month_traffic_prediction','?')}")

        if strategy.get("top_5_information_gain"):
            self._ok("\nTop 5 info gaps:")
            for g in strategy["top_5_information_gain"][:3]:
                self._ok(f"  • {g.get('title','')} (KD {g.get('kd_estimate',0)})")

        if strategy.get("seasonal_calendar"):
            self._ok("\nSeasonal calendar:")
            for s in strategy["seasonal_calendar"][:3]:
                self._ok(f"  {s.get('event','?')}: {s.get('articles',['?'])[0] if s.get('articles') else '?'}")

        return result

    def test_hospital(self):
        self._h("FULL STRATEGY — Hospital (different industry)")
        engine = StrategyDevelopmentEngine()
        result = engine.run(self.HOSPITAL)
        strategy = result.get("strategy", {})
        self._ok(f"Personas: {len(result['personas'])}")
        for p in result['personas'][:3]:
            self._ok(f"  {p.get('persona_name','')} → {p.get('search_queries',['?'])[:1]}")
        if strategy.get("industry_specific"):
            ind = strategy["industry_specific"]
            self._ok(f"Schema priority: {ind.get('schema_priority',['?'])[:3]}")
            self._ok(f"E-E-A-T requirements: {ind.get('eeat_requirements',['?'])[:2]}")

    def run_all(self):
        tests = [
            ("audience", self.test_audience),
            ("context",  self.test_context),
            ("seasonal", self.test_seasonal),
        ]
        print("\n"+"═"*55)
        print("  STRATEGY DEVELOPMENT ENGINE — TESTS")
        print("═"*55)
        p = f = 0
        for name, fn in tests:
            try: fn(); p+=1
            except Exception as e: print(f"  ✗ {name}: {e}"); f+=1
        print(f"\n  {p} passed / {f} failed\n"+"═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — FASTAPI
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from pydantic import BaseModel as PM

    app = FastAPI(title="Ruflo Strategy Dev Engine", version="1.0.0",
                  description="Audience-intelligent, context-aware strategy generation")

    sde   = StrategyDevelopmentEngine()
    _jobs = {}

    class StrategyReq(PM):
        business_name:    str
        website_url:      str
        industry:         str = "food_spices"
        business_type:    str = "D2C"
        usp:              str = ""
        products:         list = []
        competitor_urls:  list = []
        target_locations: list = ["kerala","india"]
        target_religions: list = ["general"]
        target_languages: list = ["english","malayalam"]
        audience_personas:list = []
        customer_reviews: list = []
        ad_copy:          str = ""
        seasonal_events:  list = []

    @app.post("/api/strategy/develop", tags=["Strategy"])
    def develop_strategy(req: StrategyReq, bg: BackgroundTasks):
        """Run full strategy development pipeline."""
        job_id = __import__('uuid').uuid4().hex
        _jobs[job_id] = {"status":"running"}
        def _run():
            try:
                ui = UserInput(
                    business_name=req.business_name, website_url=req.website_url,
                    industry=Industry(req.industry), business_type=req.business_type,
                    usp=req.usp, products=req.products, competitor_urls=req.competitor_urls,
                    target_locations=[GeoLevel(l) for l in req.target_locations if l in GeoLevel._value2member_map_],
                    target_religions=[Religion(r) for r in req.target_religions if r in Religion._value2member_map_],
                    target_languages=[Language(l) for l in req.target_languages if l in Language._value2member_map_],
                    audience_personas=req.audience_personas,
                    customer_reviews=req.customer_reviews,
                    ad_copy=req.ad_copy, seasonal_events=req.seasonal_events
                )
                result = sde.run(ui)
                _jobs[job_id] = {"status":"done","data":result}
            except Exception as e:
                _jobs[job_id] = {"status":"failed","error":str(e)}
        bg.add_task(_run)
        return {"job_id":job_id,"message":"Strategy development started"}

    @app.get("/api/jobs/{job_id}", tags=["Jobs"])
    def get_job(job_id:str):
        if job_id not in _jobs: raise HTTPException(404,"Not found")
        return _jobs[job_id]

    @app.get("/api/industries", tags=["Config"])
    def list_industries():
        return {"industries":[i.value for i in Industry]}

    @app.get("/api/config/options", tags=["Config"])
    def get_options():
        return {
            "industries":  [i.value for i in Industry],
            "religions":   [r.value for r in Religion],
            "languages":   [l.value for l in Language],
            "geo_levels":  [g.value for g in GeoLevel],
        }

except ImportError: pass


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    HELP = """
Ruflo — Strategy Development Engine
────────────────────────────────────────────────────────
Audience-intelligent, context-aware (location×religion×language) strategy.

Usage:
  python ruflo_strategy_dev_engine.py test               # all unit tests
  python ruflo_strategy_dev_engine.py test <stage>       # one test
  python ruflo_strategy_dev_engine.py pureleven          # full spice brand demo
  python ruflo_strategy_dev_engine.py hospital           # healthcare demo
  python ruflo_strategy_dev_engine.py api                # FastAPI server

Stages: audience, context, seasonal
"""
    if len(sys.argv) < 2: print(HELP); exit(0)
    cmd = sys.argv[1]
    if cmd == "test":
        t = Tests()
        if len(sys.argv) == 3:
            fn = getattr(t, f"test_{sys.argv[2]}", None)
            if fn: fn()
            else:  print(f"Unknown: {sys.argv[2]}")
        else: t.run_all()
    elif cmd == "pureleven": Tests().test_pureleven()
    elif cmd == "hospital":  Tests().test_hospital()
    elif cmd == "api":
        try:
            import uvicorn
            print("Strategy Dev Engine API — http://localhost:8002")
            uvicorn.run("ruflo_strategy_dev_engine:app",
                        host="0.0.0.0", port=8002, reload=True)
        except ImportError: print("pip install uvicorn")
    else: print(f"Unknown: {cmd}\n{HELP}")

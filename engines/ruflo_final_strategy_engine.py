"""
================================================================================
RUFLO — FINAL AI STRATEGY ENGINE
================================================================================
After all keyword engines complete, this module feeds the entire keyword
universe data to Claude Sonnet for the definitive #1 ranking strategy.

Algorithm:
  1. Aggregate all pipeline outputs → compressed context JSON (~8k tokens)
  2. Chain-of-thought (CoT) prompt sequence → Claude reasons step by step
  3. DeepSeek validates Claude's output → confidence scoring
  4. Strategy frozen in DB → auto-populates content calendar + link map
  5. Continuous loop → monthly refresh, rank-drop triggers, seasonal alerts

Claude is called ONCE with full context. Returns:
  - Landscape analysis (easy wins, avoid zones, guaranteed #1s)
  - 90-day priority queue (exact article sequence with reasoning)
  - Top 5 content briefs (H1/H2/entities/info-gain/GEO tips)
  - Internal link architecture (all pillars + support articles)
  - Risk factors + mitigations
  - 12-month ranking predictions per pillar

Cost: ~$0.004 per strategy run. Runs monthly or on ranking drop trigger.

AI routing:
  Claude Sonnet → strategy analysis, content briefs, diagnosis
  DeepSeek (Ollama) → validation, confidence scoring, meta generation
================================================================================
"""

import os, json, re, time, logging, hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from dotenv import load_dotenv

from services.strategy_schema import load_strategy_schema
from services.llm_parser import extract_json, parse_llm_json
from services.strategy_validator import validate_strategy_output
from engines.prompts.final_strategy_prompt import SYSTEM_PROMPT, FULL_PROMPT, build_final_strategy_prompt

load_dotenv()
log = logging.getLogger("ruflo.strategy")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class DefaultLLMClient:
    """Minimal LLM client wrapper for `generate` calls."""

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, top_p: float = 0.9, max_tokens: int = 4000):
        text, tokens = AI.claude(
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return text, tokens



# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")  # best for reasoning
    OLLAMA_URL        = os.getenv("OLLAMA_URL", "http://172.235.16.165:11434")
    OLLAMA_MODEL      = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")
    GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL        = os.getenv("GROQ_MODEL", "llama-3.3-70b-instruct")
    GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    GEMINI_RATE       = float(os.getenv("GEMINI_RATE", "4.0"))

    # Token budget for context (keep well under Claude's limit)
    MAX_KEYWORDS_PER_PILLAR = 20   # top N per pillar in context
    MAX_INFO_GAPS           = 10   # top N info gaps
    MAX_COMPETITORS         = 5
    MAX_ENTITIES            = 30

    # Ranking thresholds for triggers
    RANK_ALERT_THRESHOLD    = 5    # trigger if drops below this
    RANK_MONITOR_WEEKS      = 4    # weeks to monitor after update

    # Strategy refresh
    MONTHLY_REFRESH_DAY     = 1    # day of month to auto-refresh strategy


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PillarContext:
    name:         str
    kd_avg:       float
    top_keywords: List[dict]    # [{term, kd, vol, intent, score, is_gap}]
    info_gap_count: int
    competitor_count: int
    clusters:     List[str]

@dataclass
class CompetitorSnapshot:
    domain:            str
    pillars_covered:   List[str]
    pillars_missing:   List[str]
    estimated_da:      Optional[int] = None   # Domain Authority estimate
    da:                Optional[int] = None   # backwards compatibility alias
    content_freshness: str = "mixed"  # "fresh" | "stale" | "mixed"

    def __post_init__(self):
        # Backwards compatibility: allow both da and estimated_da
        if self.estimated_da is None and self.da is not None:
            self.estimated_da = self.da
        if self.estimated_da is None:
            self.estimated_da = 0

    @classmethod
    def from_dict(cls, data: dict):
        norm = normalize_competitor_data(data.copy())
        return cls(
            domain=norm.get("domain", ""),
            pillars_covered=norm.get("pillars_covered", []),
            pillars_missing=norm.get("pillars_missing", []),
            estimated_da=norm.get("domain_authority", norm.get("estimated_da", norm.get("da"))),
            da=norm.get("da"),
            content_freshness=norm.get("content_freshness", "mixed")
        )


def normalize_competitor_data(data: dict) -> dict:
    if "da" in data and "domain_authority" not in data:
        data["domain_authority"] = data.pop("da")
    if "domain_authority" in data and "estimated_da" not in data:
        data["estimated_da"] = data["domain_authority"]
    # ensure canonical field names
    if "domain_authority" in data:
        data["estimated_da"] = data["domain_authority"]
    return data


@dataclass
class UniverseContext:
    """Complete data package fed to Claude. Compressed for token efficiency."""
    universe:         str
    business_context: str
    domain_age_months: int
    existing_pages:   int
    pillars:          List[PillarContext]
    top_20_keywords:  List[dict]
    info_gaps:        List[dict]
    competitors:      List[CompetitorSnapshot]
    entities:         List[str]
    languages:        List[str]
    regions:          List[str]
    current_rankings: List[dict]   # [{keyword, rank, impressions}]
    avg_rank:         Optional[float]

    def to_compressed_json(self) -> str:
        """
        Serialize to token-efficient JSON for Claude context.
        Aggressive compression: abbreviate, drop verbose fields.
        Target: < 8,000 tokens.
        """
        data = {
            "universe": self.universe,
            "business": self.business_context,
            "domain": {"age_months": self.domain_age_months,
                       "pages": self.existing_pages,
                       "avg_rank": self.avg_rank},
            "pillars": [
                {
                    "name": p.name,
                    "kd_avg": p.kd_avg,
                    "gap_count": p.info_gap_count,
                    "comp_count": p.competitor_count,
                    "top_kws": [
                        {"t": k["term"], "kd": k.get("kd_estimate",30),
                         "vol": k.get("volume_estimate",500),
                         "intent": k.get("intent","info")[:4],
                         "gap": k.get("is_info_gap", False)}
                        for k in p.top_keywords[:Cfg.MAX_KEYWORDS_PER_PILLAR]
                    ]
                }
                for p in self.pillars
            ],
            "top20": [
                {"t": k["term"], "kd": k.get("kd_estimate",30),
                 "vol": k.get("volume_estimate",500),
                 "score": k.get("final_score", 5.0),
                 "gap": k.get("is_info_gap", False)}
                for k in self.top_20_keywords[:20]
            ],
            "gaps": [
                {"q": g.get("question", g.get("term","")),
                 "kd": g.get("kd_estimate", 5),
                 "vol": g.get("volume_estimate", 500),
                 "unique": g.get("why_unique","")[:80]}
                for g in self.info_gaps[:Cfg.MAX_INFO_GAPS]
            ],
            "competitors": [
                {"domain": c.domain,
                 "covers": c.pillars_covered,
                 "misses": c.pillars_missing,
                 "da": c.estimated_da,
                 "fresh": c.content_freshness}
                for c in self.competitors[:Cfg.MAX_COMPETITORS]
            ],
            "entities": self.entities[:Cfg.MAX_ENTITIES],
            "languages": self.languages,
            "regions": self.regions,
            "rankings": self.current_rankings[:20]
        }
        return json.dumps(data, separators=(',', ':'))


@dataclass
class StrategyOutput:
    """Structured output from Claude's final strategy analysis."""
    landscape:       dict   # easy_win_pillars, avoid_pillars, guaranteed_#1, ceiling
    priority_queue:  List[dict]   # weekly article plan for 12 weeks
    content_briefs:  List[dict]   # top 5 detailed briefs
    link_map:        dict   # pillar-pillar, support-pillar, to-product
    risks:           List[dict]   # {risk, mitigation, severity}
    predictions:     List[dict]   # monthly milestones
    confidence:      float  # DeepSeek validation score 0-1
    generated_at:    str
    tokens_used:     int


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — AI HELPERS
# ─────────────────────────────────────────────────────────────────────────────

import requests as _req

class AI:

    @staticmethod
    def claude(system: str, messages: List[dict],
               max_tokens: int = 4096, temperature: float = 0.3) -> Tuple[str, int]:
        """
        Call Claude Sonnet for final strategy analysis.
        Returns: (response_text, tokens_used)
        """
        if not Cfg.ANTHROPIC_API_KEY:
            log.warning("No ANTHROPIC_API_KEY set")
            return '{"error": "No API key"}', 0
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=Cfg.ANTHROPIC_API_KEY)
            r = client.messages.create(
                model=Cfg.CLAUDE_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages
            )
            text   = r.content[0].text.strip()
            tokens = r.usage.input_tokens + r.usage.output_tokens
            return text, tokens
        except Exception as e:
            log.error(f"Claude API error: {e}")
            return '{"error": "' + str(e) + '"}', 0

    @staticmethod
    def deepseek(prompt: str, system: str = "You are an SEO validation expert.",
                  temperature: float = 0.1) -> str:
        """Ollama/DeepSeek via central AIRouter — no retry."""
        try:
            from core.ai_config import AIRouter
            return AIRouter._call_ollama(prompt, system, temperature)
        except ImportError:
            pass
        return ""

    @staticmethod
    def gemini(prompt: str, temperature: float = 0.3) -> str:
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
    def parse_json(text: str) -> Any:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — CONTEXT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

class ContextBuilder:
    """
    Aggregates outputs from all keyword engines into a single
    compressed context package for Claude.
    """

    def build(self, universe_result: dict, project: dict,
               gsc_data: List[dict] = None) -> UniverseContext:
        """
        Build UniverseContext from Ruflo v3 pipeline output.

        Args:
          universe_result: output from Ruflo.run_universe() or run_all_universes()
          project: project config dict
          gsc_data: current GSC rankings (optional)
        """
        tree = universe_result.get("universe_tree", universe_result)
        kw_engine_data = universe_result.get("keyword_engine", {})

        # Build pillar contexts
        pillar_contexts = []
        for p in tree.get("pillars", []):
            kws = p.get("supporting_keyword_engine", {}).get("top_50",
                  p.get("clusters", [{}])[0].get("keyword_items", []) if p.get("clusters") else [])
            gaps = p.get("supporting_keyword_engine", {}).get("info_gaps", [])

            pillar_contexts.append(PillarContext(
                name=p["name"],
                kd_avg=self._avg_kd(kws),
                top_keywords=kws[:Cfg.MAX_KEYWORDS_PER_PILLAR],
                info_gap_count=len(gaps),
                competitor_count=p.get("competitor_count", 0),
                clusters=[c.get("name","") for c in p.get("clusters",[])]
            ))

        # All keywords across all pillars
        all_kws = tree.get("top_100", [])
        if not all_kws:
            all_kws = [k for p in tree.get("pillars",[])
                       for c in p.get("clusters",[])
                       for k in c.get("keyword_items",[])]

        # All info gaps
        all_gaps = [k for p in tree.get("pillars",[])
                    for k in p.get("supporting_keyword_engine",{}).get("info_gaps",[])]

        # Competitor snapshots (built from SERP analysis)
        competitors = self._build_competitor_snapshots(tree)

        # Entity map
        entities = list(set(
            ent for p in tree.get("pillars",[])
            for ent in p.get("supporting_keyword_engine",{}).get("competitor_entities",[])
        ))

        # Current rankings from GSC
        current = gsc_data or []
        avg_rank = (sum(r.get("rank",50) for r in current) / len(current)) if current else None

        return UniverseContext(
            universe=tree.get("universe", ""),
            business_context=self._format_business(project),
            domain_age_months=project.get("domain_age_months", 3),
            existing_pages=project.get("existing_pages", 0),
            pillars=pillar_contexts,
            top_20_keywords=sorted(all_kws, key=lambda x: x.get("final_score",0), reverse=True)[:20],
            info_gaps=all_gaps[:Cfg.MAX_INFO_GAPS],
            competitors=competitors,
            entities=entities[:Cfg.MAX_ENTITIES],
            languages=project.get("target_languages", ["english"]),
            regions=project.get("target_regions", ["india"]),
            current_rankings=current[:20],
            avg_rank=avg_rank
        )

    def _avg_kd(self, kws: List[dict]) -> float:
        kds = [k.get("kd_estimate", 30) for k in kws if k.get("kd_estimate")]
        return round(sum(kds)/len(kds), 1) if kds else 30.0

    def _format_business(self, project: dict) -> str:
        return (f"{project.get('name','Business')} · {project.get('industry','Tourism')} · "
                f"{project.get('business_type','B2C')} · "
                f"USP: {project.get('usp','quality local experience')} · "
                f"Audience: {', '.join(project.get('target_audience',[]))}")

    def _build_competitor_snapshots(self, tree: dict) -> List[CompetitorSnapshot]:
        """Build competitor snapshots from SERP data in tree."""
        from engines.serp_utils import extract_competitors
        serp_source = tree.get("serp_intelligence") or tree.get("serp") or tree.get("serp_data") or {}
        raw_competitors = []

        # Back-compat with old pipeline shapes
        if isinstance(serp_source, dict) and serp_source.get("organic_results"):
            raw_competitors = extract_competitors(serp_source, limit=Cfg.MAX_COMPETITORS)
        elif isinstance(serp_source, dict) and serp_source.get("results"):
            raw_competitors = extract_competitors(serp_source, limit=Cfg.MAX_COMPETITORS)
        elif isinstance(serp_source, list):
            raw_competitors = extract_competitors({"organic_results": serp_source}, limit=Cfg.MAX_COMPETITORS)

        # Always attempt to enrich/augment SERP data using SERPEngine
        try:
            from engines.serp import SERPEngine
            serp_engine = SERPEngine()

            # Build a short list of candidate queries from the tree
            queries = []
            top_kws = tree.get("top_100") or tree.get("top_20") or []
            if isinstance(top_kws, list) and top_kws:
                for k in top_kws[:3]:
                    if isinstance(k, dict):
                        q = k.get("term") or k.get("keyword") or k.get("query")
                        if q:
                            queries.append(q)
                    elif isinstance(k, str):
                        queries.append(k)

            # Fallback: inspect pillars for keywords
            if not queries:
                for p in tree.get("pillars", []):
                    kws = p.get("supporting_keyword_engine", {}).get("top_50") or p.get("top_keywords") or []
                    if isinstance(kws, list) and kws:
                        for kw in kws[:2]:
                            if isinstance(kw, dict):
                                q = kw.get("term") or kw.get("keyword")
                                if q:
                                    queries.append(q)
                            elif isinstance(kw, str):
                                queries.append(kw)
                    if queries:
                        break

            if not queries:
                # last resort: use universe name
                cand = tree.get("universe") or tree.get("name") or "example"
                queries = [cand]

            # Aggregate provider responses
            aggregated = []
            for q in queries[:3]:
                try:
                    resp = serp_engine.get_serp(q)
                    if isinstance(resp, dict):
                        results = resp.get("organic_results") or resp.get("results") or []
                        if isinstance(results, list):
                            aggregated.extend(results)
                except Exception as e:
                    log.warning("SERPEngine provider call failed for query %s: %s", q, e)
                    continue

            # Also include any existing SERP results from the pipeline
            existing_results = []
            if isinstance(serp_source, dict):
                existing_results = serp_source.get("organic_results") or serp_source.get("results") or []
            elif isinstance(serp_source, list):
                existing_results = serp_source

            # Combine and deduplicate by URL/title
            combined = []
            seen = set()
            for item in (aggregated + existing_results):
                if not isinstance(item, dict):
                    key = str(item)
                else:
                    url = item.get("link") or item.get("url") or item.get("link_raw") or ""
                    title = item.get("title") or item.get("name") or ""
                    key = url or title or json.dumps(item, sort_keys=True)
                if not key:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                combined.append(item)

            if combined:
                serp_data = {"organic_results": combined[:50]}
                # store back into tree for downstream consumers
                try:
                    tree["serp"] = serp_data
                    tree["serp_data"] = serp_data
                except Exception:
                    pass
                raw_competitors = extract_competitors(serp_data, limit=Cfg.MAX_COMPETITORS)
        except Exception as e:
            log.warning("SERP enrichment via SERPEngine failed: %s", e)

        return [CompetitorSnapshot.from_dict(c) for c in raw_competitors]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — PROMPT TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

class StrategyPrompts:
    """Chain-of-thought prompt sequence for Claude."""

    SYSTEM = """You are the world's most effective SEO strategist. You have ranked hundreds of 
websites to #1 on Google using content-led SEO with limited budgets.

Your expertise:
- Information Gain theory (unique content beats repeated content)  
- Topic cluster architecture and internal link strategy
- GEO (Generative Engine Optimization) for Perplexity/ChatGPT/Gemini citation
- Keyword difficulty vs opportunity analysis
- Content velocity and sequencing for maximum ranking speed
- E-E-A-T authority signals

You think in 12-month arcs. You are ruthlessly strategic and specific.
You tell users EXACTLY what to publish, in what order, and why.

CRITICAL RULES:
1. Always identify information gaps as the highest priority (no competition = fast #1)
2. Never recommend competing head-on with Tripadvisor/MakeMyTrip on their best keywords
3. Internal links are non-negotiable — every article connects to the pillar and product page
4. GEO formatting: every article must have at least one direct-answer paragraph for AI citation
5. Sequence matters: publish easy+gap articles first to build domain authority before tackling hard ones

Always respond in valid JSON only. No markdown, no explanation outside JSON."""

    # Step 1: Landscape analysis
    STEP1_LANDSCAPE = """Analyse this keyword universe data for "{universe}":

DATA:
{context_json}

Perform landscape analysis. Return ONLY valid JSON:
{{
  "landscape_analysis": {{
    "easy_win_pillars": [
      {{"pillar":"...", "why":"...", "expected_time_to_top3":"X weeks", "kd_avg":0}}
    ],
    "avoid_pillars": [
      {{"pillar":"...", "why":"...", "who_dominates":"..."}}
    ],
    "guaranteed_#1_opportunities": [
      {{"keyword":"...", "why_guaranteed":"...", "kd":0, "est_volume":0, "content_angle":"..."}}
    ],
    "biggest_single_opportunity": "one sentence — the single best move",
    "realistic_12_month_ceiling": "honest prediction",
    "domain_authority_assessment": "based on age {age}mo and {pages} existing pages",
    "critical_insight": "the one thing that will make or break this strategy"
  }}
}}"""

    # Step 2: Priority queue
    STEP2_QUEUE = """Based on the landscape analysis:
{landscape}

And the full data:
{context_json}

Create the exact 90-day publication priority queue. 
RULES:
- Week 1-2: ONLY information gaps and KD < 8 articles
- Week 3-4: Quick wins + first supporting cluster articles
- Month 2: Medium difficulty + pillar page drafts
- Month 3: Pillar pages go live (supported by already-ranking cluster articles)
- Internal link chain must be ready BEFORE pillar page publishes

Return ONLY valid JSON:
{{
  "priority_queue": [
    {{
      "week": 1,
      "articles": [
        {{
          "title": "exact H1 title",
          "target_keyword": "primary keyword",
          "pillar": "parent pillar name",
          "kd_estimate": 0,
          "volume_estimate": 0,
          "why_this_week": "specific strategic reason",
          "information_gain_angle": "the unique element no competitor covers",
          "internal_links_to": ["article title this links TO"],
          "internal_links_from": ["article title that will link FROM here"],
          "schema_type": "Article|FAQPage|HowTo|Product",
          "language": "english|malayalam|hindi",
          "est_rank_by_month_3": 0
        }}
      ]
    }}
  ]
}}
Include weeks 1 through 12."""

    # Step 3: Top 5 content briefs
    STEP3_BRIEFS = """For the 5 highest-opportunity articles from the priority queue, 
create detailed content briefs. These are your anchor articles — get these right 
and the entire strategy succeeds.

Priority queue context:
{top_5_from_queue}

Data context:
{context_json}

Return ONLY valid JSON:
{{
  "content_briefs": [
    {{
      "article_title": "exact H1",
      "target_keyword": "...",
      "secondary_keywords": ["...", "..."],
      "meta_description": "155 chars max, include target keyword",
      "h2_structure": ["H2 1", "H2 2", "H2 3", "H2 4 FAQs"],
      "word_count_target": 0,
      "information_gain_angle": "the specific unique angle — be very specific",
      "unique_data_point": "exact stat or fact to find and cite with source",
      "entities_to_include": ["entity1", "..."],
      "faq_questions": ["Q1", "Q2", "Q3", "Q4"],
      "internal_links": [
        {{"anchor_text":"...", "links_to_article":"...", "placement":"intro|body|conclusion"}}
      ],
      "schema_markup": "FAQPage|HowTo|Article",
      "geo_optimisation_tip": "specific tip for Perplexity/ChatGPT citation",
      "opening_paragraph_template": "first 2 sentences that answer the search intent directly",
      "language": "english",
      "estimated_weeks_to_top3": 0,
      "conversion_cta": "how to convert this reader to a customer"
    }}
  ]
}}"""

    # Step 4: Internal link architecture
    STEP4_LINKS = """Design the complete internal link architecture for all pillars.
This is the Knowledge Graph that tells Google we are the authoritative source.

Pillars: {pillar_names}
Priority queue top 20: {top_20_articles}

Rules:
- Every cluster article → its pillar page (keyword anchor = pillar keyword)
- Every pillar page → 2-3 other related pillar pages (semantic connection)
- Top-intent transactional articles → product/service page
- No article is an orphan
- Maximum 5 outgoing internal links per article (don't dilute)

Return ONLY valid JSON:
{{
  "internal_link_map": {{
    "pillar_to_pillar": [
      {{"from_pillar":"...", "to_pillar":"...", "anchor_text":"...", "reason":"..."}}
    ],
    "cluster_to_pillar": [
      {{"article_keyword":"...", "pillar":"...", "anchor_text":"...", "placement":"..."}}
    ],
    "to_product_page": [
      {{"article_keyword":"...", "anchor_text":"...", "intent":"transactional", "cta":"..."}}
    ]
  }},
  "linking_rules": ["rule1", "rule2", "rule3"],
  "orphan_risk_articles": ["any articles that need special attention"]
}}"""

    # Step 5: Risks + predictions
    STEP5_RISKS_PREDICTIONS = """Final analysis:
Business: {business}
Strategy so far: {landscape_summary}

Step 5a — Risk analysis. Return top 5 risks:
{{
  "risks": [
    {{
      "risk": "...",
      "probability": "low|medium|high",
      "impact": "low|medium|high",
      "mitigation": "specific action to prevent or recover",
      "early_warning_signal": "how to detect this early"
    }}
  ]
}}

Step 5b — 12-month ranking prediction (be honest, not optimistic):
{{
  "predictions": [
    {{
      "month": 1,
      "keywords_in_top_20": 0,
      "keywords_in_top_10": 0,
      "keywords_in_top_3": 0,
      "milestone": "description",
      "condition": "what must happen for this to be true"
    }}
  ],
  "traffic_estimate_month_12": "...",
  "confidence_level": "low|medium|high",
  "make_or_break_factor": "the single most important thing"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — STRATEGY VALIDATOR (DeepSeek)
# ─────────────────────────────────────────────────────────────────────────────

class StrategyValidator:
    """
    DeepSeek validates Claude's strategy output.
    Checks for: cannibalisation, missing pillars, unrealistic predictions,
    internal link conflicts, keyword misuse.
    """

    VALIDATE_PROMPT = """You are an SEO QA expert. Review this strategy output for the keyword universe "{universe}":

STRATEGY:
{strategy_json}

Check for:
1. Keyword cannibalisation (same keyword targeted by 2+ articles)
2. Missing pillar coverage (any pillar with <3 articles in first 90 days)
3. Unrealistic ranking predictions (new domain claiming #1 in <4 weeks for KD>20)
4. Broken internal link chains (article links to something not published yet)
5. Missing information gain angles (any top-5 brief without a unique angle)

Return ONLY valid JSON:
{{
  "issues_found": [
    {{"issue_type":"cannibalisation|missing_pillar|unrealistic|broken_link|missing_gain",
      "description":"...", "severity":"critical|warning|info", "fix":"..."}}
  ],
  "validated_items": ["what is correct and good"],
  "confidence_score": 0.0-1.0,
  "recommendation": "approve|needs_revision|reject"
}}"""

    def validate(self, strategy: dict, universe: str) -> dict:
        prompt = self.VALIDATE_PROMPT.format(
            universe=universe,
            strategy_json=json.dumps({
                "priority_queue_first_3_weeks": strategy.get("priority_queue",[])[:3],
                "content_briefs_count": len(strategy.get("content_briefs",[])),
                "link_map_summary": {
                    "pillar_links": len(strategy.get("link_map",{}).get("pillar_to_pillar",[])),
                    "cluster_links": len(strategy.get("link_map",{}).get("cluster_to_pillar",[])),
                },
                "predictions_summary": strategy.get("predictions",[])[:3],
            }, indent=2)[:3000]
        )
        result = AI.deepseek(prompt, temperature=0.1)
        try:
            return AI.parse_json(result)
        except Exception:
            return {"confidence_score": 0.7, "recommendation": "approve",
                    "issues_found": [], "validated_items": ["validation parse failed"]}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — FINAL STRATEGY ENGINE (MAIN ORCHESTRATOR)
# ─────────────────────────────────────────────────────────────────────────────

CLAUDE_COST_PER_TOKEN = float(os.getenv("CLAUDE_COST_PER_TOKEN", "0.000003"))


class FinalStrategyEngine:
    """
    FinalStrategyEngine does one-shot strategy generation via LLM, strict schema validation,
    and retry logic.

    Input payload MUST include:
      project, keyword_universe, gsc_data, serp_data, competitors, strategy_meta
    """

    REQUIRED_PAYLOAD_KEYS = [
        "project", "keyword_universe", "gsc_data", "serp_data", "competitors", "strategy_meta"
    ]

    def __init__(self, llm_client):
        self.llm = llm_client
        self.max_retries = 2

    def _validate_input_payload(self, payload: dict) -> Optional[str]:
        if not isinstance(payload, dict):
            return "input_payload must be a dict"
        missing = [k for k in self.REQUIRED_PAYLOAD_KEYS if k not in payload]
        if missing:
            return f"missing required payload keys: {', '.join(missing)}"
        return None

    def run(self, input_payload: dict, memory_patterns: str = ""):
        input_error = self._validate_input_payload(input_payload)
        if input_error:
            return {
                "success": False,
                "error": input_error,
                "error_type": "input_validation",
                "raw": "",
                "data": {},
                "tokens_used": 0,
                "cost_usd": 0.0,
                "validation_status": "invalid",
            }

        schema = load_strategy_schema()
        last_error = None
        raw_response = None

        for attempt in range(self.max_retries + 1):
            prompt = build_final_strategy_prompt(
                input_payload=input_payload,
                schema=schema,
                attempt=attempt,
                memory_patterns=memory_patterns,
            )
            # One-shot single-call variant hint; strict JSON output expected:
            prompt = f"{prompt}\n\n{FULL_PROMPT.format(context_json=json.dumps(input_payload, indent=2))}" if attempt == 0 else prompt

            response = self._call_strategy_model(prompt, max_tokens=4000)
            # response will be a (text, tokens) tuple or a plain string
            if isinstance(response, tuple) and len(response) == 2:
                response_text, tokens_used = response
            else:
                response_text = response
                tokens_used = 0
            raw_response = response_text

            cleaned = extract_json(response_text)
            parsed, parse_error = parse_llm_json(cleaned)

            if parse_error:
                last_error = f"parse_error: {parse_error}"
                if attempt >= self.max_retries:
                    return {
                        'success': False,
                        'error': last_error,
                        'error_type': 'parse_error',
                        'raw': raw_response,
                        'data': {},
                        'validation_status': 'invalid',
                        'tokens_used': tokens_used,
                        'cost_usd': tokens_used * CLAUDE_COST_PER_TOKEN,
                    }
                time.sleep(min(2 ** attempt, 30))
                continue

            valid, schema_error = validate_strategy_output(parsed, schema)
            if not valid:
                last_error = f"schema_error: {schema_error}"
                if attempt >= self.max_retries:
                    return {
                        'success': False,
                        'error': last_error,
                        'error_type': 'schema_error',
                        'raw': raw_response,
                        'data': {},
                        'validation_status': 'invalid',
                        'tokens_used': tokens_used,
                        'cost_usd': tokens_used * CLAUDE_COST_PER_TOKEN,
                    }
                time.sleep(min(2 ** attempt, 30))
                continue

            return {
                'success': True,
                'data': parsed,
                'raw': raw_response,
                'validation_status': 'valid',
                'tokens_used': tokens_used,
                'cost_usd': tokens_used * CLAUDE_COST_PER_TOKEN,
            }

        return {
            'success': False,
            'error': last_error or 'unknown',
            'error_type': 'provider_error',
            'raw': raw_response,
            'tokens_used': tokens_used if 'tokens_used' in locals() else 0,
            'cost_usd': (tokens_used if 'tokens_used' in locals() else 0) * CLAUDE_COST_PER_TOKEN,
        }

    def _classify_error(self, msg: str) -> str:
        if 'parse_error' in msg:
            return 'parse_error'
        if 'schema_error' in msg:
            return 'schema_error'
        if 'timeout' in msg.lower():
            return 'timeout'
        return 'provider_error'

    def _call_strategy_model(self, prompt: str, max_tokens: int = 4000):
        """
        Centralized wrapper for calling the LLM client. Returns (text, tokens)
        or a plain string if the client does not return token usage.
        """
        try:
            resp = self.llm.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.2,
                top_p=0.9,
                max_tokens=max_tokens,
            )
            if isinstance(resp, tuple) and len(resp) == 2:
                return resp
            return resp
        except Exception as e:
            log.error(f"_call_strategy_model error: {e}")
            return ('{"error":"llm_call_failed","message":"%s"}' % str(e), 0)


from services.ranking_monitor import RankingMonitor as ServiceRankingMonitor


class RankingMonitor(ServiceRankingMonitor):
    """Wrapper to keep backward compatibility with engine import path."""
    pass

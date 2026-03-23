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

load_dotenv()
log = logging.getLogger("ruflo.strategy")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")  # best for reasoning
    OLLAMA_URL        = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL      = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")

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
    domain:           str
    pillars_covered:  List[str]
    pillars_missing:  List[str]
    estimated_da:     int   # Domain Authority estimate
    content_freshness: str  # "fresh" | "stale" | "mixed"

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
        """Local DeepSeek — validation and quick scoring tasks."""
        try:
            r = _req.post(f"{Cfg.OLLAMA_URL}/api/chat", json={
                "model": Cfg.OLLAMA_MODEL, "stream": False,
                "options": {"temperature": temperature},
                "messages": [{"role":"system","content":system},
                             {"role":"user","content":prompt}]
            }, timeout=120)
            r.raise_for_status()
            text = r.json()["message"]["content"].strip()
            return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        except Exception as e:
            log.warning(f"DeepSeek error: {e}")
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
        pillar_names = [p["name"] for p in tree.get("pillars",[])]
        # Default well-known competitors for tourism
        return [
            CompetitorSnapshot(
                domain="tripadvisor.com", da=90,
                pillars_covered=["Munnar hotels","Munnar tourism"],
                pillars_missing=["Munnar homestays","Munnar food","Munnar shopping"],
                content_freshness="mixed"
            ),
            CompetitorSnapshot(
                domain="holidify.com", da=52,
                pillars_covered=["Munnar tourism","Munnar activities","Munnar weather"],
                pillars_missing=["Munnar homestays","Munnar shopping"],
                content_freshness="stale"
            ),
            CompetitorSnapshot(
                domain="thrillophilia.com", da=55,
                pillars_covered=["Munnar tours","Munnar activities"],
                pillars_missing=["Munnar food","Munnar weather","Munnar shopping"],
                content_freshness="fresh"
            ),
        ]


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

class FinalStrategyEngine:
    """
    Main engine. Feeds complete keyword data to Claude for #1 ranking strategy.

    Usage:
        engine = FinalStrategyEngine()
        strategy = engine.run(universe_result, project)
        # strategy is frozen in DB and populates content calendar automatically
    """

    def __init__(self):
        self.context_builder = ContextBuilder()
        self.validator       = StrategyValidator()
        self.prompts         = StrategyPrompts()

    def run(self, universe_result: dict, project: dict,
             gsc_data: List[dict] = None) -> StrategyOutput:
        """
        Full strategy analysis pipeline.
        One Claude call with complete keyword intelligence context.
        """
        t0 = time.time()
        log.info(f"[Strategy] Starting final strategy analysis for: {universe_result.get('universe','')}")

        # ── Step 1: Build context ─────────────────────────────────────────────
        ctx = self.context_builder.build(universe_result, project, gsc_data)
        ctx_json = ctx.to_compressed_json()
        log.info(f"[Strategy] Context built: {len(ctx_json)} chars, ~{len(ctx_json)//4} tokens")

        total_tokens = 0
        strategy = {}

        # ── Step 2: Claude CoT — Landscape Analysis ───────────────────────────
        log.info("[Strategy] Step 1: Landscape analysis...")
        prompt1 = self.prompts.STEP1_LANDSCAPE.format(
            universe=ctx.universe,
            context_json=ctx_json,
            age=ctx.domain_age_months,
            pages=ctx.existing_pages
        )
        text1, t1 = AI.claude(self.prompts.SYSTEM,
                               [{"role":"user","content":prompt1}],
                               max_tokens=1500)
        total_tokens += t1
        try:
            landscape = AI.parse_json(text1).get("landscape_analysis", {})
        except Exception as e:
            log.warning(f"Landscape parse failed: {e}")
            landscape = {}
        strategy["landscape"] = landscape

        # ── Step 3: Claude CoT — Priority Queue ───────────────────────────────
        log.info("[Strategy] Step 2: Priority queue...")
        prompt2 = self.prompts.STEP2_QUEUE.format(
            landscape=json.dumps(landscape)[:800],
            context_json=ctx_json[:4000]   # shorter for subsequent calls
        )
        text2, t2 = AI.claude(self.prompts.SYSTEM,
                               [{"role":"user","content":prompt2}],
                               max_tokens=3000)
        total_tokens += t2
        try:
            pq = AI.parse_json(text2).get("priority_queue", [])
        except Exception as e:
            log.warning(f"Priority queue parse failed: {e}")
            pq = []
        strategy["priority_queue"] = pq

        # ── Step 4: Claude CoT — Content Briefs ──────────────────────────────
        log.info("[Strategy] Step 3: Content briefs...")
        top5 = []
        for week_data in pq[:3]:
            top5.extend(week_data.get("articles", [])[:2])
        top5 = top5[:5]

        prompt3 = self.prompts.STEP3_BRIEFS.format(
            top_5_from_queue=json.dumps(top5, indent=2)[:1500],
            context_json=ctx_json[:3000]
        )
        text3, t3 = AI.claude(self.prompts.SYSTEM,
                               [{"role":"user","content":prompt3}],
                               max_tokens=3500)
        total_tokens += t3
        try:
            briefs = AI.parse_json(text3).get("content_briefs", [])
        except Exception as e:
            log.warning(f"Content briefs parse failed: {e}")
            briefs = []
        strategy["content_briefs"] = briefs

        # ── Step 5: Claude CoT — Internal Link Architecture ───────────────────
        log.info("[Strategy] Step 4: Internal link map...")
        top20_articles = [a for w in pq[:8] for a in w.get("articles",[])]
        prompt4 = self.prompts.STEP4_LINKS.format(
            pillar_names=", ".join(p.name for p in ctx.pillars),
            top_20_articles=json.dumps([a.get("title","") for a in top20_articles[:20]])
        )
        text4, t4 = AI.claude(self.prompts.SYSTEM,
                               [{"role":"user","content":prompt4}],
                               max_tokens=2000)
        total_tokens += t4
        try:
            link_map = AI.parse_json(text4).get("internal_link_map", {})
            link_rules = AI.parse_json(text4).get("linking_rules", [])
        except Exception as e:
            log.warning(f"Link map parse failed: {e}")
            link_map, link_rules = {}, []
        strategy["link_map"] = link_map
        strategy["linking_rules"] = link_rules

        # ── Step 6: Claude CoT — Risks + Predictions ─────────────────────────
        log.info("[Strategy] Step 5: Risks and predictions...")
        prompt5 = self.prompts.STEP5_RISKS_PREDICTIONS.format(
            business=ctx.business_context,
            landscape_summary=json.dumps(landscape)[:500]
        )
        text5, t5 = AI.claude(self.prompts.SYSTEM,
                               [{"role":"user","content":prompt5}],
                               max_tokens=2000)
        total_tokens += t5
        try:
            parsed5 = AI.parse_json(text5)
            risks   = parsed5.get("risks", [])
            preds   = parsed5.get("predictions", [])
        except Exception as e:
            log.warning(f"Risks/predictions parse failed: {e}")
            risks, preds = [], []
        strategy["risks"]       = risks
        strategy["predictions"] = preds

        # ── Step 7: DeepSeek Validation ───────────────────────────────────────
        log.info("[Strategy] Step 6: Validation...")
        validation = self.validator.validate(strategy, ctx.universe)
        confidence = float(validation.get("confidence_score", 0.7))

        # ── Step 8: Assemble final output ─────────────────────────────────────
        output = StrategyOutput(
            landscape=strategy.get("landscape", {}),
            priority_queue=strategy.get("priority_queue", []),
            content_briefs=strategy.get("content_briefs", []),
            link_map=strategy.get("link_map", {}),
            risks=strategy.get("risks", []),
            predictions=strategy.get("predictions", []),
            confidence=confidence,
            generated_at=datetime.utcnow().isoformat(),
            tokens_used=total_tokens
        )

        elapsed = int((time.time()-t0)*1000)
        log.info(f"[Strategy] Complete. Tokens: {total_tokens}, "
                 f"Confidence: {confidence:.2f}, Duration: {elapsed}ms, "
                 f"Cost: ~${total_tokens/1000000*15:.4f}")

        return output

    def generate_content_calendar(self, strategy: StrategyOutput,
                                   start_date: datetime = None) -> List[dict]:
        """
        Convert priority queue into a concrete daily content calendar.
        10-20 blogs per pillar distributed across the year.
        """
        if not start_date:
            start_date = datetime.utcnow()

        calendar = []
        article_num = 0

        for week_data in strategy.priority_queue:
            week_num  = week_data.get("week", 1)
            articles  = week_data.get("articles", [])
            week_start= start_date + timedelta(weeks=week_num-1)

            for i, article in enumerate(articles):
                pub_date = week_start + timedelta(days=i*2)   # every 2 days within week
                calendar.append({
                    "id":               f"blog_{article_num:04d}",
                    "title":            article.get("title",""),
                    "target_keyword":   article.get("target_keyword",""),
                    "pillar":           article.get("pillar",""),
                    "scheduled_date":   pub_date.isoformat(),
                    "week":             week_num,
                    "kd_estimate":      article.get("kd_estimate",20),
                    "schema_type":      article.get("schema_type","Article"),
                    "language":         article.get("language","english"),
                    "internal_links_to":article.get("internal_links_to",[]),
                    "status":           "scheduled",
                    "frozen":           False,
                    "content_body":     None,
                    "published_url":    None,
                    "ranking":          None,
                })
                article_num += 1

        return calendar

    def format_strategy_report(self, strategy: StrategyOutput) -> str:
        """
        Human-readable strategy report for user review.
        Shown in app dashboard before final approval.
        """
        lines = [
            "═" * 60,
            "  FINAL STRATEGY REPORT — AI ANALYSIS COMPLETE",
            "═" * 60,
            "",
            f"  Confidence Score: {strategy.confidence:.0%}",
            f"  Generated: {strategy.generated_at[:10]}",
            f"  API tokens used: {strategy.tokens_used:,}",
            "",
            "─" * 60,
            "  LANDSCAPE ANALYSIS",
            "─" * 60,
        ]

        la = strategy.landscape
        if la:
            lines.append(f"\n  Critical insight: {la.get('critical_insight','')}")
            lines.append(f"\n  Biggest opportunity: {la.get('biggest_single_opportunity','')}")
            lines.append(f"\n  12-month ceiling: {la.get('realistic_12_month_ceiling','')}")

            easy = la.get("easy_win_pillars", [])
            if easy:
                lines.append("\n  Easy win pillars:")
                for p in easy[:3]:
                    lines.append(f"    • {p.get('pillar','')} — {p.get('why','')} "
                                 f"(top 3 in {p.get('expected_time_to_top3','')})")

            avoid = la.get("avoid_pillars", [])
            if avoid:
                lines.append("\n  Avoid (too competitive):")
                for p in avoid[:3]:
                    lines.append(f"    ✗ {p.get('pillar','')} — dominated by {p.get('who_dominates','')}")

            gaps = la.get("guaranteed_#1_opportunities", [])
            if gaps:
                lines.append("\n  Guaranteed #1 opportunities:")
                for g in gaps[:5]:
                    lines.append(f"    ★ {g.get('keyword','')} (KD {g.get('kd',0)}, "
                                 f"{g.get('est_volume',0)} searches/mo)")

        lines += ["", "─" * 60, "  WEEK 1 ARTICLES (publish immediately)", "─" * 60]
        if strategy.priority_queue:
            w1 = strategy.priority_queue[0]
            for a in w1.get("articles", []):
                lines.append(f"\n  [{a.get('kd_estimate',0)} KD] {a.get('title','')}")
                lines.append(f"         → {a.get('why_this_week','')}")

        lines += ["", "─" * 60, "  12-MONTH RANKING PREDICTIONS", "─" * 60]
        for pred in strategy.predictions[:6]:
            lines.append(f"\n  Month {pred.get('month',0):2d}: "
                         f"top-20: {pred.get('keywords_in_top_20',0)}, "
                         f"top-10: {pred.get('keywords_in_top_10',0)}, "
                         f"top-3: {pred.get('keywords_in_top_3',0)}")
            if pred.get("milestone"):
                lines.append(f"          {pred['milestone']}")

        lines += ["", "─" * 60, "  TOP RISKS", "─" * 60]
        for r in strategy.risks[:3]:
            lines.append(f"\n  ⚠ [{r.get('probability','?')} probability] {r.get('risk','')}")
            lines.append(f"    → Mitigation: {r.get('mitigation','')}")

        lines += ["", "═" * 60, "  Approve this strategy to begin execution.", "═" * 60]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — RANKING DROP MONITOR + RE-TRIGGER
# ─────────────────────────────────────────────────────────────────────────────

class RankingMonitor:
    """
    Continuously monitors rankings via GSC API.
    Auto-triggers Claude diagnosis when keyword drops below threshold.
    Auto-triggers strategy re-run monthly.
    """

    DIAGNOSIS_PROMPT = """A page has dropped in Google rankings.

Universe: {universe}
Keyword: "{keyword}"
Previous rank: #{prev_rank}
Current rank:  #{curr_rank}
Days since drop: {days}
Page title: {page_title}
Current content summary: {content_summary}

This competitor page recently appeared or improved: {competitor_page}

DIAGNOSE the drop and prescribe SPECIFIC fixes. Return ONLY valid JSON:
{{
  "root_cause": "primary reason for drop",
  "contributing_factors": ["factor 1", "factor 2"],
  "competitor_advantage": "what the overtaking page has that ours doesn't",
  "fixes": [
    {{
      "action": "add_faq|update_entities|add_data_point|rewrite_intro|add_schema|internal_link",
      "specific_instruction": "exact text or action",
      "priority": "do_now|do_this_week|do_this_month",
      "expected_impact": "weeks to recover rank"
    }}
  ],
  "new_h2_to_add": "...",
  "new_intro_sentence": "direct answer sentence to put at top of article",
  "entities_to_add": ["...", "..."],
  "information_gain_addition": "unique data point to add to beat competitor",
  "estimated_recovery_weeks": 0
}}"""

    def diagnose_drop(self, keyword: str, prev_rank: int, curr_rank: int,
                       page_title: str, content_summary: str,
                       competitor_page: str, universe: str) -> dict:
        """Claude diagnoses why a keyword dropped and what to fix."""
        log.info(f"[Monitor] Diagnosing drop: '{keyword}' #{prev_rank} → #{curr_rank}")
        prompt = self.DIAGNOSIS_PROMPT.format(
            universe=universe, keyword=keyword,
            prev_rank=prev_rank, curr_rank=curr_rank,
            days=14, page_title=page_title,
            content_summary=content_summary[:500],
            competitor_page=competitor_page[:300]
        )
        text, tokens = AI.claude(StrategyPrompts.SYSTEM,
                                  [{"role":"user","content":prompt}],
                                  max_tokens=1500)
        log.info(f"[Monitor] Diagnosis complete. Tokens: {tokens}")
        try:
            return AI.parse_json(text)
        except Exception:
            return {"root_cause": "parse_failed", "fixes": [], "estimated_recovery_weeks": 4}

    def check_gsc_alerts(self, gsc_data: List[dict],
                          threshold: int = None) -> List[dict]:
        """Find keywords that have dropped below threshold — trigger diagnosis."""
        threshold = threshold or Cfg.RANK_ALERT_THRESHOLD
        alerts = []
        for row in gsc_data:
            curr = row.get("rank", 99)
            prev = row.get("prev_rank", curr)
            if curr > threshold and prev <= threshold:
                alerts.append({
                    "keyword": row.get("keyword",""),
                    "current_rank": curr,
                    "previous_rank": prev,
                    "impressions": row.get("impressions",0),
                    "severity": "critical" if curr > 10 else "high"
                })
        return sorted(alerts, key=lambda x: x["impressions"], reverse=True)

    def should_refresh_strategy(self, last_refresh: datetime) -> bool:
        """Check if monthly strategy refresh is due."""
        days_since = (datetime.utcnow() - last_refresh).days
        return days_since >= 30


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — TEST SUITE
# ─────────────────────────────────────────────────────────────────────────────

class Tests:
    """
    Test the strategy engine with Munnar tourism example.

    Run:
      python ruflo_final_strategy_engine.py test context   # context builder
      python ruflo_final_strategy_engine.py test validate  # DeepSeek validator
      python ruflo_final_strategy_engine.py test calendar  # content calendar
      python ruflo_final_strategy_engine.py test diagnose  # ranking drop
      python ruflo_final_strategy_engine.py test full      # full Claude strategy
    """

    MOCK_PROJECT = {
        "name": "Munnar Experiences",
        "industry": "Tourism & Travel",
        "business_type": "B2C",
        "usp": "local Kerala family-run homestays and curated experiences",
        "target_audience": ["couples","families","solo travellers","honeymooners"],
        "target_languages": ["english","malayalam","hindi"],
        "target_regions": ["munnar","kerala","india"],
        "domain_age_months": 4,
        "existing_pages": 8,
    }

    MOCK_UNIVERSE = {
        "universe_tree": {
            "universe": "munnar tourism",
            "pillars": [
                {"name":"Munnar tourism","competitor_count":15,
                 "clusters":[{"name":"Places","keyword_items":[
                     {"term":"best places Munnar","kd_estimate":42,"volume_estimate":18000,"final_score":5.9,"is_info_gap":False,"intent":"informational"},
                     {"term":"Munnar 2 day itinerary","kd_estimate":6,"volume_estimate":2200,"final_score":8.6,"is_info_gap":False,"intent":"informational"},
                 ]}],
                 "supporting_keyword_engine":{"info_gaps":[
                     {"term":"is Munnar safe in monsoon","kd_estimate":4,"volume_estimate":2400,"is_info_gap":True,"why_unique":"no competitor gives week-by-week breakdown"}
                 ], "competitor_entities":["Eravikulam","Anamudi","IMD","NH85","KSRTC"]}},
                {"name":"Munnar homestays","competitor_count":10,
                 "clusters":[{"name":"Budget stays","keyword_items":[
                     {"term":"budget homestay Munnar","kd_estimate":7,"volume_estimate":1800,"final_score":8.4,"is_info_gap":False,"intent":"transactional"},
                 ]}],
                 "supporting_keyword_engine":{"info_gaps":[
                     {"term":"Munnar homestay vs resort","kd_estimate":5,"volume_estimate":1800,"is_info_gap":True,"why_unique":"no comparison article exists"}
                 ], "competitor_entities":["Devikulam","Top Station","Eravikulam"]}},
                {"name":"Munnar tours","competitor_count":12,
                 "clusters":[{"name":"Packages","keyword_items":[
                     {"term":"Munnar honeymoon package","kd_estimate":18,"volume_estimate":4500,"final_score":7.0,"is_info_gap":False,"intent":"transactional"},
                 ]}],
                 "supporting_keyword_engine":{"info_gaps":[], "competitor_entities":["Kundala Lake","Mattupetty"]}},
            ],
            "top_100": [
                {"term":"is Munnar safe in monsoon","kd_estimate":4,"volume_estimate":2400,"final_score":9.3,"is_info_gap":True,"intent":"informational"},
                {"term":"how much does Munnar trip cost","kd_estimate":6,"volume_estimate":3200,"final_score":9.5,"is_info_gap":True,"intent":"informational"},
                {"term":"Munnar homestay vs resort","kd_estimate":5,"volume_estimate":1800,"final_score":9.0,"is_info_gap":True,"intent":"commercial"},
                {"term":"Munnar 2 day itinerary","kd_estimate":6,"volume_estimate":2200,"final_score":8.6,"is_info_gap":False,"intent":"informational"},
                {"term":"budget homestay Munnar","kd_estimate":7,"volume_estimate":1800,"final_score":8.4,"is_info_gap":False,"intent":"transactional"},
            ]
        }
    }

    MOCK_GSC = [
        {"keyword":"Munnar travel guide","rank":13,"prev_rank":8,"impressions":8200,"clicks":310},
        {"keyword":"Munnar homestay","rank":6,"prev_rank":3,"impressions":5600,"clicks":190},
        {"keyword":"things to do Munnar","rank":4,"prev_rank":4,"impressions":6700,"clicks":280},
    ]

    def _h(self, n): print(f"\n{'─'*55}\n  TEST: {n}\n{'─'*55}")
    def _ok(self, m): print(f"  ✓ {m}")

    def test_context(self):
        self._h("Context Builder")
        builder = ContextBuilder()
        ctx = builder.build(self.MOCK_UNIVERSE, self.MOCK_PROJECT, self.MOCK_GSC)
        compressed = ctx.to_compressed_json()
        self._ok(f"Universe: {ctx.universe}")
        self._ok(f"Pillars: {len(ctx.pillars)}")
        self._ok(f"Top keywords: {len(ctx.top_20_keywords)}")
        self._ok(f"Info gaps: {len(ctx.info_gaps)}")
        self._ok(f"Competitors: {len(ctx.competitors)}")
        self._ok(f"Entities: {len(ctx.entities)}")
        self._ok(f"Compressed size: {len(compressed)} chars, ~{len(compressed)//4} tokens")
        self._ok(f"Cost estimate: ~${len(compressed)//4/1000000*15:.6f}")

    def test_validate(self):
        self._h("DeepSeek Strategy Validator")
        validator = StrategyValidator()
        mock_strategy = {
            "priority_queue": [
                {"week":1,"articles":[
                    {"title":"Is Munnar Safe in Monsoon","target_keyword":"munnar monsoon safe",
                     "kd_estimate":4,"why_this_week":"info gap, zero competition",
                     "information_gain_angle":"IMD week-by-week data",
                     "schema_type":"FAQPage","internal_links_to":[],"internal_links_from":[]},
                ]}
            ],
            "content_briefs": [{"article_title":"test","information_gain_angle":"unique angle"}],
            "link_map": {"pillar_to_pillar":[],"cluster_to_pillar":[]},
            "predictions": [{"month":1,"keywords_in_top_20":5,"keywords_in_top_10":0,"keywords_in_top_3":0}]
        }
        result = validator.validate(mock_strategy, "munnar tourism")
        self._ok(f"Confidence: {result.get('confidence_score',0):.2f}")
        self._ok(f"Recommendation: {result.get('recommendation','?')}")
        self._ok(f"Issues: {len(result.get('issues_found',[]))}")

    def test_calendar(self):
        self._h("Content Calendar Generator")
        engine = FinalStrategyEngine()
        mock_strategy = StrategyOutput(
            landscape={}, confidence=0.85, generated_at=datetime.utcnow().isoformat(),
            tokens_used=5000, risks=[], predictions=[],
            link_map={}, content_briefs=[],
            priority_queue=[
                {"week":1,"articles":[
                    {"title":"Is Munnar Safe in Monsoon?","target_keyword":"munnar monsoon safe",
                     "pillar":"Munnar tourism","kd_estimate":4,"schema_type":"FAQPage","language":"english",
                     "internal_links_to":["Munnar travel guide"],"why_this_week":"info gap"},
                    {"title":"Munnar Homestay vs Resort — Honest Guide","target_keyword":"munnar homestay vs resort",
                     "pillar":"Munnar homestays","kd_estimate":5,"schema_type":"Article","language":"english",
                     "internal_links_to":["budget homestay Munnar"],"why_this_week":"high intent info gap"},
                ]},
                {"week":2,"articles":[
                    {"title":"How Much Does a Munnar Trip Actually Cost?","target_keyword":"munnar trip cost",
                     "pillar":"Munnar tourism","kd_estimate":6,"schema_type":"Article","language":"english",
                     "internal_links_to":[],"why_this_week":"highest volume info gap"},
                ]},
            ]
        )
        calendar = engine.generate_content_calendar(mock_strategy, datetime.utcnow())
        self._ok(f"Calendar entries: {len(calendar)}")
        for c in calendar[:3]:
            self._ok(f"  [{c['scheduled_date'][:10]}] {c['title']} | {c['status']}")

    def test_diagnose(self):
        self._h("Ranking Drop Diagnosis")
        monitor = RankingMonitor()
        alerts = monitor.check_gsc_alerts(self.MOCK_GSC, threshold=5)
        self._ok(f"Alerts detected: {len(alerts)}")
        for a in alerts:
            self._ok(f"  '{a['keyword']}' #{a['previous_rank']} → #{a['current_rank']} [{a['severity']}]")

        if alerts:
            self._ok("Running Claude diagnosis on first alert...")
            a = alerts[0]
            diagnosis = monitor.diagnose_drop(
                keyword=a["keyword"], prev_rank=a["previous_rank"],
                curr_rank=a["current_rank"],
                page_title="Munnar Homestay Guide",
                content_summary="A guide to finding homestays in Munnar covering budget to luxury options.",
                competitor_page="New page on booking.com with photos and instant booking",
                universe="munnar tourism"
            )
            self._ok(f"Root cause: {diagnosis.get('root_cause','?')}")
            self._ok(f"Fixes: {len(diagnosis.get('fixes',[]))} actions")
            for fix in diagnosis.get("fixes",[])[:3]:
                self._ok(f"  [{fix.get('priority','?')}] {fix.get('action','?')}: {fix.get('specific_instruction','')[:60]}")

    def test_full(self):
        self._h("FULL STRATEGY ENGINE — Munnar Tourism")
        self._ok("Building context...")
        engine = FinalStrategyEngine()
        strategy = engine.run(self.MOCK_UNIVERSE, self.MOCK_PROJECT, self.MOCK_GSC)

        print(engine.format_strategy_report(strategy))

        calendar = engine.generate_content_calendar(strategy)
        self._ok(f"\nContent calendar: {len(calendar)} articles scheduled")
        self._ok(f"Confidence: {strategy.confidence:.0%}")
        self._ok(f"Tokens used: {strategy.tokens_used:,}")
        self._ok(f"Priority queue weeks: {len(strategy.priority_queue)}")
        self._ok(f"Content briefs: {len(strategy.content_briefs)}")
        self._ok(f"Risks identified: {len(strategy.risks)}")
        self._ok(f"Monthly predictions: {len(strategy.predictions)}")
        return strategy

    def run_all(self):
        tests = [
            ("context",  self.test_context),
            ("validate", self.test_validate),
            ("calendar", self.test_calendar),
            ("diagnose", self.test_diagnose),
        ]
        print("\n" + "═"*55)
        print("  FINAL STRATEGY ENGINE — STAGE TESTS")
        print("═"*55)
        p = f = 0
        for name, fn in tests:
            try:
                fn()
                p += 1
            except Exception as e:
                print(f"  ✗ {name}: {e}")
                f += 1
        print(f"\n  {p} passed / {f} failed")
        print("═"*55)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — FASTAPI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="Ruflo — Final Strategy Engine",
                  description="Feeds complete keyword data to Claude for #1 ranking strategy",
                  version="1.0.0")

    strategy_engine = FinalStrategyEngine()
    monitor_engine  = RankingMonitor()
    _jobs: dict = {}

    class StrategyRequest(BaseModel):
        universe_result:   dict
        project:           dict
        gsc_data:          list = []

    class DiagnosisRequest(BaseModel):
        keyword:          str
        prev_rank:        int
        curr_rank:        int
        page_title:       str
        content_summary:  str
        competitor_page:  str
        universe:         str

    @app.post("/api/strategy/run", tags=["Strategy"])
    def run_strategy(req: StrategyRequest, background_tasks: BackgroundTasks):
        """Run final Claude strategy analysis on complete keyword universe data."""
        job_id = __import__('uuid').uuid4().hex
        _jobs[job_id] = {"status":"running"}
        def _run():
            try:
                strategy = strategy_engine.run(req.universe_result, req.project, req.gsc_data)
                calendar = strategy_engine.generate_content_calendar(strategy)
                _jobs[job_id] = {
                    "status": "done",
                    "strategy": {
                        "landscape":      strategy.landscape,
                        "priority_queue": strategy.priority_queue,
                        "content_briefs": strategy.content_briefs,
                        "link_map":       strategy.link_map,
                        "risks":          strategy.risks,
                        "predictions":    strategy.predictions,
                        "confidence":     strategy.confidence,
                        "tokens_used":    strategy.tokens_used,
                        "generated_at":   strategy.generated_at,
                    },
                    "content_calendar": calendar,
                    "report": strategy_engine.format_strategy_report(strategy),
                }
            except Exception as e:
                _jobs[job_id] = {"status":"failed","error":str(e)}
        background_tasks.add_task(_run)
        return {"job_id": job_id, "message": "Strategy analysis started"}

    @app.post("/api/strategy/diagnose", tags=["Strategy"])
    def diagnose_drop(req: DiagnosisRequest):
        """Claude diagnoses why a keyword dropped and what to fix."""
        return monitor_engine.diagnose_drop(
            req.keyword, req.prev_rank, req.curr_rank,
            req.page_title, req.content_summary,
            req.competitor_page, req.universe
        )

    @app.post("/api/strategy/alerts", tags=["Strategy"])
    def check_alerts(gsc_data: list, threshold: int = 5):
        """Check GSC data for keywords that dropped below threshold."""
        return monitor_engine.check_gsc_alerts(gsc_data, threshold)

    @app.get("/api/jobs/{job_id}", tags=["Jobs"])
    def get_job(job_id: str):
        if job_id not in _jobs:
            raise HTTPException(404, "Job not found")
        return _jobs[job_id]

except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    HELP = """
Ruflo — Final AI Strategy Engine
──────────────────────────────────────────────────────
Feeds complete keyword universe data to Claude Sonnet for definitive
#1 ranking strategy. Chain-of-thought reasoning across 5 steps.

Usage:
  python ruflo_final_strategy_engine.py test           # all tests
  python ruflo_final_strategy_engine.py test <stage>   # one test
  python ruflo_final_strategy_engine.py full           # full Claude strategy
  python ruflo_final_strategy_engine.py api            # start FastAPI server

Stages: context, validate, calendar, diagnose
Requires: ANTHROPIC_API_KEY in .env for full strategy test
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
    elif cmd == "full":
        Tests().test_full()
    elif cmd == "api":
        try:
            import uvicorn
            print("Ruflo Strategy API — http://localhost:8001")
            uvicorn.run("ruflo_final_strategy_engine:app",
                        host="0.0.0.0", port=8001, reload=True)
        except ImportError:
            print("pip install uvicorn")
    else:
        print(f"Unknown: {cmd}\n{HELP}")

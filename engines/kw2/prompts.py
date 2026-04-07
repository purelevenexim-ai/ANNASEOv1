"""
kw2 prompts — all AI prompt templates centralized.
"""

# ── Phase 1: Business Analysis ──────────────────────────────────────────

BUSINESS_ANALYSIS_SYSTEM = (
    "You are a senior SEO strategist and business analyst. "
    "Focus ONLY on revenue-generating aspects. Think like someone trying to SELL products. "
    "Output ONLY valid JSON, no markdown fences."
)

BUSINESS_ANALYSIS_USER = """Analyze this business website data and return a structured business profile.

PRODUCTS PAGE DATA:
{products}

CATEGORIES PAGE DATA:
{categories}

ABOUT PAGE DATA:
{about}

EXTRACTED ENTITIES:
{entities}

EXTRACTED TOPICS:
{topics}

COMPETITOR DATA:
{competitor_data}

MANUAL INPUT FROM USER:
{manual_input}

Return JSON with these exact keys:
{{
  "universe": "2-3 word business universe name (e.g. 'Indian Spices', 'Organic Supplements')",
  "pillars": ["max 10 pillar keywords — ONLY physical sellable product categories, NOT informational topics"],
  "product_catalog": ["specific products found on site"],
  "modifiers": ["qualifiers: organic, wholesale, bulk, premium, etc."],
  "audience": ["target buyer types"],
  "intent_signals": ["primary buyer intents detected"],
  "geo_scope": "primary geographic market",
  "business_type": "B2B|B2C|D2C|SaaS|Local|Ecommerce",
  "negative_scope": ["terms to ALWAYS exclude: recipe, benefits, how to, what is, health benefits, side effects, nutritional value, home remedy, ayurvedic uses — at minimum"]
}}

RULES:
- pillars = physical sellable product categories, NOT informational topics
- negative_scope MUST include: recipe, benefits, how to, what is (at minimum)
- product_catalog = specific items, not categories
- modifiers = words that combine with pillars to form buyer keywords"""

# ── Phase 1: Consistency Check ───────────────────────────────────────────

CONSISTENCY_CHECK_SYSTEM = (
    "You are a data validation expert. Check business profiles for internal consistency. "
    "Output ONLY valid JSON."
)

CONSISTENCY_CHECK_USER = """Is this business profile accurate and internally consistent?

PROFILE:
{profile_json}

Check:
1. Pillars are sellable products (not informational topics like "benefits" or "recipes")
2. negative_scope excludes all informational patterns
3. product_catalog items match at least some pillars
4. No pillar appears in negative_scope

Return JSON: {{"valid": true/false, "issues": ["list of issues if any"]}}"""

# ── Phase 2: AI Keyword Expansion ────────────────────────────────────────

UNIVERSE_EXPAND_SYSTEM = (
    "You are an SEO keyword specialist. Generate ONLY commercial/transactional keyword variations. "
    "No informational keywords whatsoever. One keyword per line, no numbering, no bullets."
)

UNIVERSE_EXPAND_USER = """Business universe: {universe}
Pillar product: {pillar}
Existing modifiers: {modifiers}

Generate 30 buyer-intent keyword variations for this pillar.

ONLY use these intent types: buy, price, wholesale, supplier, bulk, near me, online, for sale, order, shop, export, manufacturer, distributor.
NEVER generate: benefits, recipes, how to, what is, history, ayurvedic, health, nutrition, side effects.

One keyword per line:"""

# ── Phase 3: AI Validation ───────────────────────────────────────────────

VALIDATE_SYSTEM = (
    "You are a strict SEO quality filter. Evaluate keyword commercial relevance for a specific business. "
    "Return ONLY a valid JSON array, no explanation."
)

VALIDATE_USER = """Business: {universe}
Pillars: {pillars_str}
Hard-reject if matches: {negative_scope_str}
Number of keywords to evaluate: {n}

Keywords:
{keywords_list}

Return JSON array — one object per keyword:
[{{"keyword": "...", "relevance": 0.0-1.0, "intent": "purchase|transactional|commercial|comparison|local|informational", "buyer_readiness": 0.0-1.0}}]

RULES:
- informational keywords (how to, benefits, recipes, what is) = relevance < 0.3 ALWAYS
- keywords not containing any pillar word = relevance < 0.5
- buyer-ready keywords (buy, price, wholesale, supplier) = relevance > 0.8"""

# ── Phase 4b: Cluster Naming ─────────────────────────────────────────────

CLUSTER_NAME_SYSTEM = (
    "You are an SEO content strategist. "
    "Return ONLY a 2-4 word cluster name, no explanation."
)

CLUSTER_NAME_USER = """Given these semantically similar commercial keywords:
{keywords_list}

Name this cluster with 2-4 words that describe their commercial theme.
Examples: "Wholesale Bulk Orders", "Price Comparison", "Local Suppliers", "Online Purchase".

Cluster name:"""

# ── Phase 5: Keyword Explanation ─────────────────────────────────────────

KEYWORD_EXPLAIN_SYSTEM = (
    "You are an SEO strategist. Explain in 1-2 sentences why a keyword is valuable."
)

KEYWORD_EXPLAIN_USER = (
    "Why is '{keyword}' a high-value SEO keyword for a {universe} business? "
    "Intent: {intent}, Score: {score}."
)

# ── Phase 9: Strategy Generation ─────────────────────────────────────────

STRATEGY_SYSTEM = (
    "You are a senior SEO strategist. Generate a comprehensive content strategy "
    "based on validated keyword data. Output ONLY valid JSON."
)

STRATEGY_USER = """Business: {universe} ({business_type})
Pillars: {pillars}
Top keywords ({count}): {top_keywords}
Clusters: {clusters}
Audience: {audience}
Geo: {geo_scope}

Generate a 90-day SEO content strategy as JSON:
{{
  "strategy_summary": {{
    "headline": "one-sentence strategy",
    "biggest_opportunity": "underserved keyword gap or persona",
    "why_we_win": "specific competitive advantage"
  }},
  "priority_pillars": ["ordered by opportunity"],
  "weekly_plan": [
    {{
      "week": 1,
      "focus_pillar": "...",
      "articles": [
        {{
          "title": "...",
          "primary_keyword": "...",
          "intent": "...",
          "page_type": "product_page|category_page|blog_page|b2b_page|local_page"
        }}
      ]
    }}
  ],
  "quick_wins": ["keywords with low KD and high buyer intent"],
  "content_gaps": ["topics competitors cover that we don't"]
}}"""

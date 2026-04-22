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
- pillars must be concrete noun phrases the business can actually sell, usually 1-3 words
- reject pillars that are only promo words, quality adjectives, geo words, packaging words, or search intent words
- reject examples like: benefits, recipe, quality, premium, best seller, new arrival, online, near me, price
- negative_scope MUST include: recipe, benefits, how to, what is (at minimum)
- product_catalog = specific items, not categories
- modifiers = product-safe qualifiers that combine naturally with pillars to form buyer keywords
- modifiers should prefer qualifiers like: organic, wholesale, bulk, premium, export quality, farm direct, manufacturer
- modifiers must NOT be informational topics, promo fluff, or generic store labels"""

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
5. modifiers are usable product qualifiers, not generic promo/store words or pure search verbs

Return JSON: {{"valid": true/false, "issues": ["list of issues if any"]}}"""

# ── Phase 2: AI Keyword Expansion ────────────────────────────────────────

UNIVERSE_EXPAND_SYSTEM = (
    "You are an SEO keyword specialist. Generate ONLY commercial/transactional keyword variations. "
    "No informational keywords whatsoever. One keyword per line, no numbering, no bullets."
)

UNIVERSE_EXPAND_USER = """Business universe: {universe}
Pillar product: {pillar}
Core search term: {core_term}
Existing modifiers: {modifiers}
Target locations: {target_locations}
Business locations (where business operates/sources from): {business_locations}
Languages: {languages}
Cultural context: {cultural_context}
USP: {usp}
Customer voice: {customer_voice}

Generate {target_count} buyer-intent keyword variations for this product pillar.

Include ALL of these categories:
- Buy/order/shop intent: "buy {core_term}", "order {core_term} online", "shop {core_term} india"
- Price/rate intent: "{core_term} price", "{core_term} rate india", "{core_term} cost per kg"
- Wholesale/bulk: "{core_term} wholesale", "{core_term} bulk buy", "{core_term} bulk price"
- Supplier/source: "{core_term} supplier", "{core_term} manufacturer india", "{core_term} exporter"
- Geo variants: use EACH target location listed above (e.g. "{core_term} [location]", "buy {core_term} [location]")
- Source/origin: use business locations for origin keywords (e.g. "{core_term} from [business_location]", "[business_location] {core_term} supplier")
- Product variants: different weights (100g, 200g, 500g, 1kg), packs, grades
- B2B/trade: "{core_term} wholesale dealer", "{core_term} trade price", "{core_term} reseller"
- Cultural/niche: use cultural context above to generate niche keywords (e.g. "ayurvedic {core_term}", "halal {core_term}")
- Customer language: use real phrases from customer voice above to inspire natural keyword variations
- USP-driven: combine USP angles (e.g. "organic", "farm direct") with {core_term}

ONLY commercial/transactional keywords.
NEVER generate: health benefits, recipes, how to use, what is, history, side effects, nutrition.
{existing_kws_note}
One keyword per line, no numbering, no bullets:"""

# ── Phase 3: AI Validation ───────────────────────────────────────────────

VALIDATE_SYSTEM = (
    "You are a strict SEO quality filter. Evaluate keyword commercial relevance for a specific business. "
    "Return ONLY a valid JSON array, no explanation."
)

VALIDATE_USER = """Business: {universe}
Pillars: {pillars_str}
Hard-reject if matches: {negative_scope_str}
Target locations: {target_locations}
Business locations (where the business operates): {business_locations}
Cultural context: {cultural_context}
Number of keywords to evaluate: {n}

Keywords:
{keywords_list}

Return JSON array — one object per keyword:
[{{"keyword": "...", "relevance": 0.0-1.0, "intent": "purchase|transactional|commercial|comparison|local|informational", "buyer_readiness": 0.0-1.0}}]

RULES:
- informational keywords (how to, benefits, recipes, what is) = relevance < 0.3 ALWAYS
- keywords not containing any pillar word = relevance < 0.5
- buyer-ready keywords (buy, price, wholesale, supplier) = relevance > 0.8
- keywords containing target locations listed above = relevance boost +0.1
- keywords matching business locations (origin/source) = relevance boost +0.1 (strong supplier/source signal)
- keywords matching cultural context (e.g. ayurvedic, halal) = relevance boost +0.1 if business-relevant"""

# ── Phase 4b: Cluster Naming ─────────────────────────────────────────────

CLUSTER_NAME_SYSTEM = (
    "You are an SEO content strategist. "
    "Return ONLY a 2-4 word cluster name, no explanation."
)

CLUSTER_NAME_USER = """Business: {business_context}

Given these semantically similar commercial keywords:
{keywords_list}

Name this cluster with 2-4 words that describe their commercial theme.
Use terminology specific to this business and industry.
Examples: "Wholesale Bulk Orders", "Price Comparison", "Local Suppliers", "Online Purchase".

Cluster name:"""

# ── Batch Cluster Naming (names up to 10 clusters in ONE AI call) ──────────

BATCH_CLUSTER_NAME_SYSTEM = (
    "You are an SEO content strategist. Name keyword clusters concisely. "
    "Output ONLY valid JSON, no markdown fences."
)

BATCH_CLUSTER_NAME_USER = """Business: {business_context}

Name each of these keyword clusters with a 2-4 word commercial theme.

{clusters_block}

Return ONLY this JSON (one entry per cluster, same order):
{{
  "names": ["Cluster 1 Name", "Cluster 2 Name", ...]
}}

Rules:
- 2-4 words per name, Title Case
- Use terminology relevant to this specific business and industry
- Describe the commercial theme, not the product
- Examples: "Wholesale Bulk Orders", "Price Comparison", "Local Suppliers", "Online Purchase", "Farm Direct Buy"
- Never use generic names like "Cluster" or "General" """

# ── Multi-dimension expansion (all dims in ONE AI call per seed) ─────────────

MULTI_DIM_EXPAND_SYSTEM = (
    "You are an SEO content strategy specialist who generates authentic, diverse search queries. "
    "You NEVER produce template substitutions. Every question must be genuinely unique. "
    "Output ONLY valid JSON with no markdown fences."
)

MULTI_DIM_EXPAND_USER = """BUSINESS: {business_context}

BASE QUESTION / SEED:
{base_question}

EXPAND ACROSS THESE DIMENSIONS (generate {per_dim} variations per dimension value):
{dimensions_block}

CRITICAL RULES — read carefully:
1. Each question must sound like a REAL Google search query a human would type
2. DO NOT just insert/append a dimension value into the base question
   BAD: "Kerala spices for cooking in Mumbai" (just appended city)
   BAD: "Benefits of spices for home cooks" / "Benefits of spices for restaurants" (same template, swapped audience)
   BAD: "How to store spices in 100gm" / "How to store spices in 200gm" (trivial size swap)
3. Each question must explore a DIFFERENT angle, intent, or topic
4. Vary sentence structure — mix how-to, comparisons, lists, buying guides, vs-comparisons, tips
5. Questions must be self-contained and meaningful on their own
6. SKIP dimension values that don't produce genuinely different questions
7. Quality over quantity — 5 great questions beat 20 template swaps

GOOD examples:
- "Which Kerala spices pair best with South Indian breakfast dishes?"
- "Bulk whole spice suppliers in Mumbai with farm-to-table Kerala sourcing"
- "Restaurant chef tips: storing whole spices vs ground spices for maximum flavor"
- "Why is Cardamom from Idukki considered premium for desserts?"

Return ONLY this JSON:
{{
  "expanded_questions": [
    {{
      "question": "genuine search query here",
      "dimension_applied": "geo",
      "dimension_value": "Kerala"
    }}
  ]
}}"""

# ── AI Validation prompt (post-expansion quality filter) ─────────────────

VALIDATE_QUESTIONS_SYSTEM = (
    "You are a strict SEO quality auditor. You evaluate whether generated questions "
    "are authentic search queries that real people would type into Google. "
    "Output ONLY valid JSON with no markdown fences."
)

VALIDATE_QUESTIONS_USER = """BUSINESS: {business_context}

Evaluate each question below. For EACH question, decide:
- KEEP: authentic, specific, someone would actually search this on Google
- REJECT: template substitution, unnatural phrasing, nonsensical, too generic, or duplicate intent of another question in the list

A question is a REJECT if:
- It reads like "[base phrase] + [city/size/audience appended]" (template swap)
- Nobody would realistically type it into Google
- It's nearly identical in meaning to another question (just reworded)
- It contains brand name stuffed unnaturally
- It's a product size query that isn't a real search pattern (e.g. "300gm Kerala spices for cooking")

QUESTIONS TO EVALUATE:
{questions_json}

Return ONLY this JSON:
{{
  "results": [
    {{
      "id": "question_id",
      "verdict": "KEEP" or "REJECT",
      "reason": "brief reason"
    }}
  ]
}}"""

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
USP: {usp}
Target locations: {target_locations}
Languages: {languages}
Cultural context: {cultural_context}
Customer voice: {customer_voice}
Top keywords ({count}): {top_keywords}
Clusters: {clusters}
Audience: {audience}
Geo: {geo_scope}

Generate a 90-day SEO content strategy as JSON:
{{
  "strategy_summary": {{
    "headline": "one-sentence strategy",
    "biggest_opportunity": "underserved keyword gap or persona",
    "why_we_win": "specific competitive advantage based on USP and cultural positioning"
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
          "page_type": "product_page|category_page|blog_page|b2b_page|local_page",
          "target_location": "specific location if geo-targeted, or empty"
        }}
      ]
    }}
  ],
  "quick_wins": ["keywords with low KD and high buyer intent"],
  "content_gaps": ["topics competitors cover that we don't"],
  "geo_content_plan": "strategy for location-specific content across target locations",
  "multilingual_plan": "how to target content in specified languages",
  "customer_voice_content": ["content ideas inspired by actual customer language and reviews"]
}}"""


# ── Business Context README Prompt ──────────────────────────────────────────

BIZ_README_SYSTEM = (
    "You are a senior business intelligence analyst writing the definitive business context document. "
    "This document is the HEART of an SEO keyword strategy system — every keyword, content piece, "
    "and strategy decision downstream depends on the quality of this analysis. "
    "Write in clear, structured markdown. Be SPECIFIC — use actual product names, regions, grades, "
    "and numbers. Never be generic. This is not a summary — it's an intelligence briefing."
)

BIZ_README_USER = """Write a comprehensive BUSINESS INTELLIGENCE README for the SEO keyword strategy pipeline.
This document will be read by AI agents in later phases to generate keywords, content, and strategy.
The richer and more specific this document is, the better the entire system performs.

BUSINESS PROFILE DATA:
{profile_json}

DEEP BUSINESS INTELLIGENCE (from website crawl + competitor analysis + AI synthesis):
{knowledge_json}

SEO STRATEGY DATA:
{strategy_json}

WEBSITE PAGES ANALYZED:
{pages_summary}

COMPETITOR DATA:
{competitors_summary}

Write a COMPREHENSIVE markdown document with ALL of these sections. Be detailed and specific:

# Business Intelligence README

## 1. Business Identity & Positioning
- Brand name, legal entity, positioning (premium/budget/organic/D2C/etc.)
- Core value proposition — what makes them unique
- Brand story — the narrative behind the business
- Trust signals — certifications, sourcing claims, heritage
- Key differentiators from competitors

## 2. Geographic & Source Intelligence
- Production/sourcing region (specific locations, not just country)
- Why this region matters for SEO (terroir, reputation, search demand)
- Selling market/geo scope
- Micro-regions that create keyword opportunities
- Export potential and international keyword angles

## 3. Product Intelligence (Structured)
- Product categories (pillars) with specific variants
- Product attributes table: grade, origin, format, packaging → keyword impact
- Quality markers that generate trust-based keywords
- Product comparison angles (X vs Y)

## 4. Supply Chain & Trust Layer
- Sourcing model (farm-direct, manufacturer, importer)
- Processing method (minimal, hand-harvested, chemical-free)
- How freshness/quality is maintained
- Keywords this enables (farm direct, non-processed, fresh, etc.)

## 5. Target Customer Intelligence (ICP)
- B2C segments with buying triggers and keyword patterns
- B2B segments with buying triggers and keyword patterns  
- Audience pain points this business solves
- Behavioral insights per segment

## 6. Commercial Intent Mapping
- High-intent modifiers detected
- Transactional keyword patterns
- Comparison keyword patterns  
- Geo-intent patterns
- Audience × product patterns

## 7. Strategic Keyword Clusters
- Origin-specific cluster (geo + product combos)
- Quality-driven cluster (grade + quality markers)
- User-intent cluster (buy/price/wholesale)
- Niche/variety cluster (specific variants, comparisons)
- B2B/wholesale cluster

## 8. Content Opportunity Engine
- Commercial content ideas (pages that convert)
- Comparison content (high-ROI X vs Y articles)
- Buyer guides (pre-purchase research that converts)
- Authority content (geo/quality stories that build trust)

## 9. Competitive Landscape
- Who they compete against
- Our advantages
- Gaps to exploit
- Counter-strategy

## 10. SEO Execution Notes
- Priority keyword types (purchase > commercial > informational)
- Negative scope (topics to ALWAYS exclude)
- Pillar confirmation checklist
- Content calendar seeds
- Quick wins for immediate impact

CRITICAL: Be SPECIFIC to THIS business. Use actual product names, regions, grades, prices.
Every section should generate keyword and content ideas for the downstream pipeline."""


# ── Business Intelligence Stage Prompts ──────────────────────────────────────

BIZ_PAGE_CLASSIFY_SYSTEM = (
    "You are an SEO page analyst. Classify webpages and extract key SEO signals. "
    "Output ONLY valid JSON, no markdown fences."
)

BIZ_PAGE_CLASSIFY_USER = """Classify this webpage for SEO analysis.

URL: {url}

CONTENT (first 2500 chars):
{content}

Return ONLY valid JSON:
{{
  "page_type": "homepage|landing_page|product_page|pillar_page|blog_post|other",
  "primary_topic": "main topic in 3-6 words",
  "search_intent": "informational|commercial|transactional|navigational",
  "target_keyword": "most likely primary keyword targeted on this page",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "audience": "who this page targets (1 sentence)",
  "funnel_stage": "TOFU|MOFU|BOFU|none",
  "value_proposition": "what they are offering (1 sentence)"
}}"""

BIZ_COMPETITOR_PAGES_SYSTEM = (
    "You are a competitive intelligence analyst for SEO. "
    "Analyze competitor pages and extract keyword and strategy data. "
    "Output ONLY valid JSON."
)

BIZ_COMPETITOR_STRATEGY_USER = """Analyze this competitor's complete SEO strategy.

COMPETITOR DOMAIN: {domain}

PAGES ANALYZED (type / topic / keywords):
{pages_summary}

ALL KEYWORDS FOUND: {all_keywords}

Return ONLY valid JSON:
{{
  "target_audience": "who they primarily target",
  "business_model": "B2B|B2C|both",
  "content_strategy": "blog-heavy|landing-heavy|mixed|thin",
  "funnel_coverage": {{
    "TOFU": "weak|medium|strong",
    "MOFU": "weak|medium|strong",
    "BOFU": "weak|medium|strong"
  }},
  "tone": "professional|casual|sales-heavy|educational|technical",
  "top_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "strengths": ["strength1", "strength2"],
  "weaknesses": ["weakness1", "weakness2"],
  "missed_opportunities": ["opportunity1", "opportunity2"],
  "keyword_patterns": ["pattern1 (e.g. buy X online)", "pattern2"]
}}"""

BIZ_KNOWLEDGE_SYNTHESIS_SYSTEM = (
    "You are a senior business intelligence analyst and SEO strategist. "
    "Your job is to deeply understand a business — its identity, positioning, geographic advantage, "
    "product intelligence, supply chain model, audience segments, and commercial opportunities. "
    "Extract EVERYTHING that can generate keywords and content ideas. "
    "Output ONLY valid JSON, no markdown fences."
)

BIZ_KNOWLEDGE_SYNTHESIS_USER = """Perform a DEEP business intelligence analysis from all available data.
Go beyond surface-level summaries. Extract the SOUL of this business.

BUSINESS PROFILE:
{business_profile}

WEBSITE PAGE ANALYSIS:
{website_analysis}

COMPETITOR INSIGHTS:
{competitor_insights}

USER GOALS: {goals}
PRICING MODEL: {pricing}
USPs: {usps}
TARGET AUDIENCE SEGMENTS: {audience_segments}

Return ONLY valid JSON with ALL of these sections:
{{
  "business_identity": {{
    "name": "brand name",
    "positioning": "premium|budget|mid-range|artisan|organic|farm-direct|D2C|wholesale",
    "value_proposition": "1-2 sentence core value proposition",
    "brand_story": "2-3 sentence brand narrative — what makes them unique",
    "trust_signals": ["origin sourcing", "certifications", "processing method", "farm-direct", "no middlemen"],
    "differentiators": ["what sets them apart from competitors — be specific"]
  }},
  "geographic_intelligence": {{
    "production_region": "where products are sourced/made (city, state, country)",
    "selling_region": "primary market (country/region)",
    "geo_seo_advantage": "why their location is an SEO goldmine (e.g. Kerala = spice capital)",
    "micro_regions": ["specific sub-regions, districts, or terroirs mentioned"],
    "export_potential": true,
    "geo_keyword_patterns": ["region + product patterns that generate search demand"]
  }},
  "product_intelligence": {{
    "product_categories": ["main product categories/pillars"],
    "product_attributes": [
      {{"attribute": "grade/size/type", "value": "e.g. 8mm", "keyword_impact": "high purchase intent"}},
      {{"attribute": "origin", "value": "e.g. Adimali", "keyword_impact": "geo-intent keywords"}},
      {{"attribute": "format", "value": "e.g. raw whole, ground, combo", "keyword_impact": "product variant keywords"}},
      {{"attribute": "packaging", "value": "e.g. 100g, 200g, 500g, 1kg", "keyword_impact": "transactional keywords"}}
    ],
    "quality_markers": ["specific quality indicators: non-oil extracted, hand-harvested, chemical-free, etc."],
    "product_comparison_angles": ["e.g. Ceylon vs Cassia, Bold vs Regular — generates comparison content"]
  }},
  "supply_chain_insight": {{
    "sourcing_model": "farm-direct|aggregator|manufacturer|importer|reseller",
    "processing_type": "minimal|standard|heavy — and specifics",
    "freshness_angle": "how they emphasize freshness/quality retention",
    "keyword_opportunities": ["farm direct spices", "fresh cardamom online", "non processed spices"]
  }},
  "audience_segmentation": {{
    "b2c_segments": [
      {{"segment": "home cooks", "buying_trigger": "quality & aroma", "keyword_pattern": "premium spices online"}},
      {{"segment": "health buyers", "buying_trigger": "purity", "keyword_pattern": "chemical free spices"}}
    ],
    "b2b_segments": [
      {{"segment": "restaurants", "buying_trigger": "bulk pricing", "keyword_pattern": "bulk cardamom supplier"}},
      {{"segment": "bakers", "buying_trigger": "flavor consistency", "keyword_pattern": "best cinnamon for baking"}}
    ],
    "pain_points": ["what problems does the audience have that this business solves"]
  }},
  "commercial_intent_signals": {{
    "high_intent_modifiers": ["buy", "price", "bulk", "wholesale", "online", "supplier", "near me"],
    "detected_on_site": ["commercial signals found in website content"],
    "transactional_patterns": ["buy + product", "product + price india", "bulk product supplier"],
    "comparison_patterns": ["product A vs product B", "best product type"],
    "geo_patterns": ["region + product", "product + in + city"]
  }},
  "content_opportunity_engine": {{
    "commercial_content_ideas": [
      {{"title": "title of commercial content piece", "angle": "why it converts", "target_keyword": "primary keyword", "page_type": "landing|pillar|comparison|buyer-guide"}}
    ],
    "comparison_content": [
      {{"title": "X vs Y: Which Should You Buy?", "keywords": ["ceylon vs cassia", "ceylon cinnamon online"]}}
    ],
    "buyer_guides": [
      {{"title": "How to Choose Premium X (Buyer Guide)", "keywords": ["how to choose cardamom", "best cardamom grade"]}}
    ],
    "authority_content": [
      {{"title": "Why Region X Produces the Best Y", "angle": "geo-authority + education that converts"}}
    ]
  }},
  "strategic_keyword_clusters": {{
    "origin_specific": {{"primary": ["Idukki Cardamom"], "modifiers": ["high-altitude Kerala spices"]}},
    "quality_driven": {{"primary": ["non-oil extracted"], "modifiers": ["export quality 8mm"]}},
    "user_intent": {{"primary": ["buy spices online India"], "modifiers": ["farm-direct price"]}},
    "niche_variety": {{"primary": ["Karimunda Pepper"], "modifiers": ["premium Cassia vs Ceylon"]}},
    "b2b_wholesale": {{"primary": ["bulk spices supplier"], "modifiers": ["wholesale pepper India"]}}
  }},
  "competitive_landscape": {{
    "competing_against": ["types of competitors — commodity sellers, D2C brands, marketplaces"],
    "our_advantages": ["what we do better"],
    "gaps_to_exploit": ["keywords/content competitors miss"],
    "counter_strategy": "1-2 sentence plan to outrank competitors"
  }},
  "quick_wins": ["immediate high-impact actions — be specific with keyword + page suggestions"],
  "primary_seo_opportunity": "the single biggest untapped opportunity"
}}

CRITICAL RULES:
- Be SPECIFIC to this business, not generic. Use actual product names, regions, grades.
- Every insight should map to keyword opportunities or content ideas.
- Think like someone trying to SELL products, not just describe them.
- Extract signals from website page content, not just the profile.
- If data is missing, infer intelligently from what IS available."""

BIZ_SEO_STRATEGY_SYSTEM = (
    "You are a senior SEO consultant with deep expertise in ecommerce, D2C, and content strategy. "
    "Create a prioritized, actionable 30-60-90 day SEO strategy that turns business intelligence into revenue. "
    "Every recommendation must be specific and executable. Output ONLY valid JSON."
)

BIZ_SEO_STRATEGY_USER = """Create a comprehensive, revenue-focused SEO action plan.

BUSINESS INTELLIGENCE (DEEP ANALYSIS):
{knowledge_summary}

BUSINESS TYPE: {business_type}
PRIMARY GOALS: {goals}
DOMAIN/UNIVERSE: {universe}

Return ONLY valid JSON:
{{
  "executive_summary": "3-sentence strategy overview — what to do, why, expected outcome",
  "priority_keywords": [
    {{"keyword": "X", "intent": "transactional|commercial", "page_type": "landing|pillar|blog|comparison|buyer-guide", "priority": "high|medium", "why": "specific reason this keyword drives revenue", "estimated_difficulty": "low|medium|high"}}
  ],
  "recommended_pages": [
    {{"page_type": "landing|blog|pillar|comparison|buyer-guide", "topic": "X", "target_keyword": "Y", "secondary_keywords": ["kw1","kw2"], "funnel": "BOFU|MOFU|TOFU", "estimated_impact": "high|medium", "content_angle": "specific angle that differentiates from competitors"}}
  ],
  "keyword_clusters": [
    {{"cluster_name": "X", "theme": "Y", "keywords": ["kw1","kw2","kw3"], "content_approach": "how to create content for this cluster"}}
  ],
  "30_day_actions": ["very specific action with target keyword/page"],
  "60_day_actions": ["specific action"],
  "90_day_actions": ["specific action for sustained growth"],
  "quick_wins": ["specific keyword + action that can rank in weeks"],
  "content_calendar_seeds": [
    {{"week": 1, "topic": "X", "keyword": "Y", "page_type": "Z", "why_now": "reason for priority"}}
  ],
  "internal_linking_strategy": "how to connect content pieces for pillar authority",
  "avoid": ["specific mistake with explanation"],
  "competitor_counter_strategy": "2-3 sentence plan to systematically outrank competitors"
}}"""


# ── v2 Keyword Brain Prompts ────────────────────────────────────────────────

# Role: Controlled Expander — commercial keywords
V2_EXPAND_COMMERCIAL_SYSTEM = (
    "You are an SEO keyword specialist. Generate ONLY commercial and transactional keyword variations. "
    "One keyword per line, no numbering, no bullets, no explanation."
)

V2_EXPAND_COMMERCIAL_USER = """Business universe: {universe}
Pillar product: {pillar}
Core search term: {core_term}
Modifiers: {modifiers}
Target locations: {target_locations}
Cultural context: {cultural_context}
USP: {usp}
Customer voice: {customer_voice}
Target count: {count}

Generate {count} COMMERCIAL/TRANSACTIONAL keyword variations for this pillar.

Categories to cover:
- Buy/order/shop: "buy {core_term}", "order {core_term} online"
- Price/rate: "{core_term} price", "{core_term} cost per kg"
- Wholesale/bulk: "{core_term} wholesale", "{core_term} bulk price"
- Supplier/source: "{core_term} supplier india", "{core_term} manufacturer"
- Product variants: different sizes (100g, 500g, 1kg), grades, types
- B2B/trade: "{core_term} wholesale dealer", "{core_term} trade price"
- Comparison: "best {core_term}", "{core_term} vs [competitor]", "{core_term} brands"
- Location-specific: use EACH target location (e.g. "{core_term} [location]", "buy {core_term} in [location]")
- Cultural/niche: use cultural context to generate niche commercial keywords
- USP-driven: combine USP angles with {core_term} (e.g. "organic {core_term}", "farm direct {core_term}")
- Customer language: use real phrases from customer voice to inspire natural buying keywords

ONLY commercial/transactional intent. No recipes, benefits, how-to, health info.
One keyword per line:"""

# Role: Controlled Expander — informational keywords
V2_EXPAND_INFORMATIONAL_SYSTEM = (
    "You are an SEO content strategist. Generate informational keyword variations "
    "that build topical authority and attract top-of-funnel traffic. "
    "One keyword per line, no numbering, no bullets, no explanation."
)

V2_EXPAND_INFORMATIONAL_USER = """Business universe: {universe}
Pillar product: {pillar}
Core search term: {core_term}
Target locations: {target_locations}
Cultural context: {cultural_context}
Customer voice: {customer_voice}
Target count: {count}

Generate {count} INFORMATIONAL keyword variations for this pillar.
These keywords build topical authority and attract research-stage visitors.

Categories to cover:
- What/how guides: "what is {core_term}", "how to choose {core_term}"
- Comparison guides: "{core_term} types explained", "{core_term} vs [alternative] comparison guide"
- Buying guides: "{core_term} buying guide", "how to pick the right {core_term}"
- Industry knowledge: "{core_term} grades", "{core_term} processing methods"
- Use cases: "{core_term} for cooking", "{core_term} industrial uses"
- FAQ content: "{core_term} shelf life", "how to store {core_term}"
- Regional knowledge: use target locations for region-specific informational content
- Cultural relevance: use cultural context for culturally specific questions and guides
- Customer questions: use customer voice to identify real questions customers ask about {core_term}

ONLY informational/educational intent. Must relate to the business selling this product.
Do NOT include: recipe instructions, health/medical benefits, home remedies, ayurvedic uses.
One keyword per line:"""

# Role: Controlled Expander — navigational keywords
V2_EXPAND_NAVIGATIONAL_SYSTEM = (
    "You are an SEO keyword specialist. Generate navigational and local-intent keyword variations. "
    "One keyword per line, no numbering, no bullets, no explanation."
)

V2_EXPAND_NAVIGATIONAL_USER = """Business universe: {universe}
Pillar product: {pillar}
Core search term: {core_term}
Geo scope: {geo}
Business locations: {business_locations}
Target locations: {target_locations}
Target count: {count}

Generate {count} NAVIGATIONAL and LOCAL keyword variations for this pillar.

Categories to cover:
- Near me: "{core_term} near me", "{core_term} shop near me"
- Location specific: generate for EACH business location AND target location listed above
  e.g. "{core_term} [location]", "{core_term} store [location]", "buy {core_term} in [location]"
- Brand navigational: "best {core_term} brand", "top {core_term} companies"
- Local supplier: "{core_term} supplier [location]", "{core_term} wholesale [location]"
- Market/bazaar: "{core_term} market", "{core_term} mandi", "{core_term} dealers [location]"

IMPORTANT: Generate location-specific keywords for EVERY location listed in business locations and target locations.
ONLY navigational/local intent.
One keyword per line:"""

# Role: Intent Analyzer — classify keywords
V2_VALIDATE_SYSTEM = (
    "You are an SEO keyword analyst. Evaluate keywords for business relevance across ALL intents. "
    "Return ONLY a valid JSON array, no explanation."
)

V2_VALIDATE_USER = """Business: {universe}
Pillars: {pillars_str}
Hard-reject patterns: {negative_scope_str}
Target locations: {target_locations}
Business locations (where the business operates/sources from): {business_locations}
Cultural context: {cultural_context}

Keywords to evaluate:
{keywords_list}

Return JSON array — one object per keyword:
[{{"keyword": "...", "relevance": 0.0-1.0, "intent": "purchase|transactional|commercial|comparison|local|informational|navigational", "buyer_readiness": 0.0-1.0}}]

RULES:
- ALL intent types are valid — do NOT reject informational keywords
- Relevance measures how well the keyword serves this business
- Buyer-ready keywords (buy, price, wholesale) → relevance > 0.8, buyer_readiness > 0.7
- Informational keywords about the product → relevance 0.5-0.7
- Keywords completely unrelated to the business → relevance < 0.3
- Hard-reject patterns always get relevance 0.0
- Keywords containing target locations = relevance boost +0.1
- Keywords matching business locations (origin/source) = relevance boost +0.1 (strong B2B/supplier signal)
- Keywords matching cultural context (e.g. ayurvedic, halal) = relevance boost +0.1 if business-relevant"""

# Role: Cluster Organizer — validate cluster boundaries
V2_CLUSTER_VALIDATE_SYSTEM = (
    "You are an SEO content strategist. Evaluate whether keywords belong together in a cluster. "
    "Return ONLY valid JSON."
)

V2_CLUSTER_VALIDATE_USER = """These keywords are currently in one cluster named "{cluster_name}":
{keywords_list}

Should they all be in the same cluster? Are there any that should be separated?

Return JSON:
{{
  "valid": true,
  "name": "better 2-4 word name if current is poor, else same name",
  "outliers": ["keyword that doesn't belong", "another outlier"],
  "sub_clusters": []
}}

If the cluster should be split:
{{
  "valid": false,
  "name": "{cluster_name}",
  "outliers": [],
  "sub_clusters": [
    {{"name": "Sub Cluster A", "keywords": ["kw1", "kw2"]}},
    {{"name": "Sub Cluster B", "keywords": ["kw3", "kw4"]}}
  ]
}}"""

# Role: Strategist — enhanced strategy with relationship insights
V2_STRATEGY_SYSTEM = (
    "You are a senior SEO strategist. Generate a strategy that leverages keyword relationships "
    "and content clusters for maximum impact. Output ONLY valid JSON."
)

V2_STRATEGY_USER = """Business: {universe} ({business_type})
Pillars: {pillars}
USP: {usp}
Target locations: {target_locations}
Business locations: {business_locations}
Languages: {languages}
Cultural context: {cultural_context}
Customer reviews summary: {customer_voice}
Top keywords ({kw_count}): {top_keywords}
Clusters ({cluster_count}): {clusters}
Bridge keywords (shared across pillars): {bridge_keywords}
Relationship stats: {rel_stats}
Link suggestions: {link_count} internal links
Calendar: {calendar_range}
Audience: {audience}
Geo: {geo_scope}

Generate a comprehensive 90-day SEO strategy as JSON:
{{
  "executive_summary": "3-sentence strategy overview",
  "pillar_strategies": [
    {{
      "pillar": "name",
      "priority": "high|medium|low",
      "keyword_count": 100,
      "top_opportunity": "biggest keyword gap",
      "content_approach": "how to dominate this pillar",
      "bridge_leverage": "how shared keywords connect to other pillars",
      "geo_strategy": "location-specific tactics using target locations",
      "cultural_angle": "how to leverage cultural context for this pillar"
    }}
  ],
  "quick_wins": [
    {{"keyword": "...", "action": "create|optimize", "page_type": "...", "expected_impact": "high|medium"}}
  ],
  "content_priorities": [
    {{"week": 1, "pillar": "...", "topic": "...", "keyword": "...", "reason": "..."}}
  ],
  "geo_content_plan": "strategy for creating location-specific content for each target location",
  "multilingual_plan": "strategy for targeting content in specified languages",
  "link_building_plan": "how to use internal links for pillar reinforcement",
  "competitive_gaps": ["gap1", "gap2"],
  "customer_voice_content": ["content ideas inspired by actual customer reviews and language"],
  "timeline": {{
    "month_1": "focus areas",
    "month_2": "focus areas",
    "month_3": "focus areas"
  }}
}}"""

# ── Strategy v2 Sub-Module Prompts ───────────────────────────────────────────

STRATEGY_V2_SYSTEM = (
    "You are a senior SEO strategist. "
    "Output ONLY valid JSON with no markdown fences or explanation text."
)

# Module 2A — Business Analysis
STRATEGY_2A_USER = """Analyze this business and produce a structured business intelligence summary.

BUSINESS PROFILE:
{profile_json}

BUSINESS INTEL (website crawl + competitor analysis):
{biz_intel_json}

WEBSITE PAGES ({page_count} analyzed):
{pages_summary}

VALIDATED KEYWORDS: {kw_count} keywords across pillars: {pillars}

Return ONLY this JSON structure:
{{
  "business_type": "...",
  "core_offering": "...",
  "value_proposition": "one clear sentence",
  "target_intent": "online_sales|lead_gen|brand_awareness|support",
  "pricing_position": "budget|mid-range|premium",
  "key_differentiators": ["..."],
  "audience_segments": [
    {{"segment": "...", "primary_driver": "...", "estimated_share": "..."}}
  ],
  "content_authority_topics": ["topics where this biz has genuine expertise"],
  "geo_footprint": {{"primary": "...", "secondary": [...]}},
  "business_weaknesses": ["gaps that content can address"],
  "competitor_gaps": ["topics competitors rank for that we should target"]
}}"""

# Module 2B — Keyword Intelligence (uses full keyword set)
STRATEGY_2B_USER = """Analyze the complete keyword dataset and produce strategic intelligence.

BUSINESS: {universe} | PILLARS: {pillars}

KEYWORD SUMMARY ({total_kw} total keywords):
By intent:
{intent_breakdown}

By pillar:
{pillar_breakdown}

Top 50 by score:
{top_50_kws}

Clusters ({cluster_count}):
{cluster_summary}

Return ONLY this JSON structure:
{{
  "strongest_pillar": "...",
  "weakest_pillar": "...",
  "dominant_intent": "informational|commercial|transactional",
  "keyword_depth_assessment": "shallow|moderate|deep",
  "high_value_opportunities": [
    {{"keyword": "...", "pillar": "...", "why": "..."}}
  ],
  "intent_gaps": ["intent types that are underrepresented"],
  "cluster_insights": [
    {{"cluster": "...", "strength": "strong|moderate|weak", "action": "..."}}
  ],
  "recommended_kw_focus": ["top 10 keywords to prioritize for content creation"],
  "long_tail_potential": "high|medium|low",
  "notes": "any important observations"
}}"""

# Module 2C — Full Strategy Builder (uses 2A + 2B outputs)
STRATEGY_2C_USER = """Generate a comprehensive SEO content strategy using this intelligence.

BUSINESS ANALYSIS (Module 2A):
{module_2a_json}

KEYWORD INTELLIGENCE (Module 2B):
{module_2b_json}

CONTENT PARAMETERS:
- Publishing cadence: {blogs_per_week} articles/week for {duration_weeks} weeks ({total_articles} total)
- Content mix: {content_mix}
- Publishing days: {cadence_str}
{extra_guidance}

Return ONLY this JSON structure:
{{
  "strategy_summary": {{
    "headline": "one compelling strategy sentence",
    "biggest_opportunity": "the single most important gap to capture",
    "why_we_win": "specific competitive advantage"
  }},
  "priority_pillars": [
    {{
      "pillar": "...",
      "rank": 1,
      "rationale": "...",
      "kw_count": 0,
      "primary_intent": "...",
      "content_angle": "how to approach this pillar"
    }}
  ],
  "quick_wins": [
    {{"keyword": "...", "action": "create|optimize", "page_type": "...", "reason": "..."}}
  ],
  "weekly_plan": [
    {{
      "week": 1,
      "focus_pillar": "...",
      "articles": [
        {{
          "title": "...",
          "primary_keyword": "...",
          "intent": "informational|commercial|transactional",
          "page_type": "blog_page|product_page|category_page|landing_page"
        }}
      ]
    }}
  ],
  "link_building_plan": "internal linking priorities and strategy",
  "competitive_gaps": ["topic areas competitors dominate that we must address"],
  "content_gaps": ["topics completely missing from our current coverage"],
  "timeline": {{
    "month_1": "...",
    "month_2": "...",
    "month_3": "..."
  }}
}}"""

# Module 2D — Action Mapping (derives execution actions from strategy)
STRATEGY_2D_USER = """Map this SEO strategy to concrete execution actions.

STRATEGY (Module 2C):
{module_2c_json}

CURRENT KEYWORD SCORES (sample):
{kw_score_sample}

CURRENT CLUSTERS:
{cluster_list}

Map strategy decisions to execution actions. Return ONLY this JSON:
{{
  "keyword_boosts": [
    {{"keyword": "...", "boost_reason": "...", "new_priority": "high|medium|low"}}
  ],
  "cluster_reorder": [
    {{"cluster": "...", "new_rank": 0, "reason": "..."}}
  ],
  "calendar_priority": [
    {{"title": "...", "move_to_week": 0, "reason": "..."}}
  ],
  "immediate_actions": [
    {{"action": "...", "target": "...", "expected_impact": "..."}}
  ]
}}"""

# ── Question Intelligence Prompts (Phase 3) ───────────────────────────────────

QUESTION_MODULE_SYSTEM = (
    "You are an expert SEO strategist and user search behavior analyst specialising in {module_role}. "
    "Output ONLY valid JSON with no markdown fences or explanation text."
)

QUESTION_MODULE_USER = """BUSINESS CONTEXT:
{business_context}

{module_specific_data}

TASK: Generate REAL user search queries that people actually type into Google, related to this business.
Focus area: {module_focus}
Dimensions to cover: {dimension_list}
Maximum: {max_questions} questions

CRITICAL RULES — every question MUST:
1. Be a real search query someone types into Google — treat it like a keyword
2. Start with one of: What, How, Which, Where, Why, Best, Top, Can, Do, Is, Are, Buy
3. Be specific to THIS business's products, location, and audience — never generic
4. Be content-creation-ready (can become a blog title or landing page directly)
5. Be expandable across location, use case, or audience type

STRICTLY REJECT any item that:
- Is a business strategy statement (e.g. "Optimizing pricing strategy", "Leveraging reviews")
- Is an internal business question (e.g. "How can we improve...")
- Reads like a management consulting insight (e.g. "Understanding purchasing decisions of bakers")
- Cannot be turned into a blog post or landing page
- Is a generic question not tied to this specific business, product, or location

GOOD examples for a spice business:
✓ "How to use cardamom in Kerala chicken biriyani?"
✓ "Where to buy organic Kerala spices online in India?"
✓ "Which cardamom is best for baking cakes?"
✓ "What spices are used in Hyderabadi biriyani?"
✓ "Best organic cardamom brands in India 2024"
✓ "How to store cardamom to keep it fresh?"

BAD examples (REJECT THESE):
✗ "Optimizing pricing strategy to balance profitability" — business strategy, not a search query
✗ "Understanding purchasing decisions of bakers" — not a search query
✗ "Leveraging reviews and ratings" — management insight, not searchable
✗ "What certifications can Indian Organic Spices pursue?" — internal business question

Return ONLY this JSON:
{{
  "questions": [
    {{
      "question": "real user search query here",
      "category": "buying|usage|regional|comparison|problem|informational",
      "why_it_matters": "why users search this and how it drives business value",
      "data_source": "keyword|competitor|biz_intel|ai_inference",
      "priority": "high|medium|low"
    }}
  ]
}}"""

# ── Enrichment Prompt (Phase 5) ───────────────────────────────────────────────

ENRICHMENT_SYSTEM = (
    "You are an SEO and content analyst. "
    "Output ONLY valid JSON with no markdown fences."
)

ENRICHMENT_USER = """BUSINESS: {business_context}

Analyse these questions and add structured intelligence metadata.

QUESTIONS (batch of {batch_size}):
{questions_json}

For each question return:
- intent: informational|commercial|transactional|navigational
- funnel_stage: TOFU|MOFU|BOFU
- audience_segment: who would search this
- geo_relevance: local|regional|national|global
- business_relevance: 0-100 score (how directly relevant to this business)
- content_type: blog|guide|comparison|landing-page|faq|video-script
- effort: low|medium|high

Return ONLY this JSON:
{{
  "enriched": [
    {{
      "id": "",
      "intent": "",
      "funnel_stage": "",
      "audience_segment": "",
      "geo_relevance": "",
      "business_relevance": 0,
      "content_type": "",
      "effort": ""
    }}
  ]
}}"""

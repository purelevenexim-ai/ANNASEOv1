"""
KW2 Prompt Test Data — sample variables for live-testing each prompt in Prompt Studio.

Keeps data compact so it fits within Ollama's 4096-token context window.
Uses a fictional "Sunrise Spices" Indian spice ecommerce business.
"""

# Map each user prompt → its system prompt key
SYSTEM_PROMPT_MAP = {
    "strategy_2a": "strategy_v2_system",
    "strategy_2b": "strategy_v2_system",
    "strategy_2c": "strategy_v2_system",
    "strategy_2d": "strategy_v2_system",
    "question_module": "question_module_system",
    "enrichment": "enrichment_system",
    "title_generation": "title_system",
}

# Default sample data per prompt key — used to .format() the template
KW2_SAMPLE_DATA = {
    # ── Strategy Phase (2) ─────────────────────────────────────────

    "strategy_v2_system": {
        # System prompts have no variables; we provide a test user message
        "_test_user_prompt": "Briefly describe your role and how you would approach building an SEO strategy for an Indian spice ecommerce business."
    },

    "strategy_2a": {
        "profile_json": '{"universe":"Indian Spices","pillars":["Cardamom","Black Pepper","Turmeric"],"business_type":"D2C Ecommerce","geo_scope":"India","audience":["home cooks","restaurants","wholesalers"]}',
        "biz_intel_json": '{"strengths":["Farm-direct Kerala sourcing","Premium 8mm cardamom"],"competitors":["SpiceJunction","MasalaMart"],"gaps":["No bulk pricing page","Missing B2B landing pages"]}',
        "pages_summary": "Homepage: D2C spice brand | Products: Cardamom, Pepper, Turmeric | About: Family farm in Idukki, Kerala",
        "page_count": "3",
        "pillars": "Cardamom, Black Pepper, Turmeric",
        "kw_count": "120",
    },

    "strategy_2b": {
        "universe": "Indian Spices",
        "pillars": "Cardamom, Black Pepper, Turmeric",
        "total_kw": "120",
        "intent_breakdown": "Commercial: 45 | Transactional: 35 | Informational: 25 | Local: 15",
        "pillar_breakdown": "Cardamom: 50 | Black Pepper: 40 | Turmeric: 30",
        "top_50_kws": "buy cardamom online, cardamom price per kg, bulk black pepper supplier, organic turmeric powder, Kerala spices wholesale, cardamom 8mm price, black pepper rate India, turmeric wholesale price, buy spices online India, premium cardamom Idukki",
        "cluster_count": "8",
        "cluster_summary": "Wholesale Buying (15 kws) | Price Comparison (12 kws) | Organic Premium (10 kws) | Kerala Origin (10 kws) | B2B Supply (8 kws) | Product Grades (8 kws) | Online Purchase (7 kws) | Local Sourcing (5 kws)",
    },

    "strategy_2c": {
        "module_2a_json": '{"business_type":"D2C Ecommerce","core_offering":"Farm-direct Kerala spices","value_proposition":"Premium single-origin spices from Idukki","target_intent":"online_sales","pricing_position":"premium","key_differentiators":["Farm-direct","Non-processed","8mm grade cardamom"]}',
        "module_2b_json": '{"strongest_pillar":"Cardamom","weakest_pillar":"Turmeric","dominant_intent":"commercial","high_value_opportunities":[{"keyword":"buy cardamom online","why":"High volume, strong buyer intent"}],"recommended_kw_focus":["buy cardamom online","Kerala spices wholesale","organic turmeric powder"]}',
        "blogs_per_week": "2",
        "duration_weeks": "12",
        "total_articles": "24",
        "content_mix": "60% blog, 25% landing page, 15% product page",
        "cadence_str": "Monday and Thursday",
        "extra_guidance": "Focus on premium positioning and farm-direct sourcing story.",
    },

    "strategy_2d": {
        "module_2c_json": '{"strategy_summary":{"headline":"Dominate Kerala spice D2C market through premium content","biggest_opportunity":"Wholesale buyer landing pages","why_we_win":"Farm-direct sourcing from Idukki"},"priority_pillars":[{"pillar":"Cardamom","rank":1}],"quick_wins":[{"keyword":"buy cardamom online","action":"create"}]}',
        "kw_score_sample": "buy cardamom online: 0.95 | cardamom price per kg: 0.88 | Kerala spices wholesale: 0.85",
        "cluster_list": "Wholesale Buying, Price Comparison, Organic Premium, Kerala Origin",
    },

    # ── Question Module Phase (3) ──────────────────────────────────

    "question_module_system": {
        "_test_user_prompt": "Briefly describe your role in generating search queries for an Indian spice ecommerce business and what dimensions you consider."
    },

    "question_module": {
        "business_context": "Sunrise Spices — D2C premium Kerala spice brand selling Cardamom, Black Pepper, and Turmeric from Idukki farms.",
        "module_specific_data": "PRODUCT FOCUS: Cardamom (8mm premium grade)\nKEY LOCATIONS: Idukki, Munnar, Wayanad\nAUDIENCE: Home cooks, restaurants, wholesale buyers",
        "module_focus": "buying and usage questions for Cardamom",
        "dimension_list": "geo (Kerala, Mumbai, Delhi), audience (home cooks, chefs, wholesalers), format (comparison, how-to, buying guide)",
        "max_questions": "5",
    },

    # ── Enrichment Phase (5) ───────────────────────────────────────

    "enrichment_system": {
        "_test_user_prompt": "Briefly describe how you enrich search queries with intent, funnel stage, and business relevance metadata."
    },

    "enrichment": {
        "business_context": "Sunrise Spices — D2C premium Kerala spice brand selling Cardamom, Black Pepper, and Turmeric.",
        "batch_size": "3",
        "questions_json": '[{"id":"q1","question":"Where to buy premium Idukki cardamom online?"},{"id":"q2","question":"Best black pepper varieties for restaurant cooking"},{"id":"q3","question":"Organic turmeric powder price per kg in India"}]',
    },

    # ── Title Generation Phase (9) ─────────────────────────────────

    "title_system": {
        "_test_user_prompt": "Briefly describe how you convert search queries into SEO-optimised content titles."
    },

    "title_generation": {
        "business_context": "Sunrise Spices — D2C premium Kerala spice brand from Idukki.",
        "batch_size": "2",
        "questions_json": '[{"id":"q1","question":"Where to buy premium Idukki cardamom online in India?"},{"id":"q2","question":"How to choose the best black pepper grade for cooking?"}]',
    },
}

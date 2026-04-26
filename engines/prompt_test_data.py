"""
Content Prompt Test Data — sample variables for live-testing each prompt in Prompt Studio.

Uses a fictional "Golden Crust Bakery" artisan bakery business.
Keeps data compact for Ollama's 4096-token context window.
"""

_CUSTOMER_CONTEXT = """BRAND: Golden Crust Bakery
TYPE: Local artisan bakery & online shop
WEBSITE: goldencrust.com
LOCATIONS: Austin, TX
AUDIENCE: Health-conscious foodies, home bakers, local cafes
USP: Organic sourdough with 48-hour cold fermentation
PRODUCTS: Sourdough loaves, croissants, artisan bread, pastries, gluten-free options"""

CONTENT_SAMPLE_DATA = {
    "step1_research_instructions": {
        "customer_context": _CUSTOMER_CONTEXT,
        "_meta": {"keyword": "best sourdough bread Austin", "intent": "commercial"},
    },

    "step2_structure_rules": {
        "keyword": "best sourdough bread Austin",
        "_meta": {"intent": "commercial", "page_type": "blog"},
    },

    "step3_verify_instructions": {
        "customer_context": _CUSTOMER_CONTEXT,
        "_meta": {
            "keyword": "best sourdough bread Austin",
            "structure_preview": "H1: 5 Best Sourdough Bread Options in Austin | H2s: What Makes Great Sourdough?, How Cold Fermentation Works, Where to Buy in Austin, Which Sourdough Is Best for You?, FAQ",
        },
    },

    "step4_link_planning": {
        "customer_context": _CUSTOMER_CONTEXT,
        "_meta": {"keyword": "best sourdough bread Austin"},
    },

    "step5_reference_rules": {
        "customer_context": _CUSTOMER_CONTEXT,
        "_meta": {"keyword": "best sourdough bread Austin"},
    },

    "step6_quality_rules": {
        "_meta": {
            "keyword": "best sourdough bread Austin",
            "research_themes": "Cold fermentation benefits, Austin bakery scene, Sourdough nutrition, Gluten sensitivity and sourdough",
            "structure_summary": "H1: 5 Best Sourdough Bread Options in Austin | 7 H2 sections | FAQ with 5 questions",
            "links_plan": "4 internal links to /products/, /sourdough-guide/, /locations/, /wholesale/ | 3 external to USDA, Wikipedia, PubMed",
        },
    },

    "step6_intelligence_rules": {
        "customer_context": _CUSTOMER_CONTEXT,
        "_meta": {"keyword": "best sourdough bread Austin"},
    },

    "step7_review_criteria": {
        "_meta": {
            "keyword": "best sourdough bread Austin",
            "note": "This prompt is an evaluation checklist — test with a sample article excerpt.",
            "sample_article_excerpt": "<h1>5 Best Sourdough Bread Options in Austin</h1><p>Austin's artisan bread scene has exploded. According to a 2024 USDA report, sourdough sales grew 34% year-over-year.</p>",
        },
    },

    "step9_quality_rules": {
        "customer_context": _CUSTOMER_CONTEXT,
        "_meta": {
            "keyword": "best sourdough bread Austin",
            "failed_rules": "R20 (need more authority phrases), R36 (need real-world proof signals), R26 (missing Wikipedia link)",
        },
    },

    "step10_scoring_rules": {
        "_meta": {
            "note": "This is a scoring configuration prompt — no variables to fill. Test verifies the AI understands the scoring framework.",
        },
    },

    "step11_quality_loop": {
        "customer_context": _CUSTOMER_CONTEXT,
        "_meta": {
            "keyword": "best sourdough bread Austin",
            "current_score": "82%",
            "failed_rules": "R20 (authority signals: 3/5), R36 (real-world proof: 1/3), R26 (Wikipedia: 0/1)",
        },
    },
}

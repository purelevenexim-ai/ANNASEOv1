"""
kw2 constants — hard-coded values used across all phases.
"""

# Phase 3: hard-reject patterns. Any keyword containing these substrings is rejected.
NEGATIVE_PATTERNS = [
    "recipe", "recipes", "health benefits", "benefits of", "benefit of",
    "how to use", "how to make", "how to grow", "how to cook",
    "what is", "meaning", "definition", "nutrition facts", "nutritional value",
    "side effects", "dosage", "dosage of", "home remedy", "home remedies",
    "uses of", "in hindi", "in urdu", "in tamil", "ayurvedic uses",
    "traditional use", "history of", "origin of",
    "images", "photos", "wallpaper", "free download", "wikipedia",
    "pdf", "drawing", "emoji", "meme", "memes",
    "diy", "craft", "coloring page",
]

# Points added to commercial_score when keyword contains these tokens
COMMERCIAL_BOOSTS = {
    "buy": 30, "wholesale": 35, "price": 25, "online": 20,
    "supplier": 20, "near me": 20, "bulk": 25, "export": 15,
    "exporter": 15, "manufacturer": 20, "distributor": 15,
    "cheapest": 20, "best": 15, "for sale": 25,
    "order": 20, "shop": 15, "store": 10, "dealer": 15,
}

# Weight per intent category (0-1 scale, used in scoring)
# Uses 3 canonical intents (raw AI values are normalized via _normalize_intent)
INTENT_WEIGHTS = {
    "commercial": 0.85,
    "informational": 0.25,
    "navigational": 0.40,
}

# Top-100 category percentage caps (sums to 100)
CATEGORY_CAPS = {
    "purchase": 40,
    "wholesale": 20,
    "price": 15,
    "comparison": 10,
    "local": 10,
    "other": 5,
}

# Phase 4b: sentence-transformers model (CPU-friendly, 384-dim)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Phase 4b: cosine threshold for greedy centroid clustering
CLUSTER_SIMILARITY_THRESHOLD = 0.85

# Phase 2: max rule keywords kept per pillar after scoring (score-and-trim gate)
MAX_RULES_PER_PILLAR = 50

# Phase 2: scoring gate — max template keywords per pillar before real-data layers run
SCORING_GATE_PER_PILLAR = 80

# Phase 2: target total keywords per pillar (AI expand fills up to this)
PILLAR_TARGET_COUNT = 100

# Only name clusters with >N keywords via AI; smaller ones use representative keyword
CLUSTER_NAME_MIN_SIZE = 3

# Phase 3: AI validation batch size (80 works well with Qwen2.5 3B)
VALIDATION_BATCH_SIZE = 80

# Phase 3: early stop after this many accepted keywords (LEGACY — not used in v2 brain)
VALIDATION_TARGET_COUNT = 400

# Phase 3: pre-score threshold — keywords below this skip AI validation entirely
PRE_SCORE_THRESHOLD = 55

# Phase 3: max keywords sent to AI per pillar (after pre-score trim)
MAX_PER_PILLAR_AI = 500

# Phase 3: smart early-stop — stop AI batches if last N batches have acceptance rate below threshold
EARLY_STOP_WINDOW = 3
EARLY_STOP_MIN_RATE = 0.10

# Phase 3: max concurrent AI calls (limited by 8GB RAM + local Ollama)
AI_CONCURRENCY = 4

# Phase 1: cache business profile for N days before re-analyzing
PROFILE_CACHE_DAYS = 7

# Phase 1: crawl config
CRAWL_MAX_PAGES = 20
CRAWL_PRIORITY_PATHS = ["/", "/products", "/collections", "/shop", "/about", "/category", "/categories"]
CRAWL_IGNORE_PATHS = ["/blog", "/faq", "/policy", "/terms", "/login", "/cart", "/checkout"]

# Phase 2: transactional keyword templates ({k} = pillar keyword)
TRANSACTIONAL_TEMPLATES = [
    "buy {k}", "buy {k} online", "{k} price", "{k} price per kg",
    "{k} wholesale", "{k} wholesale price", "{k} bulk", "{k} bulk buy",
    "{k} supplier", "{k} supplier india", "{k} near me", "{k} online india",
    "best {k}", "cheapest {k}", "{k} export quality", "{k} manufacturer",
    "{k} distributor", "{k} for sale",
]

# Phase 2: commercial templates
COMMERCIAL_TEMPLATES = [
    "{k} vs {alt}", "best {k} brands", "{k} reviews", "top {k}",
    "{k} comparison", "{k} alternatives",
]

# Phase 2: local templates
LOCAL_TEMPLATES = [
    "{k} {loc}", "{k} near me", "{k} {loc} supplier",
    "{k} {loc} wholesale", "{k} {loc} exporter",
]

# Phase 2: navigational templates (new — brand/store/location awareness)
NAVIGATIONAL_TEMPLATES = [
    "{k} near me",
    "{k} store",
    "{k} shop",
    "{k} brand",
    "{k} brands",
    "{k} retailer",
    "{k} retailers",
    "{k} website",
    "{k} official",
    "where to buy {k}",
    "{k} stockist",
]

# Phase 2: audience-based templates ({k} = pillar, {a} = audience segment)
AUDIENCE_TEMPLATES = [
    "{k} for {a}",
    "best {k} for {a}",
    "{k} {a}",
    "{a} {k} supplier",
    "{a} {k} guide",
]

# Phase 2: comparison templates ({k} = product, {alt} = comparison target)
COMPARISON_TEMPLATES = [
    "{k} vs {alt}",
    "{k} or {alt}",
    "{k} compared to {alt}",
    "best {k} or {alt}",
    "difference between {k} and {alt}",
]

# Phase 2: problem/solution templates ({k} = pillar)
PROBLEM_TEMPLATES = [
    "best quality {k}",
    "trusted {k} supplier",
    "authentic {k}",
    "genuine {k} online",
    "fresh {k} delivery",
    "where to find real {k}",
    "{k} not adulterated",
    "purest {k}",
]

# Phase 2: attribute-based templates ({k} = pillar, {attr} = product attribute)
ATTRIBUTE_TEMPLATES = [
    "{attr} {k}",
    "{attr} {k} price",
    "{attr} {k} online",
    "buy {attr} {k}",
    "best {attr} {k}",
    "{attr} {k} supplier",
]

# Phase 4: Hybrid scoring weights
HYBRID_SCORE_WEIGHTS = {
    "rule": 0.40,
    "context": 0.35,
    "data": 0.25,
}

# Phase 4: Rule-based scoring signals
RULE_SCORE_INTENT = {
    "buy": 30, "price": 25, "best": 20, "near me": 25,
    "wholesale": 30, "bulk": 25, "supplier": 25, "order": 20,
    "cheapest": 20, "for sale": 25,
}

RULE_SCORE_MODIFIER_PREMIUM = {
    "premium": 20, "organic": 18, "pure": 18, "farm-direct": 20,
    "fresh": 15, "chemical-free": 18, "hand-harvested": 20,
    "non-oil extracted": 20, "export quality": 20,
}

RULE_SCORE_MODIFIER_GENERIC = {
    "online": 10, "india": 8, "best": 12, "top": 10, "good": 5,
}

# Garbage words for filtering crawl-extracted n-grams
GARBAGE_WORDS = frozenset({
    "the", "a", "an", "of", "in", "to", "for", "and", "or", "is", "it",
    "by", "on", "at", "this", "that", "with", "from", "as", "are", "was",
    "be", "has", "had", "have", "do", "does", "did", "will", "would",
    "home", "cart", "login", "menu", "page", "click", "here", "more",
    "read", "share", "next", "prev", "back", "close", "open", "new",
    "blog", "post", "comment", "reply", "search", "filter", "sort",
    "footer", "header", "sidebar", "nav", "main", "body",
    # Ecommerce UI/pricing noise (from product pages)
    "your", "our", "my", "all", "you", "we", "us", "out", "get",
    "add", "buy", "view", "show", "select", "choose", "continue",
    "skip", "cancel", "save", "apply", "submit", "send", "update",
    "price", "original", "inclusive", "taxes", "tax", "gst", "cess",
    "stock", "sold", "available", "delivery", "shipping", "checkout",
    "quantity", "qty", "amount", "total", "subtotal", "discount",
    "offer", "sale", "deal", "coupon", "code", "promo",
    "login", "signup", "account", "wishlist", "compare",
    "reviews", "rating", "stars", "verified", "purchase",
})

# Multi-word phrases to always remove from competitor keyword extraction
GARBAGE_PHRASES = frozenset({
    "all taxes", "all taxes inclusive", "taxes inclusive", "price inclusive",
    "inclusive all taxes", "price price", "original price", "your price",
    "add to cart", "out of stock", "in stock", "taxes add", "out original",
    "out original price", "price inclusive all", "taxes add cart",
    "related products", "additional information", "product description",
    "view cart", "proceed checkout", "continue shopping",
    "free delivery", "free shipping", "cash on delivery",
    "skip content", "skip main", "back top",
})

# ── v2 Keyword Brain constants ──────────────────────────────────────────────

# Default intent distribution for new sessions (% of 100 target per pillar)
DEFAULT_INTENT_DISTRIBUTION = {
    "commercial": 60,
    "informational": 25,
    "navigational": 15,
}

# Target candidates per pillar before narrowing (2x target to allow selection)
CANDIDATES_PER_PILLAR = 200

# Default final keywords per pillar
TARGET_KW_PER_PILLAR = 100

# Top-100 split: pillar-specific vs supporting/bridge
TOP100_PILLAR_RATIO = 0.60     # 60 unique to pillar
TOP100_SUPPORTING_RATIO = 0.40  # 40 shared/supporting

# AI expansion counts per intent batch (per pillar)
# Reduced from 80/40/20 — rules already cover most transactional patterns.
# AI should focus on UNIQUE angles rules can't generate.
AI_EXPAND_COMMERCIAL = 40
AI_EXPAND_INFORMATIONAL = 20
AI_EXPAND_NAVIGATIONAL = 10

# Normalization: semantic dedup threshold (tighter than old 0.85)
SEMANTIC_DEDUP_THRESHOLD = 0.90

# Multi-pillar: minimum confidence to assign a keyword to a pillar
PILLAR_CONFIDENCE_THRESHOLD = 0.3

# Scoring bonuses (v2)
MULTI_PILLAR_BONUS = 0.10    # +10% for bridge keywords
CLUSTER_TOP_BONUS = 0.05     # +5% for cluster-best keyword

# Relationship graph weights
REL_WEIGHT_SIBLING = 0.8
REL_WEIGHT_CROSS_CLUSTER = 0.5
REL_WEIGHT_CROSS_PILLAR = 0.6
REL_WEIGHT_MODIFIER = 0.7
REL_WEIGHT_VARIANT = 0.9

# v2 phase names (for phase_status JSON)
V2_PHASES = ["understand", "expand", "organize", "apply"]

# ── Smart validation: skip AI for high-confidence rule/seed keywords ─────────
# These source types always produce structurally valid commercial phrases.
# No need to pay AI to confirm "buy cardamom online" is a valid keyword.
SKIP_VALIDATION_SOURCES = frozenset({"seeds", "rules"})
SKIP_VALIDATION_MIN_SCORE = 65   # raw_score threshold for auto-approval
SKIP_VALIDATION_RELEVANCE = 0.80  # pre-approved ai_relevance score

# ── Batch cluster naming ──────────────────────────────────────────────────────
# Name this many clusters in a single AI call (was 1 per cluster)
CLUSTER_NAME_BATCH_SIZE = 10

# ── Modifier seed-building quality gate ──────────────────────────────────────
# These modifier words are INTENT signals, not QUALIFIER prefixes.
# Using them as seed prefixes creates invalid phrases like "online cardamom",
# "price cardamom", "buy organic". They belong in templates, not seed combos.
SEED_INTENT_MODIFIERS_EXCLUDE = frozenset({
    "online", "price", "buy", "order", "cost", "rate", "cheap", "cheapest",
    "free", "delivery", "shipping", "sale", "discount", "deal",
    "best price", "lowest price",
})

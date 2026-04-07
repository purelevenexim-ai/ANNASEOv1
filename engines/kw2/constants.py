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
INTENT_WEIGHTS = {
    "purchase": 1.0,
    "transactional": 0.90,
    "commercial": 0.70,
    "comparison": 0.60,
    "local": 0.50,
    "research": 0.30,
    "informational": 0.10,
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

# Only name clusters with >N keywords via AI; smaller ones use representative keyword
CLUSTER_NAME_MIN_SIZE = 3

# Phase 3: AI validation batch size (25 = sweet spot for JSON accuracy)
VALIDATION_BATCH_SIZE = 25

# Phase 3: early stop after this many accepted keywords
VALIDATION_TARGET_COUNT = 400

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

# Garbage words for filtering crawl-extracted n-grams
GARBAGE_WORDS = frozenset({
    "the", "a", "an", "of", "in", "to", "for", "and", "or", "is", "it",
    "by", "on", "at", "this", "that", "with", "from", "as", "are", "was",
    "be", "has", "had", "have", "do", "does", "did", "will", "would",
    "home", "cart", "login", "menu", "page", "click", "here", "more",
    "read", "share", "next", "prev", "back", "close", "open", "new",
    "blog", "post", "comment", "reply", "search", "filter", "sort",
    "footer", "header", "sidebar", "nav", "main", "body",
})

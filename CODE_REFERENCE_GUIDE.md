# AnnaSEO Code Reference Guide

Quick reference for navigating and understanding key source files.

---

## 📂 Main Entry Point

### `main.py` (7,204 lines)

**Lines 1-100: Imports & Setup**
- Import FastAPI, JWT, services, job queues
- Set up logging, Sentry, OpenTelemetry
- Initialize error tracking

**Lines 101-191: Exception Handlers**
- Global error handler catches all exceptions
- Logs to ERROR_LOG and triggers alerts
- Formats JSON 5xx responses

**Lines 202-280: Middleware**
- metrics_collector: Logs every request + latency
- Tracks request count, latency per endpoint
- Handles exceptions in middleware

**Lines 282-454: Database Setup (get_db())**
- Creates 45+ tables if they don't exist
- Schema script (CREATE TABLE statements)
- Migrations applied safely (ALTER TABLE)
- WAL mode enabled for concurrency

**Lines 454+: API Routes**
- **GET /api/health** — System status check
- **POST /api/register** — User registration
- **POST /api/login** — JWT authentication
- **GET /api/projects** — List user projects
- **POST /api/run** — Start keyword pipeline (main entry)
- **GET /api/runs/{run_id}** — Get pipeline result
- **POST /api/strategy/develop** — Strategy development engine
- **GET /api/blogs** — List articles
- **POST /api/blogs/{id}/approve** — Approve article
- **POST /api/rankings/import** — GSC sync
- **WebSocket /ws** — SSE streaming for progress

---

## 🧠 Core Engines

### `engines/ruflo_20phase_engine.py` (3,600+ lines)

**Lines 1-70: File Header & Documentation**
- Architecture overview (20 phases, memory management, caching)
- Pipeline from P1 (Seed) to P20 (Ranking Feedback)

**Lines 73-160: Configuration (Cfg)**
```python
class Cfg:
    BASE_DIR = "./ruflo_data"           # Root for all cache/checkpoint/embeddings
    CACHE_DIR, CHECKPOINT_DIR, EMBED_DIR, BRIEF_DIR, ARTICLE_DIR

    # AI Models
    OLLAMA_URL = "http://localhost:11434"
    GEMINI_KEY, GEMINI_MODEL, GEMINI_RATE
    ANTHROPIC_KEY, CLAUDE_MODEL
    GROQ_KEY, GROQ_MODEL

    # Memory budgets per phase (MB)
    MEMORY_BUDGET = {"P1": 5, "P4": 150, "P8": 380, ...}

    # Cache TTLs
    TTL_SUGGESTIONS = 7 days
    TTL_SERP = 14 days
    TTL_ENTITIES = 30 days

    PUBLISH_THRESHOLD = 75  # Min score for auto-publish
    HEAVY_PHASES = {"P4", "P8"}  # Never simultaneous
    CHUNK_SIZE = 500  # Stream large sets
```

**Lines 164-222: ContentPace**
```python
class ContentPace:
    duration_years: int = 2
    blogs_per_day: float = 3
    parallel_claude_calls: int = 5
    per_pillar_overrides: Dict[str, float] = {}
    seasonal_priorities: Dict[str, float] = {}

    def summary(self) -> {...}  # Cost + time preview
    def schedule(self, pillars) -> {...}  # Create content calendar
```

**Lines 222-276: MemoryManager**
```python
class MemoryManager:
    @staticmethod
    def acquire(phase: str) -> None
    @staticmethod
    def release(phase: str) -> None
    @staticmethod
    def can_run(phase: str) -> (bool, reason)
    # Prevents memory overload; sequences heavy phases (P4, P8)
```

**Lines 277-437: Cache**
```python
class Cache:
    # L1: In-memory LRU cache (1000 items)
    # L2: SQLite disk cache (14d TTL for SERP, 7d for suggestions)
    # L3: File checkpoints (.json.gz per phase)

    @staticmethod
    def get_l1(key) -> value or None
    @staticmethod
    def set_l1(key, value) -> None
    @staticmethod
    def load_checkpoint(phase, seed) -> data or None
    @staticmethod
    def save_checkpoint(phase, seed, data) -> None
```

**Lines 438-618: AI**
```python
class AI:
    # Route to correct LLM based on task

    @staticmethod
    def call_ollama(model, prompt) -> text
    @staticmethod
    def call_gemini(prompt) -> text  # Free tier
    @staticmethod
    def call_groq(prompt) -> text    # Free tier
    @staticmethod
    def call_claude(prompt) -> text  # $0.022/article

    @staticmethod
    def extract_json(raw_text) -> dict or None
```

**Lines 632-650: P1_SeedInput**
```python
class P1_SeedInput:
    def run(self, keyword: str, language: str, region: str, product_url: str) -> Seed:
        # Normalize seed keyword
        # Validate against domain (if project_id passed)
        # Return Seed object with metadata
```

**Lines 651-996: P2_KeywordExpansion**
```python
class P2_KeywordExpansion:
    def run(self, seed: Seed) -> List[str]:
        # Fetch from 5 sources:
        # 1. Google autocomplete API
        # 2. YouTube autocomplete
        # 3. Amazon autocomplete
        # 4. Reddit /r/{seed} posts
        # 5. Competitor SERP mining
        #
        # Parallel requests (rate-limited)
        # Dedupe + flatten to ~1,000 keywords
        # Cache results (7d TTL)
```

**Lines 997-1144: P3_Normalization**
```python
class P3_Normalization:
    def run(self, seed: Seed, raw_keywords: List[str]) -> List[str]:
        # Remove duplicates (case-insensitive)
        # Remove stop words (the, a, and)
        # Remove exact parent seed
        # Remove spam patterns (>5 repeated chars, all symbols)
        # Filter by min_length=3, max_length=100 chars
        # Return ~300 clean keywords
```

**Lines 1145-1214: P4_EntityDetection**
```python
class P4_EntityDetection:
    def run(self, seed: Seed, keywords: List[str]) -> Dict[str, List[str]]:
        # Use spaCy NER (en_core_web_sm)
        # Extract: PERSON, PRODUCT, GPE, ORG, NORP, etc.
        # Group keywords by entity type
        # Cache entity embeddings (.npy files)
        # Heavy phase (150MB budget)
```

**Lines 1239-1333: P5_IntentClassification**
```python
class P5_IntentClassification:
    def run(self, seed: Seed, keywords: List[str], entities: Dict) -> Dict[str, str]:
        # Classify each keyword:
        #   - informational (how to, what is, guide, learn)
        #   - commercial (buy, best, vs, review)
        #   - navigational (site name, brand)
        #   - transactional (near me, prices, compare)
        #
        # Uses Gemini for fast classification
        # Return: {keyword: intent}
```

**Lines 1334-1422: P6_SERPIntelligence**
```python
class P6_SERPIntelligence:
    def run(self, seed: Seed, keywords: List[str]) -> Dict[str, Dict]:
        # Fetch Google top 10 for each keyword
        # Extract:
        #   - result titles, URLs, snippets
        #   - keyword difficulty (KD, 0-100)
        #   - search volume (if available)
        #   - featured snippet data
        #
        # Use Playwright (headless browser) or SerpAPI
        # Cache 14 days
        # Return: {keyword: {position_0: {...}, ..., kd: 45, ...}}
```

**Lines 1528-1612: P7_OpportunityScoring**
```python
class P7_OpportunityScoring:
    def run(self, seed: Seed, keywords, intent_map, serp_map, entities) -> Dict[str, float]:
        # Score = (volume × intent_multiplier) / (kd + 1)
        #
        # Intent multipliers:
        #   - informational: 0.6 (high volume, low conversion)
        #   - commercial: 1.5 (lower volume, high conversion)
        #   - transactional: 2.0 (exact buyer intent)
        #
        # Boost for entity mentions (PRODUCT, GPE)
        # Penalty for highly competitive (KD > 80)
        #
        # Return: {keyword: 0-100 score}
```

**Lines 1613-1685: P7_TopKeywordSelector**
```python
class P7_TopKeywordSelector:
    def run(self, seed, keywords, scores, intent_map, top_n=100) -> List[Dict]:
        # Select top N keywords ensuring intent diversity
        # Quota:
        #   - 40% informational
        #   - 35% commercial
        #   - 15% transactional
        #   - 10% navigational
        #
        # Return: top100_keywords[] for later ranking tracking
```

**Lines 1686-1773: P8_TopicDetection**
```python
class P8_TopicDetection:
    def run(self, seed: Seed, keywords, scores, intent_map) -> Dict[str, str]:
        # Embed keywords using SBERT (Sentence BERT)
        # HDBSCAN clustering on embeddings
        # Min cluster size: 5, min samples: 2
        # Assign keywords to topics
        #
        # Heavy phase (380MB budget)
        # Cache embeddings permanently (.npy files)
        #
        # Return: {keyword: topic_label}
```

**Lines 1774-1850: P9_ClusterFormation**
```python
class P9_ClusterFormation:
    def run(self, seed, topic_map, project_id) -> Dict[str, List[str]]:
        # Group topics into clusters (semantic groups)
        # Each cluster = ~50-200 keywords with similar meaning
        # Name clusters based on keywords
        #
        # Apply domain context filter (project_id)
        # Remove off-topic clusters
        #
        # Return: {cluster_name: [keywords]}
```

**Lines 1851-1907: P10_PillarIdentification**
```python
class P10_PillarIdentification:
    def run(self, seed, clusters, project_id) -> Dict[str, Dict]:
        # Identify pillar pages (main hubs in each cluster)
        # Pillars are top-ranked competitors' pages
        #
        # Logic:
        #   1. Fetch SERP data for cluster keywords
        #   2. Group SERPs by landing page URL
        #   3. Count keyword coverage per URL
        #   4. Top 3-5 URLs per cluster = pillars
        #
        # Return: {pillar_id: {name, cluster, keywords, url}}
```

**Lines 1914-1958: P11_KnowledgeGraph**
```python
class P11_KnowledgeGraph:
    def run(self, seed, pillars, topic_map, intent_map, scores) -> Dict:
        # Build semantic knowledge graph
        # Nodes: pillars + high-scoring keywords
        # Edges: keyword relationships
        #   - semantic similarity (SBERT)
        #   - intent compatibility
        #   - entity connections
        #
        # Graph structure:
        # {
        #   "nodes": [{id, label, type, score}],
        #   "edges": [{source, target, weight, type}]
        # }
```

**Lines 1959-2022: P12_InternalLinking**
```python
class P12_InternalLinking:
    def run(self, seed, graph) -> Dict[str, List[str]]:
        # Generate internal link recommendations
        # For each article: suggest 3-5 internal links
        #
        # Algorithm:
        #   1. For article X, find semantically similar articles
        #   2. Prioritize articles with lower ranking (boost them)
        #   3. Avoid silo bloat (not >3 from same cluster)
        #   4. Anchor text = keyword of target article
        #
        # Return: {article_id: [{target, anchor_text, reason}]}
```

**Lines 2023-2132: P13_ContentCalendar**
```python
class P13_ContentCalendar:
    def run(self, seed, graph, scores, pace: ContentPace) -> List[Dict]:
        # Create 2-year content publication schedule
        #
        # Algorithm:
        #   1. Rank pillars by opportunity score
        #   2. For each pillar, calculate supporting articles
        #   3. Spread articles over duration_years
        #   4. Allocate blogs_per_day slots
        #   5. Group by season + religion (if specified)
        #
        # Per-pillar overrides: some pillars publish faster
        # Seasonal priorities: boost certain topics in seasons
        #
        # Return: [
        #   {
        #     "pillar": "cinnamon health benefits",
        #     "keyword": "cinnamon lowers blood sugar",
        #     "scheduled_date": "2026-04-15",
        #     "priority": 1,
        #     "estimated_rank": 5
        #   }, ...
        # ]
```

**Lines 2133-2180: P14_DedupPrevention**
```python
class P14_DedupPrevention:
    def run(self, seed, calendar, existing_articles) -> List[Dict]:
        # Remove articles already published on client's site
        #
        # Check:
        #   1. Exact keyword match (case-insensitive)
        #   2. URL match
        #   3. Title similarity (>90%)
        #
        # Skip duplicates from calendar
        #
        # Return: deduplicated calendar
```

**Lines 2181-2264: P15_ContentBrief**
```python
class P15_ContentBrief:
    def run(self, seed, calendar) -> List[Dict]:
        # Generate content briefs for each article
        #
        # Brief structure:
        # {
        #   "keyword": "cinnamon lowers blood sugar",
        #   "pillar": "cinnamon health benefits",
        #   "intent": "informational",
        #   "target_length": 2500,
        #   "h2_outline": ["What is...", "How does...", "Research shows..."],
        #   "entities_to_mention": ["diabetes", "fasting"],
        #   "internal_links": [{"keyword": "...", "anchor": "..."}],
        #   "schema_types": ["Article", "NewsArticle"],
        #   "angle": "Scientific evidence for cinnamon benefits"
        # }
```

**Lines 2265-2333: P16_ClaudeContentGeneration**
```python
class P16_ClaudeContentGeneration:
    def run(self, brief, project_id, language, region) -> Dict:
        # Generate full article using Claude Sonnet
        #
        # Prompt includes:
        #   - Brief structure
        #   - Target audience (from project)
        #   - SEO requirements (keywords, internal links)
        #   - Domain context (project-specific rules)
        #
        # Output:
        # {
        #   "title": "...",
        #   "meta_title": "...",
        #   "meta_desc": "...",
        #   "body": "<h2>...</h2><p>...</p>...",
        #   "word_count": 2843,
        #   "internal_links": [{url, anchor_text, position}],
        #   "entities_covered": [...]
        # }
        #
        # Cost: ~$0.022/article (Claude Sonnet)
```

**Lines 2334-2409: P17_SEOOptimization**
```python
class P17_SEOOptimization:
    def run(self, article) -> Dict:
        # Optimize for SEO
        #
        # Checks:
        #   1. Keyword density (target 1.5% ± 0.5%)
        #   2. Readability (Flesch-Kincaid grade)
        #   3. H2/H3 distribution
        #   4. Image alt text presence
        #   5. Internal link anchor text variety
        #
        # Adjustments:
        #   - Rewrite title if keyword missing
        #   - Add/remove keyword mentions
        #   - Restructure headings
        #   - Enhance meta description
        #
        # Output: optimized article
```

**Lines 2410-2472: P18_SchemaMetadata**
```python
class P18_SchemaMetadata:
    def run(self, article) -> Dict:
        # Add JSON-LD schema + OpenGraph metadata
        #
        # Schema types:
        #   - Article (default)
        #   - NewsArticle (if published news-style)
        #   - BlogPosting (if blog)
        #   - FAQPage (healthcare/gov only)
        #
        # Avoid:
        #   - HowTo (deprecated Sept 2023)
        #   - Microdata (use JSON-LD only)
        #
        # OpenGraph:
        #   - og:title, og:description, og:image
        #   - og:type, og:url
        #
        # Output: article with schema_json
```

**Lines 2473-2593: P19_Publishing**
```python
class P19_Publishing:
    def run(self, articles, project_id) -> Dict[str, str]:
        # Publish articles to WordPress or Shopify
        #
        # WordPress:
        #   1. Connect via REST API (wp_url, wp_user, wp_pass)
        #   2. Create post with content
        #   3. Set status (publish/draft)
        #   4. Add featured image
        #   5. Set categories/tags
        #
        # Shopify:
        #   1. Connect via token (shopify_store, shopify_token)
        #   2. Create article in blog
        #   3. Set SEO metadata
        #
        # Return: {article_id: published_url}
```

**Lines 2594-3100: RufloOrchestrator**
```python
class RufloOrchestrator:
    def __init__(self):
        # Initialize all 20 phase engines
        self.p1, self.p2, ..., self.p20 = ...
        self.phase_callback = None

    def run_seed(self, keyword, pace, project_id, generate_articles) -> Dict:
        # Execute P1-P20 pipeline
        #
        # Flow:
        #   P1 → P2 → P3 → GATE_A → P4-P8 → GATE_B → P9-P14
        #   → GATE_C → P15-P19 (optional) → P20
        #
        # Gates pause for user approval:
        #   - GATE_A: Confirm universe keywords
        #   - GATE_B: Confirm pillars
        #   - GATE_C: Confirm content calendar
        #
        # Memory management: acquire/release per phase
        # Checkpoint save after each phase
        #
        # Return: {
        #   "seed": {...},
        #   "keyword_count": 312,
        #   "cluster_count": 42,
        #   "calendar_count": 2400,
        #   "_graph": {...},  # Knowledge graph
        #   "_calendar": [...],  # Full calendar
        #   "cost_preview": {...}
        # }
```

---

## 🔐 Domain Context Engine

### `quality/annaseo_domain_context.py` (1,200+ lines)

**Lines 87-100: Industry Enum**
```python
class Industry(str, Enum):
    FOOD_SPICES = "food_spices"
    TOURISM = "tourism"
    ECOMMERCE = "ecommerce"
    HEALTHCARE = "healthcare"
    AGRICULTURE = "agriculture"
    EDUCATION = "education"
    REAL_ESTATE = "real_estate"
    TECH_SAAS = "tech_saas"
    WELLNESS = "wellness"
    RESTAURANT = "restaurant"
    FASHION = "fashion"
    GENERAL = "general"
```

**Lines 105-200: CROSS_DOMAIN_VOCABULARY**
```python
CROSS_DOMAIN_VOCABULARY: Dict[str, Dict[str, str]] = {
    "tour": {
        Industry.TOURISM: "accept",    # Good for travel
        Industry.FOOD_SPICES: "reject",  # Bad for spice sellers
        Industry.ECOMMERCE: "reject",  # Bad for e-commerce
    },
    "price": {
        Industry.ECOMMERCE: "accept",
        Industry.FOOD_SPICES: "accept",
        Industry.TOURISM: "conditional",  # "tour price" = OK
    },
    "ceylon": {
        Industry.TOURISM: "accept",
        Industry.FOOD_SPICES: "accept",  # "ceylon cinnamon" = product name
        Industry.AGRICULTURE: "accept",
    },
    # ... 100+ cross-domain terms
}

# Global noise (applies to ALL projects)
OffTopicFilter.GLOBAL_KILL = [
    "meme", "viral", "tiktok", "joke",  # Social media noise
    "nsfw", "xxx", "porn",              # Adult content
    "scam", "bitcoin", "crypto",        # Spam
]
```

**Lines 300-400: ProjectDomainProfile**
```python
@dataclass
class ProjectDomainProfile:
    project_id: str
    industry: Industry

    # Domain vocabulary for THIS project
    domain_keywords: List[str]  # What this business cares about
    anti_keywords: List[str]    # What this business explicitly rejects

    # Cross-domain words specific to THIS project
    cross_domain_signals: Dict[str, str]  # word → "accept" or "reject"

    # Tuning history
    tuning_history: List[Dict]  # [{keyword, decision, reason, date}]
```

**Lines 450-600: DomainContextEngine**
```python
class DomainContextEngine:
    def classify(self, keyword: str, project_id: str) -> (str, str):
        # Returns: (ACCEPT / REJECT / AMBIGUOUS, reason)
        #
        # Logic:
        #   1. Check GLOBAL_KILL (universal noise) → REJECT
        #   2. Check ProjectDomainProfile.reject_overrides → REJECT
        #   3. Check project domain_keywords → ACCEPT
        #   4. Check CROSS_DOMAIN_VOCABULARY[keyword][industry] → decision
        #   5. Check anti_keywords → REJECT
        #   → Default: AMBIGUOUS
        #
        # Track in tuning_history

    def cross_domain_check(self, keyword: str, project_id: str) -> bool:
        # Is this a cross-domain term for this industry?
        # Used to gate P2 expansion

    def score_for_domain(self, keyword: str, project_id: str) -> float:
        # 0-100 domain relevance score
        # 100 = perfect for project
        # 0 = completely off-topic
```

**Lines 700-800: GlobalTuningRegistry**
```python
class GlobalTuningRegistry:
    # Affects ALL projects

    # Algorithm bugs (code-level fixes)
    rephrase_rules: Dict[str, str]  # Common misspellings → correct form
    embedding_model_version: str    # Track SBERT version
    hdbscan_params: Dict[str, float]  # Cluster parameters

    # Quality thresholds (global)
    min_cluster_size: int = 5
    min_keyword_count: int = 20
    max_kd_for_easy_wins: int = 10
```

**Lines 850-950: ProjectTuningRegistry**
```python
class ProjectTuningRegistry:
    # Per-project tuning (doesn't affect other projects)

    project_id: str

    # Kill lists (per-project)
    reject_overrides: List[str]  # Keywords to reject for THIS project only
    accept_overrides: List[str]  # Keywords to force-accept

    # Scoring adjustments (per-project)
    scoring_multipliers: Dict[str, float]  # {intent: 0.5-2.0}
    seasonal_boosts: Dict[str, float]  # {month: multiplier}

    # Prompt customization (per-project)
    content_angle_hints: str  # "Emphasize sustainability"
    tone_override: str  # "formal" or "conversational"
```

---

## 📝 Frontend Components

### `frontend/src/App.jsx`

**Lines 1-100: Setup & Store**
```javascript
const useStore = create((set, get) => ({
    user: null,
    token: localStorage.getItem("annaseo_token"),
    activeProject: localStorage.getItem("annaseo_project"),
    sidebarOpen: true,
    currentPage: "dashboard",

    setUser, setToken, setProject, setPage, toggleSidebar, logout
}))

// Global API client
const api = {
    get: async (path) => { /* with auth header */ },
    post: async (path, body) => { /* with JWT */ },
    put, delete
}

// Design tokens
const T = {
    purple: "#7F77DD",
    teal: "#1D9E75",
    red: "#E24B4A",
    // ...
}
```

**Lines 150-400: Shared Components**
- `Badge({children, color})` — Status badges
- `Card({children})` — Container card
- `StatCard({label, value, sub})` — Stat display
- `Button({onClick, children})` — Standard button
- `Modal({isOpen, onClose, children})` — Modal dialog
- `Spinner()` — Loading spinner

### `frontend/src/KeywordInput.jsx`

**Keyword Universe Flow**
```javascript
// 5-step process:
1. Seed Keyword Input
2. Confirm Universe Keywords (GATE A)
3. Confirm Pillars (GATE B)
4. Confirm Content Calendar (GATE C)
5. View Results (graph, calendar, stats)

// SSE streaming from backend
const source = new EventSource(`/api/runs/${runId}/events`)
source.onmessage = (e) => {
    const event = JSON.parse(e.data)
    // event.phase, event.status, event.progress, event.message
    setProgress({...})
}
```

### `frontend/src/StrategyPage.jsx`

**4 Tabs**
1. **Audience Setup:** Input personas, locations, languages, USP
2. **Run Strategy:** Select variants, launch engine, monitor
3. **Results:** Display generated strategies + ROI predictions
4. **Priority Queue:** Articles pending publication

---

## 🔗 Key Connections

### Run Pipeline (main.py)
```python
@app.post("/api/run")
async def start_run(project_id, keyword, pace_dict, generate_articles):
    # 1. Create run record in database
    run = {"run_id": uuid.uuid4(), "project_id": project_id, "seed": keyword}

    # 2. Background: Start Ruflo pipeline
    # ruflo = WiredRufloOrchestrator()
    # result = ruflo.run_seed(keyword, pace, project_id)

    # 3. Stream progress via SSE
    # For each phase:
    #   phase_callback({phase, status, progress, message})
    #   → Emit to client via SSE

    # 4. Save result to runs table

    # 5. Return run_id to client
    return {"run_id": run_id}
```

### Database Flow
```python
# After run completes:
db.execute("""
    INSERT INTO runs (run_id, project_id, seed, status, result, cost_usd)
    VALUES (?, ?, ?, ?, ?, ?)
""", (run_id, project_id, keyword, "completed", json.dumps(result), cost))

# If articles generated:
for article in result["articles"]:
    db.execute("""
        INSERT INTO content_blogs
        (blog_id, project_id, keyword, title, body, status)
        VALUES (?, ?, ?, ?, ?, 'draft')
    """, (uuid.uuid4(), project_id, article["keyword"], ...))
```

---

## 🎯 Common Tasks

### Add a new cross-domain word
1. Edit `quality/annaseo_domain_context.py:CROSS_DOMAIN_VOCABULARY`
2. Add entry: `"word": {Industry.X: "accept", Industry.Y: "reject"}`

### Add a new phase
1. Create class `class PXX_NameOfPhase` in `engines/ruflo_20phase_engine.py`
2. Add to `RufloOrchestrator.__init__()`: `self.pXX = PXX_NameOfPhase()`
3. Add phase execution in `RufloOrchestrator.run_seed()`:
   ```python
   result = self._run_phase("PXX", self.pXX.run, args...)
   ```

### Add a new API endpoint
1. Create route in `main.py`:
   ```python
   @app.post("/api/path")
   async def handler(request_data):
       return {"result": "..."}
   ```
2. Add frontend call in React:
   ```javascript
   const response = await api.post("/api/path", data)
   ```

### Add a new database table
1. Add to `get_db()` CREATE TABLE statement (lines 301-348)
2. Create index if needed
3. Add migration if needed (ALTER TABLE for existing DBs)

---

## ⚡ Performance Tips

1. **Use cache:** `Cache.get_l1(key)` before expensive operations
2. **Stream large sets:** 500-item chunks (Cfg.CHUNK_SIZE)
3. **Memory aware:** Check `MemoryManager.can_run()` before heavy phase
4. **Parallel safe:** Only P2 sources run parallel; P4 + P8 are sequential
5. **Checkpoint aggressive:** Save after each phase for resume capability

---

## 🧪 Testing

```bash
# Run tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_p2_keyword_expansion.py -v

# Test a single phase locally
python -c "
from engines.ruflo_20phase_engine import RufloOrchestrator, ContentPace
r = RufloOrchestrator()
result = r.run_seed('cardamom', pace=ContentPace(), generate_articles=False)
print(result['keyword_count'], result['cluster_count'])
"
```

---

## 📞 Key Support Classes

**Seed** — Represents input keyword
```python
@dataclass
class Seed:
    keyword: str
    language: str
    region: str
    product_url: str = ""
```

**IntentResult** — Intent classification
```python
@dataclass
class IntentResult:
    keyword: str
    primary_intent: str  # informational/commercial/navigational/transactional
    confidence: float  # 0-1
```

**KnowledgeGraph** — Semantic graph
```python
@dataclass
class KnowledgeGraph:
    nodes: List[Dict]  # [{id, label, type, score}]
    edges: List[Dict]  # [{source, target, weight, type}]
```


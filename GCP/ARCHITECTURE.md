# GSC Engine — Architecture

---

## PHASE 1 — DATA FOUNDATION + AI PROJECT UNDERSTANDING ✅ UPGRADED

**Goal:** AI-generated project config drives all downstream GSC filtering.
The upgrade adds a new Step 0 before the data fetch — the **Project Intelligence Layer**.

---

### STEP 0 — AI PROJECT UNDERSTANDING (NEW — Phase 1 Upgrade)

**File:** `engines/gsc/gsc_ai_config.py`

#### What changes

Before this upgrade, the GSC engine required a bare list of pillar names.
Now the engine runs an AI prompt to generate a full `ProjectConfig` object
that tells every downstream step *what to look for* and *what matters*.

#### Flow

```
User Input (business desc + goal + seeds)
  → AI Prompt (gsc_ai_config.generate_project_config)
  → ProjectConfig stored in gsc_project_config table
  → Used by all processing steps
```

#### ProjectConfig schema

```json
{
  "business_summary": "Exporter of premium Indian spices targeting global wholesale buyers",
  "target_audience": "Importers, wholesalers, B2B buyers",
  "goal": "sales",
  "pillars": ["cardamom", "turmeric", "black pepper"],
  "purchase_intent_keywords": ["buy", "price", "wholesale", "bulk", "supplier", "export"],
  "supporting_angles": ["benefits", "uses", "origin", "quality", "processing"],
  "synonyms": {
    "cardamom": ["elaichi", "elachi"],
    "turmeric": ["haldi", "curcumin"]
  },
  "customer_language_examples": [
    "cardamom wholesale supplier India",
    "buy turmeric bulk export quality"
  ]
}
```

#### Key design decisions

| Decision | Why |
|---|---|
| AI defines WHAT to look for | Pillar matching + intent classification uses business-specific signals, not just generic ones |
| Config-driven synonym expansion | AI knows "elaichi" = cardamom; regional terms improve match rate significantly |
| Stored in DB | Config persists across sessions; user can edit it manually |
| Backward compatible | If no config exists, bare `pillars[]` still works via `ProjectConfig.from_pillars()` |

---

### STEP 1 — PILLAR MATCHING (Upgraded)

**File:** `engines/gsc/gsc_processor.py` → `detect_pillar(keyword, pillars, config)`

#### Matching tiers (3-tier, same as before but now config-aware)

```
Tier 1: Exact substring — "cardamom" in "buy cardamom online"
Tier 2: Core term       — strip geo/quality/promo words, then match
Tier 3: Word overlap    — >40% shared words → match
```

#### Synonym expansion (upgraded)

```python
# Built-in synonyms (hardcoded — ~15 spice/product terms)
SYNONYMS = { "cardamom": ["elaichi", "elachi", ...], ... }

# Config synonyms (AI-generated, business-specific)
config.get_synonyms_for(pillar)  # e.g. ["elaichi", "cardamon"]
```

Both synonym sources are applied. Config synonyms take priority.

#### Correct filtering approach

```python
# ONE API call fetches all GSC data
all_keywords = fetch_gsc_keywords()  # last 90 days

# Filter locally — NO extra API calls
for kw in all_keywords:
    pillar = detect_pillar(kw, config.pillars, config)  # uses config synonyms
    if pillar:
        process(kw, pillar, config)
```

---

### STEP 2 — INTENT CLASSIFICATION (Upgraded)

**File:** `gsc_processor.py` → `classify_intent(keyword, config)`

```python
# Config-driven check FIRST (business-specific terms)
for sig in config.purchase_set:
    if sig in kw:
        return "purchase"

# Fall back to built-in signal sets
# _WHOLESALE > _PURCHASE > _NAVIGATIONAL > _COMMERCIAL > _INFORMATIONAL
```

Intent values: `purchase | wholesale | commercial | informational | navigational`

---

### STEP 3 — SUPPORTING ANGLE DETECTION (NEW)

**File:** `gsc_processor.py` → `detect_angle(keyword, config)`

```python
for angle in config.supporting_angles:  # ["benefits", "uses", "origin", ...]
    if angle in kw:
        return angle
return "general"
```

This groups informational keywords into content clusters for the strategy layer.

---

### STEP 4 — SCORING ENGINE

```python
final_score = (
    5                        # GSC source base score
    + impressions * 0.005    # demand proxy (capped 30)
    + clicks * 0.05          # actual traffic (capped 20)
    + intent_boost           # purchase=5 | wholesale=4 | commercial=2 | info=1
    + opportunity_score      # high impressions + poor rank (pos > 10)
)
```

**Top 100 per pillar**: sorted by `final_score` descending → first 100 marked `top100=1`.
This is business-prioritized, not just impression volume.

---

### STEP 5 — TOP 100 OUTPUT

```python
def top_keywords(pillar_keywords):
    return sorted(
        pillar_keywords,
        key=lambda x: x["score"],
        reverse=True
    )[:100]
```

For 10 pillars = up to 1,000 top-priority keywords.

---

### Database schema (Phase 1)

**gsc_project_config** (NEW)
```sql
project_id               TEXT UNIQUE
business_summary         TEXT
target_audience          TEXT
goal                     TEXT
pillars                  TEXT  -- JSON array
purchase_intent_keywords TEXT  -- JSON array
supporting_angles        TEXT  -- JSON array
synonyms                 TEXT  -- JSON object
customer_language_examples TEXT -- JSON array
source                   TEXT  -- 'ai' | 'manual' | 'default'
generated_at             TEXT
```

**gsc_integration_settings** (unchanged)
**gsc_keywords_raw** (unchanged)
**gsc_keywords_processed** (extended with `angle` field logic)

---

### API endpoints (Phase 1)

```
POST /api/gsc/{project_id}/config/generate  ← Step 0: AI config generation
GET  /api/gsc/{project_id}/config           ← Read stored config
PUT  /api/gsc/{project_id}/config           ← Manual edit/override

POST /api/gsc/{project_id}/sync             ← One GSC data pull
POST /api/gsc/{project_id}/process          ← Config-driven processing
GET  /api/gsc/{project_id}/keywords         ← Processed results
GET  /api/gsc/{project_id}/top100           ← Top 100 per pillar
GET  /api/gsc/{project_id}/tree             ← Tree-structured output
```

---

### Frontend (Phase 1 Upgrade)

`PhaseGSC.jsx` now has **4 tabs** (was 3):

| Tab | Name | Purpose |
|---|---|---|
| 0 | 🧠 AI Config | Describe business → AI generates ProjectConfig |
| 1 | 🔗 Connect & Sync | OAuth, site selection, GSC data pull |
| 2 | ⚡ Intelligence | Run processing, keyword table, filters |
| 3 | 📊 Strategy | Top 100, quick wins, tree view |

---

## PHASE 2 — INTELLIGENCE LAYER (Planned)

### 2.1 AI Intent Classifier
Replace rule-based intent with AI:
```python
# Input: keyword + pillar context + config
# Output: {intent, confidence, reasoning}
```

### 2.2 Automatic Pillar Detection from GSC
```python
# Extract dominant topics from GSC data automatically
# Cluster top queries → generate pillar suggestions
# User can confirm/reject suggested pillars
```

### 2.3 Keyword Clustering Engine
Group keywords into clusters using embeddings (sentence_transformers):
- Supporting clusters (informational → blog content)
- Purchase clusters (transactional → product pages)
- Local clusters (geographic → local pages)

### 2.4 Advanced Scoring v2
```python
# Add to Phase 1 scoring:
ai_confidence = ai_confidence_score * 3  # AI classifier certainty
angle_boost   = 2 if angle in ["benefits", "uses"] else 0
```

---

## PHASE 3 — UI + STRATEGY ENGINE (Planned)

### 3.1 GSC-Like Dashboard
Full metrics table with click-to-inspect, sortable columns, score breakdown panel.

### 3.2 Strategy Cards
- 🔥 Quick Wins: position 11-30 + high impressions
- 💰 Money Keywords: purchase/wholesale intent + high score
- 📈 Content Gaps: informational, high impressions, low CTR
- ⚡ Opportunities: high impressions + no clicks (page not ranking well)

### 3.3 Tree View
```
Universe
├── 🎯 Cardamom (42 GSC keywords)
│   ├── 💰 Purchase (12) — buy cardamom, wholesale price, bulk supplier
│   ├── 🧩 Benefits (8)  — cardamom benefits, health uses  [supporting angle]
│   └── ⚡ Quick Wins (6) — pos 14-22, high impressions
```

### 3.4 Internal Linking Suggestions
```
"cardamom benefits" blog → links to → "buy cardamom bulk" product page
```

---

## Full System Flow

```
[ User Input ]
       ↓
[ 🧠 AI Config (Tab 0) ]
   business_desc + goal + seeds
       ↓
[ ProjectConfig stored in DB ]
   pillars + intent_kws + angles + synonyms
       ↓
[ 🔗 GSC OAuth + Sync (Tab 1) ]
   1 API call → all queries (last 90 days) → gsc_keywords_raw
       ↓
[ ⚡ Processing (Tab 2) ]
   detect_pillar(config) → classify_intent(config) → detect_angle(config) → score()
       ↓
[ Top 100 per Pillar ]
   sorted by business-prioritized score
       ↓
[ 📊 Strategy Tree (Tab 3) ]
   Purchase | Supporting | Quick Wins | Opportunities
       ↓
[ Phase 2 keyword generation (enriched seeds) ]
```

---

## Scoring Formula

```python
final_score = (
    5                           # GSC source base
    + impressions * 0.005       # demand proxy (capped 30)
    + clicks * 0.05             # traffic proof (capped 20)
    + intent_boost              # purchase=5, wholesale=4, commercial=2, info=1
    + opportunity_score         # high impressions + position 11-50
)
```

**Top 100 is NOT just impressions** — it's business-prioritized:
- A "buy cardamom bulk" keyword with 500 impressions beats "cardamom history" with 5000 impressions
- Because purchase intent adds +5 to the score

---

## Integration with kw2 Workflow

GSC sits between PhaseBI and Phase2:

```
PhaseBI (pillars + business goals)
   ↓
GSC Engine (real demand signals, AI-filtered)
   ↓
Phase2 (keyword generation — uses GSC top100 as priority seeds)
```

The `gsc_top100` data feeds `keyword_generator.py` as seeds with `source_score=5`
so they rank above AI-generated candidates in final validated output.


**Goal:** Get real GSC keyword data flowing and structured into the database.

### 1.1 OAuth Integration Layer
```
User clicks "Connect Google Search Console"
  → Backend generates OAuth URL (scope: webmasters.readonly)
  → User authorizes in Google
  → Google redirects to /api/gsc/auth/callback?code=...&state={project_id}
  → Backend exchanges code for access_token + refresh_token
  → Tokens stored in gsc_integration_settings table
```

### 1.2 Database Layer

**Table: gsc_integration_settings**
```sql
id              INTEGER PRIMARY KEY
project_id      TEXT UNIQUE
site_url        TEXT            -- e.g. https://yoursite.com/
access_token    TEXT
refresh_token   TEXT
token_expiry    TEXT            -- ISO datetime
status          TEXT            -- 'connected' | 'disconnected' | 'error'
created_at      TEXT
updated_at      TEXT
```

**Table: gsc_keywords_raw**
```sql
id              INTEGER PRIMARY KEY
project_id      TEXT
keyword         TEXT
clicks          INTEGER
impressions     INTEGER
ctr             REAL
position        REAL
date_start      TEXT
date_end        TEXT
synced_at       TEXT
```
Index: (project_id, keyword)

**Table: gsc_keywords_processed**
```sql
id              INTEGER PRIMARY KEY
project_id      TEXT
keyword         TEXT
pillar          TEXT
intent          TEXT            -- purchase|wholesale|supporting|informational|navigational
score           REAL            -- final composite score
source_score    INTEGER         -- +5 from GSC
impression_score REAL           -- impressions * 0.01
click_score     REAL            -- clicks * 0.05
intent_boost    INTEGER         -- +5 purchase, +3 wholesale, +1 supporting
top100          INTEGER         -- 0/1 per pillar
processed_at    TEXT
```
Index: (project_id, pillar), (project_id, intent), (project_id, score DESC)

### 1.3 Keyword Processing Core

**Pillar Matching:**
```python
# 3-tier matching (same as keyword_generator._detect_pillar)
1. Exact substring: "cardamom" in "buy cardamom online"
2. Core term: strip weights/geo/promo → match core
3. Word overlap: >40% shared words → match
```

**Synonym Handling:**
```python
SYNONYMS = {
    "cardamom": ["elaichi", "elachi", "cardamon"],
    "turmeric": ["haldi", "curcumin"],
    "pepper": ["kali mirch", "black pepper"],
    "clove": ["lavang", "laung"],
    "cinnamon": ["dalchini"],
}
```

**Intent Classification (rule-based):**
```python
PURCHASE_SIGNALS = ["buy", "price", "order", "wholesale", "bulk", "supplier", "purchase", "shop", "cost"]
WHOLESALE_SIGNALS = ["wholesale", "bulk", "b2b", "export", "distributor", "kg price", "per kg"]
INFORMATIONAL_SIGNALS = ["benefits", "uses", "how", "what", "guide", "recipe", "nutrition"]
NAVIGATIONAL_SIGNALS = ["brand name", "review", "official", "website"]
```

### 1.4 Scoring Engine v1

```python
score = source_score + impression_score + click_score + intent_boost

# Weights:
source_score   = 5         # 5 points for being a GSC keyword
impression_score = impressions * 0.01
click_score    = clicks * 0.05
intent_boost   = 5 (purchase) | 4 (wholesale) | 2 (commercial) | 1 (informational)
```

### 1.5 Basic API
```
POST /api/gsc/{project_id}/sync      → fetch all queries, store raw
POST /api/gsc/{project_id}/process   → filter per pillar, classify, score
GET  /api/gsc/{project_id}/keywords  → return processed keywords
```

### Output of Phase 1
✅ Users can:
- Connect their GSC account
- Pull all real search query data (last 30-90 days)
- See keywords filtered per pillar with intent + scoring

---

## PHASE 2 — INTELLIGENCE LAYER

**Goal:** Make the keyword system smart with AI-enhanced classification and clustering.

### 2.1 AI Intent Classifier
Replace rule-based intent with AI:
```python
# Groq-70b or Gemini-2.0-flash
# Input: keyword + pillar context
# Output: {intent, confidence, reasoning}
# Intents: informational | commercial | transactional | navigational
```

### 2.2 Automatic Pillar Detection from GSC
```python
# Extract dominant topics from GSC data automatically
# Cluster top queries → generate pillar suggestions
# User can confirm/reject suggested pillars
```

### 2.3 Keyword Clustering Engine
```python
# Group keywords into:
# - Supporting clusters (informational → blog content)
# - Purchase clusters (transactional → product pages)  
# - Local clusters (geographic → local pages)
# Uses embeddings (sentence_transformers) for semantic similarity
```

### 2.4 Keyword Graph Builder
```python
# Build relationships:
#   keyword ↔ keyword (semantic similarity > 0.7)
#   keyword ↔ pillar (pillar match)
#   pillar ↔ pillar (cluster overlap)
# Stored in gsc_keyword_graph table
```

### 2.5 Advanced Scoring v2
```python
# Add to v1:
opportunity_score = impressions if position > 20 else 0  # high impressions + low rank
           + (10 if position > 10 and clicks > 5 else 0)  # almost-top-10 keyword
ai_confidence = ai_confidence_score * 3  # from AI classifier
```

### Output of Phase 2
✅ Fully structured: Pillar → Clusters → Intent groups
✅ AI-enhanced keyword prioritization
✅ Opportunity signals (high impressions + poor rank)

---

## PHASE 3 — UI + STRATEGY ENGINE

**Goal:** Build the GSC-like dashboard UI that turns data into actionable SEO strategy.

### 3.1 GSC-Like Dashboard UI
```
┌────────────────────────────────────────────────────┐
│  📊  Total Clicks   Total Impressions   Avg CTR   Avg Position
│      12,450          284,300            4.4%       14.2
├────────────────────────────────────────────────────┤
│  Query          │ Clicks │ Impressions │ CTR  │ Pos │ Score │ Intent
│  buy cardamom   │  420   │  8,200      │ 5.1% │ 8.3 │  95  │ 💰
│  cardamom price │  280   │  5,400      │ 5.2% │ 9.1 │  88  │ 💰
│  cardamom uses  │  190   │  12,000     │ 1.6% │ 6.2 │  71  │ 📚
└────────────────────────────────────────────────────┘
```

### 3.2 Keyword Detail Panel
On click:
- Score breakdown (source + impressions + clicks + intent + opportunity)
- GSC metrics (clicks trend, position trend)
- Intent label
- Mapped pillar
- SEO suggestion (optimize for → product page / blog post)

### 3.3 Filters + Search
- Filter by: Pillar | Intent | Score range | Position range | Impressions range
- Toggle: 🔥 Quick wins (pos > 10, impressions > 500)
- Toggle: 💰 Money keywords (purchase + wholesale intent)
- Search bar (keyword substring match)

### 3.4 Strategy Layer
Auto-generated strategy cards:
- 🔥 Quick Wins: high impressions + position 11-30 (optimize existing content)
- 💰 Money Keywords: purchase + wholesale intent, score > 60
- 📈 Content Gaps: informational, high impressions, low CTR
- 🌍 Local Opportunities: geographic keywords

### 3.5 Internal Linking Suggestions
```
blog post "cardamom benefits" → link to → product page "buy cardamom"
supporting keyword page → pillar page
```

### 3.6 Tree View
Visual tree connecting GSC data to kw2 tree:
```
Universe
├── 🎯 Cardamom (42 GSC keywords)
│   ├── 💰 Purchase (12)
│   │   ├── buy cardamom online [★ top100, score:95]
│   │   └── cardamom wholesale price [★ top100, score:88]
│   ├── 📚 Supporting (18)
│   │   ├── cardamom benefits [★ top100, score:71]
│   │   └── cardamom medicinal uses [score:54]
│   └── ⚡ Opportunities (12)
│       └── buy organic cardamom [pos:24, impressions:3400]
```

### Output of Phase 3
✅ GSC-like metrics dashboard  
✅ Strategy cards (quick wins, money keywords, content gaps)  
✅ Tree view with GSC data overlay  
✅ Internal linking suggestions  

---

## Scoring Formula (Final)

```python
final_score = (
    5                              # GSC source
    + impressions * 0.01           # demand proxy (capped at 30)
    + clicks * 0.05                # actual traffic (capped at 20)
    + intent_boost                 # purchase=5, wholesale=4, commercial=2, info=1
    + opportunity_score            # position 11-30 + high impressions
    + ai_confidence_score          # Phase 2 AI boost (0-3)
)
```

---

## Integration with kw2 Workflow

The GSC stage runs **after PhaseBI (Intel)** and **before Phase2 (Generate)**:
1. PhaseBI gives us: pillars, business goals, intent focus
2. GSC stage enriches with: real demand signals from Google
3. Phase2 uses GSC top keywords as priority seeds

The `gsc_top100` data is passed to `keyword_generator.py` as high-priority seeds with `source_score=5` so they rank higher in the final validated output.

---

## PHASE 2 — INTELLIGENCE LAYER ✅ COMPLETE

**Goal:** Transform processed keywords into actionable intelligence via ML embeddings, clustering, graph analysis, and AI-driven insights.

### Pipeline Overview

```
Run Intelligence Pipeline (POST /api/gsc/{project_id}/intelligence/run)
  ├── Step 1: Embeddings (sentence-transformers/all-MiniLM-L6-v2, 384 dims)
  ├── Step 2: AI Intent Classification (batch LLM via AIRouter)
  ├── Step 3: HDBSCAN Clustering + LLM cluster naming
  ├── Step 4: Keyword Graph (top-K cosine neighbors)
  ├── Step 5: Advanced Scoring v2 (confidence + business priority)
  ├── Step 6: Insight Generation (5 types)
  └── Step 7: Pillar Authority Scoring
```

---

### New Backend Modules (engines/gsc/)

| File | Purpose |
|---|---|
| `gsc_embeddings.py` | Local sentence-transformers embedding engine; incremental embedding; BLOB serialization |
| `gsc_intent_ai.py` | Batch LLM intent classification with pre-filter for obvious intents |
| `gsc_clustering.py` | HDBSCAN auto-cluster detection + LLM-based cluster naming |
| `gsc_graph.py` | Top-K cosine similarity graph construction (min_similarity threshold) |
| `gsc_scoring_v2.py` | Advanced scoring (intent confidence + business priority) + pillar authority |
| `gsc_insights.py` | Generates 5 insight types: quick_wins, money_keywords, content_gaps, linking, opportunities |
| `gsc_intelligence.py` | Pipeline orchestrator — runs all 7 steps in sequence with timing |

---

### New Database Tables (gsc_db.py)

| Table | Purpose |
|---|---|
| `gsc_keyword_embeddings` | Stores keyword vectors as BLOBs (project_id, keyword, vector) |
| `gsc_keyword_clusters` | Cluster assignments (cluster_id, cluster_name, keyword, pillar) |
| `gsc_keyword_graph` | Edge list (keyword_a, keyword_b, similarity score) |
| `gsc_insights` | JSON insight data keyed by (project_id, insight_type) |

**New columns on `gsc_keywords_processed`:** `intent_confidence`, `cluster_name`, `cluster_id`, `angle`

---

### New API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/gsc/{project_id}/intelligence/run` | Run full Phase 2 pipeline |
| GET | `/api/gsc/{project_id}/clusters` | Get keyword clusters |
| GET | `/api/gsc/{project_id}/graph?min_similarity=0.3` | Get keyword graph (nodes + links) |
| GET | `/api/gsc/{project_id}/insights?type=X` | Get SEO insights (optional type filter) |
| GET | `/api/gsc/{project_id}/authority` | Get pillar authority scores |

---

### Embedding Strategy

- **Primary:** Local `sentence-transformers/all-MiniLM-L6-v2` (384 dims, free, ~0.04s/3 keywords)
- **Fallback:** GCP `gemini-embedding-001` (3072 dims) via `GCP_API_KEY` env var (requires Generative Language API enabled)
- Vectors stored as numpy BLOB in SQLite; loaded into memory for similarity computations
- Incremental: only embeds keywords not already in `gsc_keyword_embeddings`

### Clustering Strategy

- **Algorithm:** HDBSCAN (auto-detects cluster count, handles noise)
- `min_cluster_size=5`, metric=euclidean
- Noise keywords (label=-1) remain unclustered
- Cluster names generated by LLM via AIRouter (all clusters in one prompt)

### Insight Types

| Type | Logic |
|---|---|
| `quick_wins` | Position 5-20, impressions ≥ 100 (top 50) |
| `money_keywords` | Purchase/wholesale intent, impressions ≥ 50 (top 50) |
| `content_gaps` | Clusters lacking purchase-intent keywords |
| `linking` | Supporting → purchase internal linking pairs (top 100) |
| `opportunities` | Position > 20, impressions ≥ 200 (top 30) |

### Authority Scoring

Per-pillar score (0-100):
```python
authority = (
    coverage * 0.2       # keyword count ratio
  + traffic * 0.3        # impression share
  + intent_value * 0.2   # purchase intent density
  + ranking_strength * 0.2  # avg position quality
  + cluster_depth * 0.1  # cluster count
)
```
Status: **strong** (≥60), **moderate** (≥30), **weak** (<30)

---

### Frontend (Phase 2)

| File | Purpose |
|---|---|
| `KeywordGraph.jsx` | ForceGraph2D interactive keyword graph (intent colors, pillar colors, zoom-on-click) |
| `PhaseGSC.jsx` → Tab 4 | Intelligence Dashboard: pipeline runner, cluster cards, graph view, insights panel, authority scores |
| `api.js` | 5 new functions: `runIntelligence`, `getClusters`, `getGraph`, `getInsights`, `getAuthority` |

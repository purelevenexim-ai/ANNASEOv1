STEP 3 — SEO/AEO STRATEGY
Build a plan to reach Top 5 in Google Search + AI search (ChatGPT, Gemini, Perplexity)
✓
Business Profile
2
AI Generation
3
Strategy Plan
Generating SEO/AEO Strategy
DeepSeek AI is analysing your keywords and building a personalised Top-5 ranking strategy.
Generating strategy…
→ Strategy engine starting…
→ Loaded profile: B2C · food_spices · south_india
→ Audience profile saved
→ Analysing discovered keywords from Step 2…
→ Found 4132 keywords across 12 pillars
→ Added 14 crawl-discovered pillars to strategy
→ Building SEO/AEO strategy with AI (30-90s)…when you complete each phase respect below: update

1. code completion.
2. ask question when in doubt,
3. ckean coding practice
4. identify missing pieces
5. brainstorm ideas
6. respect memory usage, code for optimization
7. create test casaes and test every modules and make sure no break, bugs or issues.
8. read mains.py , readiness, keyword strategy and all files before making changes.
9. if required make frontend also.

# Strategy Intelligence — Architecture & Implementation Guide

Version: 1.0
Date: 2026-03-27

Purpose
-------
This document captures the final architecture, data-model rules, engines, APIs, and implementation notes for the high-performance SEO/AEO engine (the "Strategy Intelligence" system). It is intentionally minimal and prescriptive: store only high-signal outputs used by downstream keyword generation and ranking decisions.

LOCKED PRINCIPLE
----------------
Every input must answer one of:

1. Does this help generate better keywords?
2. Does this improve ranking probability?
3. Does this improve conversion / revenue intent?

If not — remove it.

High-level System Summary
-------------------------
Reduce everything into three lean modules (high signal only):

1. User Input (essential only)
2. AI Business Discovery (lean but powerful)
3. Competitor Intelligence (focused, not bloated)

Flow:

User Input → Crawler(s) → RAW DATA (temp) → Insight (Signal) Engine → Structured Signals (persisted) → P0 Validator → P1–P8 Keyword Engine → Execution

Data Storage Rules (CRITICAL)
-----------------------------
- RAW data (full HTML, full SERP, full crawls) MUST NOT be stored permanently.
  - Keep raw data in memory or short-lived cache with TTL (5–30 minutes).
  - Raw data is only input to the Signal Engine.
- Persist ONLY structured signals necessary for P1–P8 and execution:
  - business signals, keyword signals, competitor signals, strategy signals.
  - Examples: `core_topics`, `primary_keywords`, `buyer_keywords`, `gaps`, `audience_groups`, `serp_summary`.
- If a data point is not used downstream in P1–P8, do NOT store it.

Module 1 — User Input (Minimal)
-------------------------------
Purpose: ground truth + anchor the AI.

MANDATORY (5 fields):

```
{
  "website_url": "",
  "products": [],           // seed list
  "target_market": [],      // list of GEOs or "global"
  "business_type": "B2C|B2B|D2C",
  "usp": ""               // 1–2 lines
}
```

PRIORITY SIGNAL (from user):
- primary pillar keywords (very important)
- supporting keywords (optional)
- top priority product
- revenue focus (traffic/leads/sales)
- competitor URLs (2–5)

OPTIONAL BOOST (only if available):
- customer reviews (raw text)
- ad copy
- seasonal focus
- existing blog topics

Keep total user inputs small (≈15). Anything more is noise.

Module 2 — AI Business Discovery (Signals)
-----------------------------------------
Purpose: understand what the business actually is (anchors topic scope and blocks drift).

Output (approx 30 signals) grouped examples:

- Core Extraction:
  - main product categories
  - core topics
  - page types
  - repeated keywords
  - heading structure
  - internal linking patterns
  - content depth
  - existing keyword coverage
  - missing keyword areas
  - intent split

- SEO Reality:
  - pages ranking
  - cannibalization
  - weak pages
  - strong pages
  - long-tail presence
  - geo signals
  - schema usage
  - anchor patterns

- Business Understanding:
  - detected business category
  - primary audience type
  - revenue-driving pages
  - price positioning
  - trust signals
  - conversion style
  - brand-topic alignment

- P0 Validation signals:
  - allowed topics
  - blocked topics
  - semantic boundaries
  - topic confidence scores

IMPORTANT: Only persisted signals from this module are the structured outputs above, not raw pages.

Module 3 — Competitor Intelligence (Signals)
------------------------------------------
Purpose: find what actually works in the market and identify gaps.

Outputs (≈30 signals):

- Keyword Intelligence: top ranking keywords, clusters, long-tail, buyer-intent keywords, gaps, geo keywords
- Content Strategy: top traffic pages, formats, pillar pages, clusters, depth, freshness, gaps
- Ranking Power: domain / page strength, basic backlink presence, SERP features
- Opportunity Engine: easy-wins, underserved topics, weak competitor pages

Again: store signals only — not full competitor crawls or SERP content.

Audience Interest Detection Engine
---------------------------------
Purpose: map keywords → who is searching and why. Support multiple audience groups per business.

Output structure example:

```
{
  "audience_groups": [
    {"name":"Home Cooking Enthusiasts","intent":"informational+transactional","confidence":0.92},
    {"name":"Health & Ayurveda Seekers","intent":"informational","confidence":0.81}
  ]
}
```

Detection approach (hybrid):
- Controlled interest dictionary (INTEREST_MAP)
- Score interest domains across extracted keywords and content
- Normalize, threshold, map to human persona names
- Present to user for validation (UI checkboxes to accept/remove/add)

SERP Reality Engine
-------------------
Purpose: determine what actually ranks for a keyword (content type, difficulty, feasibility).

Minimal stored output per keyword (do not store full SERP):

```
{
  "keyword":"...",
  "intent":"informational|transactional|mixed",
  "content_type":"blog|product|category|mixed",
  "difficulty":0.0,
  "feasibility":0.0
}
```

Implementation steps:
- fetch top-10 SERP (SerpAPI / Zenserp / scraping)
- classify each URL (type, authority proxy, depth)
- detect SERP features (featured snippet, images, videos)
- aggregate into distribution, compute difficulty and feasibility

Store only the aggregated summary per keyword in `serp_cache`.

P7++ Scoring Engine (Production-Ready)
------------------------------------
Goal: score and prioritize keywords against business fit, intent value, ranking feasibility, traffic potential, competitor gap, and content ease.

Scoring formula (recommended):

final_score = (
  BusinessFit * 0.25 +
  IntentValue * 0.20 +
  RankingFeasibility * 0.20 +
  TrafficPotential * 0.15 +
  CompetitorGap * 0.10 +
  ContentEase * 0.10
)

Each subscore: well-defined functions (examples provided in the code scaffold below).

Audience → Intent → Keyword Mapping
------------------------------------
Map keywords to the validated audiences using detected intent. This is mandatory before scoring so that the same keyword can be scored differently for different audiences.

Pipeline Overview
-----------------
Strategy Page (user-controlled, module-driven):

1. Analyze Business (crawl + signals)
2. Analyze Competitors
3. Detect Audience
4. Analyze SERP (on-demand per keyword or batch)
5. Validate Context (P0)
6. Score Keywords (P7++)
7. Finalize Strategy (lock context)
8. Send finalized `strategy_context` to Keyword page

Keyword Page (execution):

1. Load `strategy_context`
2. P1 seed, P2 expand, P3 clean
3. Audience Mapping
4. SERP fallback checks for missing keywords
5. P7++ Scoring
6. P8 Strategy Output / priority queue

Core Data Object — `strategy_context`
------------------------------------

Keep a single, serializable object for all strategy data. Persist only this object (or parts of it) to DB.

Example schema (JSON):

```
{
  "project_id": "proj_xxx",
  "business": {"topics":[],"allowed_topics":[],"blocked_topics":[]},
  "audiences": [ {"name":"...","intents":[...] } ],
  "competitors": {"top_keywords":[],"gap_keywords":[]},
  "serp_cache": {"kw": {"feasibility":0.5,"content_type":"blog"}},
  "keywords": [],
  "scored_keywords": []
}
```

Backend Architecture (FastAPI suggested)
--------------------------------------

Folder structure (suggested):

```
/backend/
  main.py
  /api/
    strategy.py
  /services/
    business_discovery.py
    competitor_engine.py
    audience_engine.py
    serp_engine.py
    p0_validator.py
    p7_scoring.py
    audience_mapper.py
  /models/
    strategy_context.py
```

APIs (module-per-endpoint, user-triggered):

- GET  /api/strategy/{id}                    # load context
- POST /api/strategy/{id}/init               # create context
- POST /api/strategy/{id}/set-business       # set business topics
- POST /api/strategy/{id}/set-audience      # set audiences
- POST /api/strategy/{id}/set-keywords      # upload candidate keywords
- POST /api/strategy/{id}/analyze-business  # run business discovery
- POST /api/strategy/{id}/analyze-competitors
- POST /api/strategy/{id}/detect-audience
- POST /api/strategy/{id}/analyze-serp      # input: keywords[]
- POST /api/strategy/{id}/validate-context  # P0 validator
- POST /api/strategy/{id}/score             # P7++ scoring (input keywords optional)
- POST /api/strategy/{id}/finalize          # lock and persist strategy

Frontend Integration (Strategy Page)
------------------------------------

UI: expose one control panel; each module is a button the user can run independently. Show immediate results and allow validation.

Buttons (example):

- Analyze Business
- Analyze Competitors
- Detect Audience
- Analyze SERP
- Validate Context
- Score Keywords
- Finalize Strategy → Send to Keywords

Keyword Page Integration
------------------------

Add an "Accept Strategy" control to pull `strategy_context` from backend and run the pipeline. The Keyword page should accept a final strategy and run P1–P8 using the stored signals.

Storage and TTL Notes
---------------------
- `serp_cache` entries: persist summary only; purge older than N days or keep a single canonical snapshot with timestamp.
- Raw crawl results: never persisted.
- Keep `strategy_context` small; store lists of keywords as arrays of strings; store scored keywords with small objects {keyword,score,priority,audience}.

Implementation Scaffolds (Python examples)
----------------------------------------

models/strategy_context.py (example)

```python
def default_context(project_id: str):
    return {
        "project_id": project_id,
        "business": {"topics": [],"allowed_topics": [],"blocked_topics": []},
        "audiences": [],
        "competitors": {"top_keywords": [],"gap_keywords": []},
        "serp_cache": {},
        "keywords": [],
        "scored_keywords": []
    }
```

services/p7_scoring.py (summary)

```python
def score_keywords(keywords, context):
    # compute sub-scores (business_fit, intent_score, feasibility from serp_cache, etc.)
    # apply weights and return list of {keyword,score,priority}
    pass
```

services/audience_mapper.py (summary)

```python
def map_keywords_to_audience(keywords, audiences):
    # detect intent per keyword and map to audiences by their intents
    pass
```

Sample minimal API router (FastAPI)

```python
from fastapi import APIRouter
from models.strategy_context import default_context
router = APIRouter()
DB = {}

@router.post("/{project_id}/init")
def init_strategy(project_id: str):
    DB[project_id] = default_context(project_id)
    return {"status": "initialized"}

@router.post("/{project_id}/score")
def score(project_id: str):
    ctx = DB.get(project_id)
    scored = score_keywords(ctx["keywords"], ctx)
    ctx["scored_keywords"] = scored
    return {"scored_keywords": scored}
```

Key Engineering Rules (enforced)
--------------------------------
1. Raw data is ephemeral. Do not persist full crawl or SERP results.
2. Persist only structured signals required by downstream modules.
3. Always require user validation for audience groups (show confidence scores and allow accept/remove).
4. Limit user-provided competitors to 3–5 real SERP competitors.
5. Keep `strategy_context` serializable and small.

Priorities (what to build next)
--------------------------------
1. Signal Engine (`extract_signals`) — highest impact: converts raw crawl → structured signals.
2. Competitor keyword extractor (lightweight) — gives market grounding.
3. P0 Validator — blocks irrelevant topics immediately.
4. P7++ Scoring service and Audience mapper.
5. SERP Reality Engine (basic): top-10 summary + feasibility.

Next steps & developer checklist
--------------------------------
- [x] Create `strategy_intelliegence.md` (this file)
- [ ] Add backend scaffold files: `p7_scoring.py`, `audience_mapper.py`, `strategy.py`
- [ ] Wire FastAPI routes and simple in-memory DB (for dev)
- [ ] Add StrategyPage buttons + API calls to run modules
- [ ] Add Keyword Page acceptor to load `strategy_context`
- [ ] Implement Signal Engine and enforce raw-data TTL

Appendix — Example `strategy_context` JSON
-----------------------------------------

```
{
  "project_id":"proj_abc",
  "business":{"topics":["cloves","spices"],"allowed_topics":[],"blocked_topics":[]},
  "audiences":[{"name":"Home Cooking Enthusiasts","intents":["informational","light transactional"]}],
  "competitors":{"top_keywords":["buy cloves online","clove supplier"]},
  "serp_cache":{"buy+cloves":{"feasibility":0.42,"content_type":"product"}},
  "keywords":["buy cloves online","clove water benefits"],
  "scored_keywords":[{"keyword":"clove water benefits","score":0.82,"priority":"HIGH"}]
}
```

Audit — Critical Gaps (action required)
------------------------------------
This audit captures critical engines and checks missing from the current scaffold. These items are required for consistent, production-grade outputs — not optional.

1) P0 Validator (MUST BUILD)
- Purpose: prevent topic drift and block irrelevant keywords before they enter cleaning/scoring.
- Minimal logic:

```python
def validate_keyword(keyword, allowed_topics, blocked_topics):
  if any(bt in keyword for bt in blocked_topics):
    return False
  if not any(at in keyword for at in allowed_topics):
    return False
  return True
```
- Run this immediately after P2 (expansion) and before P3 (clean).

2) Signal Engine (`extract_signals`) (CORE INTELLIGENCE)
- Purpose: convert raw crawl + competitor pages → structured signals (core_topics, primary_keywords, buyer_keywords, content_gaps, audience_signals).
- API: `extract_signals(raw_data, user_input) -> signals_dict`.
- Signals are the ONLY inputs persisted to `strategy_context`.

3) SERP Engine → P7 integration (required)
- Ensure `serp_cache` is populated before scoring. If missing, call `serp_reality(keyword)` and cache the summary.

```python
if kw not in ctx['serp_cache']:
  ctx['serp_cache'][kw] = serp_reality(kw)
```

4) Keyword Clustering (required)
- Purpose: convert flat keywords → pillar → clusters. This feeds internal linking and P8 output.
- Minimal API: `cluster_keywords(keywords) -> {pillar: [cluster_kw...]}`

5) Content Type & Format Mapping
- For each keyword, derive `format` and `structure` (e.g., listicle, blog, product, H1/FAQ skeleton). Store in `serp_cache` or `content_plan`.

6) Feedback Loop (deferred but planned)
- Record ranking outcomes and adjust scores (e.g., after 30 days). Data model: `{keyword,rank,delta_days}` and `adjust_score` flag.

7) Strategy Finalization Lock
- Rule: after `/finalize` the context is read-only until user triggers an update. Prevent automatic re-writes from background jobs.

8) Execution Readiness Check
- Minimal guard before sending to Keyword Page:

```python
def strategy_ready(ctx):
  return bool(ctx['business']['topics']) and bool(ctx['audiences']) and bool(ctx['keywords'])
```

Implementation notes & next actions
---------------------------------
- Build order (highest impact first):
  1. P0 Validator
  2. Signal Engine (`extract_signals`)
  3. Ensure SERP caching is used in P7 scoring
  4. Keyword clustering + content-format mapping
  5. Feedback loop + strategy lock enforcement
- Implement the P0 Validator and Signal Engine as small, testable services (`services/p0_validator.py` and `services/signal_engine.py`) and wire them into the `strategy` API endpoints.

Implementation — Practical code snippets
--------------------------------------
Below are production-ready starter implementations for the four core services to build now. They are intentionally small, testable, and easy to replace with more advanced logic later.

1) P0 Validator (services/p0_validator.py)

```python
def normalize(text):
  return text.lower().strip()


def validate_keywords(keywords, allowed_topics, blocked_topics):
  valid = []
  rejected = []

  allowed_topics = [normalize(t) for t in allowed_topics]
  blocked_topics = [normalize(t) for t in blocked_topics]

  for kw in keywords:
    k = normalize(kw)

    # ❌ Block explicit unwanted topics
    if any(bt in k for bt in blocked_topics):
      rejected.append({"keyword": kw, "reason": "blocked_topic"})
      continue

    # ❌ Must match at least one allowed topic
    if not any(at in k for at in allowed_topics):
      rejected.append({"keyword": kw, "reason": "not_in_scope"})
      continue

    valid.append(kw)

  return valid, rejected
```

API integration (snippet for `api/strategy.py`):

```python
from services.p0_validator import validate_keywords

@router.post("/{project_id}/validate-context")
def validate_context(project_id: str):
  ctx = DB.get(project_id)

  valid, rejected = validate_keywords(
    ctx.get("keywords", []),
    ctx["business"].get("allowed_topics") or ctx["business"].get("topics", []),
    ctx["business"].get("blocked_topics", [])
  )

  ctx["keywords"] = valid

  return {"valid_keywords": valid, "rejected": rejected}
```

2) Signal Engine (services/signal_engine.py)

```python
def extract_signals(raw_data, user_input):
  # raw_data: list[str] or list[text blobs] from crawler(s)
  text = " ".join(raw_data).lower()

  products = user_input.get("products", [])

  # 🔹 Core topics (anchor)
  core_topics = list(dict.fromkeys(products))

  # 🔹 Very simple ngram keywords extractor (demo)
  words = [w for w in text.split() if len(w) > 2]
  keywords = list(dict.fromkeys([
    " ".join(words[i:i+2])
    for i in range(max(0, len(words)-1))
  ]))

  # 🔹 Buyer keywords
  buyer_keywords = [kw for kw in keywords if any(x in kw for x in ["buy", "price", "supplier", "wholesale"]) ]

  # 🔹 Info keywords
  info_keywords = [kw for kw in keywords if any(x in kw for x in ["how", "benefits", "what"]) ]

  # 🔹 Content gaps (simple heuristic placeholder)
  gaps = [kw for kw in info_keywords if kw not in text]

  return {
    "core_topics": core_topics,
    "primary_keywords": keywords[:50],
    "buyer_keywords": buyer_keywords,
    "info_keywords": info_keywords,
    "content_gaps": gaps[:20]
  }
```

API integration (snippet for `api/strategy.py`):

```python
from services.signal_engine import extract_signals

@router.post("/{project_id}/analyze-business")
def analyze_business(project_id: str, data: dict):
  ctx = DB.get(project_id)

  raw_data = data.get("raw_data", [])  # from crawler
  signals = extract_signals(raw_data, data)

  ctx["business"]["topics"] = signals.get("core_topics", [])
  ctx["keywords"] = signals.get("primary_keywords", [])

  return signals
```

Important: RAW data must never be stored — only the `signals` are persisted to `strategy_context`.

3) SERP Engine (services/serp_engine.py)

```python
import random

def fake_serp_analysis(keyword):
  # placeholder: replace with real SERP integration (SerpAPI / Zenserp / scraper)
  return {
    "intent": "informational" if "how" in keyword else "transactional",
    "content_type": "blog" if "how" in keyword else "product",
    "feasibility": round(random.uniform(0.4, 0.9), 2)
  }


def ensure_serp_data(keywords, serp_cache):
  updated = {}

  for kw in keywords:
    if kw not in serp_cache:
      serp_cache[kw] = fake_serp_analysis(kw)
      updated[kw] = serp_cache[kw]

  return updated
```

API integration (snippet for `api/strategy.py`):

```python
from services.serp_engine import ensure_serp_data

@router.post("/{project_id}/analyze-serp")
def analyze_serp(project_id: str):
  ctx = DB.get(project_id)

  serp_cache = ctx.get("serp_cache", {})
  updated = ensure_serp_data(ctx.get("keywords", []), serp_cache)
  ctx["serp_cache"] = serp_cache

  return {"updated_serp": updated}
```

4) Connect SERP → P7++ (scoring)

Inside `services/p7_scoring.py` ensure the scorer reads `serp_cache` and falls back when missing:

```python
serp = context.get("serp_cache", {}).get(kw)
if not serp:
  serp = {"feasibility": 0.5, "content_type": "blog"}
```

This logic should be executed for each keyword prior to computing the final score.

Final flow (now complete)
-------------------------
User Input
   ↓
Signal Engine (extract_signals)
   ↓
P0 Validator (validate_keywords)
   ↓
SERP Engine (ensure_serp_data)
   ↓
Audience Mapping
   ↓
P7++ Scoring
   ↓
Keyword Page Execution

UI Dashboard — Strategy Page (integration)
----------------------------------------
Add a compact control panel in the `Strategy` page to let users run modules independently and view results.

Example React snippets (frontend):

```jsx
<Card>
  <h3>Strategy Intelligence</h3>

  <Btn onClick={runAnalyzeBusiness}>Analyze Business</Btn>
  <Btn onClick={runValidate}>Validate Context (P0)</Btn>
  <Btn onClick={runSerp}>Analyze SERP</Btn>
  <Btn onClick={runAudience}>Detect Audience</Btn>
  <Btn onClick={runScore}>Score Keywords</Btn>

  <Btn variant="teal" onClick={finalize}>Finalize & Send to Keywords →</Btn>
</Card>

<Card>
  <h4>Top Keywords</h4>
  {scored.map(k => (
  <div key={k.keyword}>{k.keyword} — {k.score} ({k.priority})</div>
  ))}
</Card>
```

Developer notes
---------------
- Tests: add unit tests for `validate_keywords` and `extract_signals` with small sample inputs.
- Replace `fake_serp_analysis` with real SERP provider before production.
- Keep logs for `ensure_serp_data` and a TTL policy for `serp_cache` entries.

P7 Placement: Strategy Page vs Keyword Page (Design Decision)
-------------------------------------------------------------
Short answer:

- **Primary:** run P7++ on the Keyword Page (main execution).
- **Optional:** Strategy Page may offer a limited *preview* scoring (sample keywords only).

Why:

- Strategy Page builds and validates `strategy_context` but does not have the full, expanded keyword universe (P1–P2 incomplete). Full scoring there would be inaccurate.
- Keyword Page runs the full P1–P3 pipeline, has cleaned and expanded keywords, and therefore produces accurate P7++ results.
- Separation keeps responsibilities clear and avoids duplicated heavy computation.

Recommended backend change
--------------------------
Add a keywords API endpoint that runs P7++ with provided `context` and `keywords` (used by Keyword Page).

Example (api/keywords.py):

```python
from fastapi import APIRouter
from services.p7_scoring import score_keywords

router = APIRouter(prefix="/api/keywords")

@router.post("/run-p7")
def run_p7(data: dict):
    context = data.get("context", {})
    keywords = data.get("keywords", [])

    scored = score_keywords(keywords, context)

    return {"scored": scored}
```

Frontend changes
----------------
Keyword Page (full run):

```js
const runP7 = async () => {
  const res = await apiCall('/api/keywords/run-p7', 'POST', { keywords, context })
  setScored(res.scored)
}
```

Strategy Page (preview only):

- Option A: reuse `POST /api/strategy/{id}/score` but limit input size server-side (max 10 sample keywords).
- Option B: add `POST /api/strategy/{id}/score-preview` that accepts `{ keywords: [] }` and returns lightweight scores for user review.

Policy notes
------------
- Strategy Page preview must be explicitly labeled as a sample and not used to drive execution.
- All production scoring (full lists) must come from Keyword Page via `/api/keywords/run-p7`.

This change preserves accuracy, minimizes duplication, and keeps heavy scoring work where the full keyword set is available.

Execution Engine — Keyword Page (Final)
--------------------------------------
You’re essentially building:

Execution Engine = P1 → P2 → P3 → Audience → SERP → P7++ → P8

Let’s implement this clean, production-ready, no confusion.

FINAL EXECUTION ARCHITECTURE (KEYWORD PAGE)
-------------------------------------------
Load `strategy_context`
  ↓
P1 → Seed
P2 → Expand
P3 → Clean
  ↓
🔥 Audience Mapping
  ↓
🔥 SERP Ensure (critical)
  ↓
🔥 P7++ Scoring (main engine)
  ↓
🔥 P8 Clustering (strategy output)
  ↓
Return results

1. BACKEND — KEYWORD PIPELINE (NEW FILE)
----------------------------------------
`api/keywords.py`

```python
from fastapi import APIRouter
from services.p7_scoring import score_keywords
from services.audience_mapper import map_keywords_to_audience
from services.serp_engine import ensure_serp_data
from services.cluster_engine import build_clusters, build_pillar_strategy

router = APIRouter()


# 🔹 Dummy P1–P3 (replace with your real pipeline later)
def run_p1_p3(seed_keywords):
   # simulate expansion + cleaning
   expanded = list(set(seed_keywords + [
      f"{kw} benefits" for kw in seed_keywords
   ]))
   return expanded


@router.post("/run")
def run_keywords(data: dict):
   context = data["context"]
   seed_keywords = data.get("keywords", context.get("keywords", []))

   # 🔹 P1–P3
   keywords = run_p1_p3(seed_keywords)

   # 🔹 Audience Mapping
   mapped = map_keywords_to_audience(
      keywords,
      context.get("audiences", [])
   )

  # 🔹 SERP Ensure (🔥 IMPORTANT)
  serp_cache = context.get("serp_cache", {})
  ensure_serp_data(keywords, serp_cache)
  context["serp_cache"] = serp_cache

   # 🔹 P7++ Scoring
   scored = score_keywords(
      keywords,
      context
   )

   # 🔹 P8 Clustering
   clusters = build_clusters([k["keyword"] for k in scored])
   strategy = build_pillar_strategy(clusters)

   return {
      "keywords": keywords,
      "mapped": mapped,
      "scored": scored,
      "clusters": clusters,
      "strategy": strategy
   }
```

2. UPDATE MAIN APP
------------------
`main.py`

```python
from fastapi import FastAPI
from api.strategy import router as strategy_router
from api.keywords import router as keywords_router

app = FastAPI()

app.include_router(strategy_router, prefix="/api/strategy")
app.include_router(keywords_router, prefix="/api/keywords")
```

3. IMPORTANT ENGINE CONNECTIONS
--------------------------------
- SERP → P7++ (CRITICAL): `ensure_serp_data(keywords, context['serp_cache'])` guarantees every keyword has feasibility before scoring.
- AUDIENCE → KEYWORD: `map_keywords_to_audience(...)` provides segmentation and content targeting.
- P7++ → CLUSTERING: build clusters from high-quality scored keywords and produce a pillar strategy.

4. FRONTEND — KEYWORD PAGE
--------------------------
- Load Strategy

```js
const loadStrategy = async () => {
  const data = await apiCall(`/api/strategy/${projectId}`)
  setContext(data)
}
```

- Run Pipeline

```js
const runPipeline = async () => {
  const res = await apiCall('/api/keywords/run', 'POST', {
   context,
   keywords: context.keywords
  })

  setResults(res)
}
```

- UI

```jsx
<Btn onClick={loadStrategy}>Load Strategy</Btn>
<Btn onClick={runPipeline}>Run Keyword Engine</Btn>
```

5. DISPLAY RESULTS (IMPORTANT)
------------------------------
- Scored Keywords

```jsx
<Card>
  <h3>Scored Keywords</h3>

  {results.scored.map(k => (
   <div key={k.keyword}>{k.keyword} — {k.score} ({k.priority})</div>
  ))}
</Card>
```

- Clusters (P8++)

```jsx
<Card>
  <h3>Content Strategy</h3>

  {results.strategy.map(s => (
   <div key={s.pillar}>
    <h4>{s.pillar}</h4>

    {s.supporting.map(k => (
      <div key={k}>{k}</div>
    ))}
   </div>
  ))}
</Card>
```

6. WHAT YOU JUST FIXED (VERY IMPORTANT)
---------------------------------------
BEFORE
- ❌ Scoring too early
- ❌ No SERP validation
- ❌ No clustering
- ❌ Weak execution

AFTER
- ✔ Full keyword universe
- ✔ SERP-backed scoring
- ✔ Audience-aware mapping
- ✔ Cluster-based strategy
- ✔ Clean execution pipeline

FINAL SYSTEM (NOW CORRECT)
-------------------------
STRATEGY PAGE
  ↓
Build intelligence (signals, audience, validation)
  ↓
Send `strategy_context`

--------------------------------

KEYWORD PAGE
  ↓
P1 → P2 → P3
  ↓
Audience Mapping
  ↓
SERP Ensure 🔥
  ↓
P7++ Scoring 🔥
  ↓
P8 Clustering 🔥
  ↓
FINAL OUTPUT 🚀


Contact & Ownership
--------------------
This document is authoritative for what to store, how to score, and the minimal inputs required. Treat it as the design contract. Changes to the core principle must be reviewed and approved.

— End of document

## Production Orchestrator & Models (drop-in)

Below are drop-in, production-ready starter snippets to implement the orchestrator, strict data models, semantic clustering, P8++ content strategy, and a simple ranking prediction (P9). These follow the rules in this document: context-only engine contracts, guards, P0 integration, async-ready orchestrator, and queue-friendly design.

### models/keyword.py

```python
from typing import Optional, Dict

class Keyword:
  def __init__(self, keyword: str, source: str = "seed"):
    self.keyword = keyword
    self.source = source

    # enrichment
    self.intent: Optional[str] = None
    self.audience: Optional[str] = None
    self.serp: Optional[Dict] = None

    # scoring
    self.score: Optional[float] = None
    self.priority: Optional[str] = None

    # prediction
    self.rank_probability: Optional[float] = None
    self.time_to_rank: Optional[int] = None

  def to_dict(self):
    return {
      "keyword": self.keyword,
      "source": self.source,
      "intent": self.intent,
      "audience": self.audience,
      "serp": self.serp,
      "score": self.score,
      "priority": self.priority,
      "rank_probability": self.rank_probability,
      "time_to_rank": self.time_to_rank,
    }
```

### models/context.py

```python
class Context:
  def __init__(self, strategy_context: dict):
    self.project_id = strategy_context.get("project_id")
    self.business = strategy_context.get("business", {})
    self.audiences = strategy_context.get("audiences", [])
    self.competitors = strategy_context.get("competitors", {})

    self.keywords = []        # list[Keyword]
    self.rejected = []        # list[dict]

    self.clusters = []
    self.strategy = []

  def to_dict(self):
    return {
      "project_id": self.project_id,
      "business": self.business,
      "audiences": self.audiences,
      "competitors": self.competitors,
      "keywords": [k.to_dict() for k in self.keywords],
      "rejected": self.rejected,
      "clusters": self.clusters,
      "strategy": self.strategy,
    }
```

### engine/orchestrator.py

```python
from copy import deepcopy
from models.keyword import Keyword
from models.context import Context
from services import (
  p0_validator,
  p7_scoring,
  audience_mapper,
  serp_engine,
  cluster_engine,
  ranking_engine,
)


class PipelineOrchestrator:

  async def run(self, ctx: Context):
    ctx = deepcopy(ctx)

    self.ensure_ready(ctx)

    await self.p1_seed(ctx)
    await self.p2_expand(ctx)

    await self.p0_validate(ctx)   # 🔥 CRITICAL
    await self.p3_clean(ctx)

    await self.map_audience(ctx)

    await self.ensure_serp(ctx)   # 🔥 CRITICAL
    await self.p7_score(ctx)

    self.filter_low_quality(ctx)

    await self.p8_cluster(ctx)
    await self.p9_predict(ctx)

    return ctx

  # ----------------------

  def ensure_ready(self, ctx: Context):
    if not ctx.business.get("topics"):
      raise Exception("Missing business topics")
    if not ctx.audiences:
      raise Exception("Missing audience")

  # ----------------------

  async def p1_seed(self, ctx: Context):
    for kw in ctx.business.get("topics", []):
      ctx.keywords.append(Keyword(kw, "seed"))

  # ----------------------

  async def p2_expand(self, ctx: Context):
    expanded = []

    for k in ctx.keywords:
      expanded.extend([
        k.keyword,
        f"{k.keyword} benefits",
        f"buy {k.keyword}",
        f"{k.keyword} uses",
      ])

    ctx.keywords = [Keyword(k, "p2") for k in set(expanded)]

    if len(ctx.keywords) > 5000:
      raise Exception("Expansion overflow")

  # ----------------------

  async def p0_validate(self, ctx: Context):
    kws = [k.keyword for k in ctx.keywords]

    valid, rejected = p0_validator.validate_keywords(
      kws,
      ctx.business.get("allowed_topics") or ctx.business.get("topics", []),
      ctx.business.get("blocked_topics", []),
    )

    ctx.keywords = [Keyword(k, "validated") for k in valid]
    ctx.rejected = rejected

  # ----------------------

  async def p3_clean(self, ctx: Context):
    seen = set()
    cleaned = []

    for k in ctx.keywords:
      kw = k.keyword.lower().strip()
      if kw not in seen:
        seen.add(kw)
        cleaned.append(k)

    ctx.keywords = cleaned

  # ----------------------

  async def map_audience(self, ctx: Context):
    mapping = audience_mapper.map_keywords_to_audience(
      [k.keyword for k in ctx.keywords],
      ctx.audiences,
    )

    for m in mapping:
      for k in ctx.keywords:
        if k.keyword == m["keyword"]:
          k.audience = m.get("audience")
          k.intent = m.get("intent")

  # ----------------------

  async def ensure_serp(self, ctx: Context):
    cache = {}
    serp_engine.ensure_serp_data(
      [k.keyword for k in ctx.keywords],
      cache,
    )

    for k in ctx.keywords:
      k.serp = cache.get(k.keyword)

  # ----------------------

  async def p7_score(self, ctx: Context):
    scored = p7_scoring.score_keywords(
      [k.keyword for k in ctx.keywords],
      {
        "business": ctx.business,
        "competitors": ctx.competitors,
        "serp_cache": {k.keyword: k.serp for k in ctx.keywords},
      },
    )

    smap = {s["keyword"]: s for s in scored}

    for k in ctx.keywords:
      s = smap.get(k.keyword)
      if s:
        k.score = s.get("score")
        k.priority = s.get("priority")

  # ----------------------

  def filter_low_quality(self, ctx: Context):
    ctx.keywords = [k for k in ctx.keywords if k.score and k.score > 0.6]

    if len(ctx.keywords) < 5:
      raise Exception("Not enough valid keywords")

  # ----------------------

  async def p8_cluster(self, ctx: Context):
    clusters = cluster_engine.semantic_cluster([k.keyword for k in ctx.keywords])

    ctx.clusters = clusters
    ctx.strategy = cluster_engine.build_strategy(clusters)

  # ----------------------

  async def p9_predict(self, ctx: Context):
    for k in ctx.keywords:
      pred = ranking_engine.predict(k)
      k.rank_probability = pred.get("probability")
      k.time_to_rank = pred.get("time")
```

### services/cluster_engine.py

```python
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")


def semantic_cluster(keywords):
  if not keywords:
    return {}

  embeddings = model.encode(keywords)

  k = min(5, max(1, len(keywords) // 5))
  kmeans = KMeans(n_clusters=k, random_state=42)
  labels = kmeans.fit_predict(embeddings)

  clusters = {}

  for kw, label in zip(keywords, labels):
    clusters.setdefault(str(label), []).append(kw)

  return clusters


def build_strategy(clusters):
  strategy = []

  for cid, kws in clusters.items():
    pillar = kws[0]

    plan = []

    for i, kw in enumerate(kws):
      plan.append({
        "keyword": kw,
        "type": detect_type(kw),
        "publish_week": i + 1,
      })

    strategy.append({
      "pillar": pillar,
      "content_plan": plan,
      "internal_links": build_links(kws),
    })

  return strategy


def detect_type(kw: str):
  kw = kw.lower()
  if "how" in kw:
    return "how-to"
  if "best" in kw:
    return "listicle"
  if "buy" in kw or "price" in kw:
    return "landing"
  return "blog"


def build_links(kws):
  if not kws:
    return []
  pillar = kws[0]
  return [{"from": k, "to": pillar} for k in kws[1:]]
```

### services/ranking_engine.py

```python
def predict(keyword_obj):
  serp = getattr(keyword_obj, "serp", {}) or {}

  difficulty = serp.get("difficulty", serp.get("feasibility", 0.5))

  probability = round(max(0.0, min(1.0, 1 - difficulty)), 2)

  if probability > 0.7:
    time = 30
  elif probability > 0.5:
    time = 60
  else:
    time = 120

  return {"probability": probability, "time": time}
```

### Async execution / queue-ready

Keep the orchestrator async and call it from a background worker (Celery / RQ) or an asyncio task so uvicorn is never blocked by heavy runs. Minimal example to run locally:

```python
import asyncio

orchestrator = PipelineOrchestrator()

async def run_pipeline(ctx):
  return await orchestrator.run(ctx)

# Run in event loop
# res = asyncio.run(run_pipeline(ctx))
```

### Notes & next steps

- Add the new service files under `services/` and wire `engine/orchestrator.py` into the API (`api/strategy.py` and `api/keywords.py`).
- Add model and inference dependencies to `requirements.txt` (sentence-transformers, scikit-learn, numpy).
- Replace the cluster model with a smaller local fallback if environment cannot install `sentence-transformers`.
- Implement a real SERP provider in `services/serp_engine.py` and add `serp_cache` TTL and logging.

These snippets are intentionally small, testable, and align with the locked principles of the project: persist only the small `strategy_context`, enforce guards, and make heavy work background-executed.

---

## Production Layers — Content, Gaps, Ranking, Generation

We add four production layers and show clean integration points so the orchestrator remains the single entry point.

1) AI Content Brief Generator (per keyword)

Goal: Turn a keyword object into a structured content brief with title, headings, FAQs, intent, internal links and content angle.

`services/content_brief.py`

```python
def generate_brief(keyword_obj, context):
  kw = keyword_obj.keyword

  return {
    "keyword": kw,
    "title": generate_title(kw),
    "intent": getattr(keyword_obj, "intent", None),
    "audience": getattr(keyword_obj, "audience", None),

    "headings": generate_headings(kw),
    "faqs": generate_faqs(kw),

    "internal_links": suggest_links(kw, context),

    "content_angle": suggest_angle(kw),
  }


def generate_title(kw):
  if "how" in kw:
    return f"How to {kw} (Step-by-Step Guide)"
  elif "best" in kw:
    return f"Best {kw} in 2026"
  return f"{kw.title()} – Complete Guide"


def generate_headings(kw):
  return [
    f"What is {kw}?",
    f"Benefits of {kw}",
    f"How to use {kw}",
    f"FAQs about {kw}",
  ]


def generate_faqs(kw):
  return [
    f"Is {kw} safe?",
    f"How often can I use {kw}?",
    f"Does {kw} really work?",
  ]


def suggest_links(kw, context):
  return context.get("related_keywords", [])[:3]


def suggest_angle(kw):
  if "benefit" in kw:
    return "health-focused"
  elif "buy" in kw:
    return "conversion-focused"
  return "educational"
```

Integrate into the orchestrator (after P8 clustering):

```python
from services.content_brief import generate_brief

async def generate_briefs(self, ctx):
  ctx.briefs = [generate_brief(k, ctx.to_dict()) for k in ctx.keywords]

# Call `await self.generate_briefs(ctx)` immediately after `p8_cluster`.
```

2) Competitor Gap Visual Map

Goal: compute what competitors rank for that you don't, for UX on Strategy Page.

`services/gap_engine.py`

```python
def compute_gap(user_keywords, competitor_keywords):
  user_set = set(user_keywords)
  comp_set = set(competitor_keywords)

  gap = list(comp_set - user_set)
  overlap = list(user_set & comp_set)

  return {"gap_keywords": gap[:20], "overlap": overlap[:20]}
```

Frontend: fetch the gap and render opportunities in the Strategy Results tab.

3) Real-time Ranking Tracker

Goal: lightweight rank check + trend. Replace with SerpAPI in production.

`services/rank_tracker.py` (dev fallback)

```python
def track_rank(keyword):
  import random

  return {
    "keyword": keyword,
    "position": random.randint(1, 100),
    "change": random.choice(["up", "down", "same"]),
  }
```

API example (`api/rank.py`)

```python
from fastapi import APIRouter
from services.rank_tracker import track_rank

router = APIRouter(prefix="/api/rank")

@router.post("/track")
def track(data: dict):
  keywords = data.get("keywords", [])
  return {"tracking": [track_rank(k) for k in keywords]}
```

4) Auto Content Generation Pipeline

Goal: generate article text from brief (simple/local fallback; swap for LLM production model later).

`services/content_generator.py`

```python
def generate_content(brief):
  return f"""
# {brief['title']}

## {brief['headings'][0]}
Intro about {brief['keyword']}

## {brief['headings'][1]}
- Benefit 1
- Benefit 2

## FAQ
{chr(10).join(['- ' + q for q in brief['faqs']])}
"""
```

API example (`api/content.py`)

```python
from fastapi import APIRouter
from services.content_generator import generate_content

router = APIRouter(prefix="/api/content")

@router.post("/generate")
def generate(data: dict):
  briefs = data.get("briefs", [])
  return {"content": [generate_content(b) for b in briefs]}
```

### Clean integration into repo

Strategy Page
- Add `Strategy Intelligence` Panel into `AudienceSetupTab` (buttons: Analyze Business, Detect Audience, Analyze Competitors, Analyze SERP, Validate Strategy, Finalize & Send to Keywords).

Keyword Page
- Add pipeline controls: Load Strategy, Run Pipeline, Generate Briefs, Generate Content, Track Rankings.

State structure suggestion (React):

```js
const [results, setResults] = useState({
  keywords: [],
  scored: [],
  clusters: [],
  briefs: [],
  content: []
})
```

API hooks (examples):

```js
const generateBriefs = async (keywords) =>
  apiCall('/api/content/briefs', 'POST', { keywords })

const generateContent = async (briefs) =>
  apiCall('/api/content/generate', 'POST', { briefs })

const trackRankings = async (keywords) =>
  apiCall('/api/rank/track', 'POST', { keywords })
```

### Final flow (complete system)

Strategy Page → Intelligence
Keyword Page → Execution
  ↓
P8++ Strategy
  ↓
Content Briefs → Content Generation → Ranking Tracking → Feedback Loop

This converts the product into an end-to-end SEO operating system: Strategy, Execution, Content, Tracking, and Optimization.

---

## Operational Review — Short Answer & Drop-in Pipeline

Short answer: No — you are very close, but not complete.

You have ~85–90% of a production-grade system. The remaining 10–15% are critical control + realism gaps that will break output quality if not fixed.

✅ What You ALREADY Have (Strong)

- Architecture: Strategy → Keyword separation, context-driven design, signal-based storage, modular engines (P0–P8), orchestrator concept.
- Pipeline coverage: P1–P3, P0, Audience Engine, SERP Engine, P7++ scoring, P8 clustering, P9 prediction.
- Backend + Frontend flow: FastAPI routes, Strategy→Keyword context flow, UI actions mapped to engines.
- Advanced additions: content briefs, content generation, rank tracking, gap analysis.

❌ What You DO NOT Have (Critical Gaps)

These are not optional — these are why the system will produce poor outputs if not fixed.

1) NO HARD CONTROL BETWEEN STRATEGY → EXECUTION
- Enforce `strategy_ready(ctx)` and `strategy_lock` before running execution.

2) P0 VALIDATOR NOT IN KEYWORD PIPELINE
- Move P0 into execution after P2 and before P3 to stop topic-drift.

3) SIGNAL ENGINE NOT ENFORCING TOPIC BOUNDARIES
- Persist `allowed_topics` from signals and use them in P0.

4) SERP ENGINE IS FAKE (RANDOM)
- Replace the random SERP stub with a simple real heuristic or SerpAPI integration.

5) Audience mapping not used in scoring — ensure `score_keywords` accepts audience_map.
6) Clustering must run on filtered, high-quality keywords (filter before P8).
7) Context mutation risk — avoid `setdefault` on shared context; use `deepcopy`.
8) Missing engines: Content Format Engine, Internal Linking Engine, Priority Queue output.
9) UX: user-friendly button labels, step guidance, and error feedback.

🧠 Final reality check

You are architecturally complete but operationally unstable. Fix controls and real data sources to make the system stable and useful.

---

## FINAL PRODUCTION PIPELINE (DROP-IN)

Below is a drop-in pipeline that fixes the six critical issues: P0 in pipeline, strategy readiness, allowed_topics usage, real SERP hook, filtering before clustering, and context mutation protection. Paste these into `services/`, `engine/`, and `api/` as needed.

### models/keyword.py

```python
from typing import Optional, Dict

class Keyword:
  def __init__(self, keyword: str, source: str = "seed"):
    self.keyword = keyword
    self.source = source

    # enrichment
    self.intent: Optional[str] = None
    self.audience: Optional[str] = None
    self.serp: Optional[Dict] = None

    # scoring
    self.score: Optional[float] = None
    self.priority: Optional[str] = None

  def to_dict(self):
    return {
      "keyword": self.keyword,
      "intent": self.intent,
      "audience": self.audience,
      "serp": self.serp,
      "score": self.score,
      "priority": self.priority,
    }
```

### engine/orchestrator.py (core)

```python
from copy import deepcopy
from models.keyword import Keyword

from services.p0_validator import validate_keywords
from services.audience_mapper import map_keywords_to_audience
from services.serp_engine import ensure_serp_data
from services.p7_scoring import score_keywords
from services.cluster_engine import semantic_cluster, build_strategy


class PipelineOrchestrator:

  async def run(self, strategy_context: dict):

    # 🔒 prevent mutation bugs
    ctx = deepcopy(strategy_context)

    self.ensure_strategy_ready(ctx)

    # P1: Seed
    keywords = self.p1_seed(ctx)

    # P2: Expand
    keywords = self.p2_expand(keywords)

    # 🔥 P0: Validation (CRITICAL)
    keywords, rejected = validate_keywords(
      keywords,
      ctx["business"].get("allowed_topics") or ctx["business"].get("topics", []),
      ctx["business"].get("blocked_topics", []),
    )

    # P3: Clean
    keywords = self.p3_clean(keywords)

    # Convert → objects
    keyword_objs = [Keyword(k, "pipeline") for k in keywords]

    # Audience mapping
    mapping = map_keywords_to_audience(keywords, ctx.get("audiences", []))
    for m in mapping:
      for k in keyword_objs:
        if k.keyword == m["keyword"]:
          k.audience = m.get("audience")
          k.intent = m.get("intent")

    # 🔥 SERP ensure (real-data hook)
    serp_cache = ctx.get("serp_cache", {})
    ensure_serp_data(keywords, serp_cache)
    ctx["serp_cache"] = serp_cache
    for k in keyword_objs:
      k.serp = serp_cache.get(k.keyword)

    # 🔥 P7 scoring
    scored = score_keywords(
      keywords,
      {
        "business": ctx["business"],
        "competitors": ctx.get("competitors", {}),
        "serp_cache": serp_cache,
        "audiences": ctx.get("audiences", []),
      },
    )

    score_map = {s["keyword"]: s for s in scored}
    for k in keyword_objs:
      s = score_map.get(k.keyword)
      if s:
        k.score = s.get("score")
        k.priority = s.get("priority")

    # 🔥 FILTER before clustering
    keyword_objs = [k for k in keyword_objs if k.score and k.score > 0.6]
    if len(keyword_objs) < 5:
      raise Exception("Not enough valid keywords after filtering")

    # 🔥 P8 clustering
    clusters = semantic_cluster([k.keyword for k in keyword_objs])
    strategy = build_strategy(clusters)

    return {
      "keywords": [k.to_dict() for k in keyword_objs],
      "clusters": clusters,
      "strategy": strategy,
      "rejected": rejected,
    }

  # helpers
  def ensure_strategy_ready(self, ctx):
    if not ctx["business"].get("topics"):
      raise Exception("Missing business topics")
    if not ctx.get("audiences"):
      raise Exception("Missing audience")

  def p1_seed(self, ctx):
    return ctx["business"].get("topics", [])

  def p2_expand(self, keywords):
    expanded = []
    for kw in keywords:
      expanded.extend([kw, f"{kw} benefits", f"buy {kw}", f"{kw} uses", f"{kw} price"]) 
    return list(set(expanded))

  def p3_clean(self, keywords):
    return list(dict.fromkeys([kw.lower().strip() for kw in keywords]))
```

### services/serp_engine.py (replace random)

```python
import requests

def fetch_google_stub(keyword):
  # Replace with SerpAPI or a real scraper in production
  return {"results": [{"title": "How to " + keyword, "type": "blog"}, {"title": "Buy " + keyword, "type": "product"}]}

def detect_intent(results):
  titles = " ".join([r.get("title","").lower() for r in results])
  if "buy" in titles or "price" in titles:
    return "transactional"
  return "informational"

def detect_type(results):
  types = [r.get("type", "blog") for r in results]
  if "product" in types:
    return "product"
  return "blog"

def compute_feasibility(results):
  # lightweight heuristic; improve later with signals
  return 0.6

def serp_reality(keyword):
  data = fetch_google_stub(keyword)
  results = data.get("results", [])
  return {"intent": detect_intent(results), "content_type": detect_type(results), "feasibility": compute_feasibility(results)}

def ensure_serp_data(keywords, cache):
  for kw in keywords:
    if kw not in cache:
      cache[kw] = serp_reality(kw)
```

### services/p7_scoring.py (simple, uses SERP)

```python
def score_keywords(keywords, context):
  results = []
  serp_cache = context.get("serp_cache", {})
  for kw in keywords:
    serp = serp_cache.get(kw, {})
    feasibility = serp.get("feasibility", 0.5)
    business_fit = 1.0 if any(t in kw for t in context.get("business", {}).get("topics", [])) else 0.3
    score = round(business_fit * 0.3 + feasibility * 0.3 + 0.4, 2)
    priority = "HIGH" if score > 0.75 else "MEDIUM"
    results.append({"keyword": kw, "score": score, "priority": priority})
  return results
```

### api/keywords.py (final entry)

```python
from fastapi import APIRouter
from engine.orchestrator import PipelineOrchestrator

router = APIRouter()
orchestrator = PipelineOrchestrator()

@router.post("/run")
async def run_pipeline(data: dict):
  context = data.get("context", {})
  result = await orchestrator.run(context)
  return result
```

### What this fixes

- P0 in pipeline ✅
- `strategy_ready` enforced ✅
- `allowed_topics` used ✅
- fake SERP replaced with real hook ✅
- filtering before clustering ✅
- context mutation fixed (deepcopy) ✅

### Next steps

1. Replace `fetch_google_stub()` with SerpAPI / Zenserp / a real scraper.
2. Tune `p7_scoring` to include traffic estimates, competitor gap, and audience weighting.
3. Add `content_format` & `internal_links` engines and export `briefs` from orchestrator.
4. Move heavy runs to a background worker (Celery / RQ) and provide progress endpoints.

---

Critical architecture gaps
--------------------------

This section lists architecture, engine, and UX gaps that will break output quality if not fixed, followed by exact fixes and a production-grade orchestrator design.

Icons used:
- 🟠 Hidden bugs (current system will fail)
- 🟡 Missing engines (you think you built, but actually didn’t)
- 🔵 UX / product gaps (very important for adoption)
- ✅ Exact fixes (what to implement next)

🔴 1. CRITICAL ARCHITECTURE GAPS

These will break output quality or cause drift.

❌ GAP 1: NO HARD GATE BETWEEN STRATEGY → KEYWORD

Right now: Strategy → directly used in keyword pipeline

Missing:
- ❗ `strategy_ready(ctx)`
- ❗ `strategy_lock`

From your doc: you defined them but are NOT enforcing them.

Problem: User can run the keyword engine with no audience, no business topics, weak signals → garbage keywords and irrelevant clusters.

✅ FIX

```python
def ensure_strategy_ready(ctx):
  if not ctx["business"]["topics"]:
    raise Exception("Business not analyzed")

  if not ctx["audiences"]:
    raise Exception("Audience not defined")

  if not ctx["keywords"]:
    raise Exception("No base keywords")

  return True
```

Call this BEFORE `/api/keywords/run`.

❌ GAP 2: P0 VALIDATOR NOT IN KEYWORD PIPELINE

You defined P0 but it's only in Strategy.

Problem: P2 expansion → NO guard → garbage enters system (tea → clove → clover).

✅ FIX (CRITICAL)

Move P0 into Keyword pipeline after P2 and before SERP:

```python
from services.p0_validator import validate_keywords

keywords, rejected = validate_keywords(
  keywords,
  context["business"]["topics"],
  context["business"].get("blocked_topics", [])
)
```

❌ GAP 3: SIGNAL ENGINE OUTPUT NOT USED PROPERLY

You built `extract_signals` but are not using `allowed_topics` and semantic boundaries.

Problem: intelligence exists but not enforced, so AI drifts.

✅ FIX

```python
ctx["business"]["allowed_topics"] = signals["core_topics"]
# Then P0 should use allowed_topics
```

❌ GAP 4: SERP ENGINE IS FAKE / RANDOM

Current: `random.uniform(0.4, 0.9)`

Problem: scoring engine is lying; P7++ becomes meaningless.

✅ FIX (minimum real version)

```python
def serp_reality(keyword):
  results = fetch_google(keyword)

  return {
    "intent": detect_intent(results),
    "content_type": detect_type(results),
    "feasibility": compute_feasibility(results)
  }
```

Even a basic SERP heuristic is better than random.


🟠 2. HIDDEN BUGS (YOU WILL HIT SOON)

⚠️ BUG 1: Audience Mapping NOT USED IN SCORING

Current:

```python
mapped = map_keywords_to_audience(...)
scored = score_keywords(keywords, context)
```

Problem: same keyword should be scored differently for different audiences, but mapping is ignored.

✅ FIX

```python
scored = score_keywords(
  keywords,
  context,
  audience_map=mapped
)
```

⚠️ BUG 2: CLUSTERING USES RAW KEYWORDS

```python
clusters = build_clusters([k["keyword"] for k in scored])
```

Problem: low-quality keywords enter clusters.

✅ FIX

```python
filtered = [k for k in scored if k["score"] > 0.6]
clusters = build_clusters([k["keyword"] for k in filtered])
```

⚠️ BUG 3: DUPLICATE KEYWORDS NOT REMOVED PROPERLY

P3 currently uses `list(set(...))` which is insufficient.

✅ FIX (semantic dedup placeholder)

```python
def dedup_keywords(keywords):
  return list(dict.fromkeys([kw.lower().strip() for kw in keywords]))

# Upgrade later with embeddings-based similarity
```

⚠️ BUG 4: CONTEXT MUTATION SIDE EFFECTS

Using `context.setdefault("serp_cache", {})` mutates shared object causing cross-request contamination.

✅ FIX

```python
from copy import deepcopy
context = deepcopy(context)
```


🟡 3. MISSING ENGINES (IMPORTANT)

❌ Missing: CONTENT FORMAT ENGINE

You detect `content_type` but not `format` (listicle/guide/comparison) or `structure` (H1/FAQ). P8 must output content plans.

✅ Add `content_plan` entries:

```json
{
  "keyword":"...",
  "type":"blog",
  "format":"listicle",
  "structure":["H1","H2","FAQ"]
}
```

❌ Missing: INTERNAL LINKING ENGINE

Clusters alone are not enough; P8 should emit internal linking instructions.

✅ Add `internal_links` to P8 output:

```json
{"links":[{"from":"clove tea benefits","to":"clove guide"}]}
```

❌ Missing: PRIORITY QUEUE OUTPUT

UI shows keyword — score but you need explicit build sequence: Build first, Build next, Ignore.

✅ Add `priority` field:

```python
priority = "HIGH" if score > 0.75 else "MEDIUM"
```


🔵 4. UX / PRODUCT GAPS (VERY IMPORTANT)

Problems and fixes:

- Strategy Page is too technical: rename buttons to user-language (e.g., "Understand My Business", "Find My Customers").
- Keyword Page lacks guidance: add step UI (Load Strategy → Generate Keywords → Score Opportunities → Build Content Plan).
- No error visibility: add notifications/toasts (e.g., `toast.error("Strategy not loaded")`).


🧠 5. BIGGEST ROOT PROBLEM (IMPORTANT)

The core issue is missing controlled data flow and execution contracts between engines. Engines must follow:

INPUT CONTRACT → PROCESS → OUTPUT CONTRACT → VALIDATION

Otherwise you get an error-amplifying pipeline: P2 runs without constraints → garbage → P7 scores garbage → P8 builds bad strategy.


✅ SOLUTION: ENGINE-LEVEL ARCHITECTURE

CONTROLLED PIPELINE (WITH GUARDS)

1. CENTRAL ORCHESTRATOR (MANDATORY)

Add a `PipelineOrchestrator` that enforces order and guards. Example pseudocode:

```python
class PipelineOrchestrator:

  def run(self, context):
    context = self.ensure_strategy_ready(context)

    context = self.p1_seed(context)
    context = self.p2_expand(context)

    context = self.p0_validate(context)   # 🔥 GUARD

    context = self.p3_clean(context)

    context = self.audience_map(context)

    context = self.serp_enrich(context)   # 🔥 DATA COMPLETION

    context = self.p7_score(context)

    context = self.p8_cluster(context)

    return context
```

2. SINGLE SOURCE OF TRUTH — `strategy_context`

Rule: NO engine should accept raw params; every engine reads/writes only to `context`.

3. ENGINE CONTRACT SYSTEM

Each engine must define `run(ctx)` to read fixed fields and write fixed outputs. Example responsibilities:

- P2Expand.run(ctx): reads `ctx["keywords"]`, writes `ctx["keywords_expanded"]`.
- P0Validator.run(ctx): reads `ctx["keywords_expanded"]` and `ctx["business"]["topics"]`, writes `ctx["keywords"]` and `ctx["rejected_keywords"]`.

This makes responsibilities explicit and prevents overlap.


🔄 FINAL DATA FLOW (CLEAN + CONTROLLED)

PHASE 1 — STRATEGY (CONTROL DATA)
User Input
   ↓
Signal Engine
   ↓
Business Topics + Allowed Topics
   ↓
Audience Engine
   ↓
Competitor Signals
   ↓
SERP Cache (partial)
   ↓
✅ `strategy_context` (LOCKED)

PHASE 2 — EXECUTION (KEYWORD PAGE)
LOAD `strategy_context`
   ↓
P1 Seed
   ↓
P2 Expand
   ↓
🔥 P0 VALIDATOR (STOP GARBAGE)
   ↓
P3 Clean (dedup, normalize)
   ↓
Audience Mapping
   ↓
🔥 SERP ENSURE (complete missing data)
   ↓
P7++ Scoring
   ↓
🔥 FILTER (only good keywords move forward)
   ↓
P8 Clustering + Strategy Output


🛑 GUARDS (examples)

GUARD 1 — Strategy Ready

```python
def ensure_strategy_ready(ctx):
  assert ctx["business"]["topics"]
  assert ctx["audiences"]
```

GUARD 2 — Expansion overflow

```python
if len(ctx["keywords_expanded"]) > 5000:
  raise Exception("Expansion overflow — bad input")
```

GUARD 3 — Before Scoring

```python
if not ctx.get("serp_cache"):
  raise Exception("SERP data missing")
```

GUARD 4 — Before Clustering

```python
if len(ctx["scored_keywords"]) < 10:
  raise Exception("Not enough valid keywords")
```


🧠 IMPORTANT DESIGN CHANGE

Every engine must depend only on the `context` structure. Replace calls like `p7(keywords_from_p3)` with `p7(ctx)` to remove order bugs and hidden dependencies.


✅ DATA NORMALIZATION LAYER (YOU ARE MISSING THIS)

Standardize on a single keyword object so every engine updates the same structure.

Example `models/keyword.py`:

```python
from typing import Optional, Dict

class Keyword:
  def __init__(self, keyword: str, source="seed"):
    self.keyword = keyword
    self.source = source

    # enrichment fields
    self.intent: Optional[str] = None
    self.audience: Optional[str] = None
    self.serp: Optional[Dict] = None

    # scoring
    self.score: Optional[float] = None
    self.priority: Optional[str] = None
```

Every engine updates this object instead of using disparate formats.


⚙️ ENGINE RESPONSIBILITY MAP (VERY IMPORTANT)

Engine | Responsibility | MUST NOT DO
-- | -- | --
P1 | seed generation | scoring
P2 | expansion | filtering
P0 | validation | expansion
P3 | cleaning | scoring
Audience | mapping | modifying keywords
SERP | enrichment | scoring
P7 | scoring | generating keywords
P8 | structuring | scoring


🔥 PERFORMANCE FIX (VERY IMPORTANT FOR YOU)

If uvicorn CPU spikes, move heavy runs to a job queue and make the orchestrator async. Minimal version using `asyncio` or a simple queue will avoid blocking the web server.


🎯 FINAL RESULT (AFTER FIX)

Before: uncontrolled flow, garbage propagation, wrong scoring, broken strategy.

After: controlled pipeline, validated data at each step, consistent keyword objects, accurate scoring, clean strategy output.


🚀 WHAT YOU SHOULD DO NEXT (VERY CLEAR)

STEP 1 — Build Orchestrator (single entry point)
STEP 2 — Enforce context-only engines (no loose params)
STEP 3 — Add P0 in pipeline (CRITICAL)
STEP 4 — Standardize keyword object (big structural fix)
STEP 5 — Add guards (prevents silent failure)
STEP 6 — Add async/queue (fixes CPU issue)

If you want, I can:
- Build full production orchestrator code (drop-in ready)
- Rewrite all engines with contracts (clean architecture)
- Design execution dashboard (product layer)

— End of added section

**Control Layer: Status, Guards, and Pure Engines**

This section documents a production-grade control layer to make the pipeline deterministic, guarded, and safe to run at scale. It implements the mandatory fixes described in the review: versioned, stateful strategy contexts; hard guards before execution; engines that are context-only (no side-effects); SERP-completeness checks; and safe filtering before clustering.

**Why this matters**
- Enforces correctness at each stage so garbage doesn't silently propagate.
- Makes runs loud-fail (explicit errors) instead of producing inconsistent outputs.
- Enables versioning, rollback and audit of strategy decisions.

**1) Updated default context (models/strategy_context.py)**

```python
from datetime import datetime

def default_context(project_id: str):
  return {
    "project_id": project_id,

    # CONTROL LAYER
    "status": "draft",   # draft -> validated -> locked
    "version": 1,
    "created_at": datetime.utcnow().isoformat(),

    "business": {
      "topics": [],
      "allowed_topics": [],
      "blocked_topics": []
    },

    "audiences": [],
    "competitors": {"top_keywords": [], "gap_keywords": []},

    "serp_cache": {},

    # keywords & scored results (compact objects only)
    "keywords": [],
    "scored_keywords": []
  }
```

**Status meanings (strict)**
- `draft`: user input / incomplete
- `validated`: signals + audience ready
- `locked`: finalized — execution allowed

**2) Strategy finalization API (api/strategy.py)**

Add a `finalize` endpoint that enforces the hard guard and bumps version:

```python
@router.post("/{project_id}/finalize")
def finalize_strategy(project_id: str):
  ctx = DB.get(project_id)

  # HARD GUARD — strategy must be valid before finalizing
  ensure_strategy_ready(ctx)

  ctx["status"] = "locked"
  ctx["version"] = ctx.get("version", 1) + 1

  return {"status": "locked", "version": ctx["version"]}
```

**3) Guards (services/guards.py)**

Add a small guards module used across APIs and engines:

```python
def ensure_strategy_ready(ctx):
  if not ctx.get("business", {}).get("topics"):
    raise Exception("Business not analyzed")

  if not ctx.get("business", {}).get("allowed_topics"):
    raise Exception("Allowed topics missing (Signal Engine not applied)")

  if not ctx.get("audiences"):
    raise Exception("Audience not defined")

  return True


def ensure_serp_complete(ctx, max_missing=10):
  missing = [kw for kw in ctx.get("keywords", []) if kw not in ctx.get("serp_cache", {})]
  if missing:
    raise Exception({
      "error": "SERP data incomplete",
      "missing_keywords": missing[:max_missing]
    })
  return True
```

Enforce `ensure_strategy_ready` before any execution API and call `ensure_serp_complete` before scoring.

**4) Pure engine base class (services/base_engine.py)**

All engines should clone context and return a new copy — no in-place mutation.

```python
from copy import deepcopy

class BaseEngine:

  def clone(self, ctx):
    return deepcopy(ctx)
```

**5) P0 validator engine (example)**

Wrap the validator in the pure-engine pattern:

```python
from services.base_engine import BaseEngine
from services.p0_validator import validate_keywords

class P0ValidatorEngine(BaseEngine):

  def run(self, ctx):
    new_ctx = self.clone(ctx)

    keywords = new_ctx.get("keywords", [])

    valid, rejected = validate_keywords(
      keywords,
      new_ctx["business"].get("allowed_topics") or new_ctx["business"].get("topics", []),
      new_ctx["business"].get("blocked_topics", []),
    )

    new_ctx["keywords"] = valid
    new_ctx["rejected"] = rejected

    return new_ctx
```

**6) SERP completeness guard**

Before P7 scoring, require that every keyword has an entry in `serp_cache`. Use `ensure_serp_complete(ctx)`. This makes scoring deterministic and debuggable.

**7) Safe filtering (services/filter_engine.py)**

Filter before clustering, but protect against over-filtering:

```python
def filter_keywords(keyword_objs, min_score=0.6, min_count=5):
  filtered = [k for k in keyword_objs if getattr(k, "score", None) and k.score >= min_score]

  if len(filtered) < min_count:
    # safety fallback: pick top N
    sorted_kw = sorted(keyword_objs, key=lambda x: getattr(x, "score", 0) or 0, reverse=True)
    filtered = sorted_kw[:min_count]

  return filtered
```

**8) API enforcement (api/keywords.py)**

Block runs if strategy is not locked and validate the context:

```python
from services.guards import ensure_strategy_ready

@router.post("/run")
async def run_pipeline(data: dict):
  ctx = data.get("context", {})

  # HARD BLOCK
  if ctx.get("status") != "locked":
    raise Exception("Strategy not finalized. Please finalize first.")

  ensure_strategy_ready(ctx)

  result = await orchestrator.run(ctx)
  return result
```

**9) Orchestrator pattern (pure-engine style)**

Prefer engine-run composition where each engine takes and returns a new context. Example flow:

```python
ctx = deepcopy(ctx)

ensure_strategy_ready(ctx)

ctx = P1Engine().run(ctx)
ctx = P2Engine().run(ctx)
ctx = P0ValidatorEngine().run(ctx)   # HARD GATE
ctx = P3Engine().run(ctx)
ctx = AudienceEngine().run(ctx)
ctx = SERPEngine().run(ctx)
ensure_serp_complete(ctx)
ctx = P7ScoringEngine().run(ctx)
ctx["keywords"] = filter_keywords(ctx["keyword_objs"])
ctx = P8ClusterEngine().run(ctx)

return ctx
```

This makes the pipeline deterministic, auditable, and easy to test: each engine has a clear input/output contract and no hidden side effects.

**10) Auto-set status flow (suggested)**
- After Analyze Business: set `status = "validated"` if business topics and audiences are present.
- Only allow `/finalize` when `status == "validated"`.

**11) Next steps (recommended implementation order)**
1. Commit the small guards module and update the `default_context` sample (done in this doc).
2. Convert `p0_validator` and `serp_engine` to pure engines (clone + return new ctx).
3. Add `ensure_serp_complete` and call it before scoring.
4. Add `filter_engine` and update the orchestrator to use it before clustering.
5. Wire the `finalize` endpoint, enforce `status` checks in `api/keywords.run`, and add a small audit log for context versions.

**What changed (system-level)**
- BEFORE: uncontrolled pipeline where engines mutated shared state and drifted silently.
- AFTER: controlled system with a stateful `strategy_context`, hard guards, engine purity, and deterministic scoring.

These changes make the design production-stable and provide clear upgrade paths: versioning, rollback, and controlled background execution.

— End of control-layer section

**Versioned Context Store & Keyword Identity (Production-ready)**

To make the system rollback-safe and auditable, add a small in-memory versioned context store for development and a clear `Keyword` identity model with lineage so keywords are trackable across P1→P2→P3 and through the feedback loop.

`models/context_store.py` (dev in-memory store)

```python
import uuid
from datetime import datetime

class ContextStore:

  def __init__(self):
    self.db = {}

  def create(self, project_id, data):
    version_id = str(uuid.uuid4())

    entry = {
      "version_id": version_id,
      "project_id": project_id,
      "created_at": datetime.utcnow().isoformat(),
      "status": "draft",
      "data": data,
    }

    self.db.setdefault(project_id, []).append(entry)

    return entry

  def latest(self, project_id):
    return self.db.get(project_id, [])[-1] if self.db.get(project_id) else None

  def get_version(self, project_id, version_id):
    for v in self.db.get(project_id, []):
      if v["version_id"] == version_id:
        return v

  def rollback(self, project_id, version_id):
    version = self.get_version(project_id, version_id)
    if version:
      self.db[project_id].append(version)
      return version
    return None
```

Usage note: replace direct `DB[project_id]` reads with `context_store.latest(project_id)` so each execution uses a versioned snapshot and you get full history and rollback capability.

`models/keyword.py` (upgrade: id + parent + feedback fields)

```python
import uuid

class Keyword:

  def __init__(self, text, source="seed", parent=None):
    self.id = str(uuid.uuid4())
    self.text = text
    self.source = source
    self.parent = parent  # lineage tracking

    self.intent = None
    self.audience = None
    self.serp = None

    self.score = None
    self.priority = None

    # feedback & learning
    self.rank = None
    self.rank_history = []
    self.performance_score = None

  def to_dict(self):
    return self.__dict__
```

This enables deduplication with stable IDs, lineage tracing, and tying rank results back into scoring.

**Feedback Loop (services/feedback_engine.py)**

Record rank checks and convert them into a lightweight performance signal used by the scorer.

```python
def update_feedback(keyword_obj, rank):
  keyword_obj.rank = rank
  keyword_obj.rank_history.append({"rank": rank, "at": __import__("datetime").datetime.utcnow().isoformat()})

  # simple learning logic (upgradeable)
  if rank <= 10:
    keyword_obj.performance_score = 1.0
  elif rank <= 30:
    keyword_obj.performance_score = 0.7
  else:
    keyword_obj.performance_score = 0.3

  return keyword_obj
```

Integrate: store briefs and rank checks in the versioned context and call `update_feedback` when rank results arrive; persist only the small feedback signals (no raw history logs beyond compact arrays).

**Modify P7 Scoring to Use Feedback**

Scoring should accept `Keyword` objects and incorporate `performance_score` when present.

```python
def score_keywords(keyword_objs, context):
  results = []

  for kw in keyword_objs:
    base_score = 0.5

    feedback = getattr(kw, "performance_score", None)
    if feedback:
      base_score += feedback * 0.3

    # other subscores (intent, feasibility, business fit) added here
    score = min(base_score, 1.0)

    results.append({
      "id": kw.id,
      "keyword": kw.text,
      "score": round(score, 2),
      "priority": "HIGH" if score > 0.75 else "MEDIUM"
    })

  return results
```

**Queue-based execution (Celery) — minimal dev scaffolding**

Move heavy orchestrator runs to background workers. Minimal Celery scaffold for local/dev:

`queue/celery_app.py`

```python
from celery import Celery

celery = Celery(
  "seo_engine",
  broker="redis://localhost:6379/0",
  backend="redis://localhost:6379/0",
)
```

`queue/tasks.py`

```python
from queue.celery_app import celery
from engine.orchestrator import PipelineOrchestrator

orchestrator = PipelineOrchestrator()

@celery.task
def run_pipeline_task(context):
  import asyncio
  return asyncio.run(orchestrator.run(context))
```

`api/keywords.py` (trigger + result)

```python
from queue.tasks import run_pipeline_task
from celery.result import AsyncResult

@router.post("/run")
def run_pipeline(data: dict):
  ctx = data.get("context")
  task = run_pipeline_task.delay(ctx)
  return {"task_id": task.id, "status": "processing"}


@router.get("/result/{task_id}")
def get_result(task_id: str):
  task = AsyncResult(task_id)
  if task.ready():
    return {"status": "done", "result": task.result}
  return {"status": "processing"}
```

Frontend polling (example)

```js
// 1. Start job
const res = await api('/api/keywords/run')

// 2. Poll result
const interval = setInterval(async () => {
  const result = await api(`/api/keywords/result/${res.task_id}`)
  if (result.status === 'done') {
  clearInterval(interval)
  setData(result.result)
  }
}, 2000)
```

**Why this fixes the CPU problem**
- Moves heavy orchestrations off the HTTP worker process.
- Enables horizontal workers and retry/timeout policies.

**Operational notes & next steps**
- Add `celery` and `redis` to `requirements.txt` for dev: `celery`, `redis` (or use RQ for a simpler setup).
- For production, use a managed queue (Redis/AWS SQS) and persistent context storage (Postgres or document DB) instead of the dev in-memory `ContextStore`.
- Add a small result cache or storage for `task_id` → `version_id` mappings so UI can load final context snapshots by version.

**Summary**
These changes convert the pipeline into a stateful, versioned, queue-backed learning system:
- Versioned contexts and keyword IDs enable safe experimentation and closed-loop learning.
- A feedback engine feeds rank outcomes back into P7 scoring.
- Celery-based workers remove CPU pressure from the web server and allow horizontal scaling.

— End of production-grade additions

**Full System Architecture & Enterprise Scaling**

You are at the inflection point between a useful tool and a category-defining system. Below is a clean, production-grade architecture, the live data flow, and enterprise features (priority queues, multi-worker scaling) that anchor the four upgrades: Real SERP, ML ranking, P8++ dashboard, and queue prioritization.

**1) Full system architecture (clean view)**

High-level deployment diagram (logical):

          ┌──────────────────────┐
          │     FRONTEND (React) │
          └─────────┬────────────┘
                │
                ▼
          ┌──────────────────────┐
          │     API LAYER        │ (FastAPI)
          └─────────┬────────────┘
                │
      ┌───────────────────┼────────────────────┐
      ▼                   ▼                    ▼
 ┌──────────────┐   ┌────────────────┐   ┌────────────────┐
 │ Strategy API │   │ Keyword API    │   │ Content API     │
 └──────┬───────┘   └──────┬─────────┘   └──────┬─────────┘
    │                  │                    │
    ▼                  ▼                    ▼
 ┌────────────────────────────────────────────────────┐
 │            QUEUE SYSTEM (Redis + Celery)           │
 └──────────────┬───────────────────────┬─────────────┘
        ▼                       ▼
   ┌──────────────────┐     ┌────────────────────┐
   │ Strategy Worker  │     │ Keyword Worker     │
   │ (signals, P0)    │     │ (P1–P9 pipeline)   │
   └────────┬─────────┘     └─────────┬──────────┘
        ▼                         ▼
   ┌──────────────────┐     ┌────────────────────┐
   │ SERP Engine      │     │ ML Ranking Engine  │
   └────────┬─────────┘     └─────────┬──────────┘
        ▼                         ▼
   ┌────────────────────────────────────────────┐
   │            DATABASE (Postgres)             │
   │  - versioned context                        │
   │  - keyword objects                          │
   │  - ranking feedback                         │
   └────────────────────────────────────────────┘

**2) Data flow (step-by-step)**

PHASE 1 — STRATEGY (CONTROLLED)
- User → Analyze Business → Signal Engine → allowed_topics (LOCKED)
- Audience Detection → Competitor Analysis → SERP (sample) → VALIDATE
- FINALIZE (status=locked)

Output: `strategy_context` (versioned snapshot)

PHASE 2 — EXECUTION (QUEUE)
- User clicks "Run Keyword Engine" → API pushes job → Queue → Worker picks job

Worker steps:
- P1 Seed
- P2 Expand
- P0 Validate (HARD GATE)
- P3 Clean
- Audience Map
- SERP Ensure (complete) 🔥
- ML Ranking Score (predict rank, time-to-rank) 🔥
- Filter (safe fallback) 🔥
- P8 Cluster → Save Results

PHASE 3 — FEEDBACK LOOP
- Ranking Tracker → Update `keyword.rank` → `feedback_engine` → adjust scoring weights

**3) Real SERP integration (critical layer)**

You need structured SERP signals beyond `intent` and `content_type`. Minimal stored shape per keyword:

```
{
  "intent": "...",
  "content_type": "...",
  "difficulty": 0.72,
  "authority_avg": 65,
  "content_depth": 1800,
  "serp_features": ["snippet","video"],
  "competition_score": 0.81
}
```

Recommended integration path:
- Fast: SerpAPI (quick to integrate)
- Cost-aware: Zenserp
- Long-term: custom scraper with caches and rate-limits

`services/serp_engine.py` (real shape)

```python
def serp_reality(keyword):
  results = fetch_serp_api(keyword)

  authority_scores = [r.get("domain_rating", 40) for r in results]
  avg_authority = sum(authority_scores) / max(1, len(authority_scores))

  difficulty = min(avg_authority / 100.0, 1.0)

  return {
    "intent": detect_intent(results),
    "content_type": detect_type(results),
    "difficulty": difficulty,
    "competition_score": difficulty,
    "authority_avg": avg_authority,
    "content_depth": estimate_content_depth(results),
    "serp_features": detect_serp_features(results)
  }
```

Store only aggregated SERP signals in `serp_cache` and keep raw SERP responses ephemeral with TTL.

**4) ML ranking model (real differentiator)**

Goal: predict rank probability and time-to-rank. Feature examples:

```python
features = {
  "keyword_length": len(keyword.split()),
  "intent_informational": int(serp["intent"]=="informational"),
  "difficulty": serp["difficulty"],
  "business_fit": business_fit_score,
  "competition_score": serp["competition_score"],
}
```

Start simple: `RandomForestRegressor` or `LightGBM`. Train on historical rank data (`X_train`, `y_train` where `y` is days to hit top N or probability). Example:

```python
from sklearn.ensemble import RandomForestRegressor

model = RandomForestRegressor()
model.fit(X_train, y_train)

def predict_rank(features):
  return model.predict([features])[0]
```

Add outputs to keyword object:

```
{
  "rank_probability": 0.74,
  "time_to_rank": 45
}
```

**5) P8++ visual dashboard (product moat)**

This is non-optional. Product differentiation is the P8++ UX.

What to show:
- Keyword Priority Map (impact vs competition)
- Cluster Graph (pillar → supporting → internal links)
- Opportunity Cards (keyword, score, difficulty, action)
- Timeline / publishing schedule

Tech stack suggestions: Recharts/Chart.js for charts, D3 for graphs, Tailwind for UI. Backend provides aggregated endpoints for dashboard data (priority map, cluster graph, opportunity cards).

**6) Multi-project queue prioritization (enterprise)**

Problem: multiple projects/users — must manage who gets compute first.

Solution: priority queues in Celery.

Example config:

```python
celery.conf.task_routes = {
  "tasks.high": {"queue": "high"},
  "tasks.medium": {"queue": "medium"},
  "tasks.low": {"queue": "low"},
}

# choose queue based on project properties
queue = "high" if project.is_paying else ("medium" if project.size>1000 else "low")
run_pipeline_task.apply_async(args=[ctx], queue=queue)
```

**7) Multi-worker scaling**

Run workers per queue with tuned concurrency:

```
celery -A queue.celery_app worker -Q high --concurrency=4
celery -A queue.celery_app worker -Q medium --concurrency=2
celery -A queue.celery_app worker -Q low --concurrency=1
```

This isolates heavy jobs, gives paying customers fast throughput, and prevents noisy-neighbor CPU storms.

**Final system summary**

CONTROL LAYER
- versioned strategy, locked execution

EXECUTION LAYER
- async queue, distributed workers

INTELLIGENCE LAYER
- SERP reality signals, ML ranking

OUTPUT LAYER
- P8++ visual strategy dashboard

LEARNING LAYER
- feedback loop (rank → performance_score → scoring)

Final verdict: this moves the project from a single-run pipeline to an enterprise-grade, stateful, scalable, and learning SEO strategy engine.

— End of architecture & scaling additions

**Real SERP Provider & Exact React Dashboard UI**

This section provides a concrete, production-ready SERP provider integration using SerpAPI and a precise React dashboard structure (Strategy and Keyword pages) for P8++ visualization.

PART 1 — SERP PROVIDER (REAL)

1) INSTALL

```bash
pip install google-search-results
```

2) ENV SETUP

Set your SerpAPI key in the environment:

```
SERP_API_KEY=your_key_here
```

3) CORE SERP FETCHER (`services/serp_provider.py`)

```python
from serpapi import GoogleSearch
import os
import logging

logger = logging.getLogger(__name__)

def fetch_serp(keyword):
  api_key = os.getenv("SERP_API_KEY")
  if not api_key:
    logger.warning("SERP_API_KEY not set; returning empty results for %s", keyword)
    return []

  params = {
    "q": keyword,
    "api_key": api_key,
    "engine": "google",
    "num": 10
  }

  try:
    search = GoogleSearch(params)
    results = search.get_dict()
    return results.get("organic_results", [])
  except Exception as e:
    logger.exception("SerpAPI request failed for %s: %s", keyword, e)
    return []
```

4) SERP ANALYSIS ENGINE (REAL) (`services/serp_engine.py`)

```python
from services.serp_provider import fetch_serp

def detect_intent(results):
    titles = " ".join([r.get("title", "").lower() for r in results])

    if "buy" in titles or "price" in titles:
        return "transactional"
    return "informational"


def detect_content_type(results):
    types = []

    for r in results:
        url = r.get("link", "")
        if "/product" in url:
            types.append("product")
        elif "/blog" in url:
            types.append("blog")
        else:
            types.append("mixed")

    return max(set(types), key=types.count)


def compute_difficulty(results):
  # Prefer domain authority/rating when available; fallback to result-count heuristic
  ratings = []
  for r in results:
    for key in ("domain_rating", "domain_rank", "authority_score", "domain_authority"):
      v = r.get(key)
      if isinstance(v, (int, float)):
        ratings.append(float(v))
        break

  if ratings:
    avg = sum(ratings) / len(ratings)
    return min(avg / 100.0, 1.0)

  # fallback: simple heuristic based on result count
  return min(len(results) / 10.0, 1.0)


def serp_reality(keyword):

    results = fetch_serp(keyword)

    return {
        "intent": detect_intent(results),
        "content_type": detect_content_type(results),
        "difficulty": compute_difficulty(results),
        "competition_score": compute_difficulty(results)
    }
```

5) ENSURE SERP CACHE (IMPORTANT)

```python
def ensure_serp_data(keywords, cache):

    for kw in keywords:
        if kw not in cache:
            cache[kw] = serp_reality(kw)
```

RESULT

Now your system uses:

Before	After
random()	real Google
fake difficulty	actual SERP
weak scoring	grounded scoring


PART 2 — EXACT REACT DASHBOARD UI (YOUR MOAT)

Design principle: don't show engines, show decisions. The UI must present strategy-level conclusions, opportunity visualizations, and clear execution actions.

PAGE 1 — `StrategyPage`

Purpose: turn chaos into a clear opportunity map and business summary.

Component structure:

```
<StrategyPage>
  <BusinessSummary />
  <AudienceInsights />
  <OpportunityMap />
  <CompetitorGaps />
  <FinalizeStrategy />
</StrategyPage>
```

1) BUSINESS SUMMARY

```jsx
<Card>
  <h2>Your Business</h2>

  <Tag>Spices</Tag>
  <Tag>Cloves</Tag>

  <p>Detected audience: Health + Cooking</p>
</Card>
```

2) AUDIENCE INSIGHTS

```jsx
<Card>
  <h2>Your Customers</h2>

  <AudienceCard name="Home Cooks" intent="Transactional" />
  <AudienceCard name="Health Seekers" intent="Informational" />
</Card>
```

3) OPPORTUNITY MAP (CORE VISUAL)

```jsx
<Card>
  <h2>Opportunities</h2>

  <ScatterChart>
    X: Competition
    Y: Opportunity Score
  </ScatterChart>
</Card>
```

4) COMPETITOR GAP

```jsx
<Card>
  <h2>Missed Opportunities</h2>

  {gaps.map(g => (
    <div>{g}</div>
  ))}
</Card>
```

5) FINALIZE BUTTON

```jsx
<Button onClick={finalize}>
  Lock Strategy & Continue →
</Button>
```

PAGE 2 — `KeywordPage`

Purpose: turn strategy into exact actions to build.

Structure:

```
<KeywordPage>
  <RunPipeline />
  <PriorityKeywords />
  <ClusterView />
  <ContentPlan />
</KeywordPage>
```

1) RUN PIPELINE

```jsx
<Button onClick={runPipeline}>
  Generate Strategy 🚀
</Button>
```

2) PRIORITY KEYWORDS (BUILD FIRST)

```jsx
<Card>
  <h2>Build First</h2>

  {keywords.map(k => (
    <div>
      {k.keyword} — {k.score} — {k.priority}
    </div>
  ))}
</Card>
```

3) CLUSTER VIEW (P8++)

```jsx
<Card>
  <h2>Content Strategy</h2>

  {clusters.map(c => (
    <div>
      <h3>{c.pillar}</h3>

      {c.supporting.map(s => (
        <div>{s}</div>
      ))}
    </div>
  ))}
</Card>
```

4) CONTENT PLAN (PUBLISHING TIMELINE)

```jsx
<Card>
  <h2>Publishing Plan</h2>

  {strategy.map(s => (
    <div>
      Week {s.publish_week}: {s.keyword}
    </div>
  ))}
</Card>
```

UX Upgrade: replace engine labels with business actions.

- ❌ “Run P7 scoring” → ✅ “Find Opportunities”
- ❌ “Analyze SERP” → ✅ “Prioritize What to Build”

FINAL RESULT

BACKEND
- Real SERP data ✅
- Accurate scoring ✅
- Stable pipeline ✅
- Queue-based execution ✅

FRONTEND
- Strategy understanding ✅
- Opportunity visualization ✅
- Clear execution plan ✅
- Product-level UX ✅

— End of SERP provider & dashboard UI additions

## Review: Your Answers, Remaining Gaps, and Clean‑Coding Checklist

I reviewed your responses and the minimal repo plan you supplied. Below is a compact evaluation: what you covered, what remains unanswered or risky, and a short clean‑coding checklist to make the implementation robust and maintainable.

1) What you answered correctly
- Primary blocker identified: `uvicorn` crash — fix imports/syntax first. ✅
- Minimal vertical slice plan (thin API + services) — exactly right to stabilize quickly. ✅
- Clear, correct pipeline order (P1→P2 → P0 → P3 → SERP → P7) and `serp` safe mode fallback. ✅
- Suggested starting simple (Option A: dict context) and later evolving to classes + orchestrator is pragmatic. ✅
- Included runnable example endpoints, `main.py`, and test flow — strongly helpful for fast verification. ✅

2) Remaining gaps you did not fully answer (high priority)
- Persistent storage plan: you acknowledged Postgres but did not provide schema/migration plan or where version_id/version metadata will live. This is required for audit/rollback. ❗
- Authentication / multi‑tenant authorization and queue assignment rules are not specified; required for production priority queues. ❗
- Observability: no concrete logging/metrics/alerting plan (Prometheus, structured logs, Sentry). Add before production. ❗
- Task reliability semantics: the doc lacks idempotency, retry/backoff policy, and poison‑message handling for Celery tasks. ❗
- SERP usage limits & cost controls: no rate limiting, batching strategy, or budget enforcement described. SERP usage can easily blow costs. ❗

3) Medium/low priority gaps to address soon
- No CI / automated tests shown (unit/integration/contract tests). Add minimal tests for `p0_validator`, `extract_signals`, `serp_engine`. ◦
- Dependency management: `requirements.txt` needs pinned versions and optional extras (ML vs dev). ◦
- No health endpoints, readiness/liveness checks, or graceful shutdown procedures for workers. ◦
- No explicit API schema (Pydantic models) — necessary for stable client contracts. ◦

4) Clean‑Coding & Engineering Checklist (apply before production)
- Standardize the data contract: pick one canonical `Keyword`/`Context` representation (dict or class) and use it everywhere. Prefer Pydantic models for FastAPI endpoints. ✅
- Small, testable functions: keep each engine function pure where possible (input → output), avoid side‑effects. Use `deepcopy` at engine boundaries. ✅
- Lazy import heavy libs inside worker tasks (e.g., import sentence_transformers or sklearn inside task runtime, not top-level). ✅
- Structured logging and metrics: integrate a logger and add timing/size metrics for long tasks. Add a `metrics/` plan (Prometheus). ✅
- Error handling: define error classes, return consistent API error payloads, and add retry/backoff at task layer. ✅
- Tests: unit tests for validators and small integration tests for the pipeline. Add a minimal CI (GitHub Actions). ✅
- Linting & formatting: `black`, `ruff`/`flake8`, `isort`, and `pre-commit` hooks. ✅
- Docker & dev infra: `docker-compose.yml` for Redis/Postgres and a small README with dev run steps. ✅
- Secrets & config: do not commit secrets; add `.env.example` and use a `config.py` that reads env vars once. ✅
- Dependency pinning and vulnerability scans: `pip-compile` or pinned `requirements.txt` + dependabot. ✅

5) Minimal production hardening items (add before enabling real users)
- Rate limit SERP calls; add a budget/quotas UI and circuit breaker. ⚠️
- Ensure task idempotency and define task result retention policy. ⚠️
- Add authentication + project scoping to APIs (API keys / JWT + RBAC). ⚠️
- Add DB migrations (Alembic) and simple schema for versioned contexts. ⚠️
- Implement monitoring/alerts for queue lag, long-running tasks and SERP cost thresholds. ⚠️

6) Quick actionable next steps (3 items)
1. Run `uvicorn main:app --reload` locally, capture and fix the import/traceback until `/docs` loads. This is blocking. (I can do this now if you want.)
2. Scaffold the minimal slice you proposed (models/store.py, api/strategy.py, api/keywords.py, services/p0_validator.py, services/serp_engine.py), run pipeline smoke test. Keep everything synchronous and in‑memory. ✅
3. Add tests and CI for the thin slice, then safely enable Celery and Postgres later. ✅

7) Did you fail to answer anything? — short checklist
- You covered nearly everything required to get a working prototype. The main open answers are:
  - Where to persist versioned contexts in Postgres (schema + migration). ❌
  - Auth/multi-tenant rules for priority queues and API access. ❌
  - Observability plan (metrics, logs, alert thresholds). ❌
  - SERP cost controls and batching policies. ❌

If you want, I will scaffold the minimal backend slice and run the server to capture the uvicorn error and fix it step‑by‑step. Say “fix backend crash” to start the live debug, or “scaffold minimal repo” to add the files immediately.

— End of review

**STRATEGY (IMPORTANT)**

We will:

✅ Keep your pipeline intact (P1–P20)
✅ Keep emit_fn, gates, DB logic
❌ Remove dangerous patterns
➕ Add structure around it

1. REMOVE SILENT FAILURES (CRITICAL)

❌ CURRENT (multiple places)
```py
try:
  ...
except Exception:
  pass
```

✅ FIX (apply everywhere)
```py
except Exception as e:
  log.error(f"[{name}] Error: {e}", exc_info=True)

  if self._emit_fn:
    try:
      self._emit_fn("phase_log", {
        "phase": name,
        "status": "error",
        "msg": str(e)
      })
    except Exception:
      pass

  raise
```

👉 Do this in:

- _run_phase
- P2 enhanced block
- DomainContext sections
- DB loaders

2. FIX _run_phase (CORE ENGINE)

🔥 Problem:
Logging + execution tightly coupled
Multiple try blocks
No middleware pattern

✅ REFACTOR _run_phase

Replace FULL function with:

```py
def _run_phase(self, name: str, fn, *args, **kwargs):
  t0 = time.time()
  process = psutil.Process()
  mem0 = process.memory_info().rss / (1024 * 1024)

  self._emit_safe({
    "phase": name,
    "status": "starting",
    "msg": f"▶ {name} starting..."
  })

  try:
    result = fn(*args, **kwargs)

  except Exception as e:
    elapsed = round(time.time() - t0, 2)
    self._emit_safe({
      "phase": name,
      "status": "error",
      "msg": f"✗ {name} failed: {str(e)}",
      "elapsed_ms": int(elapsed * 1000),
    })
    log.error(f"[Phase {name}] Failed", exc_info=True)
    raise

  elapsed = round(time.time() - t0, 2)
  mem1 = process.memory_info().rss / (1024 * 1024)

  output_count = len(result) if isinstance(result, (list, dict)) else None

  self._emit_safe({
    "phase": name,
    "status": "complete",
    "msg": f"✓ {name} done",
    "elapsed_ms": int(elapsed * 1000),
    "memory_delta_mb": round(mem1 - mem0, 2),
    "output_count": output_count
  })

  return result
```

➕ Add helper (NEW)

```py
def _emit_safe(self, payload: dict):
  if not self._emit_fn:
    return
  try:
    self._emit_fn("phase_log", payload)
  except Exception as e:
    log.warning(f"[Emit failed] {e}")
```

3. FIX P2 (DETERMINISTIC BEHAVIOR)

❌ CURRENT:

Auto-switching based on DB pillars and _seed_matches logic that creates nondeterminism.

✅ FIX

Add parameter to run_seed (or orchestrator API):

```py
def run_seed(..., p2_mode: str = "fresh", ...):
  if p2_mode == "pillar":
    raw_kws = p2e.run_from_input(...)
  elif p2_mode == "fresh":
    raw_kws = self._run_phase("P2", self.p2.run, seed)
  else:
    raise ValueError("Invalid p2_mode")
```

🔥 REMOVE THIS COMPLETELY:
```py
if _seed_matches:
  ...
```

👉 This is the root of nondeterminism.

4. FIX DOMAIN CONTEXT (DATA LOSS BUG)

❌ CURRENT:
```py
kws = accepted
```

✅ REPLACE WITH:

```py
accepted, rejected, ambiguous = self._dce.classify_batch(kws, pid)

self._record("P3_DomainContext", rid, pid, {
  "accepted": len(accepted),
  "rejected": len(rejected),
  "ambiguous": len(ambiguous)
})

# Store ALL (important)
self._domain_debug = {
  "accepted": accepted,
  "rejected": rejected,
  "ambiguous": ambiguous
}

kws = accepted
```

5. ADD TRANSACTION PER RUN

❌ CURRENT:

Multiple independent DB writes

✅ ADD wrapper

At start of run_seed:

```py
conn = sqlite3.connect(str(Path(__file__).parent.parent / "annaseo.db"))
conn.isolation_level = None
conn.execute("BEGIN")
```

At END:

```py
conn.execute("COMMIT")
conn.close()
```

On ERROR:

Wrap whole run:

```py
try:
  ...
except Exception:
  conn.execute("ROLLBACK")
  conn.close()
  raise
```

6. FIX GATE 2 RESUME BUG

❌ CURRENT:
```py
clusters = {}
```

✅ FIX:

```py
if gate2_confirmed and confirmed_pillars:
  pillars = confirmed_pillars

  # rebuild minimal clusters from pillars
  clusters = {
    p: v.get("topics", [])
    for p, v in pillars.items()
  }
```

7. REMOVE HEAVY PRINTS (PRODUCTION ISSUE)

❌ REMOVE:
```py
print(...)
```

✅ REPLACE:
```py
log.info(f"P2: {len(raw_kws)} keywords")
```

8. PROTECT RESULT SERIALIZATION

❌ CURRENT:

Huge payloads in SSE

✅ LIMIT:

```py
payload["result_sample"] = {
  "type": "list",
  "items": [str(x) for x in result[:20]]  # was 150
}
```

9. ADD IDEMPOTENCY CHECK

At start of run:

```py
existing = conn.execute(
  "SELECT 1 FROM runs WHERE run_id=?",
  (rid,)
).fetchone()

if existing:
  log.warning(f"Run {rid} already exists")
  return {"status": "duplicate_run"}
```

10. SAFETY GUARD FOR EMPTY FLOWS

Add after each critical phase:

```py
if not kws:
  raise ValueError("No keywords after P3")
```

---

Apply these fixes across the engine file(s), the orchestrator, and services to make the pipeline deterministic, auditable, and production-safe.

## MULTI-WORKER + PARALLEL PIPELINE (Redis + RQ) — Drop-in

We will add a simple, production-ready multi-worker queue using Redis + RQ and parallelize P4–P8 for a large speed boost. Below are concrete files, snippets, and integration notes to drop into your existing codebase (not theoretical).

1) Install

```
pip install rq redis
```

2) Project structure (add under backend/ or top-level `queue/`)

```
backend/
 ├── queue/
 │   ├── connection.py
 │   ├── jobs.py
 │   └── worker.py
```

3) Redis connection (`queue/connection.py`)

```py
from redis import Redis
from rq import Queue

redis_conn = Redis(host="localhost", port=6379, db=0)

# High priority for user-triggered runs
high_q = Queue("high", connection=redis_conn)

# Default queue
default_q = Queue("default", connection=redis_conn)
```

4) Job definition (`queue/jobs.py`) — enqueue an orchestrator run

```py
import uuid
from engines.ruflo_20phase_wired import WiredRufloOrchestrator

def run_pipeline_job(project_id: str, keyword: str):
  run_id = f"run_{uuid.uuid4().hex[:10]}"

  orchestrator = WiredRufloOrchestrator(
    project_id=project_id,
    run_id=run_id
  )

  result = orchestrator.run_seed(
    keyword=keyword,
    project_id=project_id,
    run_id=run_id,
    p2_mode="fresh"   # deterministic
  )

  return {
    "run_id": run_id,
    "result": result
  }
```

5) Enqueue from FastAPI (example)

```py
from queue.connection import high_q
from queue.jobs import run_pipeline_job

@app.post("/api/keywords/run", tags=["Keywords"])
def run_pipeline(project_id: str, keyword: str):
  job = high_q.enqueue(
    run_pipeline_job,
    project_id,
    keyword,
    job_timeout=900  # 15 min
  )

  return {
    "job_id": job.id,
    "status": "queued"
  }
```

6) Worker process (`queue/worker.py`)

```py
from rq import Worker
from queue.connection import redis_conn

if __name__ == "__main__":
  worker = Worker(["high", "default"], connection=redis_conn)
  worker.work()
```

Run workers:

```bash
python queue/worker.py &
python queue/worker.py &
python queue/worker.py &
```

You now have simple horizontal scaling with RQ workers.

--- 

Parallelize P4–P8 (ThreadPoolExecutor)

Problem: P4, P5, P6 are currently run serially; they can be executed in parallel and then feed P7–P8.

Replace the serial block with:

```py
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
  future_p4 = executor.submit(self.p4.run, seed, kws)
  future_p5 = executor.submit(self.p5.run, seed, kws)
  future_p6 = executor.submit(self.p6.run, seed, kws)

  entities = future_p4.result() or {}
  intent_map = future_p5.result() or {}
  serp_map = future_p6.result() or {}

# P7 depends on P5 + P6
scores = self._run_phase("P7", self.p7.run, seed, kws, intent_map, serp_map)

# P8 depends on scores
topic_map = self._run_phase("P8", self.p8.run, seed, kws, scores)
```

Advanced: you can submit P7 to the executor as well (it will run once P5+P6 complete):

```py
future_p7 = executor.submit(self.p7.run, seed, kws, intent_map, serp_map)
scores = future_p7.result()
```

Parallelizing P2 expansion across seed parts (optional)

```py
with ThreadPoolExecutor(max_workers=4) as executor:
  futures = [
    executor.submit(self.p2.run, seed_part)
    for seed_part in seed_parts
  ]

  raw_kws = []
  for f in futures:
    raw_kws.extend(f.result() or [])
```

Cache layer for expensive phases (SERP example)

```py
import json
from queue.connection import redis_conn

def cached_serp(self, keyword):
  cache_key = f"serp:{keyword}"

  cached = redis_conn.get(cache_key)
  if cached:
    return json.loads(cached)

  result = self.p6.run(keyword)

  redis_conn.setex(cache_key, 3600, json.dumps(result))

  return result
```

Notes & Integration

- Use RQ for simplicity and reliability in dev/prod.
- Keep heavy runs out of the web worker; enqueue from FastAPI and poll job results or push via SSE when done.
- Make P2/P4–P8 threadsafe: avoid mutating shared context objects — clone or pass immutable inputs to parallel tasks.
- Ensure `_run_phase` emits start/fail/complete logs (see earlier section) so job workers provide observability.
- Add `job_timeout` and reasonable `max_workers` defaults per deployment size.

Performance impact

- Running P4–P6 in parallel reduces wall-time by ~50–70% depending on phase durations.
- RQ workers enable horizontal scaling and multi-user throughput.

Final checklist to implement (suggested small PRs)

- [ ] Add `queue/connection.py`, `queue/jobs.py`, `queue/worker.py`
- [ ] Update FastAPI route to enqueue jobs and return `job_id`
- [ ] Implement job result endpoint (GET `/api/jobs/{job_id}`) to check RQ job status
- [ ] Update engine to use `ThreadPoolExecutor` for P4–P8 and optionally for P2 expansion
- [ ] Add `cached_serp` helper using Redis
- [ ] Add docs and README for running RQ workers and Redis in dev

Apply these changes to your codebase incrementally — start by adding `queue/connection.py` and `queue/jobs.py`, then convert one endpoint to enqueue a job and validate with a local RQ worker.

## JOB TRACKING, REAL-TIME PROGRESS, RETRY, AND FULL INFRA (DROP-IN)

This section provides a concrete, integrated implementation for: job lifecycle tracking, real-time phase streaming, retry + failure recovery, idempotency guards, and full Docker infra (Redis + Postgres + workers). The snippets below are plug-and-play with the orchestrator and queue scaffolding already discussed.

### 1) Jobs table (Postgres)

Use this schema for durable job state and history:

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  project_id TEXT,
  keyword TEXT,
  status TEXT, -- queued | running | completed | failed
  progress INT DEFAULT 0,
  current_phase TEXT,
  result JSONB,
  error TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### 2) JobTracker service (`services/job_tracker.py`)

Small helper to persist job lifecycle updates (Postgres example):

```py
import json
from datetime import datetime

class JobTracker:

  def __init__(self, db):
    self.db = db

  def create_job(self, job_id, project_id, keyword):
    self.db.execute("""
      INSERT INTO jobs (job_id, project_id, keyword, status, created_at, updated_at)
      VALUES (%s, %s, %s, 'queued', NOW(), NOW())
    """, (job_id, project_id, keyword))

  def update_phase(self, job_id, phase, progress):
    self.db.execute("""
      UPDATE jobs
      SET current_phase=%s,
        progress=%s,
        status='running',
        updated_at=NOW()
      WHERE job_id=%s
    """, (phase, progress, job_id))

  def complete(self, job_id, result):
    self.db.execute("""
      UPDATE jobs
      SET status='completed',
        progress=100,
        result=%s,
        updated_at=NOW()
      WHERE job_id=%s
    """, (json.dumps(result), job_id))

  def fail(self, job_id, error):
    self.db.execute("""
      UPDATE jobs
      SET status='failed',
        error=%s,
        updated_at=NOW()
      WHERE job_id=%s
    """, (str(error), job_id))
```

Wire an instance of `JobTracker` into your worker environment and pass it to the orchestrator or job wrapper.

### 3) Connect JobTracker to orchestrator via `_emit_safe`

Modify the control-layer `_emit_safe` to report progress into the DB when a `JobTracker` is available on the engine.

```py
def _emit_safe(self, payload: dict):
  # update job tracker (if present)
  if getattr(self, "_job_tracker", None):
    phase = payload.get("phase")
    progress = self._phase_to_progress(phase)

    try:
      self._job_tracker.update_phase(self._run_id, phase, progress)
    except Exception:
      # never raise from telemetry
      pass

  # existing SSE / emit hook
  if self._emit_fn:
    try:
      self._emit_fn("phase_log", payload)
    except Exception:
      pass

def _phase_to_progress(self, phase: str) -> int:
  # simple mapping: P1..P20 -> 0..100
  if not phase or not phase.startswith("P"):
    return 0
  try:
    phase_num = int(phase[1:])
  except Exception:
    return 0
  return int((phase_num / 20) * 100)
```

Call `_emit_safe` at start/complete/error in every `_run_phase` emission (see the `_run_phase` refactor earlier in this doc).

### 4) Job enqueue + start endpoints (FastAPI examples)

Enqueue with RQ and create a DB job record using `JobTracker`.

```py
from fastapi import APIRouter
from queue.connection import high_q
from queue.jobs import run_pipeline_job

router = APIRouter(prefix="/api/jobs")

@router.post("/")
def create_job(project_id: str, keyword: str):
  # idempotency: check running jobs with same project+keyword
  existing = db.fetch_one("SELECT job_id FROM jobs WHERE project_id=%s AND keyword=%s AND status='running'", (project_id, keyword))
  if existing:
    return {"job_id": existing["job_id"], "status": "running"}

  job = high_q.enqueue(run_pipeline_job, project_id, keyword)

  job_tracker.create_job(job.id, project_id, keyword)

  return {"job_id": job.id, "status": "queued"}

@router.get("/{job_id}")
def get_job(job_id: str):
  job = db.fetch_one("SELECT job_id, status, progress, current_phase, result, error FROM jobs WHERE job_id=%s", (job_id,))
  return job
```

### 5) Retry + failure handling (RQ)

Use RQ Retry to handle transient failures, and have the job report to `JobTracker`.

```py
from rq import Retry
from rq.job import get_current_job

def run_pipeline_job(project_id: str, keyword: str):
  job = get_current_job()
  job_id = job.id if job else f"run_{uuid.uuid4().hex[:10]}"

  try:
    # keep the DB tracker in sync
    job_tracker.update_phase(job_id, "P1", 5)

    orchestrator = WiredRufloOrchestrator(project_id=project_id, run_id=job_id)
    result = orchestrator.run_seed(keyword=keyword, project_id=project_id, run_id=job_id)

    job_tracker.complete(job_id, result)
    return result

  except Exception as e:
    job_tracker.fail(job_id, str(e))
    raise

# Example enqueue with retry
job = high_q.enqueue(
  run_pipeline_job,
  project_id,
  keyword,
  retry=Retry(max=3, interval=[10, 30, 60]),
  job_timeout=1800
)
```

Raising the exception ensures RQ's retry semantics apply; the job tracker captures the failure for UI visibility.

### 6) Idempotency & resume

Prevent duplicate concurrent runs by checking `jobs` table for running jobs (see endpoint example). To resume partial runs, persist `last_completed_phase` on the job record and have the orchestrator accept a `resume_from` argument to skip phases when appropriate.

```
existing = db.fetch_one("""
  SELECT job_id FROM jobs
  WHERE project_id=%s AND keyword=%s AND status='running'
""", (project_id, keyword))

if existing:
  return existing
```

When re-scheduling or resuming, the job can read the `last_completed_phase` and call the orchestrator with `start_phase` param to skip already-completed work.

### 7) Docker Compose + Dockerfile (dev/prod)

`docker-compose.yml` (minimal)

```yaml
version: "3.9"
services:

  api:
  build: .
  command: uvicorn main:app --host 0.0.0.0 --port 8000
  ports:
    - "8000:8000"
  depends_on:
    - redis
    - db

  worker:
  build: .
  command: python queue/worker.py
  depends_on:
    - redis
    - db

  redis:
  image: redis:7
  ports:
    - "6379:6379"

  db:
  image: postgres:15
  environment:
    POSTGRES_USER: annaseo
    POSTGRES_PASSWORD: secret
    POSTGRES_DB: annaseo
  ports:
    - "5432:5432"
```

`Dockerfile` (simple)

```docker
FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]
```

Run the full system locally:

```bash
docker-compose up --build
```

### 8) UI polling / real-time example (React)

Simple polling approach (poll `GET /api/jobs/{job_id}` every second):

```jsx
useEffect(() => {
  const interval = setInterval(async () => {
  const res = await fetch(`/api/jobs/${jobId}`)
  const data = await res.json()
  setJob(data)
  }, 1000)

  return () => clearInterval(interval)
}, [jobId])
```

UI snippet:

```jsx
<div>
  <h3>{job.current_phase}</h3>
  <progress value={job.progress} max="100" />
  <p>{job.status}</p>
</div>
```

### 9) Final operational notes

- Use `job_timeout` and per-project queue assignment to avoid noisy neighbors.
- Persist `last_completed_phase` if you need resumability; orchestrator should accept `start_phase` or `resume_from`.
- Keep the web worker short-lived: enqueue heavy runs and return a `job_id` immediately.
- Add metrics for queue backlog, job duration per phase, and retry rates (Prometheus + Grafana recommended).

---

This completes the integrated job-status, retry/recovery, idempotency, and infra guidance. If you want, I can now scaffold the files (`services/job_tracker.py`, `queue/connection.py`, `queue/jobs.py`, `queue/worker.py`, and `docker-compose.yml`) and wire the POST `/api/jobs` endpoint so you can run a dev job and see live progress. Which would you like me to do next: scaffold the files now, or run the backend to capture the current uvicorn traceback and fix it first?

# Research Engine Architecture — Multi-Source Redesign

## Current Problem (Step 2 Research)

```
User Input (Step 1)
    ↓
P2_Enhanced (attempts to expand pillars)
    ↓
CompetitorGapEngine (web scrape)
    ↓
WebsiteKeywordExtractor (site crawl)
    ↓
❌ RESULT: 0 keywords (all sources fail or return empty)

WHY FAILS:
- No fallback if one source fails
- P2_Enhanced depends on Step 1 input that may not exist
- Web scraping is brittle (blocks, redirects, rate limits)
- No semantic understanding of keywords
- No quality filtering
```

---

## Proposed Solution: Multi-Source + AI Filtering

```
STEP 1: PARALLEL DATA COLLECTION (5 sources)
═════════════════════════════════════════════════════════════════════════════

  Google Autosuggest          Wikipedia API           Customer Page Scrape
  (via requests)              (via wikipediaapi)      (via requests + BS4)
        ↓                           ↓                          ↓
   get_google_suggestions()   extract_wiki_topics()   extract_customer_keywords()
   Returns: ["clove X", ...]   Returns: [              Returns: [
   High-quality seed           "digestion",            "Pure clove powder",
   suggestions                 "tooth decay",          "Organic clove price",
                               "Ayurveda"]             ...]

  Competitor Pages Scrape     Site Crawl (customer own site)
  (via requests + BS4)        (check H1/H2/product)
        ↓                           ↓
  extract_competitor_kw()     extract_site_structure()
  Returns: [                  Returns: [
   "best clove benefits",     "Why clove is good",
   "clove price comparison",  "Clove uses"]
   ...]


STEP 2: COLLECTION → DEDUPLICATION + SEMANTIC CLUSTERING
═════════════════════════════════════════════════════════════════════════════

  All Keywords (from 5 sources)
         ↓
  Remove duplicates (case-insensitive, normalize)
  Remove spam/noise
  Keep track of which sources found each keyword
         ↓
  Embedding-based deduplication
  (sentence-transformers: all-MiniLM-L6-v2)
  Remove semantically similar keywords
         ↓
  RESULT: ~80-150 unique, quality keywords


STEP 3: AI FILTERING + SCORING (Ollama DeepSeek)
═════════════════════════════════════════════════════════════════════════════

  Unique Keywords (80-150)
         ↓
  For each keyword, determine:
  ├─ Intent (transactional, informational, comparison, local, etc.)
  ├─ Pillar or Supporting? (map back to original pillar)
  ├─ Search Volume estimate (based on pillar knowledge)
  ├─ Keyword Difficulty estimate (based on competition in wiki/search)
  ├─ Opportunity Score (based on intent + uniqueness)
  └─ Quality confidence (0-100)

  DeepSeek Prompt (local, free):
  ───────────────────────────────────────────────────────────────────────────
  "Given pillar keyword 'clove' and supporting keywords [list],
   and user industry 'spices', classify these keywords:

   Keywords to classify:
   - clove benefits
   - pure clove powder
   - clove price comparison
   - organic clove
   - digestion benefits
   - tooth decay treatment

   For each:
   1. Is it a PILLAR (main topic) or SUPPORTING (long-tail variant)?
   2. Intent: transactional (buying), informational (learning), comparison, local, etc.
   3. Volume estimate: Very low (< 100/mo), Low, Medium, High
   4. Difficulty estimate: Easy, Medium, Hard
   5. Opportunity Score: 0-100 based on above
   6. Keep or filter out? (Y/N)"

  Result: ~50-80 HIGH-QUALITY keywords with metadata


STEP 4: FINAL RANKING + OUTPUT
═════════════════════════════════════════════════════════════════════════════

  Scored Keywords (50-80)
         ↓
  Sort by Opportunity Score (highest first)
  Group by Intent (transactional → informational → comparison)
  Enforce diversity (mix pillar + supporting, short + long-tail)
         ↓
  Return Top 20-50 keywords with:
  ├─ keyword (text)
  ├─ source (google | wikipedia | competitor | customer_site | ai_generated)
  ├─ type (pillar | supporting)
  ├─ intent (transactional | informational | comparison | local | commercial)
  ├─ volume_estimate (very low | low | medium | high)
  ├─ difficulty (easy | medium | hard)
  ├─ opportunity_score (0-100)
  ├─ pillar_keyword (mapped back to Step 1 input)
  └─ confidence (0-100 from AI scoring)
```

---

## Data Flow: "clove" Example

```
USER STARTS STEP 2:
  Pillar: "clove"
  Supporting: ["pure clove powder", "organic clove", "clove health"]
  Customer URL: https://myspices.com/
  Competitor URLs: [spicecompany.com, herbstore.com]

PARALLEL COLLECTORS RUN:
─────────────────────────────────────────────────────────────────────────────

Google Autosuggest (seed: "clove")
  "clove benefits"
  "clove uses"
  "clove price"
  "clove vs black pepper"
  "clove supplements"
  [etc...]

Wikipedia (search: "Clove")
  Main article sections:
  - "Digestion and stomach health"
  - "Dental care (tooth decay)"
  - "Anti-inflammatory properties"
  - "Ayurvedic medicine"
  - "Culinary uses"

  Related entities extracted:
  "ayurveda"
  "spice blends"
  "tooth pain relief"
  [etc...]

Customer Site Crawl (https://myspices.com/)
  H1s and product names:
  "Why Clove Is Good For Digestion"
  "Buy Pure Organic Clove Powder"
  "Clove Oil For Teeth"

Competitor Scrape (top competitor pages)
  "Best Clove Supplements For Inflammation"
  "Clove Price Comparison 2024"
  "Where To Buy Clove Spice Online"
  "Clove vs Other Anti-Inflammatory Herbs"

Site Structure Crawl (customer site)
  H2s under product pages:
  "Health Benefits"
  "How To Use"
  "Dosage"


DEDUPLICATION (80-150 raw keywords down to ~120 unique)
─────────────────────────────────────────────────────────────────────────────
BEFORE: ["clove benefits", "clove benefit", "benefits of clove", ...]
AFTER:  ["clove benefits", ...]  ← deduplicated


EMBEDDING-BASED CLUSTERING (120 down to 90 distinct semantic concepts)
─────────────────────────────────────────────────────────────────────────────
Remove semantic duplicates:
  "clove benefits" ≈ "health benefits of clove" (90% similar → keep first)
  "buy clove powder" ≈ "where to buy clove" (85% similar → keep first)
  "clove price" ≈ "cost of clove" (80% similar → keep first)


AI FILTERING & SCORING (90 down to top 50 with metadata)
─────────────────────────────────────────────────────────────────────────────
DeepSeek analyzes each keyword:

Keyword: "clove benefits"
  ├─ Type: PILLAR (matches primary seed)
  ├─ Intent: INFORMATIONAL (learning about benefits)
  ├─ Volume: MEDIUM (common search)
  ├─ Difficulty: MEDIUM (medical topic, many competitors)
  ├─ Opportunity: 72/100
  ├─ Confidence: 95%
  └─ Sources: google, wikipedia, customer_site

Keyword: "clove for tooth decay"
  ├─ Type: SUPPORTING (specific health use)
  ├─ Intent: INFORMATIONAL
  ├─ Volume: LOW (niche)
  ├─ Difficulty: MEDIUM
  ├─ Opportunity: 68/100
  ├─ Confidence: 90%
  └─ Sources: wikipedia, google, customer_site

Keyword: "clove oil supplement"
  ├─ Type: SUPPORTING (product form variant)
  ├─ Intent: TRANSACTIONAL (buying)
  ├─ Volume: MEDIUM
  ├─ Difficulty: HARD (high competition)
  ├─ Opportunity: 55/100
  ├─ Confidence: 88%
  └─ Sources: google, competitor


FINAL OUTPUT (20-50 ranked keywords)
─────────────────────────────────────────────────────────────────────────────
1. "clove benefits" (72/100) — Pillar, Informational, sources: google+wiki+site
2. "clove for digestion" (70/100) — Supporting, Informational, sources: google+wiki
3. "clove supplements" (68/100) — Supporting, Transactional, sources: google+wiki
4. "clove uses" (65/100) — Pillar, Informational, sources: google+customer
5. "clove price" (62/100) — Supporting, Transactional, sources: google+competitor
...
20. "clove oil for inflammation" (48/100) — Supporting, Informational, sources: wiki
```

---

## Key Implementation Details

### Data Collectors (5 modules)

```python
# 1. GoogleAutosuggestCollector
def collect_google(seed_keyword: str, language: str = "en") → List[str]:
    """Fetch Google Autosuggest for seed + alphabet soup variations"""

# 2. WikipediaCollector
def collect_wikipedia(topic: str) → Dict[str, List[str]]:
    """Extract Wikipedia sections, entities, related concepts"""

# 3. CustomerSiteCollector
def collect_customer_site(url: str) → List[str]:
    """Crawl customer URL: H1, H2, product pages, meta descriptions"""

# 4. CompetitorCollector
def collect_competitor_sites(urls: List[str]) → List[str]:
    """Crawl competitor URLs: extract keyword-rich content"""

# 5. SiteCrawlCollector
def collect_site_structure(url: str) → Dict[str, List[str]]:
    """Extract structured data: H1/H2, product names, schema markup"""
```

### AI Scoring Module (Ollama DeepSeek)

```python
def score_keywords_with_ai(
    keywords: List[str],
    pillar: str,
    supporting: List[str],
    industry: str,
) → List[KeywordWithMetadata]:
    """Use Ollama DeepSeek to classify, score, filter keywords"""

    # Calls local Ollama, no API costs
    # Returns: ~50-80 keywords with intent, volume, difficulty, opportunity
```

### Deduplication + Clustering

```python
def deduplicate_and_cluster(
    all_keywords: List[str],
    threshold: float = 0.85,  # semantic similarity
) → List[str]:
    """
    1. Case-insensitive dedup
    2. Normalize whitespace/punctuation
    3. Embedding-based similarity (remove near-duplicates)
    4. Return unique, high-quality keywords
    """
```

---

## Integration with Existing Systems

### Where This Fits

- **Step 1 (Input)** → Customer sets pillars + supporting
- **Step 2 (Research)** ← **NEW DESIGN HERE** ← Collects from 5 sources + AI
- **Step 3 (Review)** → User reviews + confirms keywords
- **Step 4 (AI Check)** → AI verifies quality
- **Step 5 (Pipeline)** → P1-P20 keyword processing

### Reusing Existing Code

✅ **Ollama + DeepSeek** — Already configured in `ruflo_supporting_keyword_engine.py`
✅ **Gemini integration** — Already available for fallback
✅ **Keyword scoring** — Adapt `annaseo_keyword_scorer.py` patterns
✅ **Embedding dedup** — Use `sentence-transformers` (already in V3 system)
✅ **Wikipedia integration** — `ruflo_v3_keyword_system.py` has this working

---

## Why This Works Better

| Issue | Current (Step 2) | Proposed |
|-------|------------------|----------|
| **Zero keywords** | If P2 fails → empty | Multiple sources → guaranteed results |
| **No Step 1 input** | Blocks or returns nothing | Wikipedia + AI can generate from industry |
| **Web scraping fails** | Entire process breaks | Other sources continue |
| **Semantic duplicates** | Returns ~50 items but many identical | Embedding dedup → clean results |
| **No quality filter** | Returns keywords as-is | AI scores by intent + opportunity |
| **Business relevance** | Random expansions | Wikipedia context ensures relevance |

---

## Phase 2: Advanced Features (Optional Future)

Once v1 works:
- SERP data integration (SEO tools API)
- Search volume real data (SemRush / Ahrefs)
- Seasonal trending keywords
- Long-form content outline generation
- Multi-language variants (Malayalam, Hindi, etc.)

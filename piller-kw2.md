# Pillar & Modifier Keyword: Full System Audit & Upgrade Plan

## 1. Where Pillars Come From — Current State

### 1.1 Old Keywords v1 (legacy `intelligent_crawl_engine.py`)

The old page used a two-phase pillar extraction:

**Phase A — Site Crawl → `_extract_tier1_pillars()`**
- Crawl customer site → filter to `product`, `category`, `homepage`, `about` page types
- Feed product page text into AI with this rule set:
  - Remove geo qualifiers: `"Kerala Cardamom"` → `"cardamom"`
  - Remove size/weight: `"Black Pepper 500g"` → `"black pepper"`
  - Remove quality adjectives: `"Pure Organic Turmeric Powder"` → `"turmeric powder"`
  - **Maximum 2 words per pillar**
  - Do not include: brand names, sizes, "pack", "bundle", "combo"
  - Same product in multiple variants → listed ONCE
- Returns `tier1_pillars` with confidence scores + supporting keywords

**Phase B — SERP+Wikipedia → `PillarExtractor.extract_pillars()`** (`ruflo_v3_keyword_system.py`)
- Takes `universe_term` (e.g. "Indian Spices")
- Scrapes top SERP pages → extracts all `h1/h2/h3` headings + FAQ questions
- Feeds headings + Wikipedia sections to Gemini
- Extracts **traffic-backed** pillar topics (pillars validated by what ranks in Google)
- Fallback: top headings used raw if AI fails

**Phase C — `_extract_core_pillar()`** (module-level util)
```python
# "Kerala Cardamom 8mm Fruit - 100gm" → {"core_pillar": "cardamom", "modifiers": ["kerala","8mm","fruit","100gm"]}
# "Aromatic True Cinnamon (Ceylon) — 100g" → {"core_pillar": "cinnamon", "modifiers": ["aromatic","true","ceylon","100g"]}
```
Uses `_GEO_WORDS`, `_QUALITY_WORDS`, `_NOISE_WORDS`, `_SIZE_PAT` to strip noise then finds the core noun.

**Frontend (Step1Setup.jsx + Step2Discovery.jsx)**
- User manually types pillars, OR
- Crawled products auto-populate pillars
- `TagInput` component — press Enter to add, click × to remove
- Loads existing pillars from `/api/ki/{projectId}/pillars` on mount
- Passed as `step1.pillars` to Step2 and Step3

---

### 1.2 Keywords v2 / kw2 (`engines/kw2/`)

**Phase 1 — `BusinessIntelligenceEngine.analyze()`** (`business_analyzer.py`)

Full pipeline:
```
crawl site → segment_content → extract_entities → get_competitor_insights
→ BUSINESS_ANALYSIS_USER prompt → AI → validate_profile → rule_based_fallback
→ check_consistency → merge_manual → confidence_score → save_business_profile
```

AI prompt asks for:
```json
{
  "universe": "2-3 word business universe name",
  "pillars": ["max 10 — ONLY physical sellable product categories, NOT informational topics"],
  "product_catalog": ["specific products found on site"],
  "modifiers": ["organic, wholesale, bulk, premium, etc."],
  ...
}
```

Rules baked into the prompt:
- `pillars` = physical sellable product categories, NOT informational topics
- `product_catalog` = specific items (not categories)
- `negative_scope` MUST include: recipe, benefits, how to, what is

**Validation** (`_validate_profile`):
- `pillars` must be a list with ≥1 item
- No pillar can contain any word from `NEGATIVE_PATTERNS`
- Will retry AI once if validation fails

**Rule-based fallback** (`_rule_based_fallback`):
```python
all_products = segmented["found_products"] + manual_input.get("products", [])
pillars = all_products[:10] if all_products else ["general"]
modifiers = ["wholesale", "bulk", "organic", "premium", "online"]  # HARDCODED
```

**Manual merge** (`_merge_manual`):
- Adds manual `products` from form to `product_catalog`
- Does NOT currently add manual products to `pillars`
- Overrides `business_type`, `geo_scope`, `audience`

**DB storage** (`kw2_business_profile` table):
```sql
pillars TEXT,          -- JSON array: ["cardamom", "black pepper", ...]
product_catalog TEXT,  -- JSON array: specific variants
modifiers TEXT,        -- JSON array: ["organic", "wholesale", ...]
negative_scope TEXT,   -- JSON array: excluded terms
```

**Frontend (Phase1.jsx)**
- Separate fields: `pillars` (TagInput, blue), `products` (TagInput, green), `modifiers` (TagInput, purple)
- `pillars` state populated from `profile.pillars` after AI analyze
- User can manually add/remove pillars before proceeding
- "Crawl from Website" → fills `products`, NOT `pillars`
- "Suggest All Fields" → suggests `modifiers`, `audience`, `negScope` — NOT pillars directly
- Manual pillars added in Phase1 → sent to `phase1` endpoint as `body.pillars`
- But `_merge_manual()` only merges products, not pillars — **BUG: manual pillars overridden by AI**

---

## 2. Problem: Why kw2 Pillars Are Worse Than v1

### 2.1 The Core Quality Gap

| Dimension | v1 Pillars | kw2 Pillars |
|---|---|---|
| Source | SERP-backed + site crawl | Site crawl only |
| Format | Max 2 words, cleaned | Full product names kept ("Kerala Black Pepper - 200gm") |
| Processing | `_extract_core_pillar()` before use | Raw pillar passed to Google Suggest and AI expand |
| Traffic signal | Yes (validated by SERP headings) | No |
| Fallback | Top SERP headings | Hardcoded `["general"]` |
| Google Suggest input | Cleaned core term | Raw product name (→ 0 results for most) |

### 2.2 The "Raw Product Names as Pillars" Problem

kw2 stores pillars as the user's product names:
```
"Kerala Black Pepper - 200gm"
"Kerala Cardamom 8mm - 200gm - Free Delivery"
"Aromatic True Cinnamon (Ceylon)"
```

These are fine as `product_catalog` entries but are **terrible as search keywords**.

When kw2's `_google_suggest` queried `"Kerala Cardamom 8mm - 200gm - Free Delivery"` → **0 results**.
When it queries `"cardamom"` (core term) → **308 results**.

### 2.3 The Modifier Problem

v1 had a clear separator: product names have **modifiers extracted and stripped**.
kw2 has:
- `modifiers` field = intent modifiers (organic, wholesale, bulk)
- But pillars themselves contain quality/geo modifiers inline ("Aromatic", "Kerala", "Premium")
- These inline modifiers are not used in keyword expansion — wasted signal

### 2.4 Known Bugs

1. **Manual pillars overridden** — `_merge_manual()` in `business_analyzer.py` only merges `product_catalog`, not `pillars`. After AI returns new profile, user additions are lost.
2. **Phase2 useEffect overwrites** — Every time `profile` updates in store, Phase2's `useEffect` resets `confirmedPillars`. Fixed by `pillarsInitialized` ref, but the underlying data isn't persisted until Stream runs.
3. **`addManualPillar` in Phase2** — Saves to profile via PATCH now, but Phase1's manual pillar input (`TagInput` for `pillars`) doesn't persist if user adds items then *doesn't* click "Analyze Business".

---

## 3. How `_extract_core_term` Works Now (After Fix)

```python
def _extract_core_term(self, pillar: str) -> str:
    s = pillar
    s = re.sub(r'\b\d+\s*(gm|g|kg|ml|l|mm|cm|oz)\b', '', s)          # weights
    s = re.sub(r'\b(free\s*delivery|free\s*ship\w*|offer|discount)\b', '', s)  # promo
    s = re.sub(r'\b(kerala|indian|india)\b', '', s)                     # geo
    s = re.sub(r'[-–—&,\(\)]+', ' ', s)                                 # separators
    # NEW: strip quality/descriptor noise
    _NOISE = {"aromatic","premium","true","finest","pure","natural","organic",
              "fresh","best","top","authentic","raw","selected","handpicked",
              "certified","bold","extra","special","quality"}
    words = [w for w in s.split() if w.lower() not in _NOISE and len(w) > 1]
    s = " ".join(words).strip().lower()
    return s if len(s) > 2 else pillar.lower()
```

**Results:**
```
"Aromatic True Cinnamon (Ceylon)"           → "cinnamon ceylon"
"Premium Cassia Cinnamon - 100g"            → "cassia cinnamon"
"Kerala Black Pepper - 200gm"               → "black pepper"
"Kerala Cardamom 8mm - 200gm - Free Delivery" → "cardamom"
"Cardamom (100g)"                           → "cardamom"
"Black Pepper (200g) & Clove (100g)"        → "black pepper clove"
"Kerala Adimali Clove -200gm"               → "adimali clove"
```

---

## 4. Upgrade Plan: Making kw2 Pillars as Good as v1

### 4.1 Separate `product_catalog` from `pillars` Clearly

The system should distinguish between:

| Field | Purpose | Example |
|---|---|---|
| `product_catalog` | Full product names as listed on site | "Kerala Black Pepper - 200gm" |
| `pillars` | Clean 1-3 word SEO keyword categories | "black pepper" |
| `pillar_core_terms` | Stripped, noise-free search seeds | "black pepper" |
| `modifiers` | Intent/quality qualifiers | ["wholesale", "organic", "bulk"] |

### 4.2 Auto-Derive Pillars from Product Catalog

In `_merge_manual()` and after AI analysis:

```python
def _derive_pillars_from_catalog(self, product_catalog: list[str]) -> list[str]:
    """
    Extract clean search-quality pillar keywords from raw product names.
    Uses the same logic as _extract_core_term but groups duplicates.
    """
    seen = set()
    pillars = []
    for product in product_catalog:
        core = self._extract_core_term(product)
        if core and core not in seen and len(core) > 2:
            seen.add(core)
            pillars.append(core)
    return pillars[:10]
```

When user provides products but no explicit pillars:
```python
if not profile.get("pillars") and profile.get("product_catalog"):
    profile["pillars"] = _derive_pillars_from_catalog(profile["product_catalog"])
```

### 4.3 Add SERP-Backed Pillar Validation (v1's Key Feature)

Port `PillarExtractor` logic to kw2:

```python
class PillarValidator:
    """
    Validate and enrich pillars using SERP data.
    Checks if proposed pillar actually has Google search results.
    """
    def validate(self, pillars: list[str]) -> list[dict]:
        validated = []
        for p in pillars:
            suggests = self._get_suggest_count(p)
            validated.append({
                "pillar": p,
                "has_traffic": suggests > 0,
                "suggest_count": suggests,
                "confidence": min(1.0, suggests / 50),
            })
        return sorted(validated, key=lambda x: -x["suggest_count"])

    def _get_suggest_count(self, pillar: str) -> int:
        """Quick signal: how many Google Suggest results exist for this term."""
        from engines.intelligent_crawl_engine import GoogleSuggestEnricher
        enricher = GoogleSuggestEnricher()
        results = enricher._query(pillar)
        return len(results)
```

### 4.4 Modifier System Upgrade

**Current state:**
- v1 modifiers: derived from SERP's top modifier patterns (traffic-backed)
- kw2 modifiers: hardcoded `["wholesale", "bulk", "organic", "premium", "online"]`

**What good modifiers look like:**
- **Intent modifiers**: buy, wholesale, bulk, price, rate, supplier — transactional
- **Quality modifiers**: organic, pure, fresh, authentic, certified — trust signals
- **Geo modifiers**: india, kerala, malabar, online india — location targeting
- **Audience modifiers**: restaurant, hotel, home, commercial — B2B/B2C split

**Proposed modifier categories in profile:**
```json
{
  "modifiers": {
    "intent": ["buy", "wholesale", "bulk", "price", "supplier"],
    "quality": ["organic", "pure", "authentic", "premium"],
    "geo": ["india", "kerala", "online india"],
    "audience": ["restaurant", "home", "commercial"]
  }
}
```

For backward compatibility, keep flat `modifiers` list but populate it from all categories:
```python
modifiers = intent_mods + quality_mods + geo_mods[:2]  # max 10 total
```

### 4.5 Fix `_merge_manual()` to Respect User Pillars

```python
def _merge_manual(self, profile: dict, manual_input: dict):
    # EXISTING: add manual products to catalog
    ...

    # NEW: if user explicitly set pillars, respect them (don't let AI override)
    manual_pillars = manual_input.get("pillars", [])
    if isinstance(manual_pillars, str):
        manual_pillars = [p.strip() for p in manual_pillars.split(",") if p.strip()]
    if manual_pillars:
        # User pillars take precedence — add AI pillars only if user list is thin
        existing = set(p.lower() for p in manual_pillars)
        ai_pillars = profile.get("pillars", [])
        for p in ai_pillars:
            core = self._extract_core_term(p)
            if core and core not in existing:
                existing.add(core)
                manual_pillars.append(core)
        profile["pillars"] = manual_pillars[:12]
    elif not profile.get("pillars"):
        # No user pillars and no AI pillars → derive from product catalog
        profile["pillars"] = self._derive_pillars_from_catalog(
            profile.get("product_catalog", [])
        )
```

### 4.6 Fix Phase1.jsx: Persist Manual Pillars Before "Analyze"

```jsx
// When user types a pillar and presses Enter, save immediately
const handlePillarChange = async (newPillars) => {
  setPillars(newPillars)
  // Optimistic save — don't wait for "Analyze Business"
  try {
    await api.updateProfile(projectId, { pillars: newPillars })
  } catch { /* ignore */ }
}
```

---

## 5. Complete Data Flow: Pillar & Modifier Journey

```
User Input (Phase1.jsx)
├── domain: "https://pureleven.com/"
├── products: ["Aromatic True Cinnamon (Ceylon)", "Kerala Black Pepper - 200gm", ...]
├── pillars: []  ← user rarely fills this manually
└── modifiers: []  ← user rarely fills this manually
         │
         ▼
"Analyze Business" → POST /api/kw2/{proj}/sessions/{sess}/phase1
         │
         ▼
BusinessIntelligenceEngine.analyze()
├── _crawl(domain) → CrawledPage list
├── segment_content(pages) → {products, categories, about, found_products}
├── extract_entities(text) → [entities], [topics]
├── get_competitor_insights(comp_urls) → text
├── BUSINESS_ANALYSIS_USER prompt → AI
│   └── Returns: {universe, pillars, product_catalog, modifiers, audience, ...}
├── _validate_profile(profile) → retry if invalid
├── _rule_based_fallback() if AI fails
├── check_consistency()
├── _merge_manual(profile, manual_input)
│   ├── Adds manual products to product_catalog
│   └── ⚠ Does NOT add manual pillars to profile.pillars ← BUG
├── compute_confidence()
└── save_business_profile(project_id, profile)
         │
         ▼
profile.pillars stored in kw2_business_profile
         │
         ▼
Phase2.jsx loads confirmed_pillars from profile.pillars
         │
         ▼ (Stream button clicked)
KeywordUniverseGenerator.generate_stream()
├── For each pillar → _extract_core_term(pillar) → clean search seed
├── _build_seeds(pillars, modifiers)   ← pillar × modifier matrix
├── _rule_expand(pillars, modifiers, geo)  ← template expansion
├── _google_suggest([pillar]) → GoogleSuggestEnricher(core_term)
│   └── ⚠ Previously used raw pillar → 0 results for product names
│   └── ✅ Now uses _extract_core_term → "cardamom", "black pepper", etc.
├── _ai_expand([pillar], modifiers, universe, provider)
│   └── UNIVERSE_EXPAND_USER prompt → 80 buyer-intent keywords per pillar
└── _negative_filter + _normalize_dedup
         │
         ▼
kw2_universe_items table → Phase 3 validation → Phase 4 scoring → Top 100
```

---

## 6. What to Implement

### Priority 1: Fix Manual Pillar Override Bug
**File:** `engines/kw2/business_analyzer.py`, `_merge_manual()`

Add logic to respect `manual_input["pillars"]` — currently completely ignored.

### Priority 2: Auto-Derive Pillars from Product Catalog
**File:** `engines/kw2/business_analyzer.py`

When AI gives back full product names as pillars ("Kerala Black Pepper - 200gm"),
auto-derive clean SEO pillars ("black pepper") using `_extract_core_term`.

```python
# After AI returns profile, clean the pillars:
profile["pillars"] = [
    _extract_core_term(p) for p in profile.get("pillars", [])
]
# Deduplicate
seen = set()
profile["pillars"] = [p for p in profile["pillars"] if not (p in seen or seen.add(p))]
```

### Priority 3: Show Both Raw Products AND Clean Pillars in Phase1 UI
**File:** `frontend/src/kw2/Phase1.jsx`

Currently the UI only shows `pillars` TagInput. User needs to see:
- **Products** (green) = full product names from site/manual entry
- **Pillar Keywords** (blue) = auto-cleaned SEO terms derived from products

The "Pillar Keywords" field should auto-populate from products when user clicks "Derive Pillars"
(or auto on every product add).

### Priority 4: Structured Modifier Categories
**File:** `engines/kw2/business_analyzer.py` prompt + `Phase1.jsx`

Instead of a flat list, show modifiers grouped:
```
Intent:   [buy] [wholesale] [bulk] [price] [supplier]
Quality:  [organic] [pure] [authentic]  
Geo:      [india] [kerala]
```

### Priority 5: SERP-Validated Pillars
**File:** new `engines/kw2/pillar_validator.py`

After Phase 1 generates pillars, validate each against Google Suggest.
Sort by `suggest_count` descending — pillars with 0 suggests get a ⚠ warning in UI.

---

## 7. File Reference Map

| Component | File | Purpose |
|---|---|---|
| kw2 Phase 1 UI | `frontend/src/kw2/Phase1.jsx` | Pillar/modifier input, AI analyze trigger |
| kw2 Phase 2 UI | `frontend/src/kw2/Phase2.jsx` | Confirmed pillars → generation |
| kw2 API client | `frontend/src/kw2/api.js` | `runPhase1`, `streamPhase2`, `updateProfile` |
| kw2 store | `frontend/src/kw2/store.js` | `profile.pillars`, `profile.modifiers` |
| Business analyzer | `engines/kw2/business_analyzer.py` | AI analysis, pillar extraction |
| AI prompts | `engines/kw2/prompts.py` | `BUSINESS_ANALYSIS_USER`, `UNIVERSE_EXPAND_USER` |
| Keyword generator | `engines/kw2/keyword_generator.py` | `_extract_core_term`, `_google_suggest`, `_ai_expand` |
| DB layer | `engines/kw2/db.py` | `save_business_profile`, `load_business_profile` |
| Constants | `engines/kw2/constants.py` | Templates, defaults, scoring weights |
| v1 crawler | `engines/intelligent_crawl_engine.py` | `_extract_tier1_pillars`, `_extract_core_pillar` |
| v1 SERP pillars | `engines/ruflo_v3_keyword_system.py` | `PillarExtractor.extract_pillars` |
| Phase 1 endpoint | `main.py:20664` | `POST /api/kw2/{proj}/sessions/{sess}/phase1` |
| Profile PATCH | `main.py:20718` | `PATCH /api/kw2/{proj}/profile` |
| Phase 2 stream | `main.py:21723` | `GET /api/kw2/{proj}/sessions/{sess}/phase2/stream` |

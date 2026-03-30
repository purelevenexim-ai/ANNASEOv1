# Step 2 — Research Engine (Revised Design)

## Core Principle
**Respect user intent + respect memory constraints**

Process incrementally. Rank by priority: User Input > Google > AI.

---

## Data Lifecycle

```
STEP 1: KEYWORD INPUT (User provides)
═════════════════════════════════════════════════════════════════════════════
  ✅ Pillar keywords: e.g., ["clove", "cardamom"]
  ✅ Supporting keywords PER PILLAR:
      clove → ["pure clove powder", "organic clove", "clove health"]
      cardamom → ["cardamom powder", "green cardamom price"]
  ✅ Intent/Business context: (ADD TO STEP 1 if missing)
      - "What is the primary business intent?"
        ├─ e-commerce (selling products)
        ├─ health information (education/blogs)
        ├─ B2B suppliers (wholesale)
        ├─ mixed
      - "Target audience?" (health-conscious, budget-aware, professional chefs)
      - "Geographic focus?" (India, global)


STEP 2: RESEARCH ENGINE (3-source ranking)
═════════════════════════════════════════════════════════════════════════════

For each PILLAR keyword:

  SOURCE 1: USER'S OWN SUPPORTING KEYWORDS (Priority = 10)
  ────────────────────────────────────────────────────────────
    From Step 1, the user ALREADY provided supporting keywords
    These get HIGHEST ranking because user explicitly chose them

    Example for pillar "clove":
    User provided supporting:
      ✓ "pure clove powder"       → Score: 10 (user intent)
      ✓ "organic clove"           → Score: 10 (user intent)
      ✓ "clove health"            → Score: 10 (user intent)

    These appear FIRST in research results


  SOURCE 2: GOOGLE AUTOSUGGEST (Priority = 5 + AI boost)
  ────────────────────────────────────────────────────────────
    For each pillar, fetch Google suggestions
    Add these to keyword list with score +5

    Example for pillar "clove":
    Google suggests:
      → "clove benefits"          → Score: 5 + AI scoring
      → "clove uses"              → Score: 5 + AI scoring
      → "clove price"             → Score: 5 + AI scoring
      → "where to buy clove"      → Score: 5 + AI scoring
      → "clove vs black pepper"   → Score: 5 + AI scoring


  SOURCE 3: AI CLASSIFICATION & SCORING (Ollama DeepSeek)
  ────────────────────────────────────────────────────────────
    For ALL keywords from Source 1 + Source 2:

    DeepSeek classifies ONCE for all pillars:
    ┌─────────────────────────────────────────────────────────┐
    │ "User pillar: 'clove'                                   │
    │  User supporting: [pure clove powder, organic clove]    │
    │  Business intent: e-commerce                            │
    │  Industry: spices                                       │
    │                                                          │
    │  Keywords to score:                                     │
    │  - pure clove powder (source: user)                     │
    │  - organic clove (source: user)                         │
    │  - clove health (source: user)                          │
    │  - clove benefits (source: google)                      │
    │  - clove uses (source: google)                          │
    │  - clove price (source: google)                         │
    │                                                          │
    │  For EACH keyword, determine:                           │
    │  1. Is it relevant to 'e-commerce' intent? (Y/N)        │
    │  2. Intent: transactional|informational|comparison      │
    │  3. Volume: very_low|low|medium|high (estimate)         │
    │  4. Difficulty: easy|medium|hard (estimate)             │
    │  5. Opportunity Score: 0-100                            │
    │  6. Keep or discard? (for this intent)                  │
    │                                                          │
    │  Return JSON with all above for Step 3 review"          │
    └─────────────────────────────────────────────────────────┘

    DeepSeek output example:
    ```json
    {
      "pure clove powder": {
        "source": "user",
        "source_score": 10,
        "intent": "transactional",
        "relevant_to_ecommerce": true,
        "volume": "medium",
        "difficulty": "medium",
        "ai_score": 15,  // 10 (user) + 5 (AI boost for e-commerce match)
        "total_score": 25,
        "confidence": 95,
        "reasoning": "User-specified, high commercial intent, strong buyer signal"
      },
      "clove benefits": {
        "source": "google",
        "source_score": 5,
        "intent": "informational",
        "relevant_to_ecommerce": false,
        "volume": "high",
        "difficulty": "hard",
        "ai_score": 3,  // No e-commerce relevance, informational only
        "total_score": 8,
        "confidence": 85,
        "reasoning": "Educational content, not transactional. Low relevance for e-commerce"
      },
      "clove price": {
        "source": "google",
        "source_score": 5,
        "intent": "transactional",
        "relevant_to_ecommerce": true,
        "volume": "medium",
        "difficulty": "hard",
        "ai_score": 8,  // Some e-commerce relevance
        "total_score": 13,
        "confidence": 90,
        "reasoning": "Commercial intent, buyer looking for pricing"
      }
    }
    ```


STEP 3: REVIEW & FILTER BY INTENT (User confirms)
═════════════════════════════════════════════════════════════════════════════
  User sees keywords sorted by:
  1. Score (descending)
  2. Grouped by intent (transactional → commercial → informational)
  3. Color-coded by source (user input = green, google = blue, ai = orange)

  User can:
  ├─ Confirm keywords for next phase
  ├─ Toggle intent filter ("show only transactional keywords")
  ├─ Adjust scores for specific keywords
  └─ Add more keywords manually
```

---

## Implementation Architecture

### Step 2 Processing Flow

```
INPUT (from Step 1)
├─ project_id
├─ session_id (where user input is stored)
├─ pillars: ["clove", "cardamom"]
├─ supporting_keywords: {
│    "clove": ["pure powder", "organic"],
│    "cardamom": ["green cardamom", "pods"]
│  }
├─ business_intent: "e-commerce"  ← ADD THIS TO STEP 1
└─ target_audience: "health-conscious"  ← ADD THIS TO STEP 1


PROCESS (Research Engine)
├─ Load user's supporting keywords from Step 1
│  ├─ For each pillar, retrieve its supporting keywords
│  ├─ Score each with +10 (user intent)
│  └─ Store as source="user"
│
├─ Fetch Google Autosuggest for each pillar
│  ├─ Call P2_PhraseSuggestor.expand_phrase(pillar)
│  ├─ Score each with +5 (google source)
│  └─ Store as source="google"
│
└─ Call AI to score everything at once
   ├─ Combine user + google keywords
   ├─ Send batch to Ollama DeepSeek
   ├─ DeepSeek classifies intent + relevance
   ├─ DeepSeek computes final scores
   └─ Return scored keywords


OUTPUT (to Step 3)
├─ Keywords (sorted by total_score DESC)
├─ Metadata per keyword:
│  ├─ source (user | google | ai_generated)
│  ├─ intent (transactional | informational | comparison | commercial | local)
│  ├─ volume_estimate (very_low | low | medium | high)
│  ├─ difficulty (easy | medium | hard)
│  ├─ total_score (0-100)
│  ├─ confidence (0-100)
│  └─ ai_reasoning (why this score)
└─ Grouped by intent for Step 3 filtering
```

---

## Code Changes Required

### Step 1 Enhancement (Add Intent Collection)

```python
# In KeywordInput form, ADD these fields:

class KeywordInputForm:
    # Existing fields
    pillars: List[str]
    supporting_keywords: Dict[str, List[str]]

    # NEW FIELDS
    business_intent: Enum["ecommerce", "health_blog", "supplier", "mixed"]
    target_audience: str  # "health-conscious", "budget-aware", etc.
    geographic_focus: str  # "India", "Global", etc.
    primary_kw_type: Enum["product", "service", "information", "mixed"]
```

### Step 2 Redesign

```python
class ResearchEngine:
    def research_keywords(
        self,
        project_id: str,
        session_id: str,
        business_intent: str,  # ← NEW
        language: str = "en",
    ) -> List[KeywordWithMetadata]:
        """
        3-source research:
        1. User's supporting keywords (score +10)
        2. Google Autosuggest (score +5)
        3. AI classification + scoring
        """

        # Load Step 1 data
        pillars, supporting = self._load_user_keywords(session_id)

        # Source 1: User keywords (score +10)
        user_keywords = self._extract_user_keywords(supporting)  # score=10

        # Source 2: Google Autosuggest (score +5)
        google_keywords = self._fetch_google_suggestions(pillars)  # score=5

        # Combine
        all_keywords = user_keywords + google_keywords

        # Source 3: AI scoring (batch, single call)
        scored = self._score_with_ai(
            keywords=all_keywords,
            pillars=pillars,
            supporting=supporting,
            business_intent=business_intent,  # context for DeepSeek
        )

        # Sort by score, return
        return sorted(scored, key=lambda x: x.total_score, reverse=True)
```

### AI Scoring Module (Ollama DeepSeek)

```python
class AIScorer:
    def score_keywords_batch(
        self,
        keywords: List[KeywordWithSource],
        pillars: List[str],
        supporting: Dict[str, List[str]],
        business_intent: str,
    ) -> List[KeywordWithMetadata]:
        """
        Single batch call to Ollama DeepSeek.
        For 50 keywords, 1 API call = fast.
        """

        prompt = f"""
Given this context:
- Primary keywords (pillars): {', '.join(pillars)}
- User-provided supporting keywords: {json.dumps(supporting)}
- Business intent: {business_intent}
- Industry: {self.industry}

Classify and score these keywords:

{self._format_keywords_for_prompt(keywords)}

For EACH keyword, return JSON:
{{
  "keyword": str,
  "intent": "transactional|informational|comparison|commercial|local",
  "relevant_to_business_intent": bool,
  "volume": "very_low|low|medium|high",
  "difficulty": "easy|medium|hard",
  "ai_score": int (0-20, boost if relevant to intent),
  "confidence": int (0-100),
  "recommendation": "keep|discard" (for this intent)
}}

Return as JSON array.
        """

        response = ollama.generate(prompt, model="deepseek-r1:7b")
        parsed = json.loads(response)

        # Merge with source scores
        result = []
        for item in parsed:
            kw = next((k for k in keywords if k.keyword == item["keyword"]), None)
            if not kw:
                continue

            total_score = kw.source_score + item["ai_score"]
            result.append(KeywordWithMetadata(
                keyword=item["keyword"],
                source=kw.source,
                source_score=kw.source_score,
                intent=item["intent"],
                volume=item["volume"],
                difficulty=item["difficulty"],
                ai_score=item["ai_score"],
                total_score=total_score,
                confidence=item["confidence"],
                reasoning=item.get("explanation", ""),
            ))

        return result
```

---

## Memory Efficiency

✅ **No memory spike**: Process one pillar at a time (or batch of pillars)
✅ **Respect Step 1**: Don't re-collect what user already provided
✅ **One AI call per batch**: Score all keywords in single DeepSeek call
✅ **Incremental updates**: User can research one pillar, then next

```python
# Example: Research multiple pillars one at a time
for pillar in pillars:
    keywords = research_engine.research_keywords(
        project_id=project_id,
        pillar=pillar,  # single pillar per call
        session_id=session_id,
    )
    results[pillar] = keywords
    # No memory accumulation, fresh per pillar
```

---

## Scoring Logic

```
Total Score = Source Score + AI Score + Intent Bonus

Source Score:
  ├─ User-provided supporting: +10
  ├─ Google Autosuggest: +5
  └─ AI-generated: +0

AI Score (added by DeepSeek):
  ├─ Matches business intent: +8-10
  ├─ Partial relevance: +3-5
  ├─ No relevance: +0-2
  └─ Volume/Difficulty bonus: +0-3

Intent Bonus (Step 3 can reweight):
  ├─ Transactional: +3 (if intent=ecommerce)
  ├─ Informational: +2 (if intent=health_blog)
  ├─ Commercial: +2
  └─ Local: +1

Example Rankings:
─────────────────────────────────────────────────────────
"pure clove powder" (user) → 10 + 10 + 3 = 23/100 ✓ TOP
"organic clove" (user) → 10 + 9 + 2 = 21/100
"clove price" (google) → 5 + 8 + 3 = 16/100
"clove benefits" (google) → 5 + 2 + 0 = 7/100
"clove supplement" (google) → 5 + 6 + 2 = 13/100
```

---

## Success Criteria

✅ **Step 2 never returns 0 keywords** (has user input + google + ai)
✅ **Respects user's supporting keywords** (priority 1)
✅ **Filters by business intent** (Step 3 can filter further)
✅ **No memory overload** (batch processing, one pillar at a time)
✅ **Fast** (one Google call + one Ollama call per pillar)
✅ **Quality** (AI validates relevance to business intent)

---

## Questions for Step 1 Enhancement

When updating Step 1 to collect business intent, ask:

```
1. "What's your primary business goal?"
   - E-commerce (selling products)
   - Content/Blog (educational information)
   - B2B (supplier/wholesale)
   - Mixed

2. "What's your target audience?"
   - Health-conscious customers
   - Budget-aware shoppers
   - Professional chefs
   - [custom input]

3. "Geographic focus?"
   - India
   - Specific region
   - Global

4. "Primary keyword type?"
   - Product keywords (transactional)
   - Information keywords (educational)
   - Mixed
```

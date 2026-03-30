# Research Engine Redesign — Complete Specification

**Date:** 2026-03-30
**Project:** ANNASEOv1 — Keyword Intelligence Step 2
**Status:** Design Approved
**Owner:** Keyword Research Pipeline
**Priority:** HIGH (blocks user workflow)

---

## Executive Summary

Step 2 (Research Engine) currently returns 0 keywords because:
1. P2_Enhanced depends on Step 1 input that may not exist
2. CompetitorGapEngine web scraping is fragile
3. No fallback or quality filtering

**Solution:** Redesign around 3 priority-ranked sources with AI validation.

**Impact:** Step 2 will always return meaningful keywords, respecting user intent and business goals.

---

## Problem Statement

### Current Issues

| Issue | Impact | Severity |
|-------|--------|----------|
| Step 2 returns 0 keywords on failure | User can't proceed | CRITICAL |
| No fallback when P2_Enhanced fails | Entire research blocks | CRITICAL |
| Web scraping brittleness | CompetitorGapEngine unreliable | HIGH |
| No intent filtering | Returns irrelevant keywords | MEDIUM |
| No business context | Can't filter by e-commerce vs blog | MEDIUM |
| Memory load unclear | Step 1 might be too heavy | MEDIUM |

### Root Causes

1. **Single points of failure** — If P2_Enhanced returns [], entire process fails
2. **No quality gates** — Returns keywords without validating relevance
3. **Missing context** — Doesn't know if user is selling products or writing blogs
4. **Architectural disconnect** — V3 system has sophistication but Step 2 doesn't use it

---

## Design Overview

### Core Principle
**3-tier priority: User Intent (High) > Google Autosuggest (Medium) > AI Classification (Score)**

### Data Flow

```
Step 1 Input (NEW: add business intent)
    ↓
Step 2 Research (redesigned)
    ├─ Load user's supporting keywords (+10 score)
    ├─ Fetch Google Autosuggest (+5 score)
    ├─ Call AI once to classify all (+0-10 score)
    └─ Sort by total score, return
    ↓
Step 3 Review (user confirms by intent)
    ├─ Filter by transactional/informational/comparison
    ├─ Adjust scores
    └─ Confirm for pipeline
```

---

## Architecture

### Components

#### 1. Step 1 Enhancement: Business Intent Collection

**Purpose:** Capture user's business goal so research engine can filter appropriately.

**New fields to add:**

```python
class KeywordInputRequest:
    # Existing
    pillars: List[str]
    supporting_keywords: Dict[str, List[str]]
    customer_url: str

    # NEW
    business_intent: Enum["ecommerce", "content_blog", "supplier", "mixed"]
    target_audience: str  # "health-conscious", "budget-aware", etc.
    geographic_focus: str  # "India", "Global"
    primary_keyword_type: Enum["product", "information", "mixed"]
```

**UI Changes:** Add 4 radio/select questions before Step 2 research button.

---

#### 2. Research Engine: 3-Source Architecture

**Purpose:** Gather keywords from multiple sources with priority ranking.

**Source 1: User-Provided Supporting Keywords**
- Priority: 10/10 (highest)
- Process: Load from Step 1 session storage
- Score: +10 to base score
- Quality: 100% (user explicitly chose them)

**Source 2: Google Autosuggest**
- Priority: 5/10 (medium)
- Process: Call P2_PhraseSuggestor.expand_phrase() for each pillar
- Score: +5 to base score
- Fallback: If fails, continue with Source 1 only
- Quality: ~70% (Google suggestions can have noise)

**Source 3: AI Classification & Scoring**
- Priority: Variable (enhances other sources)
- Process: Single batch call to Ollama DeepSeek
- Determines:
  - Intent (transactional / informational / comparison / commercial / local)
  - Volume estimate (very_low / low / medium / high)
  - Difficulty estimate (easy / medium / hard)
  - Relevance to business intent (boolean)
  - Final score bonus (0-10)
- Quality: ~85-90% (LLM classification with business context)

---

#### 3. AI Scoring Module: Batch Processing

**Purpose:** Classify and score all keywords in single API call (memory efficient).

**Algorithm:**

```
Input: keywords[] from sources 1 & 2
       + pillars, supporting_keywords, business_intent

For each keyword:
  score = source_score (10 or 5)

Call DeepSeek once with all keywords:
  For each keyword, classify:
    - intent type
    - volume estimate
    - difficulty estimate
    - relevance to business_intent (0-1)
    - ai_score (+3-10 based on above)

Final score = source_score + ai_score
```

**DeepSeek Prompt Template:**

```
You are a keyword intelligence expert. Classify and score these keywords for an e-commerce business selling spices.

Context:
- Primary keywords (pillars): clove, cardamom
- User-provided variants: pure clove powder, organic clove, green cardamom
- Business intent: e-commerce (selling products)
- Target audience: health-conscious customers

Keywords to score:
1. pure clove powder (source: user)
2. organic clove (source: user)
3. clove benefits (source: google)
4. where to buy clove (source: google)
5. clove price (source: google)

For EACH keyword, respond with JSON:
{
  "keyword": "...",
  "intent": "transactional|informational|comparison|commercial|local",
  "relevant_to_ecommerce": true/false,
  "volume_estimate": "very_low|low|medium|high",
  "difficulty": "easy|medium|hard",
  "ai_score": <0-10>,
  "confidence": <0-100>,
  "reason": "..."
}

Return as JSON array only, no other text.
```

---

#### 4. Output: Ranked Keywords

**Format:**

```python
@dataclass
class KeywordWithMetadata:
    keyword: str
    source: str  # "user" | "google" | "ai_generated"
    intent: str  # "transactional" | "informational" | ...
    volume: str  # "very_low" | "low" | "medium" | "high"
    difficulty: str  # "easy" | "medium" | "hard"
    source_score: int  # 10 (user) or 5 (google)
    ai_score: int  # 0-10
    total_score: int  # source_score + ai_score (0-20, normalized to 0-100)
    confidence: int  # 0-100 (AI confidence)
    pillar_keyword: str  # which pillar this came from
    reasoning: str  # AI's explanation
```

**Sort order:** Total score DESC, then by intent (transactional first).

---

## Implementation Scope

### Phase 1: Core Research Engine (Current)

**Deliverables:**

1. **Update Step 1 form** to collect business_intent + target_audience
2. **Redesign /api/ki/{project_id}/research endpoint** to use new 3-source model
3. **Create ResearchEngine class** with:
   - `research_keywords()` — main entry point
   - `_load_user_keywords()` — load from Step 1
   - `_fetch_google_suggestions()` — call Google Autosuggest
   - `_score_with_ai()` — batch AI scoring
4. **Create AIScorer class** with:
   - `score_keywords_batch()` — single Ollama call
   - Proper prompt engineering
5. **Update Step 3** to show source colors + intent filtering

**Files to create/modify:**

```
CREATE:
  engines/research_engine.py
  engines/research_ai_scorer.py
  docs/superpowers/specs/2026-03-30-research-engine-redesign.md

MODIFY:
  main.py (Step 1 form + Step 2 endpoint)
  frontend/src/KeywordWorkflow.jsx (Step 1 intent questions + Step 3 filtering)
  annaseo_wiring.py (add schema tables if needed)
```

**Acceptance Criteria:**

- ✅ Step 2 returns 20-50 keywords minimum (never 0)
- ✅ Keywords ranked by score (user input first)
- ✅ Intent classification accurate (matches business_intent)
- ✅ No memory spikes (process one pillar at a time)
- ✅ Speed < 5 seconds per pillar (Google + Ollama)

---

### Phase 2: Advanced Features (Future)

- Wikipedia topic extraction (semantic enrichment)
- Competitor gap analysis (better web scraping)
- Search volume real data (SemRush/Ahrefs API)
- Language variants (Malayalam, Hindi, etc.)
- Seasonal trends

---

## Data Storage

### Tables Needed

**keyword_research_sessions** (if not exists)

```sql
CREATE TABLE keyword_research_sessions (
  session_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  business_intent TEXT,  -- "ecommerce" | "content_blog" | "supplier" | "mixed"
  target_audience TEXT,  -- "health-conscious", "budget-aware"
  geographic_focus TEXT, -- "India", "Global"
  pillars TEXT,  -- JSON array
  supporting_keywords TEXT,  -- JSON dict
  research_status TEXT DEFAULT 'pending',  -- "pending" | "running" | "completed" | "failed"
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE research_results (
  result_id TEXT PRIMARY KEY,
  session_id TEXT,
  keyword TEXT,
  source TEXT,  -- "user" | "google" | "ai"
  intent TEXT,
  volume TEXT,
  difficulty TEXT,
  score FLOAT,
  confidence FLOAT,
  pillar_keyword TEXT,
  created_at TEXT,
  FOREIGN KEY(session_id) REFERENCES keyword_research_sessions(session_id)
);
```

---

## API Changes

### Step 1: Update POST /api/ki/{project_id}/input

**New request body:**

```json
{
  "session_id": "...",
  "pillars": ["clove", "cardamom"],
  "supporting_keywords": {
    "clove": ["pure clove powder", "organic"],
    "cardamom": ["green cardamom", "pods"]
  },
  "customer_url": "https://myspices.com/",
  "competitor_urls": ["..."],

  "business_intent": "ecommerce",        // NEW
  "target_audience": "health-conscious", // NEW
  "geographic_focus": "India",           // NEW
  "primary_keyword_type": "product"      // NEW
}
```

---

### Step 2: Redesign POST /api/ki/{project_id}/research

**Request:**

```json
{
  "session_id": "kis_f6b2641978...",
  "business_intent": "ecommerce"
}
```

**Response:**

```json
{
  "job_id": "job_xxx",
  "status": "completed",
  "keywords": [
    {
      "keyword": "pure clove powder",
      "source": "user",
      "intent": "transactional",
      "volume": "medium",
      "difficulty": "medium",
      "total_score": 20,
      "confidence": 95,
      "pillar_keyword": "clove"
    },
    {
      "keyword": "organic clove",
      "source": "user",
      "intent": "transactional",
      "volume": "low",
      "difficulty": "hard",
      "total_score": 18,
      "confidence": 92,
      "pillar_keyword": "clove"
    },
    {
      "keyword": "clove benefits",
      "source": "google",
      "intent": "informational",
      "volume": "high",
      "difficulty": "hard",
      "total_score": 7,
      "confidence": 85,
      "pillar_keyword": "clove"
    }
  ],
  "summary": {
    "total_keywords": 45,
    "by_source": { "user": 6, "google": 28, "ai_generated": 11 },
    "by_intent": { "transactional": 18, "informational": 22, "comparison": 5 },
    "estimated_volume_total": 450000
  }
}
```

---

## Testing Strategy

### Unit Tests

```python
def test_load_user_keywords():
    # Load from Step 1 storage, verify +10 score

def test_fetch_google_suggestions():
    # Mock Google API, verify +5 score

def test_ai_scoring_batch():
    # Mock Ollama, verify scoring logic

def test_score_never_zero():
    # Ensure keywords are returned even if sources fail
```

### Integration Tests

```python
def test_research_flow_ecommerce():
    # Full flow with e-commerce intent
    # Verify transactional keywords ranked first

def test_research_flow_blog():
    # Full flow with content_blog intent
    # Verify informational keywords ranked higher

def test_research_with_no_user_input():
    # If Step 1 empty, verify Google + AI still returns keywords
```

### User Acceptance Tests

```
Scenario 1: E-commerce spice seller
- Input: pillars="clove", supporting=["pure powder"]
- Intent: "ecommerce"
- Expected: Top keywords are transactional ("buy", "price", product variants)

Scenario 2: Health blog
- Input: pillars="clove", supporting=["health benefits"]
- Intent: "content_blog"
- Expected: Top keywords are informational ("benefits", "uses", "how to")

Scenario 3: Network failure
- If Google API fails, system should still return user keywords + AI scoring

Scenario 4: No Step 1 input
- If user skips Step 1, Step 2 should use Ollama to generate from industry alone
```

---

## Rollout Plan

### Phase A: Backend Implementation
1. Create `ResearchEngine` and `AIScorer` classes
2. Update /api/ki/research endpoint
3. Add database tables
4. Write unit + integration tests

### Phase B: Frontend Update
1. Add Step 1 intent questions
2. Update Step 3 to show source colors + intent filtering
3. Test end-to-end in UI

### Phase C: Validation
1. Test with 5 sample projects
2. Verify speed < 5s per pillar
3. Manual review of keyword quality
4. Get user feedback on intent filtering

### Phase D: Deployment
1. Merge to main branch
2. Deploy to Linode machine
3. Monitor error logs
4. Gather user feedback

---

## Success Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|-----------------|
| Step 2 returns 0 keywords | ~70% failure | 0% | Count empty results |
| Keywords per pillar | 0 | 20-50 | Log result counts |
| Top 5 keywords relevance | N/A | >90% correct intent | Manual review |
| Speed per pillar | N/A | <5 seconds | Time API calls |
| User intent accuracy | N/A | >85% | Compare to user selections |
| Memory usage | Unknown | <100MB per session | Profile with memory tools |

---

## Dependencies

### External APIs
- Google Autosuggest (free, via `requests`)
- Ollama local (DeepSeek model, must be running)

### Libraries
- `requests` (Google, web scraping)
- `beautifulsoup4` (HTML parsing, if needed)
- `sentence-transformers` (embedding dedup, future)
- Existing: SQLAlchemy, FastAPI, sqlite3

### Code Dependencies
- `engines/annaseo_p2_enhanced.py` (P2_PhraseSuggestor)
- `services/db_session.py` (database access)
- `job_tracker.py` (async job management)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Ollama down | Medium | HIGH | Fallback to just user + Google; user can continue manually |
| Google rate limit | Low | MEDIUM | Implement backoff; cache results |
| Memory spike | Medium | MEDIUM | Process one pillar at a time; don't collect all at once |
| AI scoring wrong intent | Medium | MEDIUM | Manual review in Step 3; user can override |
| Web scraping fails (future) | High | LOW | Phase 2 feature; not required for Phase 1 |

---

## Questions & Decisions

### Q1: Should we block Step 2 if Step 1 intent is missing?
**A:** No. If intent not provided, default to "mixed" and let AI decide. User can refine in Step 3.

### Q2: What happens if both Google and user keywords exist?
**A:** Merge them. User keywords get +10, Google gets +5. AI scores all together.

### Q3: Should Step 3 allow manual keyword addition?
**A:** Yes, in future. Phase 1 focuses on research only.

### Q4: Can user re-run Step 2 with different intent?
**A:** Yes. Each research job stores the intent used. User can re-run with new intent.

---

## Specification Sign-Off

- **Architecture:** Approved ✓
- **Scope:** Approved ✓
- **API changes:** Approved ✓
- **Testing plan:** Approved ✓
- **Timeline:** To be determined ✓

---

## Appendix A: Example DeepSeek Response

```json
[
  {
    "keyword": "pure clove powder",
    "intent": "transactional",
    "relevant_to_ecommerce": true,
    "volume_estimate": "medium",
    "difficulty": "medium",
    "ai_score": 10,
    "confidence": 95,
    "reason": "User-specified variant, high commercial intent, matches e-commerce goal perfectly"
  },
  {
    "keyword": "clove benefits",
    "intent": "informational",
    "relevant_to_ecommerce": false,
    "volume_estimate": "high",
    "difficulty": "hard",
    "ai_score": 2,
    "confidence": 90,
    "reason": "Educational content, not product-focused. Low relevance for e-commerce goal"
  },
  {
    "keyword": "organic clove supplement",
    "intent": "transactional",
    "relevant_to_ecommerce": true,
    "volume_estimate": "low",
    "difficulty": "hard",
    "ai_score": 6,
    "confidence": 88,
    "reason": "Commercial intent, matches business goal. Lower volume and high competition"
  }
]
```

---

**Document Status:** Complete & Ready for Implementation Planning


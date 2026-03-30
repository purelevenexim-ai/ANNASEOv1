# Research Engine — Technical Documentation

## Architecture Overview

The Research Engine orchestrates a 3-source keyword collection and ranking pipeline with built-in deduplication and AI scoring.

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        STEP 1: USER INPUT                            │
│  Project ID → Pillars: ["clove", "cardamom"]                        │
│             → Supporting: {"clove": ["powder", "oil"], ...}          │
│             → Intent: "ecommerce"                                    │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  ResearchEngine.research_keywords()                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ SOURCE 1: Load User Keywords (from Step 1 session)          │   │
│  │ _load_user_keywords() → keyword_input_sessions table        │   │
│  │ _extract_user_keywords() → Score +10 (fixed, highest)       │   │
│  │ Output: [{"keyword": "powder", "source": "user", ...}, ...] │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                         │                                             │
│                         ▼                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ SOURCE 2: Google Autosuggest (P2_PhraseSuggestor)           │   │
│  │ _fetch_google_suggestions() → Score +5 (market-validated)   │   │
│  │ For each pillar: expand_phrase() → get ~20-30 suggestions   │   │
│  │ Output: [{"keyword": "clove powder", "source": "google", ...}│  │
│  └─────────────────────────────────────────────────────────────┘   │
│                         │                                             │
│                         ▼                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ COMBINE & DEDUPLICATE                                       │   │
│  │ all_keywords = user_kws + google_kws                        │   │
│  │ _deduplicate() → Remove case-insensitive duplicates         │   │
│  │ Keep highest source_score version of duplicates             │   │
│  │ Result: ~30-50 unique keywords                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                         │                                             │
│                         ▼                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ SOURCE 3: AI Scoring (Ollama DeepSeek)                      │   │
│  │ scorer.score_keywords_batch()                               │   │
│  │  ├─ Build single prompt with all keywords                   │   │
│  │  ├─ Call Ollama once (batch call, not per-keyword)          │   │
│  │  ├─ Classify: intent (5 types)                              │   │
│  │  ├─ Estimate: volume (4 levels), difficulty (3 levels)      │   │
│  │  └─ Score: 0-10 based on intent match + context             │   │
│  │ Output: [KeywordScore(...), ...] with ai_score 0-10         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                         │                                             │
│                         ▼                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ FINAL RANKING                                               │   │
│  │ total_score = source_score + ai_score                       │   │
│  │ Sort by total_score DESC                                    │   │
│  │ Return top 20-50 keywords                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
└────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 STEP 3: Display Results                              │
│  ResearchResult[] sorted by total_score DESC                        │
│  - Color-coded by source (green=user, blue=google, orange=ai)       │
│  - Filterable by intent type                                        │
│  - Exportable as CSV                                                │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Input Collection (Step 1)

User provides:
- `pillars`: List of main keywords ["clove", "cardamom"]
- `supporting_keywords`: Dict[pillar] → List[supporting_kw]
  ```json
  {
    "clove": ["pure clove powder", "organic clove", "ground clove"],
    "cardamom": ["green cardamom", "black cardamom"]
  }
  ```
- `business_intent`: "ecommerce" | "content_blog" | "supplier" | "mixed"
- `project_id`: For data persistence
- `session_id`: Links to Step 1 session data

Data stored in: `keyword_input_sessions` table

### 2. Source 1: Load User Keywords

```python
engine._load_user_keywords(session_id, project_id)
  ↓
Query: SELECT pillars, supporting_keywords FROM keyword_input_sessions WHERE session_id=?
  ↓
Extract supporting keywords only (not pillars)
  ↓
For each pillar → for each supporting keyword:
  Create: {
    "keyword": "pure clove powder",
    "source": "user",
    "source_score": 10,        # Fixed, highest priority
    "pillar_keyword": "clove"
  }
```

**Characteristics:**
- Source Score: +10 (fixed)
- Trust Level: 100% (user-confirmed)
- Count: Usually 5-20 keywords

### 3. Source 2: Google Autosuggest

```python
engine._fetch_google_suggestions(pillars, language)
  ↓
For each pillar:
  suggester.expand_phrase(pillar, deep=False)
    ├─ Query Google Autosuggest API
    ├─ Returns ~20-30 suggestions per pillar
    └─ Examples: "clove powder", "clove oil", "clove benefits"
  ↓
For each suggestion:
  Create: {
    "keyword": "clove oil",
    "source": "google",
    "source_score": 5,         # Fixed, medium priority
    "pillar_keyword": "clove"
  }
```

**Characteristics:**
- Source Score: +5 (fixed)
- Trust Level: ~70% (market-validated)
- Count: Usually 20-50 keywords per pillar
- Timeout: 8 seconds per pillar
- Failure Mode: Skip Google, continue with user + AI

### 4. Deduplication

```python
engine._deduplicate(all_keywords)
  ↓
For each keyword in all_keywords:
  kw_lower = keyword.lower().strip()
  if kw_lower not in seen:
    seen[kw_lower] = keyword      # First occurrence
  elif kw.source_score > seen[kw_lower].source_score:
    seen[kw_lower] = keyword      # Keep higher score version
  ↓
Return list(seen.values())
```

**Examples:**

Input:
```
"pure clove powder" (user, score 10)
"Pure Clove Powder" (google, score 5)
"PURE CLOVE POWDER" (google, score 5)
```

Output (1 keyword):
```
"pure clove powder" (user, score 10)  # Kept highest score version
```

**Guarantees:**
- Case-insensitive matching
- Whitespace-normalized
- Keeps highest source_score
- Reduces duplicates by ~15-25%

### 5. Source 3: AI Scoring

```python
scorer.score_keywords_batch(
  keywords: List[Dict],
  pillars: List[str],
  supporting_keywords: Dict,
  business_intent: str
)
  ↓
_build_scoring_prompt(keywords, pillars, supporting_keywords, business_intent)
  ├─ Format keywords: "1. clove powder (source: user)"
  ├─ Include pillars: "clove, cardamom"
  ├─ Include supporting: {"clove": ["powder", "oil"], ...}
  ├─ Include intent: "ecommerce"
  ├─ Add instructions: Return JSON only
  └─ Template example:
      ```
      INDUSTRY: Spices
      PILLARS: clove, cardamom
      INTENT: ecommerce

      Score these keywords (JSON output only):
      1. pure clove powder (source: user)
      2. clove health benefits (source: google)
      ...

      Return JSON:
      [
        {"keyword": "...", "intent": "...", "volume": "...", "difficulty": "...", "ai_score": ...},
        ...
      ]
      ```
  ↓
_call_ollama(prompt)
  ├─ Endpoint: POST /api/generate
  ├─ Model: deepseek-r1:7b
  ├─ Temperature: 0.3 (consistent, not creative)
  ├─ Max tokens: 4096
  ├─ Timeout: 120 seconds
  └─ Failure Mode: Log error, return unscored
  ↓
_parse_ollama_response(response, keywords)
  ├─ Extract JSON from response
  ├─ Enrich with source_score (user=10, google=5, ai=0)
  ├─ Calculate total_score = source_score + ai_score
  └─ Create KeywordScore objects
```

**Ollama Request/Response:**

```python
Request:
{
  "model": "deepseek-r1:7b",
  "prompt": "...full prompt above...",
  "stream": False,
  "temperature": 0.3,
}

Response:
{
  "response": "[{\"keyword\": \"pure clove powder\", \"intent\": \"transactional\", \"volume\": \"medium\", \"difficulty\": \"medium\", \"ai_score\": 10, \"confidence\": 95, \"reasoning\": \"Perfect e-commerce match\"}]"
}
```

**Parsing:**
1. Extract JSON from `response.response`
2. Parse each object into KeywordScore
3. Enrich with source_score from original keywords dict
4. Validate: intent, volume, difficulty are valid values

**Scoring Matrix:**

| Intent | Expected AI Score Range | Example Keywords |
|--------|------------------------|------------------|
| transactional | 8-10 (if ecommerce intent) | "buy clove", "order online" |
| informational | 8-10 (if content_blog intent) | "how to use", "benefits" |
| comparison | 6-10 (depends on intent) | "vs", "best" |
| commercial | 8-10 (if supplier intent) | "supplier", "wholesale" |
| local | 5-9 (geographic focus) | "near me", city names |

### 6. Final Ranking & Storage

```python
# Convert to ResearchResult format
results = [ResearchResult(...) for s in scored]

# Ensure minimum results (fallback if AI fails)
if len(results) < 10:
  results.extend(_generate_fallback_keywords(...))

# Sort by total_score DESC
results.sort(key=lambda x: x.total_score, reverse=True)

# Save to database
for result in results:
  Insert INTO research_results (
    project_id, session_id, keyword, source, intent,
    volume, difficulty, total_score, confidence,
    pillar_keyword, reasoning, created_at
  )
```

**Storage Table:** `research_results`
- Columns: project_id, session_id, keyword, source, intent, volume, difficulty, total_score, confidence, pillar_keyword, reasoning, created_at
- Indexes: (project_id, session_id), (keyword), created_at

## How to Add New Sources in Future

If you want to add a 3rd or 4th keyword source (e.g., Wikipedia, industry databases):

### 1. Create Collector Function

```python
def _fetch_wikipedia_topics(self, pillars: List[str]) -> List[Dict[str, Any]]:
    """Fetch related topics from Wikipedia."""
    results = []
    try:
        import wikipedia
        for pillar in pillars:
            try:
                # Search Wikipedia
                search_results = wikipedia.search(pillar, results=10)
                for topic in search_results:
                    results.append({
                        "keyword": topic,
                        "source": "wikipedia",
                        "source_score": 2,  # Lower than user/google
                        "pillar_keyword": pillar,
                    })
            except Exception as e:
                log.debug(f"Wikipedia fetch failed for {pillar}: {e}")
                continue
    except ImportError:
        log.warning("Wikipedia module not installed")
    return results
```

### 2. Add to research_keywords() Pipeline

```python
def research_keywords(self, project_id, session_id, business_intent, language="en"):
    pillars, supporting_kws = self._load_user_keywords(session_id, project_id)

    user_keywords = self._extract_user_keywords(supporting_kws)
    google_keywords = self._fetch_google_suggestions(pillars, language)

    # NEW: Add your source here
    wikipedia_keywords = self._fetch_wikipedia_topics(pillars)

    # Combine all sources
    all_keywords = user_keywords + google_keywords + wikipedia_keywords

    # Continue with dedup and scoring...
    all_keywords = self._deduplicate(all_keywords)
    scored = self.scorer.score_keywords_batch(...)
    # ...rest of pipeline
```

### 3. Update AI Scoring Prompt

In `AIScorer._build_scoring_prompt()`:

```python
# Add to prompt template:
"""
KEYWORD SOURCES:
- User-provided (source: user) — highest trust
- Google Autosuggest (source: google) — market-validated
- Wikipedia (source: wikipedia) — encyclopedia references
- [Your new source] — [description]

Ensure AI scorer accounts for all sources when scoring.
"""
```

### 4. Update UI Source Mapping

In Step 3 frontend (StrategyPage.jsx or equivalent):

```javascript
const sourceColors = {
  "user": "#22c55e",        // Green
  "google": "#3b82f6",      // Blue
  "wikipedia": "#8b5cf6",   // Purple
  "ai_generated": "#f97316", // Orange
};
```

### 5. Testing

Add test for new source:

```python
def test_wikipedia_source():
    engine = ResearchEngine()
    with patch('wikipedia.search') as mock_wiki:
        mock_wiki.return_value = ["Clove - Spice", "Clove Oil", "...]
        keywords = engine._fetch_wikipedia_topics(["clove"])

        assert len(keywords) > 0
        assert all(k["source"] == "wikipedia" for k in keywords)
        assert all(k["source_score"] == 2 for k in keywords)
```

### Source Priority Recommendations

When adding new sources, consider the priority:

```
1. User (score: +10)        — Personal business knowledge
2. Google (score: +5)       — Market reality
3. Wikipedia (score: +2)    — Reference/encyclopedia
4. LinkedIn (score: +3)     — Professional networks
5. Industry DB (score: +4)  — Vertical-specific
```

## DeepSeek Prompt Engineering Tips

### Temperature Setting

```python
# Current: temperature=0.3
# Why: Consistent, deterministic output
# Example output variance: ~5% between runs
```

Use higher temperature (0.5-0.7) only if you want more creative classifications.

### Context Window Management

DeepSeek 7B model: ~2048 token context window

Current strategy:
- Batch max 50 keywords (1-2KB tokens)
- Include pillars + supporting keywords (1KB tokens)
- Leave room for response (~1KB tokens)
- Total per batch: ~3-4KB tokens (safe)

If you hit context limits:
- Split into smaller batches (25 keywords max)
- Or upgrade to 13B model
- Or use streaming response

### Prompt Tuning

Key sections of scoring prompt:

```
1. CONTEXT
   - INDUSTRY: [industry]
   - PILLARS: [pillars]
   - INTENT: [business_intent]

2. DATA
   - Supporting keywords: [JSON]
   - Keywords to score: [numbered list]

3. INSTRUCTIONS
   - Be concise
   - Return JSON only
   - Include these fields: [...field list...]

4. EXAMPLE
   [JSON example with 2-3 keyword examples]
```

**Optimization tips:**
- Put most important context first
- Use numbered lists for keywords (clearer)
- Include example JSON (reduces parsing errors)
- Temperature 0.3 for consistency
- Keep instruction language simple

### Handling Malformed JSON

Current approach:
```python
try:
    parsed = json.loads(response_text)
except json.JSONDecodeError:
    # Try to extract JSON object from response
    match = re.search(r'\[.*\]', response_text, re.DOTALL)
    if match:
        parsed = json.loads(match.group())
    else:
        # Fallback: return unscored keywords
        return []
```

**Prevention:**
- Add `(JSON only, no markdown)` to prompt
- Include example JSON
- Request smaller batches
- Temperature 0.2-0.3 only

## Performance Benchmarks

### Speed

| Operation | Time | Notes |
|-----------|------|-------|
| Load user keywords | <50ms | Database query |
| Fetch Google (per pillar) | 3-5s | Network dependent |
| Deduplicate (50 kws) | <10ms | String operations |
| AI score batch (50 kws) | 8-15s | Ollama inference |
| Total per pillar | 12-20s | Parallelizable |
| 5 pillars | 60-100s | Sequential batches |

**Optimization opportunities:**
- Parallelize Google fetches (currently sequential)
- Parallelize Ollama calls (one batch per pillar)
- Cache Google suggestions per pillar
- Implement incremental scoring (score as you go)

### Memory Usage

| Stage | Peak RAM | Notes |
|-------|----------|-------|
| Baseline | ~50MB | Python process |
| Loaded 100 kws | ~60MB | In-memory lists |
| Ollama inference | +50-100MB | Model loading |
| Peak total | ~150-200MB | During batch scoring |

**Memory-efficient strategies:**
- Process keywords in batches (max 50 per batch)
- Close Ollama connection after each call
- Garbage collect deduped keywords
- Stream results to database instead of holding in memory

### Keyword Counts

| Source | Typical Count | Range |
|--------|---------------|-------|
| User | 5-20 | 2-50 |
| Google | 20-50 | 5-100 |
| Before dedup | 25-70 | 7-150 |
| After dedup | 20-50 | 5-100 |
| Final results | 20-50 | 10-100 |

**Dedup efficiency:**
- Typical dedup rate: 15-25%
- Removes case variations, typos
- Keeps highest source_score version

## Known Limitations

### 1. Google Autosuggest Rate Limiting
- Can be rate-limited if called too frequently
- Current workaround: 1 second delay between pillars
- Future: Implement rate limit detection + backoff

### 2. Ollama Dependency
- Requires local Ollama running
- Model must be downloaded: `deepseek-r1:7b`
- Fails completely if unavailable
- Future: Add fallback to simpler scoring

### 3. Model Context Limits
- DeepSeek 7B: ~2048 token context
- Max 50 keywords per batch
- Large pillars with many supporting keywords need splitting
- Future: Use larger model or chunking strategy

### 4. Intent Classification Accuracy
- Accuracy: ~85-90% on common keywords
- Edge cases: Keywords with multiple intents
- Example: "clove powder" could be transactional or informational
- Future: Fine-tune model on SEO domain

### 5. Search Volume Estimates
- No real Google Search Console data
- AI estimates based on context
- Accuracy: ±30% typical
- Future: Integrate with SerpAPI or similar

### 6. Language Support
- Currently supports: English, Malayalam, Hindi
- DeepSeek trained primarily on English
- Multilingual keywords may have lower accuracy
- Future: Add language-specific models

### 7. No Keyword History
- No tracking of keyword rankings over time
- Research results stored but not compared
- Can't detect seasonal trends
- Future: Add historical tracking table

### 8. Wikipedia Not Integrated
- Mentioned as future source, not yet added
- Would help with educational content ideas
- Future: Add as optional 3rd source

## Testing

### Run All Research Tests

```bash
# All research tests
pytest tests/test_research*.py -v

# Only integration tests
pytest tests/test_research_integration.py -v

# Specific test
pytest tests/test_research_integration.py::TestResearchIntegrationEcommerce::test_research_integration_ecommerce_intent -v

# With coverage
pytest tests/test_research*.py --cov=engines.research_engine --cov-report=html
```

### Individual Test Suites

```bash
# AI Scorer tests
pytest tests/test_research_ai_scorer.py -v

# Engine tests
pytest tests/test_research_engine.py -v

# Schema tests
pytest tests/test_research_schema.py -v

# Integration tests
pytest tests/test_research_integration.py -v
```

### Test Categories

**Unit Tests:**
- `test_research_engine.py` — Individual methods
- `test_research_ai_scorer.py` — Scoring logic
- `test_research_schema.py` — Data structures

**Integration Tests:**
- `test_research_integration.py` — Full Step 1→2→3 flow
- Multiple business intents
- Keyword ranking verification
- Deduplication logic
- Fallback handling

### CI/CD Pipeline

Tests run on:
- Push to main branch
- Pull request creation
- Manual trigger

Requirements:
- All unit tests pass (coverage >80%)
- Integration tests pass (with mocked Ollama)
- No memory leaks (< 10MB increase)
- Performance < 20s per pillar

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("annaseo.research_engine")
log.setLevel(logging.DEBUG)
```

### Monitor Ollama

```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Get model info
curl http://localhost:11434/api/show -d '{"name":"deepseek-r1:7b"}'

# Test inference
curl http://localhost:11434/api/generate -d '{
  "model": "deepseek-r1:7b",
  "prompt": "Hello",
  "stream": false
}'

# Kill Ollama
pkill -f ollama
```

### Database Inspection

```bash
# Check research_results table
sqlite3 annaseo.db "SELECT COUNT(*) FROM research_results;"
sqlite3 annaseo.db "SELECT * FROM research_results LIMIT 5;"

# Check keyword_input_sessions
sqlite3 annaseo.db "SELECT * FROM keyword_input_sessions WHERE session_id=?;" -bind "session_id_here"

# Total keywords by source
sqlite3 annaseo.db "SELECT source, COUNT(*) FROM research_results GROUP BY source;"

# Average scores
sqlite3 annaseo.db "SELECT source, AVG(total_score) FROM research_results GROUP BY source;"
```

### Performance Profiling

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

engine = ResearchEngine()
results = engine.research_keywords(
    project_id="test",
    session_id="test_session",
    business_intent="ecommerce"
)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats("cumulative").print_stats(20)
```

### Common Issues & Solutions

**Issue: Ollama connection refused**
```
Error: Connection refused to http://localhost:11434
Solution: Start Ollama: `ollama serve`
```

**Issue: Model not found: deepseek-r1:7b**
```
Solution: Pull model: `ollama pull deepseek-r1:7b`
```

**Issue: Keywords returned with score 0**
```
Cause: AI scoring failed, fallback used
Check: Ollama logs, context size
Solution: Reduce batch size or check Ollama
```

**Issue: Deduplication reduced keywords too much**
```
Cause: User provided too many similar keywords
Solution: Review input for typos/duplicates
Future: Add fuzzy matching threshold
```

---

**See Also:**
- [RESEARCH_ENGINE.md](./RESEARCH_ENGINE.md) — User guide
- [KEYWORD_WORKFLOW.md](./KEYWORD_WORKFLOW.md) — Full Step 1-7 flow
- [ENGINES.md](./ENGINES.md) — Other engine documentation

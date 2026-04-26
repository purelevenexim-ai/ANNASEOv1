# Strategy Page Complete Reference — Full Dataflow & Pipeline

**Last Updated:** 2026-04-26  
**Status:** Complete Implementation with Full Technical Documentation  
**Scope:** End-to-end Strategy page (3-step wizard: Profile → Generate → Review)

---

## Table of Contents

1. [Overview & Architecture](#1-overview--architecture)
2. [Complete Data Flow (End-to-End)](#2-complete-data-flow-end-to-end)
3. [Backend Pipeline (Step-by-Step)](#3-backend-pipeline-step-by-step)
4. [Database Schema](#4-database-schema)
5. [Frontend Implementation (React)](#5-frontend-implementation-react)
6. [All API Endpoints](#6-all-api-endpoints)
7. [Working Examples & Data Structures](#7-working-examples--data-structures)
8. [Error Handling & Recovery](#8-error-handling--recovery)
9. [Performance & Optimization](#9-performance--optimization)
10. [Troubleshooting Guide](#10-troubleshooting-guide)

---

## 1) Overview & Architecture

### What is the Strategy Page?

The Strategy page is a **3-step wizard** for generating SEO/AEO content strategies:

1. **Step 1: Business & Audience Profile Form**
   - Collect business details, target market, products, personas
   - Validate and save to `audience_profiles` table
   - Load defaults from `projects` table if first time

2. **Step 2: AI Strategy Generation (SSE Streaming)**
   - Load audience profile + top keywords from database
   - Send to AI provider (Groq → Gemini → Ollama → Claude)
   - Stream progress logs in real-time (Server-Sent Events)
   - Return complete strategy JSON

3. **Step 3: Strategy Review & Confirmation**
   - Display strategy: executive summary, goals, pillars, calendar, KPIs
   - Show AI confidence score
   - Allow regeneration or edit profile

### File Locations

| Component | Path | Type |
|-----------|------|------|
| Frontend (main) | `frontend/src/StrategyPage.jsx` | React (800 lines) |
| Backend Routes | `main.py` lines 20898–21650 | FastAPI |
| Database Init | `main.py` lines 333–350 | SQLite setup |
| App Route Wire | `frontend/src/App.jsx` | React Router |

### Technology Stack

- **Frontend**: React 18, TanStack Query (useQuery), Fetch API (SSE)
- **Backend**: FastAPI, SQLite3, Bearer token auth
- **AI Providers**: Groq LLaMA, Google Gemini, Ollama, Claude (fallback cascade)
- **Data Flow**: REST APIs + Server-Sent Events (SSE) for streaming

---

## 2) Complete Data Flow (End-to-End)

### 2.1 User Interaction → Data Storage

```
┌─────────────────────────────────────────────────────────────┐
│ USER SELECTS PROJECT (from sidebar)                         │
│ → App state: activeProject = "proj_cc8c240d60"             │
└─────────────┬───────────────────────────────────────────────┘
              ▼
┌─────────────────────────────────────────────────────────────┐
│ StrategyPage({ projectId }) renders                         │
│ Fetches: GET /api/strategy/{projectId}/latest              │
│ (useQuery hook with kw="latest-strategy")                  │
└─────────────┬───────────────────────────────────────────────┘
              │
              ├─ If latestStrategy exists:
              │  → Jump to Step 3 (show saved strategy)
              │
              └─ Otherwise:
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: ProfileStep Component                              │
│ ──────────────────────────────────────────────────────────  │
│ On Mount:                                                   │
│  • GET /api/strategy/{projectId}/audience                  │
│    └─ Load existing audience_profile OR fallback to        │
│       project defaults                                      │
│                                                             │
│ Form Fields (React State):                                 │
│  • website_url (text)                                       │
│  • business_type (select: B2C/B2B/D2C/marketplace)         │
│  • usp (textarea)                                           │
│  • products (array/chips)                                   │
│  • personas (array/chips)                                   │
│  • target_locations (array/chips)                           │
│  • target_languages (array/chips)                           │
│  • target_religions (array/chips)                           │
│  • customer_reviews (textarea, optional)                    │
│  • competitor_urls (array/chips)                            │
│                                                             │
│ On Save Button:                                             │
│  1. Client-side validation:                                 │
│     - personas ✓ (min 1)                                    │
│     - products ✓ (min 1)                                    │
│     - target_locations ✓ (min 1)                            │
│     - target_languages ✓ (min 1)                            │
│     - target_religions ✓ (min 1)                            │
│                                                             │
│  2. PUT /api/strategy/{projectId}/audience                 │
│     Body: { website_url, business_type, usp, products, ... }
│                                                             │
│  3. Backend processing:                                     │
│     → Validate again (server-side)                          │
│     → INSERT/UPDATE audience_profiles table                 │
│     → SYNC projects table (master profile)                  │
│     → Return { saved: true, updated: true }                │
│                                                             │
│  4. Frontend:                                               │
│     → Invalidate ["audience", projectId]                    │
│     → Call onNext() → setStep(2)                            │
└─────────────┬───────────────────────────────────────────────┘
              ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: GenerateStep Component                             │
│ ──────────────────────────────────────────────────────────  │
│ On Mount (useEffect):                                       │
│  • Immediately starts generation (no user click)            │
│  • startGeneration() callback:                              │
│                                                             │
│  1. setStatus("running")                                    │
│  2. POST /api/strategy/{projectId}/generate-stream         │
│     Method: SSE (Server-Sent Events, not Request/Response) │
│     Body: { } (empty)                                       │
│                                                             │
│  3. Read streaming response:                                │
│     - res.body.getReader() for raw stream                   │
│     - Parse "data: {json}" lines                            │
│     - Accumulate in buf: string (handle partial lines)      │
│     - TextDecoder to convert bytes to UTF-8                 │
│     - JSON.parse each event                                 │
│                                                             │
│  4. Handle events:                                          │
│     • { type: "log", msg: "...", level: "info"|"success"|... }
│       → setLogs(prev => [...prev.slice(-199), { msg, level }])
│       (keep only last 200 logs in memory)                   │
│                                                             │
│     • { type: "complete", strategy: {...} }               │
│       → setStrategy(strategy)                               │
│       → setStatus("done")                                   │
│                                                             │
│     • { type: "error", msg: "..." }                        │
│       → setError(msg)                                       │
│       → setStatus("error")                                  │
│                                                             │
│  5. Error handling:                                         │
│     • Network error (e.g., AbortError)                      │
│       → setError(string(e))                                 │
│       → setStatus("error")                                  │
│     • Retry available on error (Retry button)               │
│       → startGeneration() again                             │
│                                                             │
│  Cleanup: abortRef.current?.abort() on unmount             │
│           (prevents memory leaks on cancel/back btn)        │
└─────────────┬───────────────────────────────────────────────┘
              ▼
│ Logs Display (auto-scroll):                                 │
│  • Styled console (dark bg, monospace)                      │
│  • Status indicator (pulse animation while running)         │
│  • Height: 240px, max 200 log entries                       │
│                                                             │
└─────────────┬───────────────────────────────────────────────┘
              ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: StrategyPlanStep Component                         │
│ ──────────────────────────────────────────────────────────  │
│ Display (Read-Only until confirmation):                     │
│  • [Executive Summary] (purple card)                        │
│  • [Ranking Goals]                                          │
│    - Google target                                          │
│    - AI search target                                       │
│    - Monthly traffic estimate                               │
│  • [Pillar Strategy] (2-col grid)                           │
│    - pillar name, target_rank, monthly_searches             │
│    - difficulty, content_type, ai_snippet_opportunity       │
│  • [Content Calendar] (scrollable months)                   │
│    - month.month, month.focus_pillar                        │
│    - articles[] with title, type, word_count, keyword       │
│  • [Quick Wins]                                             │
│  • [AEO Tactics]                                            │
│  • [Competitor Gaps]                                        │
│  • [KPIs]                                                   │
│  • [AI Confidence badge] (top-right)                        │
│                                                             │
│ User Actions:                                               │
│  • ✓ Confirm Strategy (locks it in, setConfirmed=true)     │
│  • ↻ Regenerate (back to Step 2)                           │
│  • ← Edit Profile (back to Step 1)                          │
│                                                             │
│ Confirmed state:                                            │
│  • Disables back/edit (prevents accidental changes)         │
│  • Shows green success banner                               │
│  • Strategy effectively saved to step.state                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Backend Database Writes During Flow

```
Step 1 Save:
  PUT /api/strategy/{project_id}/audience
  ▼
  INSERT INTO audience_profiles (...) VALUES (...)
  ON CONFLICT(project_id) DO UPDATE
  UPDATE projects SET target_locations, target_languages, ...

Step 3 Confirmation:
  (Currently: confirmation is client-side only)
  (No backend write occurs on "Confirm Strategy")
  (Strategy is only saved when user proceeds to content pipeline)
```

---

## 3) Backend Pipeline (Step-by-Step)

### Backend Route: POST /api/strategy/{project_id}/generate-stream

**Signature:**
```python
@app.post("/api/strategy/{project_id}/generate-stream", tags=["Strategy"])
async def strategy_generate_stream(
    project_id: str,
    body: dict = Body(default={}),
    user=Depends(current_user),
):
```

**Processing Flow:**

```
1. LOAD CONTEXT (from database)
   ──────────────────────────────
   • audience_profiles WHERE project_id = ?
   • projects WHERE project_id = ?
   
   If either missing:
   → yield error event
   → return

2. NORMALIZE DATA (safe JSON parse)
   ────────────────────────────────
   For each field in audience profile (target_locations, personas, etc):
     if field is None → use default [] or ["India"]
     if field is list/dict → use as-is
     if field is string → json.loads() with fallback
   
   Result: normalized_profile = {
     "project_name": "...",
     "industry": "...",
     "target_locations": [...],
     "personas": [...],
     "products": [...],
     "business_type": "B2C",
     "usp": "...",
     "competitor_urls": [...],
     ... (15+ fields)
   }

3. LOAD TOP KEYWORDS (from keyword_universe_items)
   ────────────────────────────────────────────────
   SELECT keyword, pillar_keyword, intent, opportunity_score
   WHERE project_id = ? AND status IN ('accepted', 'pending')
   ORDER BY opportunity_score DESC LIMIT 80
   
   Group by pillar_keyword:
   {
     "pillar_1": ["keyword1", "keyword2", ...],
     "pillar_2": ["keyword3", "keyword4", ...],
     ...
   }
   
   Yield: "Loaded 80 keywords across 5 pillars"

4. BUILD AI PROMPT
   ────────────────
   Construct strategic prompt with:
   • Business context (name, industry, location, language, culture)
   • Audience personas
   • Products/services
   • Competitor analysis
   • Top keyword pillars (with 6 keywords per pillar)
   
   Request AI to return JSON:
   {
     "executive_summary": "...",
     "seo_goals": { "google_target": "...", ... },
     "pillar_strategy": [{ "pillar": "...", "target_rank": 1, ... }],
     "content_calendar": [{ "month": "...", "articles": [...] }],
     "aeo_tactics": [...],
     "competitor_gaps": [...],
     "quick_wins": [...],
     "kpis": [...],
     "recommended_posting_frequency": "...",
     "strategy_confidence": 85
   }

5. CALL AI PROVIDER (CASCADE)
   ─────────────────────────────
   Try each in order:
   
   a) GROQ (fastest, most reliable)
      POST https://api.groq.com/openai/v1/chat/completions
      model: llama-3.3-70b-versatile
      timeout: 60s
      temp: 0.3, max_tokens: 3000
      
      If success: extract text from response → yield "Groq success"
      If timeout/error: continue to next provider
   
   b) GEMINI (Google Paid API)
      POST https://generativelanguage.googleapis.com/v1/models/...
      model: gemini-pro or gemini-2.0-flash
      timeout: 60s
      stream: false (single response)
      
      If success: extract content → yield "Gemini success"
      If timeout/error: continue to next
   
   c) OLLAMA (Local, free)
      POST http://OLLAMA_URL:8080/api/generate
      model: mistral:7b-instruct-q4_K_M (or env override)
      timeout: 120s (longer for local)
      stream: false (already SSE at HTTP level)
      
      If success: extract response → yield "Ollama success"
      If timeout/error: continue to next
   
   d) CLAUDE (Anthropic, expensive fallback)
      POST https://api.anthropic.com/v1/messages
      model: claude-opus
      timeout: 60s
      
      If success: extract content → yield "Claude success"
      If all fail: yield error event → return

6. PARSE & VALIDATE JSON
   ──────────────────────
   text = "{...}" (raw AI output)
   
   Try:
     clean_json = re.sub(r'^```json|```$', '', text).strip()
     strategy = json.loads(clean_json)
   Catch JSONDecodeError:
     yield error event
     return
   
   Validate structure (normalize_strategy function):
     • Ensure all required top-level keys exist
     • Set defaults for missing optional fields
     • Validate arrays and nested objects

7. STREAM COMPLETION EVENT
   ────────────────────────
   yield f"data: {json.dumps({
     'type': 'complete',
     'strategy': normalized_strategy,
   })}\n\n"

8. CLOSE SSE STREAM
   ─────────────────
   Return (end of async generator)
```

### Data Normalization (normalize_strategy)

```python
def normalize_strategy(result_json: dict) -> dict:
    """
    Ensures strategy has all required fields with sensible defaults.
    """
    return {
        "executive_summary": result_json.get("executive_summary", ""),
        "seo_goals": result_json.get("seo_goals", {
            "google_target": "Top 5 positions",
            "ai_search_target": "Featured in AI answers",
            "monthly_traffic_target": "Estimated organic traffic"
        }),
        "pillar_strategy": result_json.get("pillar_strategy", []),
        "content_calendar": result_json.get("content_calendar", []),
        "aeo_tactics": result_json.get("aeo_tactics", []),
        "competitor_gaps": result_json.get("competitor_gaps", []),
        "quick_wins": result_json.get("quick_wins", []),
        "kpis": result_json.get("kpis", []),
        "recommended_posting_frequency": result_json.get("recommended_posting_frequency", "2-3 articles/week"),
        "strategy_confidence": int(result_json.get("strategy_confidence", 0)),
    }
```

---

## 4) Database Schema

### Table: audience_profiles

Stores business profile, market targeting, and audience data.

```sql
CREATE TABLE IF NOT EXISTS audience_profiles(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL UNIQUE,
    
    -- Business
    website_url TEXT DEFAULT '',
    business_type TEXT DEFAULT 'B2C',  -- B2C|B2B|D2C|marketplace|publisher|service
    usp TEXT DEFAULT '',  -- Unique Selling Proposition
    
    -- Target Market (arrays stored as JSON strings)
    target_locations TEXT DEFAULT '[]',  -- ["India", "US", ...]
    target_languages TEXT DEFAULT '[]',  -- ["English", "Hindi", ...]
    target_religions TEXT DEFAULT '[]',  -- ["general", "Hindu", "Muslim", ...]
    
    -- Audience
    personas TEXT DEFAULT '[]',  -- ["Health-conscious home cooks", ...]
    products TEXT DEFAULT '[]',  -- ["Organic spices", "Gift hampers", ...]
    customer_reviews TEXT DEFAULT '',  -- User-provided review insights
    ad_copy TEXT DEFAULT '',  -- User-provided ad copy for context
    
    -- Competitive landscape
    competitor_urls TEXT DEFAULT '[]',  -- ["https://competitor1.com", ...]
    seasonal_events TEXT DEFAULT '[]',  -- ["Diwali", "Christmas", ...]
    
    -- Advanced targeting
    pillar_support_map TEXT DEFAULT '{}',  -- {"pillar": ["supporting_kw", ...]}
    intent_focus TEXT DEFAULT 'transactional',  -- transactional|informational|both
    allowed_topics TEXT DEFAULT '[]',
    blocked_topics TEXT DEFAULT '[]',
    business_locations TEXT DEFAULT '[]',
    
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Example Row:**
```json
{
  "id": 42,
  "project_id": "proj_cc8c240d60",
  "website_url": "https://pureleven.com",
  "business_type": "B2C",
  "usp": "Single-origin premium spices with certificates",
  "target_locations": ["India", "US"],
  "target_languages": ["English", "Hindi"],
  "target_religions": ["general", "Hindu"],
  "personas": ["Health-conscious home cooks", "Chefs buying bulk"],
  "products": ["Organic turmeric powder", "Spice blends", "Gift sets"],
  "customer_reviews": "Customers ask about purity, aroma, and bulk options",
  "competitor_urls": ["https://everest.in", "https://mdh.in"],
  "pillar_support_map": {
    "organic turmeric": ["benefits of turmeric", "how to use turmeric"],
    "spice blends": ["Indian spice blends", "cooking with spices"]
  },
  "intent_focus": "both",
  "created_at": "2026-04-20T09:15:30Z",
  "updated_at": "2026-04-26T14:45:20Z"
}
```

### Table: strategy_sessions

Stores generated strategies and metadata.

```sql
CREATE TABLE IF NOT EXISTS strategy_sessions(
    session_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    engine_type TEXT DEFAULT 'audience',  -- 'audience' | 'development' | etc
    status TEXT DEFAULT 'pending',  -- pending|running|completed|failed
    
    -- What was sent to AI
    input_json TEXT DEFAULT '{}',
    
    -- What AI returned (normalized)
    result_json TEXT DEFAULT '{}',
    
    -- Metadata
    confidence REAL DEFAULT 0,  -- AI confidence (0-100)
    tokens_used INTEGER DEFAULT 0,  -- tokens consumed
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_project_created (project_id, created_at)
);
```

**Example Row:**
```json
{
  "session_id": "sess_abc123xyz",
  "project_id": "proj_cc8c240d60",
  "engine_type": "audience",
  "status": "completed",
  "input_json": "{\"project_name\": \"Pure Eleven\", ...}",
  "result_json": "{\"executive_summary\": \"...\", \"seo_goals\": {...}, ...}",
  "confidence": 87,
  "tokens_used": 2845,
  "created_at": "2026-04-26T14:45:30Z"
}
```

### Table: projects

Extensions used by strategy page (subset shown):

```sql
CREATE TABLE IF NOT EXISTS projects(
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    industry TEXT DEFAULT 'general',
    description TEXT DEFAULT '',
    
    -- Seed keywords (products/services)
    seed_keywords TEXT DEFAULT '[]',
    
    -- Master audience (sync'd from audience_profiles on Step 1 save)
    target_locations TEXT DEFAULT '[]',
    target_languages TEXT DEFAULT '[]',
    religion TEXT DEFAULT 'general',  -- single value
    audience_personas TEXT DEFAULT '[]',
    competitor_urls TEXT DEFAULT '[]',
    customer_reviews TEXT DEFAULT '',
    
    business_type TEXT DEFAULT 'B2C',
    usp TEXT DEFAULT '',
    
    -- WordPress integration (not used by strategy)
    wp_url TEXT DEFAULT '',
    wp_user TEXT DEFAULT '',
    wp_pass_enc TEXT DEFAULT '',  -- encrypted
    
    owner_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_owner (owner_id)
);
```

---

## 5) Frontend Implementation (React)

### Component Hierarchy

```
StrategyPage
  ├─ useQuery("latest-strategy", projectId)
  │  └─ GET /api/strategy/{projectId}/latest
  │
  ├─ Step === 1
  │  └─ ProfileStep
  │     ├─ Form state: { website_url, business_type, usp, products, ... }
  │     ├─ Load: GET /api/strategy/{projectId}/audience OR fallback to projects
  │     ├─ Save: PUT /api/strategy/{projectId}/audience
  │     └─ Validation: client-side + backend server-side
  │
  ├─ Step === 2
  │  └─ GenerateStep
  │     ├─ useRef(abortCtrl) for cancel support
  │     ├─ Stream: POST /api/strategy/{projectId}/generate-stream
  │     ├─ Parse SSE: "data: {...}\n\n"
  │     ├─ State: status, logs[], strategy, error
  │     └─ Auto-retry: available if error
  │
  └─ Step === 3
     └─ StrategyPlanStep
        ├─ Read-only display until confirmed
        ├─ Show: summary, goals, pillars, calendar, KPIs, gaps, tactics
        ├─ AI confidence badge
        └─ Actions: Confirm, Regenerate, Edit Profile
```

### ProfileStep: Key Code Patterns

```javascript
// Load existing profile
useEffect(() => {
  const r = await fetch(`${API}/api/strategy/${projectId}/audience`, 
    { headers: authHeaders() })
  const audience = await r.json()
  
  // Merge with form defaults
  setForm({
    website_url: audience.website_url || "",
    target_locations: audience.target_locations || [],
    // ... other fields
  })
}, [projectId])

// Save profile
const handleSave = async () => {
  setSaving(true)
  const errors = []
  
  // Client validation
  if (!form.personas.length) errors.push("At least one persona required")
  if (!form.products.length) errors.push("At least one product required")
  if (!form.target_locations.length) errors.push("Location required")
  // ... 2 more validations
  
  if (errors.length) {
    setErrors(errors)
    setSaving(false)
    return
  }
  
  try {
    const r = await fetch(`${API}/api/strategy/${projectId}/audience`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders()
      },
      body: JSON.stringify(form)
    })
    
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      setErrors([d?.detail || "Save failed"])
      return
    }
    
    // Invalidate cache & proceed
    queryClient.invalidateQueries(["audience", projectId])
    onNext()
  } catch (e) {
    setErrors([String(e)])
  } finally {
    setSaving(false)
  }
}
```

### GenerateStep: SSE Streaming Pattern

```javascript
const startGeneration = useCallback(() => {
  setStatus("running")
  setLogs([])
  setError("")
  
  const ctrl = new AbortController()
  abortRef.current = ctrl
  
  fetch(`${API}/api/strategy/${projectId}/generate-stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders()
    },
    body: JSON.stringify({}),
    signal: ctrl.signal,
  })
    .then(async res => {
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        setError(d?.detail || `HTTP ${res.status}`)
        setStatus("error")
        return
      }
      
      // SSE streaming read
      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ""
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        
        buf += dec.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop()  // Keep incomplete line in buffer
        
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          
          try {
            const ev = JSON.parse(raw)
            
            if (ev.type === "log") {
              setLogs(prev => [
                ...prev.slice(-199),  // Keep last 200
                { msg: ev.msg, level: ev.level }
              ])
            } else if (ev.type === "complete") {
              setStrategy(ev.strategy)
              setStatus("done")
            } else if (ev.type === "error") {
              setError(ev.msg || "Generation failed")
              setStatus("error")
            }
          } catch { /* ignore parse errors */ }
        }
      }
      
      setStatus(s => s === "running" ? "done" : s)
    })
    .catch(e => {
      if (e.name !== "AbortError") {
        setError(String(e))
        setStatus("error")
      }
    })
}, [projectId])

// Auto-start on mount
useEffect(() => { startGeneration() }, [startGeneration])

// Cancel on unmount
useEffect(() => () => abortRef.current?.abort(), [])
```

### StrategyPlanStep: Display Rendering

```javascript
function StrategyPlanStep({ strategy, onBack, onRegenerate }) {
  const [confirmed, setConfirmed] = useState(false)
  
  const conf = strategy.strategy_confidence || 0
  const confColor = conf >= 80 ? T.teal : conf >= 50 ? T.amber : T.red
  
  // Render sections conditionally based on strategy content
  return (
    <div>
      {/* Confidence badge */}
      <div style={{ ... }}>
        <div>{conf}%</div>
        <div>AI Confidence</div>
      </div>
      
      {/* Executive Summary (purple card) */}
      {strategy.executive_summary && (
        <Card style={{ background: T.purpleLight }}>
          {strategy.executive_summary}
        </Card>
      )}
      
      {/* Ranking Goals (3-col grid) */}
      {strategy.seo_goals && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr" }}>
          <div>{strategy.seo_goals.google_target}</div>
          <div>{strategy.seo_goals.ai_search_target}</div>
          <div>{strategy.seo_goals.monthly_traffic_target}</div>
        </div>
      )}
      
      {/* Pillar Strategy (table-like) */}
      {strategy.pillar_strategy?.map(p => (
        <div key={p.pillar}>
          <div>{p.pillar}</div>
          <div>#{p.target_rank}</div>
          <div>{p.difficulty}</div>
          {p.ai_snippet_opportunity && "🤖 AI"}
        </div>
      ))}
      
      {/* Content Calendar (scrollable) */}
      {strategy.content_calendar?.map(month => (
        <div key={month.month}>
          <div>{month.month}</div>
          {month.articles?.map(a => (
            <div key={a.title}>
              <div>{a.title}</div>
              <div>{a.type} · {a.word_count} words</div>
              {a.target_keyword && <div>{a.target_keyword}</div>}
            </div>
          ))}
        </div>
      ))}
      
      {/* Quick Wins, AEO Tactics, Competitor Gaps, KPIs */}
      ...
      
      {/* Confirmation */}
      <Card>
        {confirmed 
          ? <div>✓ Strategy confirmed!</div>
          : <div>Review above, then confirm.</div>
        }
        {!confirmed && (
          <Btn onClick={() => setConfirmed(true)}>✓ Confirm Strategy</Btn>
        )}
      </Card>
    </div>
  )
}
```

---

## 6) All API Endpoints

### Endpoints Summary Table

| Method | Endpoint | Purpose | Auth | Response |
|--------|----------|---------|------|----------|
| GET | `/api/strategy/{project_id}/audience` | Load audience profile | Bearer | `{...audience fields}` |
| PUT | `/api/strategy/{project_id}/audience` | Save audience profile | Bearer | `{saved: bool, updated: bool}` |
| POST | `/api/strategy/{project_id}/generate-stream` | Generate strategy via SSE | Bearer | SSE Stream |
| GET | `/api/strategy/{project_id}/latest` | Get latest saved strategy | Bearer | `{strategy: {...}, meta: {...}}` |
| GET | `/api/strategy/{project_id}/input-health` | Validate Step 1 inputs | Bearer | `{ready: bool, missing: [], status: str}` |

### 6.1 GET /api/strategy/{project_id}/audience

**Purpose:** Load business profile for Step 1 form

**Query Params:** None

**Response:**
```json
{
  "website_url": "https://pureleven.com",
  "business_type": "B2C",
  "usp": "Premium single-origin spices",
  "target_locations": ["India", "US"],
  "target_languages": ["English", "Hindi"],
  "target_religions": ["general"],
  "personas": ["Health-conscious home cooks"],
  "products": ["Organic turmeric"],
  "customer_reviews": "Customers ask about purity",
  "ad_copy": "",
  "competitor_urls": ["https://everest.in"],
  "seasonal_events": [],
  "pillar_support_map": {"turmeric": ["benefits", "uses"]},
  "intent_focus": "transactional",
  "allowed_topics": [],
  "blocked_topics": []
}
```

**Fallback (if no audience_profiles row):**
```json
{
  "status": "processing",
  "audience": null,
  "message": "Strategy not generated yet",
  "website_url": "<from projects.wp_url>",
  "target_locations": "<from projects.target_locations>",
  // ... other fields from projects table
}
```

### 6.2 PUT /api/strategy/{project_id}/audience

**Purpose:** Save/update business profile after Step 1 form

**Request Body:**
```json
{
  "website_url": "https://pureleven.com",
  "business_type": "B2C",
  "usp": "Premium spices with certificates",
  "target_locations": ["India", "US"],
  "target_languages": ["English", "Hindi"],
  "target_religions": ["general"],
  "personas": ["Health-conscious home cooks"],
  "products": ["Organic turmeric powder", "Spice blends"],
  "customer_reviews": "Customers ask about purity and aroma",
  "ad_copy": "",
  "competitor_urls": ["https://everest.in", "https://mdh.in"],
  "seasonal_events": [],
  "pillar_support_map": {},
  "intent_focus": "both",
  "allowed_topics": [],
  "blocked_topics": []
}
```

**Validation (Backend):**
- personas: min 1 item → 400 error
- products: min 1 item → 400 error
- target_locations: min 1 item → 400 error
- target_languages: min 1 item → 400 error
- target_religions: min 1 item → 400 error

**Response on Success (200):**
```json
{
  "saved": true,
  "updated": true,
  "message": "Profile saved"
}
```

**Response if No Change (200):**
```json
{
  "saved": true,
  "updated": false,
  "message": "No changes"
}
```

**Side Effects:**
- Inserts/updates `audience_profiles` table
- Updates `projects` table (replicate target_locations, target_languages, religion, etc.)

### 6.3 POST /api/strategy/{project_id}/generate-stream

**Purpose:** Generate SEO/AEO strategy via AI with SSE streaming

**Request Body:**
```json
{}  // Empty body, all context loaded from audience_profiles + keyword universe
```

**Response Type:** Server-Sent Events (SSE)

**Streamed Events:**

1. Log events:
```
data: {"type":"log","msg":"Strategy AI engine starting...","level":"info"}

data: {"type":"log","msg":"Loaded profile: B2C | general | India, US","level":"success"}

data: {"type":"log","msg":"Loading top-ranked keywords from universe...","level":"info"}

data: {"type":"log","msg":"Loaded 80 keywords across 5 pillars","level":"success"}

data: {"type":"log","msg":"Generating SEO/AEO strategy with AI (this may take 30-60s)...","level":"info"}

data: {"type":"log","msg":"AI strategy generated via Groq","level":"success"}

data: {"type":"log","msg":"Validating and normalizing strategy...","level":"info"}
```

2. Complete event (on success):
```
data: {"type":"complete","strategy":{"executive_summary":"...","seo_goals":{...},"pillar_strategy":[...],"content_calendar":[...],"aeo_tactics":[...],"competitor_gaps":[...],"quick_wins":[...],"kpis":[...],"recommended_posting_frequency":"2-3 articles/week","strategy_confidence":87}}
```

3. Error event:
```
data: {"type":"error","msg":"Project not found"}

data: {"type":"error","msg":"All AI providers failed"}
```

**AI Provider Cascade:**
1. **Groq** (llama-3.3-70b) — fastest, preferred
2. **Gemini** (Google) — reliable fallback
3. **Ollama** (local) — free, slower
4. **Claude** (Anthropic) — expensive last resort

**Timeout Handling:**
- Groq/Gemini/Claude: 60s timeout
- Ollama: 120s timeout (local, slower)
- If timeout → try next provider

### 6.4 GET /api/strategy/{project_id}/latest

**Purpose:** Fetch last saved strategy (for Step 3 jump or review)

**Response:**
```json
{
  "strategy": {
    "executive_summary": "Pure Eleven is a premium spice brand...",
    "seo_goals": {
      "google_target": "Top 5 positions for 20+ spice keywords",
      "ai_search_target": "Featured in AI answers for spice health benefits",
      "monthly_traffic_target": "5,000+ monthly organic visits"
    },
    "pillar_strategy": [
      {
        "pillar": "organic turmeric",
        "target_rank": 1,
        "difficulty": "medium",
        "monthly_searches": "15,000",
        "content_type": "blog",
        "ai_snippet_opportunity": true,
        "rationale": "High commercial intent, health trend"
      },
      // ... more pillars
    ],
    "content_calendar": [
      {
        "month": "Month 1",
        "focus_pillar": "organic turmeric",
        "articles": [
          {
            "title": "Benefits of Organic Turmeric: Science-Backed Guide",
            "type": "pillar",
            "target_keyword": "organic turmeric benefits",
            "word_count": 2500
          },
          // ... more articles
        ]
      },
      // ... more months
    ],
    "aeo_tactics": [
      "Target natural language questions in FAQ schema",
      "Create structured data for product reviews",
      "Optimize for featured snippets in ingredient keywords"
    ],
    "competitor_gaps": [
      "None of competitors have blog on bulk buying",
      "No content on international shipping"
    ],
    "quick_wins": [
      "Publish FAQ page for top 10 customer questions this week",
      "Update homepage with trust badges and certifications",
      "Create 'Spices 101' pillar content (supports 8+ keywords)"
    ],
    "kpis": [
      {
        "metric": "Top 5 organic ranked keywords",
        "target": "20+",
        "timeframe": "6 months"
      },
      {
        "metric": "Monthly organic traffic",
        "target": "5000+",
        "timeframe": "6 months"
      }
    ],
    "recommended_posting_frequency": "2-3 articles/week",
    "strategy_confidence": 87
  },
  "meta": {
    "project_id": "proj_cc8c240d60",
    "has_data": true,
    "version": "v1",
    "engine_type": "audience",
    "created_at": "2026-04-26T14:45:30Z"
  }
}
```

**If No Strategy Exists** (has_data: false):
```json
{
  "strategy": {
    // All fields with empty/default values
  },
  "meta": {
    "project_id": "proj_cc8c240d60",
    "has_data": false,
    "version": "v1"
  }
}
```

### 6.5 GET /api/strategy/{project_id}/input-health

**Purpose:** Quick validation of Step 1 inputs before generation

**Response (Ready):**
```json
{
  "ready": true,
  "missing": [],
  "profile": {
    "personas": ["Health-conscious home cooks"],
    "products": ["Organic spices"],
    "target_locations": ["India"],
    "target_languages": ["English"],
    "target_religions": ["general"]
  },
  "status": "ok"
}
```

**Response (Not Ready):**
```json
{
  "ready": false,
  "missing": ["personas", "products"],
  "profile": {
    "personas": [],
    "products": [],
    "target_locations": ["India"],
    "target_languages": ["English"],
    "target_religions": ["general"]
  },
  "status": "incomplete"
}
```

---

## 7) Working Examples & Data Structures

### 7.1 Complete Request/Response Flow

#### Step 1: Save Profile

```bash
# Generate JWT token
TOKEN="eyJ...abc123...xyz"

# Save audience profile
curl -X PUT "http://127.0.0.1:8000/api/strategy/proj_cc8c240d60/audience" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "website_url": "https://pureleven.com",
    "business_type": "B2C",
    "usp": "Single-origin premium spices with lab certificates",
    "target_locations": ["India", "USA"],
    "target_languages": ["English", "Hindi"],
    "target_religions": ["general", "Hindu"],
    "personas": ["Health-conscious home cooks", "Professional chefs"],
    "products": ["Organic turmeric powder", "Spice blends", "Gift hampers"],
    "customer_reviews": "Customers ask about: purity & testing, bulk orders, international shipping",
    "ad_copy": "Never settle for less - 100% pure, lab-tested spices",
    "competitor_urls": ["https://everest.in", "https://mdh.in", "https://indianspice.co"],
    "seasonal_events": ["Diwali", "Navratri"],
    "pillar_support_map": {
      "organic turmeric": ["benefits of turmeric", "how to use turmeric", "turmeric health"],
      "spice blends": ["Indian spice blends", "cooking with spices"]
    },
    "intent_focus": "both",
    "allowed_topics": ["health benefits", "cooking"],
    "blocked_topics": ["banned topics not relevant"]
  }'
```

**Response:**
```json
{
  "saved": true,
  "updated": true
}
```

#### Step 2: Stream Generation

```bash
curl -N -X POST "http://127.0.0.1:8000/api/strategy/proj_cc8c240d60/generate-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Streamed Output (first 10 lines):**
```
data: {"type":"log","msg":"Strategy AI engine starting...","level":"info"}

data: {"type":"log","msg":"Loaded profile: B2C | general | India, USA","level":"success"}

data: {"type":"log","msg":"Loading top-ranked keywords from universe...","level":"info"}

data: {"type":"log","msg":"Loaded 78 keywords across 4 pillars","level":"success"}

data: {"type":"log","msg":"Building AI prompt with business context...","level":"info"}

data: {"type":"log","msg":"Generating SEO/AEO strategy with AI (this may take 30-60s)...","level":"info"}

data: {"type":"log","msg":"Calling Groq LLaMA API...","level":"info"}

data: {"type":"log","msg":"AI strategy generated via Groq","level":"success"}

data: {"type":"log","msg":"Validating and normalizing strategy...","level":"info"}

data: {"type":"complete","strategy":{...}}
```

#### Step 3: Retrieve Latest

```bash
curl -s "http://127.0.0.1:8000/api/strategy/proj_cc8c240d60/latest" \
  -H "Authorization: Bearer $TOKEN" | jq '.strategy.pillar_strategy[0]'
```

**Output:**
```json
{
  "pillar": "organic turmeric",
  "target_rank": 1,
  "difficulty": "medium",
  "monthly_searches": "18,500",
  "content_type": "comprehensive guide",
  "ai_snippet_opportunity": true,
  "rationale": "High commercial intent, health trend growing 40% YoY, supports 8+ supporting keywords"
}
```

### 7.2 Strategy JSON Structure (Full Example)

```json
{
  "executive_summary": "Pure Eleven is a premium single-origin spice brand targeting health-conscious Indian and international audiences. Strategy focuses on Top 5 Google rankings for 20+ high-intent keywords (turmeric, spice blends, organic spices) + AI search visibility through FAQ optimization and snippet-friendly content. 6-month plan: 3-6 pillar articles (2-3k words) + 12-15 supporting articles (1-2k words) + schema implementation. Projected reach: 5,000+ monthly organic visitors.",

  "seo_goals": {
    "google_target": "Top 5 positions for 20+ keywords (turmeric, spice blends, organic spices + long-tail)",
    "ai_search_target": "Featured in Perplexity, ChatGPT, Gemini answers for spice health + cooking questions",
    "monthly_traffic_target": "5,000+ monthly organic visits from search (grow 100+ weekly)"
  },

  "pillar_strategy": [
    {
      "pillar": "organic turmeric",
      "target_rank": 1,
      "difficulty": "medium",
      "monthly_searches": "18,500",
      "content_type": "comprehensive guide + FAQ",
      "ai_snippet_opportunity": true,
      "rationale": "High commercial intent (people searching to buy), health trend (wellness + inflammation), supports 8+ keywords (benefits, uses, dosage, etc)"
    },
    {
      "pillar": "Indian spice blends",
      "target_rank": 2,
      "difficulty": "medium",
      "monthly_searches": "12,000",
      "content_type": "listicle",
      "ai_snippet_opportunity": true,
      "rationale": "Growing cooking interest, cultural relevance for India + diaspora market"
    },
    {
      "pillar": "organic spices",
      "target_rank": 3,
      "difficulty": "high",
      "monthly_searches": "22,000",
      "content_type": "comparison guide",
      "ai_snippet_opportunity": false,
      "rationale": "Highly competitive, broad category, supports selling angle (purity + certification)"
    }
  ],

  "content_calendar": [
    {
      "month": "Month 1 (May 2026)",
      "focus_pillar": "organic turmeric",
      "articles": [
        {
          "title": "Organic Turmeric 101: Health Benefits, Uses & How to Choose Quality",
          "type": "pillar",
          "target_keyword": "organic turmeric benefits",
          "word_count": 2500,
          "schema_type": "Article + FAQ"
        },
        {
          "title": "Why Lab-Tested Turmeric Matters: What to Look For",
          "type": "supporting",
          "target_keyword": "pure turmeric",
          "word_count": 1200
        },
        {
          "title": "10 Turmeric Recipes for Inflammation & Immunity",
          "type": "supporting",
          "target_keyword": "turmeric recipes",
          "word_count": 1500
        }
      ]
    },
    {
      "month": "Month 2 (June 2026)",
      "focus_pillar": "Indian spice blends",
      "articles": [
        {
          "title": "Best Indian Spice Blends:Garam Masala, Panch Puran & More Explained",
          "type": "pillar",
          "target_keyword": "Indian spice blends",
          "word_count": 2000
        },
        {
          "title": "How to Store Spices for Maximum Freshness",
          "type": "faq",
          "target_keyword": "how to store spices",
          "word_count": 800
        }
      ]
    }
  ],

  "aeo_tactics": [
    "Create FAQ sections in pillar articles targeting natural language questions (use Google People Also Ask for ideas)",
    "Implement Schema.org Product + Review markup on pages for rich snippets",
    "Answer 'how', 'why', 'what' questions in intro paragraphs (AI search prefers direct answers)",
    "Include data/statistics (e.g., 'Turmeric demand grew 40% YoY') for authority",
    "Create definition sections upfront for terms (AI extracts these)"
  ],

  "competitor_gaps": [
    "None of top 3 competitors have blog content on 'bulk spice ordering' → opportunity",
    "No competitor addresses 'international shipping' concern → opportunity",
    "Limited FAQ content on spice storage/freshness → low hanging fruit",
    "Health benefits content is generic, not India-specific → differentiate with Ayurvedic angle"
  ],

  "quick_wins": [
    "Week 1: Publish FAQ page answering top 10 customer questions (sourced from reviews + support tickets)",
    "Week 2: Update homepage with trust badges (lab certifications, organic seals, awards)",
    "Week 3: Create 'Spice Storage 101' guide (easy 1k word article, targets long-tail keywords)",
    "Week 4: Add customer reviews + photos to product pages (social proof + image optimization)"
  ],

  "kpis": [
    {
      "metric": "Keywords in Top 5 Google",
      "target": "20+",
      "timeframe": "6 months"
    },
    {
      "metric": "Monthly organic traffic",
      "target": "5,000+",
      "timeframe": "6 months"
    },
    {
      "metric": "Average ranking position (weighted)",
      "target": "<8",
      "timeframe": "6 months"
    },
    {
      "metric": "AI search feature ratio",
      "target": "30% of target keywords in AI answers",
      "timeframe": "4 months"
    }
  ],

  "recommended_posting_frequency": "2-3 articles/week (6-9 per month)",

  "strategy_confidence": 87
}
```

---

## 8) Error Handling & Recovery

### Client-Side Error Scenarios

#### Scenario 1: Missing Required Fields (Step 1)

```javascript
// Validation errors from PUT /api/strategy/{project_id}/audience
if (!form.personas.length) errors.push("At least one persona is required.")
if (!form.products.length) errors.push("At least one product is required.")
if (!form.target_locations.length) errors.push("...")
// ... etc

// Display errors
{errors.length > 0 && (
  <div style={{ background: "#FEF2F2", border: "1px solid #FCA5A5" }}>
    {errors.map(e => <div style={{color: "#DC2626"}}>• {e}</div>)}
  </div>
)}
```

**User Action:** Fill all required fields and retry.

#### Scenario 2: Generation Timeout (Step 2)

```javascript
// Timeout occurs if fetch takes > browser's implicit timeout
try {
  // fetch(...) with 60s+ operation
} catch (e) {
  if (e.name !== "AbortError") {
    setError(String(e))  // "Timeout" or network error
    setStatus("error")
  }
}

// Retry button available
{status === "error" && (
  <Btn onClick={startGeneration}>↻ Retry</Btn>
)}
```

**Root Cause:** 
- All AI providers timed out (60-120s per provider)
- Network interrupted during stream

**User Action:** 
- Check backend logs for provider errors
- Retry from UI
- If persistent, wait 5min then retry (rate limit)

#### Scenario 3: Invalid JSON from AI (Step 2)

```javascript
try {
  const ev = JSON.parse(raw)
  // process event
} catch {
  // Silently ignore malformed JSON lines
  // Continue reading next line
}
```

**Prevention:** Backend re-cleans JSON before yielding:
```python
clean = re.sub(r'^```json|```$', '', text).strip()
strategy = json.loads(clean)
```

**Fallback:** If final strategy is unparseable:
```python
yield f"data: {json.dumps({'type': 'error', 'msg': 'Invalid JSON'})}\n\n"
return
```

#### Scenario 4: Project Not Found (All Steps)

```python
@app.post("/api/strategy/{project_id}/generate-stream")
async def strategy_generate_stream(...):
    db = get_db()
    pr_row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    
    if not pr_row:
        yield f"data: {json.dumps({'type': 'error', 'msg': 'Project not found'})}\n\n"
        return
```

**HTTP Response:** 200 with SSE error event (not 404)

**User Action:** 
- Verify project_id in URL matches sidebar selection
- Refresh page
- Create a new project if deleted

### Server-Side Error Scenarios

#### Error: All AI Providers Failed

```python
text = ""

# Try Groq
if groq_key and not text:
    try:
        _gr = requests.post(..., timeout=60)
        if _gr.status_code == 200:
            text = _gr.json()["choices"][0]["message"]["content"]
            yield evt("AI generated via Groq", "success")
        else:
            yield evt(f"Groq {_gr.status_code}, trying Gemini", "warn")
    except Exception as e:
        yield evt(f"Groq timeout/error, trying Gemini", "warn")

# Try Gemini
if gemini_key and not text:
    try:
        _ge = requests.post(..., timeout=60)
        ...
    except:
        yield evt("Gemini failed, trying Ollama", "warn")

# Try Ollama
if not text:
    try:
        _ol = requests.post(..., timeout=120)
        ...
    except:
        yield evt("Ollama failed, trying Claude", "warn")

# Try Claude
if anthropic_key and not text:
    ...

# All failed
if not text:
    yield f"data: {json.dumps({'type': 'error', 'msg': 'All AI providers unavailable'})}\n\n"
    return
```

**Resolution:** 
- Check environment variables for API keys
- Verify provider health (test endpoints manually)
- Check rate limits and quotas

#### Error: Invalid Audience Profile

```python
if not pr_row:
    yield error
    return

audience = dict(ap_row) if ap_row else {}

# If audience profile missing, use project defaults
# This prevents errors — fields have safe defaults
```

**Prevention:** Profile is always available (either from audience_profiles or fallback to projects).

---

## 9) Performance & Optimization

### Load Time Analysis

| Operation | Duration | Notes |
|-----------|----------|-------|
| GET /audience | 5-20ms | Direct DB query |
| PUT /audience | 50-200ms | 2 INSERT + 1 UPDATE |
| POST /generate-stream (step 1-5) | 2-5s | Load profile, keywords, build prompt |
| POST /generate-stream (AI call) | 30-90s | Depends on provider & latency |
| Total Step 2 | 35-100s | User sees live logs (no waiting blind) |
| GET /latest | 10-30ms | Single query, JSON parse |

### Optimization Techniques

#### 1. Keyword Caching in Memory

```python
# Load LIMIT 80 keywords instead of all
kw_rows = ki_db.execute(
    "SELECT keyword, pillar FROM keyword_universe_items 
     WHERE project_id=? AND status IN ('accepted', 'pending')
     ORDER BY opportunity_score DESC LIMIT 80"
)
```

**Benefit:** Reduce AI context size (fewer tokens = faster)

#### 2. AI Provider Fallback (Fastest First)

Order: Groq (35-60s) → Gemini (40-80s) → Ollama (60-120s) → Claude (80-120s)

**Benefit:** 50+ seconds can be saved by Groq success

#### 3. SSE Streaming (Perceived UX)

Instead of showing blank screen for 60s, stream logs every 2-5s.

**Benefit:** Users see progress, no anxiety

#### 4. Log Size Limit (Last 200)

```javascript
setLogs(prev => [
  ...prev.slice(-199),  // Keep only last 200
  { msg, level }
])
```

**Benefit:** Prevent memory leak if generation runs for hours

#### 5. JSON Cleaning Regex

```python
clean_json = re.sub(r'^```json|```$', '', text).strip()
```

**Benefit:** Handle AI response with markdown fence

### Memory & Database Optimization

#### Table Indexing

```sql
CREATE INDEX IF NOT EXISTS idx_audience_project 
  ON audience_profiles(project_id);

CREATE INDEX IF NOT EXISTS idx_strategy_project_created 
  ON strategy_sessions(project_id, created_at);
```

**Benefit:** O(log n) lookup instead of O(n) scan

#### Row Limits

- Keyword load: LIMIT 80 (8+ pillars × 10 keywords each)
- Strategy sessions stored indefinitely (but latest query forces DESC order)

---

## 10) Troubleshooting Guide

### Problem: "Select a project" Screen on Page Load

**Symptoms:**
- StrategyPage renders with message "Select a project"
- No Step 1 form visible

**Cause:**
- `projectId` prop is null or undefined
- App global state not set

**Diagnosis:**
```javascript
// In browser console
console.log(activeProject)  // Should be string like "proj_cc8c240d60"
```

**Fix:**
1. Click project in sidebar
2. Wait for App state to update
3. Navigate to /strategy
4. Verify URL has project param if using route params

---

### Problem: Step 1 Save Fails with 400 Error

**Symptoms:**
- Click "Save & Generate Strategy"
- See error: "At least one persona is required"

**Cause:**
- Missing required field: personas | products | target_locations | target_languages | target_religions

**Diagnosis:**
```javascript
// In Step 1 code
if (!form.personas.length) {
  console.log("Personas empty:", form.personas)
}
```

**Fix:**
- Fill at least 1 value for each required field
- Use "+" button to add chips
- Press Enter to confirm chip

---

### Problem: Step 2 Stuck at "Generating"

**Symptoms:**
- Click "Save & Generate"
- Step 2 shows "Generating strategy..." > 2 minutes
- No error shown

**Cause:**
1. **AI provider timeout** — all providers (60-120s) exceeded
2. **Network interrupted** — browser lost connection
3. **Backend hanging** — AI endpoint unreachable

**Diagnosis:**
```bash
# Check backend health
curl -s http://127.0.0.1:8000/api/ai/health | jq

# Check logs
tail -50f /root/ANNASEOv1/logs/app.log | grep "strategy\|generate"
```

**Fix:**
1. Wait up to 120s (Ollama can be slow)
2. If > 2min, click "Retry" button
3. Check backend logs for provider errors
4. Verify environment variables:
   ```bash
   env | grep -E "GROQ_|GEMINI_|OLLAMA_|ANTHROPIC_"
   ```

---

### Problem: Step 2 Returns Error "All AI providers unavailable"

**Symptoms:**
- Generation starts
- Logs show "Trying Gemini", "Trying Ollama", etc.
- Final error: "All AI providers unavailable"

**Cause:**
- No API keys configured for any provider
- All provider endpoints are down/unreachable

**Diagnosis:**
```bash
# Check which keys are set
echo "GROQ: $GROQ_API_KEY"
echo "GEMINI: $GEMINI_API_KEY"
echo "OLLAMA: $OLLAMA_URL"
echo "ANTHROPIC: $ANTHROPIC_API_KEY"

# Test Groq directly
curl -s -X POST https://api.groq.com/openai/v1/chat/completions \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"test"}]}'

# Test Ollama locally
curl -s http://127.0.0.1:8000/api/generate -d '{"model":"mistral","prompt":"test"}'
```

**Fix:**
1. **Enable Groq** (fast, free tier available):
   ```bash
   export GROQ_API_KEY="gsk_..."  # Get key from groq.com
   ```

2. **Or enable Gemini**:
   ```bash
   export GEMINI_API_KEY="AIza..."  # Get key from Google Cloud
   ```

3. **Or run Ollama locally**:
   ```bash
   ollama pull mistral:7b-instruct-q4_K_M
   OLLAMA_URL=http://127.0.0.1:11434 node app.js
   ```

4. **Restart backend**:
   ```bash
   pkill -f "python.*main.py"
   python main.py  # or systemctl restart app
   ```

---

### Problem: Strategy JSON Parsing Fails

**Symptoms:**
- Step 2 shows "Validating and normalizing strategy..."
- Error appears: "Invalid JSON response"

**Cause:**
- AI returned non-JSON text
- JSON is malformed (extra commas, missing quotes)

**Diagnosis:**
```bash
# Check backend logs for "Failed to parse JSON"
grep -i "json" /root/ANNASEOv1/logs/app.log | tail -20

# Manually test AI provider
curl -X POST ... -d "$(python3 -c "import json; print(json.dumps(...))")"
```

**Fix:**
1. Retry from Step 2 (different AI provider may work)
2. Reduce prompt complexity (fewer pillars/keywords)
3. Check backend logs for which provider failed
4. Switch to Groq/Gemini if Ollama is failing

---

### Problem: Navigation Buttons Don't Work

**Symptoms:**
- Click "← Edit Profile" on Step 3
- Nothing happens, still on Step 3

**Cause:**
- `onBack` prop not wired to parent's state setter
- Component re-render issue

**Diagnosis:**
```javascript
// In StrategyPage
<StrategyPlanStep 
  strategy={strategy}
  onBack={() => setStep(1)}  // Check this is passed
  onRegenerate={() => setStep(2)}
/>
```

**Fix:**
1. Check StrategyPage parent component
2. Ensure `setStep()` is updating state
3. Verify React DevTools shows step state change
4. Clear browser cache & reload

---

### Problem: Form Fields Won't Update

**Symptoms:**
- Type in website_url field
- Text doesn't appear
- Or text appears but state doesn't update

**Cause:**
- onChange handler not linked
- Form state not initialized

**Diagnosis:**
```javascript
// Verify form state
console.log("form state:", form)

// Verify setter
const set = (key, value) => {
  setForm(prev => ({ ...prev, [key]: value }))
  console.log("After set:", form)  // Check updated
}
```

**Fix:**
1. Ensure `<input onChange={e => set("field", e.target.value)}` pattern
2. Check ChipInput onChange callback receives array
3. Clear localStorage if token is stale:
   ```bash
   localStorage.removeItem("annaseo_token")
   # Then login again
   ```

---

### Problem: Audience Profile Not Loading

**Symptoms:**
- Step 1 shows form but all fields are empty
- No pre-filled values from audience_profiles

**Cause:**
1. No audience_profiles row exists for this project (first time)
2. Fallback to projects table not working
3. API returns empty object

**Diagnosis:**
```bash
# Check if audience profile exists
sqlite3 /path/to/db.db "SELECT * FROM audience_profiles WHERE project_id='proj_...';"

# If empty, check projects table has fields
sqlite3 /path/to/db.db "SELECT target_locations, target_languages, ... FROM projects WHERE project_id='proj_...';"

# Test API
curl -s http://127.0.0.1:8000/api/strategy/proj_.../audience -H "Authorization: Bearer $TOKEN" | jq
```

**Fix:**
1. If no audience_profiles, Step 1 form shows empty — user fills from scratch (expected)
2. If projects table has data, fallback fills those values
3. Fill Step 1 form manually and save

---

### Problem: Network timeout during stream

**Symptoms:**
- Step 2 logs flow for 30s
- Then connection drops
- "Generation failed" error

**Cause:**
- Server crashed or restarted during generation
- Network latency spike
- Reverse proxy closed connection

**Diagnosis:**
```bash
# Check if server is alive
curl -s http://127.0.0.1:8000/api/ai/health

# Check logs for crash
tail -100 /root/ANNASEOv1/logs/app.log | grep -i "error\|exception"
```

**Fix:**
1. Click "Retry" button (state preserved)
2. If server down, restart:
   ```bash
   systemctl restart annaseo  # or
   python main.py  # if running locally
   ```
3. Reduce keyword count (#1) to reduce generation time

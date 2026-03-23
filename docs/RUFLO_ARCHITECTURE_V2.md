# RUFLO v2 — UPDATED APPLICATION ARCHITECTURE
## With Console Output, Content Strategy Module & Full Flexibility System

---

## UPDATED PAGE STRUCTURE

### Global (outside projects)
- **G1: Main Dashboard** — all projects, health scores, AI config, system status

### Inside Project (side navigation — 8 modules)
- **P1: Profile & Business Settings** — all inputs, fully editable with smart rerun
- **P2: Keywords & Strategy** — personas, context, execution console, keyword tree
- **P3: Keyword Universe Explorer** — D3 tree with full edit controls
- **P4: Content Creation Strategy** ← NEW (runs BEFORE content generation)
- **P5: Content Calendar** — 12-month grid, freeze queue
- **P6: Blog Editor** — draft/review/approve/freeze/fail
- **P7: SEO Checker** — technical audit
- **P8: Rankings & Analytics** — GSC, alerts, predictions

---

## G1: MAIN DASHBOARD

### Layout
```
Top bar: Logo | Global search | Notifications | User avatar

Project grid:
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────┐
│ Pureleven Organics  │  │ Munnar Tourism       │  │  + Create   │
│ Food & Spices · D2C │  │ Tourism · B2C        │  │  New Project│
│ ●──── 74/100 ────   │  │ ●──── 81/100 ────    │  │             │
│ 106 keywords        │  │ 94 keywords          │  │             │
│ 32 blogs frozen     │  │ 18 blogs published   │  │             │
│ Avg rank: 12.4      │  │ Avg rank: 8.1        │  │             │
│ [Open] [⋯]         │  │ [Open] [⋯]          │  │             │
└─────────────────────┘  └─────────────────────┘  └─────────────┘

⋯ menu: Open · Edit settings · Duplicate · Pause/Resume · Delete
```

### AI Configuration Panel (global)
```
Ollama status:   ● Running (deepseek-r1:7b loaded) | [Test connection]
Gemini API:      ● Configured | Free tier: 847/1000 req today | [Update key]
Claude API:      ● Configured | Balance: $18.42 | $2.38 used this month
GSC:             ● Connected (3 projects) | Last sync: 2h ago
WordPress:       ● Pureleven (connected) · Munnar (not connected)

Model selection:
  Keyword tasks:   [deepseek-r1:7b ▾]    Fallback: [llama3.1:8b ▾]
  Expansion:       [gemini-1.5-flash ▾]  Rate: [4s ▾]
  Content/Strategy:[claude-sonnet-4-6 ▾]

Cost tracker:     Claude this month: $2.38 | Projected: $6.90 | [Per-project ▾]
```

---

## PROJECT SIDE NAVIGATION

```
┌──────────────────┐
│ Pureleven        │
│ Organics         │
├──────────────────┤
│ Profile          │ ← P1
│ Keywords         │ ← P2 (with console)
│ Keyword Explorer │ ← P3 (D3 tree)
│ Content Strategy │ ← P4 NEW
│ Content Calendar │ ← P5
│ Blog Editor      │ ← P6
│ SEO Checker      │ ← P7
│ Rankings         │ ← P8
├──────────────────┤
│ Health: 74/100   │
│ Keywords: 106    │
│ Frozen: 32       │
│ Avg rank: 12.4   │
└──────────────────┘
```

---

## P1: PROFILE & BUSINESS SETTINGS

All fields editable. Every change shows "Impact assessment" before rerunning.

### Fields
```
Business name:     [Pureleven Organics          ] [Edit]
Website URL:       [https://pureleven.com        ] [Edit] [Re-crawl]
Industry:          [Food & Spices ▾              ]
Business type:     [D2C ▾                        ]
USP:               [Single-origin organic spices ] [Edit]

Products list:
  [✓] Black Pepper    /products/black-pepper    [Edit] [Remove]
  [✓] Cardamom       /products/cardamom         [Edit] [Remove]
  [✓] Cinnamon       /products/cinnamon         [Edit] [Remove]
  [+ Add product]
  → Adding a product: system runs M3+M4+M6+M7 for new product (~8 min)
  → Removing a product: shows "28 keywords will be removed. Confirm?"

Target locations (multi-select hierarchy):
  [✓] Wayanad    [✓] Kerala    [✓] Malabar    [✓] National (India)
  [ ] Tamil Nadu  [ ] Karnataka  [ ] South India  [ ] Global
  → Adding Tamil Nadu: system adds Tamil keywords to all pillars (~3 min)

Target religions (multi-select):
  [✓] Hindu    [✓] Muslim    [✓] Christian    [ ] Jain    [ ] General
  → Adding Christian: "15 new Christmas/Easter keyword opportunities detected"
  → User decides: [Run now] or [Skip]

Target languages:
  [✓] English    [✓] Malayalam    [✓] Hindi    [ ] Tamil    [ ] Arabic
  
Audience personas:    [free text, comma separated]
Competitor URLs:      [add/remove, each auto-crawled on add]
Customer reviews:     [paste reviews, Gemini extracts keywords]
Ad copy:              [paste ad text, extracts winning angles]
Seasonal events:      [✓] Christmas  [✓] Onam  [✓] Eid  [✓] Diwali  [+ Add]
```

### Change Impact Dialog
```
You changed: Added "Christian" to Target Religions

This will trigger:
  ✦ Context Engine: Generate Christian × all locations × all languages keywords
  ✦ Seasonal Engine: Add Christmas, Easter, Good Friday keyword clusters
  
Estimated time: ~3 minutes
New keywords expected: ~15–25

Existing keywords:     NOT AFFECTED
Existing frozen blogs: NOT AFFECTED
Scheduled content:     NOT AFFECTED

[Cancel] [Run now in background] [Run now + show console]
```

---

## P2: KEYWORDS & STRATEGY

### Sub-sections (tab navigation within P2)
1. **Audience Personas** — discovered persona chains, search queries per persona
2. **Context Clusters** — location × religion × language keyword clusters
3. **Seasonal Calendar** — festival keyword clusters with dates
4. **Strategy Plan** — Claude's approved 90-day plan, internal link map
5. **Execute** — run keyword pipeline button → opens console

### Execution Console (full spec)

**Layout:**
```
┌─ Ruflo Engine Console ──────────────────── [Running] [Pause] [Clear] [Export log] ─┐
│                                                                                      │
│ Overall: ████████████░░░░░░░░  7/12 engines · ~4 min remaining                     │
│                                                                                      │
│ Engine progress:                                                                     │
│  M1 Business Intel  [████████████] Done (11.2s)                          ✓          │
│  M2 Strategy Dev    [████████████] Done (9.4s)                           ✓          │
│  M3 Universe        [████████████] Done (11.1s)                          ✓          │
│  M4 Expansion       [████████████] Done (31.2s) ← longest engine        ✓          │
│  M5 Dedup           [████████████] Done (15.4s)                          ✓          │
│  M6 Clustering      [████████████] Done (11.3s)                          ✓          │
│  M7 Scoring         [████████░░░░] Running... (18.4s elapsed)            ⟳          │
│  M8 Claude Strategy [░░░░░░░░░░░░] Waiting                               ○          │
│  M9 Validation      [░░░░░░░░░░░░] Waiting                               ○          │
│                                                                                      │
│ [Scroll log ▼]                                                                      │
│ 09:14:02 [M1 ✓] Business Intelligence — crawled 24 pages · 47 existing KWs          │
│ 09:14:13 [M1 →] Output fed to M2: 47 existing KWs, 34 competitor topics              │
│ 09:14:14 [M2 ✓] Strategy Engine — 11 personas · 42 context clusters                 │
│ 09:14:23 [M2 →] Output fed to M3: personas + business context                        │
│ ...                                                                                  │
│ 09:15:36 [M7 ⟳] Scoring 291 keywords via DeepSeek...                               │
│                                                                                      │
│ Data flow summary:                                                                   │
│ Raw keywords collected: 564                                                          │
│ After exact dedup: 412                                                               │
│ After semantic dedup: 291                                                            │
│ Currently scoring: 291 → estimating Top 100                                          │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Color coding:**
- `#5DCAA5` (teal) = success / ✓ complete
- `#FAC775` (amber) = in progress / data
- `#F09595` (light red) = error / warning
- `#E24B4A` (red) = critical failure
- `#85B7EB` (blue) = engine output data
- `#CECBF6` (lavender) = Claude output
- `#888` (gray) = data handoff arrows / metadata

**Engine failure handling:**
```
Soft failure (retry succeeds):
  ⚠ [amber] "M4 Method 2 failed: Google rate limit. Retrying with DDG fallback..."
  ✓ [teal]  "M4 Method 2 recovered: 148 suggestions (vs 214 expected)"
  → Continue normally

Hard failure (all retries exhausted):
  ✗ [red] "M6 Clustering: all retries failed. Ollama not responding."
  [red] "PIPELINE PAUSED: 6/9 engines complete. 1 critical failure."
  [amber] "Partial results saved to job_id: abc123"
  
  Options shown to user:
  [Fix & Resume from M6] ← saves all completed engine outputs
  [See full error log]
  [Start fresh from M1]

Resume from step:
  User fixes Ollama → clicks "Resume from M6 Clustering"
  → Console shows: "Resuming from M6. Loading M1-M5 outputs from cache..."
  → Only M6, M7, M8, M9 re-run
  → Does NOT re-crawl, does NOT re-expand keywords
```

**Data inspection (click any engine row):**
```
Click [M4 Expansion ✓] → expands to show:
  Method 1 (PAA):          18 keywords  [View all]
  Method 2 (Alphabet):    148 keywords  [View all]
  Method 3 (Preposition):  48 keywords  [View all]
  Method 4 (Qualifier):   126 keywords  [View all]
  Method 5 (Utility):      24 keywords  [View all]
  Method 6 (Competitor):   89 keywords  [View all]
  Method 7 (Forum):        31 keywords  [View all]
  Method 8 (Info gaps):    14 keywords  [View all] ← most valuable
  Gemini expansion:        +67 keywords  [View all]
  Total before dedup:     564 keywords
  
  [Mark this engine output as bad] → flags for manual review + reruns this engine only
```

---

## P3: KEYWORD UNIVERSE EXPLORER

### D3.js Tree Controls
```
Every node has a context menu (right-click or ⋯):

Universe node:
  [Add pillar manually]
  [Rerun universe pipeline]
  [View Wikipedia research]
  [Mark universe complete]

Pillar node:
  [Edit name]
  [Set product page URL]
  [Generate content brief]
  [Add cluster manually]
  [Rerun pillar expansion]
  [Remove pillar] → shows impact dialog

Cluster node:
  [Edit name]
  [Merge with cluster...]
  [Split cluster]
  [Expand (generate 20 more)]
  [Add keyword manually]
  [Remove cluster] → moves keywords to "Unclustered"

Keyword node:
  [Edit text]
  [Change intent tag]
  [Mark priority ★]
  [Approve ✓]
  [Reject ✗]
  [Request replacement]
  [Move to cluster...]
  [Generate blog now]
  [Remove]
```

### Bulk Keyword Review Mode
```
Toggle: [Tree view] [Table view] [Review mode]

Review mode — keyboard shortcuts:
  A = approve          R = reject
  P = mark priority    S = skip
  E = edit             B = move to different cluster

Table columns:
  # | Keyword | KD | Vol | Intent | Score | Status | Action
  1 | black pepper health benefits | 35 | 18k | info | 5.9 | [A] [R] [E]
  2 | buy organic black pepper     |  7 | 2.2k| tran | 8.4 | [A] [R] [E]
  ...

Batch actions:
  [Approve all quick wins (KD<10)]
  [Reject all KD>70]
  [Remove all rejected]
  [Export to CSV]
```

---

## P4: CONTENT CREATION STRATEGY (NEW MODULE)

**When:** After all keywords approved. Before any blog is written.
**Purpose:** Define HOW content will be created, not what content.

### Module sections

#### 4.1 Pillar-by-Pillar Content Plan
```
Pillar: Black Pepper Health Benefits
├── Articles planned: 12
├── Content type mix: 7 blog · 3 FAQ · 2 guide
├── Languages: English (8) · Malayalam (3) · Hindi (1)
├── Personas targeted:
│   ├── Health-conscious home cook → 5 articles
│   ├── Ayurveda practitioner → 4 articles
│   └── General buyer → 3 articles
├── Religion context:
│   ├── Hindu (Ayurveda angle): 4 articles
│   ├── Muslim (Unani angle): 2 articles
│   └── General: 6 articles
├── Week 1 priority: "Does black pepper affect drug absorption?" (KD 4)
└── [Edit plan] [Approve this pillar]
```

#### 4.2 Content Angle Matrix
```
Same keyword → different angle per persona:

"black pepper health benefits"
├── For home cook:      Practical cooking benefits + recipe angle
├── For Ayurveda buyer: Trikatu, piperine bioavailability, traditional uses
├── For export buyer:   Piperine % data, certified content, lab reports
└── For Christian baker: Cinnamon + black pepper in Christmas baking
→ DECISION: Which article runs first? Which audience is primary?
   [Health-conscious home cook ▾] as primary angle
```

#### 4.3 Internal Link Architecture Preview
```
Visual map (before any content is written):

black pepper pillar page
  ← linked from: "buy organic black pepper" (transactional)
  ← linked from: "black pepper vs white pepper" (comparison)
  → links to:    product page /products/black-pepper
  → links to:    cardamom pillar (related spice)
  
[Edit any link] [Add link] [Remove link]
[Validate: no orphans detected ✓] [Validate: no circular links ✓]
```

#### 4.4 Publication Sequence Plan
```
Week 1: (info gaps first — fastest to rank)
  1. "Does black pepper affect drug absorption?" (KD 4, gap)
  2. "Christmas cake cinnamon powder Kerala" (KD 3, Christian×Dec)
  3. "Malabar chicken masala halal recipe" (KD 2, Muslim×Malabar)

Week 2: (quick wins)
  4. "buy organic black pepper Kerala" (KD 7, transactional)
  5. "black pepper 2 day itinerary" [ERROR: wrong pillar example]

[Drag to reorder] — system warns if dependency broken
[Approve sequence] → locks in order for content calendar
```

#### 4.5 Seasonal Pre-scheduling
```
December (Christmas peak):
  Must be live by: November 15
  Content creation must start: October 20
  Articles needing early scheduling:
    - "Christmas cake cinnamon powder Kerala" → October 22 generation
    - "Kerala plum cake spice list" → October 24
    - "Christmas baking spice kit" → October 26

[Auto-schedule seasonal articles] → calendar auto-fills with constraints
```

#### Approval gate
```
Before generation:
  ✓ 8 pillar plans reviewed
  ✓ Content angle matrix approved
  ✓ Internal link map validated
  ✓ Publication sequence approved
  ✓ Seasonal constraints set

[Begin Content Generation]
→ triggers M5 Content Engine
→ console shows blog generation progress
→ each generated blog appears in P6 Blog Editor for review
```

---

## P5: CONTENT CALENDAR

### 12-Month Grid
```
         Jan  Feb  Mar  Apr  May  Jun  Jul  Aug  Sep  Oct  Nov  Dec
Hlth Ben  [8✓] [8✓] [6→] [0□] [0□] [0□] [0□] [0□] [0□] [0□] [0□] [0□]
Cooking   [6✓] [4✓] [8→] [0□] [0□] [0□] [0□] [0□] [0□] [0□] [0□] [0□]
Ayurveda  [4✓] [3✓] [5→] [0□] ...
Buying    [5✓] [4✓] [6→] ...
Christmas [0□] [0□] [0□] [0□] [0□] [0□] [0□] [0□] [0□] [6□] [8□] [10□]

Legend: ✓=published  →=frozen/scheduled  □=planned
Color:  green=published  blue=frozen  amber=draft  gray=empty

Click any cell: shows list of articles in that pillar-month
Drag article: reschedule to different month
Bulk actions: [Freeze all drafts] [Publish all scheduled]
```

---

## P6: BLOG EDITOR

### Editor Layout
```
┌─ Top bar ─────────────────────────────────────────────────────────┐
│ "Does black pepper affect drug absorption?" | [Draft] | [Actions▾] │
│ Target: "black pepper drug absorption" | KD 4 | Est. rank: top 3   │
└───────────────────────────────────────────────────────────────────┘

┌─ Left: Content ──────────────────────┐ ┌─ Right: Sidebar ─────────┐
│ [Preview] [Edit] [Source]             │ │ Keyword details          │
│                                       │ │ Intent: informational    │
│ [H1] Does Black Pepper Affect Drug    │ │ Volume: ~800/mo          │
│      Absorption? The Full Answer      │ │ KD: 4 (easy win)         │
│                                       │ │ Score: 9.1/10            │
│ [Meta] "Learn how piperine in black   │ │                          │
│  pepper affects medication..."        │ │ Internal links           │
│                                       │ │ Links TO: 3 pages        │
│ [Body] Article content here...        │ │ Links FROM: 0 (publish   │
│        2,156 words | 18 FAQ | Grade A │ │ first, then link back)  │
│                                       │ │                          │
│                                       │ │ Schema: FAQPage          │
│                                       │ │ Language: English        │
│                                       │ │ Pillar: Health Benefits  │
└───────────────────────────────────────┘ └──────────────────────────┘

┌─ Bottom action bar ────────────────────────────────────────────────┐
│ [Regenerate with new angle] [Mark as failure ✗] [Request edits]    │
│                                              [Schedule] [Freeze ❄] │
└────────────────────────────────────────────────────────────────────┘
```

### Mark as Failure Flow
```
User clicks [Mark as failure ✗]

Dialog:
  Why is this content wrong?
  ○ Factually incorrect
  ○ Wrong persona/angle
  ○ Too generic — needs more specific examples
  ○ Wrong language/tone
  ○ Keyword used incorrectly
  ○ Other: [______________]
  
  [Cancel] [Mark failed + Regenerate]
  
→ Status: failed
→ Goes back to content queue
→ Claude regenerates with different angle (informed by failure reason)
→ Notification: "New version of [article] ready for review"
→ Version history keeps both versions
```

---

## CONSOLE LOG SPECIFICATION (Backend)

### Log Format
```python
@dataclass
class ConsoleLog:
    timestamp:    str    # "09:14:02"
    engine:       str    # "M4", "Claude", "Ruflo"
    level:        str    # "info", "success", "warning", "error", "data", "handoff"
    message:      str
    data:         dict   # optional structured data
    duration_ms:  int    # for completed steps
    
# Color mapping (frontend)
COLORS = {
    "success":  "#5DCAA5",
    "data":     "#85B7EB",
    "info":     "#FAC775",
    "warning":  "#EF9F27",
    "error":    "#F09595",
    "critical": "#E24B4A",
    "handoff":  "#888780",
    "claude":   "#CECBF6",
}
```

### SSE (Server-Sent Events) stream
```python
# Backend: stream console logs to frontend in real-time
@app.get("/api/jobs/{job_id}/console")
async def console_stream(job_id: str):
    async def generator():
        async for log in get_log_stream(job_id):
            yield f"data: {log.json()}\n\n"
    return StreamingResponse(generator(), media_type="text/event-stream")

# Frontend: React hook
function useConsole(jobId) {
  useEffect(() => {
    const es = new EventSource(`/api/jobs/${jobId}/console`);
    es.onmessage = (e) => {
      const log = JSON.parse(e.data);
      setLogs(prev => [...prev, log]);
    };
    return () => es.close();
  }, [jobId]);
}
```

### Engine data handoff visibility
```python
# Every engine must log its output before passing to next
def log_handoff(engine_from: str, engine_to: str, data_summary: dict):
    log(level="handoff", message=f"[{engine_from} →→→ {engine_to}]",
        data=data_summary)
    
# Example:
log_handoff("M4 Expansion", "M5 Dedup", {
    "keywords_passed": 564,
    "methods_used": 8,
    "gemini_calls": 7,
    "info_gaps_found": 14,
    "utility_keywords": 24
})
```

---

## CONTENT CREATION STRATEGY ENGINE (Backend)

**File:** `backend/engines/content_strategy_engine.py`

```python
class ContentStrategyEngine:
    """
    Runs AFTER keywords are approved.
    Runs BEFORE any blog is generated.
    
    Produces per-pillar content plans with:
    - Article count and type mix
    - Language distribution
    - Persona-angle mapping
    - Internal link architecture
    - Publication sequence
    - Seasonal pre-scheduling
    """
    
    def build_pillar_plan(self, pillar: Pillar, keywords: List[Keyword],
                           personas: List[Persona], user_input: UserInput,
                           strategy: StrategyOutput) -> PillarContentPlan:
        """
        For one pillar: decide article types, angles, languages.
        Uses DeepSeek for decisions (local, free).
        """
        
    def build_link_architecture(self, all_pillars: List[Pillar],
                                  strategy: StrategyOutput) -> LinkMap:
        """Preview full internal link map before any content is written."""
        
    def build_publication_sequence(self, plans: List[PillarContentPlan],
                                    seasonal_events: List[str]) -> List[ScheduledArticle]:
        """
        Order all articles considering:
        - Info gaps first (fastest to rank)
        - Quick wins before hard keywords
        - Seasonal articles pre-scheduled 6 weeks before event
        - Dependencies (article A must publish before article B links to it)
        """
        
    def validate_sequence(self, sequence: List[ScheduledArticle]) -> List[str]:
        """Check for: circular links, dependency violations, orphan articles."""
```

---

## FLEXIBILITY SYSTEM — RERUN SCOPE MATRIX

```python
RERUN_SCOPE = {
    "add_product":      ["M3_universe", "M4_expansion", "M6_cluster", "M7_score"],
    "add_religion":     ["M2_context"],
    "add_location":     ["M2_context"],
    "add_language":     ["M2_context", "language_expansion"],
    "add_competitor":   ["M1_competitor_crawl", "gap_analysis"],
    "remove_product":   [],  # just delete, no rerun
    "remove_religion":  [],  # mark keywords, user confirms
    "change_usp":       ["M2_strategy"],
    "add_pillar":       ["M3_for_pillar", "M4_for_pillar", "M6", "M7"],
    "remove_pillar":    [],  # impact dialog, then delete
    "mark_kw_failed":   [],  # replacement suggestion only
    "mark_blog_failed": ["M5_single_blog"],  # regenerate one blog
    "rank_drops":       ["M8_diagnosis", "M5_update_blog"],
}

def get_rerun_scope(change_type: str, affected_items: list) -> list:
    """Returns minimal set of engines to rerun for any change."""
    engines = RERUN_SCOPE.get(change_type, [])
    return [e for e in engines if e not in SKIP_IF_MANUAL]
```

---

## DATABASE ADDITIONS FOR NEW FEATURES

```sql
-- Console logs (streamed to frontend via SSE)
console_logs (
  id, job_id, engine, level, message, data JSON,
  duration_ms, created_at
)

-- Content creation strategy
content_plans (
  id, project_id, pillar_id, article_count, type_mix JSON,
  language_distribution JSON, persona_angles JSON,
  approved_at, created_at
)

publication_sequence (
  id, project_id, position, keyword_id, pillar_id,
  content_type, language, scheduled_date,
  depends_on_id, seasonal_event, status
)

-- Blog failure tracking
blog_failures (
  id, blog_id, reason, reason_category, marked_by,
  marked_at, replacement_blog_id
)

-- Keyword failure tracking
keyword_failures (
  id, keyword_id, reason, alternatives JSON,
  replacement_id, marked_at
)

-- Engine output snapshots (for debugging)
engine_snapshots (
  id, job_id, engine, output_summary JSON,
  output_sample JSON, created_at
)
```

---

## WHAT'S BUILT / WHAT'S NEXT

### Built (5,893 lines across 4 files)
- Ruflo v3 orchestrator + keyword universe pipeline
- Supporting keyword engine (8 methods + info gaps + GEO)
- Final strategy engine (Claude CoT synthesis)
- Strategy development engine (audience chains + context)

### Next build priority
1. **Console streaming (SSE)** — critical, users need this
2. **FastAPI routers** — wire all engines to API
3. **SQLAlchemy models** — complete schema
4. **Content Strategy Engine** — P4 module (new)
5. **Content Engine** — Claude blog writer
6. **Content Store & Freeze** — lifecycle management
7. **GSC Monitor** — ranking intelligence
8. **Frontend: Keyword Tree (D3.js)** — with edit controls
9. **Frontend: Console output UI** — SSE consumer
10. **Frontend: Content Calendar** — 12-month grid
11. **Blog Editor** — with failure/approve flow
12. **Rankings page** — charts + alerts

*Last updated: March 2026*

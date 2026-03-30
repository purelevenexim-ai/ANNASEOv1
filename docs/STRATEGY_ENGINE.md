# AnnaSEO — Strategy Engine

Two complementary engines produce the content and ranking strategy for each project.

---

## Engine 1: StrategyDevelopmentEngine (ruflo_strategy_dev_engine.py)

**Purpose:** Audience × Location × Religion × Language cross-product strategy. No Claude required — runs locally using rule-based persona synthesis and context clustering.

### Input: `UserInput` dataclass

```python
UserInput(
    seed_keyword   = "black pepper",
    industry       = Industry.FOOD_SPICES,
    target_geos    = [GeoLevel.KERALA, GeoLevel.SOUTH_INDIA],
    target_religions = [Religion.HINDU, Religion.GENERAL],
    languages      = [Language.ENGLISH, Language.MALAYALAM],
    business_type  = "B2C",
    usp            = "Kerala forest-harvested, stone-ground",
    products       = ["black pepper powder", "whole pepper"],
    customer_reviews = "...",
    competitor_urls = ["https://competitor.com"],
    seasonal_events = ["Onam", "Christmas"],
)
```

### Enums

| Enum | Values |
|------|--------|
| `Industry` | FOOD_SPICES, TOURISM, HEALTHCARE, ECOMMERCE, AGRICULTURE, EDUCATION, GENERAL, ... |
| `GeoLevel` | GLOBAL, INDIA, SOUTH_INDIA, KERALA, MALABAR, WAYANAD, KOCHI, KOZHIKODE, NATIONAL, ... |
| `Religion` | HINDU, MUSLIM, CHRISTIAN, GENERAL, ALL |
| `Language` | ENGLISH, MALAYALAM, HINDI, TAMIL, KANNADA, TELUGU, ARABIC |

### Output: `StrategyOutput` dataclass (partial)

```python
StrategyOutput(
    persona_chains        = [...],   # list of persona × journey objects
    context_clusters      = [...],   # Religion × Location × Language triples
    priority_queue        = [...],   # 12-week ordered content list
    content_briefs        = {...},   # keyword → brief dict
    internal_link_map     = {...},   # pillar → supporting URLs
    seasonal_calendar     = {...},   # month → events + keywords
    landscape_analysis    = {...},   # easy_wins, avoid, guaranteed_top
    risks                 = [...],   # risk factors with mitigation
    confidence            = 0.87,
)
```

### API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/strategy/{project_id}/develop` | Trigger strategy job (BackgroundTask) |
| GET  | `/api/strategy/{project_id}/jobs/{job_id}` | Poll job status |
| GET  | `/api/strategy/{project_id}/sessions` | List all sessions |
| GET  | `/api/strategy/{project_id}/sessions/{session_id}` | Full session result |
| GET  | `/api/strategy/{project_id}/latest` | Most recent session |
| GET  | `/api/strategy/{project_id}/audience` | Get saved audience profile |
| PUT  | `/api/strategy/{project_id}/audience` | Save audience profile |
| GET  | `/api/strategy/{project_id}/priority-queue` | Ordered 12-week content list |
| GET  | `/api/strategy/{project_id}/content-briefs` | keyword → brief map |
| GET  | `/api/strategy/{project_id}/link-map` | Internal link architecture |
| GET  | `/api/strategy/{project_id}/predictions` | 12-month rank predictions |
| GET  | `/api/strategy/{project_id}/risks` | Risk factors |

### Cost
Free — no AI API calls. Runs entirely locally with rule-based synthesis.

---

## Engine 2: FinalStrategyEngine (ruflo_final_strategy_engine.py)

**Purpose:** Claude Sonnet CoT (chain-of-thought) reasoning over the keyword universe result to produce a validated, prioritised strategy with confidence scoring and DeepSeek cross-validation.

### Input

```python
FinalStrategyEngine().run(
    universe_result = {...},   # dict from latest keyword pipeline run
    project         = {...},   # project row from DB
)
```

### Output

Returns a `StrategyOutput` (same shape as above) with additional fields:
- `claude_reasoning` — full chain-of-thought text
- `deepseek_validation_score` — 0–1 cross-validation from local DeepSeek
- `tokens_used` — total input + output tokens consumed

### API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/strategy/{project_id}/final` | Trigger FinalStrategyEngine as BackgroundTask |
| POST | `/api/strategy/{project_id}/diagnose` | RankingMonitor.diagnose_drop() for one keyword |

### Cost
~$0.04–0.12 per strategy run (Claude Sonnet input + output tokens).

---

## RankingMonitor (ruflo_final_strategy_engine.py)

Diagnoses ranking drops using Claude Sonnet.

### Usage (API)

```
POST /api/strategy/{project_id}/diagnose
Body: { "keyword": "black pepper price", "current_rank": 18, "previous_rank": 4 }
```

### Diagnosis output shape

```json
{
  "root_cause": "Competitor published a more comprehensive comparison page",
  "fixes": [
    {
      "action": "Add price comparison table",
      "instruction": "Include current market prices from 3 competitors",
      "priority": "high",
      "expected_impact": "Recover to top 5 within 6 weeks"
    }
  ],
  "estimated_recovery_weeks": 6
}
```

---

## Job Lifecycle

```
POST /develop  →  _strategy_jobs[job_id] = {status: "running"}
                  BackgroundTask → _run_strategy_job()
                  StrategyDevelopmentEngine.run(UserInput)
                  → saves result to strategy_sessions table
                  → _strategy_jobs[job_id] = {status: "completed", result: ...}

GET /jobs/{id} →  returns _strategy_jobs[job_id]
                  Frontend polls every 3-4s until status != "running"
```

---

## Frontend: StrategyPage.jsx

4-tab interface at `/strategy` in the nav.

| Tab | Purpose |
|-----|---------|
| Audience Setup | Form: locations, religions, languages, business_type, USP, products, reviews |
| Run Strategy | Trigger dev/final engine; live job progress; session history |
| Strategy Results | Landscape, predictions, risks, link map, persona chains, context clusters |
| Priority Queue | 12-week article table; "Generate Blog" per row; import to calendar |

# Strategy Engine — Complete Reference

**Last Updated:** April 3, 2026  
**Backend:** `main.py` (inline strategy generation in `/api/ki/{project_id}/post-pipeline-strategy`)  
**Frontend:** `frontend/src/workflow/Step4Strategy.jsx`

---

## Overview

The strategy system takes pipeline output (P1-P14 results) and generates an AI-powered SEO/AEO strategy. It runs as Step 4 in the KeywordWorkflow after pipeline execution (Step 3).

### Current Architecture

```
Step 3 (Pipeline P1-P14) completes
    ↓
Step 4: POST /api/ki/{project_id}/post-pipeline-strategy (SSE)
    ↓
1. Load project profile from DB (business_type, USP, personas, competitors)
2. Load ALL completed run results from run_events table
3. Extract phase summaries: P7 top keywords, P8 topics, P9 clusters, P10 pillars, P13 calendar
4. Build prompt with real pipeline data
5. AI cascade: Ollama → Groq → Rule-based fallback
6. Stream progress via SSE
7. Save to keyword_input_sessions.strategy_json
    ↓
Frontend displays in 5 tabs (read-only)
```

---

## Strategy Output Format

```json
{
  "executive_summary": "High-level strategy overview",
  "content_strategy": {
    "pillar_plan": [
      {
        "pillar": "Pillar Name",
        "priority": "high|medium|low",
        "content_types": ["blog", "guide", "comparison"],
        "target_intent": "informational|transactional|commercial",
        "estimated_articles": 15,
        "quick_wins": ["keyword1", "keyword2"]
      }
    ],
    "content_calendar_strategy": "Monthly publishing cadence details",
    "content_mix": {
      "informational": 40,
      "commercial": 30,
      "transactional": 20,
      "navigational": 10
    }
  },
  "seo_recommendations": [
    {
      "area": "Content depth",
      "priority": "high",
      "action": "Create comprehensive guides for pillar topics",
      "impact": "Improved topical authority"
    }
  ],
  "aeo_strategy": {
    "ai_visibility_targets": ["pillar1", "pillar2"],
    "structured_data_plan": ["Article", "BlogPosting"],
    "featured_snippet_targets": ["query1", "query2"]
  },
  "competitor_gaps": ["gap1", "gap2"],
  "90_day_plan": [
    {
      "month": 1,
      "focus": "Foundation",
      "deliverables": ["Pillar pages", "Technical SEO audit"]
    }
  ]
}
```

---

## Frontend UI (Step4Strategy.jsx)

### Sub-Steps
1. **GenerateSubStep** — Shows pipeline summary + Generate button + live console
2. **ReviewSubStep** — 5-tab read-only display of strategy

### Review Tabs
| Tab | Content |
|-----|---------|
| **Overview** | Executive summary, content mix % breakdown, calendar strategy |
| **Pillars** | Per-pillar cards: priority, content types, intent, article count, quick wins |
| **SEO** | Recommendation cards: area, priority, action, impact. Competitor gaps list |
| **AEO** | AI visibility targets, structured data plan, featured snippet targets |
| **90-Day Plan** | Monthly cards: focus area, deliverables list |

---

## AI Cascade

| Priority | Provider | Model | Timeout | Cost |
|----------|----------|-------|---------|------|
| 1 | Ollama (local) | qwen2.5:3b | 180s | Free |
| 2 | Groq | llama-3.1-8b-instant | 30s | Free tier |
| 3 | Rule-based | — | — | Free |

Rule-based fallback generates a structured JSON from pipeline data without AI interpretation.

---

## What Data Reaches the Strategy Prompt

From completed pipeline runs, the backend extracts:

| Source | What's Extracted | Truncation |
|--------|-----------------|------------|
| Project profile | business_type, USP, locations, personas | Full |
| P7 result_summary | top_5_keywords, avg_score | 5 keywords only |
| P8 result_summary | topic_count, first 20 topic names | 20 topics only |
| P9 result_summary | cluster_count, first 20 cluster names | 20 clusters only |
| P10 result_summary | pillar names + cluster/keyword counts | 20 pillars only |
| P13 result_summary | calendar_entries count, date range | Count only |

**⚠️ Problem:** The AI only sees summaries (counts + first 20 items), not the full dataset. For a 300-keyword universe with 80 topics and 27 clusters, the AI sees truncated data.

---

## Known Issues

### Critical
1. **Strategy is READ-ONLY** — no edit after generation
2. **No re-generate button** — must go back to Step 3 and re-enter Step 4
3. **No live data during generation** — only log lines, no intermediate results
4. **Truncated context** — AI sees summaries, not full pipeline data
5. **Step 1 business data not fully used** — competitor_urls collected but never analyzed

### Design Gaps
6. **No strategy editing UI** — can't modify pillar priorities, content mix, or 90-day plan
7. **No strategy re-run** — can't regenerate with modified parameters
8. **No strategy comparison** — can't compare two strategy versions
9. **No strategy-to-pipeline feedback** — strategy insights don't flow back to reorder/reprioritize pipeline output
10. **No per-pillar strategy detail** — strategy covers all pillars uniformly

### Data Flow Gaps
11. **Step 1 → Strategy disconnect** — business_intent, customer_url, competitor_urls stored but not analyzed for business discovery (Module 2) or competitor intelligence (Module 3)
12. **No P7++ scoring** — simple 3-source scoring vs documented 6-factor formula (BusinessFit, IntentValue, RankingFeasibility, TrafficPotential, CompetitorGap, ContentEase)
13. **Strategy doesn't influence P13 calendar** — content_mix percentages generated but not applied to scheduling

---

## Separate Strategy Engines (Not in Main Workflow)

Two additional engines exist but are NOT integrated into the Step 4 workflow:

### StrategyDevelopmentEngine
- **Endpoint:** `/api/strategy/{project_id}/develop`
- **Purpose:** Audience × location × language cross-product analysis
- **Features:** Persona synthesis, priority queue, 12-week calendar
- **Status:** Standalone tool (StrategyPage.jsx), not in KeywordWorkflow

### FinalStrategyEngine
- **Endpoint:** `/api/strategy/{project_id}/final`
- **Purpose:** Claude CoT reasoning over keyword universe
- **Features:** Deep keyword prioritization, confidence scoring
- **Status:** Available but not called from Step 4

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `keyword_input_sessions` | Stores strategy_json in column (Step 4 output) |
| `strategy_sessions` | Separate strategy results (StrategyDevelopmentEngine) |
| `strategy_jobs` | Job tracking for develop/final engines (NOT used by Step 4) |
| `run_events` | Phase-by-phase logs read by strategy generator |
| `runs` | Pipeline run results read by strategy generator |

---

## Files

| File | Purpose |
|------|---------|
| `main.py` | `ki_post_pipeline_strategy()` endpoint — inline strategy generation |
| `frontend/src/workflow/Step4Strategy.jsx` | Strategy UI: generate + review tabs |
| `engines/ruflo_strategy_engine.py` | StrategyDevelopmentEngine (standalone) |
| `engines/ruflo_final_strategy_engine.py` | FinalStrategyEngine (standalone) |

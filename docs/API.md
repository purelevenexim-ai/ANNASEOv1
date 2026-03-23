# AnnaSEO — API Reference

**Base URL:** `http://localhost:8000`  
**Auth:** JWT (to be implemented in Week 1)  
**Format:** JSON everywhere

---

## Projects

```
POST   /api/projects                          Create project
GET    /api/projects                          List all projects
GET    /api/projects/{id}                     Get project details
PUT    /api/projects/{id}                     Update project settings
DELETE /api/projects/{id}                     Delete project
```

---

## Keyword Universe (20-Phase Engine)

```
POST   /api/projects/{id}/run-keyword-universe    Start full run (SSE stream)
GET    /api/projects/{id}/universes               List keyword universes
GET    /api/projects/{id}/pillars                 List all pillars
GET    /api/projects/{id}/clusters                List all clusters
GET    /api/projects/{id}/keywords                List all keywords
GET    /api/projects/{id}/keywords?intent=transactional
GET    /api/projects/{id}/knowledge-graph         Get KG hierarchy
POST   /api/projects/{id}/confirm-gate/{gate}     Confirm one of 5 gates
```

---

## Content

```
POST   /api/projects/{id}/generate-content        Generate article for keyword
GET    /api/projects/{id}/content                 List all articles
GET    /api/projects/{id}/content/{blog_id}       Get article + scores
PUT    /api/projects/{id}/content/{blog_id}       Update article
POST   /api/projects/{id}/content/{blog_id}/approve   Approve for publishing
POST   /api/projects/{id}/content/{blog_id}/freeze    Freeze (lock) article
POST   /api/projects/{id}/calendar                Generate content calendar
GET    /api/projects/{id}/calendar                Get publishing schedule
```

---

## Publishing

```
POST   /api/projects/{id}/publish/{blog_id}       Publish one article
GET    /api/projects/{id}/publish/queue           Get publish queue
POST   /api/projects/{id}/publish/run-batch       Process next N in queue
GET    /api/projects/{id}/publish/history         Published articles
```

---

## SEO Audit

```
POST   /api/projects/{id}/audit                   Run full site audit
POST   /api/projects/{id}/audit/page              Audit one page
GET    /api/projects/{id}/audit/latest            Latest audit report
GET    /api/projects/{id}/audit/history           Audit history
POST   /api/projects/{id}/audit/generate-llmstxt  Generate llms.txt
```

---

## Rankings

```
GET    /api/projects/{id}/rankings                Current positions
GET    /api/projects/{id}/rankings/history        Position history
GET    /api/projects/{id}/rankings/alerts         Ranking drops/gains
POST   /api/projects/{id}/rankings/import-gsc     Import from GSC
```

---

## Quality Intelligence (QI Engine — port 8006)

```
GET    /api/qi/dashboard                          Full dashboard state
GET    /api/qi/dashboard?project_id=proj_001      Project-specific dashboard
POST   /api/qi/runs/{project_id}                  Start a new run
POST   /api/qi/score/{run_id}                     Score all items from run
GET    /api/qi/review-queue                       Items needing review
GET    /api/qi/review-queue?project_id=proj_001
POST   /api/qi/feedback                           Submit user feedback
  body: {output_id, project_id, label, reason, fix_hint}
POST   /api/qi/feedback/batch                     Batch feedback
GET    /api/qi/phases                             Phase health report
GET    /api/qi/degradation                        Degradation events
POST   /api/qi/tunings/from-event/{event_id}      Generate tuning from event
GET    /api/qi/tunings                            List tunings
GET    /api/qi/tunings?status=pending
POST   /api/qi/tunings/{id}/approve              MANUAL APPROVAL — apply to engine
POST   /api/qi/tunings/{id}/reject
POST   /api/qi/tunings/{id}/rollback
GET    /api/qi/anatomy                            ENGINE_ANATOMY map
POST   /api/qi/record                            Record phase output (called by engines)
```

---

## Domain Context (port 8007)

```
POST   /api/dc/projects/{project_id}/setup        Setup project domain profile
GET    /api/dc/projects/{project_id}              Get profile
POST   /api/dc/classify                           Classify keywords for project
  body: {keywords: [...], project_id: "proj_001"}
POST   /api/dc/validate-pillars/{project_id}       Validate P10 output
POST   /api/dc/feedback                           Submit domain feedback → creates tuning
  body: {project_id, keyword, verdict, reason, industry}
GET    /api/dc/tunings/project/{project_id}        Project-scope tunings
GET    /api/dc/tunings/global                      Global-scope tunings
GET    /api/dc/scope-rules                         Tuning scope decision table
GET    /api/dc/cross-domain-vocabulary             Full cross-domain word map
```

---

## RSD Engine — Code Quality (port 8004)

```
GET    /api/rsd/health                            All engines health dashboard
POST   /api/rsd/scan/all                          Scan all engines (background)
POST   /api/rsd/scan/{engine_name}                Scan one engine
GET    /api/rsd/approvals                         Pending approval requests
GET    /api/rsd/approvals/{request_id}            Get one approval
POST   /api/rsd/approvals/{request_id}/approve    MANUAL APPROVAL — push to prod
POST   /api/rsd/approvals/{request_id}/reject     Reject change
POST   /api/rsd/rollback/{engine_name}            Rollback engine
  body: {target_version: "previous"|"1.2.3", rolled_back_by: "admin"}
GET    /api/rsd/changelog                         Full change log
GET    /api/rsd/versions/{engine_name}            Version list for rollback
GET    /api/rsd/diff/{engine_name}                Unified diff between versions
POST   /api/rsd/metrics/{engine_name}/run         Record engine run metrics
```

---

## Self Development — Intelligence (port 8005)

```
GET    /api/sd/dashboard                          Full self-dev state
POST   /api/sd/crawl/all                          Crawl all 40+ sources
POST   /api/sd/crawl/{category}                   Crawl one category
POST   /api/sd/analyse                            Process items → gaps
GET    /api/sd/gaps                               Knowledge gaps
GET    /api/sd/gaps?status=pending&priority=high
POST   /api/sd/gaps/{gap_id}/implement            Implement one gap
GET    /api/sd/implementations                    All implementations
GET    /api/sd/implementations?status=pending
POST   /api/sd/implementations/{id}/approve       MANUAL APPROVAL — deploy
POST   /api/sd/implementations/{id}/reject
POST   /api/sd/implementations/{id}/rollback
POST   /api/sd/user-content                       Add user content for review
  body: {title, content, content_type, engines_affected, notes}
POST   /api/sd/user-content/{id}/analyse          Analyse submission
GET    /api/sd/user-content                       List submissions
POST   /api/sd/sources                            Add custom crawl source
GET    /api/sd/sources                            List all sources
GET    /api/sd/intelligence                       Latest intelligence items
```

---

## Data Store (deprecated — use QI Engine instead)

```
POST   /api/ds/record                            Record engine result
GET    /api/ds/records                           List records
GET    /api/ds/items                             List items
GET    /api/ds/stats                             Summary statistics
```

---

## SSE (Server-Sent Events)

Long-running jobs stream progress via SSE:

```
GET    /api/projects/{id}/run-keyword-universe/stream
GET    /api/sd/crawl/stream
GET    /api/rsd/scan/stream
```

Event format:
```json
{"type": "phase_start", "phase": "P2_KeywordExpansion", "timestamp": "..."}
{"type": "phase_log",   "phase": "P2_KeywordExpansion", "level": "data", "msg": "340 keywords fetched"}
{"type": "phase_end",   "phase": "P2_KeywordExpansion", "duration_ms": 1240}
{"type": "gate",        "gate": "G1_Universe", "requires_approval": true}
{"type": "complete",    "summary": {...}}
{"type": "error",       "phase": "P6", "error": "SERP rate limit hit"}
```

---

## Request/Response Examples

### Start keyword universe run
```http
POST /api/projects/proj_001/run-keyword-universe
{
  "seed": "cinnamon",
  "language": "english",
  "region": "kerala",
  "pace": "standard"
}

Response:
{
  "run_id": "run_abc123",
  "status": "started",
  "stream_url": "/api/projects/proj_001/run-keyword-universe/stream?run_id=run_abc123"
}
```

### Submit QI feedback
```http
POST /api/qi/feedback
{
  "output_id": "out_a1b2c3",
  "project_id": "proj_001",
  "label": "bad",
  "reason": "Tour has nothing to do with spices — tourism keyword",
  "fix_hint": "Remove tour-related words from this business's keyword universe"
}

Response:
{
  "feedback_id": "fb_x1y2z3",
  "label": "bad",
  "attribution": {
    "event_id": "dg_abc123",
    "tuning_id": "tune_xyz789",
    "degradation_at": "OffTopicFilter",
    "degradation_fn": "GLOBAL_KILL",
    "engine_file": "annaseo_addons.py",
    "fix_type": "filter",
    "fix": "Add tour, travel, trip, tourism to project reject_overrides"
  },
  "message": "Tuning generated. Review in QI dashboard."
}
```

### Classify keywords for project
```http
POST /api/dc/classify
{
  "keywords": ["cinnamon tour", "ceylon cinnamon", "buy cinnamon online"],
  "project_id": "proj_spice_001"
}

Response:
{
  "cinnamon tour": {
    "verdict": "reject",
    "score": 5.0,
    "reason": "Project cross-domain rule: 'tour' = reject for food_spices",
    "is_cross_domain": true
  },
  "ceylon cinnamon": {
    "verdict": "accept",
    "score": 95.0,
    "reason": "Explicit accept override: 'ceylon'",
    "is_cross_domain": true
  },
  "buy cinnamon online": {
    "verdict": "accept",
    "score": 80.0,
    "reason": "Domain relevance score 80/100 — accepted",
    "is_cross_domain": false
  }
}
```

# Research & Self Development — Global vs Project

## Two Separate Systems

AnnaSEO has two distinct R&D systems that work at different levels.

---

## Global RSD

**File:** `annaseo_rsd_engine.py`  
**Port:** 8004  
**Scope:** ALL projects, all engines  
**Manages:** Code quality, engine health, algorithm correctness

### What It Monitors

Every engine that runs is measured on 8 dimensions:

| Dimension | Weight | Meaning |
|-----------|--------|---------|
| Output quality | 30% | Are outputs semantically correct? |
| Execution time | 15% | p95 latency vs 30s target |
| Memory usage | 15% | Peak MB vs 512MB target |
| Error rate | 15% | Failure rate per 24h window |
| Output completeness | 10% | Are required fields present? |
| Consistency | 10% | Same input → same structure? |
| API cost | 3% | Tokens per quality point |
| Test coverage | 2% | % code paths with tests |

### What It Tunes

When an engine scores below 85:
1. **Gemini** analyses the health report and source code → writes fix spec
2. **Groq** generates test cases for the fix
3. **DeepSeek** writes the actual code change
4. **Claude** verifies — quality, safety, no regressions
5. Human reviews diff + Claude notes → **manual approval**
6. On approval → code deployed, snapshot saved, rollback available

### Scheduled Jobs

```
Daily 8:00 UTC   → scan all 10 engines
Weekly Sunday    → deep scan with test coverage check
On demand        → triggered by anomaly detection
```

### Never Touches

- Per-project keyword kill lists
- Project brand configuration
- Content angle preferences
- Domain classification rules

---

## Project RSD (Quality Intelligence)

**File:** `annaseo_qi_engine.py`  
**Port:** 8006  
**Scope:** ONE project at a time  
**Manages:** Content quality, keyword relevance, domain fit

### What It Monitors

Every output item from every engine phase, per project:

- `pillar_keyword` — is this pillar relevant to this business?
- `cluster_name` — is this cluster coherent and on-domain?
- `article_body` — E-E-A-T, GEO, readability, no AI watermarks
- `article_title` — keyword presence, CTR potential
- `supporting_keyword` — is this keyword adding value?
- `audit_finding` — is this finding accurate and actionable?

### Triggered After Each Run

```
Project run completes (any phase)
    ↓
QIEngine.job_score_run(run_id)
    ↓
Gemini scores all new items (free tier)
    ↓
Review queue populated (worst items first)
    ↓
User reviews and marks Good/Bad with reason
    ↓ (if Bad)
DegradationAttributor finds exact engine/function
    ↓
TuningGenerator creates targeted fix
    ↓
Claude verifies
    ↓
Manual approval → deployed
```

### What It Tunes (Project Scope)

- `ProjectDomainProfile.reject_overrides` — keywords to block for this project
- `ProjectDomainProfile.accept_overrides` — keywords to allow despite global rules
- `ProjectDomainProfile.cross_domain_rules` — per-word industry verdict
- Layer 2 prompt (brand voice, content angles)
- Layer 3 prompt (article-level context)

### What It Tunes (Global Scope via TuningRegistry)

When a keyword is universally bad (not just domain-specific):
- `OffTopicFilter.GLOBAL_KILL` — adds word to global kill list

Decision is automatic:
- Word in `CROSS_DOMAIN_VOCABULARY` → PROJECT tuning (domain-specific)
- Word not in vocabulary → GLOBAL tuning (universal noise)

### Never Touches

- Engine .py code
- Layer 1 system prompt
- Algorithm thresholds
- Other projects' configurations

---

## Side-by-Side Comparison

| Aspect | Global RSD | Project RSD |
|--------|-----------|-------------|
| File | annaseo_rsd_engine.py | annaseo_qi_engine.py |
| Port | 8004 | 8006 |
| Scope | All projects | One project |
| Data source | Engine metrics (timing, memory, errors) | Live output items (keywords, articles) |
| Trigger | Scheduled + anomaly | After each run + user action |
| AI pipeline | Gemini→Groq→DeepSeek→Claude | Gemini scoring + DeepSeek fix |
| Tunes | Engine .py files, Layer 1 prompt | Project config, Layer 2/3 |
| Example fix | P8 topic naming picks wrong cluster | "cinnamon tour" bad for spice project |
| Approval | System admin | Project owner |

---

## Self Development (Intelligence Crawling)

**File:** `annaseo_self_dev.py`  
**Port:** 8005  
**Scope:** GLOBAL — industry intelligence for all engines

### What It Does

Watches 40+ sources for new SEO/GEO developments and implements them.

### Source Schedule

```
Daily 8:00 UTC    → Google Official + SEO Industry
Daily 10:00 UTC   → AI Search + GitHub
Weekly Sunday     → Research papers + arXiv
On demand         → User adds custom URL
```

### Pipeline

```
Crawl sources
    ↓
Gemini extracts relevance and change type
    ↓
GapAnalyser compares against current AnnaSEO capabilities
    ↓
KnowledgeGap created if something is missing
    ↓
User or scheduler triggers implementation
    ↓
Gemini spec → Groq tests → DeepSeek code → Claude verify
    ↓
Manual approval → deployed globally
```

### User Custom Content

Users can add their own sources and content:

```
POST /api/sd/user-content
{
  "title": "New GEO paper on AI citability",
  "content": "https://arxiv.org/abs/2024.xxxxx",
  "content_type": "url",
  "engines_affected": ["rank_zero_engine", "content_engine"]
}
```

The system crawls the URL, analyses it for actionable changes, and creates a gap if warranted.

---

## The Full RSD Dashboard (UI)

The Research & Self Development page in the frontend combines:

**Tab 1: Engine Health (Global RSD)**
- Health score per engine (bar chart)
- Pending approvals for code changes
- Version history + rollback buttons

**Tab 2: Quality Review (Project RSD)**
- Review queue — items sorted worst first
- Good/Bad buttons with reason input
- Attribution: "This item came from P10_PillarIdentification.PILLAR_PROMPT"

**Tab 3: Phase Health**
- Quality score per phase
- How many bad items originated from each phase
- Known failure modes from ENGINE_ANATOMY

**Tab 4: Tuning Approvals**
- Pending tunings (project and global)
- Diff view for each change
- Approve / Reject / See evidence

**Tab 5: Intelligence Feed (Self Dev)**
- Latest crawled items
- Knowledge gaps by priority
- Pending feature implementations

**Tab 6: Changelog**
- Every change made, with score before/after
- Rollback any change instantly

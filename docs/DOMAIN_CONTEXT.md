# Domain Context & Tuning Scope

## The Core Problem

AnnaSEO is used by different business types. The same keyword means different things:

**"Cinnamon tour"**
- For a **spice exporter** → BAD. Tourism is completely off-domain.
- For a **Sri Lanka travel agency** → GOOD. Cinnamon plantation tours are their core product.

**"Ceylon cinnamon"**
- For a **spice exporter** → GOOD. It's their product.
- For a **travel agency** → GOOD. It's what tourists come to see.

**"Buy cinnamon per kg"**
- For a **spice exporter** → GOOD. Transactional keyword.
- For a **travel agency** → BAD. They don't sell spices.

Without domain context, a global kill list either blocks valid tourism keywords or allows tourism keywords into spice projects. You cannot solve this with a single list.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Project A: Ceylon Spice Exports                    │
│  Industry: FOOD_SPICES                              │
│  reject_overrides: [tour, travel, trip, holiday]    │
│  accept_overrides: [ceylon, plantation, organic]    │
└──────────────────┬──────────────────────────────────┘
                   │
         DomainContextEngine
         classify(keyword, project_id)
                   │
┌──────────────────┴──────────────────────────────────┐
│  Project B: Sri Lanka Spice Tours                   │
│  Industry: TOURISM                                  │
│  reject_overrides: [bulk order, wholesale, per kg]  │
│  accept_overrides: [ceylon cinnamon tour, plantation│
│                     spice route, culinary tour]     │
└─────────────────────────────────────────────────────┘
```

---

## Cross-Domain Vocabulary

Words that are **valid for some industries and invalid for others.**

These are NOT in `OffTopicFilter.GLOBAL_KILL`. They are in `CROSS_DOMAIN_VOCABULARY` — resolved per project based on industry.

| Word | FOOD_SPICES | TOURISM | HEALTHCARE | ECOMMERCE |
|------|-------------|---------|------------|-----------|
| tour | reject | accept | reject | reject |
| travel | reject | accept | reject | reject |
| plantation | accept | accept | — | — |
| ceylon | accept | accept | — | — |
| holiday | reject | accept | — | accept (sale) |
| buy | accept | reject | — | accept |
| wholesale | accept | reject | — | accept |
| kg | accept | reject | — | accept |
| resort | reject | accept | accept (wellness) | — |
| ayurveda | accept | accept | accept | — |
| meme | reject | reject | reject | reject |

**"—" means no specific rule — falls to domain scoring.**

---

## Where Domain Context Engine Sits in Pipeline

```
P2_KeywordExpansion produces raw_keywords
    ↓
DomainContextEngine.classify_batch(keywords, project_id)
    ├── Accepted → pass to P3_Normalization
    ├── Rejected → log to qi_classification_log, discard
    └── Ambiguous → flag for user review at Gate 3

P3_Normalization
    ↓
OffTopicFilter (GLOBAL kill list — universal noise only)
    ↓
... P4–P9 ...
    ↓
P10_PillarIdentification produces pillars
    ↓
DomainContextEngine.validate_pillars(pillars, project_id)
    ├── Valid pillars → continue
    └── Rejected pillars → logged, excluded

P15_ContentBrief produces brief
    ↓
DomainContextEngine.validate_content_brief(brief, project_id)
    ├── Valid → continue
    └── Off-domain H2s → removed, flagged
```

---

## Tuning Scope — Project vs Global

### Decision Table

| What happened | Scope | Why | Where to fix |
|---------------|-------|-----|-------------|
| "cinnamon tour" bad in spice project | PROJECT | "tour" valid in tourism projects | ProjectDomainProfile.reject_overrides |
| "meme" bad in any project | GLOBAL | Universal noise, no industry wants it | OffTopicFilter.GLOBAL_KILL |
| P8 topic naming picks wrong cluster name | GLOBAL | Code issue affects all projects | P8._name_topic prompt |
| Article lacks E-E-A-T signals | GLOBAL | Layer 1 system prompt — affects all | ContentGenerationEngine Layer 1 prompt |
| Article wrong angle for spice audience | PROJECT | Layer 2/3 — brand/article context | Project brand config |
| PILLAR_PROMPT has no domain exclusion | GLOBAL | Code fix — affects all projects | ruflo_20phase_engine.py P10 prompt |
| Engine scores 60 (slow/error-prone) | GLOBAL | Code quality — affects all projects | RSD engine tuning |
| GEO score always below 70 globally | GLOBAL | Threshold or prompt — all projects | Layer 1 prompt + GEOScorer |

### Rule of Thumb
- **User feedback on a keyword's domain relevance** → PROJECT tuning
- **Engine code bug or structural issue** → GLOBAL tuning
- **Threshold too loose/tight** → GLOBAL tuning
- **Content angle wrong for this business** → PROJECT tuning
- **Content structure wrong for all businesses** → GLOBAL tuning

---

## Research & Self Development — Two Scopes

### Global RSD

**What it monitors:** Engine code quality across ALL projects  
**Data it uses:** Engine run metrics (timing, memory, error rate, output quality scores)  
**What it tunes:** Engine .py files, Layer 1 system prompts, thresholds, algorithm parameters  
**Never touches:** Per-project keyword lists, brand config, content angles

**Scheduled jobs:**
```
Daily   8:00 UTC  → scan all engines for health
Daily  10:00 UTC  → crawl SEO/GEO intelligence sources
Weekly Sun 6:00   → crawl research papers + GitHub releases
On demand         → user triggers manual scan
```

### Project RSD

**What it monitors:** Content and keyword quality for ONE specific project  
**Data it uses:** Live keyword universe results, article scores, user feedback labels  
**What it tunes:** ProjectDomainProfile (accept/reject lists), Layer 2/3 prompts  
**Never touches:** Engine code, Layer 1 prompt, other projects

**Triggered by:**
```
After each project run completes → score all new items
User marks item as Bad → attribute → generate project tuning
Batch feedback review → pattern analysis → targeted fix
```

---

## Project Setup

When creating a new project, the user selects:
- Industry (FOOD_SPICES, TOURISM, HEALTHCARE, etc.)
- Seed keywords
- Business description

The system auto-populates from `DEFAULT_DOMAIN_PROFILES[industry]`:
- `accept_overrides` — words explicitly allowed for this industry
- `reject_overrides` — words explicitly blocked for this industry
- `cross_domain_rules` — per-industry cross-domain vocabulary rules
- `content_angles` — what content should focus on
- `avoid_angles` — what content should NOT cover

The user can then extend (not replace) these defaults with custom words.

---

## API

```
POST /api/dc/projects/{project_id}/setup
POST /api/dc/classify              → {keyword: {verdict, score, reason, is_cross_domain}}
POST /api/dc/validate-pillars/{project_id}
POST /api/dc/feedback              → creates project or global tuning
GET  /api/dc/tunings/project/{project_id}
GET  /api/dc/tunings/global
GET  /api/dc/scope-rules
GET  /api/dc/cross-domain-vocabulary
```

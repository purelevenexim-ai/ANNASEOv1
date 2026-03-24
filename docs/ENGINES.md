# AnnaSEO — Engines Reference

## File Map

| File | Lines | Role | Port |
|------|-------|------|------|
| `ruflo_20phase_engine.py` | 2,269 | 20-phase keyword universe (P1–P20) | 8000 |
| `ruflo_20phase_wired.py` | — | WiredRufloOrchestrator — RawCollector + DCE wrapper | 8000 |
| `ruflo_v3_keyword_system.py` | — | Ruflo v3 — 4-level universe hierarchy | 8000 |
| `ruflo_content_engine.py` | 1,645 | 7-pass content generation | 8000 |
| `ruflo_strategy_dev_engine.py` | 1,309 | Business strategy + personas | 8000 |
| `ruflo_final_strategy_engine.py` | 1,295 | Claude strategy synthesis | 8000 |
| `ruflo_confirmation_pipeline.py` | 1,715 | 5-gate user approval | 8000 |
| `ruflo_seo_audit.py` | 1,677 | 14 checks + AI visibility | 8000 |
| `ruflo_publisher.py` | 1,337 | WordPress + Shopify publish | 8000 |
| `annaseo_addons.py` | 929 | HDBSCAN, OffTopicFilter, lifecycle | — |
| `annaseo_doc2_addons.py` | 933 | ClusterType, Memory, Versioning | — |
| `annaseo_qi_engine.py` | 1,698 | Quality intelligence master | 8006 |
| `annaseo_domain_context.py` | ~700 | Per-project domain classification | 8007 |
| `annaseo_rsd_engine.py` | 2,061 | Code quality + engine tuning | 8004 |
| `annaseo_self_dev.py` | 1,948 | Intelligence crawling + features | 8005 |

---

## Ruflo v3 — 4-level keyword universe

**File:** `engines/ruflo_v3_keyword_system.py`
**Entry:** `RufloV3KeywordSystem.run_universe(seed, project_id)`

### Hierarchy

```
Universe  ← customer input ("black pepper")
  └── Pillar  ← competitor traffic discovery (top competitor pages for the seed)
        └── Cluster  ← semantic grouping (HDBSCAN + sentence-transformers)
              └── Supporting keywords  ← 8 long-tail methods × language/region/religion
```

### Key classes

| Class | Role |
|-------|------|
| `PillarExtractor` | Crawls SERP for competitor URLs, extracts pillar topics from competitor pages |
| `SerpScraper` | Collects SERP data for keywords — difficulty, featured snippet, PAA, video |
| `UniverseCollector` | Combines seed expansion + pillar discovery into raw keyword pool |
| `RufloV3KeywordSystem` | Orchestrates full pipeline, returns `UniverseTree` JSON |

### Methods

| Method | What it does |
|--------|-------------|
| `run_universe(seed)` | Full 20-phase pipeline for one seed |
| `run_all_universes(seeds)` | Parallel universe generation for all seeds |
| `get_universe_tree(project_id)` | Return JSON tree: Universe→Pillar→Cluster→Keywords |

---

## Engine 1: 20-Phase Keyword Universe

**File:** `ruflo_20phase_engine.py`  
**Entry:** `RufloOrchestrator.run_seed(keyword, project_id)`

### Phase Data Flow

```
Seed keyword
    ↓
P1  SeedInput          → Seed object (id, language, region)
    ↓
P2  KeywordExpansion   → raw_keywords: List[str] (500–3000)
    │  sources: google_autosuggest, youtube, amazon, duckduckgo, reddit
    ↓
    DomainContextEngine.classify_batch()  ← NEW: domain pre-filter
    ↓
P3  Normalization      → clean_keywords: List[str] (dedup, lowercase)
    ↓
    OffTopicFilter     → filtered_keywords (GLOBAL_KILL list)
    ↓
P4  EntityDetection    → entity_map: Dict[kw, {entities}] (spaCy)
    ↓
P5  IntentClassify     → intent_map: Dict[kw, intent] (rule-based)
    │  intents: informational, transactional, comparison, commercial
    ↓
P6  SERPIntelligence   → serp_map: Dict[kw, serp_data] (top 100 kws only)
    ↓
P7  OpportunityScore   → scored_kws: Dict[kw, float 0-100]
    ↓
P8  TopicDetection     → topic_map: Dict[topic_name, [kws]] (SBERT+KMeans)
    │  k = max(5, min(80, len(kws)//12))
    ↓
P9  ClusterFormation   → cluster_map: Dict[cluster, [topics]] (Gemini)
    ↓
    DomainContextEngine.validate_pillars()  ← NEW: domain validation
    ↓
P10 PillarIdentify     → pillars: Dict[cluster, {pillar_title, pillar_kw}]
    ↓
P11 KnowledgeGraph     → KnowledgeGraph (5-level hierarchy)
    ↓
P12 InternalLinking    → link_map: Dict[article, [linked_articles]]
    ↓
P13 ContentCalendar    → schedule: List[{date, keyword, pillar}]
    ↓
P14 DedupPrevention    → deduplicated_pipeline (0.85 similarity threshold)
    ↓
P15 ContentBrief       → brief: {h1, h2s, faqs, entities, links, angle}
    ↓
P16 Claude Content     → article_draft: str (full text)
    ↓
P17 SEOOptimization    → seo_score + issues (28 signals, threshold 75)
    ↓
P18 SchemaMetadata     → json_ld + meta tags
    ↓
P19 Publishing         → published_url (WordPress or Shopify)
    ↓
P20 RankingFeedback    → ranking_analysis + GSC data
```

### Critical Configuration

```python
# annaseo_addons.py — OffTopicFilter.GLOBAL_KILL (line 150)
# Current list covers: social media, furniture, DIY, pest control, sports, piracy
# MISSING (needs adding): tour, travel, trip, tourism, resort, hotel, vacation
# But these are domain-specific — use ProjectDomainProfile.reject_overrides instead

# ruflo_20phase_engine.py — P10_PillarIdentification.PILLAR_PROMPT (line 1070)
# Current: no domain exclusion instruction
# NEEDS: "If cluster is off-domain, return SKIP"

# P5_IntentClassification.RULES (line 782)
# Current: no "skip" or "noise" category — defaults to "informational"
# NEEDS: noise category for off-domain words
```

---

## Engine 2: Content Generation (7 Passes)

**File:** `ruflo_content_engine.py`  
**Entry:** `ContentGenerationEngine.generate(keyword, title, intent, style, entities, brand)`

### Pass Architecture

| Pass | Model | Purpose | Cost |
|------|-------|---------|------|
| Pass 1 | Gemini free | Research: competitor gaps, citations, data | $0 |
| Pass 2 | DeepSeek local | Brief: H1/H2/H3 structure, entity list | $0 |
| Pass 3 | Claude Sonnet | Full article: E-E-A-T + GEO + style | ~$0.022 |
| Pass 4 | Rules | SEO signal check: 28 signals, keyword density | $0 |
| Pass 4b | Rules | Readability scoring | $0 |
| Pass 5 | DeepSeek | E-E-A-T check: experience/expertise/authority/trust | $0 |
| Pass 6 | Rules | GEO check: 8 AI citation signals | $0 |
| Pass 7 | Claude Sonnet | Humanize: only if any score < 75 | ~$0.008 |

### Three-Layer Prompt Architecture

```
Layer 1 (global — never changes)
  → 500-word system prompt with all SEO rules
  → "Never use: furthermore, certainly, delve, it is worth noting"
  → "Every 300 words: first-person expertise signal"
  → "Every H2: direct answer in first sentence + one specific number"
  → Changes = GLOBAL tuning (affects all projects)

Layer 2 (brand — per project)
  → Business name, author credentials, regional terms
  → Voice and tone guidelines
  → Avoid words list
  → Changes = PROJECT tuning

Layer 3 (article — per content piece)
  → Brief structure (H1/H2/H3/FAQ)
  → Research findings and citations
  → Internal links to inject
  → Persona context
  → Changes = per-article adjustment
```

### Quality Thresholds

```python
PUBLISH_THRESHOLD = 75    # all scores must be >= 75
MAX_AUTO_REVISIONS = 2    # max Pass 7 reruns
# If score < 75 after 2 revisions → status = "needs_review"
```

---

## Engine 3: SEO Audit

**File:** `ruflo_seo_audit.py`  
**Entry:** `RufloSEOAudit.run(url, project_id)`

### Checks

**Technical (14 checks):**
HTTPS, title tag, meta description, H1, canonical, noindex, schema, OG tags, alt text, internal links, security headers, word count, heading hierarchy, redirects

**Core Web Vitals:**
LCP + INP (NOT FID — FID removed March 2024) + CLS via PageSpeed API

**AI Visibility (14 bots):**
GPTBot, ClaudeBot, PerplexityBot, OAI-SearchBot, Diffbot, Applebot, ChatGPT-User, CCBot, FacebookBot, Twitterbot, LinkedInBot, SemrushBot, AhrefsBot, MJ12bot

**Additional:**
llms.txt validation, AI citability scoring, brand mention scan (7 platforms), hreflang, programmatic SEO gates

### Critical 2026 Rules
```
INP replaces FID (March 2024) — FID is DEAD, never check it
FAQ schema: restricted to gov/healthcare only (Aug 2023)
HowTo schema: deprecated (Sept 2023)
JSON-LD only — never Microdata or RDFa
E-E-A-T: applies to ALL competitive queries (Dec 2025)
Location pages: warning 30+, hard stop 50+
Programmatic SEO: warning 100+ pages, hard stop 500+
```

---

## Engine 4: Publisher

**File:** `ruflo_publisher.py`  
**Entry:** `Publisher.publish(article, metadata, scheduled_date)`

### Platforms
- **WordPress:** REST API, App Password auth, Yoast+RankMath meta, JSON-LD injection, Google Indexing API ping
- **Shopify:** Admin REST API 2024-01, SEO metafields, scheduled publish, blog mapping by pillar
- **Queue:** SQLite-backed, one-at-a-time (never parallel), 3× retry, 30s delay between publishes

---

## Engine 5: Quality Intelligence (QI)

**File:** `annaseo_qi_engine.py`  
**Entry:** `QIEngine.job_dashboard(project_id)`

### Data Flow

```
Engine run completes
    ↓
RawCollector.record_phase()  → qi_raw_outputs table
    ↓
QIEngine.job_score_run()     → Gemini scores each item
    ↓
Review queue populated        → sorted worst-first
    ↓
User feedback (good/bad)      → qi_user_feedback table
    ↓ (if bad)
DegradationAttributor.attribute()  → finds exact phase/fn
    ↓
TuningGenerator.generate()   → creates targeted fix
    ↓
Claude verifies               → approval notes
    ↓
Manual approval gate          → human approves/rejects
    ↓ (if approved)
TuningApplicator.apply()      → modifies engine file
    ↓
Rollback available            → snapshot saved pre-change
```

### ENGINE_ANATOMY Map

Built by reading every engine file — exact failure modes per phase:

| Phase | File | Known failures |
|-------|------|---------------|
| P2_KeywordExpansion | 20phase | Tourism words from autosuggest |
| OffTopicFilter | addons | GLOBAL_KILL missing tourism words |
| P5_IntentClassification | 20phase | No "skip/noise" category — defaults to informational |
| P8_TopicDetection | 20phase | SBERT embeds tourism near spices |
| P9_ClusterFormation | 20phase | Gemini CLUSTER_PROMPT has no domain exclusion |
| P10_PillarIdentification | 20phase | PILLAR_PROMPT has no domain exclusion |
| P16_Claude_Content | content | AI watermarks, low GEO, generic E-E-A-T |
| GEOScorer | content | No direct-answer block check |
| EEATScorer | content | Weak heuristic when DeepSeek unavailable |

---

## Engine 6: Domain Context

**File:** `annaseo_domain_context.py`  
**Entry:** `DomainContextEngine.classify(keyword, project_id)`

### The Cross-Domain Problem

Same keyword, different verdict based on project industry:

| Keyword | Spice project | Tourism project | Why |
|---------|--------------|----------------|-----|
| "cinnamon tour" | REJECT | ACCEPT | "tour" = valid for tourism |
| "ceylon cinnamon" | ACCEPT | ACCEPT | product + destination both valid |
| "buy cinnamon kg" | ACCEPT | REJECT | commercial = not tourism |
| "cinnamon plantation" | ACCEPT | ACCEPT | valid for both |
| "cinnamon holiday" | REJECT | ACCEPT | holiday = tourism context |
| "cinnamon meme" | REJECT | REJECT | universal noise |

**Rule:** Cross-domain words live in `ProjectDomainProfile.cross_domain_rules`.  
Universal noise lives in `OffTopicFilter.GLOBAL_KILL`.

### Pipeline Position

```
After P3_Normalization → DomainContextEngine.classify_batch()
After P10_PillarIdentification → DomainContextEngine.validate_pillars()
In P15_ContentBrief → DomainContextEngine.validate_content_brief()
```

---

## Engine 7: RSD (Research & Self Development)

**File:** `annaseo_rsd_engine.py`  
**Entry:** `ResearchAndSelfDevelopment.job_scan_all()`

### Scope: GLOBAL

Monitors engine CODE quality across all projects.  
Does not touch project-specific keyword or content quality.

### Scoring (8 dimensions, weighted)

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Output quality | 30% | Quality signals from engine outputs |
| Execution time | 15% | p95 latency vs 30s target |
| Memory usage | 15% | Peak MB vs 512MB target |
| Error rate | 15% | Failures per 24h |
| Output completeness | 10% | Required fields present |
| Consistency | 10% | Same input → same structure |
| API cost | 3% | Tokens per quality point |
| Test coverage | 2% | % code paths with tests |

---

## Engine 8: Self Development

**File:** `annaseo_self_dev.py`  
**Entry:** `SelfDevelopmentEngine.job_crawl_all()`

### Scope: GLOBAL

Watches 40+ external sources for new SEO/GEO signals.  
Identifies what AnnaSEO should implement next.

### Source Categories

- **google_official:** Search Central Blog, web.dev, schema.org releases
- **seo_industry:** searchengineland, moz, ahrefs, backlinko, seroundtable
- **ai_search:** Perplexity, OpenAI, Anthropic, llmstxt.org, Bing
- **github:** Trending SEO repos, watched releases (Ruflo, claude-seo, Agentic-SEO-Skill)
- **research:** arXiv, Google Research, HTTP Archive

---

## Addons Modules

### annaseo_addons.py

| Class | Purpose |
|-------|---------|
| `HDBSCANClustering` | Density-based keyword clustering (no K needed) |
| `OffTopicFilter` | Kill-word filter — GLOBAL_KILL + per-seed custom |
| `KeywordTrafficScorer` | Quick Win / Gold Mine opportunity scorer |
| `CannibalizationDetector` | Checks for duplicate article targets |
| `MissingExpansionDimensions` | Storage/Cultivation/History expansion |
| `ContentLifecycleManager` | new→growing→peak→declining→refresh_needed |

### annaseo_doc2_addons.py

| Class | Purpose |
|-------|---------|
| `ClusterTypeClassifier` | Pillar/Subtopic/Support/Conversion |
| `KeywordStatusTracker` | not_used→planned→in_content→published→ranking→optimized |
| `PromptVersioning` | A/B testing prompts, performance tracking |
| `MemorySystem` | 4-layer memory (project, learning, interaction, global) |
| `CompetitorAttackPlan` | Gap analysis → quick wins → strategy |

# Implementation Plan — Pipeline Quality + Strategy Overhaul

**Date:** April 3, 2026  
**Goal:** Fix pipeline data quality (P8-P14), add full data visibility, make strategy editable/re-runnable

---

## BLOCK A: Pipeline Phase Quality Improvements (P8-P14)

### A1. P8 — Replace word-overlap with embedding-based clustering
**Problem:** Current word-overlap algorithm (min 2 shared words) fails on single-word keywords and semantically similar keywords that don't share words (e.g., "cinnamon health benefits" and "cassia wellness properties").  
**Fix:**
- Use SBERT embeddings (all-MiniLM-L6-v2) cached in `ruflo_data/embeddings/`
- Cosine similarity threshold (0.55) for topic grouping
- Keep intent-based pre-grouping as first pass, then refine with embeddings
- Community detection (simple agglomerative) within each intent group
- Unload SBERT after use (380MB freed)
- Fallback to current word-overlap if SBERT unavailable

**File:** `engines/ruflo_20phase_engine.py` — `P8_TopicDetection.run()`  
**Effort:** Medium

### A2. P9 — Remove topic truncation, improve cluster prompt
**Problem:** Only sends `topics[:60]` to Gemini. Large universes (80+ topics) lose clustering info.  
**Fix:**
- Send ALL topics to Gemini (paginate if needed: split into batches of 100, merge results)
- Improve prompt: include top 3 keywords per topic for Gemini to see actual content
- Add deterministic naming: require cluster names to be derived from input topics
- Fix return validation: ensure returned cluster names map back to actual topic names

**File:** `engines/ruflo_20phase_engine.py` — `P9_ClusterFormation.run()`  
**Effort:** Medium

### A3. P10 — Better pillar naming with full cluster context
**Problem:** Only sends `topics[:10]` to Gemini. Pillar keyword = `cluster_name.lower()` (no optimization).  
**Fix:**
- Send ALL topics per cluster (up to 30) to pillar naming prompt
- Optimize pillar_keyword: use highest-scoring keyword in cluster, not cluster name
- Improve naming prompt: include seed keyword, business type, intent distribution
- Add article_count: calculate from actual keyword count, not just `len(topics)+1`

**File:** `engines/ruflo_20phase_engine.py` — `P10_PillarIdentification.run()`  
**Effort:** Low

### A4. P11 — Add semantic edges to knowledge graph
**Problem:** Knowledge graph is just a tree hierarchy. No semantic relationship edges. No edge weights.  
**Fix:**
- Add `edges` to KnowledgeGraph: cross-topic links based on entity sharing
- Add `intent_progression` edges: informational → commercial → transactional chains
- Calculate edge weights from keyword overlap + entity overlap
- Store in a format compatible with D3 force-directed graph

**File:** `engines/ruflo_20phase_engine.py` — `P11_KnowledgeGraphBuilder.run()`  
**Effort:** Medium

### A5. P12 — Context-aware internal linking
**Problem:** Hardcoded URL format, CTA always "buy X online", only sibling links.  
**Fix:**
- Accept optional `site_structure` parameter (from project config)
- If no site structure, use reasonable defaults based on business_type
- CTA varies by intent: informational→"learn more about", commercial→"compare", transactional→"buy"
- Add cross-cluster authority links: point from high-score articles to low-score ones in related clusters
- Limit links per page: 3-5 internal links (not unlimited)
- Add relationship type to each link for frontend display

**File:** `engines/ruflo_20phase_engine.py` — `P12_InternalLinking.run()`  
**Effort:** Medium

### A6. P13 — Smarter scheduling with intent distribution
**Problem:** Question articles always first regardless of score. No intent diversity per week.  
**Fix:**
- Ensure weekly intent diversity: mix of informational (40%), commercial (30%), transactional (20%), navigational (10%)
- Pillar pages published in Month 1 (foundation), cluster articles follow
- Score-based priority within each intent bucket
- Add `estimated_difficulty` and `estimated_traffic` to each calendar entry
- Don't force question articles first — let score + intent together determine order

**File:** `engines/ruflo_20phase_engine.py` — `P13_ContentCalendar`  
**Effort:** Low

### A7. P14 — Smarter dedup with fuzzy matching
**Problem:** Punctuation removal too aggressive. No semantic dedup.  
**Fix:**
- Fix normalization: keep hyphens in compound words, handle special chars properly
- Add fuzzy title matching: Levenshtein ratio > 0.85 = duplicate
- Add keyword-pair similarity: if two keywords share >80% words (order-independent), flag as duplicate
- Keep higher-scoring article when removing duplicates
- Log which articles were removed and why

**File:** `engines/ruflo_20phase_engine.py` — `P14_DedupPrevention.run()`  
**Effort:** Low

---

## BLOCK B: Full Data Visibility (P1-P14)

### B1. Backend: Rich result_summary with ALL data
**Problem:** Frontend PhaseCard shows summaries (first 10-20 items). No way to see full data.  
**Fix:** Enhance `result_summary` sent via SSE for each phase:

| Phase | Current Summary | Enhanced Summary |
|-------|----------------|-----------------|
| P2 | expanded_count, sample(10) | expanded_count, ALL keywords in chunks |
| P3 | normalized_count | normalized_count, ALL keywords |
| P5 | intent distribution | ALL keyword→intent mappings |
| P7 | top 5, avg score | ALL keyword→score, score histogram |
| P8 | 20 topics + sizes | ALL topics with ALL keywords per topic |
| P9 | 20 clusters + counts | ALL clusters with ALL topic names |
| P10 | 20 pillars | ALL pillars with full detail |
| P11 | graph_nodes count | Full graph tree (already in _graph) |
| P12 | link_count | ALL links grouped by type |
| P13 | calendar_entries, date_range | ALL calendar entries with scheduled dates |
| P14 | deduplicated_count | Final calendar + removed items list |

**Approach:** Store full phase output in `run_events` payload alongside the summary. The existing `/api/runs/{run_id}/phase/{phase}/detail` endpoint already returns `result_sample` — enhance it to return the complete data.

**Files:** `engines/ruflo_20phase_wired.py` (result_summary builder), `main.py` (phase detail endpoint)  
**Effort:** Medium

### B2. Frontend: Expandable data tables per phase
**Problem:** PhaseCard expanded view shows 10 topics, 10 clusters, etc. No pagination, no search, no export.  
**Fix:**
- Add a "View All Data" button per phase that opens a full-screen modal
- Modal has: searchable table, pagination (50 items/page), sort by columns
- Phase-specific columns:
  - P7: keyword, score, intent, entity_count — sortable
  - P8: topic_name, keyword_count, top_keywords — expandable
  - P9: cluster_name, topic_count, keyword_count — expandable
  - P10: pillar_title, pillar_keyword, cluster_count, keyword_count, article_count
  - P13: title, keyword, cluster, scheduled_date, score, intent
- Export button: download as CSV

**File:** `frontend/src/workflow/Step3Pipeline.jsx`  
**Effort:** High

### B3. Frontend: Phase data flow visualization
**Problem:** No visual indication of how data flows between phases (243 kw → 81 topics → 27 clusters → 12 pillars).  
**Fix:**
- Add a data flow bar between phase groups showing: input count → output count
- Color-coded: green if reasonable reduction, yellow if suspicious, red if >80% data loss
- Example: "P3: 400 kw → P7: 400 scored → P8: 81 topics → P9: 27 clusters → P10: 12 pillars → P13: 156 articles"

**File:** `frontend/src/workflow/Step3Pipeline.jsx`  
**Effort:** Low

---

## BLOCK C: Strategy Overhaul

### C1. Strategy editing UI
**Problem:** Strategy is read-only after generation.  
**Fix:**
- Make ReviewSubStep editable:
  - **Pillar plan:** drag to reorder priority, edit content_types, estimated_articles
  - **Content mix:** editable percentage sliders (must sum to 100)
  - **SEO recommendations:** add/remove/edit items
  - **90-day plan:** edit deliverables, add items
  - **Executive summary:** textarea for editing
- "Save Changes" button → `POST /api/ki/{project_id}/save-strategy`
- Track edit history (version_id in strategy_json)

**Files:** `frontend/src/workflow/Step4Strategy.jsx`, `main.py`  
**Effort:** High

### C2. Strategy re-generation
**Problem:** No re-generate button.  
**Fix:**
- Add "🔄 Regenerate Strategy" button in ReviewSubStep
- When clicked: re-calls `/api/ki/{project_id}/post-pipeline-strategy` with optional overrides:
  - `focus_areas`: ["content_depth", "competitor_gaps", "quick_wins"]
  - `pillar_priorities`: user-edited pillar priority overrides
  - `tone`: "aggressive|conservative|balanced"
- Shows diff between old and new strategy (highlight changes)
- User can accept new or keep old

**Files:** `frontend/src/workflow/Step4Strategy.jsx`, `main.py`  
**Effort:** Medium

### C3. Live strategy data during generation
**Problem:** During strategy generation, user only sees log lines. No intermediate data.  
**Fix:**
- Stream pipeline summary as structured data (not just log text)
- Show real-time: which runs are being analyzed, keyword counts, pillar names
- Show AI prompt context (what the AI is seeing) — transparency
- Show intermediate AI response chunks (token-by-token if possible)

**Files:** `main.py` (SSE enhancement), `frontend/src/workflow/Step4Strategy.jsx`  
**Effort:** Medium

### C4. Richer strategy context to AI
**Problem:** AI only sees summaries (counts + first 20 items). For 300 keywords, AI sees truncated data.  
**Fix:**
- Send full pipeline data to AI (not just result_summary):
  - ALL pillar names + keyword counts
  - ALL cluster names
  - ALL scored keywords (top 100 with scores)
  - Intent distribution (full breakdown)
  - Calendar entry count per pillar
- For large datasets: use a 2-step approach:
  1. First call: AI generates per-pillar strategy (one call per pillar with full pillar data)
  2. Second call: AI synthesizes overall strategy from per-pillar strategies

**File:** `main.py` (strategy generation logic)  
**Effort:** Medium

### C5. Strategy → Pipeline feedback loop
**Problem:** Strategy insights don't flow back to pipeline.  
**Fix:**
- After strategy is accepted, update P13 calendar ordering:
  - High-priority pillars get earlier dates
  - Quick-win keywords move to Month 1
  - Content mix percentages applied to weekly scheduling
- Store strategy decisions in `content_strategy` table for P15+ to use

**Files:** `engines/ruflo_20phase_engine.py` (P13), `main.py`  
**Effort:** Medium

---

## BLOCK D: Strategy Formulation Flow Fixes

### D1. Fix Step 1 → Strategy data flow
**Problem:** customer_url, competitor_urls, business_intent collected in Step 1 but not analyzed.  
**Fix:**
- When customer_url provided: basic site analysis (title, meta, heading structure) via lightweight scrape
- When competitor_urls provided: extract their pillar pages, estimate keyword targets
- Feed business_intent + site analysis + competitor data into strategy prompt

**File:** `main.py` (strategy generation)  
**Effort:** Medium

### D2. Save strategy as versioned snapshots
**Problem:** Only latest strategy stored. No history.  
**Fix:**
- New table `strategy_versions`: `(id, project_id, session_id, version, strategy_json, ai_source, created_at, is_active)`
- Each generation creates a new version
- User can view/compare old versions
- "Revert to version X" capability

**Files:** `main.py` (new table + endpoints), `frontend/src/workflow/Step4Strategy.jsx`  
**Effort:** Medium

---

## Priority Order

### Sprint 1 — Must Have (Pipeline Quality + Visibility)
1. **A1** P8 embedding-based clustering
2. **A2** P9 remove truncation, improve prompt
3. **A3** P10 better pillar naming
4. **A7** P14 smarter dedup
5. **B1** Backend rich result_summary (ALL data per phase)
6. **B2** Frontend expandable data tables
7. **B3** Data flow bar visualization

### Sprint 2 — Must Have (Strategy)
8. **C1** Strategy editing UI
9. **C2** Strategy re-generation
10. **C3** Live strategy data
11. **C4** Richer AI context

### Sprint 3 — Should Have
12. **A4** P11 semantic edges
13. **A5** P12 context-aware linking
14. **A6** P13 smarter scheduling
15. **C5** Strategy → Pipeline feedback
16. **D1** Step 1 data flow fix

### Sprint 4 — Nice to Have
17. **D2** Strategy version snapshots

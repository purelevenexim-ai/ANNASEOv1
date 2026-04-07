# Pipeline Engine — P1 to P14 (Complete Reference)

**Last Updated:** April 3, 2026  
**Engine:** `engines/ruflo_20phase_engine.py` + `engines/ruflo_20phase_wired.py`  
**Frontend:** `frontend/src/workflow/Step3Pipeline.jsx`

---

## Overview

The 14-phase pipeline transforms a single seed keyword into a complete content strategy with knowledge graph, internal linking plan, and content calendar. Phases are grouped into 5 gate-controlled groups:

| Group | Phases | Purpose | Gate |
|-------|--------|---------|------|
| **Collection** | P1-P3 | Seed → expanded → normalized keywords | Gate A (keyword confirmation) |
| **Analysis** | P4-P6 | Entity detection, intent classification, SERP intelligence | — |
| **Scoring** | P7-P10 | Opportunity scoring, topic detection, cluster formation, pillar identification | Gate B (pillar confirmation) |
| **Structure** | P11-P12 | Knowledge graph, internal linking | — |
| **Planning** | P13-P14 | Content calendar, deduplication | Gate C (calendar/pace confirmation) |

In **step_by_step** mode, the pipeline pauses between groups. User can **Continue**, **Skip Next Group**, or **Stop Here**.

---

## Phase Detail

### P1 — Seed Validation
- **Input:** Raw keyword string + language + region
- **Output:** `Seed` object with `{id, keyword, language, region, product_url}`
- **AI:** None
- **Time:** < 1s

### P2 — Keyword Expansion
- **Input:** Seed object
- **Sources:** 5 parallel: Google Autosuggest, YouTube, Amazon, Reddit, DuckDuckGo
- **Output:** 500-3000 raw keywords (list of strings)
- **Cache:** 7-day TTL
- **AI:** None (web scraping only)
- **Time:** 20-40s

### P3 — Normalization
- **Input:** Raw keywords from P2
- **Processing:** Dedup (case-insensitive), remove stop words, spam patterns, symbols, very short/long strings
- **Output:** ~200-400 clean keywords
- **AI:** None
- **Time:** 1-2s

### P4 — Entity Detection
- **Input:** Clean keywords from P3
- **Processing:** spaCy NER (en_core_web_sm) extracts PERSON, PRODUCT, GPE, ORG, NORP, DATE, EVENT
- **Output:** `{keyword: [entity_list]}` dict
- **AI:** spaCy model (local, no API)
- **Memory:** ~150 MB (heavy)
- **Time:** 5-10s

### P5 — Intent Classification
- **Input:** Keywords + Seed + entities
- **Processing:** Rule-based + Gemini for ambiguous cases
- **Categories:** informational, commercial, transactional, navigational, local
- **Output:** `{keyword: intent_string}` or `{keyword: {intent, confidence}}`
- **AI:** Gemini (for edge cases)
- **Time:** 10-15s
- **Known Issue:** Rule-based only, no learning from feedback

### P6 — SERP Intelligence
- **Input:** All keywords (no truncation since fix)
- **Processing:** SERP data collection (keyword difficulty, volume estimates, feature data)
- **Output:** `{keyword: {positions, kd_estimate, volume_estimate, feature_data}}`
- **AI:** None (external data source)
- **Progress:** Emits progress event every 25 keywords
- **Time:** 30-60s

### P7 — Opportunity Scoring
- **Input:** Keywords, intent map, SERP map, entities
- **Formula:** `score = (volume × intent_multiplier) / (KD + 1) + entity_bonus - competitive_penalty`
- **Intent Multipliers:** informational=0.6, commercial=1.5, transactional=2.0
- **Output:** `{keyword: score}` (0-100)
- **AI:** None
- **Time:** 2-3s

### P8 — Topic Detection ⚠️
- **Input:** Keywords, scores, intent_map from P5
- **Processing:**
  1. Group keywords by intent (informational/commercial/transactional)
  2. Within each intent group, sub-cluster by word overlap (≥2 shared words)
  3. Cap each sub-cluster at 8 keywords
  4. Name topics from top-5 scoring keywords (stripping filler words)
  5. If too few topics, split largest ones to reach target
- **Target Topics:** `max(10, min(120, len(keywords) // 3))`
- **Output:** `{topic_name: [keyword_list]}` dict
- **AI:** None — pure word-overlap algorithm
- **Time:** 2-5s
- **⚠️ Issues:**
  - Word overlap (min 2 words shared) is too aggressive — single-word keywords and keywords with no overlap scatter into noise
  - No embedding-based semantic similarity
  - No AI for topic naming (uses heuristic)

### P9 — Cluster Formation ⚠️
- **Input:** Topic map from P8, project_id
- **Processing:**
  1. Calculate target clusters: `max(5, min(50, len(topics) // 3))`
  2. Call Gemini with `topics[:60]` to group into clusters
  3. DomainContext filtering (drops clusters losing >60% keywords)
  4. Fallback: if AI fails, returns topic_map as-is
- **Output:** `{cluster_name: [topic_names]}` dict
- **AI:** Gemini (temperature 0.2)
- **Time:** 5-10s
- **⚠️ Issues:**
  - **Truncates to `topics[:60]`** — large keyword universes lose clustering info
  - AI cluster naming non-deterministic (different names on reruns)
  - Gemini prompt asks to map topic names to clusters, but topics may have been renamed since P8

### P10 — Pillar Identification ⚠️
- **Input:** Clusters from P9, project_id
- **Processing:**
  1. If >15 clusters: consolidate via AI merge (target: `min(15, max(5, len//2))`)
  2. For each cluster: Gemini generates pillar page title (sends `topics[:10]`)
  3. DomainContext validation removes off-domain pillars
- **Output:** `{cluster_name: {pillar_title, pillar_keyword, topics, article_count}}` dict
- **AI:** Gemini (1 call per cluster + 1 consolidation call if >15)
- **Time:** 10-30s (rate-limited, 4s between calls)
- **⚠️ Issues:**
  - Only sends `topics[:10]` to naming prompt — misses context from large clusters
  - `pillar_keyword = cluster_name.lower()` — no keyword optimization
  - `article_count = len(topics) + 1` — doesn't account for content depth

### P11 — Knowledge Graph
- **Input:** Pillars, topic_map, intent_map, scores
- **Processing:** Builds 5-level tree: Seed → Pillar → Cluster → Topic → Keywords
- **Output:** `KnowledgeGraph` dataclass with `{seed, pillars: {name: {title, keyword, clusters: {topic: {keywords, best_keyword, intent}}}}}`
- **AI:** None — pure data organization
- **Time:** 1-2s
- **Issue:** No semantic relationship edges — just a tree hierarchy

### P12 — Internal Linking
- **Input:** Knowledge graph from P11
- **Processing:** Generates 4 link types:
  - `topic_to_pillar`: each topic article → its pillar page
  - `topic_to_topic`: consecutive sibling topics link to each other
  - `cluster_to_pillar`: cluster-level aggregation
  - `pillar_to_product`: pillar → seed product page (CTA: "buy {seed} online")
- **Output:** `{link_type: [{from_page, to_page, anchor_text, placement}]}`
- **AI:** None — rule-based linking
- **Time:** 1-2s
- **Issues:**
  - URL format hardcoded: `/{seed-slug}/{topic-slug}` — doesn't match actual site structure
  - CTA always "buy {keyword} online" — wrong for informational sites
  - Only sibling links (i→i-1), no cross-cluster linking
  - No authority-based linking (boost low-ranking pages)

### P13 — Content Calendar
- **Input:** Knowledge graph, scores, ContentPace config
- **Processing:**
  1. Flatten graph into article list (pillar first per cluster)
  2. Sort: informational+question → highest score first
  3. Distribute across `total_days` at `blogs_per_day` rate
  4. Apply seasonal overrides (6 weeks before deadline)
- **Output:** `[{type, title, keyword, cluster, score, scheduled_date, article_id, status}]`
- **AI:** None — scheduling algorithm
- **Time:** 2-5s
- **Issues:**
  - No competitor timing analysis
  - Question articles prioritized regardless of score
  - Seasonal override parsing is brittle (requires ISO date format)

### P14 — Dedup Prevention
- **Input:** Calendar from P13, existing_articles list
- **Processing:**
  1. Pass 1: Title dedup (normalize: strip all punctuation, lowercase)
  2. Pass 2: Keyword dedup (same target keyword = same article)
- **Output:** Deduplicated calendar list
- **AI:** None
- **Time:** 1-2s
- **Issues:**
  - Punctuation removal too aggressive ("blood-sugar" → "bloodsugar", "C++" → "C")
  - No semantic/embedding-based dedup — similar titles with different words pass through
  - No fuzzy matching threshold

---

## Data Flow Summary

```
P1 (seed)
 └→ P2 (500-3000 raw keywords)
     └→ P3 (200-400 clean keywords)
         ├→ P4 (entity map)
         ├→ P5 (intent map)
         └→ P6 (SERP map)
             └→ P7 (score map: keyword → 0-100)
                 └→ P8 (topic map: topic_name → [keywords])
                     └→ P9 (cluster map: cluster_name → [topic_names])
                         └→ P10 (pillar map: cluster → {title, keyword, topics})
                             └→ P11 (KnowledgeGraph tree)
                                 ├→ P12 (internal link map)
                                 └→ P13 (content calendar)
                                     └→ P14 (deduplicated calendar)
```

---

## What Frontend Shows per Phase (Current)

| Phase | Summary Line | Expanded Detail | Full Data |
|-------|-------------|-----------------|-----------|
| P1 | seed keyword | — | — |
| P2 | `expanded_count` keywords | sample (10 keywords) | ❌ |
| P3 | `normalized_count` keywords | — | ❌ |
| P4 | `entity_count` entities | — | ❌ |
| P5 | `classified_count`, intent distribution (8 intents) | intent breakdown | ❌ |
| P6 | `serp_analyzed_count` | — | ❌ |
| P7 | `scored_count`, avg score, top 5 keywords | top 5 keywords | ❌ |
| P8 | `topic_count`, first 20 topics with sizes | topic name + size | ❌ |
| P9 | `cluster_count`, first 20 clusters with keyword counts | cluster name + count | ❌ |
| P10 | `pillar_count`, up to 20 pillars with details | pillar name + cluster/kw counts | ❌ |
| P11 | `graph_nodes` count | — | ❌ |
| P12 | `link_count` | — | ❌ |
| P13 | `calendar_entries`, date range | — | ❌ |
| P14 | `deduplicated_count` | — | ❌ |

**❌ = No way to see full data (all keywords, all topics, etc.)**

---

## Known Quality Issues

1. **P8 word-overlap clustering** produces poor topics when keywords don't share words
2. **P9 topic truncation** (`[:60]`) loses data for large universes
3. **P10 pillar naming** only sees `topics[:10]` — misses full cluster context
4. **P12 hardcoded URLs** don't match real site structure
5. **P14 punctuation removal** causes false positive dedup
6. **No semantic similarity** used anywhere in P9-P14
7. **No embedding-based dedup** in P14
8. **Frontend shows summaries only** — no full data visibility
9. **No per-phase edit capability** — can't fix bad clusters/pillars/topics
10. **result_summary for P11/P12** is minimal — graph_nodes/link_count only

---

## Files

| File | Purpose |
|------|---------|
| `engines/ruflo_20phase_engine.py` | Phase class definitions (P1-P20) |
| `engines/ruflo_20phase_wired.py` | `run_seed()` orchestration, gates, SSE emission |
| `frontend/src/workflow/Step3Pipeline.jsx` | Pipeline UI: console + phase cards |
| `main.py` | API endpoints: `/api/ki/{project_id}/run-pipeline`, `/api/runs/{run_id}/stream`, gates |

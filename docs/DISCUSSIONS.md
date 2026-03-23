# AnnaSEO — Design Decisions & Discussions

All major design choices and the reasoning behind them.

---

## D1: Universe → Pillar → Cluster → Keyword hierarchy

**Decision:** 4-level hierarchy, not flat keyword list.

**Why:** A flat list of 2000 keywords has no structure for content planning. The hierarchy gives us:
- Universe = the business's core topic (e.g. "black pepper")
- Pillar = broad authoritative content area (e.g. "black pepper health benefits")
- Cluster = grouped related topics
- Keyword = specific search queries

**Impact:** 20-phase engine, knowledge graph, internal linking, content calendar — all depend on this hierarchy.

---

## D2: Industry enum on strategy engine

**Decision:** `Industry` enum with 12 values in `ruflo_strategy_dev_engine.py`.

**Why:** Different industries need different personas, content angles, and vocabulary. A healthcare project and a spice project cannot share the same prompt templates.

**Impact:** Led directly to the Domain Context Engine — same seed, different industry, different keyword verdict.

---

## D3: Domain Context solves cross-domain problem

**Decision:** Don't add "tour" to GLOBAL_KILL. Create per-project domain profiles instead.

**Why:** "Tour" is a legitimate keyword for a travel business. A global kill list cannot differentiate. The answer is per-project classification using industry-specific cross-domain vocabulary.

**The cinnamon example:**
- Spice project: "cinnamon tour" → REJECT ("tour" = travel, off-domain for spice seller)
- Travel project: "ceylon cinnamon tour" → ACCEPT ("cinnamon" = legitimate tourism attraction in Sri Lanka)
- Both projects share "ceylon cinnamon" as ACCEPT (product + destination are the same thing)

**Impact:** `annaseo_domain_context.py` — inserted at P2 output and P10 output in the pipeline.

---

## D4: Global vs Project tuning separation

**Decision:** Two distinct tuning types with different files, different scope, different approval audiences.

**Global tuning:** touches engine .py files. Fixes code bugs, algorithm thresholds, Layer 1 prompt. Affects all projects. Needs system admin approval.

**Project tuning:** touches `ProjectDomainProfile` config. Fixes per-project keyword and content issues. Affects only that project. Needs project owner approval.

**Rule of thumb:**
- Keyword wrong for THIS business → project tuning
- Keyword universally wrong (meme, viral) → global tuning
- Code bug → global tuning
- Business-specific content angle → project tuning

---

## D5: Data lineage for quality attribution

**Decision:** Every output item tagged with origin phase, function, and trace path.

**Why:** "Cinnamon tour" showed up as a pillar. Which engine produced it? Without a trace chain, you don't know where to fix. With a trace chain:

```
P2._google_autosuggest → fetched "cinnamon tour"
P3_Normalization       → passed through (no filter matched)
OffTopicFilter         → passed through ("tour" not in GLOBAL_KILL)
P8_TopicDetection      → clustered into "Cinnamon Tourism"
P10_PillarIdentification → promoted to pillar
```

The fix is at `OffTopicFilter` (GLOBAL_KILL missing "tour") AND `P10_PillarIdentification.PILLAR_PROMPT` (no domain exclusion). Not at P2 which just fetched what Google gave it.

**Impact:** `annaseo_qi_engine.py` ENGINE_ANATOMY map — every phase's known failure modes documented from reading the actual code.

---

## D6: AI model routing — free tools for coding, Claude only for verification

**Decision:** Gemini + Groq + DeepSeek do all the work. Claude only does final verification.

**Why:**
- Gemini 1.5 Flash: free tier, good at analysis and spec writing
- Groq Llama 3.1: very fast, free tier, good at test generation
- DeepSeek local (Ollama): free, runs on your machine, good at code
- Claude: ~$0.022/article, best quality — worth it for content and final code review

This separation means the quality loop (score → feedback → fix) costs essentially $0. Only content generation and code verification use Claude.

---

## D7: Manual approval gate — non-negotiable

**Decision:** Every production change requires human approval. No exceptions.

**Why:** AI-generated fixes can introduce regressions. The system is self-modifying — if a bad fix gets auto-applied, it could affect all projects. A human must verify.

**Implementation:**
- All tunings → `qi_tunings` table with `status='pending'`
- Frontend shows diff, Claude's confidence score, evidence
- Human clicks Approve → code applied, snapshot saved
- Rollback available instantly — no downtime required

---

## D8: INP replaces FID in SEO audit

**Decision:** Check INP, never FID. FID was removed from Core Web Vitals in March 2024.

**Why:** Google officially removed First Input Delay (FID) from the Core Web Vitals metrics in March 2024 and replaced it with Interaction to Next Paint (INP). Any SEO tool still checking FID is outdated.

**Impact:** `ruflo_seo_audit.py` — all CWV checks use INP.

---

## D9: Schema.org deprecated types

**Decision:** Never generate HowTo or FAQ schema for non-healthcare/gov sites.

**Why:**
- HowTo schema: Google stopped showing rich results for HowTo in September 2023
- FAQPage schema: Restricted to authoritative gov/healthcare sites in August 2023

**Impact:** `ruflo_seo_audit.py` and `ruflo_content_engine.py` — schema generator only creates Article, Product, Organization, LocalBusiness, BreadcrumbList.

---

## D10: JSON-LD only — never Microdata or RDFa

**Decision:** All structured data as JSON-LD. Microdata and RDFa are not supported.

**Why:** Google strongly prefers JSON-LD. It's easier to inject and maintain. Microdata and RDFa are tied to HTML structure and break when HTML changes.

**Impact:** `ruflo_content_engine.py` `SchemaGenerator` — always outputs `<script type="application/ld+json">` blocks.

---

## D11: One-at-a-time publishing

**Decision:** Publisher processes one article at a time, 30s delay between publishes.

**Why:** WordPress and Shopify rate limits. Parallel publishing causes 429 errors. One-at-a-time with retry logic is more reliable.

**Impact:** `ruflo_publisher.py` — SQLite queue, `publish_one_at_a_time()`, 3× retry.

---

## D12: p95 latency, not average

**Decision:** All performance scoring uses p95, not mean.

**Why:** Average hides outliers. An engine that takes 2 seconds 95% of the time but 45 seconds 5% of the time has a terrible user experience. p95 catches the slow tail.

**Impact:** `annaseo_rsd_engine.py` `EngineScorer._score_execution_time()`.

---

## D13: HDBSCAN primary, KMeans fallback

**Decision:** Use HDBSCAN for topic detection, fall back to KMeans if HDBSCAN fails.

**Why:** HDBSCAN doesn't require specifying K (number of clusters). It finds natural density-based clusters and handles noise (-1 cluster). But it's sensitive to parameter choices and can fail on sparse data. KMeans is reliable and deterministic.

**Impact:** `annaseo_addons.py` `HDBSCANClustering` — tries HDBSCAN first, falls back to KMeans.

---

## D14: Memory management — SBERT unloaded after P8

**Decision:** Unload sentence-transformers model from memory after Phase 8 completes.

**Why:** The all-MiniLM-L6-v2 model uses ~380MB RAM. After P8 (topic detection via embeddings), it's not needed. Keeping it loaded for P9–P20 wastes memory and can cause OOM on smaller machines.

**Impact:** `ruflo_20phase_engine.py` `AI.unload_embed_model()` called after P8.

---

## D15: 3-tier caching strategy

**Decision:** L1 in-memory LRU → L2 SQLite disk → L3 .json.gz checkpoint files.

**Why:**
- L1: hot keywords accessed repeatedly within a run
- L2: SERP data (expensive to fetch) cached 14 days
- L3: full phase outputs (crash recovery — can resume from any phase)

**Impact:** `ruflo_20phase_engine.py` `Cache` class.

---

## D16: Content quality gate — 75 threshold all dimensions

**Decision:** Article must score ≥75 on ALL dimensions (SEO, E-E-A-T, GEO, readability) to publish.

**Why:** One weak dimension means the article will underperform. GEO < 75 means AI search won't cite it. E-E-A-T < 75 means Google won't trust it.

**Impact:** `ruflo_content_engine.py` `PUBLISH_THRESHOLD = 75`.

---

## D17: GEO scoring — 8 AI citation signals

**Decision:** Custom GEO scorer with 8 specific signals for AI search citability.

**Signals:**
1. Direct answer in first sentence of H2
2. Specific numbers/statistics per H2
3. Self-contained passages (134–167 words)
4. Fact density (facts per 100 words)
5. Source citations (PubMed, .gov, .edu)
6. Schema markup present
7. Structured lists and tables
8. Bold takeaway statements

**Why:** Perplexity, ChatGPT Search, and Gemini cite passages that are self-contained, factual, and directly answer a question. Generic content doesn't get cited.

**Impact:** `ruflo_content_engine.py` `GEOScorer`.

---

## D18: Brand mention scanner — 7 platforms

**Decision:** Scan for brand mentions on YouTube, Reddit, Wikipedia, LinkedIn, IndiaMART, Quora, Trustpilot.

**Why:** AI search engines (especially Perplexity) look for brand mentions across the web as a trust signal. 3 unprompted brand mentions > 100 backlinks for AI visibility.

**Impact:** `ruflo_seo_audit.py` `BrandMentionScanner`.

---

## D19: Programmatic SEO gates

**Decision:** Warning at 100+ pages, hard stop at 500+ pages.

**Why:** Thin programmatic content (e.g. 10,000 location pages with the same template) triggers Google's spam policies. The gates prevent accidental mass publishing.

**Impact:** `ruflo_seo_audit.py` `ProgrammaticSEOGates`.

---

## D20: llms.txt generation

**Decision:** Auto-generate llms.txt from the knowledge graph.

**Why:** llms.txt (from llmstxt.org) is the emerging standard for telling AI crawlers what content is available and how to access it. Similar to robots.txt but for LLMs.

**Impact:** `ruflo_seo_audit.py` `LLMsTxtGenerator`.

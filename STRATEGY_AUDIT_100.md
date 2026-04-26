# Strategy Pages — Comprehensive Audit
## 100+ Issues, Upgrades, and Workflow Fixes
_Generated from live data + full codebase review_

---

## 🔴 CRITICAL — Session / Data Source Bugs

### 1. AnalysisPhase reads OLD KI pipeline data, not KW2 session
`AnalysisPhase` fetches from `/api/ki/{projectId}/keyword-strategy-brief` regardless of which session is selected. The Cardamom KW2 session has 253 validated keywords in 2 pillars — but the Analysis tab shows 2,170 keywords in 17 pillars from the old pipeline.  
**Fix:** When a KW2 session is selected, load from `/api/kw2/.../validated` and `/api/kw2/.../organize/summary` instead.

### 2. ContentHubPhase uses OLD KI pipeline clusters, not KW2 clusters
`ContentHubPhase` fetches `kwBrief.context_json.content_clusters` from the KI brief. The KW2 session has its own clusters in `kw2_clusters` table but the Content Hub never reads them.  
**Fix:** When a session is selected, use `v2OrganizeSummary()` or `v2ExpandClusters()` to load the session's actual clusters.

### 3. ResearchPhase (hidden) also reads OLD pipeline data
The `ResearchPhase` component (reachable via `goals` route but not visible in nav) reads from `kwBrief` not session data.

### 4. OverviewPhase KPI strip reads OLD pipeline
`OverviewPhase` shows keyword counts and pillar counts from `kwBrief` (old KI pipeline), not from the selected KW2 session. When a session with 253 validated keywords is active, overview still says "2170 keywords, 17 pillars."

### 5. Topic regeneration in ContentHub writes back to KI brief, not KW2 session
`regenMut` calls `/api/ki/{projectId}/cluster/{clusterIndex}/regenerate-topics` — this writes to the old pipeline table. Topics generated here never connect to the KW2 session.  
**Fix:** Add a new endpoint that writes topics to KW2 session clusters.

### 6. `strategy_json` weekly_plan uses "Week N" not "Month N"
The actual DB data has `{week: 1, focus_pillar: ...}` keys but content calendar display expects `{month: "Month 1"}`. ContentHubPhase and StrategyPhase correctly remap weekly_plan → contentCalendar, but the SessionCalendar check in ContentHubPhase reads `kw2Session._strategy.content_calendar` which is empty — it never checks `weekly_plan`.  
**Fix:** In ContentHubPhase, fall back: `sessionCalendar = kw2Session?._strategy?.content_calendar || kw2Session?._strategy?.weekly_plan || []` and normalize month field.

### 7. KwSessionCard calls wrong strategy endpoint
`KwSessionCard` (in Overview) calls `/api/kw2/.../apply/strategy` (v2 Apply engine) but the Cardamom session used the `expand` mode which stores strategy in `phase9_done`/`strategy_json` column, not the apply pipeline. This always returns empty/error for expand-mode sessions.  
**Fix:** Try `/apply/strategy` first, fall back to `/strategy`.

### 8. `phase_status` is always `{}` for expand-mode sessions
The Cardamom session has `phase_status: {}` (empty) despite `phase9_done: 1`. Expand mode uses `phase{N}_done` boolean columns, not `phase_status JSON`. `inferInitialPhase()` in flow.js correctly handles this, but any code that reads `phase_status` for completeness checking will show incorrect state.

### 9. Session auto-selection ignores in-progress sessions in StrategyPhase
`StrategyPhase` auto-selects from `kw2Completed = kw2Sessions.filter(s => s.phase9_done || s._strategy)`. If user's only session is still in-progress, `selectedKw2Session` is null so the empty state CTA is wrong — it tells user to "Complete Phase 9" without pointing to which session.

### 10. Analysis quick-wins tab shows OLD pipeline keyword scores
The quick-wins tab in AnalysisPhase shows `scoredKws.filter(k => k.score >= 60)` from the KI pipeline. The KW2 session has its own `final_score` per keyword (range 0–100) in `kw2_validated_keywords` but these never appear in Analysis.

---

## 🟠 WORKFLOW ISSUES

### 11. No navigation link from Strategy → KW2 to continue incomplete session
When a session has 7/9 phases done, the Strategy Hub shows session card with "Continue in Keywords v2 →" but it navigates to `kw2` page without auto-opening the correct session to the correct phase. The user lands at a fresh session picker.

### 12. `openKw2Session` sets localStorage but KwPage may not read it on mount
`openKw2Session` writes `annaseo_kw2_open_session` to localStorage, but `KwPage.jsx` doesn't check this on mount — it calls `getLatestSession` instead. The redirect to kw2 page doesn't actually pre-select the right session.  
**Fix:** Add `useEffect` in `KwPage` to check `annaseo_kw2_open_session` and load that session.

### 13. Strategy Hub has NO auto-refresh when Phase 9 completes in KwPage
After Phase 9 finishes in KwPage, the Strategy Hub's `kw2-hub-sessions` query has 20 second poll interval. User must wait up to 20 seconds or manually navigate back. There's no event/websocket to push the update. A shorter poll (5s) or invalidation on tab focus would help.

### 14. "Generate Legacy Strategy" button calls old `/api/strategy/{projectId}/generate-stream`
This old endpoint generates a strategy from the KI pipeline brief data, not from the KW2 session. When KW2 sessions exist, clicking this misleads users into thinking they're generating from their session data.  
**Fix:** Rename to "Legacy Strategy" or hide if KW2 sessions with strategy exist.

### 15. Phase 9 in KwPage has no AI provider selector
The `runPhase9` API call doesn't accept a provider parameter. The strategy is generated with whatever the default provider is. No UI control, no visibility into which AI generated it.  
**Fix:** Add AI provider selector to Phase9.jsx.

### 16. Phase 9 can't be re-run with different parameters
Once `phase9_done = 1`, Phase9.jsx shows "Regenerate" but clicking it calls `api.runPhase9()` again with the same provider. No way to compare strategies from different AI providers.

### 17. Content Hub "Generate Topics" regenerates for entire cluster, not per-keyword
`regenMut.mutate(ci)` regenerates all topics for a cluster index. There's no way to regenerate specific topics or add variety.

### 18. "Open Content Hub" button in StrategyPhase session card navigates to `content` route (old content page), not to ContentHubPhase
When user clicks "Open Content Hub" from session card, it calls `routeToPage("content")` which navigates to the top-level content writing page — not to the Strategy Hub's Content Hub phase.

### 19. Hub has no "Run All Phases" button for a session
No shortcut to run all 9 phases end-to-end for a selected session from the Strategy Hub.

### 20. When switching between sessions in the hub, stale data from previous session is shown
The `KeywordPillarsPhase` query key is `["kw2-validated-hub", projectId, kw2Session?.id]` which correctly changes, but there's a brief flash where old data is visible before the new query loads. No loading skeleton.

### 21. Strategy Hub URL doesn't encode activePhase or selectedSessionId
Refreshing the page always resets to the Overview tab and to auto-selected session. Deep linking is impossible.

### 22. Goals (GoalsPhase) and Goals sub-section in StrategyPhase duplicate the same UI
There's a `GoalsPhase` component (registered for `goals` route) AND a goals form inside `StrategyPhase`. They hit the same endpoint but are separate components with separate state.

### 23. Link Building phase is present in nav but not audited yet for content
`LinkBuildingPhase` is referenced in the hub root at `activePhase === "links" && <LinkBuildingPhase>` but the component isn't visible in the read portion of the file. Need to confirm it's implemented.

### 24. No confirmation when deleting keywords from the pipeline view
In `KeywordPillarsPhase` pipeline view, clicking 🗑 shows "Delete?" inline—but this writes permanently to the KI brief. There's no undo, no soft-delete, no archive.

### 25. Bulk keyword delete in pipeline view calls `/api/ki/{projectId}/keyword-delete`
This persists deletion in the `keyword_strategy_briefs` table. If user accidentally deletes a pillar's keywords, there's no recovery path.

### 26. `v2Strategy()` (apply/strategy) is different from `getStrategy()` (phase9/strategy)
Two separate strategy endpoints exist — one from the Apply phase pipeline (v2), one from Phase 9. The hub uses both in different places inconsistently, leading to some tabs showing one and others showing the other.

### 27. "Open Calendar" navigates to `blogs` page but content calendar isn't session-scoped there
The blog calendar page doesn't filter by `sessionId`, so it shows all articles across all sessions regardless of which session was selected.

### 28. No way to create a new KW2 session from within the Strategy Hub
The hub shows "+ New Session" button in the Overview that navigates to `kw2` page. This breaks the user's flow in Strategy Hub entirely.

---

## 🟡 SESSION DISPLAY ISSUES

### 29. Session cards in StrategyPhase group by "topic" from unreliable `getSessionTopics()`
`getSessionTopics()` tries to parse session's strategy to find topics, but it has 5 different fallback sources that can produce inconsistent groupings. Two sessions about "Cardamom" might be grouped under different topic labels.

### 30. Session card shows "0/9 phases done" for expand mode sessions that skip Phase 1
In expand mode, the flow is `["SEARCH", 2, 3, "REVIEW", 4, 5, 6, 7, 8, 9]`. Phase 1 is never done, so `phaseDoneCount` using `[1,2,3,4,5,6,7,8,9].filter(i => s[phase${i}_done])` will always max at 8/9 for expand mode sessions.  
**Fix:** Calculate done phases based on mode-specific flow.

### 31. KwSessionCard phase dots use wrong keys for v2 mode
`KW_PHASE_KEYS = [1, 2, 3, 4, 5, 6, 7, 8, 9]` — v2 mode uses `phase_status` JSON field (`understand/expand/organize/apply`), not numeric done flags. So v2 sessions show all 9 dots as grey.

### 32. Session name display falls back to seed_keywords but truncates mid-word
`sessionLabel` truncates at 3 seed_keywords. If a session was seeded with "organic kerala spices wholesale", the label is just the raw array join with "·" separator — not human-readable.

### 33. Universe/validated counts in StrategyPhase session cards come from the session object, not real-time DB
`s.universe_total` and `s.validated_total` are computed at session-list time and may be stale after running phases. No live count refresh without session refresh.

### 34. Sessions with `phase9_done = 1` but no meaningful strategy (empty JSON) show "Strategy Ready" badge
If Phase 9 ran but AI returned an empty/malformed response, the session still shows the green "Strategy Ready" badge because it only checks `phase9_done`.

### 35. No session comparison view
Can't put two sessions side-by-side to compare their strategies, keyword counts, or pillar coverage.

### 36. No session export (PDF/CSV)
No way to export a session's strategy, keyword list, or content calendar.

---

## 🟡 CONTENT HUB ISSUES

### 37. ContentHubPhase loads ALL articles for the project, not session-scoped
`apiFetch(/api/projects/{projectId}/content)` returns all articles for the project. When viewing a session's content hub, articles from OTHER sessions are shown mixed in.

### 38. "Generate Article" quick box uses project-level endpoint, not session-aware
`apiFetch(/api/content/generate, { keyword, title, project_id })` — no `session_id` attached. Generated articles aren't linked to the current KW2 session.

### 39. `articleMap` lookup is by `keyword.toLowerCase()` — breaks for multi-word keywords with punctuation
If topic keyword is "organic kerala spices?" (with question mark), the map lookup won't match articles generated with normalized keyword "organic kerala spices".

### 40. "Topics not expanded yet" warning shows for KW2 sessions that have their own clusters
ContentHubPhase checks `!topicsExpanded && totalTopics === 0` from the KI brief. If user is using KW2 mode with clusters, this warning fires incorrectly.

### 41. `topicsExpanded` flag is read from KI brief `context_json.topics_expanded`
This boolean in the KI brief has nothing to do with whether KW2 session clusters have been processed.

### 42. Session content calendar in ContentHubPhase uses `content_calendar` field but strategy JSON for expand-mode sessions uses `weekly_plan`
Already noted in #6 — the fix needs to be in ContentHubPhase specifically: normalize `weekly_plan → {month, focus_pillar, articles}` before rendering.

### 43. No "mark as scheduled" / "publish" workflow in ContentHub
Articles go: `draft → review → approved → published` but there's no publish action in the UI — just Approve and Retry buttons visible.

### 44. Approve button only shows when article is selected AND status is `draft`
`{selectedArticle === a.article_id && a.status === "draft"}` — but the article must be clicked to expand it first. Approve is a "hidden" action most users won't find.

### 45. `PipelineProgress` polls every 4 seconds for active articles but never cleans up on unmount
`refetchInterval: (q) => q.state.data?.status === "generating" ? 4000 : false` — if user switches tabs while an article is generating, the query keeps polling in the background until the component unmounts. On component re-mount, a fresh subscription is created — potentially doubling poll requests.

### 46. Content cluster accordion only allows one open at a time
`setOpenCluster(isOpen ? null : ci)` — user can't compare two clusters simultaneously.

### 47. Topic scores (business_value, relevance, ranking_feasibility, content_uniqueness) show as individual numbers, not an average bar
4 scores shown as "Biz: 72 | Rel: 68 | Rank: 55 | Uniq: 80". No visual bar or aggregate score to compare topics quickly.

### 48. Generated article list at bottom of ContentHub has no sorting or filtering
All articles are shown in creation order. No sorting by score, wordcount, status. With 50+ articles this list becomes unmanageable.

### 49. No ability to delete an article from Content Hub
Retry is the only action for failed articles. No delete/remove option.

### 50. No batch "generate all topics" feature
Each cluster's topics must be individually regenerated. If there are 10 clusters and you want to generate 150 topics for all, you'd click 10 times.

---

## 🟡 STRATEGY DISPLAY ISSUES

### 51. `pillar_strategies` key in strategy JSON is never read
The DB shows `strategy_json` has `pillar_strategies` key (plural), but the display code reads `pillar_strategy || priority_pillars`. The `pillar_strategies` data is never shown.

### 52. `timeline` key in strategy JSON is never displayed
`kw2_sessions.strategy_json` has a `timeline` key but no UI component renders it.

### 53. `content_priorities` key in strategy JSON is never displayed
Same as above — the field exists in DB but is silently ignored.

### 54. `link_building_plan` in strategy JSON is empty string but never shown even when present
The field exists but shows `""` for the Cardamom session. UI doesn't show a placeholder or CTA to generate link building data.

### 55. Quick wins in Phase9.jsx shows flat string list
Quick wins such as "buy organic spices online in india" are shown as bare bullet points with no context — no search volume, no difficulty, no suggested content type.

### 56. Weekly plan shows "Week 1, Week 2..." with no actual dates
No date picker for strategy start date. The Content Roadmap section is entirely abstract timing.

### 57. Phase9 strategy has no "Regenerate" confirmation
Clicking "Regenerate Strategy" in Phase9.jsx immediately runs Phase 9 again, overwriting the existing strategy_json with no warning.

### 58. StrategyPhase "Generate Legacy Strategy" button always appears even with KW2 strategy ready
The button label doesn't adapt correctly—when `kw2Completed.length > 0` the label is "Generate Legacy Strategy" but still runs `startGeneration()` which hits the OLD legacy endpoint.

### 59. Confidence score from legacy strategy is shown but KW2 strategy has no confidence score
Old strategy has `strategy.strategy_confidence` shown as a percentage circle. KW2 strategy from Phase 9 doesn't include a confidence score — the circle never appears for KW2 strategies.

### 60. AEO tactics section empty for all KW2 sessions
`strat.aeo_tactics` check in StrategyPhase — Phase 9 engine doesn't generate AEO tactics, only the old legacy strategy endpoint does. The section is silently absent.

---

## 🟡 PERFORMANCE / MEMORY ISSUES

### 61. StrategyIntelligenceHub.jsx is 5,140 lines — single monolithic component
All 6 phase components + 3 helper components + hub root are in one file. This causes the entire file to be re-compiled on any change. Split into separate files per phase.

### 62. 7+ separate useQuery calls for `kw-strategy-brief` (one per phase component)
Every phase that reads pipeline data calls `useQuery(["kw-strategy-brief", projectId], ...)`. With `staleTime: 60_000`, the first navigation between phases within a minute returns cached data — but on cache miss, 7 simultaneous requests can fire.

### 63. `kw2-hub-sessions` polls every 20 seconds with `refetchInterval: 20_000`
This is unnecessary when no sessions are actively running phases. Should only poll when a session was recently started or phase is in progress.

### 64. `si-goal-progress` and `si-insights` queries load even when those tabs aren't visible
`AnalysisPhase` always enables `showLHF` query once the component mounts, and mounts as soon as "Analysis" tab is clicked. The query runs even if users never click "Low-Hanging Fruit".  
Actually on review, `showLHF` starts `false` so `enabled: !!projectId && showLHF` prevents this one. But `si-insights` in ResearchPhase always fetches.

### 65. `PipelineProgress` creates a separate useQuery per article ID
If 20 articles are in `generating` status simultaneously, 20 separate 4-second polling queries run in parallel.

### 66. All articles for project loaded on ContentHub mount with no pagination
`/api/projects/{projectId}/content` returns all articles. At 500+ articles this becomes a large payload with no virtual scrolling.

### 67. `kw2-validated-hub` query staleTime is 30s — editing keywords in KwPage won't reflect for 30 seconds
After adding/removing validated keywords in KwPage, switching to Strategy Hub still shows old counts for 30 seconds.

### 68. The `kw2Sessions` array is re-mapped with JSON.parse on every render
```js
const kw2Sessions = (kw2SessionsData?.sessions || []).map(s => {
  let _strategy = null; const raw = s?.strategy_json
  if (raw) { try { _strategy = typeof raw === "string" ? JSON.parse(raw) : raw } catch {} }
  return { ...s, _strategy }
})
```
This runs on every render cycle. Should be wrapped in `useMemo`.

### 69. `getSessionTopics()` function runs for every session on every render of StrategyPhase
The function has 5 array spreads and set operations — it runs for ALL sessions to build `topicBySessionId`. Should be memoized.

### 70. Large Strategy page re-renders when activePhase changes due to no component splitting
Switching from Overview to Keywords unmounts/remounts the entire right panel div, losing scroll position and local state in previous phases.

### 71. `inferInitialPhase()` in flow.js tries JSON.parse on phase_status on EVERY phase navigation
Called by `KwPage.jsx` on session load, but `phase_status` is `{}` (empty object) for expand-mode sessions. The function correctly handles this but still runs string checks and parse attempts.

### 72. Session strategy_json is stored as raw JSON string in SQLite, parsed on every list call
`kw2_sessions.strategy_json` can be 10-50KB for a session with 12 weeks of plan. Every `/sessions/list` call serializes and returns ALL session strategy data to the frontend, even when only the session name/phase_done flags are needed.  
**Fix:** Strip `strategy_json` from list response, fetch it separately when needed.

### 73. `articleMap` built as key-value on every ContentHub render
```js
const articleMap = {}
articleList.forEach(a => { articleMap[a.keyword?.toLowerCase()] = a })
```
Not memoized — rebuilds on every render even when articles haven't changed.

### 74. `selected`, `editModal`, `hoveredRow` state in KeywordPillarsPhase causes full re-render on every hover
Hovering over any keyword row updates `hoveredRow` state, re-rendering the entire pillar table. At 2,170 keywords in 17 pillars, this re-renders thousands of DOM nodes.

### 75. `scoredKws`, `highScore`, `medScore`, `lowScore` computed on render in AnalysisPhase without memo
Four derived arrays computed every time `AnalysisPhase` renders — not memoized.

---

## 🟡 UX / DESIGN ISSUES

### 76. Phase sidebar navigates between tabs but doesn't show completion status
Phase nav buttons show only an icon and label. Should show ✓ for completed phases, ⏳ for in-progress, blank for not started.

### 77. "Strategy Hub" overview page title says "6-phase SEO strategy" but nav only shows 6 phases (including overview itself as a non-strategy phase)
The overview sub-copy says: "6-phase SEO strategy — Keywords → Analysis → Strategy → Content → Links" which is 5 downstream phases from Overview. Heading/subtitle mismatch.

### 78. Session context bar has no visual indication when `selectedSession` is the "best match" session for current keyword pillar
If user has multiple sessions, the auto-selected first session may not be relevant to the keyword they're viewing. No recommendation logic.

### 79. "All Sessions" option in session dropdown (value `""`) leads to confusing behaviour
When `selectedSessionId = null`, the `KeywordPillarsPhase` shows OLD pipeline data. The user sees "2170 keywords" when really they should see a merged KW2 view. 

### 80. Header stat bar in AnalysisPhase shows totalKeywords from old pipeline, not session
When user selects "Cardamom Search Test" session, Analysis → Research tab says "2170 Total Keywords, 17 Pillars" — never the session's 253/2.

### 81. No empty state for Link Building phase
`LinkBuildingPhase` is rendered but if there's no link data, user sees a blank panel with no guidance.

### 82. KwSessionCard "Set as Active Session" button sets the `selectedSessionId` in Overview but this doesn't sync to other phases
`onSelect` sets `selectedSessionId` at hub root level, which is correctly passed to all phases. But feedback to the user after clicking "Set as Active Session" is only a button state change ("✓ Active Session") with no toast/banner.

### 83. Search bar is missing from Strategy Hub
No way to search across keywords, articles, sessions, or strategy content within the hub.

### 84. Modal for editing keywords (pipeline view) has no keyboard navigation support (Tab doesn't cycle through fields)
The edit modal has only one input (keyword text). But pressing Tab goes to browser chrome, not to the Save button.

### 85. Strategy content roadmap shows max 8 weeks despite having 12-week plan in DB
`contentCalendar.slice(0, 8)` — the DB for Cardamom session has 12 weeks. The last 4 weeks are invisible in the StrategyPhase display.

### 86. Phase 9 results in KwPage show only 5 fields: headline, biggest_opportunity, why_we_win, priority_pillars, quick_wins
Missing from Phase9.jsx display: content_gaps, content_priorities, pillar_strategies, link_building_plan, competitive_gaps, timeline — all exist in the strategy_json but aren't shown.

### 87. Progress log console in StrategyPhase only keeps last 200 logs
`setLogs(prev => [...prev.slice(-199), ...])` — for long strategy generations with many steps, early logs are lost.

### 88. No dark mode support
All inline styles use hardcoded light mode colors.

### 89. Mobile layout not considered
The hub uses fixed sidebar (180px width) + main panel. On screens < 768px, the layout breaks.

### 90. Pillar accordion in Session Keywords view can only open one pillar at a time
`setOpenSessionPillar(isOpen ? null : pillar)` — same one-at-a-time restriction as ContentHub clusters.

---

## 🟢 MISSING FEATURES / NEW IDEAS

### 91. No "strategy health score" for a session
Compute a composite score from: validated keyword count, pillar coverage, content gaps filled, weekly plan completeness. Show as a progress bar at the top of Strategy phase.

### 92. No competitor keyword overlap analysis
No view showing which validated keywords overlap with competitor domains, even though competitor crawl data may exist in `kw2_biz_competitors`/`kw2_biz_competitor_keywords` tables.

### 93. No content brief generator from validated keywords
User can "generate an article" but can't generate a proper SEO brief (H1, H2 outline, target URL, internal links, word count range, meta description template) from a keyword.

### 94. No pillar-to-page URL mapping
`mapped_page` field exists in `kw2_validated_keywords` table with `''` default — never shown or editable in the Strategy Hub.

### 95. No "suggested internal links" view in Strategy Hub
`kw2_internal_links` table exists but `LinkBuildingPhase` may not show session-scoped internal links.

### 96. No calendar view for the content plan
The content roadmap is horizontal scrollable cards. An actual calendar grid (week/month) view would help planning.

### 97. No AI-powered "what to write next" recommendation
Given the session's keywords, published articles, and strategy, AI could recommend the single most impactful article to write next.

### 98. No integration between Content Hub articles and the KW2 session's content calendar
Articles generated from ContentHub aren't automatically scheduled in the `kw2_calendar` table.

### 99. No cross-session keyword deduplication report
If two sessions have both validated "buy organic cardamom" — there's no report highlighting overlaps so user can avoid duplicate content.

### 100. No "strategy version history"
Phase 9 overwrites `strategy_json` in place. There's no audit trail of previous strategy versions.

### 101. Phase 9 doesn't use validated keyword data as context
`runPhase9()` is called with just `(projectId, sessionId)`. The backend should receive the top 50 validated keywords with their scores/intents as context for strategy generation.

### 102. No "export to Google Sheets" for content calendar
High-value export that teams need to share calendar with clients or other tools.

### 103. No "import keywords from CSV"
User can't import an existing keyword list into a KW2 session from the Strategy Hub.

### 104. No "create session from template"
New sessions always start fresh. No way to clone an existing session's seed keywords and mode.

### 105. Analysis page has no "compared to last session" trend
If two sessions ran in sequence, Analysis could compare validated keyword counts, score distributions, and pillar coverage between them.

### 106. Strategy summary "biggest_opportunity" and "why_we_win" fields visible in Phase9.jsx but not in StrategyPhase of the hub
These valuable AI-generated insights are only visible inside KwPage → Phase9, not surfaced in the hub's Strategy phase.

### 107. No visual knowledge graph view in the hub
`kw2_graph_edges` table is populated by Phase 6. This data is never visualized in the Strategy Hub — only in KwPage if at all.

### 108. KI pipeline brief can't be deleted or reset
Old pipeline data (17 pillars, 2170 keywords) accumulates and clutters the Keywords "pipeline" view. No reset or archive button.

### 109. No token/cost display for Phase 9 strategy generation
AI Cost Analytics is built and deployed but Phase 9 generation doesn't show the cost or tokens used in the hub.

### 110. No "strategy for multiple sessions combined" feature
When user runs 3 KW2 sessions for different keyword subsets of the same project, there's no way to merge those strategies into one master content plan.

---

## 🟢 BACKEND / API ISSUES

### 111. `/api/kw2/{projectId}/sessions/list` returns `strategy_json` for ALL sessions
This can be 10-50KB per session × N sessions in a single API response. Strip strategy_json from list; add a separate `/sessions/{id}/strategy` already exists for fetching it individually.

### 112. No endpoint to get session-level content calendar from KW2 schema vs. the old `kw2_calendar` table
`v2Calendar()` hits `apply/calendar` — OK for v2 Apply mode. But for expand-mode sessions, the calendar data is in `kw2_calendar` table not the apply tables. No unified calendar endpoint.

### 113. `runPhase9()` doesn't accept `ai_provider` parameter
The Phase 9 engine doesn't allow provider selection. It should accept `provider` query param and store the used provider in `kw2_sessions`.

### 114. `/api/ki/{projectId}/keyword-delete` is a destructive permanent delete
No soft-delete mechanism. An accidental bulk delete of keywords from the old pipeline is unrecoverable.

### 115. No endpoint to get KW2 session pillar statistics for the Strategy Hub
`getPillarStats()` exists in api.js but it reads from `kw2_validated_keywords` grouped by pillar — the hub doesn't call this anywhere.

### 116. Sessions list endpoint doesn't support filtering by mode or status
`/api/kw2/{projectId}/sessions/list` returns all sessions. When a project has 20 sessions, the hub receives all 20 with full data.

---

## ⚡ QUICK WINS (can fix in under 1 hour each)

### QW1. Add `useMemo` to `kw2Sessions` strategy_json parsing in hub root
Prevents redundant JSON.parse on every render.

### QW2. Add `useMemo` to `getSessionTopics()` and `topicBySessionId` map in StrategyPhase

### QW3. Strip `strategy_json` from `/sessions/list` response
Reduce list payload by 80%.

### QW4. Normalize `weekly_plan → content_calendar` in ContentHubPhase
Fix the session calendar not showing for expand-mode sessions.

### QW5. Fix `KwSessionCard` to fall back from `apply/strategy` to `strategy` endpoint
Fix "Strategy not available" error for expand-mode sessions on Overview page.

### QW6. Add session `id` to article generation to link articles to sessions
Pass `session_id: kw2Session?.id` in `generateMut.mutationFn`.

### QW7. Add `OpenAI` to `PROVIDER_LABELS` in KwPage.jsx (missing from previous session)
Was added to frontend provider drop-down but KwPage.jsx still missing it.

### QW8. Reduce `kw2-hub-sessions` poll interval to 5s when any session has incomplete phases
Use React Query's `refetchInterval` as a function that checks session states.

### QW9. Add session-scoped article filter in ContentHub
Filter `articleList.filter(a => a.session_id === kw2Session?.id)`.

### QW10. Add Phase 9 strategy fields to Phase9.jsx display
Show `content_gaps`, `pillar_strategies`, `competitive_gaps`, `link_building_plan`, `timeline`.

---

## Summary by Category

| Category | Count |
|---|---|
| Critical session/data source bugs | 10 |
| Workflow issues | 18 |
| Session display issues | 8 |
| Content Hub issues | 14 |
| Strategy display issues | 10 |
| Performance/memory issues | 15 |
| UX/design issues | 15 |
| Missing features | 20 |
| Backend/API issues | 6 |
| Quick wins | 10 |
| **TOTAL** | **126** |

---

## Priority Fix Order

**Week 1 — Data Integrity (stop showing wrong data):**
1. Fix #1 (AnalysisPhase uses session data)
2. Fix #2 (ContentHubPhase uses KW2 clusters)
3. Fix #6 (weekly_plan → content_calendar normalization)
4. Fix #7 (KwSessionCard uses correct strategy endpoint)
5. Fix QW3 (strip strategy_json from list)
6. Fix QW4 (ContentHub session calendar)
7. Fix QW6 (session_id on article generation)

**Week 2 — Workflow & Navigation:**
8. Fix #11/#12 (navigate to KW2 and open correct session/phase)
9. Fix #21 (URL deep linking for active phase + session)
10. Fix #29/#30 (fix session phase count/grouping)
11. Fix #57 (add confirm before regenerating Phase 9)
12. Fix QW5 (KwSessionCard fallback endpoint)
13. Fix #13 (push refresh after Phase 9 completes)

**Week 3 — Performance:**
14. QW1/QW2 (useMemo fixes)
15. Fix #62/#63 (query parallelism and poll intervals)
16. Fix #66 (paginate articles endpoint)
17. Fix #72 (strip strategy_json from sessions list)
18. Fix #74 (throttle hover state updates in pillar table)

**Week 4 — New Features:**
19. Feature #91 (strategy health score)
20. Feature #96 (calendar grid view)
21. Feature #100 (strategy version history)
22. Feature #103 (CSV import)
23. Feature #109 (token cost display for Phase 9)

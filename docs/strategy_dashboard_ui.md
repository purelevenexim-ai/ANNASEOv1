# Strategy Dashboard UI — Design & Implementation

Purpose
-------
Visual decision system for strategy review, prioritization, and execution.

Main page structure
-------------------
Dashboard
 ├── Strategy Overview
 ├── Priority Queue (timeline)
 ├── Content Briefs
 ├── Gap Opportunities
 ├── Internal Link Map
 └── Predictions

Key components
--------------
1. Strategy Overview (top block)
- Show `confidence`, `biggest_single_opportunity`, `critical_insight`.

2. Priority Queue
- Timeline view grouped by week, article cards with KD, why_this_week, CTA to freeze/approve.

3. Gap Opportunities
- Badge list of missing topics discovered by Gap Engine with quick-brief generator action.

4. Content Briefs view
- Accordion list: H2 structure, word targets, FAQs, entities to include.

5. Internal Link Graph
- Use `react-flow` or `d3` to render pillar → cluster → article → product graph.

6. Predictions chart
- Line chart (12 months) with top-3/top-10 keyword counts (use `recharts`).

7. Job progress UI
- Show `<Progress value={progress} />` and `currentPhase` from `/api/jobs/{job_id}`.

React snippets (examples)

Strategy Overview
```jsx
<Card>
  <h2>Strategy Score: {confidence}%</h2>
  <p>Biggest Opportunity: {strategy.biggest_single_opportunity}</p>
  <p>Insight: {strategy.critical_insight}</p>
</Card>
```

Priority Queue (render)
```jsx
{queue.map(week => (
  <div key={week.week}>
    <h3>Week {week.week}</h3>
    {week.articles.map(a => (
      <Card key={a.target_keyword}>
        <h4>{a.title}</h4>
        <p>KD: {a.kd_estimate}</p>
        <p>{a.why_this_week}</p>
      </Card>
    ))}
  </div>
))}
```

Gap Opportunities
```jsx
<Card>
  <h3>Content Gaps</h3>
  {gaps.map(g => <Badge key={g}>{g}</Badge>)}
</Card>
```

Content Briefs (accordion)
```jsx
{briefs.map(b => (
  <AccordionItem key={b.article_title}>
    <h4>{b.article_title}</h4>
    <ul>{b.h2_structure.map(h => <li key={h}>{h}</li>)}</ul>
  </AccordionItem>
))}
```

Internal link graph
- Use `react-flow` nodes for pillars and cluster articles; allow drag & drop to adjust internal link suggestions.

Job progress polling (simple)
```js
useEffect(() => {
  const t = setInterval(async () => {
    const res = await fetch(`/api/jobs/${jobId}`)
    const data = await res.json()
    setJob(data)
  }, 1500)
  return () => clearInterval(t)
}, [jobId])
```

UX principles
-------------
- Show decisions (what to publish), not engine internals
- Keep controls business-facing: "Find Opportunities", "Lock Strategy", "Build First"
- Provide clear preview vs final actions: Strategy page = preview; Keyword page = execution

Integration notes
-----------------
- Backend endpoints to supply aggregates: `/api/dashboard/summary`, `/api/dashboard/opportunities`, `/api/strategy/{id}/briefs`
- Use limited sample sizes for preview endpoints to keep latency low
- Provide CSV/export and schedule publishing API for content calendar

Accessibility & performance
---------------------------
- Lazy-load heavy graphs and briefs
- Server-side paginate long lists (scored keywords)
- Add aria labels and keyboard navigation for accordion and graph

This doc is a concise, implementable UI spec that maps directly to the strategy outputs produced by the backend engines.

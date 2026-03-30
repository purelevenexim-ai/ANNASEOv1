# AnnaSEO — Ranking Intelligence

Automated GSC ranking import, drop detection, Claude-powered diagnosis, and 12-month prediction display.

---

## Data Flow

```
GSC OAuth sync  →  ranking_history table
                →  compare to previous snapshot
                →  create ranking_alerts where |delta| > threshold
                →  RankingMonitor.diagnose_drop() on critical alerts (optional)
```

---

## Tables

### ranking_history

Snapshot per keyword per sync run.

```sql
id, project_id, keyword, position, ctr, impressions, clicks, recorded_date
```

### ranking_alerts

Created whenever a keyword position drops beyond the configured threshold.

```sql
id, project_id, keyword, old_position, new_position, change,
severity, status, diagnosis_json, created_at
```

**Severity levels:**

| Severity | Condition |
|----------|-----------|
| `critical` | Dropped >5 positions AND new position is below #5 |
| `high` | New position crossed below #5 |
| `warning` | New position crossed below #10 |

**Status flow:** `new` → `acknowledged` → `fixed`

### ranking_predictions

Populated automatically when a strategy session completes.

```sql
id, project_id, keyword, pillar, predicted_rank, predicted_month, confidence, created_at
```

---

## API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/rankings/{project_id}/record` | Save a ranking snapshot row |
| GET  | `/api/rankings/{project_id}/history` | All keywords, last 90 days |
| GET  | `/api/rankings/{project_id}/history/{keyword}` | Single keyword history |
| GET  | `/api/rankings/{project_id}/alerts` | List alerts (filter: severity, status) |
| POST | `/api/rankings/{project_id}/alerts/{id}/acknowledge` | Mark alert seen |
| POST | `/api/rankings/{project_id}/alerts/{id}/diagnose` | Claude diagnosis |
| GET  | `/api/rankings/{project_id}/predictions` | 12-month predictions |
| POST | `/api/rankings/{project_id}/check-alerts` | Manual alert scan |
| GET  | `/api/rankings/{project_id}/dashboard` | Combined: rankings + alerts + trends |
| GET  | `/api/rankings/{project_id}/top-movers` | Biggest gainers/losers this week |
| GET  | `/api/rankings/{project_id}/by-pillar` | Rankings grouped by pillar |

---

## Alert Thresholds

Default drop threshold: **5 positions**. Configurable per project (future: project_settings.alert_threshold).

---

## Claude Diagnosis

`POST /api/rankings/{project_id}/alerts/{alert_id}/diagnose` calls `RankingMonitor.diagnose_drop()` from `ruflo_final_strategy_engine.py`.

Response shape stored in `ranking_alerts.diagnosis_json`:

```json
{
  "root_cause": "...",
  "fixes": [
    { "action": "...", "instruction": "...", "priority": "high|medium|low", "expected_impact": "..." }
  ],
  "estimated_recovery_weeks": 4
}
```

Cost: ~$0.01–0.03 per diagnosis (Claude Sonnet).

---

## Frontend: RankingsPage

Located as a tab within `KeywordsUnifiedPage` (App.jsx).

### Tabs

| Tab | Content |
|-----|---------|
| Overview | Stat cards (Top3/Top10/Top20/Alerts), top movers widget, 12-month prediction grid |
| Alerts | Alert list with severity badges, per-alert Claude diagnosis, acknowledge button |
| Predictions | Per-pillar confidence cards, month-by-month rank forecast |

### Stat cards

- **Keywords in Top 3** — position ≤ 3
- **Keywords 4–10** — position 4–10
- **Keywords 11–20** — position 11–20
- **Active Alerts** — unacknowledged alerts count

### Auto-refresh

Polls for new alerts every 5 minutes while the Rankings tab is active.

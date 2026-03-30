# Gate 2 Integration - End-to-End Testing Guide

## Quick Start (10 minutes total)

### Prerequisites
- Python 3.9+ with all dependencies installed
- Node.js 18+ with npm
- Ollama running locally (or comment out in system-status)
- Fresh database or test project

### Step 1: Start Backend (Terminal 1)

```bash
cd /root/ANNASEOv1
python3 main.py
```

Expected output:
```
✓ Database connected
✓ Alembic migrations up to date
✓ API running on http://localhost:8000
✓ WebSocket ready
```

### Step 2: Start Frontend (Terminal 2)

```bash
cd /root/ANNASEOv1/frontend
npm run dev
```

Expected output:
```
  VITE v... dev server running at:
  ➜ Local: http://localhost:5173/
```

### Step 3: Access Application
Open browser: `http://localhost:5173`

---

## Test Scenario 1: Basic Gate 2 Flow (30 minutes)

### Objective
Verify that pillar confirmation modal appears after P10 and data persists.

### Steps

1. **Create Test Project**
   - Click "New Project"
   - Name: "Gate2TestProject"
   - Niche: "SEO Tools"
   - Click Create

2. **Complete Steps 1-4**
   - Step 1: Enter domain (any domain, e.g., example.com)
   - Step 2: Set initial keywords (3-5 keywords, e.g., SEO tool, keyword research)
   - Step 3: Enter intent (informational)
   - Step 4: Confirm (can leave blank or add notes)

3. **Start Pipeline**
   - Click "Run Full Pipeline"
   - Watch console output stream in real-time
   
   Expected phases:
   - P1-P3: Universe Keywords (should complete in 10-30s)
   - P4-P8: Domain Assessment (5-15s)
   - P9-P10: Pillar Identification (15-30s)
   
   **Console should show color-coded output:**
   ```
   [TEAL] P1 Complete | Universe Keywords | 5 items | 2.1s
   [CYAN] P2 Complete | Intent Analysis | 5 items | 1.8s
   [BLUE] P3 Complete | Initial Filtering | 4 items | 1.2s
   ...
   [🎯] P9 Complete | Initial Clustering | 5 pillars | 5.3s
   [🏆] P10 Complete | Pillar Keyword Extraction | 5 items | 4.7s
   ```

4. **Verify Gate 2 Modal Appears**
   
   **Expected:** After P10 completes, modal should popup with:
   - Title: "Confirm Pillar Structure"
   - Table with 5 rows (one per pillar)
   - Columns: Cluster Name | Pillar Title | Pillar Keyword | Topics | Article Count
   
   Example:
   ```
   | Cluster Name      | Pillar Title              | Pillar Keyword     | Topics | Articles |
   |-------------------|---------------------------|-------------------|--------|----------|
   | Content Planning  | Keyword Research Methods  | keyword research   | 3      | 12       |
   | On-Page SEO       | Technical SEO Basics      | technical seo      | 4      | 18       |
   | Link Building     | Backlink Strategy         | backlinks          | 3      | 8        |
   | Tools & Software  | SEO Tools Comparison      | seo tools          | 5      | 25       |
   | Metrics & Analytics| Ranking Tracking         | rank tracking      | 3      | 10       |
   ```

5. **Test Edit Operations**
   - Click edit icon on first pillar
   - Change "Pillar Title" to something different (e.g., "Advanced Keyword Research")
   - Click save ✓
   - Verify change persists in table
   
6. **Test Delete**
   - Click delete icon on any pillar
   - Click confirm
   - Row should disappear
   - Count should decrease (5 → 4)

7. **Test Add New Pillar**
   - Click "Add Pillar" button
   - Fill in form:
     - Cluster: "Content Distribution"
     - Title: "Social Media SEO"
     - Keyword: "social signals"
     - Topics: 2
     - Articles: 5
   - Click Save
   - New row should appear in table

8. **Confirm Pillars**
   - Click "Confirm Pillar Structure" button
   - Optional: Add notes (e.g., "Looks good, ready for keywords")
   - Click Submit
   
   **Expected:**
   - Modal closes
   - Console shows: `[✓] P11 Starting | Knowledge Graph Building...`
   - Pipeline resumes (should skip P9-P10)
   - Status badge shows "✓ Confirmed"

### ✓ Success Criteria
- [ ] Modal appears after P10 completes
- [ ] 5 pillars display correctly
- [ ] Edit operations work
- [ ] Delete operations work
- [ ] Add new pillar works
- [ ] Confirmation saves to database
- [ ] Pipeline resumes to P11 (not P9-P10)
- [ ] Console shows appropriate phase descriptions

---

## Test Scenario 2: Cancel & Resume (20 minutes)

### Objective
Verify that canceling Gate 2 allows resume later without restarting pipeline.

### Steps

1. **Start from Test Scenario 1 Step 3**
   - Run pipeline to Gate 2 modal
   - Gate 2 modal appears

2. **Cancel Confirmation**
   - Click "Cancel" button (or press ESC)
   
   **Expected:**
   - Modal closes
   - Pipeline pauses (status shows "waiting_gate")
   - Console stops emitting events

3. **Verify Wait State**
   - Status badge should show "⏳ Waiting for Confirmation"
   - Run card should not disappear
   - No new phase logs in console

4. **Resume Later**
   - Wait 10 seconds
   - Click the run card again
   - Modal should reappear with SAME pillars (from database)
   
   **Expected:**
   - Data persisted: Same 5 pillars, same values
   - No P9-P10 re-execution (uses DB cache)

5. **Confirm This Time**
   - Make a small edit (change article count on one pillar)
   - Click Confirm
   
   **Expected:**
   - Modal closes
   - Pipeline resumes to P11
   - Console shows: `[🎯] P11 Starting...`

### ✓ Success Criteria
- [ ] Cancel pauses pipeline without error
- [ ] Pillars persist in database
- [ ] Reopening modal shows same data
- [ ] No re-execution of P9-P10
- [ ] Confirmation resumes from P11 (not P9)

---

## Test Scenario 3: SSE Streaming & Real-time Console (15 minutes)

### Objective
Verify Server-Sent Events (SSE) stream phase logs correctly to browser.

### Steps

1. **Open Browser DevTools**
   - Press F12
   - Go to Network tab
   - Filter: Type "stream" or look for "stream" request

2. **Start Pipeline**
   - Click Run Full Pipeline
   - Watch Network tab
   
   **Expected:**
   - Request to `GET /api/runs/{run_id}/stream`
   - Status: 200
   - Content-Type: text/event-stream

3. **View Console Output**
   - In Network tab, click the stream request
   - Go to "Events" tab (or "Response" in some browsers)
   
   **Expected output pattern:**
   ```
   data: {"phase":"P1","status":"complete","msg":"✓ P1 Complete | Universe Keywords | 5 items | 2.1s","color":"teal","elapsed_ms":2100,"output_count":5}
   
   data: {"phase":"P2","status":"running","msg":"⏳ P2 Running | Intent Analysis...","color":"cyan","elapsed_ms":450,"output_count":0}
   
   data: {"phase":"P2","status":"complete","msg":"✓ P2 Complete | Intent Analysis | 0 items | 1.8s","color":"cyan","elapsed_ms":1800,"output_count":0}
   
   ... continues until P10 complete ...
   
   data: {"phase":"GATE_2_READY","status":"waiting","msg":"🎯 Waiting for customer pillar confirmation at Gate 2","color":"orange","elapsed_ms":0}
   ```

4. **Verify Color Coding**
   - P1-P3 should have "teal" color
   - P4-P6 should have "cyan" color
   - P9-P10 should have different colors
   - Gate 2 should have "orange" color
   
   Frontend should display in console with matching colors:
   - Teal text for P1-P3
   - Cyan text for P4-P6
   - etc.

5. **Check Timing Accuracy**
   - Each phase should show realistic elapsed_ms
   - Should increment between phase updates
   - memory_delta_mb should track memory changes

### ✓ Success Criteria
- [ ] SSE connection established (status 200)
- [ ] Events stream continuously (not blocked)
- [ ] JSON payloads valid (parse without errors)
- [ ] Color codes match phase ranges
- [ ] Timing data increments correctly
- [ ] Phase descriptions are readable

---

## Test Scenario 4: Database Persistence (10 minutes)

### Objective
Verify that Gate 2 confirmations persist in database across server restarts.

### Steps

1. **Complete Gate 2 Confirmation**
   - Follow Test Scenario 1 steps 1-8
   - Confirm pillars
   - Note the run_id (should be in URL or card)

2. **Check Database**
   - Open new terminal
   - Run SQL query:
   ```bash
   sqlite3 /root/ANNASEOv1/annaseo.db
   ```
   
   Query:
   ```sql
   SELECT * FROM gate_states WHERE gate_number = 2 AND run_id = '{YOUR_RUN_ID}';
   ```
   
   **Expected output:**
   ```
   id | run_id | gate_number | input_json | customer_input_json | confirmed_at
   -- | ------ | --- | ... | ... | 2024-XX-XX HH:MM:SS
   ```
   
   Check that `customer_input_json` contains your confirmed pillars with edits.

3. **Restart Server**
   - Kill backend (Ctrl+C in Terminal 1)
   - Wait 3 seconds
   - Restart: `python3 main.py`
   
   **Expected:**
   - Fresh server instance
   - Database still loaded
   - No errors on startup

4. **Verify Persistence**
   - Go to frontend (should still be running on 5173)
   - Create NEW pipeline run
   - Get to Gate 2 again
   
   Run query over `runs.run_data`:
   ```sql
   SELECT pillars_json FROM runs WHERE run_id = '{OLD_RUN_ID}';
   ```
   
   **Expected:**
   - Old run's pillars still in database
   - Can retrieve them via API: `GET /api/runs/{old_run_id}/gate-2`

### ✓ Success Criteria
- [ ] Gate 2 data saved to database
- [ ] customer_input_json contains pillar list with edits
- [ ] Server restart doesn't lose data
- [ ] GET /api/runs/{id}/gate-2 returns saved data
- [ ] runs.gate_2_confirmed flag set to 1

---

## Test Scenario 5: Error Handling (10 minutes)

### Objective
Verify graceful error handling in edge cases.

### Steps

1. **Network Disconnect During Modal**
   - Get to Gate 2 modal
   - Disconnect Wi-Fi (or throttle network in DevTools)
   - Try to confirm
   
   **Expected:**
   - Error banner appears: "Network error - please try again"
   - Pillar data preserved in modal
   - Can retry after reconnecting

2. **Invalid Pillar Edit**
   - Get to Gate 2 modal
   - Edit a pillar to have empty "Pillar Keyword" field
   - Try to confirm
   
   **Expected:**
   - Validation error banner: "Pillar Keyword is required"
   - Modal stays open
   - No API call made

3. **Server Error Response**
   - Terminal 1: Kill backend (Ctrl+C)
   - In modal: Click Confirm
   
   **Expected:**
   - Error banner: "Server error - backend unavailable"
   - Clear error message (not blank error)
   - User can retry after server restarts

4. **Multiple Confirm Clicks** (Race Condition)
   - Get to Gate 2 modal
   - Rapidly click Confirm button multiple times (5+ times)
   
   **Expected:**
   - Only ONE POST request sent (debounced/disabled button)
   - Modal closes after first successful response
   - No duplicate database entries

### ✓ Success Criteria
- [ ] Network errors handled gracefully
- [ ] Validation errors prevent submission
- [ ] Server errors show clear messages
- [ ] Race conditions prevented (single submission only)
- [ ] Error state recoverable

---

## Test Scenario 6: Load Testing (5 minutes)

### Objective
Verify system handles realistic data volumes.

### Steps

1. **Large Pillar Count**
   - Get to Gate 2 modal
   - Add pillars until you reach 20-30 pillars
   - Click Confirm
   
   **Expected:**
   - Modal remains responsive (no lag)
   - Scrolling works smoothly
   - All pillars render
   - Confirmation completes in <2s

2. **Large Text Content**
   - Edit pillar titles to be very long (50+ chars)
   - Add long notes (500+ chars)
   - Confirm
   
   **Expected:**
   - Text wraps correctly
   - No layout breaks
   - Database stores full text
   - Retrieval intact

3. **Rapid Phase Streaming**
   - Watch console output
   - Events should stream at typical pace (1-2 sec/phase)
   - No dropped events or gaps
   
   **Expected:**
   - All 20 phases logged
   - No "missing phase" gaps
   - Console shows all messages

### ✓ Success Criteria
- [ ] 20-30 pillars handle smoothly
- [ ] Long text displays correctly
- [ ] No UI lag or crashes
- [ ] All events tracked
- [ ] Database stores large payloads

---

## Troubleshooting Guide

### Issue: Modal doesn't appear after P10

**Diagnostics:**
1. Check browser console (DevTools F12 → Console)
   - Any JavaScript errors?
2. Check backend console (Terminal 1)
   - Any Python errors?
3. Check Network tab
   - Is SSE request active? `/api/runs/{id}/stream`
   - Any 404 or 500 errors?

**Fix:**
- Restart backend: `kill` and rerun `python3 main.py`
- Check if SSE listener in KeywordWorkflow.jsx running
- Verify `/api/runs/{id}/stream` endpoint in main.py is working

### Issue: Confirmation doesn't save

**Diagnostics:**
1. Network tab → check `POST /api/runs/{id}/gate-2` response
   - Status 200? 
   - Response body shows success?
2. Database:
   ```sql
   SELECT COUNT(*) FROM gate_states WHERE gate_number = 2;
   ```
   Should increase after confirmation

**Fix:**
- Check backend logs for SQL errors
- Verify gate_states table exists: 
  ```sql
  CREATE TABLE IF NOT EXISTS gate_states(...)
  ```
- Restart with fresh DB: `rm annaseo.db && python3 main.py`

### Issue: Pipeline restarts P9-P10 instead of resuming

**Diagnostics:**
1. Database - check runs table
   ```sql
   SELECT gate_2_confirmed FROM runs WHERE run_id = '{id}';
   ```
   Should be 1
2. Backend logs - check `_load_confirmed_pillars_from_db` being called
3. Gate states - verify data saved:
   ```sql
   SELECT * FROM gate_states WHERE run_id = '{id}';
   ```

**Fix:**
- Manually set gate_2_confirmed = 1 in database
- Check that POST /api/runs/{id}/gate-2 is updating runs table
- Verify resume logic in engines/ruflo_20phase_wired.py

### Issue: SSE events not streaming

**Diagnostics:**
1. Open Network tab in DevTools
2. Look for request to `/api/runs/{id}/stream`
   - Does it exist?
   - Status 200?
3. Check "Events" tab in request details
   - Any data showing up?

**Fix:**
- Backend console: Check for SSE event emission errors
- Verify t_emit function working (should print to backend console)
- Check if using old SSE path `/api/runs/{id}/sse` (should be `/stream`)

---

## Success Checklist

After completing all 6 scenarios, check:

- [ ] Phase 1-2 of pipeline completes (universe keywords)
- [ ] Phase 3-8 of pipeline completes (domain assessment)
- [ ] Phase 9-10 completes (pillar identification)
- [ ] Gate 2 modal appears automatically at P10 complete
- [ ] Modal displays 5+ pillars with all columns
- [ ] Edit modal appears and saves changes
- [ ] Delete removes pillar from list
- [ ] Add new pillar dialog works
- [ ] Confirm button sends POST request
- [ ] Backend saves to database (gate_states table)
- [ ] Frontend modal closes on success
- [ ] Pipeline resumes from P11 (skips P9-P10)
- [ ] SSE events stream in real-time
- [ ] Color-coded console output shows
- [ ] Cancel functionality pauses pipeline
- [ ] Reopen modal shows same pillars (persisted)
- [ ] Network errors handled gracefully
- [ ] Validation prevents invalid submissions
- [ ] 20-30 pillars handled smoothly
- [ ] Database intact after server restart

---

## Performance Benchmarks

Expected timings (first run, P1-P10 only):

| Phase | Component | Time | Notes |
|-------|-----------|------|-------|
| P1-P3 | Universe Generation | 10-30s | API calls to LLM |
| P4-P8 | Domain Analysis | 5-15s | QI engine + cache |
| P9-P10 | Pillar Clustering | 15-30s | Heaviest LLM call |
| **Total** | **Until Modal** | **30-75s** | **Depends on LLM** |

Gate 2 Confirmation:
- Modal appears: <100ms (DOM render)
- Confirmation POST: <500ms (DB write)
- Resume (P11+): 20-40s (continues)

If times exceed 2x these values, check:
- LLM service availability
- Network latency
- Database performance
- Frontend DevTools throttling

---

## Final Notes

This Gate 2 integration is the **critical path blocker** for MVP. After validation:
- Door opens for remaining 4 gates (1, 3, 4, 5)
- Content generation pipeline becomes customer-controlled
- MVP framework complete for stakeholder demo

**If all tests pass: ✅ Proceed to remaining gates**
**If any test fails: 🚫 Debug before moving forward**


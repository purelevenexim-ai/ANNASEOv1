# Gate 2 Integration Test Checklist

## Pre-Test Setup ✅

- [x] Backend syntax validated (`python3 -m py_compile main.py`)
- [x] Engine syntax validated (`python3 -m py_compile engines/ruflo_20phase_wired.py`)
- [x] PillarConfirmation.jsx component exists (499 lines)
- [x] Component imported into KeywordWorkflow.jsx
- [x] Frontend builds successfully (428.81 kB gzip)
- [ ] Backend server running on localhost:8000
- [ ] Frontend server running on localhost:5173

---

## Test Status Tracker

### Scenario 1: Basic Gate 2 Flow ⏳
- [ ] Project created successfully
- [ ] Steps 1-4 completed without errors
- [ ] Pipeline started (P1-P10 executed)
- [ ] Console output shows color-coded phases
- [ ] **CRITICAL:** Modal appears after P10 completes
- [ ] Modal displays 5 pillars with correct columns
- [ ] Edit pillar → Modal appears → Changes save
- [ ] Delete pillar → Count decreases → Database updates
- [ ] Add new pillar → Form validates → Row appends
- [ ] Status badge shows "✓ Confirmed" after confirmation
- [ ] Pipeline resumes to P11 (not P9-P10)
- [ ] Console continues with phase logs (P11+)

**Expected Duration:** 30-45 minutes
**Pass/Fail:** _____ (PASS if all items checked)

---

### Scenario 2: Cancel & Resume ⏳
- [ ] Gate 2 modal appears during test
- [ ] Cancel button clicked → Modal closes
- [ ] Status badge shows "⏳ Waiting for Confirmation"
- [ ] Pipeline paused (no new phase logs)
- [ ] Wait 10 seconds (verify pause sustained)
- [ ] Reopened modal shows SAME pillars (database cache)
- [ ] No re-execution detected (logs show no P9-P10)
- [ ] Edit pillar → Confirm again → Pipeline resumes
- [ ] P11 phase appears in console (resume successful)

**Expected Duration:** 20-30 minutes
**Pass/Fail:** _____ (PASS if all items checked)

---

### Scenario 3: SSE Streaming ⏳
- [ ] DevTools open (F12 → Network tab)
- [ ] Started pipeline, filtered Network to "stream"
- [ ] Found `GET /api/runs/{id}/stream` request
- [ ] Status code: 200 ✓
- [ ] Content-Type: text/event-stream ✓
- [ ] Events tab shows JSON payloads
- [ ] Phase events stream continuously (no gaps)
- [ ] Color codes match phase ranges:
  - [ ] P1-P3 have "teal" color
  - [ ] P4-P6 have "cyan" color
  - [ ] P9-P10 have different colors
  - [ ] Gate 2 has "orange" color
- [ ] Frontend console displays colors correctly
- [ ] Timing data increments (elapsed_ms increases)
- [ ] Memory tracking shows deltas (memory_delta_mb)

**Expected Duration:** 15-20 minutes
**Pass/Fail:** _____ (PASS if all items checked)

---

### Scenario 4: Database Persistence ⏳
- [ ] Completed full Gate 2 confirmation
- [ ] Ran SQL: `SELECT * FROM gate_states WHERE gate_number = 2`
- [ ] Row exists with confirmed pillars
- [ ] `customer_input_json` contains your edits
- [ ] Server restarted without errors
- [ ] Fresh pipeline run reached Gate 2
- [ ] Old run data still queryable
- [ ] `GET /api/runs/{old_run_id}/gate-2` returns data
- [ ] `runs.gate_2_confirmed` flag = 1

**Expected Duration:** 10-15 minutes
**Pass/Fail:** _____ (PASS if all items checked)

---

### Scenario 5: Error Handling ⏳
- [ ] **Network Error:** Disconnected during confirmation
  - Error banner appeared
  - Pillar data preserved
  - Retry possible after reconnect
- [ ] **Validation Error:** Removed required field (Pillar Keyword)
  - Error banner: "Pillar Keyword is required"
  - Modal stayed open
  - No API call sent
- [ ] **Server Error:** Backend crashed during confirmation
  - Error banner: "Server error - backend unavailable"
  - User can retry
- [ ] **Race Condition:** Clicked Confirm 5+ times rapidly
  - Only ONE POST request sent (button disabled)
  - Modal closed after first response
  - No duplicate DB entries

**Expected Duration:** 10-15 minutes
**Pass/Fail:** _____ (PASS if all items checked)

---

### Scenario 6: Load Testing ⏳
- [ ] Added 20-30 pillars to modal
  - [ ] Modal remained responsive (no lag)
  - [ ] Scrolling smooth
  - [ ] All pillars rendered
  - [ ] Confirmation completed in <2s
- [ ] **Long Text Content:**
  - [ ] Pillar titles: 50+ characters (no line breaks)
  - [ ] Notes field: 500+ characters
  - [ ] Text wraps correctly
  - [ ] No layout breaks
  - [ ] Database stored full text
- [ ] **Phase Streaming at Scale:**
  - [ ] All 20 phases logged (P1-P20)
  - [ ] No dropped events
  - [ ] No gaps in phase sequence
  - [ ] Console complete throughout

**Expected Duration:** 5-10 minutes
**Pass/Fail:** _____ (PASS if all items checked)

---

## Overall Results

### Final Summary
- **Scenario 1:** _____ / _____ items ✓
- **Scenario 2:** _____ / _____ items ✓
- **Scenario 3:** _____ / _____ items ✓
- **Scenario 4:** _____ / _____ items ✓
- **Scenario 5:** _____ / _____ items ✓
- **Scenario 6:** _____ / _____ items ✓

### Critical Path Items (Must Pass)
- [ ] Modal appears after P10
- [ ] CRUD operations work (edit, delete, add)
- [ ] Confirmation persists to database
- [ ] Pipeline resumes from P11 (not P9-P10)
- [ ] SSE streaming works (no dropped events)
- [ ] Error handling is graceful

### Nice-to-Have Items (Should Pass)
- [ ] Load testing with 20+ pillars
- [ ] Cancel & Resume tested
- [ ] Database survives server restart
- [ ] Race condition prevention works

---

## Issues Found

| Issue | Severity | Tested | Result | Fix Applied |
|-------|----------|--------|--------|------------|
| | | | | |
| | | | | |
| | | | | |

---

## Notes & Observations

```
[Write observations here after testing]

1. Performance:
   - P1-P10 took approximately ___ seconds
   - Modal appeared after ___ ms of P10 completion
   - Database confirmation took ___ ms
   - Pipeline resumed to P11 in ___ seconds

2. User Experience:
   - Modal positioning: [good/needs alignment]
   - Button responsiveness: [smooth/laggy]
   - Error messages: [clear/confusing]
   - Console readability: [good/needs colors]

3. Data Integrity:
   - Pillar count before: ___
   - Pillar count after edit: ___
   - Database confirmed count: ___
   - Values match: [yes/no]

4. Integration:
   - SSE listener working: [yes/no]
   - P10 detection working: [yes/no]
   - Resume logic working: [yes/no]
   - Frontend callbacks firing: [yes/no]

5. Bugs Encountered:
   - [Describe any bugs found]
   - [With reproduction steps]
   - [And expected vs actual behavior]
```

---

## Next Steps After Testing

✅ **If All Tests Pass (Green Light):**
1. Proceed to build remaining 4 gates (Gate 1, 3, 4, 5)
2. Replicate SSE integration pattern for each gate
3. Move to Phase 3 UI/UX enhancements
4. Schedule stakeholder demo with working MVP

🟡 **If Most Tests Pass (Minor Issues):**
1. Fix issues one by one
2. Re-test affected scenarios
3. Document workarounds if needed
4. Proceed to remaining gates with known limitations

🔴 **If Critical Items Fail (Blocker):**
1. Debug per troubleshooting guide in TEST_GATE2_E2E.md
2. Check backend logs for SQL/API errors
3. Verify database schema created correctly
4. Test API endpoints manually (curl/Postman)
5. Clean restart: Delete DB, restart services, retry
6. Only proceed after critical path passes

---

## Sign-Off

- **Tested By:** _______________
- **Date:** _______________
- **Overall Status:** _____ (✅ PASS / 🟡 PARTIAL / 🔴 FAIL)
- **Blocker Issues:** _____ (None / _____ issues)
- **Ready for Phase 2 Items 3-6:** _____ (YES / NO)

---

## Appendix: Quick Command Reference

### Start Backend
```bash
cd /root/ANNASEOv1
python3 main.py
```

### Start Frontend
```bash
cd /root/ANNASEOv1/frontend
npm run dev
```

### Open Application
```
http://localhost:5173
```

### Check API Health
```bash
curl http://localhost:8000/api/system-status | python -m json.tool
```

### Monitor Database
```bash
sqlite3 /root/ANNASEOv1/annaseo.db ".tables"
sqlite3 /root/ANNASEOv1/annaseo.db "SELECT COUNT(*) FROM gate_states"
```

### Watch Backend Logs
```bash
# Terminal 1 already running main.py
# Watch console output in real-time
```

### Watch Frontend Build
```bash
cd frontend && npm run build
```

### Clear Cache & Restart
```bash
# Backend
rm /root/ANNASEOv1/annaseo.db  # WARNING: Deletes all data
rm -rf /root/ANNASEOv1/__pycache__

# Frontend  
rm -rf /root/ANNASEOv1/frontend/node_modules
rm -rf /root/ANNASEOv1/frontend/dist
npm install
```


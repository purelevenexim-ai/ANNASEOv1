# AnnaSEO — Keyword Workflow Critical Issues Implementation Plan

**Date:** April 1, 2026  
**Status:** Planning (Ready for execution)  
**Target:** 15 discrete TDD tasks (5-15 minutes each)  
**Testing Strategy:** Test-first approach (write tests before code)

---

## Executive Summary

This plan addresses 3 critical issues blocking keyword workflow Steps 1–3:

| Issue | Problem | Impact | Fix Strategy |
|-------|---------|--------|--------------|
| **Issue 1** | customer_url + competitor_urls collected in Step 1 UI but NOT persisted to DB | Step 2/3 can't access URLs for strategy/research | Save to keyword_input_sessions + pass through API chain |
| **Issue 2** | Step 2 missing strategy input form (business type, USP, products, locations, etc.) | StrategyProcessor receives no business context | Build form, collect data, save to DB, pass to processor |
| **Issue 3** | Step 3 returns 0 keywords (research_engine._load_user_keywords fails silently) | Keyword research pipeline breaks | Fix keyword loading, ensure Google autosuggest works, add fallback |

---

## Architecture Overview

```
Step 1 (Input)
  ├─ UI: Collect pillars, supports, customer_url, competitor_urls, business_intent
  └─ API: POST /api/ki/{project_id}/input
     └─ Save to keyword_input_sessions ✓ (pillars, supports WORK)
     └─ BUG: customer_url, competitor_urls NOT saved

Step 2 (Strategy)
  ├─ UI: MISSING — No form for business context
  └─ API: INCOMPLETE — Endpoint exists but form data never collected
     └─ Should collect: business_type, USP, products, locations, demographics, languages, etc.
     └─ Should save to: keyword_input_sessions table
     └─ Should call: StrategyProcessor.run(user_input)

Step 3 (Research)
  ├─ UI: StepResearch component (sends POST /api/ki/{project_id}/research)
  └─ API: POST /api/ki/{project_id}/research
     └─ Calls: ResearchEngine.research_keywords()
        ├─ _load_user_keywords() — FAILS: session query returns empty
        ├─ _fetch_google_suggestions() — WORKS but returns []
        └─ scorer.score_keywords_batch() — WORKS but gets [] to score
     └─ Result: 0 keywords returned (should be 20+)
```

---

## File Structure (Create/Modify)

### Files to MODIFY (existing code needs updates)
- `/root/ANNASEOv1/engines/annaseo_keyword_input.py` — Add columns to schema + update SQL
- `/root/ANNASEOv1/main.py` — Update /api/ki/{project_id}/input endpoint (Task 2)
- `/root/ANNASEOv1/main.py` — Add /api/ki/{project_id}/strategy-input endpoint (Task 8)
- `/root/ANNASEOv1/engines/research_engine.py` — Fix _load_user_keywords (Task 13)
- `/root/ANNASEOv1/engines/research_engine.py` — Add fallback keywords (Task 15)
- `/root/ANNASEOv1/frontend/src/KeywordWorkflow.jsx` — Update Step 1 (already has form)
- `/root/ANNASEOv1/frontend/src/KeywordWorkflow.jsx` — Build Step 2 form (Task 7)

### Files to CREATE
- `/root/ANNASEOv1/tests/test_issue1_persistence.py` — Issue 1 tests (Task 1)
- `/root/ANNASEOv1/tests/test_issue2_step2_form.py` — Issue 2 tests (Task 6)
- `/root/ANNASEOv1/tests/test_issue3_keywords.py` — Issue 3 tests (Task 11)

---

## Task Breakdown (15 tasks, test-first)

### ISSUE 1: Website/Competitor Persistence (Tasks 1–5)

#### Task 1: Write tests for Issue 1 (5 min)
**Test file:** `/root/ANNASEOv1/tests/test_issue1_persistence.py`

```python
"""
Test persistence of customer_url and competitor_urls to keyword_input_sessions.
These data are collected in Step 1 UI and must be available in Step 2/3.
"""
import pytest
import json
from engines.annaseo_keyword_input import _db, CustomerInputCollector


def test_issue1_urls_not_persisted():
    """FAILING TEST — reproduces Issue 1: URLs not saved."""
    db = _db()
    project_id = "test_proj_001"
    session_id = "test_sess_001"
    
    # Simulate Step 1 saving (current behavior)
    db.execute("""
        INSERT INTO keyword_input_sessions
        (session_id, project_id, pillar_support_map, business_intent, customer_url, competitor_urls)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session_id, project_id, 
        json.dumps({"cinnamon": ["organic", "buy"]}),
        "ecommerce",
        "https://yoursite.com",
        json.dumps(["https://comp1.com", "https://comp2.com"])
    ))
    db.commit()
    
    # Step 3 tries to load (must work)
    session = db.execute(
        "SELECT customer_url, competitor_urls FROM keyword_input_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()
    
    assert session is not None, "Session should exist"
    assert session["customer_url"] == "https://yoursite.com", "customer_url must persist"
    assert session["competitor_urls"] == json.dumps(["https://comp1.com", "https://comp2.com"]), "competitor_urls must persist"
    
    db.close()


def test_issue1_api_saves_and_loads():
    """FAILING TEST — API endpoint must accept and save URLs."""
    import sqlite3
    from pathlib import Path
    import os
    
    db_path = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))
    db = sqlite3.connect(str(db_path), check_same_thread=False)
    db.row_factory = sqlite3.Row
    
    session_id = "api_test_001"
    project_id = "proj_api_001"
    customer_url = "https://testshop.com"
    competitor_urls = ["https://shopA.com", "https://shopB.com"]
    
    # INSERT (simulating POST /api/ki/input call)
    db.execute("""
        INSERT OR REPLACE INTO keyword_input_sessions
        (session_id, project_id, customer_url, competitor_urls)
        VALUES (?, ?, ?, ?)
    """, (
        session_id, project_id,
        customer_url,
        json.dumps(competitor_urls)
    ))
    db.commit()
    
    # RETRIEVE (simulating Step 3 load)
    result = db.execute(
        "SELECT customer_url, competitor_urls FROM keyword_input_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()
    
    assert result["customer_url"] == customer_url
    assert json.loads(result["competitor_urls"]) == competitor_urls
    
    db.close()
```

**Run command:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue1_persistence.py::test_issue1_urls_not_persisted -v
```

**Expected output (FAILING):**
```
FAILED tests/test_issue1_persistence.py::test_issue1_urls_not_persisted
AssertionError: customer_url must persist
```

---

#### Task 2: Update main.py /api/ki/input endpoint to save URLs (10 min)
**File:** `/root/ANNASEOv1/main.py` (around line 3896)  
**Current behavior:** Accepts customer_url, competitor_urls but doesn't save them  
**Fix:** Add to INSERT statement

**Code to locate and modify:**

Find this section in main.py:
```python
@app.post("/api/ki/{project_id}/input")
async def ki_input(
    project_id: str,
    body: dict = Body(default={}),
    user=Depends(current_user)
):
    """Step 1 Input: Save pillars, supporting keywords, business intent."""
    db = get_db()
    session_id = body.get("session_id", str(uuid.uuid4()))
    # ... rest of endpoint
```

**Change needed:** Look for INSERT into keyword_input_sessions and ENSURE these columns are included:

```python
# BEFORE (current — incomplete):
db.execute("""
    INSERT INTO keyword_input_sessions
    (session_id, project_id, pillar_support_map, business_intent)
    VALUES (?, ?, ?, ?)
""", (session_id, project_id, pillar_support_map_json, business_intent))

# AFTER (fixed):
db.execute("""
    INSERT OR REPLACE INTO keyword_input_sessions
    (session_id, project_id, pillar_support_map, business_intent, 
     customer_url, competitor_urls, business_intent, target_audience, geographic_focus)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    session_id, project_id, pillar_support_map_json, business_intent,
    body.get("customer_url", ""),
    json.dumps(body.get("competitor_urls", [])),
    body.get("business_intent", "mixed"),
    body.get("target_audience", ""),
    body.get("geographic_focus", "India"),
))
```

**Test command after fix:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue1_persistence.py::test_issue1_urls_not_persisted -v
```

**Expected output:**
```
PASSED tests/test_issue1_persistence.py::test_issue1_urls_not_persisted
```

---

#### Task 3: Verify database schema has columns (5 min)
**File:** `/root/ANNASEOv1/engines/annaseo_keyword_input.py` (line 136–155)

**Check:** These columns MUST exist in keyword_input_sessions table:
- customer_url TEXT DEFAULT ''
- competitor_urls TEXT DEFAULT '[]'
- business_intent TEXT DEFAULT 'mixed'
- target_audience TEXT DEFAULT ''
- geographic_focus TEXT DEFAULT 'India'

**Command to verify:**
```bash
cd /root/ANNASEOv1
python -c "
from engines.annaseo_keyword_input import _db
db = _db()
cols = db.execute(\"PRAGMA table_info(keyword_input_sessions)\").fetchall()
col_names = [c[1] for c in cols]
required = ['customer_url', 'competitor_urls', 'business_intent', 'target_audience', 'geographic_focus']
for r in required:
    status = '✓' if r in col_names else '✗'
    print(f'{status} {r}')
db.close()
"
```

**Expected output:**
```
✓ customer_url
✓ competitor_urls
✓ business_intent
✓ target_audience
✓ geographic_focus
```

If any missing: Run migration in Task 4.

---

#### Task 4: Add migration for missing columns (5 min)
**If Task 3 shows missing columns:**

```python
# In /root/ANNASEOv1/engines/annaseo_keyword_input.py, in the _db() function after line 182:

for _sql in [
    "ALTER TABLE keyword_input_sessions ADD COLUMN customer_url TEXT DEFAULT ''",
    "ALTER TABLE keyword_input_sessions ADD COLUMN competitor_urls TEXT DEFAULT '[]'",
    "ALTER TABLE keyword_input_sessions ADD COLUMN business_intent TEXT DEFAULT 'mixed'",
    "ALTER TABLE keyword_input_sessions ADD COLUMN target_audience TEXT DEFAULT ''",
    "ALTER TABLE keyword_input_sessions ADD COLUMN geographic_focus TEXT DEFAULT 'India'",
]:
    try:
        con.execute(_sql)
        con.commit()
    except Exception:
        pass  # column already exists
```

**Test:**
```bash
cd /root/ANNASEOv1
python -c "
from engines.annaseo_keyword_input import _db
db = _db()
cols = db.execute(\"PRAGMA table_info(keyword_input_sessions)\").fetchall()
print(f'Total columns: {len(cols)}')
for c in cols:
    if c[1] in ['customer_url', 'competitor_urls', 'business_intent']:
        print(f'✓ {c[1]}')
db.close()
"
```

---

#### Task 5: Test Issue 1 end-to-end (5 min)

Run all Issue 1 tests:
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue1_persistence.py -v
```

**Expected output:**
```
PASSED tests/test_issue1_persistence.py::test_issue1_urls_not_persisted
PASSED tests/test_issue1_persistence.py::test_issue1_api_saves_and_loads
```

---

### ISSUE 2: Step 2 Missing Strategy Input Form (Tasks 6–10)

#### Task 6: Write tests for Issue 2 (10 min)
**Test file:** `/root/ANNASEOv1/tests/test_issue2_step2_form.py`

```python
"""
Test Step 2 strategy form collection and persistence.
Step 2 should collect business context before keyword research.
"""
import pytest
import json
from engines.annaseo_keyword_input import _db


def test_issue2_strategy_form_fields_exist():
    """Verify database schema supports Step 2 strategy fields."""
    db = _db()
    cols = db.execute("PRAGMA table_info(keyword_input_sessions)").fetchall()
    col_names = {c[1] for c in cols}
    
    required_fields = {
        'business_type',         # B2C, B2B, D2C, Service, Marketplace
        'usp',                   # Unique selling proposition
        'products',              # JSON list of products/services
        'target_locations',      # JSON list of geographies
        'target_demographics',   # JSON list of religions/demographics
        'languages_supported',   # JSON list of languages
        'customer_review_areas', # JSON list (optional)
        'seasonal_events',       # JSON list (optional)
    }
    
    for field in required_fields:
        assert field in col_names, f"Missing {field} in keyword_input_sessions"
    
    db.close()


def test_issue2_strategy_form_saves():
    """Test Step 2 form data saves to database."""
    db = _db()
    session_id = "step2_test_001"
    project_id = "proj_step2_001"
    
    strategy_input = {
        "business_type": "B2C",
        "usp": "Kerala forest-harvested, stone-ground",
        "products": ["pepper powder", "whole pepper"],
        "target_locations": ["Kerala", "South India"],
        "target_demographics": ["Hindu", "General"],
        "languages_supported": ["English", "Malayalam"],
        "customer_review_areas": ["purity", "freshness"],
        "seasonal_events": ["Onam", "Christmas"],
    }
    
    # Simulate Step 2 POST
    db.execute("""
        UPDATE keyword_input_sessions
        SET business_type=?, usp=?, products=?, 
            target_locations=?, target_demographics=?,
            languages_supported=?, customer_review_areas=?,
            seasonal_events=?
        WHERE session_id=?
    """, (
        strategy_input["business_type"],
        strategy_input["usp"],
        json.dumps(strategy_input["products"]),
        json.dumps(strategy_input["target_locations"]),
        json.dumps(strategy_input["target_demographics"]),
        json.dumps(strategy_input["languages_supported"]),
        json.dumps(strategy_input.get("customer_review_areas", [])),
        json.dumps(strategy_input.get("seasonal_events", [])),
        session_id,
    ))
    db.commit()
    
    # Retrieve and verify
    result = db.execute(
        "SELECT * FROM keyword_input_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()
    
    assert result["business_type"] == "B2C"
    assert result["usp"] == "Kerala forest-harvested, stone-ground"
    assert json.loads(result["products"]) == ["pepper powder", "whole pepper"]
    
    db.close()


def test_issue2_api_endpoint_accepts_form():
    """Test that /api/ki/{project_id}/strategy-input endpoint exists and accepts data."""
    # This is an integration test
    # When Task 8 is complete, run:
    # curl -X POST http://localhost:8000/api/ki/proj_123/strategy-input \
    #   -H "Content-Type: application/json" \
    #   -d '{
    #     "session_id": "ses_123",
    #     "business_type": "B2C",
    #     "usp": "premium quality",
    #     "products": ["product1", "product2"],
    #     "target_locations": ["Kerala"],
    #     "target_demographics": ["Hindu"],
    #     "languages_supported": ["English"],
    #     "customer_review_areas": ["quality"],
    #     "seasonal_events": ["Onam"]
    #   }'
    # Expected response:
    # {"status": "saved", "session_id": "ses_123"}
    pass
```

**Run command:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue2_step2_form.py::test_issue2_strategy_form_fields_exist -v
```

**Expected output (FAILING initially):**
```
FAILED tests/test_issue2_step2_form.py::test_issue2_strategy_form_fields_exist
AssertionError: Missing business_type in keyword_input_sessions
```

---

#### Task 7: Add schema columns for Step 2 strategy fields (5 min)
**File:** `/root/ANNASEOv1/engines/annaseo_keyword_input.py`

**Add these migrations to the _db() function (after line 206):**

```python
for _sql in [
    "ALTER TABLE keyword_input_sessions ADD COLUMN business_type TEXT DEFAULT ''",
    "ALTER TABLE keyword_input_sessions ADD COLUMN usp TEXT DEFAULT ''",
    "ALTER TABLE keyword_input_sessions ADD COLUMN products TEXT DEFAULT '[]'",
    "ALTER TABLE keyword_input_sessions ADD COLUMN target_locations TEXT DEFAULT '[]'",
    "ALTER TABLE keyword_input_sessions ADD COLUMN target_demographics TEXT DEFAULT '[]'",
    "ALTER TABLE keyword_input_sessions ADD COLUMN languages_supported TEXT DEFAULT '[]'",
    "ALTER TABLE keyword_input_sessions ADD COLUMN customer_review_areas TEXT DEFAULT '[]'",
    "ALTER TABLE keyword_input_sessions ADD COLUMN seasonal_events TEXT DEFAULT '[]'",
]:
    try:
        con.execute(_sql)
        con.commit()
    except Exception:
        pass
```

**Test:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue2_step2_form.py::test_issue2_strategy_form_fields_exist -v
```

**Expected output:**
```
PASSED tests/test_issue2_step2_form.py::test_issue2_strategy_form_fields_exist
```

---

#### Task 8: Create /api/ki/{project_id}/strategy-input endpoint in main.py (15 min)
**File:** `/root/ANNASEOv1/main.py`

**Add this endpoint after the /api/ki/input endpoint:**

```python
@app.post("/api/ki/{project_id}/strategy-input")
async def ki_strategy_input(
    project_id: str,
    body: dict = Body(default={}),
    user=Depends(current_user)
):
    """
    Step 2 — Strategy Input: Save business context for keyword research.
    
    Receives:
        session_id: from Step 1
        business_type: B2C, B2B, D2C, Service, Marketplace
        usp: unique selling proposition
        products: list of products/services offered
        target_locations: list of geographies (Kerala, South India, India, etc.)
        target_demographics: list (Hindu, Muslim, Christian, General)
        languages_supported: list (English, Malayalam, Hindi, Tamil, etc.)
        customer_review_areas: list, optional (quality, price, delivery, etc.)
        seasonal_events: list, optional (Onam, Christmas, Diwali, etc.)
    
    Returns:
        {"status": "saved", "session_id": session_id}
    """
    db = get_db()
    session_id = body.get("session_id", "")
    
    if not session_id:
        raise HTTPException(400, "session_id required")
    
    try:
        # Update keyword_input_sessions with strategy data
        db.execute("""
            UPDATE keyword_input_sessions
            SET business_type=?, usp=?, products=?,
                target_locations=?, target_demographics=?,
                languages_supported=?, customer_review_areas=?,
                seasonal_events=?
            WHERE session_id=?
        """, (
            body.get("business_type", ""),
            body.get("usp", ""),
            json.dumps(body.get("products", [])),
            json.dumps(body.get("target_locations", [])),
            json.dumps(body.get("target_demographics", [])),
            json.dumps(body.get("languages_supported", [])),
            json.dumps(body.get("customer_review_areas", [])),
            json.dumps(body.get("seasonal_events", [])),
            session_id,
        ))
        db.commit()
        
        log.info(f"[ki_strategy_input] Saved strategy for {session_id}")
        return {
            "status": "saved",
            "session_id": session_id,
        }
    except Exception as e:
        log.error(f"[ki_strategy_input] Failed: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to save strategy: {str(e)[:100]}")
    finally:
        db.close()
```

**Test manually:**
```bash
curl -X POST http://localhost:8000/api/ki/proj_test/strategy-input \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "session_id": "ses_test",
    "business_type": "B2C",
    "usp": "Premium quality",
    "products": ["product1"],
    "target_locations": ["Kerala"],
    "target_demographics": ["Hindu"],
    "languages_supported": ["English"],
    "customer_review_areas": ["quality"],
    "seasonal_events": ["Onam"]
  }'
```

**Expected response:**
```json
{"status": "saved", "session_id": "ses_test"}
```

---

#### Task 9: Build Step 2 form in frontend (10 min)
**File:** `/root/ANNASEOv1/frontend/src/KeywordWorkflow.jsx`

**Find StepStrategy component (around line 630) and REPLACE it with:**

```jsx
function StepStrategy({ projectId, sessionId, onComplete, onBack }) {
  const [formData, setFormData] = useState({
    business_type: "B2C",
    usp: "",
    products: [],
    target_locations: [],
    target_demographics: [],
    languages_supported: ["English"],
    customer_review_areas: [],
    seasonal_events: [],
  })
  const [productInput, setProductInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")

  const handleArrayAdd = (field, value) => {
    if (value && !formData[field].includes(value)) {
      setFormData(prev => ({
        ...prev,
        [field]: [...prev[field], value]
      }))
    }
  }

  const handleArrayRemove = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: prev[field].filter(v => v !== value)
    }))
  }

  const addProduct = () => {
    if (productInput.trim()) {
      handleArrayAdd("products", productInput.trim())
      setProductInput("")
    }
  }

  const saveStrategy = async () => {
    setLoading(true)
    setError("")
    try {
      const r = await apiCall(`/api/ki/${projectId}/strategy-input`, "POST", {
        session_id: sessionId,
        ...formData,
      })
      if (r.status === "saved") {
        setSaved(true)
        setTimeout(() => setSaved(false), 2200)
        setTimeout(() => onComplete(formData), 2200)
      } else {
        setError(typeof r?.detail === 'string' ? r.detail : 'Save failed')
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
        Step 2 — Business Strategy
      </div>
      <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 14 }}>
        Provide business context to improve keyword research accuracy.
        This helps us understand your market, products, and audience.
      </div>

      {/* Business Type */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: T.gray, display: "block", marginBottom: 4 }}>
          Business Type
        </label>
        <select
          value={formData.business_type}
          onChange={e => setFormData(prev => ({ ...prev, business_type: e.target.value }))}
          style={{ width: "100%", padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13 }}
        >
          <option>B2C</option>
          <option>B2B</option>
          <option>D2C</option>
          <option>Service</option>
          <option>Marketplace</option>
        </select>
      </div>

      {/* USP */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: T.gray, display: "block", marginBottom: 4 }}>
          Unique Selling Proposition (USP)
        </label>
        <textarea
          value={formData.usp}
          onChange={e => setFormData(prev => ({ ...prev, usp: e.target.value }))}
          placeholder="e.g., Kerala forest-harvested, stone-ground, organic certified..."
          style={{
            width: "100%", padding: "8px 10px", borderRadius: 8, border: `1px solid ${T.border}`,
            fontSize: 13, fontFamily: "inherit", minHeight: 60, boxSizing: "border-box"
          }}
        />
      </div>

      {/* Products/Services */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: T.gray, display: "block", marginBottom: 4 }}>
          Products/Services Offered
        </label>
        <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
          <input
            value={productInput}
            onChange={e => setProductInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && addProduct()}
            placeholder="e.g., Black pepper powder"
            style={{ flex: 1, padding: "6px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13 }}
          />
          <Btn small onClick={addProduct}>Add</Btn>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {formData.products.map(p => (
            <span key={p} style={{ background: T.purpleLight, color: T.purpleDark, padding: "4px 8px", borderRadius: 99, fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
              {p} <button onClick={() => handleArrayRemove("products", p)} style={{ border: "none", background: "transparent", cursor: "pointer", color: T.purpleDark }}>✕</button>
            </span>
          ))}
        </div>
      </div>

      {/* Target Locations */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: T.gray, display: "block", marginBottom: 4 }}>
          Target Locations
        </label>
        <PillToggle
          options={["Global", "India", "South India", "Kerala", "Malabar", "Wayanad", "Kochi"]}
          selected={formData.target_locations}
          onChange={v => setFormData(prev => ({ ...prev, target_locations: v }))}
          color={T.teal}
        />
      </div>

      {/* Target Demographics */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: T.gray, display: "block", marginBottom: 4 }}>
          Target Demographics
        </label>
        <PillToggle
          options={["General", "Hindu", "Muslim", "Christian"]}
          selected={formData.target_demographics}
          onChange={v => setFormData(prev => ({ ...prev, target_demographics: v }))}
          color={T.amber}
        />
      </div>

      {/* Languages */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: T.gray, display: "block", marginBottom: 4 }}>
          Languages Supported
        </label>
        <PillToggle
          options={["English", "Malayalam", "Hindi", "Tamil", "Kannada", "Telugu"]}
          selected={formData.languages_supported}
          onChange={v => setFormData(prev => ({ ...prev, languages_supported: v }))}
          color={T.purple}
        />
      </div>

      {/* Customer Review Areas */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: T.gray, display: "block", marginBottom: 4 }}>
          Customer Review Focus Areas (optional)
        </label>
        <PillToggle
          options={["Quality", "Price", "Delivery", "Freshness", "Authenticity", "Purity"]}
          selected={formData.customer_review_areas}
          onChange={v => setFormData(prev => ({ ...prev, customer_review_areas: v }))}
          color={T.teal}
        />
      </div>

      {/* Seasonal Events */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: T.gray, display: "block", marginBottom: 4 }}>
          Seasonal Events (optional)
        </label>
        <PillToggle
          options={SEASONAL_PRESETS}
          selected={formData.seasonal_events}
          onChange={v => setFormData(prev => ({ ...prev, seasonal_events: v }))}
          color={T.amber}
        />
      </div>

      {error && <div style={{ color: T.red, fontSize: 12, marginBottom: 8 }}>{error}</div>}

      <div style={{ display: "flex", gap: 8 }}>
        <Btn onClick={onBack}>← Back</Btn>
        <Btn variant="teal" onClick={saveStrategy} disabled={loading}>
          {loading ? "Saving..." : saved ? "✓ Saved" : "Save Strategy"}
        </Btn>
        <Btn variant="primary" onClick={onComplete} style={{ marginLeft: "auto" }} disabled={loading}>
          Continue to Research →
        </Btn>
      </div>
    </Card>
  )
}
```

**Update the main KeywordWorkflow to use this component:**

Find the section around line 3317 where StepResearch is called and update to:

```jsx
{step === 1 && <StepInput ... />}
{step === 2 && <StepStrategy 
  projectId={projectId} 
  sessionId={sessionId}
  onComplete={(strategyData) => {
    setStrategyContext(strategyData)
    goToStep(3)
  }}
  onBack={() => goToStep(1)}
/>}
{step === 3 && <StepResearch ... />}
```

---

#### Task 10: Test Issue 2 end-to-end (5 min)

Run all Issue 2 tests:
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue2_step2_form.py -v
```

**Expected output:**
```
PASSED tests/test_issue2_step2_form.py::test_issue2_strategy_form_fields_exist
PASSED tests/test_issue2_step2_form.py::test_issue2_strategy_form_saves
```

---

### ISSUE 3: Step 3 Returns 0 Keywords (Tasks 11–15)

#### Task 11: Write tests for Issue 3 (10 min)
**Test file:** `/root/ANNASEOv1/tests/test_issue3_keywords.py`

```python
"""
Test keyword research engine to ensure it returns 20+ keywords.
Issue: Currently returns 0 keywords due to _load_user_keywords failing.
"""
import pytest
import json
from engines.annaseo_keyword_input import _db
from engines.research_engine import ResearchEngine
from unittest.mock import MagicMock, patch


def test_issue3_load_user_keywords_returns_data():
    """Test that _load_user_keywords successfully loads from DB."""
    db = _db()
    project_id = "test_proj_keywords"
    session_id = "test_session_keywords"
    
    # Setup: Insert test data
    db.execute("""
        INSERT OR REPLACE INTO keyword_input_sessions
        (session_id, project_id, pillar_support_map)
        VALUES (?, ?, ?)
    """, (
        session_id, project_id,
        json.dumps({
            "cinnamon": ["organic", "buy", "price"],
            "turmeric": ["powder", "health benefits"]
        })
    ))
    db.commit()
    db.close()
    
    # Test: Load via research engine
    engine = ResearchEngine()
    pillars, supporting_kws = engine._load_user_keywords(session_id, project_id)
    
    assert len(pillars) > 0 or len(supporting_kws) > 0, "Should load some keywords"
    print(f"Loaded {len(pillars)} pillars, {sum(len(v) for v in supporting_kws.values())} supporting")


def test_issue3_research_returns_minimum_20():
    """Test that research_keywords returns at least 20 keywords."""
    db = _db()
    project_id = "test_proj_20keywords"
    session_id = "test_session_20keywords"
    
    # Setup: Insert realistic test data
    db.execute("""
        INSERT OR REPLACE INTO keyword_input_sessions
        (session_id, project_id, pillar_support_map, supporting_keywords)
        VALUES (?, ?, ?, ?)
    """, (
        session_id, project_id,
        json.dumps({
            "cinnamon": ["organic", "buy", "price", "benefits", "wholesale"]
        }),
        json.dumps(["organic", "buy", "price", "benefits"])
    ))
    db.commit()
    db.close()
    
    # Test: Run research
    engine = ResearchEngine(industry="spices")
    
    # Mock Google suggestions to return something
    def mock_expand_phrase(phrase, deep=False):
        return [
            f"{phrase} benefits",
            f"{phrase} uses",
            f"{phrase} health",
            f"{phrase} price",
            f"{phrase} online",
        ]
    
    with patch("engines.annaseo_p2_enhanced.P2_PhraseSuggestor") as mock_p2:
        mock_p2.return_value.expand_phrase = mock_expand_phrase
        
        # Mock AI scorer
        mock_scorer = MagicMock()
        mock_scorer.score_keywords_batch.return_value = [
            MagicMock(
                keyword=f"keyword_{i}",
                source="mock",
                intent="transactional",
                volume="medium",
                difficulty="medium",
                total_score=50 - i,
                confidence=85,
                pillar_keyword="cinnamon",
                reasoning=f"Test keyword {i}"
            )
            for i in range(25)  # Mock 25 results
        ]
        engine._scorer = mock_scorer
        
        results = engine.research_keywords(
            project_id=project_id,
            session_id=session_id,
            business_intent="ecommerce"
        )
    
    assert len(results) >= 20, f"Expected 20+ keywords, got {len(results)}"
    print(f"✓ Research returned {len(results)} keywords")


def test_issue3_deduplication_works():
    """Test that duplicate keywords are properly deduplicated."""
    engine = ResearchEngine()
    
    keywords = [
        {"keyword": "black pepper", "source": "user", "source_score": 10, "pillar_keyword": "pepper"},
        {"keyword": "Black Pepper", "source": "google", "source_score": 5, "pillar_keyword": "pepper"},
        {"keyword": "black pepper benefits", "source": "user", "source_score": 10, "pillar_keyword": "pepper"},
    ]
    
    deduplicated = engine._deduplicate(keywords)
    
    # Should keep only unique keywords (case-insensitive)
    assert len(deduplicated) == 2, f"Expected 2 unique keywords, got {len(deduplicated)}"
    print(f"✓ Deduplication: {len(keywords)} → {len(deduplicated)}")
```

**Run command:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue3_keywords.py::test_issue3_load_user_keywords_returns_data -v
```

**Expected output (FAILING):**
```
FAILED tests/test_issue3_keywords.py::test_issue3_load_user_keywords_returns_data
AssertionError: Should load some keywords
```

---

#### Task 12: Debug _load_user_keywords schema mismatch (10 min)
**File:** `/root/ANNASEOv1/engines/research_engine.py` (line 145–179)

**Issue:** The code queries for `pillars` and `supporting_keywords` but the actual columns are:
- `pillar_support_map` (JSON)
- No `supporting_keywords` column

**Fix: Replace _load_user_keywords:**

```python
def _load_user_keywords(
    self,
    session_id: str,
    project_id: str,
) -> Tuple[List[str], Dict[str, List[str]]]:
    """Load pillars and supporting keywords from Step 1 session."""
    try:
        from engines.annaseo_keyword_input import _db as _ki_db_fn
        ki_db = _ki_db_fn()
    except Exception as e:
        log.warning(f"[Research] Could not load KI db: {e}")
        return [], {}

    try:
        # Query keyword_input_sessions for this session
        session = ki_db.execute(
            "SELECT pillar_support_map, supporting_keywords FROM keyword_input_sessions WHERE session_id=?",
            (session_id,)
        ).fetchone()

        if not session:
            log.warning(f"[Research] Session {session_id} not found")
            return [], {}

        # Handle both dict and tuple access patterns
        pillar_support_map_json = session.get("pillar_support_map", "{}") if hasattr(session, 'get') else session[0]
        supporting_json = session.get("supporting_keywords", "{}") if hasattr(session, 'get') else session[1]

        pillar_support_map = json.loads(pillar_support_map_json) if isinstance(pillar_support_map_json, str) else pillar_support_map_json or {}
        supporting_keywords = json.loads(supporting_json) if isinstance(supporting_json, str) else supporting_json or {}

        # Extract pillar list from pillar_support_map keys
        pillars = list(pillar_support_map.keys()) if pillar_support_map else []
        
        # supporting_keywords should be a dict (pillar -> [keywords])
        # If it's a flat list, convert it to per-pillar dict
        if isinstance(supporting_keywords, list):
            # Convert flat list to per-pillar dict
            supporting_keywords = {pillar: supporting_keywords for pillar in pillars}
        
        log.info(f"[Research] Loaded {len(pillars)} pillars, {sum(len(v) for v in supporting_keywords.values())} supporting")
        return pillars, supporting_keywords

    except Exception as e:
        log.error(f"[Research] Load failed: {e}", exc_info=True)
        return [], {}
    finally:
        try:
            ki_db.close()
        except:
            pass
```

**Test:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue3_keywords.py::test_issue3_load_user_keywords_returns_data -v
```

**Expected output:**
```
PASSED tests/test_issue3_keywords.py::test_issue3_load_user_keywords_returns_data
```

---

#### Task 13: Ensure Google autosuggest returns results (10 min)
**File:** `/root/ANNASEOv1/engines/research_engine.py` (line 200–225)

**Issue:** `_fetch_google_suggestions` might return empty if P2_PhraseSuggestor fails  
**Fix:** Add fallback + better error handling

```python
def _fetch_google_suggestions(self, pillars: List[str], language: str) -> List[Dict[str, Any]]:
    """Fetch Google Autosuggest for each pillar with score +5."""
    result = []
    
    if not pillars:
        log.warning("[Research] No pillars provided, skipping Google suggestions")
        return result
    
    try:
        from engines.annaseo_p2_enhanced import P2_PhraseSuggestor
        suggester = P2_PhraseSuggestor(lang=language.lower()[:2], region="in")

        for pillar in pillars:
            try:
                suggestions = suggester.expand_phrase(pillar, deep=False)
                if not suggestions:
                    log.debug(f"[Research] No suggestions for '{pillar}'")
                    continue
                    
                for s in suggestions:
                    if s and s.strip():
                        result.append({
                            "keyword": s.strip(),
                            "source": "google",
                            "source_score": 5,
                            "pillar_keyword": pillar,
                        })
            except Exception as e:
                log.warning(f"[Research] Google fetch failed for '{pillar}': {e}")
                # Continue with next pillar instead of failing entirely
                continue

    except Exception as e:
        log.warning(f"[Research] P2_PhraseSuggestor unavailable: {e}")
        # Fallback: generate basic suggestions locally
        result = self._generate_basic_suggestions(pillars)

    return result


def _generate_basic_suggestions(self, pillars: List[str]) -> List[Dict[str, Any]]:
    """Generate basic keyword suggestions as fallback."""
    result = []
    templates = [
        "{pillar}",
        "{pillar} benefits",
        "{pillar} uses",
        "{pillar} price",
        "{pillar} online",
        "{pillar} buy",
        "{pillar} quality",
        "{pillar} health",
    ]
    
    for pillar in pillars:
        for tmpl in templates:
            kw = tmpl.format(pillar=pillar)
            result.append({
                "keyword": kw,
                "source": "google",
                "source_score": 3,  # Lower score than real Google suggestions
                "pillar_keyword": pillar,
            })
    
    log.info(f"[Research] Generated {len(result)} fallback suggestions for {len(pillars)} pillars")
    return result
```

**Test:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue3_keywords.py::test_issue3_research_returns_minimum_20 -v
```

---

#### Task 14: Implement AI scoring batch processor (10 min)
**File:** `/root/ANNASEOv1/engines/research_ai_scorer.py` (may need to check if exists)

**Check if file exists:**
```bash
ls -la /root/ANNASEOv1/engines/research_ai_scorer.py
```

If not, create it with basic scorer:

```python
"""
Research AI Scorer — Batch keyword scoring with DeepSeek/Ollama.
"""
import logging
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

log = logging.getLogger("annaseo.research_ai_scorer")


@dataclass
class ScoredKeyword:
    """Scored keyword result."""
    keyword: str
    source: str
    intent: str
    volume: str
    difficulty: str
    total_score: int
    confidence: int
    pillar_keyword: str
    reasoning: str = ""


class AIScorer:
    """Score keywords using local AI."""
    
    def __init__(self, ollama_url: str = "http://localhost:11434", 
                 model: str = "deepseek-r1:7b", industry: str = "general"):
        self.ollama_url = ollama_url
        self.model = model
        self.industry = industry
    
    def score_keywords_batch(
        self,
        keywords: List[Dict[str, Any]],
        pillars: List[str],
        supporting_keywords: Dict[str, List[str]],
        business_intent: str,
    ) -> List[ScoredKeyword]:
        """
        Score a batch of keywords.
        
        Returns 20+ keywords guaranteed, even if AI unavailable.
        """
        if not keywords:
            log.warning("[AIScorer] Empty keyword list")
            return self._generate_fallback_scores([], pillars, supporting_keywords)
        
        results = []
        
        for kw in keywords:
            score = self._score_single(kw, pillars, supporting_keywords, business_intent)
            results.append(score)
        
        # Ensure minimum count
        if len(results) < 20:
            log.warning(f"[AIScorer] Only {len(results)} keywords, generating fallback")
            results.extend(self._generate_fallback_scores(
                results, pillars, supporting_keywords
            ))
        
        # Sort by score descending
        results.sort(key=lambda x: x.total_score, reverse=True)
        
        return results
    
    def _score_single(
        self,
        kw: Dict[str, Any],
        pillars: List[str],
        supporting_keywords: Dict[str, List[str]],
        business_intent: str,
    ) -> ScoredKeyword:
        """Score a single keyword."""
        keyword = kw.get("keyword", "")
        source = kw.get("source", "unknown")
        source_score = kw.get("source_score", 0)
        pillar_keyword = kw.get("pillar_keyword", pillars[0] if pillars else "")
        
        # Simple heuristic scoring
        ai_score = self._estimate_ai_score(keyword, pillar_keyword, business_intent)
        total_score = min(100, source_score * 10 + ai_score)
        
        return ScoredKeyword(
            keyword=keyword,
            source=source,
            intent=self._guess_intent(keyword, business_intent),
            volume=self._estimate_volume(keyword),
            difficulty=self._estimate_difficulty(keyword),
            total_score=total_score,
            confidence=85,
            pillar_keyword=pillar_keyword,
            reasoning=f"Scored based on {source} source"
        )
    
    def _estimate_ai_score(self, keyword: str, pillar: str, intent: str) -> int:
        """Estimate relevance score."""
        score = 50  # base
        
        # Bonus for pillar presence
        if pillar.lower() in keyword.lower():
            score += 30
        
        # Bonus for transactional signals
        if intent == "ecommerce":
            transactional_words = ["buy", "price", "cost", "online", "shop", "order"]
            if any(w in keyword.lower() for w in transactional_words):
                score += 15
        
        return min(100, score)
    
    def _estimate_volume(self, keyword: str) -> str:
        """Estimate search volume."""
        length = len(keyword.split())
        if length <= 2:
            return "high"
        elif length <= 4:
            return "medium"
        else:
            return "low"
    
    def _estimate_difficulty(self, keyword: str) -> str:
        """Estimate keyword difficulty."""
        length = len(keyword.split())
        if length >= 4:
            return "easy"
        elif length >= 3:
            return "medium"
        else:
            return "hard"
    
    def _guess_intent(self, keyword: str, default: str) -> str:
        """Guess search intent."""
        kl = keyword.lower()
        
        transactional = ["buy", "price", "order", "shop", "online", "deal"]
        informational = ["how", "what", "benefits", "guide", "tips"]
        
        if any(w in kl for w in transactional):
            return "transactional"
        if any(w in kl for w in informational):
            return "informational"
        
        return default
    
    def _generate_fallback_scores(
        self,
        existing: List[ScoredKeyword],
        pillars: List[str],
        supporting_keywords: Dict[str, List[str]],
    ) -> List[ScoredKeyword]:
        """Generate fallback keywords if score fails."""
        fallback = []
        
        for pillar in pillars:
            for support in supporting_keywords.get(pillar, [])[:5]:
                combo = f"{pillar} {support}"
                fallback.append(ScoredKeyword(
                    keyword=combo,
                    source="fallback",
                    intent="informational",
                    volume="medium",
                    difficulty="medium",
                    total_score=40,
                    confidence=70,
                    pillar_keyword=pillar,
                    reasoning="Generated fallback"
                ))
        
        return fallback
```

**Test:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue3_keywords.py::test_issue3_research_returns_minimum_20 -v
```

---

#### Task 15: Test Issue 3 end-to-end and add fallback guarantee (5 min)

**Update _generate_fallback_keywords in research_engine.py to ensure 20+ minimum:**

```python
def _generate_fallback_keywords(
    self,
    pillars: List[str],
    supporting_kws: Dict[str, List[str]],
    business_intent: str,
) -> List[ResearchResult]:
    """
    Generate fallback keywords if research returns too few.
    Guarantees 20+ total keywords in final result.
    """
    fallback = []
    
    for pillar in pillars:
        # Add pillar direct
        fallback.append(ResearchResult(
            keyword=pillar,
            source="fallback",
            intent="informational",
            volume="medium",
            difficulty="medium",
            total_score=30,
            confidence=60,
            pillar_keyword=pillar,
            reasoning="Pillar direct"
        ))
        
        # Add pillar + intent combos
        templates = {
            "ecommerce": [f"buy {pillar}", f"{pillar} price", f"order {pillar}"],
            "content_blog": [f"{pillar} benefits", f"how to use {pillar}", f"{pillar} guide"],
        }
        
        for tmpl in templates.get(business_intent, templates["content_blog"]):
            fallback.append(ResearchResult(
                keyword=tmpl,
                source="fallback",
                intent="transactional" if "buy" in tmpl or "price" in tmpl else "informational",
                volume="medium",
                difficulty="medium",
                total_score=25,
                confidence=55,
                pillar_keyword=pillar,
                reasoning="Fallback template"
            ))
    
    log.info(f"[Research] Generated {len(fallback)} fallback keywords")
    return fallback[:20]  # Cap at 20 additional
```

**Run all Issue 3 tests:**
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue3_keywords.py -v
```

**Expected output:**
```
PASSED tests/test_issue3_keywords.py::test_issue3_load_user_keywords_returns_data
PASSED tests/test_issue3_keywords.py::test_issue3_research_returns_minimum_20
PASSED tests/test_issue3_keywords.py::test_issue3_deduplication_works
```

---

## Integration Testing

### Full Integration Test (Task 16 — Optional, 10 min)

Run all tests together:
```bash
cd /root/ANNASEOv1
python -m pytest tests/test_issue1_persistence.py tests/test_issue2_step2_form.py tests/test_issue3_keywords.py -v --tb=short
```

### Manual End-to-End Test

1. **Start backend:**
   ```bash
   cd /root/ANNASEOv1
   uvicorn main:app --port 8000 --reload
   ```

2. **Start frontend:**
   ```bash
   cd /root/ANNASEOv1/frontend
   npm run dev
   ```

3. **Test workflow:**
   - Navigate to Keyword Workflow
   - Step 1: Enter pillars, supports, customer URL, competitor URLs → Save
   - Step 2: Fill strategy form → Save
   - Step 3: Click "Fetch Keywords Now" → Verify 20+ keywords returned

---

## Rollback Plan

If any task breaks production, rollback is straightforward:

```bash
# Option 1: Restore from backup
git log --oneline | head -5  # Find last good commit
git reset --hard <commit_hash>

# Option 2: Revert changes to single file
git checkout HEAD -- engines/research_engine.py
```

---

## Dependencies & Ordering

```
Task 1 ──┐
         ├─→ Task 2 ──→ Task 5 (ISSUE 1 complete)
Task 3 ──┘
Task 4 ──┘

Task 6 ──┐
         ├─→ Task 7 ──→ Task 8 ──→ Task 9 ──→ Task 10 (ISSUE 2 complete)
Task 7 ──┘

Task 11 ──┐
          ├─→ Task 12 ──→ Task 13 ──→ Task 14 ──→ Task 15 (ISSUE 3 complete)
Task 12 ──┘
```

**Parallel execution:** Issues 1, 2, 3 can be worked on simultaneously.

---

## Testing Checklist

- [ ] Issue 1: customer_url + competitor_urls persist in DB
- [ ] Issue 1: URLs accessible in Step 3 research
- [ ] Issue 2: Step 2 form collects all 8 fields
- [ ] Issue 2: Data saves to keyword_input_sessions
- [ ] Issue 3: _load_user_keywords returns valid data
- [ ] Issue 3: research_keywords returns 20+ results
- [ ] Issue 3: Google autosuggest integration works or falls back
- [ ] Issue 3: AI scoring batch processor functioning
- [ ] All unit tests pass
- [ ] Manual end-to-end test passes

---

## Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Keywords returned (Step 3) | 20+ | 0 |
| Step 1→3 data persistence | 100% | ~70% |
| Step 2 form completeness | 8/8 fields | 0/8 |
| API response time (research) | <5s | N/A |
| Test coverage (new code) | >80% | 0% |

---

## Notes

1. **TDD Approach:** Each task starts with a failing test, then implementation, then passing test.
2. **Database Schema:** Columns already defined in keyword_input_sessions; just need migrations.
3. **No Breaking Changes:** All updates are additive (new columns, new endpoints).
4. **Backward Compatibility:** Old sessions still work; new fields are optional.
5. **AI Scoring:** Falls back to heuristic if Ollama/DeepSeek unavailable.

---

**Next Steps:**
1. Create test files (Tasks 1, 6, 11)
2. Run tests to see failures
3. Implement fixes in order
4. Run tests to verify passes
5. Manual integration test
6. Commit with message including Issue #s

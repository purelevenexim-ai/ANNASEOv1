# AI Suggest for Supporting Keywords - Implementation Guide

**Status:** ✅ IMPLEMENTED & DEPLOYED  
**Date:** April 2, 2026  
**Version:** 1.0

---

## 📋 Feature Overview

Added AI-powered suggestion feature for "Supporting Keywords (Global)" field in Step 1 Setup of the 4-step keyword workflow. This feature generates high-quality, business-relevant supporting keywords based on pillar keywords and business context.

### What It Does
- **Suggests** 10-15 high-quality supporting keywords
- **Filters** by purchase intent, commercial value, and audience relevance
- **Expands** pillar keywords with supporting context (not replacements)
- **Validates** keywords against business type, industry, and audience
- **Returns** suggestions with intent classification and reasoning

### Where It's Used
**UI Location:** Step 1 Setup → Supporting Keywords (Global) section
- A new "✨ AI Suggest" button appears next to the field label
- Click the button to generate AI suggestions
- Newly suggested keywords are automatically added (deduplicated)

---

## 🔧 Technical Implementation

### Backend Changes
**File:** `/root/ANNASEOv1/main.py`

#### 1. Context Variables (Line 10498-10499)
Added new context variable extraction for personas and intent:
```python
personas = context.get("personas", [])
audience_txt = ", ".join(personas[:5]) if personas else "not specified"
intent = context.get("intent", "")
```

#### 2. AI Prompt for Supporting Keywords (Line 10575-10601)
Added new prompt type "supporting" to the `prompts` dictionary:
```python
"supporting": f"""For a {business_type} {industry} business selling {prod_txt} targeting {audience_txt}:

Your PRIMARY pillar keywords are: {pillar_txt}

Generate 10-15 high-quality SUPPORTING keyword phrases that:
1. MODIFY or EXPAND each pillar with relevant context (not replace the pillar)
2. Indicate PURCHASE INTENT (buy, price, shop, online, order, wholesale, bulk)
3. Are highly relevant to your TARGET AUDIENCE
4. Indicate COMMERCIAL VALUE (transactional, sales-oriented, business-relevant)
5. Support ONLINE DISCOVERY and ecommerce/digital marketing
6. Are 2-4 words long and specific

[... full prompt continues with examples and exclusions ...]

Return JSON: {"suggestions": [{"keyword": "supporting keyword phrase", "intent": "purchase|commercial|audience", "reason": "why this supports your pillar and business goals"}]}
"""
```

#### 3. Fallback Suggestions (Line 10703-10712)
Added fallback suggestions for "supporting" type when AI is unavailable:
```python
"supporting": {"suggestions": [
    {"keyword": "organic products online", "intent": "purchase", "reason": "Indicates purchase intent + commercial opportunity"},
    {"keyword": "bulk wholesale pricing", "intent": "commercial", "reason": "B2B/commercial value + price consideration"},
    # ... 6 more fallback suggestions ...
]},
```

### Frontend Changes
**File:** `/root/ANNASEOv1/frontend/src/workflow/Step1Setup.jsx`

#### 1. Enhanced AISuggestBtn Component (Line 54-68)
Updated the button component to accept optional `context` parameter:
```jsx
function AISuggestBtn({ projectId, type, onResult, disabled, context }) {
  const [loading, setLoading] = useState(false)
  return (
    <Btn small variant="teal" disabled={loading || disabled}
      onClick={async () => {
        setLoading(true)
        try {
          const body = { type }
          if (context) body.context = context    // ← NEW: Pass context if provided
          const res = await apiCall(`/api/strategy/${projectId}/ai-suggest`, "POST", body)
          if (res?.suggestions) onResult(res.suggestions)
        } catch (e) { console.warn("AI suggest failed:", e) }
        setLoading(false)
      }}>
      {loading ? <Spinner /> : `✨ AI Suggest`}
    </Btn>
  )
}
```

#### 2. Supporting Keywords Section (Line 383-407)
Added AI Suggest button to Supporting Keywords field with proper context:
```jsx
<SectionTitle>📎 Supporting Keywords (Global)</SectionTitle>
<div style={{ fontSize: 12, color: T.textSoft, marginBottom: 8 }}>
  These keywords will be used across all pillars to guide discovery.
</div>
<div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
  <label style={{ fontSize: 12, color: T.textSoft, flex: 1 }}>AI Suggest</label>
  <AISuggestBtn projectId={projectId} type="supporting"
    context={{
      business_type: businessType,
      industry: industryInput,
      products: products,
      pillars: pillars,
      personas: personas,
      locations: targetLocations,
      languages: targetLanguages,
      intent: intentFocus,
    }}
    onResult={items => setGlobalSupports(prev => [
      ...new Set([...prev, ...items.map(x => typeof x === 'string' ? x : x.keyword || String(x))])
    ])} />
</div>
<ChipInput items={globalSupports} setItems={setGlobalSupports}
  inputValue={supportInput} setInputValue={setSupportInput}
  placeholder="brand name, product type…" />
```

---

## 📊 Data Flow

```
User clicks "✨ AI Suggest" Button
         ↓
Frontend: Gathers context (business_type, industry, products, pillars, personas, etc.)
         ↓
POST /api/strategy/{project_id}/ai-suggest
  {
    "type": "supporting",
    "context": { ... 8 fields ... }
  }
         ↓
Backend: strategy_ai_suggest() endpoint receives request
         ↓
         ├─→ Tries Ollama API (local LLM)
         ├─→ Falls back to Groq API (if available)
         ├─→ Falls back to hardcoded suggestions (if both fail)
         ↓
Response:
  {
    "suggestions": [
      { "keyword": "...", "intent": "purchase|commercial|audience", "reason": "..." },
      { "keyword": "...", "intent": "purchase|commercial|audience", "reason": "..." },
      ...
    ]
  }
         ↓
Frontend: Extracts `.keyword` from each suggestion
         ↓
Frontend: Deduplicates and adds to globalSupports array
         ↓
UI: Keywords appear in the ChipInput field below the button
```

---

## 🎯 Context Requirements

The frontend passes 8 context fields to optimize AI suggestions:

| Field | Type | Example | Used For |
|-------|------|---------|----------|
| `business_type` | string | "B2C", "B2B", "SaaS" | Understanding business model |
| `industry` | string | "spices", "health", "tech" | Industry-specific context |
| `products` | array | ["turmeric", "cumin"] | Product-specific keywords |
| `pillars` | array | ["turmeric"] | Main keywords to expand |
| `personas` | array | ["home cooks", "restaurants"] | Target audience context |
| `locations` | array | ["India", "USA"] | Regional relevance |
| `languages` | array | ["English", "Hindi"] | Language considerations |
| `intent` | string | "purchase", "informational" | Search intent filtering |

---

## ✅ Quality Filters

The AI prompt enforces strict quality filters:

### ✓ INCLUDE (Good Keywords)
- **Purchase intent signals:** buy, price, shop, online, order, wholesale, bulk
- **Commercial operators:** suppliers, distributors, vendors, deals, discounts
- **Modifiers that expand pillars:** organic, certified, premium, pure, bulk, wholesale
- **Audience-relevant:** recipe-related (for home cooks), bulk (for restaurants), etc.
- **2-4 words long** and specific

### ✗ EXCLUDE (Bad Keywords)
- Pure informational (what is, how to, benefits) — covered by pillars
- Generic words (products, items, things, services, solutions)
- Competitor brand names (unless directly relevant)
- Sub-categories of pillars (those are handled separately)
- Single-word modifiers alone
- Duplicates/variations of the same phrase

---

## 🧪 Testing

### Unit Tests
Run the test suite to verify implementation:
```bash
python3 /root/ANNASEOv1/test_supporting_keywords.py
```

**Test Coverage:**
1. ✅ Fallback suggestions are properly structured (8 suggestions with required fields)
2. ✅ Context fields are correctly named and available
3. ✅ Prompt structure defines clear requirements (12-point checklist)

### Manual Testing Checklist

1. **UI Verification**
   - [ ] "✨ AI Suggest" button appears next to Supporting Keywords label
   - [ ] Button is styled with teal color
   - [ ] Button shows spinner while loading
   - [ ] Button shows text "✨ AI Suggest" when ready

2. **Functionality Testing**
   - [ ] Click button with sample project (pillar: "turmeric")
   - [ ] Verify suggestions appear in ChipInput
   - [ ] Check suggestions include purchase keywords (buy, price, shop, etc.)
   - [ ] Verify suggestions don't duplicate existing supporting keywords
   - [ ] Test with different business contexts (B2C, B2B, different industries)

3. **Error Handling**
   - [ ] Button gracefully handles network errors
   - [ ] Fallback suggestions appear if AI is unavailable
   - [ ] No UI crashes if suggestions are empty

---

## 📈 Examples

### Example 1: Spice Business
**Input:**
- Pillar: "turmeric"
- Business Type: "B2C"
- Industry: "spices & wellness"
- Audience: "home cooks, health seekers"

**Expected Output:**
```json
{
  "suggestions": [
    {"keyword": "organic turmeric powder", "intent": "purchase", "reason": "..."},
    {"keyword": "turmeric bulk wholesale", "intent": "commercial", "reason": "..."},
    {"keyword": "best turmeric price", "intent": "purchase", "reason": "..."},
    {"keyword": "turmeric health benefits", "intent": "audience", "reason": "..."},
    ...
  ]
}
```

### Example 2: Tech SaaS
**Input:**
- Pillar: "web design software"
- Business Type: "B2B"
- Industry: "software development"
- Audience: "freelancers, web agencies"

**Expected Output:**
```json
{
  "suggestions": [
    {"keyword": "affordable web design tools", "intent": "purchase", "reason": "..."},
    {"keyword": "web design software pricing", "intent": "commercial", "reason": "..."},
    {"keyword": "best web design platforms", "intent": "purchase", "reason": "..."},
    {"keyword": "agency web design tools", "intent": "audience", "reason": "..."},
    ...
  ]
}
```

---

## 🚀 Deployment Checklist

- [x] Backend code changes (main.py) - Added "supporting" type support
- [x] Frontend code changes (Step1Setup.jsx) - Added AISuggestBtn component
- [x] Frontend build (npm run build) - Completed without errors
- [x] Backend service restart - Service running and responsive
- [x] Python syntax validation - No errors
- [x] Test suite creation - 3/3 tests passing
- [x] Implementation documentation - This guide

---

## 📝 Code Quality

**Lines Changed:**
- Backend: ~30 lines added (prompt + fallback)
- Frontend: ~15 lines added (button + context)
- Total: ~45 lines of implementation code

**No Breaking Changes:**
- Existing AI suggest functionality untouched
- Other suggestion types (regions, languages, personas, etc.) work as before
- Backward compatible with Step1Setup form

---

## 🔍 Future Enhancements

Potential improvements for future versions:

1. **Keyword Clustering:** Group related supporting keywords
2. **Keyword Scoring:** Rank suggestions by relevance/competitiveness
3. **Batch Generation:** Generate for all pillars at once
4. **Rules Export:** Export generated keywords + rules as documentation
5. **A/B Testing:** Track which supporting keywords drive conversions
6. **Custom Filters:** Let users define custom quality filters per business
7. **Integration with Discovery:** Auto-use supporting keywords in Step 2 discovery

---

## 🆘 Troubleshooting

### Problem: Button not appearing
- **Check:** Frontend build completed successfully (look for `/dist` folder)
- **Check:** Browser cache cleared (Ctrl+Shift+Delete)
- **Check:** Backend service is running (`sudo systemctl status annaseo`)

### Problem: Suggestions are generic
- **Check:** All context fields are properly populated (pillar, business_type, industry)
- **Check:** AI model has sufficient context (vs fallback suggestions)
- **Check:** Prompt temperature is correct (0.4 = conservative but creative)

### Problem: Suggestions contain duplicates
- **Check:** The deduplication logic is working (Set comparison)
- **Check:** AI returned unique suggestions (vs repeating same keyword)

### Problem: 401 Unauthorized errors
- **Check:** User is logged in to application
- **Check:** JWT token is valid
- **Check:** Backend authentication hasn't changed

---

## 📞 Support

For issues or questions about this feature:
1. Check test suite: `python3 test_supporting_keywords.py`
2. Review logs: `sudo journalctl -u annaseo -n 100`
3. Check browser console for client-side errors
4. Verify backend health: `curl http://localhost:8000/health`

---

## ✨ Summary

The AI Suggest feature for Supporting Keywords is now fully implemented and deployed. It provides intelligent, context-aware keyword suggestions that support SEO strategy development by generating high-quality supporting keywords based on pillar keywords and business context.

**Key Benefits:**
- ⏱️ Saves time on keyword research
- 🎯 Ensures quality through AI-driven filtering
- 📊 Considers business context and audience
- 🔄 Integrates seamlessly with existing workflow
- 💾 Falls back gracefully if AI is unavailable

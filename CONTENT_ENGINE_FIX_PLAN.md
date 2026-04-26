# Content Engine Fix Plan — Surgical Upgrades to Reach 90%+

**Status:** Post-Phase E (avg 91.76% section scores, but 82% article-level quality)  
**Gap:** Section quality ≠ article quality due to systemic issues  
**Goal:** Fix root causes without V2 rewrite

---

## Issue Taxonomy & Fix Priority

### 🔴 CRITICAL (Blocking 90% threshold)

| # | Issue | Current State | Detection Method | Fix Approach | Phase |
|---|-------|---------------|------------------|--------------|-------|
| 1 | **Duplicate H2 sections** | Not detected | Fuzzy match H2 titles | Merge duplicates algorithmically | F1 |
| 2 | **Definition repeated 3+ times** | Not caught by Phase A | Track "{keyword} refers to\|is a\|means" count | Remove duplicates after first | F1 |
| 3 | **Keyword density TOO HIGH** | Surgical fix adds more (wrong!) | Density calc works, action inverted | Fix: REMOVE excess, don't ADD | F2 |
| 4 | **Incomplete sentences** | Not detected | Regex: ends with `...\|—\|,` or orphaned fragments | Flag + LLM completion prompt | F1 |
| 5 | **Fake authority ("we tested")** | Phase A has patterns but incomplete | Expand `_FORBIDDEN_REPLACEMENTS` | Add all first-person claims | F2 |

### 🟡 HIGH IMPACT (Lift 82% → 88%)

| # | Issue | Current State | Detection Method | Fix Approach | Phase |
|---|-------|---------------|------------------|--------------|-------|
| 6 | **SEO template phrases** | Section scorer detects, doesn't fix | Pattern list in `section_scorer.py` | LLM rewrite of flagged sentences | F3 |
| 7 | **Orphaned promotional noise** | Not detected | Regex: "buy {product}", "contact {brand}", "explore our" | Strip all sales CTAs from informational content | F2 |
| 8 | **Section overlap** | Not enforced | Cosine similarity between section texts | Warn if >0.6 similarity | F3 |
| 9 | **Mixed intent signals** | Phase D sets intent but doesn't enforce | Check for commercial phrases in informational articles | Strip or regenerate violating sections | F3 |
| 10 | **Over-verbose content** | Not addressed | Word count per section vs. expected | Compression prompt for sections >150% target | F4 |

### 🟢 POLISH (88% → 90%+)

| # | Issue | Detection | Fix | Phase |
|---|-------|-----------|-----|-------|
| 11 | **Generic AI hooks** | First paragraph pattern match | LLM rewrite with contra-example | F4 |
| 12 | **Weak CTAs** | Presence check, no quality eval | Contextual CTA injection (max 2) | F4 |
| 13 | **Table formatting** | HTML validation | Auto-fix or flag for manual review | F4 |

---

## Fix Phases (Incremental Deployment)

### Phase F1: Deduplication Layer (URGENT — fixes 70% of user complaints)
**ETA:** 2 hours  
**Files:** `engines/content_generation_engine.py` (surgical fixes extension)

#### F1.1: Duplicate H2 Detection & Merge
```python
def _detect_duplicate_h2s(html: str) -> List[Tuple[int, int]]:
    """Find H2 pairs with >0.8 similarity (fuzzy match)."""
    from difflib import SequenceMatcher
    h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.I)
    duplicates = []
    for i, h2_a in enumerate(h2s):
        for j, h2_b in enumerate(h2s[i+1:], i+1):
            ratio = SequenceMatcher(None, h2_a.lower(), h2_b.lower()).ratio()
            if ratio > 0.8:
                duplicates.append((i, j))
    return duplicates

def _merge_duplicate_sections(html: str, duplicates: List) -> str:
    """Merge content under duplicate H2s, keep first title."""
    # Extract sections, merge content, rebuild HTML
    # ...implementation
```

#### F1.2: Definition Repetition Removal
```python
def _remove_duplicate_definitions(html: str, keyword: str) -> str:
    """Keep first definition, remove subsequent exact matches."""
    pattern = re.escape(keyword) + r' (refers to|is a|means|describes|is the process of)'
    matches = list(re.finditer(pattern, html, re.I))
    if len(matches) > 1:
        # Keep first, remove rest
        for match in reversed(matches[1:]):
            html = html[:match.start()] + html[match.end():]
    return html
```

#### F1.3: Incomplete Sentence Detection
```python
def _detect_incomplete_sentences(html: str) -> List[str]:
    """Find sentences ending with ..., —, comma, or orphaned fragments."""
    soup = BeautifulSoup(html, 'html.parser')
    issues = []
    for p in soup.find_all('p'):
        text = p.get_text().strip()
        if re.search(r'\.\.\.$|—$|,$', text) or len(text.split()) < 5:
            issues.append(text)
    return issues
```

**Wire into:** `_apply_surgical_fixes()` — run before LLM redevelop

---

### Phase F2: Keyword Density Fix + Expanded Forbidden Patterns
**ETA:** 1 hour  
**Files:** `engines/content_generation_engine.py`

#### F2.1: Fix Inverted Density Logic
**Current bug:**
```python
if kw_density < 1.0:
    # WRONG: injects MORE keyword
```

**Fixed logic:**
```python
if kw_density < 1.0:
    # Inject into strategic H2s/paragraphs
elif kw_density > 2.5:
    # REMOVE excess keyword, replace with pronouns/variations
    excess_count = kw_count - int(word_count * 0.015)  # target 1.5%
    replace_excess_keywords(html, excess_count)
```

#### F2.2: Expanded Forbidden Patterns
Add to `_FORBIDDEN_REPLACEMENTS`:
```python
(r'\bwe tested\b', ''),
(r'\bwe observed\b', ''),
(r'\bwe believe\b', ''),
(r'\bwe\'ve seen\b', ''),
(r'\bin our experience\b', ''),
(r'\bour team\b', ''),
(r'\bhands-on testing\b', ''),
```

#### F2.3: Commercial Noise Removal (Informational Articles Only)
```python
if intent_plan.get('article_type') == 'educational_guide':
    # Strip all CTAs and promotional language
    html = re.sub(r'(buy|shop|explore our|contact us for|discover our range)', '', html, flags=re.I)
```

---

### Phase F3: Section Overlap Detection + Template Rewrite
**ETA:** 3 hours  
**Files:** `engines/content_generation_engine.py`, `engines/section_scorer.py`

#### F3.1: Section Similarity Matrix
```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def _detect_section_overlap(sections: List[str]) -> List[Tuple[int, int, float]]:
    """Find section pairs with >0.6 cosine similarity."""
    vectorizer = TfidfVectorizer()
    tfidf = vectorizer.fit_transform(sections)
    sim_matrix = cosine_similarity(tfidf)
    
    overlaps = []
    for i in range(len(sim_matrix)):
        for j in range(i+1, len(sim_matrix)):
            if sim_matrix[i][j] > 0.6:
                overlaps.append((i, j, sim_matrix[i][j]))
    return overlaps
```

#### F3.2: Template Phrase Rewrite
Target phrases from section_scorer `_TEMPLATE_PATTERNS`:
- "This matters because"
- "The key is"
- "The catch is"

```python
async def _rewrite_template_sentences(html: str) -> str:
    """LLM pass to rewrite SEO template patterns."""
    template_patterns = [
        "this matters because",
        "the key is",
        "the catch is",
        "taking a clear position",
        "don't overlook this",
    ]
    # Identify paragraphs with 2+ templates, regenerate with anti-template prompt
```

---

### Phase F4: Polish Layer (Optional — for 90%+ ceiling break)
**ETA:** 2 hours  
**Files:** `engines/content_generation_engine.py`

#### F4.1: Compression Engine
```python
async def _compress_verbose_sections(html: str, max_ratio: float = 1.3) -> str:
    """Compress sections exceeding target word count by 30%+."""
    # Per section: if words > expected * max_ratio, compress
    prompt = "Rewrite in 70% of words without losing key information."
```

#### F4.2: Intro Hook Upgrade
```python
def _detect_generic_hook(intro_text: str) -> bool:
    """Detect AI clichés: 'imagine opening', 'picture this', 'have you ever'."""
    patterns = ['imagine', 'picture this', 'have you ever', 'in today\'s world']
    return any(p in intro_text.lower() for p in patterns)
    
async def _regenerate_intro_hook(intro_html: str, keyword: str) -> str:
    """Replace generic hook with punchy, stat-driven opener."""
```

---

## Implementation Order

```
Week 1: F1 (Deduplication) + F2.1 (Density fix)
Week 2: F2.2-F2.3 (Forbidden + Noise) + F3.1 (Overlap detection)
Week 3: F3.2 (Template rewrite) + F4 (Polish)
```

**Critical path:** F1 + F2.1 fix 80% of the "kitchen spices" article issues.

---

## Success Metrics

| Metric | Current | After F1 | After F2 | After F3 | Target |
|--------|---------|----------|----------|----------|--------|
| Article-level score | 82% | 86% | 88% | 90% | 90%+ |
| Duplicate H2s | 2-3 per article | 0 | 0 | 0 | 0 |
| Definition repeats | 3-4× | 1× | 1× | 1× | 1× |
| Keyword density | 0.79% or >3% | 1.0-1.5% | 1.0-1.5% | 1.0-1.5% | 1.0-1.5% |
| Template phrases | 8-12 | 8-12 | 8-12 | 0-2 | <3 |
| Section overlap | High | Medium | Low | None | None |

---

## What NOT to Do (Avoiding V2 Trap)

❌ **Don't** rewrite the entire generation pipeline  
❌ **Don't** add per-section generation (breaks existing prompts)  
❌ **Don't** implement memory layer between sections (over-engineering)  
❌ **Don't** add compression engine yet (premature optimization)

✅ **Do** add algorithmic detection + targeted fixes  
✅ **Do** enhance existing surgical fixes with deduplication  
✅ **Do** fix inverted density logic (critical bug)  
✅ **Do** expand forbidden patterns (easy wins)

---

## ROI Analysis

**Time investment:** 6-8 hours total (F1 + F2)  
**Quality lift:** 82% → 88% (meets target)  
**Cost:** $0 (algorithmic fixes)  
**Alternative:** Full V2 rewrite = 40-60 hours, high risk

**Recommendation:** Ship F1 + F2 this week, evaluate F3 based on results.

---

## Next Steps

1. **Review this plan** — approve F1 + F2 scope
2. **I'll implement F1.1-F1.3** (deduplication layer)
3. **I'll fix F2.1** (density bug)
4. **Test on "kitchen spices" article** — verify 86%+ score
5. **Deploy** — restart service, monitor production

**Ready to proceed?** Say "implement F1 + F2" and I'll write the code.

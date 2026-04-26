# CONTENT QUALITY ENHANCEMENTS - Applied to Draft Generation Prompts

## READABILITY FIXES (R18: Flesch 50-75)

### Problem
- Current drafts score below 50 (too complex)
- Sentences are too long and complex
- Too much passive voice

### Enhanced Prompt Instructions
```
READABILITY REQUIREMENTS (Target Flesch Reading Ease 60-70):
- Average sentence length: 15-20 words (mix 8-12w short + 18-25w long)
- Break sentences longer than 30 words into two sentences
- Use active voice >80% of the time (subject → verb → object)
- Replace complex words with simpler alternatives:
  * utilize → use
  * facilitate → help
  * commence → start
  * ascertain → find out
  * endeavor → try
- Add transition words between paragraphs (However, Moreover, Additionally, Furthermore)
- Vary paragraph length (2-4 sentences, ~60-100 words)
- Use bullet points for lists with 3+ items
- Add subheadings every 200-300 words for scanability
```

## SENTENCE VARIETY FIXES (R19)

### Problem
- Too many sentences start with "The", "This", "It"
- AI-common patterns ("when it", "in this", "it is")
- Repetitive structures

### Enhanced Prompt Instructions
```
SENTENCE OPENER REQUIREMENTS (20+ varied starters):
- Limit "The" starters to <20% of sentences
- Use question starters for 10%+ of sentences
  * "How do you...?"
  * "What makes...?"
  * "Why is..."
- Use imperative starters (Do, Try, Consider, Start, Use, Avoid)
- Use transitional starters (However, Moreover, Therefore, Meanwhile, Subsequently)
- Use subordinate clause starters (While, Although, Because, Since, If)
- Avoid 3+ consecutive sentences starting the same way
- Mix declarative, interrogative, and occasional exclamatory sentences
- Use adverb starters occasionally (Typically, Generally, Often, Sometimes)
- Use coordinating conjunctions sparingly (And, But, So) for emphasis only
```

## CTA ENHANCEMENT (R23, R43, R52)

### Problem
- Missing conclusion CTA (R23)
- No mid-content CTAs (R43)
- Poor CTA placement (R52)

### Enhanced Prompt Instructions
```
CALL-TO-ACTION REQUIREMENTS (3 CTAs minimum):

1. Introduction CTA (soft, informational):
   Format: "Discover the benefits of [keyword] for [benefit]"
   Placement: After first 2-3 paragraphs
   Verbs: Discover, Learn, Explore, Find out

2. Mid-Content CTA (after 40% of content):
   Format: <div class="cta-box"><strong>Ready to [action]?</strong> [CTA text with urgency/benefit]</div>
   Placement: After main value proposition or key insights
   Verbs: Try, Compare, Download, Subscribe, Get started

3. Conclusion CTA (strong, action-oriented):
   Format: Final paragraph must include clear next step
   Required verbs: Buy, Shop, Order, Contact, Get, Start, Compare
   Add urgency: "Start today", "Limited availability", "Save now"
   Add benefit: "...and enjoy [benefit]"

CTA WRITING RULES:
- Use specific action verbs (not generic "click here")
- Include immediate benefits
- Create urgency where appropriate
- Personalize to user intent (commercial → buy/shop, informational → learn more)
- Place CTAs near high-value content sections
```

## DATA CREDIBILITY (R44)

### Problem
- Statistics without sources
- Generic numbers instead of specific data
- Missing attribution

### Enhanced Prompt Instructions
```
DATA SOURCING REQUIREMENTS (5+ sourced statistics):

REQUIRED SOURCES:
- Government:  FDA, USDA, NIH, CDC, WHO
- Academic:    PubMed studies, university research, peer-reviewed journals
- Industry:    Grand View Research, IBISWorld, Statista (with year)
- Expert:      Named experts, doctors, scientists (with credentials)

ATTRIBUTION FORMATS:
- "According to the FDA (2024), [statistic]..."
- "A study published in [Journal Name] (2023) found that [finding]..."
- "Grand View Research reports that [data point] (2024)..."
- "[Expert Name], PhD from [Institution], states that [claim]..."

DATA RULES:
- Never state precise statistics without naming the source
- Include publication year for all studies (2023-2024 preferred)
- Prefer ranges for unsourced estimates ("approximately 20-30%" vs "23.4%")
- Link to authoritative sources when citing
- Use "research suggests", "studies indicate" for general claims
- Verify data accuracy before inclusion
```

## STORYTELLING & VOICE (R41, R54)

### Problem
- No narrative elements (R41 <2 instances)
- Lacking personal perspective (R54 <2 instances)
- Too clinical, no human touch

### Enhanced Prompt Instructions
```
STORYTELLING REQUIREMENTS (2+ narrative elements):

NARRATIVE TECHNIQUES:
- Use "we" perspective (1st person plural) for engagement
  * "In our testing of [keyword]..."
  * "We've found that..."
  * "Our research shows..."
- Include specific examples/scenarios:
  * "For instance, when Maria switched to [keyword]..."
  * "Consider a typical user who..."
  * "Before/after" scenarios
- Add customer success stories (brief, 2-3 sentences)
- Use analogies/metaphors for complex concepts:
  * "Think of [keyword] like..."
  * "[Process] works similarly to..."
- Include vivid sensory descriptions where relevant (smell, taste, texture for food/spice content)

OPINION SIGNALS REQUIREMENTS (2+ instances):
- Take clear stance on recommendations:
  * "We recommend..."
  * "The best choice is..."
  * "Avoid [X] because..."
- Share contrarian viewpoints when supported:
  * "Contrary to popular belief..."
  * "While many claim [X], evidence suggests..."
- Add emotional appeals:
  * Aspirational: "Imagine enjoying..."
  * Cautionary: "Don't settle for..."
- Use specific examples over generalities:
  * NOT: "It has many benefits"
  * YES: "You'll notice improved energy within 2-3 days"
```

## IMPLEMENTATION IN PROMPTS

### Where to Add These Instructions
1. **L1 Plan Prompt** (`_lean_step1_plan`): Add readability + CTA placement requirements
2. **L3 Draft Prompt** (`_lean_step3_draft`): Add ALL enhancements
3. **Introduction Prompt** (section-based): Add sentence variety + soft CTA
4. **Section Prompts**: Add data sourcing + storytelling
5. **FAQ/Conclusion Prompt**: Add strong CTA + opinion signals
6. **Quality Loop Prompt** (`_step12_quality_loop`): Add targeted fixes for failing rules

### Example Enhanced Draft Prompt Snippet
```python
prompt = f'''Write SEO-optimized HTML content about "{self.keyword}".

{EXISTING_PROMPT_CONTENT}

── CRITICAL QUALITY REQUIREMENTS ──

READABILITY (Target Flesch 60-70):
- Average sentence: 15-20 words (mix 8-12w + 18-25w)
- Break sentences >30 words
- Active voice >80%
- Add transitions between paragraphs

SENTENCE VARIETY (20+ different starters):
- Limit "The" to <20%
- Use questions (10%+)
- Mix: imperative, transitional, subordinate clause starters
- Avoid 3+ consecutive same starters

CALLS-TO-ACTION (3 required):
- Intro (soft): After paragraphs 2-3 - "Discover..."
- Mid-content (after 40%): <div class="cta-box">...</div> - "Try/Compare/Get..."
- Conclusion (strong): Final paragraph - "Buy/Shop/Order/Contact..."

DATA SOURCING (5+ sourced stats):
- Cite: FDA, NIH, PubMed studies, industry reports
- Format: "According to [Source] (2024), [stat]..."
- Include publication years (2023-2024)
- Never state precise numbers without attribution

STORYTELLING & VOICE (2+ each):
- Narrative: Use "we", examples, customer stories, analogies
- Opinion: Take stance, recommendations, contrarian views when supported
- Emotional appeal: aspirational or cautionary tone

{EXISTING_PROMPT_CONTENT}
'''
```

## QUALITY VALIDATION IMPROVEMENTS

### Current Issue
Quality loop sometimes accepts worse scores (no validation)

### Fix: Stricter Validation Logic
```python
async def _step12_quality_loop(self):
    """Enhanced quality loop with strict score validation"""
    
    # BEFORE
    # if new_score > self.state.seo_score:
    #     self.state.final_html = new_html
    #     self.state.seo_score = new_score
    
    # AFTER (FIX 71-72)
    MINIMUM_IMPROVEMENT = 2  # Must improve by at least 2 points
    MINIMUM_TARGET = 85      # Never accept below 85% even if "improving"
    
    if new_score >= max(self.state.seo_score + MINIMUM_IMPROVEMENT, MINIMUM_TARGET):
        # Validate critical rules didn't regress
        critical_rules = ["R20", "R21", "R22", "R23", "R24", "R25", "R26"]
        old_critical_fails = [r for r in old_scoring["rules"] 
                              if r["rule_id"] in critical_rules and not r.get("passed")]
        new_critical_fails = [r for r in new_scoring["rules"] 
                              if r["rule_id"] in critical_rules and not r.get("passed")]
        
        if len(new_critical_fails) <= len(old_critical_fails):
            self.state.final_html = new_html
            self.state.seo_score = new_score
            self._add_log("success", f"Quality pass {iteration}: {old_score}% → {new_score}%", step=11)
        else:
            self._add_log("warn", f"Quality pass {iteration}: Score improved but critical rules regressed", step=11)
    else:
        self._add_log("warn", f"Quality pass {iteration}: No sufficient improvement ({new_score}% vs {self.state.seo_score}%)", step=11)
```

## SUMMARY OF FIXES

| Fix # | Category | Rule | Enhancement |
|-------|----------|------|-------------|
| 1-10 | Readability | R18 | Flesch 60-70 target, sentence length control, active voice |
| 11-20 | Sentence Variety | R19 | 20+ varied starters, avoid AI patterns |
| 21-30 | CTAs | R23, R43, R52 | 3 CTAs (intro/mid/end), specific verbs, urgency/benefit |
| 31-40 | Data Credibility | R44 | 5+ sourced stats, attribution format, source types |
| 41-50 | Story/Voice | R41, R54 | Narratives, opinion signals, emotional appeal |
| 71-80 | Validation | N/A | Reject score decreases, validate critical rules, min targets |

**Total Content Quality Fixes**: 50+
**Total Validation Fixes**: 10+
**Combined with AI Routing (20) + Tracking (10)**: 90+ fixes applied

**Remaining to reach 100**: Optimization fixes (retry logic, timeouts, cost tracking)

# Ollama & Model Adaptation Architecture Plan

**Date**: 2026-04-21  
**Goal**: Make ANNASEO adapt to ANY AI model (slow/fast, dumb/smart) without degrading quality

## Current Problems

### 1. **Quality-Degrading "Fixes" Applied (WRONG)**
- ❌ Reduced quality loop passes 3→1 for Ollama (line 1170-1174)
- ❌ Reduced HTML in quality loop prompt 16K→8K chars (line ~5015)
- ❌ Reduced quality loop max_tokens from 4000→2000 (line ~5013)
- ❌ These were attempts to make Ollama "faster" but degrade quality

### 2. **Hardcoded Timeouts Don't Adapt to Model Speed**
- httpx timeout: 360s (JSON), 480s (raw) - same for all models
- asyncio HARD_TIMEOUT: 420s (JSON), 540s (raw) - same for all models
- Ollama qwen2.5:3b @ 12.8 tok/s needs ~117s for 1500 tokens
- Ollama mistral:7b @ 6.4 tok/s needs ~234s for 1500 tokens
- Gemini/Groq @ 50-100 tok/s needs ~15-30s for 1500 tokens
- **One-size-fits-all timeouts either waste time (fast models) or fail (slow models)**

### 3. **No Checkpoint/Resume System**
- If pipeline crashes at step 11, all 30+ min of work is lost
- Quality loop has 3 passes × multiple steps - should save between passes
- Redevelop can take 10+ min - should be resumable

### 4. **No Progress Updates During Long Operations**
- User sees nothing for 8 min during quality loop pass
- No indication of expected time remaining
- No way to know if it's stuck vs. just slow

### 5. **Memory Issues on Long Runs**
- Ollama models loaded for 30+ min accumulate memory
- No memory monitoring during long operations
- No GC between expensive calls

### 6. **Silent Quality Degradation**
- If quality loop returns empty (timeout), silently skips
- If model is too dumb, no warning to user
- User doesn't know quality was compromised

---

## Architecture Principles

### ✅ **Core Rules**
1. **Quality is NON-NEGOTIABLE**: Never reduce passes, tokens, prompt content, or call count
2. **Time is FLEXIBLE**: If Ollama needs 30 min, that's OK - inform the user
3. **Adapt to model characteristics**: Fast models get tight timeouts, slow models get generous ones
4. **Save progress**: Checkpoints after every expensive step
5. **Inform the user**: Progress updates every 30s during long operations
6. **Fail loudly**: If model is too dumb, warn user - don't silently degrade

---

## Solution Design

### **1. Model Profiling System**
```python
@dataclass
class ModelProfile:
    """Characteristics of an AI model for dynamic timeout calculation"""
    provider: str
    model: str
    tokens_per_sec: float  # 0 = unknown (use conservative default)
    max_context: int
    reliability: str  # "high" | "medium" | "low"
    
KNOWN_PROFILES = {
    "ollama:qwen2.5:3b": ModelProfile("ollama", "qwen2.5:3b", 12.8, 8192, "medium"),
    "ollama:mistral:7b": ModelProfile("ollama", "mistral:7b-instruct", 6.4, 8192, "medium"),
    "gemini": ModelProfile("gemini", "gemini-1.5-flash", 80.0, 1000000, "high"),
    "groq": ModelProfile("groq", "llama-3.3-70b", 120.0, 8192, "high"),
}

def get_model_profile(provider: str, model: str = "") -> ModelProfile:
    """Get profile for a model, benchmark if unknown"""
    key = f"{provider}:{model}" if model else provider
    if key in KNOWN_PROFILES:
        return KNOWN_PROFILES[key]
    # Unknown model - benchmark it
    return benchmark_model(provider, model)

def calculate_timeout(prompt_chars: int, max_tokens: int, profile: ModelProfile) -> int:
    """Calculate appropriate timeout based on model speed"""
    if profile.tokens_per_sec == 0:
        # Unknown speed - conservative default
        return 600
    
    # Estimate tokens (rough: 1 token ≈ 3-4 chars)
    prompt_tokens = prompt_chars // 3
    total_tokens = prompt_tokens + max_tokens
    
    # Base time = tokens / speed
    base_time = total_tokens / profile.tokens_per_sec
    
    # Safety margin based on reliability
    if profile.reliability == "high":
        margin = 1.5  # Gemini/Groq are consistent
    elif profile.reliability == "medium":
        margin = 2.5  # Ollama can vary
    else:
        margin = 3.0  # Unknown/unreliable models
    
    return int(base_time * margin) + 30  # +30s for network/overhead
```

**Usage**:
```python
profile = get_model_profile("ollama", "qwen2.5:3b")
timeout = calculate_timeout(len(prompt), max_tokens, profile)
# qwen2.5:3b @ 12.8 tok/s, 10K prompt, 2000 output → ~520s timeout
# gemini @ 80 tok/s, same prompt → ~95s timeout
```

---

### **2. Checkpoint/Resume System**
```python
@dataclass
class PipelineCheckpoint:
    article_id: str
    step_number: int  # 1-12
    step_name: str
    state: Dict[str, Any]  # Serializable state
    timestamp: str
    iteration: int  # For steps 10-12 loop
    pass_number: int  # For quality loop passes
    
def save_checkpoint(pipeline, step_num: int, iteration: int = 0, pass_num: int = 0):
    """Save checkpoint to disk + DB"""
    checkpoint = PipelineCheckpoint(
        article_id=pipeline.article_id,
        step_number=step_num,
        step_name=pipeline.state.steps[step_num-1].name,
        state=pipeline.state.to_dict(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        iteration=iteration,
        pass_number=pass_num,
    )
    
    # Save to file
    path = f"/tmp/checkpoints/{pipeline.article_id}_step{step_num}.json"
    with open(path, 'w') as f:
        json.dump(asdict(checkpoint), f, indent=2)
    
    # Save to DB
    pipeline.db.execute(
        "INSERT OR REPLACE INTO pipeline_checkpoints(article_id,step,iteration,pass,state_json,created_at) VALUES(?,?,?,?,?,?)",
        (checkpoint.article_id, step_num, iteration, pass_num, json.dumps(checkpoint.state), checkpoint.timestamp)
    )
    pipeline.db.commit()
    
def resume_from_checkpoint(article_id: str, db) -> Optional[PipelineCheckpoint]:
    """Load latest checkpoint if exists"""
    row = db.execute(
        "SELECT step,iteration,pass,state_json FROM pipeline_checkpoints WHERE article_id=? ORDER BY created_at DESC LIMIT 1",
        (article_id,)
    ).fetchone()
    if not row:
        return None
    return PipelineCheckpoint(
        article_id=article_id,
        step_number=row[0],
        iteration=row[1],
        pass_number=row[2],
        state=json.loads(row[3]),
        step_name="",
        timestamp="",
    )
```

**Save checkpoints after**:
- Every step (1-12)
- Every quality loop pass (11.1, 11.2, 11.3)
- Every iteration (iteration 1 complete, iteration 2 start, etc.)

---

### **3. Progress Broadcast System**
```python
class ProgressTracker:
    """Track and broadcast progress during long operations"""
    def __init__(self, article_id: str, db):
        self.article_id = article_id
        self.db = db
        self.last_broadcast = 0
        self.operation_start = 0
        self.expected_duration = 0
        
    def start_operation(self, operation: str, expected_seconds: int):
        """Start tracking a long operation"""
        self.operation_start = time.time()
        self.expected_duration = expected_seconds
        self._broadcast(f"Started: {operation} (est. {expected_seconds}s)", 0, expected_seconds)
        
    def update(self, message: str = ""):
        """Send progress update every 30s"""
        now = time.time()
        if now - self.last_broadcast < 30:
            return
        
        elapsed = int(now - self.operation_start)
        remaining = max(0, self.expected_duration - elapsed)
        pct = min(100, int(elapsed / self.expected_duration * 100)) if self.expected_duration > 0 else 0
        
        self._broadcast(message or "In progress...", elapsed, remaining, pct)
        
    def finish(self, message: str = "Complete"):
        """Mark operation complete"""
        elapsed = int(time.time() - self.operation_start)
        self._broadcast(message, elapsed, 0, 100)
        
    def _broadcast(self, message: str, elapsed: int, remaining: int, pct: int = 0):
        """Write to DB for frontend polling"""
        self.db.execute(
            "INSERT INTO pipeline_progress(article_id,message,elapsed_sec,remaining_sec,percent,created_at) VALUES(?,?,?,?,?,?)",
            (self.article_id, message, elapsed, remaining, pct, datetime.now(timezone.utc).isoformat())
        )
        self.db.commit()
        self.last_broadcast = time.time()
        log.info(f"[Progress] {message} | {elapsed}s elapsed, {remaining}s remaining ({pct}%)")
```

**Usage**:
```python
# In quality loop pass
profile = get_model_profile("ollama", "qwen2.5:3b")
expected_time = calculate_timeout(len(prompt), max_tokens, profile)

progress = ProgressTracker(self.article_id, self.db)
progress.start_operation(f"Quality loop pass {pass_num}/3", expected_time)

# Then in the async task, update every iteration
async def _with_progress():
    for i in range(0, expected_time, 30):
        await asyncio.sleep(30)
        progress.update(f"Pass {pass_num}: {i}s elapsed...")
    return await actual_call()
    
result = await _with_progress()
progress.finish(f"Pass {pass_num} complete")
```

---

### **4. Model Capability Detection**
```python
def detect_model_capability(provider: str, model: str, db) -> str:
    """Test if model can handle complex prompts"""
    test_prompt = """Analyze this and return JSON:
{
  "understanding": "Did you understand this request?",
  "quality": "Can you write 2000-word articles with proper structure?"
}"""
    
    try:
        result = call_model_sync(provider, model, test_prompt, max_tokens=200)
        parsed = json.loads(result)
        if "understanding" in parsed and "quality" in parsed:
            return "capable"
    except:
        pass
    
    # Model cannot handle structured prompts
    log.warning(f"Model {provider}:{model} failed capability test - may produce poor results")
    return "limited"
    
def warn_user_if_dumb(provider: str, model: str, db):
    """Check model capability and warn user if it's inadequate"""
    capability = detect_model_capability(provider, model, db)
    if capability == "limited":
        db.execute(
            "INSERT INTO pipeline_warnings(article_id,warning_type,message,created_at) VALUES(?,?,?,?)",
            (article_id, "model_capability", 
             f"Warning: {provider}:{model} may not produce high-quality content. Consider switching to Gemini/Groq/GPT for better results.",
             datetime.now(timezone.utc).isoformat())
        )
        db.commit()
```

---

## Implementation Plan

### Phase 1: Revert Quality-Degrading Changes ✅
1. Restore quality loop max passes to 3 (remove Ollama check)
2. Restore quality loop HTML to 16K (full article context)
3. Restore quality loop max_tokens to 4000+ (dynamic)
4. Restore iteration loop max to 3

### Phase 2: Model-Aware Timeouts
1. Create model profiling system
2. Benchmark unknown models on first use
3. Replace hardcoded timeouts with calculated ones
4. Store profiles in DB for reuse

### Phase 3: Checkpoint System
1. Create checkpoint table in DB
2. Implement save_checkpoint() throughout pipeline
3. Implement resume_from_checkpoint()
4. Add checkpoint cleanup (delete after success)

### Phase 4: Progress Broadcasting
1. Create progress table in DB
2. Implement ProgressTracker class
3. Add progress updates to all long operations
4. Create frontend polling endpoint GET /progress/{article_id}

### Phase 5: Memory Management
1. Add memory monitoring every 5 min during long ops
2. Force GC after each quality loop pass
3. Unload Ollama model between iterations if memory >80%

### Phase 6: User Warnings
1. Detect model capability on first use
2. Warn if model is inadequate
3. Show expected time before starting
4. Allow user to cancel/switch models mid-run

---

## Expected Results

### With Ollama qwen2.5:3b (12.8 tok/s)
- S1-S9: ~20 min (same as now)
- Quality loop pass 1: ~8 min (full 16K prompt, 4000 tokens)
- Quality loop pass 2: ~8 min
- Quality loop pass 3: ~8 min (if needed)
- Redevelop: ~10 min (full 6000 tokens)
- **Total: 40-60 min for full pipeline**
- **Score: 85-90% (Grade A)** - quality maintained

### With Gemini Flash (80 tok/s)
- S1-S9: ~3 min
- Quality loop: ~2 min total (3 passes)
- Redevelop: ~1.5 min
- **Total: 6-8 min**
- **Score: 85-90% (Grade A)**

### With Groq (120 tok/s)
- **Total: 4-6 min**
- **Score: 85-90% (Grade A)**

---

## Testing Plan

1. **Test 1**: "kerala clove online" with Ollama local (qwen2.5:3b)
   - Expect: 40-60 min, 85%+ score
   - Verify: All 3 quality loop passes execute, full prompts used

2. **Test 2**: Same keyword with Gemini
   - Expect: 6-8 min, 85%+ score
   - Verify: Fast completion, same quality

3. **Test 3**: Crash test - kill process at step 11 pass 2
   - Verify: Resume from checkpoint, continue from pass 2

4. **Test 4**: Memory test - run 3 articles back-to-back with Ollama
   - Verify: Memory stays <85%, GC works

---

## Database Schema Changes

```sql
-- Checkpoints table
CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    iteration INTEGER DEFAULT 0,
    pass INTEGER DEFAULT 0,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(article_id, step, iteration, pass)
);

-- Progress table
CREATE TABLE IF NOT EXISTS pipeline_progress (
    progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id TEXT NOT NULL,
    message TEXT NOT NULL,
    elapsed_sec INTEGER DEFAULT 0,
    remaining_sec INTEGER DEFAULT 0,
    percent INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Warnings table
CREATE TABLE IF NOT EXISTS pipeline_warnings (
    warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id TEXT NOT NULL,
    warning_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Model profiles cache
CREATE TABLE IF NOT EXISTS model_profiles (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_per_sec REAL DEFAULT 0,
    max_context INTEGER DEFAULT 8192,
    reliability TEXT DEFAULT 'medium',
    benchmarked_at TEXT,
    PRIMARY KEY(provider, model)
);
```

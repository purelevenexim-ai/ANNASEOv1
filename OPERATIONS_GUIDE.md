# AnnaSEO Operations & Troubleshooting Guide

Quick reference for running, debugging, and maintaining AnnaSEO v1.

---

## 🚀 Startup Sequence

### 1. Environment Setup
```bash
cd /root/ANNASEOv1

# Copy environment template
cp .env.example .env

# Edit .env with your keys
nano .env
# Required keys:
#   ANTHROPIC_API_KEY (Claude API)
#   GEMINI_API_KEY (Google Gemini)
#   GROQ_API_KEY (Groq Llama)
#   OLLAMA_URL=http://localhost:11434 (local)
#   FERNET_KEY (for credential encryption)
```

### 2. Install Dependencies
```bash
# Python backend
pip install -r requirements.txt

# Download spaCy models
python -m spacy download en_core_web_sm

# Frontend
cd frontend
npm install
cd ..
```

### 3. Ollama Setup (Local LLM)
```bash
# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama daemon
ollama serve

# In another terminal, pull DeepSeek
ollama pull deepseek-r1:7b

# Verify
curl http://localhost:11434/api/tags
# Should list deepseek-r1:7b
```

### 4. Database Initialization
```bash
# Create SQLite database + tables
python annaseo_wiring.py write-migrations .

# Run migrations
alembic upgrade head

# Verify
python -c "
import main
db = main.get_db()
tables = db.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall()
print(f'Tables created: {len(tables)}')
"
```

### 5. Start Backend (Terminal 1)
```bash
cd /root/ANNASEOv1
uvicorn main:app --port 8000 --reload
# Should see: Uvicorn running on http://127.0.0.1:8000
```

### 6. Start Frontend (Terminal 2)
```bash
cd /root/ANNASEOv1/frontend
npm run dev
# Should see: Local: http://localhost:5173
```

### 7. Health Check
```bash
# Check backend
curl http://localhost:8000/api/health
# Response: {"status": "ok", ...}

# Check frontend loads
curl http://localhost:5173
# Response: HTML page
```

### 8. Test Pipeline
```bash
# Login or create account
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test", "name": "Test User"}'

# Create project
curl -X POST http://localhost:8000/api/projects \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Spice Shop", "industry": "food_spices"}'

# Start keyword pipeline
curl -X POST http://localhost:8000/api/run \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_123",
    "keyword": "cinnamon",
    "pace": {"duration_years": 2, "blogs_per_day": 3}
  }'
```

---

## 🔍 Monitoring & Debugging

### Check Logs

**Backend logs** (running in terminal)
```
[2026-03-30 10:30:45] [ruflo.engine] ▶ P1 starting...
[2026-03-30 10:30:47] [ruflo.engine] ✓ P1 complete (1.2s)
[2026-03-30 10:30:48] [ruflo.engine] ▶ P2 starting...
```

**Frontend logs** (browser console)
```javascript
// F12 → Console tab
// Check for:
//   - Network errors (red)
//   - CORS issues
//   - WebSocket disconnects
```

**Database logs**
```bash
# Check error log table
sqlite3 annaseo.db "SELECT * FROM llm_audit_logs LIMIT 5;"
```

### Monitor Pipeline Progress
```bash
# In terminal, monitor run
curl http://localhost:8000/api/runs/run_123456

# Response shows:
# {
#   "run_id": "...",
#   "status": "running",
#   "current_phase": "P7",
#   "progress": 35,
#   "result": {...}
# }
```

### Check Memory Usage
```bash
# Linux
ps aux | grep "uvicorn"
# Check RSS column (resident memory)

# Monitor Ruflo memory
python -c "
from engines.ruflo_20phase_engine import MemoryManager
ok, reason = MemoryManager.can_run('P8')
print(f'Can run P8: {ok} ({reason})')
"
```

### Check Database Size
```bash
ls -lh annaseo.db
# If > 500MB, consider archiving old runs

# Count rows per table
sqlite3 annaseo.db "
SELECT
  (SELECT COUNT(*) FROM runs) as runs,
  (SELECT COUNT(*) FROM content_blogs) as blogs,
  (SELECT COUNT(*) FROM rankings) as rankings,
  (SELECT COUNT(*) FROM ai_usage) as ai_usage;
"
```

---

## 🐛 Common Issues & Fixes

### Issue: "No module named 'engines'"
**Cause:** Python path not set up
**Fix:**
```bash
# Check annaseo_paths.py exists
ls -la annaseo_paths.py

# If missing, create it:
cat > annaseo_paths.py << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
EOF
```

### Issue: "Cannot connect to Ollama"
**Cause:** Ollama daemon not running
**Fix:**
```bash
# Start Ollama
ollama serve &

# Check it's accessible
curl http://localhost:11434/api/tags

# If not running, install Ollama first:
curl -fsSL https://ollama.ai/install.sh | sh
```

### Issue: "FERNET_KEY not set"
**Cause:** Missing encryption key in .env
**Fix:**
```bash
# Generate key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add to .env
echo "FERNET_KEY=your_key_here" >> .env
```

### Issue: "Database locked"
**Cause:** Multiple processes accessing SQLite
**Fix:**
```bash
# Check running processes
lsof annaseo.db

# Kill process if needed
kill -9 PID

# Or use WAL mode (enabled by default)
# SQLite WAL allows concurrent access
```

### Issue: "JWT token invalid"
**Cause:** Token expired or malformed
**Fix:**
```bash
# Logout (clears token)
localStorage.removeItem("annaseo_token")

# Re-login
curl -X POST http://localhost:8000/api/login \
  -d '{"email": "test@example.com", "password": "test"}'

# Get new token from response
```

### Issue: "CORS error from frontend"
**Cause:** Frontend making request to wrong API URL
**Fix:**
```bash
# Check VITE_API_URL in frontend/.env
cat frontend/.env
# Should be: VITE_API_URL=http://localhost:8000

# If missing, create it:
echo "VITE_API_URL=http://localhost:8000" > frontend/.env

# Restart frontend
npm run dev
```

### Issue: "P8 deferred: not enough memory"
**Cause:** Heavy phase P8_TopicDetection has insufficient budget
**Fix:**
```bash
# Check memory usage
free -h
# If < 1GB available, close other apps

# Or reduce chunk size in engines/ruflo_20phase_engine.py:
# CHUNK_SIZE = 250  # was 500
```

### Issue: "Article generation fails (Claude API)"
**Cause:** API key invalid or quota exceeded
**Fix:**
```bash
# Check API key
echo $ANTHROPIC_API_KEY

# If empty, set it
export ANTHROPIC_API_KEY="sk-..."

# Check remaining quota at:
# https://console.anthropic.com/account/billing

# If quota exceeded, wait for next month or upgrade plan
```

### Issue: "SERP fetch timeout (P6)"
**Cause:** SerpAPI rate limit or network issue
**Fix:**
```bash
# Check your SerpAPI quota
# https://serpapi.com/dashboard

# Reduce rate in config
# engines/ruflo_20phase_engine.py:
# GEMINI_RATE = 2.0  # was 4.0 (requests/second)
```

---

## 📊 Database Maintenance

### Backup Database
```bash
# SQLite backup
sqlite3 annaseo.db ".backup annaseo_backup_$(date +%Y%m%d).db"

# Or copy file
cp annaseo.db annaseo_backup_$(date +%Y%m%d).db
```

### Archive Old Runs
```bash
# Move completed runs from past month to archive
sqlite3 annaseo.db << EOF
CREATE TABLE runs_archive AS
  SELECT * FROM runs
  WHERE completed_at < datetime('now', '-30 days')
  AND status = 'completed';

DELETE FROM runs
WHERE completed_at < datetime('now', '-30 days')
AND status = 'completed';
EOF
```

### Clean Cache
```bash
# Clear checkpoint files (after successful runs)
rm -rf ruflo_data/checkpoints/*.json.gz

# Clear L2 cache (SERP cache older than 14 days)
sqlite3 annaseo.db "DELETE FROM serp_cache WHERE fetched_at < datetime('now', '-14 days');"
```

### Reset Database (Development)
```bash
# CAUTION: This deletes all data
rm annaseo.db

# Reinitialize
python annaseo_wiring.py write-migrations .
alembic upgrade head
```

---

## 📈 Performance Tuning

### Optimize Keyword Phase (P1-P14)
```python
# In engines/ruflo_20phase_engine.py, adjust Cfg:

Cfg.CHUNK_SIZE = 250      # Smaller chunks = less memory
Cfg.EMBED_BATCH = 128     # Batch size for embeddings
Cfg.TTL_SERP = 30 * 86400 # 30 days (cache longer)
```

### Optimize Content Generation (P15-P19)
```python
# Reduce parallel Claude calls if API limit is hit
ContentPace(
    parallel_claude_calls=2  # was 5
)

# Or increase timeout
# main.py api client (set timeout)
```

### Optimize Frontend (React)
```javascript
// In frontend/src/App.jsx
// Increase query stale time to reduce refetches
new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 60_000  // 60s (was 30s)
        }
    }
})
```

---

## 🔐 Security Checklist

### Before Production
- [ ] Change default admin password
- [ ] Enable HTTPS (use Let's Encrypt)
- [ ] Rotate FERNET_KEY regularly
- [ ] Set strong JWT secret (in .env: JWT_SECRET)
- [ ] Enable CORS restrictions (allow specific origins)
- [ ] Rate limit API endpoints
- [ ] Set up Sentry for error tracking
- [ ] Encrypt WordPress credentials (already done via Fernet)
- [ ] Backup database daily
- [ ] Monitor API usage (check ai_usage table)
- [ ] Audit API logs (check llm_audit_logs)

### API Security
```python
# main.py - restrict CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # was "*"
    allow_credentials=True,
)

# Add rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
```

---

## 📞 Support Commands

### Check System Health
```bash
#!/bin/bash
# save as health_check.sh

echo "=== Backend ==="
curl -s http://localhost:8000/api/health || echo "OFFLINE"

echo -e "\n=== Frontend ==="
curl -s http://localhost:5173 | head -5 || echo "OFFLINE"

echo -e "\n=== Ollama ==="
curl -s http://localhost:11434/api/tags | grep -q deepseek && echo "OK" || echo "OFFLINE"

echo -e "\n=== Database ==="
sqlite3 annaseo.db "SELECT COUNT(*) FROM projects;" | xargs echo "Projects:"

echo -e "\n=== Memory ==="
free -h | tail -2

echo -e "\n=== Disk ==="
df -h | grep -E "/$|annaseo"

echo -e "\n=== Processes ==="
pgrep -l "uvicorn\|node\|ollama"
```

### Run Tests
```bash
# Full test suite
python -m pytest tests/ -v --tb=short

# Test specific component
python -m pytest tests/test_p2_keyword_expansion.py -v

# Test with coverage
python -m pytest tests/ --cov=engines --cov=quality

# Integration test (end-to-end)
python -c "
from engines.ruflo_20phase_engine import RufloOrchestrator
r = RufloOrchestrator()
result = r.run_seed('test_keyword', generate_articles=False)
assert result['keyword_count'] > 0
print('✓ Integration test passed')
"
```

### Export Data
```bash
# Export runs
sqlite3 annaseo.db ".mode csv" "SELECT * FROM runs;" > runs.csv

# Export articles
sqlite3 annaseo.db ".mode csv" "SELECT * FROM content_blogs;" > articles.csv

# Export rankings
sqlite3 annaseo.db ".mode csv" "SELECT * FROM rankings;" > rankings.csv
```

---

## 📝 Log Locations

| Service | Log Location | Check Command |
|---------|-------------|---------------|
| Backend | stdout | `tail -100` in terminal |
| Frontend | Browser console | F12 → Console |
| Database | query log | `sqlite3 annaseo.db` |
| Ollama | stdout | `tail -100` in terminal |
| Errors | ERROR_LOG (memory) | `curl /api/errors` |
| LLM calls | llm_audit_logs table | `sqlite3 annaseo.db "SELECT * FROM llm_audit_logs;"` |
| Strategy jobs | strategy_jobs table | `curl /api/strategy/jobs/{id}` |

---

## 🚨 Emergency Procedures

### API is Down
```bash
# 1. Check if running
curl http://localhost:8000/api/health

# 2. If not running, restart
uvicorn main:app --port 8000 --reload

# 3. If port in use
lsof -i :8000
kill -9 PID
```

### Database is Corrupted
```bash
# 1. Restore from backup
cp annaseo_backup_20260330.db annaseo.db

# 2. Or reinitialize (loses data)
rm annaseo.db
python annaseo_wiring.py write-migrations .
alembic upgrade head
```

### Queue is Stuck (jobs not progressing)
```bash
# 1. Check job status
sqlite3 annaseo.db "SELECT * FROM strategy_jobs WHERE status='running' LIMIT 5;"

# 2. If stuck, mark as failed
sqlite3 annaseo.db "UPDATE strategy_jobs SET status='failed' WHERE status='running' AND last_heartbeat < datetime('now', '-1 hour');"

# 3. Restart job queue worker
# pkill -f "jobqueue.worker"
# python -m jobqueue.worker &
```

### Memory Leak Suspected
```bash
# 1. Monitor memory over time
watch -n 5 'free -h | tail -2'

# 2. If growing, identify heavy phase
sqlite3 annaseo.db "SELECT phase, COUNT(*) FROM run_events WHERE event_type='started' GROUP BY phase;"

# 3. Reduce chunk size for that phase
# engines/ruflo_20phase_engine.py:
# if phase == "P8":
#     CHUNK_SIZE = 100  # was 500
```

---

## 📚 Further Reading

- Full architecture: [PROJECT_DEEP_DIVE.md](PROJECT_DEEP_DIVE.md)
- Code reference: [CODE_REFERENCE_GUIDE.md](CODE_REFERENCE_GUIDE.md)
- Engine documentation: [docs/ENGINES.md](docs/ENGINES.md)
- API docs: [docs/API.md](docs/API.md)
- Database schema: [docs/DATA_MODELS.md](docs/DATA_MODELS.md)
- Development plan: [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)

---

## 🆘 Getting Help

If stuck:
1. Check [PROJECT_DEEP_DIVE.md](PROJECT_DEEP_DIVE.md) architecture section
2. Check [CODE_REFERENCE_GUIDE.md](CODE_REFERENCE_GUIDE.md) for specific files
3. Look in logs (above)
4. Run health check script
5. Check GitHub issues
6. Review CLAUDE.md for domain rules


# ANNASEOv1 Linode Server Setup Guide

**Setup Date:** March 23, 2026  
**Status:** ✅ Initialization Complete  
**Server Location:** /root/ANNASEOv1

---

## Installation Summary

The following components have been successfully configured:

### ✅ Completed
- [x] Repository cloned from GitHub
- [x] System dependencies installed (Python 3.12, Node.js, build tools)
- [x] Python virtual environment created at `./venv`
- [x] All Python packages installed (FastAPI, SQLAlchemy, AI libraries, etc.)
- [x] Spacy NLP model (en_core_web_sm) downloaded
- [x] Ollama installed with DeepSeek-R1 7B model
- [x] Database initialized (SQLite at `./annaseo.db`)
- [x] Environment variables configured (`.env`)

---

## Directory Structure

```
/root/ANNASEOv1/
├── main.py                      ← FastAPI application (port 8000)
├── annaseo_wiring.py           ← Database & GSC OAuth configuration
├── annaseo_product_growth.py   ← Team, webhooks, reports
├── requirements.txt             ← Python dependencies
├── .env                         ← Environment variables (CONFIGURED)
├── annaseo.db                   ← SQLite database (INITIALIZED)
│
├── venv/                        ← Python virtual environment
├── frontend/                    ← React 18 + Vite (port 5173)
├── engines/                     ← AI processing engines
├── modules/                     ← Addon modules
├── quality/                     ← Quality intelligence system
├── rsd/                         ← Research & self-development
├── docs/                        ← Documentation
└── alembic/                     ← Database migrations
```

---

## Required API Keys

The following API keys should be added to `.env` for full functionality:

```bash
# Edit /root/ANNASEOv1/.env and update:
ANTHROPIC_API_KEY=sk-ant-api03-xxxx        # Claude API (blog writing)
GEMINI_API_KEY=AIzaSy-xxxx                 # Google Gemini (analysis, scoring)
GROQ_API_KEY=gsk_xxxx                      # Groq API (test generation)
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxx
```

**Note:** The application can run WITHOUT these keys using:
- **Ollama (DeepSeek)** for local code generation ✓ (Already installed)
- **Mock responses** for development/testing

---

## Quick Start

### Option 1: Manual Startup (Development)

#### Terminal 1 - Backend (FastAPI)
```bash
cd /root/ANNASEOv1
source venv/bin/activate

# Ensure Ollama is running
systemctl status ollama

# Start FastAPI server
uvicorn main:app --port 8000 --reload
```

Backend will be available at: **http://localhost:8000**  
API documentation: **http://localhost:8000/docs**

#### Terminal 2 - Frontend (React)
```bash
cd /root/ANNASEOv1/frontend
npm install
npm run dev
```

Frontend will be available at: **http://localhost:5173**

---

### Option 2: Tmux Session (Recommended for servers)

```bash
# Create new tmux session
tmux new-session -d -s annaseo -x 220 -y 50

# Window 0: Backend
tmux send-keys -t annaseo:0 'cd /root/ANNASEOv1 && source venv/bin/activate && uvicorn main:app --port 8000 --reload' Enter

# Window 1: Frontend
tmux send-keys -t annaseo:1 'cd /root/ANNASEOv1/frontend && npm run dev' Enter

# Window 2: Ollama
tmux send-keys -t annaseo:2 'systemctl start ollama && sleep 2 && systemctl status ollama' Enter

# View all windows
tmux list-windows -t annaseo

# Attach to session
tmux attach -t annaseo

# Detach from session
# Press: Ctrl+B then D
```

---

## Systemd Services (Production)

### Enable Auto-Start for Services

```bash
# Ollama service (already created during installation)
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl status ollama

# Check service status
systemctl list-units --type=service --state=active | grep ollama
```

### Create FastAPI Service (Optional)

```bash
sudo tee /etc/systemd/system/annaseo-backend.service > /dev/null <<EOF
[Unit]
Description=AnnaSEO FastAPI Backend
After=network.target ollama.service

[Service]
Type=notify
User=root
WorkingDirectory=/root/ANNASEOv1
Environment="PATH=/root/ANNASEOv1/venv/bin"
ExecStart=/root/ANNASEOv1/venv/bin/uvicorn main:app --port 8000 --host 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable annaseo-backend
sudo systemctl start annaseo-backend
sudo systemctl status annaseo-backend
```

---

## Available Ports

| Port | Service | URL |
|------|---------|-----|
| 8000 | FastAPI Backend | http://localhost:8000 |
| 8000 | Swagger UI | http://localhost:8000/docs |
| 5173 | React Frontend | http://localhost:5173 |
| 11434 | Ollama API | http://localhost:11434 |

---

## Health Checks

### Backend Health
```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{ "status": "ok" }
```

### Ollama Health
```bash
curl http://localhost:11434/api/tags
```

Expected response: List of available models including `deepseek-r1:7b`

---

## Database Management

### Access SQLite Database
```bash
cd /root/ANNASEOv1
source venv/bin/activate

# Interactive shell
sqlite3 annaseo.db

# Common commands
.tables          # List all tables
.schema users    # Show users table schema
SELECT count(*) FROM users;
.exit            # Exit shell
```

### Backup Database
```bash
cd /root/ANNASEOv1
cp annaseo.db annaseo.db.backup.$(date +%Y%m%d_%H%M%S)
```

---

## Environment Variables

Located in `/root/ANNASEOv1/.env`

### Critical Variables
```bash
# Security (auto-generated)
JWT_SECRET=2L4FZlEJi3zheVKrbZo6isjMsZypqjVfqwwjRS0r6tM
FERNET_KEY=13BKNNabCJln0-qAuIsb421Dkzg4s1z4HA0fNAd-LGM=

# Local AI
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-r1:7b

# Database
ANNASEO_DB=./annaseo.db

# Frontend
FRONTEND_URL=http://localhost:5173
```

---

## Troubleshooting

### Issue: "Address already in use"
```bash
# Kill process on port 8000
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Kill process on port 5173
lsof -i :5173 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

### Issue: Ollama not responding
```bash
# Restart Ollama service
sudo systemctl restart ollama

# Verify it's running
sudo systemctl status ollama

# Check logs
sudo journalctl -u ollama -n 50 -f
```

### Issue: Python module not found
```bash
cd /root/ANNASEOv1
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Or reinstall specific package
pip install --force-reinstall sqlalchemy
```

### Issue: Frontend build errors
```bash
cd /root/ANNASEOv1/frontend
rm -rf node_modules package-lock.json
npm install
npm run dev
```

### Issue: Database locked
```bash
# Kill any running processes using the database
lsof annaseo.db | awk 'NR>1 {print $2}' | xargs kill -9

# Restart backend
systemctl restart annaseo-backend  # if using systemd service
# or restart the FastAPI process manually
```

---

## Development Workflow

### 1. Install New Package
```bash
cd /root/ANNASEOv1
source venv/bin/activate
pip install package-name
pip freeze > requirements.txt
```

### 2. Run Tests
```bash
cd /root/ANNASEOv1
source venv/bin/activate
pytest tests/ -v
```

### 3. Access Application Logs
```bash
# Backend console output - visible in terminal where uvicorn was started

# Ollama logs
sudo journalctl -u ollama -n 100 -f

# System logs
journalctl -xe | tail -50
```

### 4. Update AI Models
```bash
# List available DeepSeek versions
ollama list

# Download larger model (requires more VRAM)
ollama pull deepseek-r1:14b

# Update .env to use new model
# OLLAMA_MODEL=deepseek-r1:14b
```

---

## Production Considerations

### Security
- [ ] Change JWT_SECRET to a unique value
- [ ] Set strong passwords for user accounts
- [ ] Use HTTPS with SSL certificates
- [ ] Restrict API access with rate limiting
- [ ] Add authentication to Ollama endpoint

### Performance
- [ ] Use PostgreSQL instead of SQLite for production
- [ ] Enable Redis caching layer
- [ ] Configure Nginx reverse proxy
- [ ] Use Gunicorn with multiple workers for FastAPI
- [ ] Set up database connection pooling

### Monitoring
- [ ] Set up error tracking (Sentry)
- [ ] Configure logging to file
- [ ] Monitor disk space and memory usage
- [ ] Set up uptime monitoring

---

## Useful Commands

```bash
# View Python venv activation
source ~/ANNASEOv1/venv/bin/activate

# Check virtual environment
which python
python --version

# List installed packages
pip list

# Check Ollama models
ollama list

# Download new model
ollama pull deepseek-coder:6.7b

# Monitor system resources
top -u root
htop

# Check open ports
netstat -tlnp
lsof -i -P -n

# View service logs
systemctl status annaseo-backend
journalctl -u annaseo-backend -n 50 -f

# Restart all services
systemctl restart ollama
# and restart backend process manually
```

---

## First Login

1. Open http://localhost:5173 in your browser
2. Click "Register" to create account
3. Create first project
4. Go to "Keyword Universe" tab
5. Enter seed keywords (e.g., "sustainable fashion", "eco-friendly products")
6. Click "Run Phase 1" to start keyword analysis

---

## Next Steps

1. **Add API Keys** to `.env` for full AI capabilities
2. **Configure Publishing** (WordPress/Shopify URLs and credentials)
3. **Connect GSC** (Google Search Console OAuth)
4. **Set Preferences** (Content thresholds, AI models, publishing rules)
5. **Start Creating Content** (Run Phase 1-20 pipeline)

---

## Support & Documentation

- **API Docs:** http://localhost:8000/docs
- **Project Docs:** See `/root/ANNASEOv1/docs/` directory
- **GitHub:** https://github.com/purelevenexim-ai/ANNASEOv1
- **Claude Documentation:** Run `claude` in project root for AI assistant

---

## System Information

```
OS: Ubuntu 24.04 LTS
Python: 3.12.3
Node: 18.19.1
Ollama: Latest
DeepSeek: r1:7b
Database: SQLite 3
Framework: FastAPI 0.115.0 + React 18
```

---

**Setup completed on:** March 23, 2026  
**Next action:** Add API keys to `.env` and start the application

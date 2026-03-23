# ANNASEOv1 Server Configuration - Quick Reference

## ✅ Setup Complete

All initialization tasks have been completed on your Linode server.

---

## 📊 Installation Summary

| Component | Status | Location | Version |
|-----------|--------|----------|---------|
| Python Environment | ✅ | `/root/ANNASEOv1/venv` | 3.12.3 |
| FastAPI Backend | ✅ | `/root/ANNASEOv1` | 0.115.0 |
| React Frontend | ✅ | `/root/ANNASEOv1/frontend` | 18 |
| Ollama + DeepSeek | ✅ | System service | 7B model |
| SQLite Database | ✅ | `./annaseo.db` | Initialized |
| Environment Config | ✅ | `./.env` | Configured |
| Startup Script | ✅ | `./start.sh` | Ready |

---

## 🚀 Quick Start

### First Time Setup (Choose Option A or B)

#### Option A: Using Start Script (Recommended)
```bash
cd /root/ANNASEOv1

# Terminal 1: Start backend
./start.sh backend

# Terminal 2: Start frontend
./start.sh frontend

# Terminal 3 (Optional): Check Ollama
./start.sh ollama
```

#### Option B: Manual Start
```bash
# Terminal 1
cd /root/ANNASEOv1
source venv/bin/activate
uvicorn main:app --port 8000 --reload

# Terminal 2
cd /root/ANNASEOv1/frontend
npm run dev
```

### Access Application
- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

---

## 📋 Next Steps

1. **Configure API Keys** (Optional for development)
   ```bash
   nano /root/ANNASEOv1/.env
   # Add: ANTHROPIC_API_KEY, GEMINI_API_KEY, GROQ_API_KEY
   ```

2. **Start Services**
   ```bash
   ./start.sh all
   ```

3. **Open in Browser**
   - Go to: http://localhost:5173
   - Register new account
   - Create first project

4. **Try Keyword Universe**
   - Enter seed keywords
   - Click "Run Phase 1"
   - Watch the magic happen!

---

## 📁 Important Files & Directories

```
/root/ANNASEOv1/
├── main.py              ← FastAPI application
├── .env                 ← Environment variables (UPDATE WITH YOUR KEYS)
├── annaseo.db          ← SQLite database
├── start.sh            ← Startup script
├── LINODE_SETUP.md     ← Full setup guide
├── QUICKSTART.md       ← This file
├── venv/               ← Python virtual environment
├── frontend/           ← React application
├── engines/            ← AI processing engines
└── docs/               ← Documentation
```

---

## 🔧 Common Commands

```bash
# Activate virtual environment
source /root/ANNASEOv1/venv/bin/activate

# Check services
systemctl status ollama
curl http://localhost:8000/api/health

# View logs
journalctl -u ollama -n 50 -f

# Kill process on port
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Backup database
cp annaseo.db annaseo.db.backup

# Download Ollama models
ollama pull deepseek-r1:14b
```

---

## 🌐 Ports Used

| Port | Service | URL |
|------|---------|-----|
| 8000 | FastAPI | http://localhost:8000 |
| 5173 | React | http://localhost:5173 |
| 11434 | Ollama | http://localhost:11434 |

---

## 🔐 Security Notes

- **JWT_SECRET**: Auto-generated and stored in `.env`
- **FERNET_KEY**: Auto-generated for encryption
- **Database**: Currently SQLite (use PostgreSQL for production)
- **API Authentication**: JWT tokens required

---

## 📖 Full Documentation

For complete information, see:
- **[LINODE_SETUP.md](./LINODE_SETUP.md)** - Complete setup guide
- **[CLAUDE.md](./CLAUDE.md)** - AI assistant instructions
- **[README.md](./README.md)** - Project overview
- **[docs/](./docs/)** - API, engines, and data models documentation

---

## 🆘 Support

### Common Issues

**"Port already in use"**
```bash
lsof -i :8000  # Find process
kill -9 <PID>  # Kill it
```

**"Ollama not responding"**
```bash
sudo systemctl restart ollama
sleep 2
curl http://localhost:11434/api/tags
```

**"Database locked"**
```bash
# Stop backend, remove WAL files, restart
rm annaseo.db-wal annaseo.db-shm
```

---

## 🎯 System Resources

```
OS: Ubuntu 24.04 LTS
CPU: Variable (Linode plan dependent)
Memory: Variable (Linode plan dependent)
Storage: Variable (Linode plan dependent)

Current Installation:
- Python + packages: ~3GB
- Node modules: ~500MB
- DeepSeek model: ~4.7GB
- Database: <1MB (grows as used)
```

---

## 📞 Project Info

- **GitHub**: https://github.com/purelevenexim-ai/ANNASEOv1
- **Stack**: FastAPI + React 18 + SQLite + Ollama
- **AI Models**: Claude (remote), DeepSeek (local), Gemini (optional), Groq (optional)
- **License**: Check repository
- **Setup Date**: March 23, 2026

---

**🎉 Your ANNASEOv1 server is ready!**

Run: `./start.sh backend` in one terminal and `./start.sh frontend` in another to get started.

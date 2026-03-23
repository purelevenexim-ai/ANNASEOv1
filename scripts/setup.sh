#!/bin/bash
# AnnaSEO — One-command setup
# Usage: bash scripts/setup.sh

set -e

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║       AnnaSEO Setup Script           ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# 1. Python deps
echo "  [1/6] Installing Python dependencies..."
pip install -r requirements.txt -q
python -m spacy download en_core_web_sm -q
echo "  ✓ Python deps installed"

# 2. Ollama + DeepSeek
echo "  [2/6] Checking Ollama..."
if ! command -v ollama &> /dev/null; then
  echo "  Installing Ollama..."
  curl -fsSL https://ollama.ai/install.sh | sh
fi
echo "  Pulling deepseek-r1:7b (this takes a few minutes first time)..."
ollama pull deepseek-r1:7b
echo "  ✓ Ollama ready"

# 3. Environment
echo "  [3/6] Setting up environment..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  ⚠  .env created from .env.example — fill in your API keys"
else
  echo "  ✓ .env already exists"
fi

# 4. Database
echo "  [4/6] Running database migrations..."
python annaseo_wiring.py write-migrations .
alembic upgrade head
echo "  ✓ Database ready"

# 5. Frontend
echo "  [5/6] Installing frontend dependencies..."
cd frontend && npm install -q && cd ..
echo "  ✓ Frontend ready"

# 6. Health check
echo "  [6/6] Starting server for health check..."
uvicorn main:app --port 8000 &
SERVER_PID=$!
sleep 3
HEALTH=$(curl -s http://localhost:8000/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('database') else 'FAIL')" 2>/dev/null || echo "FAIL")
kill $SERVER_PID 2>/dev/null

echo ""
if [ "$HEALTH" = "OK" ]; then
  echo "  ╔══════════════════════════════════════╗"
  echo "  ║  ✓ Setup complete!                   ║"
  echo "  ║                                      ║"
  echo "  ║  Start backend:                      ║"
  echo "  ║    uvicorn main:app --port 8000      ║"
  echo "  ║                                      ║"
  echo "  ║  Start frontend:                     ║"
  echo "  ║    cd frontend && npm run dev        ║"
  echo "  ║                                      ║"
  echo "  ║  Open: http://localhost:5173         ║"
  echo "  ╚══════════════════════════════════════╝"
else
  echo "  ⚠  Server check failed — fill in API keys in .env then try again"
fi
echo ""

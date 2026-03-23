#!/bin/bash
# Start all AnnaSEO services
# Usage: bash scripts/start.sh

echo "Starting AnnaSEO..."

# Backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
echo "  ✓ Backend → http://localhost:8000"
echo "  ✓ API docs → http://localhost:8000/docs"

# Frontend
cd frontend && npm run dev &
echo "  ✓ Frontend → http://localhost:5173"

echo ""
echo "  All services started. Press Ctrl+C to stop all."
wait

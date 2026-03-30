#!/bin/bash

# Quick Test Runner for Gate 2 Integration
# Run this from /root/ANNASEOv1 directory

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        Gate 2 Integration - Quick Test Runner                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if backend is running
if ! curl -s http://localhost:8000/api/system-status > /dev/null 2>&1; then
    echo "⚠️  Backend not running. Start it first:"
    echo "   Terminal 1: cd /root/ANNASEOv1 && python3 main.py"
    echo ""
fi

# Check if frontend is running
if ! curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "⚠️  Frontend not running. Start it first:"
    echo "   Terminal 2: cd /root/ANNASEOv1/frontend && npm run dev"
    echo ""
fi

echo "🧪 GATE 2 E2E TESTS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Test Scenarios:"
echo "1. Basic Gate 2 Flow (30 min)        - Modal appearance, CRUD ops"
echo "2. Cancel & Resume (20 min)         - Pause & retry pipeline"
echo "3. SSE Streaming (15 min)           - Real-time console output"
echo "4. Database Persistence (10 min)    - Data survives restart"
echo "5. Error Handling (10 min)          - Network/validation errors"
echo "6. Load Testing (5 min)             - Large data volume"
echo ""
echo "Total: ~90 minutes"
echo ""
echo "📋 TEST CHECKLIST"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Backend checks
echo "✓ Backend Validation"
python3 -m py_compile main.py 2>/dev/null && echo "  ✅ main.py syntax valid" || echo "  ❌ main.py syntax error"
python3 -m py_compile engines/ruflo_20phase_wired.py 2>/dev/null && echo "  ✅ engine syntax valid" || echo "  ❌ engine syntax error"

# Database checks
echo ""
echo "✓ Database Validation"
if [ -f annaseo.db ]; then
    # Check if gate_states table exists
    result=$(sqlite3 annaseo.db "SELECT name FROM sqlite_master WHERE type='table' AND name='gate_states';" 2>/dev/null)
    if [ ! -z "$result" ]; then
        echo "  ✅ gate_states table exists"
        count=$(sqlite3 annaseo.db "SELECT COUNT(*) FROM gate_states;" 2>/dev/null)
        echo "     └─ Confirmations: $count"
    else
        echo "  ⚠️  gate_states table not found (migrations may need running)"
    fi
else
    echo "  ⚠️  annaseo.db not found (will be created on first backend run)"
fi

# Frontend checks
echo ""
echo "✓ Frontend Validation"
if [ -f frontend/src/components/PillarConfirmation.jsx ]; then
    echo "  ✅ PillarConfirmation.jsx exists"
    wc_lines=$(wc -l < frontend/src/components/PillarConfirmation.jsx)
    echo "     └─ Lines: $wc_lines"
else
    echo "  ❌ PillarConfirmation.jsx missing"
fi

if grep -q "import PillarConfirmation" frontend/src/KeywordWorkflow.jsx 2>/dev/null; then
    echo "  ✅ PillarConfirmation imported in KeywordWorkflow"
else
    echo "  ❌ PillarConfirmation not imported"
fi

# Endpoint checks
echo ""
echo "✓ API Endpoints"
if ! curl -s http://localhost:8000/api/system-status > /dev/null 2>&1; then
    echo "  ⚠️  Backend not running (skipping endpoint checks)"
else
    # Check gate endpoints
    response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/system-status)
    if [ "$response" = "200" ]; then
        echo "  ✅ GET /api/system-status"
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📖 NEXT STEPS"
echo ""
echo "1. Open TEST_GATE2_E2E.md for detailed test procedures"
echo "2. Start backend (if not running):"
echo "   Terminal 1: cd /root/ANNASEOv1 && python3 main.py"
echo "3. Start frontend (if not running):"
echo "   Terminal 2: cd /root/ANNASEOv1/frontend && npm run dev"
echo "4. Open browser: http://localhost:5173"
echo "5. Follow test scenarios in order"
echo "6. Check off items as they pass"
echo ""
echo "🎯 Critical Path: Test scenarios 1, 2, 3 are blocking for remaining gates"
echo ""

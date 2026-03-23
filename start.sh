#!/bin/bash

# ANNASEOv1 Startup Script
# Description: Start backend, frontend, and Ollama services
# Usage: ./start.sh [backend|frontend|all]

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
BACKEND_PORT=8000
FRONTEND_PORT=5173
OLLAMA_PORT=11434

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}✗ Virtual environment not found at $VENV_DIR${NC}"
    echo "Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Function to check if port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to start backend
start_backend() {
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}Starting FastAPI Backend (port $BACKEND_PORT)${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    
    if check_port $BACKEND_PORT; then
        echo -e "${YELLOW}⚠ Port $BACKEND_PORT already in use${NC}"
        echo "Kill process: lsof -i :$BACKEND_PORT | grep LISTEN | awk '{print \$2}' | xargs kill -9"
        return 1
    fi
    
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
    echo -e "${GREEN}✓ Starting uvicorn server...${NC}"
    echo ""
    echo "Backend URL: http://localhost:$BACKEND_PORT"
    echo "API Docs:    http://localhost:$BACKEND_PORT/docs"
    echo ""
    
    uvicorn main:app --port $BACKEND_PORT --reload --host 0.0.0.0
}

# Function to start frontend
start_frontend() {
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}Starting React Frontend (port $FRONTEND_PORT)${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    
    if check_port $FRONTEND_PORT; then
        echo -e "${YELLOW}⚠ Port $FRONTEND_PORT already in use${NC}"
        echo "Kill process: lsof -i :$FRONTEND_PORT | grep LISTEN | awk '{print \$2}' | xargs kill -9"
        return 1
    fi
    
    cd "$PROJECT_DIR/frontend"
    
    echo -e "${GREEN}✓ Checking dependencies...${NC}"
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}Installing npm packages...${NC}"
        npm install
    fi
    
    echo -e "${GREEN}✓ Starting Vite dev server...${NC}"
    echo ""
    echo "Frontend URL: http://localhost:$FRONTEND_PORT"
    echo ""
    
    npm run dev
}

# Function to check Ollama
check_ollama() {
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}Checking Ollama Service${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    
    if systemctl is-active --quiet ollama; then
        echo -e "${GREEN}✓ Ollama is running${NC}"
        
        # Check if model is available
        if curl -s http://localhost:$OLLAMA_PORT/api/tags | grep -q "deepseek-r1"; then
            echo -e "${GREEN}✓ DeepSeek-R1 model is available${NC}"
        else
            echo -e "${YELLOW}⚠ DeepSeek-R1 model not found, downloading...${NC}"
            ollama pull deepseek-r1:7b
        fi
    else
        echo -e "${YELLOW}⚠ Ollama is not running${NC}"
        echo -e "${YELLOW}Starting Ollama service...${NC}"
        sudo systemctl start ollama
        sleep 3
        
        if systemctl is-active --quiet ollama; then
            echo -e "${GREEN}✓ Ollama started successfully${NC}"
        else
            echo -e "${RED}✗ Failed to start Ollama${NC}"
            return 1
        fi
    fi
}

# Function to show usage
show_usage() {
    cat <<EOF
ANNASEOv1 Startup Script

Usage: ./start.sh [COMMAND]

Commands:
    backend     Start FastAPI backend only
    frontend    Start React frontend only
    ollama      Check and start Ollama service
    all         Start backend, frontend, and verify Ollama
    help        Show this help message

Examples:
    ./start.sh backend       # Terminal 1: Start backend
    ./start.sh frontend      # Terminal 2: Start frontend
    ./start.sh ollama        # Check Ollama status
    ./start.sh all           # Start everything (runs backend in foreground)

Quick Start (3 terminals):
    Terminal 1: ./start.sh ollama
    Terminal 2: ./start.sh backend
    Terminal 3: ./start.sh frontend

Then open: http://localhost:5173

Environment:
    Backend:  http://localhost:8000
    Frontend: http://localhost:5173
    Ollama:   http://localhost:11434

    API Docs: http://localhost:8000/docs
    ReDoc:    http://localhost:8000/redoc

EOF
}

# Main logic
case "${1:-all}" in
    backend)
        check_ollama
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    ollama)
        check_ollama
        ;;
    all)
        check_ollama
        echo ""
        echo -e "${YELLOW}Note: Running backend in foreground${NC}"
        echo -e "${YELLOW}Open another terminal to start frontend: ./start.sh frontend${NC}"
        echo ""
        start_backend
        ;;
    help|-h|--help)
        show_usage
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_usage
        exit 1
        ;;
esac

#!/usr/bin/env bash
#
# Consularis – setup and run frontend + backend
#
# What this does:
#   1. Installs Node dependencies (frontend)
#   2. Creates root .venv and installs from requirements.txt (root)
#   3. Starts the backend from backend/ on http://localhost:8000
#   4. Starts the frontend on http://localhost:5173
#
# To stop: press Ctrl+C in this terminal. That stops the frontend and the script
# will also kill the backend. If you started servers by hand, use ./stop.sh
#
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

echo "Consularis – setup & run"
echo "======================="

# --- Check tools ---
if ! command -v node &>/dev/null; then
  echo "Error: Node.js is not installed. Install it from https://nodejs.org/"
  exit 1
fi
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is not installed. Install Python 3.10+."
  exit 1
fi

echo ""
echo "1/4 Installing frontend dependencies..."
cd "$REPO_ROOT/frontend"
npm install
cd "$REPO_ROOT"

echo ""
echo "2/4 Setting up backend (Python venv + deps)..."
cd "$REPO_ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt --index-url https://pypi.org/simple
cd "$REPO_ROOT"

# --- Run backend in background ---
echo ""
echo "3/4 Starting backend on http://localhost:8000 ..."
cd "$REPO_ROOT/backend"
source "$REPO_ROOT/.venv/bin/activate"
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd "$REPO_ROOT"

# Kill backend when this script exits (e.g. Ctrl+C)
cleanup() {
  echo ""
  echo "Stopping backend (PID $BACKEND_PID)..."
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 0
}
trap cleanup EXIT INT TERM

# Give backend a moment to bind
sleep 2

echo ""
echo "4/4 Starting frontend on http://localhost:5173 ..."
echo ""
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo "  Stop:      Ctrl+C in this terminal"
echo ""

cd "$REPO_ROOT/frontend"
npm run dev

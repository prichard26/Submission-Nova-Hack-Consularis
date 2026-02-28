# Consularis – Nova Hack MVP

Process intelligence: domain selection, interview flow, and operational mapping (Amazon Nova AI Hackathon).

## Quick start

**Requirements:** Node.js (LTS), Python 3.10+

```bash
./run.sh
```

This will:

1. Install frontend dependencies (`frontend/node_modules`)
2. Create a Python venv and install backend deps (`backend/.venv`)
3. Start the **backend** at **http://localhost:8000**
4. Start the **frontend** at **http://localhost:5173**

Open **http://localhost:5173** in your browser.

### Stop the app

- **If you started with `./run.sh`:** press **Ctrl+C** in that terminal. The script will stop the frontend and kill the backend.
- **If you started servers manually** (e.g. `npm run dev` in one terminal, `uvicorn` in another), either press Ctrl+C in each terminal, or run:

```bash
./stop.sh
```

That kills any process listening on port **5173** (frontend) and **8000** (backend).

## Where things run

| Service   | URL                  | Started by                          |
|----------|----------------------|-------------------------------------|
| Frontend | http://localhost:5173 | `npm run dev` (Vite) in `frontend/` |
| Backend  | http://localhost:8000 | `uvicorn main:app` in `backend/`    |

The frontend talks to the backend for the domain-selection API (`POST /api/select-domain`).

## Manual setup (optional)

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend (another terminal)
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
```

## Repo layout

- `frontend/` – React + Vite app (Aurelius robot, domain form)
- `backend/` – FastAPI (domain selection endpoint)
- `databases/` – APQC Excel data
- `run.sh` – one-shot setup and run
- `stop.sh` – stop dev servers on 5173 and 8000

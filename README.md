# Consularis – Nova Hack MVP

Process intelligence: domain selection, interview flow, and operational mapping (Amazon Nova AI Hackathon).

## Quick start

**Requirements:** Node.js (LTS), Python 3.10+

**Groq API key (for Aurelius chat):** Get a key at [console.groq.com](https://console.groq.com). Then put it in **`backend/.env`**:

```bash
cp backend/env.example backend/.env
# Edit backend/.env and set (no spaces): GROQ_KEY=gsk_your_actual_key
```

Then:

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

## How the agent works

1. **Session:** Each company name is a `session_id`. The backend keeps one process graph per session (phases + steps + flow_connections).
2. **Chat:** When you send a message, the backend calls Groq (Llama 3.3 70B) with a system prompt (Aurelius personality + “if unclear, ask to repeat”) and **tools**: `get_graph`, `get_node`, `update_node`, `add_node`, `delete_node`, `get_edges`, `update_edge`, `add_edge`, `validate_graph`.
3. **Tool loop:** If the model returns tool calls (e.g. “update P1.2 duration to 10 min”), the backend runs the tool on the session graph, appends the result to the conversation, and calls the model again. This repeats until the model replies with plain text and no tool calls.
4. **Validation:** Every tool call is validated (node/edge exists, IDs from the graph only). Invalid calls return an error to the model so it can say “Please repeat” or correct.
5. **Live graph:** The API returns `{ message, graph }`. The frontend updates the diagram from `graph` so edits appear immediately.

## Repo layout

- `frontend/` – React + Vite app (Aurelius robot, interactive graph, chat)
- `backend/` – FastAPI (graph store, Groq agent with tools, `/api/chat`, `/api/graph`)
- `databases/` – APQC Excel data
- `datasets/pharmacy/` – pharmacy circuit JSON (source for default graph)
- `run.sh` – one-shot setup and run
- `stop.sh` – stop dev servers on 5173, 5174, 8000

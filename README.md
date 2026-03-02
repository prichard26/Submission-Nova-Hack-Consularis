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

| Service  | URL                  | Started by                          |
|----------|----------------------|-------------------------------------|
| Frontend | http://localhost:5173 | `npm run dev` (Vite) in `frontend/` |
| Backend  | http://localhost:8000 | `uvicorn main:app` in `backend/`    |

The frontend uses these backend APIs:

- **GET /api/graph/baseline?process_id=…** — baseline BPMN XML (no session needed, default `Process_Global`)
- **GET /api/graph/export?session_id=…&process_id=…** — session graph as BPMN XML
- **GET /api/graph/resolve?session_id=…&name=…** — fuzzy name-to-ID resolution
- **POST /api/chat** — send message; returns assistant reply, updated `bpmn_xml`, and meta

## Manual setup (optional)

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend (another terminal)
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
```

## Run tests

```bash
cd backend && source .venv/bin/activate && pytest -v
```

## How the agent works

1. **Session:** Each company name is a `session_id`. The backend keeps a set of BPMN 2.0 process graphs per session (hierarchical: global map + subprocesses), backed by in-memory SQLite.
2. **Chat:** When you send a message, the backend calls Groq (Llama 3.3 70B) with a system prompt (Aurelius personality + "if unclear, ask to repeat") and **tools**: `get_graph`, `get_node`, `update_node`, `add_node`, `delete_node`, `get_edges`, `update_edge`, `add_edge`, `validate_graph`, plus hierarchy tools (`resolve_step`, `list_processes`, `navigate_process`).
3. **Tool loop:** If the model returns tool calls (e.g. "update P1.2 duration to 10 min"), the backend runs the tool on the session graph, appends the result to the conversation, and calls the model again. This repeats until the model replies with plain text and no tool calls.
4. **Validation:** Every tool call is validated (node/edge exists, IDs from the graph only). Invalid calls return an error to the model so it can self-correct.
5. **Live graph:** The API returns `{ message, bpmn_xml, meta }`. The frontend updates the BPMN diagram from `bpmn_xml` so edits appear immediately.

## Architecture

The system uses a **hierarchical process tree** stored in **BPMN 2.0 XML** and backed by **in-memory SQLite**:

- A **process registry** (`registry.json`) defines the tree structure.
- Each process is a separate BPMN file (`global.bpmn`, `P1.bpmn`–`P7.bpmn`).
- Parent processes link to children via **call activities**.
- Tasks carry 19 metadata fields (actor, duration, risks, operational data like frequency, costs, SLA targets).
- Sessions get a deep copy of the baseline; each session evolves independently.

## Project structure

```
├── backend/                  FastAPI app
│   ├── main.py               App entry, lifespan, CORS, routers
│   ├── config.py             Env and constants
│   ├── db.py                 In-memory SQLite (baseline, sessions, chat)
│   ├── routers/              HTTP endpoints (health, chat, graph)
│   ├── agent/                Aurelius: runtime, tools, prompt
│   ├── bpmn/                 BPMN domain: model, parser, serializer, layout, store
│   ├── services/             Chat orchestration
│   ├── data/
│   │   └── graphs/           Baseline BPMN hierarchy
│   │       ├── registry.json
│   │       ├── global.bpmn
│   │       └── P1-P7.bpmn
│   └── tests/
├── frontend/                 React + Vite app
│   └── src/
│       ├── components/       BpmnViewer, AureliusChat, Robot, etc.
│       ├── hooks/            useBpmnXml
│       ├── pages/            Landing, Dashboard
│       └── services/         API client
├── docs/                     Architecture and reference docs
├── run.sh                    One-shot setup and run
└── stop.sh                   Stop dev servers
```

Documentation: [docs/README.md](docs/README.md) (index). Data flow and state: [docs/DATA_FLOW.md](docs/DATA_FLOW.md). Graph structure: [docs/GRAPH_STRUCTURE.md](docs/GRAPH_STRUCTURE.md).

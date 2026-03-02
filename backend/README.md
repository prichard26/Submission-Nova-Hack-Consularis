# Consularis Backend

FastAPI API for the Consularis app: Aurelius chat (Groq + tools), hierarchical BPMN process store, and in-memory SQLite persistence.

## Run

```bash
cd backend
cp env.example .env
# Edit .env and set GROQ_KEY (get one at https://console.groq.com)

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`

To run tests, install dev dependencies: `pip install -r requirements-dev.txt`, then `pytest` from the `backend` directory.

## Structure

```
backend/
├── main.py              # FastAPI app, lifespan (init DB + seed baseline), CORS, routers
├── config.py            # Env and constants (GROQ_KEY, paths, CORS, limits)
├── db.py                # In-memory SQLite: baseline_processes, session_processes, chat_messages
├── requirements.txt
├── env.example          # Template for .env
│
├── routers/             # HTTP routes by feature
│   ├── health.py        # GET /health
│   ├── chat.py          # OPTIONS + POST /api/chat
│   └── graph.py         # GET /api/graph/baseline, /export, /resolve
│
├── agent/               # Aurelius chat + tools
│   ├── runtime.py       # run_chat loop (Groq, tool rounds, timeout/retries)
│   ├── tools.py         # Tool schemas + registry, run_tool dispatch
│   └── prompt.py        # SYSTEM_PROMPT
│
├── bpmn/                # BPMN 2.0 domain
│   ├── model.py         # BpmnModel, lanes, tasks, flows, 19 extension keys
│   ├── parser.py        # parse_bpmn_xml (file or string)
│   ├── serializer.py    # serialize_bpmn_xml (with diagram interchange for bpmn-js)
│   ├── layout.py        # Layout constants and layout_bounds() for diagram
│   └── store.py         # Session-scoped BPMN store with SQLite backing + in-memory cache
│
├── data/                # Runtime data
│   └── graphs/          # Baseline BPMN hierarchy (read-only at runtime)
│       ├── registry.json    # Process tree: ids, names, parent-child, ownership
│       ├── global.bpmn      # Root process with call activities to P1-P7
│       ├── P1.bpmn          # Prescription
│       ├── P2.bpmn          # Selection, Acquisition, and Reception
│       ├── P3.bpmn          # Storage and Storage Management
│       ├── P4.bpmn          # Distribution
│       ├── P5.bpmn          # Dispensing and Preparation
│       ├── P6.bpmn          # Administration
│       └── P7.bpmn          # Monitoring and Waste Management
│
└── tests/
    ├── conftest.py          # reset_db fixture (init SQLite, seed baseline, cleanup)
    ├── test_chat_flow.py
    ├── test_graph_idempotency.py
    ├── test_hierarchy.py
    └── test_bpmn_roundtrip.py
```

### What each module does

**main.py** — App entry point. The `lifespan` initializes the SQLite database (`db.get_conn()`), seeds the baseline from `registry.json` + BPMN files (`bpmn.store.init_baseline()`), and logs Groq key status.

**config.py** — All env vars and constants. Key settings: `GROQ_KEY`, `BASELINE_GRAPHS_DIR`, `DEFAULT_PROCESS_ID`, `MAX_TOOL_ROUNDS`, `GROQ_TIMEOUT`, `ALLOWED_CORS_ORIGINS`, `SESSION_ID_MAX_LEN`.

**db.py** — Singleton in-memory SQLite connection (`:memory:`). Three tables: `baseline_processes` (seeded from files), `session_processes` (per-session graph copies), `chat_messages`. All persistence reads/writes go through this module. Data is ephemeral — lost on restart.

**routers/** — HTTP endpoints. Health check, chat (with per-session locking), and graph (baseline XML, session export, name resolution).

**agent/** — The Aurelius assistant. Runtime runs the Groq chat loop with tools (timeout and retries). Tools define what the LLM can do on the graph (get/update/add/delete nodes and edges, validate, resolve names, navigate processes). Prompt holds the system instructions.

**bpmn/** — Process graph domain. Model defines the in-memory `BpmnModel` with 19 extension metadata fields. Parser reads BPMN XML into models. Serializer writes models back to XML with diagram interchange. Layout computes positions. Store provides session-scoped CRUD with an LRU cache of parsed models backed by SQLite.

**data/graphs/** — Baseline BPMN hierarchy loaded at startup. The registry defines the process tree; each `.bpmn` file is a self-contained subprocess with start/end events, tasks, gateways, and sequence flows.

**tests/** — Pytest tests. The `reset_db` fixture in conftest initializes a fresh SQLite database and seeds the baseline before each test, then cleans up tables and cache after.

## Architecture (how it fits together)

When a request hits the API, **FastAPI** (in `main.py`) sends it to the right **router**. The router then uses **config**, **db**, **bpmn.store**, or **agent** as needed. In short: **routers** = HTTP entrypoints; **config** = settings; **db** = persistence; **bpmn.store** = BPMN + session layer that uses db and exposes a clean API to the rest of the app.

### config

**Role:** Single place for environment variables and constants (no magic values; paths and limits live here).

- **API:** `GROQ_KEY` (for the Aurelius chat LLM).
- **Paths:** `BASELINE_GRAPHS_DIR`, `BASELINE_GRAPH_REGISTRY_PATH` (where BPMN files and `registry.json` live).
- **Defaults:** `DEFAULT_PROCESS_ID` (e.g. `"Process_Global"`), `MAX_TOOL_ROUNDS`, `GROQ_TIMEOUT`, `GROQ_MAX_RETRIES`.
- **CORS:** `ALLOWED_CORS_ORIGINS` (which frontend origins are allowed).
- **Validation:** `SESSION_ID_MAX_LEN` (max length for `session_id`).

Loads `.env` from the backend directory.

### db

**Role:** The only code that talks to the database. In-memory SQLite — all data is lost when the process stops.

- **Single connection** to `:memory:` SQLite, created on first use.
- **Tables:** `baseline_processes` (read-only copy of the BPMN hierarchy from `data/graphs/`), `session_processes` (per-session BPMN XML), `chat_messages` (chat history per session).
- **Functions** do the raw SQL: `get_conn()`, `seed_baseline()`, `get_baseline_xml()`, `get_session_xml()`, `upsert_session_xml()`, `clone_baseline_to_session()`, `append_chat_message()`, `get_chat_history()`, etc.

So **db** = storage layer: it does not know about BPMN structure or sessions; it just stores and retrieves XML and chat rows.

### Routers

**Role:** Routers are FastAPI “sub-apps” that define **which URL path runs which logic**. `main.py` mounts them so that `/health`, `/api/chat`, and `/api/graph/*` are handled by the right code.

| Router  | Prefix       | Purpose |
|---------|--------------|---------|
| **health** | (none)     | `GET /health` → `{"status": "ok"}` (liveness). |
| **chat**   | `/api`     | `POST /api/chat` → receive user message, call agent (`run_chat`), save to db, return assistant message + optional BPMN XML. Uses **db** (chat history) and **bpmn.store** (via agent tools). |
| **graph**  | `/api/graph` | `GET /api/graph/baseline` (baseline BPMN XML), `GET /api/graph/export` (session BPMN XML), `GET /api/graph/resolve` (resolve step name → IDs). All use **bpmn.store** (and config for defaults). |

So **routers** = the “front” of the API: they map URLs to handlers and call **config**, **db**, **bpmn.store**, and **agent** as needed.

### bpmn.store

**Role:** Session-scoped BPMN “service” in front of the database. It gives the rest of the app a simple API: “for this session and process, get or update the graph,” without dealing with XML or SQL.

- **Uses db** to read/write baseline and per-session BPMN XML and to clone baseline → session when needed.
- **Uses config** for `BASELINE_GRAPH_REGISTRY_PATH`, `BASELINE_GRAPHS_DIR`, `DEFAULT_PROCESS_ID`.
- **Adds:** parsing (XML ↔ in-memory `BpmnModel` via `bpmn.parser` and `bpmn.serializer`), an in-memory cache `(session_id, process_id) → BpmnModel` to avoid re-parsing on every request, and logic like “get graph for session,” “update a node,” “add edge,” “resolve step name to IDs.”

Typical flow: first request for a session → no session rows in db → clone baseline into `session_processes`, load XML, parse to `BpmnModel`, cache it. Later requests often hit the cache; when the agent (or anything) mutates the model, the store serializes back to XML and writes via **db** (`upsert_session_xml`), then updates the cache.

So **bpmn.store** = BPMN + session + cache: it sits between **routers/agent** and **db** and hides XML and DB details behind a single “get/update graph for (session, process)” API.

### Summary

- **config** → settings and paths (used by main, db seeding, bpmn.store, routers).
- **db** → only place that touches SQLite (baseline + session BPMN XML, chat messages).
- **bpmn.store** → uses **db** + **config** + parser/serializer; provides “get/change BPMN per session/process” and caching.
- **Routers** → define URLs and call **config**, **db**, **bpmn.store**, and **agent**; they are the “front” of the API.

## Conventions

### Error and "not found"

- **BPMN store** (`bpmn/store.py`): Returns `None` or `False` when an entity is not found. Callers check these values.
- **Agent tools** (`agent/tools.py`): Convert store results to JSON for the LLM: success as entity or `{"deleted": true}`; "not found"/errors as `{"error": "..."}`.

### Configuration

See `env.example` for all variables. Copy to `.env` and set at least `GROQ_KEY` for chat.

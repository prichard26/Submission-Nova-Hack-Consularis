# Consularis Backend

FastAPI API for the Consularis app: Aurelius chat (Groq + tools), hierarchical JSON-native process store, and in-memory SQLite persistence.

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
├── db.py                # In-memory SQLite: baseline_processes, session_processes, workspace, chat_messages, history
├── requirements.txt
├── env.example          # Template for .env
│
├── routers/             # HTTP routes by feature
│   ├── health.py        # GET /health
│   ├── chat.py          # POST /api/chat
│   └── graph.py         # JSON graph, workspace, BPMN export, name resolution, node CRUD, positions, undo
│
├── agent/               # Aurelius chat + tools
│   ├── runtime.py       # run_chat loop (Groq, tool rounds, timeout/retries)
│   ├── tools.py         # Tool schemas + registry (all 19 metadata fields), run_tool dispatch
│   └── prompt.py        # SYSTEM_PROMPT
│
├── graph/               # JSON-native process graph domain
│   ├── model.py         # ProcessGraph: flat JSON wrapper, STEP_METADATA_KEYS, lookups
│   ├── workspace.py     # WorkspaceManifest: process tree index, summaries
│   ├── store.py         # Session-scoped graph store with SQLite backing + in-memory cache (~25 public methods)
│   ├── layout.py        # Auto-positioning for new nodes
│   └── bpmn_export.py   # JSON → BPMN 2.0 XML export (model only)
│
│
├── data/                # Runtime data
│   ├── workspace.json       # Workspace manifest (process tree, summaries, tags)
│   └── graphs/              # Baseline process hierarchy
│       ├── global.json      # Root process (7 subprocesses)
│       ├── P1.json           # Prescription
│       ├── P2.json           # Selection, Acquisition, and Reception
│       ├── P3.json           # Storage and Storage Management
│       ├── P4.json           # Distribution
│       ├── P5.json           # Dispensing and Preparation
│       ├── P6.json           # Administration
│       └── P7.json           # Monitoring and Waste Management
│
└── tests/
    ├── conftest.py          # reset_db fixture (init SQLite, seed baseline, cleanup caches)
    ├── test_chat_flow.py    # Chat returns graph_json and meta
    ├── test_graph_idempotency.py  # Risk dedup, edge idempotency
    ├── test_hierarchy.py    # Process-scoped APIs, workspace, name resolution
    └── test_json_roundtrip.py     # JSON load, ProcessGraph, BPMN export
```

### What each module does

**main.py** — App entry point. The `lifespan` initializes the SQLite database (`db.get_conn()`), seeds the baseline from `workspace.json` + JSON graph files (`graph.store.init_baseline()`), and logs Groq key status.

**config.py** — All env vars and constants. Key settings: `GROQ_KEY`, `BASELINE_GRAPHS_DIR`, `BASELINE_WORKSPACE_PATH`, `DEFAULT_PROCESS_ID`, `MAX_TOOL_ROUNDS`, `GROQ_TIMEOUT`, `ALLOWED_CORS_ORIGINS`, `SESSION_ID_MAX_LEN`.

**db.py** — Singleton in-memory SQLite connection (`:memory:`). Tables: `baseline_processes` (seeded from JSON files), `baseline_workspace`, `session_processes` (per-session graph JSON), `session_workspace`, `session_process_history` (undo support), `chat_messages`. All persistence reads/writes go through this module. Data is ephemeral — lost on restart.

**routers/** — HTTP endpoints. Health check, chat (with per-session locking), and graph (JSON graph, workspace, BPMN export, node CRUD, positions, undo, name resolution).

**agent/** — The Aurelius assistant. Runtime runs the Groq chat loop with tools. Tools define what the LLM can do: all 19 metadata fields are available in update_node. Prompt includes guidance on operational data fields.

**graph/** — JSON-native process graph domain. Model wraps a raw dict (no parsing needed). Workspace manages the process tree index. Store provides session-scoped CRUD with an LRU cache backed by SQLite. Layout positions new nodes. BPMN export converts JSON graphs to BPMN 2.0 XML for download compatibility.

**data/** — Baseline process hierarchy loaded at startup. The workspace manifest defines the process tree; each `.json` file is a self-contained subprocess.

**tests/** — Pytest tests. The `reset_db` fixture in conftest initializes a fresh SQLite database and seeds the baseline before each test, then cleans up tables and caches after.

## Architecture

When a request hits the API, **FastAPI** (in `main.py`) sends it to the right **router**. The router then uses **config**, **db**, **graph.store**, or **agent** as needed.

### graph.store

**Role:** Session-scoped JSON "service" in front of the database. It gives the rest of the app a simple API: "for this session and process, get or update the graph," without dealing with SQL.

- **Uses db** to read/write baseline and per-session graph JSON and to clone baseline → session when needed.
- **Uses config** for `BASELINE_WORKSPACE_PATH`, `BASELINE_GRAPHS_DIR`, `DEFAULT_PROCESS_ID`.
- **Adds:** an in-memory cache `(session_id, process_id) → ProcessGraph` to avoid re-parsing, and all mutation/query logic (update node, add edge, resolve step name, etc.).

Mutations are direct dict operations on the `ProcessGraph.data` dict — no XML parse/serialize cycle. This is the key simplification over the legacy BPMN store.

## Conventions

### Error and "not found"

- **Graph store** (`graph/store.py`): Returns `None` or `False` when an entity is not found.
- **Agent tools** (`agent/tools.py`): Convert store results to JSON for the LLM: success as entity or `{"deleted": true}`; "not found"/errors as `{"error": "..."}`.

### Configuration

See `env.example` for all variables. Copy to `.env` and set at least `GROQ_KEY` for chat.

# Consularis Backend

FastAPI API for the Consularis app: Aurelius chat (Amazon Nova + tools), hierarchical JSON-native process store, and in-memory SQLite persistence.

## Run

```bash
cd backend
cp env.example .env
# Edit .env and set AWS credentials for Bedrock (Nova); see env.example

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
├── config.py            # Env and constants (AWS/Bedrock, paths, CORS, limits)
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
│   ├── runtime_nova.py   # run_chat loop (Nova/Bedrock, tool rounds, timeout/retries)
│   ├── tools.py         # Tool schemas + registry (all 19 metadata fields), run_tool dispatch
│   └── prompt.py        # MULTIAGENT_CONTEXT, PLANNER, EXECUTOR prompts
│
├── graph/               # JSON-native process graph domain
│   ├── model.py         # ProcessGraph: flat JSON wrapper, STEP_METADATA_KEYS, lookups
│   ├── workspace.py     # WorkspaceManifest: process tree index, summaries
│   ├── store.py         # Session-scoped graph store with SQLite backing + in-memory cache (~25 public methods)
│   ├── layout.py        # Auto-positioning for new nodes
│   └── bpmn_export.py   # JSON → BPMN 2.0 XML export (model only)
│
│
├── data/                # One subfolder per template type (multiple pages each)
│   ├── pharmacy/            # Baseline template (seeded at startup)
│   │   ├── workspace.json   # Process tree, summaries, tags
│   │   └── graphs/          # global.json, S1.json … S7.json
│   ├── logistics/
│   │   ├── workspace.json
│   │   └── graphs/          # global.json (and optional more pages)
│   └── manufacturing/
│       ├── workspace.json
│       └── graphs/          # global.json (and optional more pages)
│
└── tests/
    ├── conftest.py          # reset_db fixture (init SQLite, seed baseline, cleanup caches)
    ├── test_chat_flow.py    # Chat returns graph_json and meta
    ├── test_graph_idempotency.py  # Risk dedup, edge idempotency
    ├── test_hierarchy.py    # Process-scoped APIs, workspace, name resolution
    └── test_json_roundtrip.py     # JSON load, ProcessGraph, BPMN export
```

### What each module does

**main.py** — App entry point. The `lifespan` initializes the SQLite database (`db.get_conn()`), seeds the baseline from `workspace.json` + JSON graph files (`graph.store.init_baseline()`), and logs Bedrock/Nova status.

**config.py** — All env vars and constants. Key settings: `DATA_DIR`, `BASELINE_TEMPLATE` (default pharmacy), `BASELINE_WORKSPACE_PATH`, `BASELINE_GRAPHS_DIR`, `DEFAULT_PROCESS_ID`, `MAX_TOOL_ROUNDS`, `GROQ_TIMEOUT`, `ALLOWED_CORS_ORIGINS`, `SESSION_ID_MAX_LEN`.

**db.py** — Singleton in-memory SQLite connection (`:memory:`). Tables: `baseline_processes` (seeded from JSON files), `baseline_workspace`, `session_processes` (per-session graph JSON), `session_workspace`, `session_process_history` (undo support), `chat_messages`. All persistence reads/writes go through this module. Data is ephemeral — lost on restart.

**routers/** — HTTP endpoints. Health check, chat (with per-session locking), and graph (JSON graph, workspace, BPMN export, node CRUD, positions, undo, name resolution).

**agent/** — The Aurelius assistant. Runtime runs the Nova (Bedrock) chat loop with tools. Tools define what the LLM can do: all 19 metadata fields are available in update_node. Prompt includes guidance on operational data fields.

**graph/** — JSON-native process graph domain. Model wraps a raw dict (no parsing needed). Workspace manages the process tree index. Store provides session-scoped CRUD with an LRU cache backed by SQLite. Layout positions new nodes. BPMN export converts JSON graphs to BPMN 2.0 XML for download compatibility.

**data/** — One subfolder per template type (`pharmacy/`, `logistics/`, `manufacturing/`). Each has `workspace.json` and `graphs/` (one or more page JSONs). Pharmacy is seeded as baseline at startup; session init can load any template by id.

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

See `env.example` for all variables. Copy to `.env` and set AWS credentials (Bedrock) for chat.

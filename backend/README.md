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

## Conventions

### Error and "not found"

- **BPMN store** (`bpmn/store.py`): Returns `None` or `False` when an entity is not found. Callers check these values.
- **Agent tools** (`agent/tools.py`): Convert store results to JSON for the LLM: success as entity or `{"deleted": true}`; "not found"/errors as `{"error": "..."}`.

### Configuration

See `env.example` for all variables. Copy to `.env` and set at least `GROQ_KEY` for chat.

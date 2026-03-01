# Consularis Backend

FastAPI API for the Consularis app: Aurelius chat (Groq + tools), session-scoped BPMN graph, and session persistence.

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

## Structure

```
backend/
├── main.py              # FastAPI app, lifespan, CORS, router registration
├── config.py            # Env and constants (GROQ_KEY, paths, CORS, storage)
├── deps.py              # get_session_store() — used by routers and overridable in tests
├── graph_store.py       # Facade over bpmn.store (session BPMN + graph ops)
├── requirements.txt
├── env.example          # Template for .env
│
├── routers/             # HTTP routes by feature
│   ├── health.py        # GET /health
│   ├── domain.py        # POST /api/select-domain
│   ├── chat.py          # OPTIONS + POST /api/chat
│   └── graph.py         # GET /api/graph/baseline, /export, /json
│
├── services/            # Application services
│   └── chat.py          # handle_chat_turn (append → run_chat/fallback → append → return)
│
├── agent/               # Aurelius chat + tools
│   ├── runtime.py       # run_chat loop (Groq, tool rounds, timeout/retries)
│   ├── tools.py         # Tool schemas + registry, run_tool dispatch
│   ├── fallback.py      # try_apply_message_update when LLM didn’t use tools
│   └── prompt.py        # SYSTEM_PROMPT
│
├── bpmn/                # BPMN 2.0 domain
│   ├── model.py         # BpmnModel, lanes, tasks, flows, extension keys
│   ├── parser.py        # parse_bpmn_xml (file or string)
│   ├── serializer.py    # serialize_bpmn_xml (with diagram interchange for bpmn-js)
│   ├── layout.py        # Layout constants and layout_bounds() for JSON + DI
│   ├── store.py         # Session-scoped in-memory BPMN store
│   └── adapter.py       # legacy_to_model (legacy JSON → BpmnModel, used by FileSessionStore)
│
├── storage/             # Session persistence
│   ├── base.py          # SessionStore protocol
│   ├── memory.py        # InMemorySessionStore (chat + graph via graph_store)
│   └── file.py          # FileSessionStore (one JSON file per session)
│
├── data/                # Runtime data
│   ├── pharmacy_circuit.bpmn   # Baseline BPMN (required at startup)
│   └── sessions/               # Session JSON files when STORAGE=file
│
└── tests/
    ├── conftest.py      # reset_graph_store, force_missing_groq_key, test_store, client (DI)
    ├── test_chat_flow.py
    ├── test_graph_idempotency.py
    └── test_bpmn_roundtrip.py
```

### What each folder does

**routers/** — HTTP endpoints. Each file groups routes for one area: health check, domain selection, chat, and graph (baseline BPMN, export XML, export JSON). The app in main.py mounts these routers so all URLs are defined here, not in main.

**services/** — Application logic that coordinates several steps. The chat service runs a full chat turn: save the user message, call the agent (or fallback), save the assistant reply, and return the result. Routes call services so HTTP handling stays thin.

**agent/** — The Aurelius assistant. Runtime runs the Groq chat loop with tools (with timeout and retries). Tools define what the LLM can do on the graph (get/update nodes and edges) and run those actions. Fallback applies simple edits from the user message when the LLM does not use tools. Prompt holds the system instructions for the assistant.

**bpmn/** — Everything about the process graph format. Model is the in-memory shape (lanes, tasks, flows). Parser reads BPMN XML from a file or string. Serializer writes BPMN XML (including diagram layout for the frontend). Layout holds shared sizes and positions for the diagram. Store keeps one graph per session in memory. Adapter converts old JSON session format into the current model (used when loading file-backed sessions).

**storage/** — Where session data lives. The protocol says each session has a graph and a chat history. Memory storage keeps both in RAM (graph via graph_store). File storage writes one JSON file per session under data/sessions when you set STORAGE=file.

**data/** — Files the app reads or writes at runtime. The baseline BPMN file is the default process graph loaded for every new session. The sessions subfolder is where file storage puts session JSON files (only used when STORAGE=file).

**tests/** — Pytest tests. Conftest sets up fixtures: reset the in-memory graph store between tests, force no Groq key so tests don’t call the API, and provide a test client that uses a dedicated session store. The test files cover chat flow, graph behaviour, and BPMN round-trip.

## Conventions

### Error and “not found”

- **BPMN store** (`bpmn/store.py`): Returns `None` or `False` when an entity is not found. Callers check these values.
- **Agent tools** (`agent/tools.py`): Convert store results to JSON for the LLM: success as entity or `{"deleted": true}`; “not found”/errors as `{"error": "..."}`.

### Configuration

See `env.example` for all variables. Copy to `.env` and set at least `GROQ_KEY` for chat.

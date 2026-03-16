# Consularis Backend

FastAPI API for Consularis: Aurelius chat (Amazon Nova + tools), JSON-native process store, and in-memory SQLite persistence.

**Deps and env:** The repo root has `requirements.txt`, `requirements-dev.txt`, and `.env.example`. Copy `.env.example` to `backend/.env` and install dependencies from the root (see [root README](../README.md)).

---

## Run

From repo root:

```bash
cp .env.example backend/.env
# Edit backend/.env with AWS credentials (Bedrock)

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- API: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`

**Tests:** From root: `pip install -r requirements-dev.txt`, then `cd backend && pytest -v`.

---

## Structure

```
backend/
├── main.py              # FastAPI app, lifespan (DB + baseline seed), CORS, routers
├── config.py            # Env and constants (loads backend/.env)
├── db.py                # In-memory SQLite: baseline, session, workspace, chat_messages
├── stats.py             # Usage stats (API calls, tokens)
│
├── routers/             # HTTP routes
│   ├── health.py        # GET /health
│   ├── chat.py          # POST /api/chat, /api/chat/confirm, GET /api/models, /api/stats
│   ├── graph.py         # JSON graph, workspace, BPMN export, node/edge CRUD
│   ├── analyze.py      # POST /api/analyze, /api/report, /api/appointment
│   ├── session.py      # POST /api/session/init
│   └── validation.py   # Shared session_id validators
│
├── agent/               # Aurelius (Nova/Bedrock)
│   ├── runtime_nova.py  # run_chat loop, planner/executor, tool rounds
│   ├── tools.py         # Tool schemas and run_tool dispatch
│   ├── prompt.py        # MULTIAGENT_CONTEXT, PLANNER prompts
│   ├── context.py       # Rolling conversation summary
│   ├── bedrock_client.py
│   ├── analyzer.py     # Automation analysis (read-only Nova call)
│   └── report_generator.py  # Report narratives (executive summary, operations)
│
├── graph/               # JSON-native process graph
│   ├── model.py         # ProcessGraph, STEP_METADATA_KEYS
│   ├── workspace.py     # WorkspaceManifest (process tree index)
│   ├── store.py         # Session-scoped CRUD, cache, baseline clone
│   ├── layout.py        # Auto-position for new nodes
│   ├── bpmn_export.py   # JSON → BPMN 2.0 XML
│   ├── summary.py      # Graph summary for LLM context
│   └── validation.py   # Plan-step and graph validation
│
├── data/                # Templates (one subfolder per sector)
│   ├── pharmacy/        # Baseline (seeded at startup)
│   │   ├── workspace.json
│   │   └── graphs/      # global.json, S1.json, …
│   ├── logistics/
│   ├── manufacturing/
│   └── …                # retail, restaurant, electrician, plumber, cleaning
│
└── tests/               # Pytest (conftest resets DB + baseline per test)
    ├── conftest.py
    ├── test_chat_flow.py
    ├── test_graph_idempotency.py
    ├── test_hierarchy.py
    ├── test_json_roundtrip.py
    └── test_session_init.py
```

---

## What each part does

- **main.py** — Entry point. Lifespan initializes SQLite and seeds baseline from `graph.store.init_baseline()`.
- **config.py** — Env and constants: AWS/Bedrock, `DATA_DIR`, `BASELINE_TEMPLATE`, CORS, timeouts, `SESSION_ID_MAX_LEN`.
- **db.py** — Singleton in-memory SQLite; tables for baseline, session processes/workspace, chat_messages, conversation_summaries, pending_plans, appointment_requests.
- **routers/** — Health, chat (Aurelius + plan confirm), graph (JSON/workspace/BPMN/CRUD), analyze (analyzer + report + appointment), session (init from template or blank). `validation.py` provides shared session_id validators.
- **agent/** — Nova/Bedrock chat loop (planner proposes plans; executor runs on confirm). Tools: get_full_graph, update_node, add_node, delete_node, add_edge, delete_edge, insert_step_between, etc. Analyzer and report_generator are separate Nova calls (read-only / narrative generation).
- **graph/** — ProcessGraph model, WorkspaceManifest, session-scoped store with cache, layout, BPMN export, summary for LLM, validation for plan steps and full graph.
- **data/** — One folder per sector; each has `workspace.json` and `graphs/*.json`. Pharmacy is the default baseline.
- **tests/** — Pytest with `reset_db` fixture (clean DB + seed baseline before each test).

---

## Conventions

- **Graph store** returns `None` or `False` when an entity is not found. **Agent tools** return JSON: success as entity or `{"deleted": true}`; errors as `{"error": "..."}`.
- **Config:** See root `.env.example`. Copy to `backend/.env` and set AWS credentials for chat and reports.

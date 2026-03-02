# Data flow and ownership

This document describes how requests flow through the Consularis backend and where graph and chat state live. It is the single reference for "who owns what."

## Backend structure

```mermaid
flowchart TB
  subgraph backend [Backend]
    Main[main.py]
    Config[config.py]
    Store[storage.memory]
    StoreBase[storage.base]
    GraphStore[graph_store]
    AgentRun[agent.runtime]
    AgentPrompt[agent.prompt]
    AgentTools[agent.tools]
    AgentFallback[agent.fallback]
  end
  Main --> Config
  Main --> Store
  Main --> AgentRun
  Store --> StoreBase
  Store --> GraphStore
  AgentRun --> AgentPrompt
  AgentRun --> AgentTools
  AgentRun --> GraphStore
  AgentFallback --> GraphStore
```

- **main.py**: Routes only; one global `store`; validates `session_id`; single fallback path when no tools.
- **config.py**: Single place for env and constants.
- **storage**: Protocol in base, in-memory/file implementations; chat in `_chat`, BPMN graph delegated to graph_store.
- **graph_store**: Session-scoped BPMN graph (`BpmnModel` per `session_id`); baseline from config; all graph CRUD and validation (risk dedupe, no duplicate edges).
- **agent**: Split into prompt, tools, fallback, runtime; tools and fallback call graph_store by `session_id`.

## Where state lives

- **Graph**: Lives in `graph_store._sessions` (keyed by `session_id`) as BPMN in-memory model. All writes go through graph_store (tools and fallback).
- **Chat**: Lives in the store’s `_chat` dict (e.g. `storage/memory.py`), keyed by `session_id`.
- **Conceptually**: One session = one BPMN graph (in graph_store) + one chat history (in store). Implemented in two modules for separation of concerns; the store interface (`get_bpmn_xml`, `get_chat_history`, `append_chat_message`) is the single abstraction used by main and agent.

## Request path

- **GET /health**: Health check; no store or session.
- **GET /api/graph/baseline**: Serves the baseline BPMN XML from file (no session). Used by the frontend to show the default graph.
- **GET /api/graph/export**: Validates `session_id` → store.ensure_session(session_id) → returns BPMN XML for that session.
- **GET /api/graph/json**: Validates `session_id` → store.ensure_session(session_id) → returns session graph as JSON (lanes, nodes, edges, layout) for the Process view.
- **POST /api/chat**: Validates body → append user message → run_chat(history) → if no tools used, try_apply_message_update (fallback) → append assistant message → return message + BPMN XML + meta. The chat handler runs under a per-session lock so concurrent requests for the same session do not interleave.

## State location: backend only, frontend is view

- **Single source of truth**: The graph and chat live only in the backend. The backend is the only place that mutates or persists state.
- **Frontend**: Holds a view of BPMN XML for rendering only. It is not authoritative. The frontend refreshes from backend BPMN XML after chat updates and on explicit export fetches.

## Where the original graph is kept

- The **baseline** graph is the file at `BASELINE_GRAPH_PATH` (default: `backend/data/pharmacy_circuit.bpmn`). It is loaded once at startup and cached; the file is read-only and never modified by the app.
- **New sessions**: When a new session is created, the backend uses `copy.deepcopy(cached_baseline)` and stores that copy in the session. Every user/session starts from the same initial graph; each session then has its own copy that can be personalized by chat. The baseline itself stays unchanged.
- **With persistence**: The baseline (or its cached copy) remains the template. New sessions are still created by cloning that baseline; only the **session** data (personalized graph + chat) is persisted.

## Graph format contract

- Canonical graph format is BPMN 2.0 XML.
- API and frontend graph exchange uses BPMN XML only.
- Legacy `{ phases, flow_connections }` is retained only for backward migration of older persisted sessions.

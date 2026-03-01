# Graph operations - verification

This doc verifies graph operations after the BPMN-only migration.

---

## 1. Canonical graph format

- Session graph is stored as `BpmnModel` in memory (`backend/bpmn/store.py`).
- API graph exchange format is BPMN XML only.
- Legacy `{ phases, flow_connections }` exists only for migration of old persisted sessions in `backend/storage/file.py`.

---

## 2. Backend operation surface

`graph_store.py` re-exports BPMN-backed operations used by agent tools and fallback:

- `get_bpmn_xml`
- `get_task_ids`
- `get_graph_summary`
- `get_node`, `update_node`, `add_node`, `delete_node`
- `get_edges`, `update_edge`, `add_edge`, `delete_edge`
- `validate_graph`

All operations mutate session state in the BPMN store and are keyed by `session_id`.

---

## 3. Agent runtime and tools

- `agent/runtime.py` builds context using `get_graph_summary(session_id)`.
- `agent/tools.py` keeps tool name `get_graph` for compatibility, but returns BPMN XML (canonical format).
- `agent/fallback.py` no longer reads legacy graph dict; it uses:
  - `get_task_ids(session_id)` for valid node IDs
  - `get_edges(session_id)` for edge existence checks

This removes all production dependencies on legacy graph JSON.

---

## 4. API responses

- `GET /api/graph/export` returns BPMN XML (`application/xml`).
- `POST /api/chat` returns:
  - `message`
  - `bpmn_xml`
  - `meta` (`tools_used`, `fallback_used`, `session_id`)

`GET /api/graph` has been removed.

---

## 5. Frontend behavior

- Dashboard is BPMN-only (no React Flow process view).
- `BpmnViewer` renders XML from:
  - `getBpmnXml(sessionId)`, or
  - `data.bpmn_xml` returned by chat.
- Chat refreshes the diagram using BPMN XML payloads.

---

## 6. Verification checklist

- Backend tests pass with BPMN-only responses.
- Frontend builds and lints after removing React Flow.
- Docs and API references align to BPMN-only contracts.

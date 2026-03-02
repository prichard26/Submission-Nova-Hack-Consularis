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
- `agent/tools.py` exposes BPMN-capable tools:
  - **Access**: `get_graph` (full BPMN XML), `get_graph_summary` (phases + step IDs), `get_node`, `get_edges`
  - **Modify nodes**: `update_node` (name, actor, duration_min, description, inputs, outputs, risks, automation_potential, automation_notes), `add_node`, `delete_node`
  - **Modify edges**: `add_edge`, `update_edge`, `delete_edge`
  - **Bulk / validation**: `set_graph(bpmn_xml)` (replace session with BPMN XML), `validate_graph`
- `agent/fallback.py` no longer reads legacy graph dict; it uses:
  - `get_task_ids(session_id)` for valid node IDs
  - `get_edges(session_id)` for edge existence checks

This removes all production dependencies on legacy graph JSON. The agent can fully read and modify the graph in BPMN terms.

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

- Dashboard offers two view modes: **Process** (React Flow, graph JSON) and **BPMN** (bpmn-js, BPMN XML).
- **Process view** (`ProcessGraphViewer`): uses `getGraphJson(sessionId)` → `GET /api/graph/json?session_id=...`; refreshes on `refreshTrigger` and after chat updates that propagate to the canvas.
- **BPMN view** (`BpmnViewer`): uses `getBpmnXml(sessionId)` or `getBaselineBpmnXml()`, and `data.bpmn_xml` returned by chat; renders via bpmn-js.
- Chat returns `bpmn_xml`; the frontend refreshes the diagram (both views) using that payload or a refetch.

---

## 6. Verification checklist

- Backend tests pass with BPMN-only responses.
- Frontend builds and lints; Process view uses React Flow with graph JSON; BPMN view uses bpmn-js with BPMN XML.
- Docs and API references align to BPMN-only contracts.

# Graph structure

The process graph is stored and exchanged as **BPMN 2.0 XML** with a **hierarchical process tree**.

## 1. Hierarchical model (digital twin)

Instead of one giant BPMN, the application manages many processes:

- A root process (default: `Process_Global`) gives the global view.
- Child processes represent subgraphs (department/process/phase).
- Parent -> child links use `bpmn:callActivity` (`calledElement=<child_process_id>`).
- The process tree is declared by `backend/data/graphs/registry.json`.

Baseline files live in `backend/data/graphs/`:

- `global.bpmn`
- `P1.bpmn` ... `P7.bpmn`
- `registry.json`

If no registry exists, the app falls back to `BASELINE_GRAPH_PATH` single-process mode.

## 2. IDs vs names

Keep stable technical IDs and expose human names:

- **Technical IDs** (stable): `Process_P1`, `P1.2`, `Call_P1`.
- **Human names** (display/chat): `Prescription`, `Verify Prescription`.

Chat remains name-friendly because:

- Graph summary includes both IDs and names.
- Process list endpoint returns process names.
- Step resolution endpoint maps name fragments to IDs.

## 3. In-memory store shape

Store state in `backend/bpmn/store.py`:

- Baseline:
  - `_baseline_models: dict[process_id, BpmnModel]`
  - `_baseline_registry: list[dict]`
- Session:
  - `_sessions: dict[session_id, dict[process_id, BpmnModel]]`
  - `_session_registries: dict[session_id, list[dict]]`

So one session contains **multiple BPMN models**, one per process.

## 4. BPMN node types

`BpmnModel` now supports:

- `tasks`
- `call_activities`
- `start_events`
- `end_events`
- `gateways`
- `sequence_flows`

`call_activities` are serialized as `<bpmn:callActivity ... calledElement="...">`.

## 5. API contracts

Graph endpoints are process-scoped:

- `GET /api/graph/baseline?process_id=Process_Global`
- `GET /api/graph/export?session_id=...&process_id=Process_P1`
- `GET /api/graph/json?session_id=...&process_id=Process_P1`
- `GET /api/graph/processes?session_id=...`
- `GET /api/graph/resolve?session_id=...&name=Verify&process_id=Process_P1` (optional process scope)

Chat is process-scoped:

- `POST /api/chat` request supports `process_id`.
- Response `meta` includes `process_id`.

## 6. Persistence format

File session storage uses multi-process payload:

```json
{
  "registry": [{"process_id": "Process_Global", "name": "Global", "parent_id": null}],
  "graphs": {
    "Process_Global": "<bpmn xml>",
    "Process_P1": "<bpmn xml>"
  },
  "chat": [{"role": "user", "content": "..."}]
}
```

Legacy `{ "graph": "<xml>" }` is still migrated/accepted.

## 7. Frontend behavior

- Viewer state tracks current `processId`.
- Process tree is fetched from `/api/graph/processes`.
- Breadcrumb + selector switch process context.
- Double-clicking a call activity in BPMN view drills down into `calledElement`.
- Chat messages include current `processId`.

This structure keeps very large enterprise maps readable while preserving a global-to-detailed navigation model.

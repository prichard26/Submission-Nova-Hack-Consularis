# Graph structure

The process graph is stored and manipulated as **BPMN 2.0**. BPMN XML is now the only graph format exchanged by API and frontend.

---

## 1. Canonical format: BPMN 2.0

**Source of truth**: BPMN 2.0 XML. Baseline: `backend/data/pharmacy_circuit.bpmn` (or path from `BASELINE_GRAPH_PATH`). Sessions hold an in-memory BPMN model; file storage persists the graph as a BPMN XML string.

### 1.1 BPMN XML structure

- **Root**: `bpmn:definitions` with one `bpmn:process`.
- **Process**: `id`, `name`, `isExecutable="false"`. Contains:
  - One **laneSet** with one **lane** per phase (P1–P7).
  - **Task** elements (one per step); each lane has **flowNodeRef** children listing the task ids in that phase.
  - **sequenceFlow** elements: `id`, `sourceRef`, `targetRef`, `name`; optional `conditionExpression` (tFormalExpression) for conditional edges.

No Exclusive Gateway nodes are stored; branching is expressed as multiple outgoing sequence flows from a task with different `conditionExpression` values.

### 1.2 Extension namespace

Custom namespace: `http://consularis.example/bpmn` (prefix `consularis`). On each **task**, `bpmn:extensionElements` may contain:

| XML element              | Purpose                          | Stored as (in-memory) |
|--------------------------|----------------------------------|------------------------|
| `consularis:actor`       | Role (e.g. Pharmacist)          | string                 |
| `consularis:durationMin` | Duration (e.g. "5–10 min")      | string                 |
| `consularis:description` | Step description                | string                 |
| `consularis:inputs`      | JSON array of input names       | list of strings        |
| `consularis:outputs`     | JSON array of output names      | list of strings        |
| `consularis:risks`       | JSON array of risk strings      | list of strings        |
| `consularis:automationPotential` | "high" / "medium" / "low" | string          |
| `consularis:automationNotes`    | Free text                      | string                 |

In XML, list fields are serialized as JSON strings (e.g. `["a","b"]`).

---

## 2. In-memory model (BpmnModel)

The backend works on a **BpmnModel** (see `backend/bpmn/model.py`): process id/name plus three lists.

### 2.1 Process

- `process_id`: string (e.g. `"Process_Pharmacy"`).
- `process_name`: string (e.g. `"Pharmacy medication circuit"`).

### 2.2 Lanes (phases)

Each lane is a dict:

| Field             | Type     | Description |
|-------------------|----------|-------------|
| `id`              | string   | Phase id (e.g. P1, P2, … P7). |
| `name`            | string   | Phase display name. |
| `description`     | string   | Optional phase description. |
| `flow_node_refs`  | string[] | Ordered list of task ids in this lane. |

Order of lanes in the list = order of phases. Order of ids in `flow_node_refs` = order of steps in that phase.

### 2.3 Tasks (steps)

Each task is a dict:

| Field        | Type  | Description |
|--------------|-------|-------------|
| `id`         | string | Step id: `{lane_id}.{number}` (e.g. P1.1, P2.4). Unique across the process. |
| `name`       | string | Task name. |
| `lane_id`    | string | Id of the lane this task belongs to. |
| `extension`  | dict   | See below. |

**extension** dict (snake_case keys):

| Key                  | Type     | Default / notes |
|----------------------|----------|------------------|
| `actor`              | string   | "" |
| `duration_min`       | string   | "—" |
| `description`        | string   | "" |
| `inputs`             | list     | [] |
| `outputs`            | list     | [] |
| `risks`              | list     | [] (deduplicated when updating). |
| `automation_potential` | string | "" |
| `automation_notes`   | string   | "" |

### 2.4 Sequence flows (edges)

Each flow is a dict:

| Field         | Type   | Description |
|---------------|--------|-------------|
| `id`          | string | Unique flow id (e.g. `flow_P1.1_P1.2`). |
| `source_ref`  | string | Source task id. |
| `target_ref`  | string | Target task id. |
| `name`        | string | Edge label. |
| `condition`   | string | Optional; present only when the edge is conditional. |

At most one flow per `(source_ref, target_ref)` pair. Adding the same pair again updates the existing flow’s `name` and/or `condition`.

---

## 3. Validation rules

- Every sequence flow’s `source_ref` and `target_ref` must be a task id in the model.
- Task ids must be unique.
- Within a lane, `flow_node_refs` must not contain duplicate ids.
- Tasks should have a name (validation reports steps with no name).

---

## 4. API contracts

- `GET /api/graph/export?session_id=...` returns the full session graph as BPMN XML (`application/xml`).
- `POST /api/chat` returns:
  - `message`: assistant reply
  - `bpmn_xml`: updated session BPMN XML
  - `meta`: `{ tools_used, fallback_used, session_id }`

---

## 5. Where it’s used

- **Baseline**: Loaded once at startup from `BASELINE_GRAPH_PATH` (BPMN XML), parsed into a BpmnModel and cached. New sessions get a deep copy of that model.
- **Sessions**: In-memory BpmnModel per session. File storage persists the graph as BPMN XML string in the session JSON.
- **API**: Graph endpoints return BPMN XML only.
- **Agent**: Tools operate on the BPMN store; graph context strings are built directly from the BPMN model.
- **Frontend**: Renders BPMN directly with `bpmn-js` and refreshes from BPMN XML.

---

## 6. Example (API chat response)

```json
{
  "message": "As you wish. I have updated P1.2.",
  "bpmn_xml": "<?xml version=\"1.0\" encoding=\"UTF-8\"?><bpmn:definitions ...>",
  "meta": {
    "tools_used": true,
    "fallback_used": false,
    "session_id": "acme-pharmacy"
  }
}
```

This document is the single reference for BPMN graph structure and BPMN-only API contracts.

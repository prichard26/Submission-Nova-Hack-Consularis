# Graph structure

The process graph is stored and exchanged as **JSON**, organized as a **hierarchical process tree** with a **workspace manifest**, backed by **in-memory SQLite**.

## 1. Process tree

The system models processes as a tree of arbitrary depth. Each node in the tree is one JSON graph document (one `ProcessGraph`). Parent processes link to children via **subprocess steps** (`type: "subprocess"`, `called_element: "Process_P1"`).

```
Process_Global (Pharmacy medication circuit)
├── Process_P1  (Prescription)
├── Process_P2  (Selection, Acquisition, and Reception)
├── Process_P3  (Storage and Storage Management)
├── Process_P4  (Distribution)
├── Process_P5  (Dispensing and Preparation)
├── Process_P6  (Administration)
└── Process_P7  (Monitoring and Waste Management)
```

The tree is defined by a **workspace manifest** (`workspace.json`), not hardcoded. Adding more depth requires only a new JSON graph file and a workspace entry — no code changes.

## 2. Workspace manifest

**File**: `backend/data/workspace.json`

```json
{
  "format_version": "1.0",
  "workspace_id": "ws_pharmacy",
  "name": "Hospital Pharmacy Operations",
  "process_tree": {
    "root": "Process_Global",
    "processes": {
      "Process_Global": {
        "name": "Pharmacy medication circuit",
        "depth": 0,
        "path": "/Process_Global",
        "children": ["Process_P1", "Process_P2", ...],
        "graph_file": "global.json",
        "owner": "Pharmacy Department",
        "category": "clinical",
        "criticality": "high",
        "summary": { "step_count": 0, "subprocess_count": 7 }
      }
    }
  }
}
```

## 3. JSON graph schema

Each process is a JSON file (`backend/data/graphs/*.json`):

```json
{
  "format_version": "1.0",
  "process_id": "Process_P1",
  "name": "Prescription",
  "metadata": { "owner": "...", "category": "...", "criticality": "..." },
  "lanes": [
    { "id": "P1", "name": "Prescription", "node_refs": ["Start_P1", "P1.1", "P1.2", "P1.3", "End_P1"] }
  ],
  "steps": [
    { "id": "P1.1", "name": "Prescribe Medication", "type": "step", "short_id": "P1.1", "lane_id": "P1",
      "position": { "x": 504, "y": 44 }, "actor": "Physician", "duration_min": "5–10 min", ... }
  ],
  "flows": [
    { "from": "Start_P1", "to": "P1.1", "label": "Process starts" }
  ]
}
```

### Step types

| Type | Description |
|------|-------------|
| `start` | Process entry point (circle, thin border) |
| `end` | Process exit point (circle, thick border) |
| `step` | Process step with full metadata |
| `decision` | Decision/routing point (diamond) |
| `subprocess` | Links to child process (`called_element` field) |

## 4. IDs vs names

**Principle**: IDs are for machines; names are for humans.

- **Technical IDs** (stable): `Process_P1`, `P1.2`, `Start_P1`, `End_P1`.
- **Short IDs** (human-friendly alias): `P1.1`, `P1.2`, etc.
- **Human names** (display/chat): `Prescription`, `Verify Prescription`.

| Surface | What is shown |
|---------|---------------|
| React Flow node labels | Step **name** + metadata badges |
| Agent graph summary (LLM context) | `P1 Prescription: P1.1 (Prescribe Medication), Physician, 5–10 min, $8.50, 3.2% err, HIGH automation` |
| Agent tool calls | **node_id** / **process_id** (resolved from name) |
| API query params | `process_id=Process_P1` (stable slug) |
| Chat with user | User says "Verify Prescription"; agent resolves to `P1.2` via `resolve_step` |

## 5. Persistence: in-memory SQLite

All state lives in a single in-memory SQLite connection (`:memory:`), managed by `backend/db.py`.

### Schema

```sql
CREATE TABLE baseline_processes (
    process_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    parent_id  TEXT,
    graph_json TEXT NOT NULL
);

CREATE TABLE baseline_workspace (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    workspace_json TEXT NOT NULL
);

CREATE TABLE session_processes (
    session_id TEXT NOT NULL,
    process_id TEXT NOT NULL,
    graph_json TEXT NOT NULL,
    PRIMARY KEY (session_id, process_id)
);

CREATE TABLE session_workspace (
    session_id     TEXT PRIMARY KEY,
    workspace_json TEXT NOT NULL
);

CREATE TABLE chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session_process_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    process_id TEXT NOT NULL,
    graph_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Lifecycle

1. **Startup**: `graph.store.init_baseline()` reads `workspace.json` and all JSON graph files into baseline tables.
2. **New session**: On first access, `db.clone_baseline_to_session()` copies all baseline rows into session tables.
3. **Mutations**: `graph.store` modifies the cached `ProcessGraph`, then calls `db.upsert_session_json()` to persist.
4. **Reads**: `graph.store._get_graph()` checks the in-memory cache first; on miss, loads from `session_processes` (or clones baseline).
5. **Undo**: Before each mutation, the current state is pushed to `session_process_history`. Undo pops and restores.

The SQLite database is ephemeral (`:memory:`) — data is lost on process restart. This provides structured SQL access without file I/O overhead.

## 6. In-memory cache

`graph.store` maintains dict caches:

```python
_cache: dict[tuple[str, str], ProcessGraph]       # (session_id, process_id) -> parsed model
_ws_cache: dict[str, WorkspaceManifest]            # session_id -> workspace
```

This avoids re-parsing JSON on every request. Cache entries are created on first access and updated on mutation.

## 7. Extension metadata (19 fields)

Steps carry rich metadata as flat top-level fields (no nested extension sub-dict):

### Core fields

| Field | Type | Description |
|-------|------|-------------|
| `actor` | string | Who performs the task |
| `duration_min` | string | Estimated duration |
| `description` | string | What the task does |
| `inputs` | list | What the task receives |
| `outputs` | list | What the task produces |
| `risks` | list | Associated risks |
| `automation_potential` | string | How automatable (high/medium/low/none) |
| `automation_notes` | string | Notes on automation feasibility |

### Operational data fields

| Field | Type | Description |
|-------|------|-------------|
| `current_state` | string | How the task is currently performed (manual/semi_automated/automated) |
| `frequency` | string | How often (e.g. "200/day", "weekly") |
| `annual_volume` | string | Yearly execution count |
| `error_rate_percent` | string | Current error rate |
| `cost_per_execution` | string | Cost per execution in currency |
| `current_systems` | list | IT systems currently used |
| `data_format` | string | Primary data format (paper/electronic/mixed) |
| `external_dependencies` | list | External systems or parties |
| `regulatory_constraints` | list | Regulatory requirements |
| `sla_target` | string | Target SLA |
| `pain_points` | list | Known problems or friction |

## 8. API contracts

### Graph endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/graph/json` | GET | Session graph as JSON. `?session_id=…&process_id=…` |
| `/api/graph/workspace` | GET | Workspace manifest JSON. `?session_id=…` |
| `/api/graph/step` | POST | Update step fields. Body: `{ step_id, updates }` |
| `/api/graph/node` | POST | Create node. Body: `{ lane_id, name, type }` |
| `/api/graph/node` | DELETE | Delete node. `?session_id=…&node_id=…&process_id=…` |
| `/api/graph/position` | POST | Batch update positions. Body: `{ positions: { id: {x,y} } }` |
| `/api/graph/undo` | POST | Undo last mutation. `?session_id=…&process_id=…` |
| `/api/graph/export` | GET | Session graph as BPMN 2.0 XML (for download). `?session_id=…&process_id=…` |
| `/api/graph/baseline` | GET | Baseline as BPMN 2.0 XML. `?process_id=…` |
| `/api/graph/resolve` | GET | Fuzzy name → ID resolution. `?session_id=…&name=…&process_id=…` |

### Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | `{ session_id, message, process_id? }` → `{ message, graph_json, process_id, meta }` |

`meta` includes `tools_used`, `session_id`, and `process_id`.

## 9. Frontend architecture

- **ProcessCanvas** renders one process graph using React Flow with custom nodes (StepNode, DecisionNode, SubprocessNode, EventNode).
- **LandscapeView** renders the workspace process tree using React Flow + Dagre layout.
- **DetailPanel** slides in to show/edit all 19 metadata fields for a selected step.
- **ProcessBreadcrumb** shows the navigation path when drilling into subprocesses.
- Graph data is fetched via `/api/graph/json`; the `useProcessGraph` hook manages loading and refresh.
- Chat returns `graph_json` and the canvas refreshes via `refreshTrigger` pattern.
- Lanes are rendered as non-interactive background rectangles (not React Flow group nodes) to avoid parent/child complexity.

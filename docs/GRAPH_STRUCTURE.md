# Graph structure

The process graph is stored and exchanged as **BPMN 2.0 XML**, organized as a **hierarchical process tree** backed by **in-memory SQLite**.

## 1. Process tree

The system models processes as a tree of arbitrary depth. Each node in the tree is one BPMN diagram (one `BpmnModel`). Parent processes link to children via **call activities** (`<bpmn:callActivity calledElement="Process_P1">`).

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

The tree is defined by a **process registry** (`registry.json`), not hardcoded. Adding more depth requires only a new BPMN file and a registry entry — no code changes.

## 2. Process registry

**File**: `backend/data/graphs/registry.json`

```json
{
  "processes": [
    {
      "process_id": "Process_Global",
      "name": "Pharmacy medication circuit",
      "parent_id": null,
      "bpmn_file": "global.bpmn",
      "owner": "Pharmacy Department",
      "category": "clinical",
      "criticality": "high"
    },
    {
      "process_id": "Process_P1",
      "name": "Prescription",
      "parent_id": "Process_Global",
      "bpmn_file": "P1.bpmn",
      "owner": "Pharmacy Department",
      "category": "clinical",
      "criticality": "high"
    }
  ]
}
```

Each entry includes:

| Field | Purpose |
|-------|---------|
| `process_id` | Stable technical ID (machine use) |
| `name` | Human-readable display name |
| `parent_id` | Parent process ID (`null` = root) |
| `bpmn_file` | Filename in `backend/data/graphs/` |
| `owner` | Department or team that owns this process |
| `category` | Process classification (clinical, logistics, supply_chain, compliance) |
| `criticality` | Risk level (critical, high, medium, low) |

## 3. IDs vs names

**Principle**: IDs are for machines; names are for humans.

- **Technical IDs** (stable): `Process_P1`, `P1.2`, `Call_P1`, `G2`.
- **Human names** (display/chat): `Prescription`, `Verify Prescription`.

| Surface | What is shown |
|---------|---------------|
| BPMN diagram labels | Task/lane **name** |
| Agent graph summary (LLM context) | `P1 Prescription: P1.1 (Prescribe Medication), P1.2 (Verify Prescription)` |
| Agent tool calls | **node_id** / **process_id** (resolved from name) |
| API query params | `process_id=Process_P1` (stable slug) |
| Chat with user | User says "Verify Prescription"; agent resolves to `P1.2` via `resolve_step` |

## 4. Persistence: in-memory SQLite

All state lives in a single in-memory SQLite connection (`:memory:`), managed by `backend/db.py`.

### Schema

```sql
CREATE TABLE baseline_processes (
    process_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    parent_id  TEXT,
    bpmn_xml   TEXT NOT NULL
);

CREATE TABLE session_processes (
    session_id TEXT NOT NULL,
    process_id TEXT NOT NULL,
    bpmn_xml   TEXT NOT NULL,
    PRIMARY KEY (session_id, process_id)
);

CREATE TABLE chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Lifecycle

1. **Startup**: `db.seed_baseline()` reads `registry.json` and all BPMN files into `baseline_processes`.
2. **New session**: On first access, `db.clone_baseline_to_session()` copies all baseline rows into `session_processes`.
3. **Mutations**: `bpmn.store` modifies the cached `BpmnModel`, then calls `db.upsert_session_xml()` to persist the serialized XML.
4. **Reads**: `bpmn.store._get_model()` checks the in-memory cache first; on miss, loads from `session_processes` (or clones baseline).

The SQLite database is ephemeral (`:memory:`) — data is lost on process restart. This provides structured SQL access without file I/O overhead.

## 5. In-memory cache

`bpmn.store` maintains a dict cache:

```python
_cache: dict[tuple[str, str], BpmnModel]  # (session_id, process_id) -> parsed model
```

This avoids re-parsing BPMN XML on every request. Cache entries are created on first access and updated on mutation.

## 6. BPMN node types

`BpmnModel` supports:

| Type | BPMN element | Usage |
|------|-------------|-------|
| `tasks` | `<bpmn:task>` | Process steps with metadata |
| `call_activities` | `<bpmn:callActivity>` | Links to child processes |
| `start_events` | `<bpmn:startEvent>` | Process entry point |
| `end_events` | `<bpmn:endEvent>` | Process exit point |
| `gateways` | `<bpmn:exclusiveGateway>` | Decision/routing points |
| `sequence_flows` | `<bpmn:sequenceFlow>` | Connections between nodes |
| `lanes` | `<bpmn:lane>` | Phases/groupings |

## 7. Extension metadata

Tasks carry rich metadata via BPMN extension elements under the `http://consularis.example/bpmn` namespace. There are 19 extension fields:

### Core fields

| Field | Type | Description |
|-------|------|-------------|
| `actor` | string | Who performs the task |
| `duration_min` | string | Estimated duration |
| `description` | string | What the task does |
| `inputs` | list | What the task receives |
| `outputs` | list | What the task produces |
| `risks` | list | Associated risks |
| `automation_potential` | string | How automatable (high/medium/low) |
| `automation_notes` | string | Notes on automation feasibility |

### Operational data fields

| Field | Type | Description |
|-------|------|-------------|
| `current_state` | string | How the task is currently performed (manual/semi-automated/automated) |
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

List-type fields are serialized as JSON arrays in the BPMN XML extension elements.

## 8. API contracts

### Graph endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/graph/baseline` | GET | Baseline BPMN XML. `?process_id=` (default `Process_Global`) |
| `/api/graph/export` | GET | Session graph as BPMN XML. `?session_id=…&process_id=…` |
| `/api/graph/resolve` | GET | Fuzzy name → ID resolution. `?session_id=…&name=…&process_id=…` |

### Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | `{ session_id, message, process_id? }` → `{ message, bpmn_xml, meta }` |

`meta` includes `tools_used`, `session_id`, and `process_id`.

## 9. Frontend behavior

- Dashboard shows one BPMN view (bpmn-js). XML is fetched via `/api/graph/export` or `/api/graph/baseline`.
- Chat returns updated `bpmn_xml` and the diagram refreshes after each turn.
- `process_id` can be included in chat requests to scope agent operations to a specific subprocess.

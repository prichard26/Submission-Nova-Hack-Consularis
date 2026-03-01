# Graph operations – verification

This doc verifies the end-to-end logic for every graph operation: backend store, agent tools, prompt, fallback, and frontend.

---

## 1. Data shape (single source of truth: backend)

- **Graph**: `{ "phases": [ ... ], "flow_connections": [ ... ] }`
- **Phase**: `{ "id": "P1"|"P2"|...|"P7", "name": "...", "steps": [ ... ] }`
- **Step (node)**: `{ "id": "P1.1", "name", "actor", "duration_min", "description", "inputs", "outputs", "risks", ... }`
- **Connection (edge)**: `{ "from": "P1.1", "to": "P1.2", "label": "...", "condition"?: "..." }`

Frontend builds React Flow nodes/edges from `phases` and `flow_connections` in `buildGraph.js`. After chat, the API returns the updated `graph` and the frontend calls `onGraphUpdate(data.graph)` so the diagram re-renders from the new `graphSource`.

---

## 2. Backend: `graph_store.py`

| Operation      | Function       | Behaviour |
|---------------|----------------|-----------|
| **Get graph** | `get_graph(session_id)` | Returns session dict (creates from baseline if new). Mutations happen on this same dict. |
| **Get node**  | `get_node(session_id, node_id)` | Finds step by `id` in any phase; returns step + `phaseName`, `phaseId` or `None`. |
| **Update node** | `update_node(session_id, node_id, updates)` | Allowed keys: `name`, `actor`, `duration_min`, `description`, `inputs`, `outputs`, `risks`. Risks deduped. Returns updated step or `None`. |
| **Add node**  | `add_node(session_id, phase_id, step_data)` | Finds phase by `phase_id` (P1..P7). New id = `{phase_id}.{last_step_num + 1}` (e.g. P2.3 → P2.4). Appends step with defaults. Returns new step or `None`. |
| **Delete node** | `delete_node(session_id, node_id)` | Removes step from its phase and **all edges** where `from` or `to` is that node. Returns `True`/`False`. |
| **Get edges**  | `get_edges(session_id, source_id?)` | Returns list of connections; optional filter by `from == source_id`. |
| **Update edge** | `update_edge(session_id, source, target, updates)` | Allowed keys: `label`, `condition`. Updates first matching connection; returns it or `None`. |
| **Add edge**   | `add_edge(session_id, source, target, label?, condition?)` | If edge already exists: **updates** its `label`/`condition` if provided and returns it. Else appends new connection. Returns `None` only if source/target not in step ids. |
| **Delete edge** | `delete_edge(session_id, source, target)` | Removes first connection with that from/to. Returns `True`/`False`. |
| **Validate**   | `validate_graph(session_id)` | Checks: edge endpoints are valid step ids; no duplicate step ids per phase; each step has name or id. Returns `{ "valid", "issues" }`. |

**Bug fix applied**: `add_node` used to compute the next id with `int(parts[0])` on "P2.3" (i.e. int("P2")), which crashed. It now uses only the part after the last dot: `int(last_id.split(".")[-1]) + 1`.

---

## 3. Agent tools: `agent/tools.py`

Each tool is dispatched in `run_tool(session_id, name, arguments)` and calls the corresponding graph_store function. Arguments are passed as given by the LLM (with safe defaults for optional fields).

| User intent (examples)        | Tool          | Args (main) | Notes |
|------------------------------|---------------|-------------|--------|
| See full graph / steps       | `get_graph`   | —           | Read-only. |
| See one step                  | `get_node`    | `node_id`   | |
| Change step name/duration/…   | `update_node` | `node_id`, `updates` | name, actor, duration_min, description, inputs, outputs, risks. |
| Add a step (box)              | `add_node`    | `phase_id`, `step_data` | phase_id P1..P7; step_data name, actor, duration_min, description. |
| Remove a step (box)           | `delete_node` | `node_id`   | Also removes all edges to/from that step. |
| List edges                    | `get_edges`   | `source_id?`| Optional filter. |
| **Rename / change link**      | **`update_edge`** | `source`, `target`, `updates` | `updates = { "label": "new name" }` or `{ "condition": "..." }`. |
| Add a link                    | `add_edge`    | `source`, `target`, `label?`, `condition?` | If edge exists, label/condition are updated (upsert). |
| Remove a link                 | `delete_edge` | `source`, `target` | |
| Move link A→B to A→C          | `delete_edge` then `add_edge` | Reconnect pattern. |
| Check consistency             | `validate_graph` | —         | |

Prompt explicitly says: *To rename or relabel an existing link, use update_edge(source, target, {"label": "new name"}) — do not use add_edge.*

---

## 4. Agent prompt: `agent/prompt.py`

- States that the agent can update steps, add/remove steps, add/remove/update links, and reconnect.
- **Rename link**: use `update_edge(source, target, {"label": "new name"})`, not `add_edge`.
- Reconnect: `delete_edge(A,B)` then `add_edge(A,C)`.
- Rules: only use tools; never invent IDs; call the tool for each change; ask if ambiguous; keep replies short.

---

## 5. Fallback: `agent/fallback.py` (when LLM does not use tools)

Fallback runs only when no tool was used. It matches the user message with regex and applies one update.

| Intent              | Pattern (simplified) | Action |
|---------------------|----------------------|--------|
| Duration            | P1.2 … 10 min / duration 10 P1.2 | `update_node(node_id, { duration_min })` |
| Step name           | P1.2 name to "X"     | `update_node(node_id, { name })` |
| Remove link          | remove link P1.1–P1.2 | `delete_edge(source, target)` |
| **Rename link**     | change link P7.2–P7.3 to "paul" | **`update_edge(source, target, { label })`** (added) |
| Reconnect           | reconnect P1.1 from P1.2 to P1.3 / change link P1.1–P1.2 to P1.3 | `delete_edge` + `add_edge` |
| Remove step(s)      | remove step P1.2 [, P1.3] | `delete_node` for each id |

---

## 6. Frontend: graph display and refresh

- **Source**: `graphSource` = `{ phases, flow_connections }` (from initial fetch and from chat response).
- **Build**: `buildGraphData(graphSource)` → `{ nodes, edges, phases, stepMap }`. Nodes from `phases[].steps`; edges from `flow_connections` with `id: "${from}-${target}"`, `label: [condition, label].filter(Boolean).join(" · ")`.
- **After chat**: `sendChat()` returns `data.graph`; `onGraphUpdate(data.graph)` → `setGraphSource({ phases, flow_connections })` → React re-runs `buildGraphData` and syncs nodes/edges, so the diagram shows all backend changes (steps and link names).

---

## 7. Quick checklist

| Operation           | Store        | Tool          | Prompt / fallback      | Frontend      |
|--------------------|-------------|---------------|-------------------------|---------------|
| Modify step         | ✅ update_node | ✅ update_node | ✅ prompt + fallback (duration, name) | ✅ from graph |
| Rename link         | ✅ update_edge | ✅ update_edge | ✅ prompt + fallback (rename link)   | ✅ edge label from `flow_connections` |
| Add link            | ✅ add_edge (or upsert) | ✅ add_edge | ✅ prompt               | ✅ from graph |
| Delete link         | ✅ delete_edge | ✅ delete_edge | ✅ prompt + fallback    | ✅ from graph |
| Add box (step)      | ✅ add_node  | ✅ add_node   | ✅ prompt               | ✅ from graph |
| Delete box (step)   | ✅ delete_node + edges | ✅ delete_node | ✅ prompt + fallback (remove step) | ✅ from graph |
| Reconnect link      | ✅ delete + add | ✅ both     | ✅ prompt + fallback    | ✅ from graph |

All graph operations are consistent end-to-end; the only fix applied was `add_node` id generation and the addition of fallback + prompt clarity for **rename link**.

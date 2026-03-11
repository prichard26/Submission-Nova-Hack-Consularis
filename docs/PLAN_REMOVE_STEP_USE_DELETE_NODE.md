# Remove/delete step must use delete_node in all cases

## Problem

When the user asks to **delete** or **remove** a step, the system should use **delete_node(id)** only. The store already removes the node and reconnects edges (predecessor → renumbered successor) automatically. In some cases the planner may still:

- Use only **delete_edge** and **add_edge** (e.g. delete_edge(pred, step), delete_edge(step, succ), add_edge(pred, succ)) without **delete_node(step)** — so the step is never removed from the graph.
- Or use **add_node** / **insert_step_between** under a misread "remove" intent.

We need this to work in **all** cases: single "remove step X", "delete step X", mixed requests (add + remove), and in any process.

## Goals

- For any request to **delete** or **remove** a step (by name or id), the plan must include **delete_node(id)** for that step.
- The plan must **not** implement removal by only delete_edge + add_edge (no delete_node).
- Validation should reject plans that delete edges to/from a step but do not delete that step (forcing correct use of delete_node).

## Changes

### 1. Prompt: remove/delete step → delete_node only, no manual rewiring

**File:** [backend/agent/prompt.py](backend/agent/prompt.py)

- **delete_node bullet (tool_guidance):** State explicitly: When the user says "delete step X", "remove step X", or "drop step X", use **delete_node(id)** only. Resolve the step by name in the full graph to get its id. **Do not** use delete_edge + add_edge to remove a step; the store reconnects edges automatically when you call delete_node. A single delete_node step is sufficient.
- **Add a constraint** (or fold into existing): When the user asks to remove or delete a step, you **must** include **delete_node(id)** for that step. Do not simulate removal with only delete_edge and add_edge.
- **Common_mistakes:** Add or sharpen: Using **delete_edge** and **add_edge** (without **delete_node**) when the user asked to remove or delete a step — use **delete_node(id)** only; edges are reconnected automatically.
- **Examples:** Ensure at least one "Delete step X" (by name) example that shows only delete_node. Optionally add "Remove the step Verify Prescription" in process S1 → delete_node(P1.2) only.
- **Claude variant:** Mirror the same delete_node-only rule and common_mistake.

### 2. Validation: require delete_node when plan deletes edges to/from a step

**File:** [backend/agent/runtime_nova.py](backend/agent/runtime_nova.py)

- In **`_validate_plan_steps`**, after existing checks:
  - Collect all step/decision node ids that appear as **source** or **target** of any **delete_edge** in the plan. Use a simple heuristic for step/decision ids: match `P<n>.<k>` or `G<n>.<k>` (e.g. `re.match(r"^[PG]\d+\.\d+$", id)`), and exclude `_start` / `_end`.
  - Collect all node ids that are the target of **delete_node** in the plan.
  - For each step/decision id X that appears in a delete_edge (as source or target): if X is **not** in the delete_node targets set, return a validation error, e.g. `"To remove a step, use delete_node(id). The plan deletes an edge involving step/decision {X} but does not delete that node. Use delete_node({X}) instead of (or in addition to) delete_edge/add_edge; edges are reconnected automatically."`
- This ensures: if the planner tries to "remove" a step by only rewiring (delete_edge + add_edge), the plan is rejected and the user sees a clear message. Plans that correctly use delete_node (e.g. "turn step into subprocess" which ends with delete_node(step)) continue to validate.

### 3. Tool description (optional)

**File:** [backend/agent/tools.py](backend/agent/tools.py)

- In the **delete_node** tool description, add: "Use this when the user asks to remove or delete a step; do not use only delete_edge and add_edge — delete_node reconnects the flow automatically."

## Files to change

- [backend/agent/prompt.py](backend/agent/prompt.py): strengthen delete_node tool_guidance (single step, resolve by name, no delete_edge/add_edge for removal); add constraint; add common_mistake; ensure delete-by-name example; mirror in Claude variant.
- [backend/agent/runtime_nova.py](backend/agent/runtime_nova.py): in `_validate_plan_steps`, require that any step/decision id appearing in a delete_edge also appears in a delete_node.
- [backend/agent/tools.py](backend/agent/tools.py) (optional): extend delete_node description.

## Edge cases

- **Turn step into subprocess:** Plan has delete_edge(., step), delete_edge(step, .), … add_node(…), add_edge(…), **delete_node(step)**. So step is in delete_edge and in delete_node → validation passes.
- **Remove step only:** Plan should be delete_node(step). No delete_edge needed; validation passes.
- **Remove by rewiring only:** Plan has delete_edge(pred, step), add_edge(pred, succ) but no delete_node(step). Step is in delete_edge but not in delete_node targets → validation fails with clear message.
- **Mixed add + remove:** Plan has insert_step_between(…) and delete_node(step) → both validated as today; remove still must use delete_node.

## Verification

- "Remove the step Verify Prescription" → plan contains delete_node(P1.2) (or correct id); no delete_edge/add_edge used instead.
- "Delete step Receive Shipment in S2" → plan contains delete_node(P2.3) only (or delete_edge + delete_node + add_edge if reconnection is explicit; but store reconnects automatically, so delete_node only is correct).
- If a plan mistakenly has delete_edge(P1.1, P1.2), add_edge(P1.1, P1.3) and no delete_node(P1.2) → validation rejects with message to use delete_node(P1.2).

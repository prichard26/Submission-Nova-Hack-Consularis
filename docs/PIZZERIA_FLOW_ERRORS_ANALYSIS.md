# Pizzeria flow errors – analysis and fixes

## Summary

Two things are going wrong when building the pizzeria flow:

1. **Steps added without edges** – The planner adds nodes (P1.1, P1.2, …) but no edges, so those nodes are orphans and validation fails.
2. **Partial execution** – The “correct errors” plan runs many steps, but only a few execute (e.g. add_node, add_edge, add_edge). Later steps fail because edges require both endpoints to exist, and/or nodes already exist from a previous run.

---

## 1. Why “Orphan node P1.1 has no edges” (add detail)

**What happens**

- User asks to “add more detail to each step” (e.g. steps inside S1, S2, …).
- The planner proposes only **add_node** steps (P1.1, P1.2, P1.3, P2.1, …) and **no add_edge** steps.
- So nodes are created but never connected to each other or to start/end. Validation then reports orphans and “no incoming/outgoing edges”.

**Root cause**

- The planner is not following the rule that “when adding steps inside a subprocess, you must also add edges so that start → first → … → last → end”.
- The prompt already says to “add internal steps and edges in the same plan” ([backend/agent/prompt.py](backend/agent/prompt.py)), but the model still omits edges.

**Ways to fix it**

- **Prompt:** Make the rule explicit and add a small example:
  - “When adding steps inside a process (e.g. S1), you must add edges in the same plan: `add_edge(process_start, first_step)`, `add_edge(first_step, second_step)`, …, `add_edge(last_step, process_end)`. Without these edges, the steps are orphans and validation will fail.”
- **Validation retry:** The existing “plan validation retry” could include a hint when the failure is “orphan / no edges”: “Add edges so that every new step is connected: start → first step → … → last step → end.”
- **Normalization (optional):** If the planner often adds a sequence of steps in one process without edges, you could add a normalizer that, when it sees N consecutive add_node steps in the same process, inserts the corresponding add_edge steps (start→first, first→second, …, last→end). This is more invasive but would make many plans valid automatically.

Recommendation: strengthen the **prompt** and, if needed, add a **validation-retry** message that specifically tells the model to add the missing edges.

---

## 2. Why “Done. Executed: add_node, add_edge, add_edge” and validation still fails

**What happens**

- User says “correct errors”.
- The planner proposes a long plan: add_node(P1.1), add_node(P1.2), …, then add_edge(S1_start, P1.1), add_edge(P1.1, P1.2), ….
- Only three steps are reported as executed (e.g. add_node, add_edge, add_edge). The rest of the plan does not run, and validation still reports orphans and unreachable nodes.

**Why only three steps run**

Two main possibilities:

1. **Step order vs. add_edge requirements**  
   - `add_edge(source, target)` only succeeds if **both** `source` and `target` already exist **in the same process** ([backend/graph/store.py](backend/graph/store.py) – `_resolve_edge_graph()` requires both in `graph.all_step_ids()`).
   - If the plan orders steps as: add_node(P1.1), add_edge(S1_start, P1.1), add_edge(P1.1, P1.2), add_node(P1.2), …, then the third step add_edge(P1.1, P1.2) runs **before** P1.2 exists, so it fails. Execution then stops (or retries and eventually stops), and you see only the first two steps (add_node, add_edge) or a few more depending on order.

2. **Nodes already exist**  
   - If an earlier run already created P1.1, P1.2, P1.3 (e.g. the “add detail” run without edges), then a later “correct errors” plan that starts with add_node(P1.1) will get “id already exists” ([backend/graph/store.py](backend/graph/store.py) around line 890–891: `if explicit_id in graph.all_step_ids(): return None`). So the first add_node fails and the rest of the plan may never run or only partially run.

So “Executed: add_node, add_edge, add_edge” is consistent with: (a) plan order that runs an add_edge before the target node exists (so execution fails at that step), or (b) an earlier add_node failing because the node already exists, with some steps still running depending on how the executor/retry works.

**Ways to fix it**

- **Planner must order steps so that nodes exist before edges:**  
  For each process, emit all add_node steps for that process first, then all add_edge steps for that process (or at least: for every add_edge(A, B), both add_node(A) and add_node(B) must appear earlier in the plan if A and B are normal steps). The prompt should state this clearly.
- **Idempotent add_node (optional):**  
  If the node already exists, add_node could no-op and return success instead of failure, so re-running a “correct errors” plan doesn’t fail on the first add_node. This avoids partial execution when the user retries after a previous run that already created some nodes.
- **Executor / retry:**  
  Ensure that when a step fails (e.g. add_edge because target missing, or add_node because id exists), the error message is clear and, if you have replan/retry, that the planner is given “add nodes before edges” and “do not re-add existing nodes” (or “add_node is idempotent”) so the next plan is valid.

Recommendation: (1) **Prompt**: require “For each process, add all new nodes first, then add all edges between them and to start/end.” (2) Optionally make **add_node** idempotent when the node already exists, so “correct errors” can be re-run safely.

---

## Checklist for implementation

- [ ] **Prompt (planner):** When adding steps inside a process, require that the plan includes add_edge steps so that start → first → … → last → end; add a short example.
- [ ] **Prompt (planner):** Require that in the plan, for each process, all add_node steps for that process appear before any add_edge that uses those nodes.
- [ ] **Validation retry:** When validation fails with “orphan” or “no incoming/outgoing edges”, include a hint in the retry message: “Add edges so that every new step is connected: start → first → … → last → end.”
- [ ] **Optional – backend:** Make add_node idempotent when the node id already exists (return success and existing node instead of None).

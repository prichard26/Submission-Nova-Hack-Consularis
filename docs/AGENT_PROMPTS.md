# Aurelius agent — tools and test prompts

**The agent has exactly 8 tools.** No other tools exist.

| # | Tool | Args |
|---|------|------|
| 1 | **get_graph_summary** | `process_id?` (optional; use for other process e.g. Process_P1) |
| 2 | **resolve_step** | `name_or_fragment` |
| 3 | **update_node** | `node_id`, `updates` (name, actor, duration_min, cost, etc.; use units) |
| 4 | **add_node** | `phase_id`, `step_data` (name, type: step\|decision\|subprocess) |
| 5 | **delete_node** | `node_id` (removes step, decision, or subprocess node) |
| 6 | **add_edge** | `source`, `target`, `label?`, `condition?` |
| 7 | **delete_edge** | `source`, `target` |
| 8 | **create_subprocess_page** | `node_id`, `name?` (create new process page for a subprocess node) |

- **Decisions**: Add with add_node(..., type: "decision"); delete with delete_node. Connect branches with add_edge(..., label="Yes"/"No").
- **Subprocess (call box)**: Add with add_node(..., type: "subprocess"); delete with delete_node.
- **New process page**: create_subprocess_page(node_id) creates a new process linked to a subprocess node (node must have type "subprocess").

---

## Test prompts (by tool)

**Context:** Open Prescription (Process_P1). Steps: P1.1 Prescribe Medication, P1.2 Verify Prescription, P1.3 Approve Prescription.

### 1. get_graph_summary
- For the **current** process the agent already has the data in the "Graph:" context—it should answer without calling get_graph_summary (e.g. "This process has…" / "Verify Prescription is step P1.2…").
- *"List the steps in the Prescription process."* — When on global map, agent calls get_graph_summary(process_id="Process_P1") and then explains the result in a few sentences.

### 2. resolve_step
- For the current process, step/phase IDs are in the Graph context—agent uses that and does **not** call resolve_step for "Where is X?" or "What's the id for P1.2?".
- resolve_step is used when the name isn't in the Graph or when mutating (update_node, add_edge, etc.) and the step isn't listed.

### 3. update_node
- *"Rename 'Verify Prescription' to 'Pharmacist verification'."*
- *"Set actor of 'Prescribe Medication' to 'Physician' and duration to 10 min."*
- *"Set cost to 9 EUR and error rate 2.8% for P1.1."*

### 4. add_node
- *"Add a step 'Compliance check' in the Prescription lane."* (type: step)
- *"Add a decision 'Eligibility OK?' in the Prescription lane."* (type: decision)
- *"Add a subprocess 'Quality check'."* (type: subprocess)

### 5. delete_node
- *"Delete the step 'Approve Prescription'."* (same for decisions and subprocess nodes; reconnect flow with add_edge)

### 8. create_subprocess_page
- *"Create a new page for the Quality check subprocess."* / *"Expand this subprocess."* — node_id must be a step with type "subprocess".

### 6. add_edge
- *"Add a flow from 'Verify Prescription' to 'Approve Prescription'."*

### 7. delete_edge
- *"Remove the flow between Prescribe Medication and Verify Prescription."*

### Multi-tool (add step in flow)
- *"Between 'Prescribe Medication' and 'Verify Prescription' add a step 'Intake check' and connect the flow."*  
  → add_node, delete_edge(P1.1, P1.2), add_edge(P1.1, new), add_edge(new, P1.2).

---

## Low-level prompts (single tool or very specific)

Try these when the process is already open; the agent should do one clear thing.

- *"What's the id of Verify Prescription?"*
- *"Set duration of P1.2 to 15 min."*
- *"Set cost of Approve Prescription to 5 EUR."*
- *"Rename P1.1 to 'Prescribe medication order'."*
- *"Add a step 'Document in EHR' in the Prescription lane."*
- *"Add a decision 'Controlled substance?' in Prescription."*
- *"Remove the flow from Prescribe Medication to Verify Prescription."*
- *"Delete the step Approve Prescription."* (agent should reconnect P1.2 → End or next step)
- *"Connect P1.1 to P1.3."* (add edge; may already exist)

---

## Middle-level prompts (multi-step or one clear intent)

Agent should do several tool calls in one turn or interpret one sentence into a small sequence.

- *"Between Prescribe Medication and Verify Prescription add a step 'Check drug interactions' and connect the flow."*
- *"Add a decision 'Patient eligible?' after Prescribe Medication, then connect Yes to Verify Prescription and No to a new step 'Reject and notify'."*
- *"Rename Verify Prescription to 'Pharmacist verification' and set its duration to 12 min."*
- *"Add a subprocess 'External validation' after Approve Prescription and connect it to End."*
- *"Remove the step Verify Prescription and connect Prescribe Medication directly to Approve Prescription."*
- *"List the steps in the Dispensing process."* (on global map → get_graph_summary(Process_P5) and answer)
- *"What's in the Storage and Storage Management process?"* (on global → get_graph_summary(Process_P3))
- *"Add a step 'Final sign-off' at the end of the Prescription lane, after Approve Prescription."*
- *"Set actor to 'Pharmacist' and duration to 8 min for Verify Prescription; set cost to 6 EUR for Approve Prescription."*

---

## High-level prompts (vague, discovery, or many steps)

See how the agent clarifies, plans, or applies many changes.

- *"We want to add a quality gate before approval."*  
  → Agent may ask where, or add a step between Verify and Approve.

- *"Map our prescription flow from doctor to pharmacy."*  
  → May list current steps and ask what to add/change, or suggest refinements.

- *"Add a branch: if the prescription is for a controlled substance, we do an extra check."*  
  → Add decision + new step + edges with labels.

- *"Simplify the Prescription process: remove the verification step."*  
  → delete_node(Verify), add_edge(Prescribe, Approve).

- *"Make sure every step in Prescription has an actor and a duration; use 5 min where missing."*  
  → get_graph_summary / Graph, then multiple update_node calls.

- *"Create a new subprocess for 'Compliance review' and give it its own page."*  
  → add_node(type: subprocess), then create_subprocess_page(node_id).

- *"What processes do we have and what's in each?"*  
  → On global: list from Graph/Subprocesses; may call get_graph_summary for each or summarize.

- *"Our process is wrong: after prescribe we do intake, then verification, then approval."*  
  → Reorder: add Intake if missing, ensure edges Prescribe → Intake → Verify → Approve.

- *"Add a decision after verification: if OK go to approval, if not go to a new step 'Escalate to senior'."*  
  → add_node(decision), add_node(step), delete_edge(Verify, Approve), add_edge(Verify, decision), add_edge(decision, Approve, label Yes?), add_edge(decision, Escalate, label No?), add_edge(Escalate, …).

---

After structural changes the frontend auto-arranges when `meta.structural_change` is true.

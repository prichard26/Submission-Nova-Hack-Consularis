# Aurelius agent — step-by-step

We improve the model step by step. Each step adds capability.

---

## Step 1: Read the graph and dialogue (no tools)

**Goal:** The agent can read the process map and talk with the user about it. It cannot add, change, or delete anything.

**No tools.** The agent receives the **full graph** in its system message every time: every process (global map + all subprocesses) with phases, steps (id, name, actor, duration, cost), and edges. It answers only from that context.

**Expected behaviour:**
- Answers "What's in Prescription?", "List the steps in Dispensing", "Where is X?", "What processes do we have?" from the graph data in context.
- Replies in clear sentences (and may use markdown). Does not call any tool.
- Asks the user questions when useful (who does what, how long, variations).
- If the user asks to add/rename/delete something, the agent says it can only read and discuss in this step.

---

### Test questions for Step 1 (high → low level)

**High level (overview, discovery, vague)**

- *"What process are we looking at?"*
- *"Give me an overview of what we have here."*
- *"What's the big picture?"*
- *"How does this process work?"*
- *"What processes do we have in this workspace?"* (when on global map)
- *"Walk me through the whole thing."*
- *"I'm new—what am I looking at?"*
- *"Summarise this for a stakeholder."*

**Middle level (one process or flow)**

- *"What are the steps in the Prescription process?"* (on global: agent should use get_graph_summary(Process_P1) and answer)
- *"List the steps in Dispensing."* (on global → Process_P5)
- *"What's in Storage and Storage Management?"* (on global → Process_P3)
- *"What's the flow in this process?"* (current process: from Graph)
- *"How many steps are there?"*
- *"What phases do we have?"*
- *"What comes after Prescribe Medication?"*
- *"What comes before Approve Prescription?"*
- *"Which step has the longest duration?"*
- *"Which steps have a cost set?"*

**Low level (single step or ID)**

- *"Where is Verify Prescription?"*
- *"What's the id for Verify Prescription?"*
- *"What step is P1.2?"*
- *"What is P1.1?"*
- *"Who performs Prescribe Medication?"* (from Graph: actor)
- *"How long does Verify Prescription take?"* (from Graph: duration_min)
- *"What does Approve Prescription cost?"* (from Graph: cost_per_execution)
- *"Find the step called 'Approve Prescription'."*

**Dialogue / clarification**

- *"Hi."* → Agent should greet and ask what they want to know.
- *"I'm not sure what I need."* → Agent can suggest: overview, list steps, or ask about a specific process.
- *"Tell me about the Prescription process."* → get_graph_summary(Process_P1) and describe.

**Requests that should be declined (Step 1 cannot edit)**

- *"Add a step called Compliance check."* → Agent says it can only read and discuss.
- *"Rename Verify Prescription to Pharmacist verification."* → Same.
- *"Delete the Approve Prescription step."* → Same.
- *"Connect P1.1 to P1.3."* → Same.

---

## Step 2: Read the graph, dialogue, and edit steps

**Goal:** Same as Step 1, plus the agent can **modify one or more steps (nodes)** when the user asks. It can update everything inside each node: name, actor, duration, description, inputs, outputs, risks, cost, automation fields, etc. It does not add/delete steps, edges, or lanes.

**Tool (1):**

| # | Tool | Purpose |
|---|------|--------|
| 1 | **update_node** | Update a step. Arguments: `process_id` (optional), `step_id` (e.g. P1.1), `updates` (object with name, actor, duration_min, description, inputs, outputs, risks, cost_per_execution, etc.). Call multiple times per turn to update multiple steps. |

The agent still receives the **full graph** in context every time (all processes, any depth). It uses that to find the right step_id and process_id, then calls update_node for each step to change (one or more per turn).

**What it can do in Step 2:**
- Everything from Step 1: read the full graph, answer questions, ask clarifying questions, use markdown.
- **Edit one or more steps per turn:** change any step’s name, actor, duration, description, inputs, outputs, risks, cost, automation fields, SLA, pain points, etc. (all fields inside the node). Can update multiple steps in a single turn.
- It does **not** add or delete steps, edges, or lanes; it does not create subprocesses.

**Expected behaviour:**
- Same read/dialogue as Step 1.
- When the user asks to change something about one or more steps, the agent calls update_node for each step to update, with the correct step_id and process_id from the graph.
- If the user asks to add/delete steps or edges, the agent says it can only edit existing steps in this step.

---

### Possible prompts for Step 2

**Read / dialogue (same as Step 1 — no tool)**

- *"What's in the Prescription process?"*
- *"Who does Verify Prescription?"*
- *"List the steps in Dispensing."*
- *"What's the flow in this process?"*

**Edit step(s) — name**

- *"Rename Verify Prescription to Pharmacist verification."*
- *"Change the name of P1.2 to Prescription check."*
- *"Call the first step 'Receive request' instead."*

**Edit step(s) — actor / who**

- *"Set the actor of Verify Prescription to Pharmacist."*
- *"P1.1 should be performed by the doctor."*
- *"Who does Approve Prescription? Set it to Senior pharmacist."*
- *"Set the actor to Pharmacist for both Verify Prescription and Approve Prescription."*

**Edit step(s) — duration / time**

- *"Set the duration of Verify Prescription to 5 minutes."*
- *"Change P1.2 to 10 minutes."*
- *"How long is Approve Prescription? Make it 3 minutes."*
- *"Set duration to 5 min for P1.1, P1.2, and P1.3."*

**Edit step(s) — description**

- *"Add a description to Verify Prescription: the pharmacist checks the prescription for validity and dosage."*
- *"Update the description of P1.1."*

**Edit step(s) — inputs / outputs / risks**

- *"Add 'prescription' to the inputs of Approve Prescription."*
- *"Set the outputs of P1.2 to approved prescription, rejection reason."*
- *"Add a risk to Verify Prescription: wrong dosage if not checked."*
- *"What are the risks of P1.1? Add 'missing signature'."*

**Edit step(s) — cost / volume / automation**

- *"Set the cost of Approve Prescription to 2.50."*
- *"Change cost_per_execution of P1.2 to 3."*
- *"Set annual_volume for Verify Prescription to 50000."*
- *"Set automation_potential of P1.1 to high."*
- *"Set cost to 2 EUR for all three steps in Prescription."*

**Edit step(s) — other metadata**

- *"Set the SLA for Verify Prescription to 24 hours."*
- *"Add 'legacy system' to current_systems for P1.2."*
- *"Set data_format of Approve Prescription to PDF."*

**Requests that should be declined in Step 2 (no add/delete steps, no edges, no subprocesses)**

- *"Add a new step called Compliance check."* → Agent says it can only edit existing steps (and in Step 3, edges).
- *"Delete the Approve Prescription step."* → Same.
- *"Create a subprocess for this."* → Same.

---

## Step 3: Read, dialogue, edit steps, and edit edges

**Goal:** Same as Step 2, plus the agent can **add, delete, and update edges** (connections between steps). When the agent adds, deletes, or updates an edge, the frontend auto-arranges the graph.

**Tools (in addition to update_node):**

| # | Tool | Purpose |
|---|------|--------|
| 1 | **add_edge** | Add a connection between two steps. Arguments: `process_id` (optional), `source` (step id), `target` (step id), optional `label`. If the edge already exists, it is updated. |
| 2 | **delete_edge** | Remove the edge from source step to target step. Arguments: `process_id` (optional), `source`, `target`. |
| 3 | **update_edge** | Update an existing edge's label or condition. Arguments: `process_id` (optional), `source`, `target`, `updates` (object with label, condition). |

**What it can do in Step 3:**
- Everything from Step 1 and 2 (read, dialogue, edit one or more steps).
- **Add an edge:** connect step A to step B (e.g. "Connect P1.1 to P1.3").
- **Delete an edge:** remove the connection between two steps.
- **Update an edge:** change an edge's label or condition.
- The frontend **auto-arranges** the canvas after any add_edge, delete_edge, or update_edge so the layout stays readable.
- It does **not** add or delete steps/lanes in Step 3 (Step 4 adds that).

**Possible prompts for Step 3 (edges)**

- *"Connect P1.1 to P1.3."* / *"Add an edge from P1.1 to P1.3."*
- *"Remove the connection between Verify Prescription and Approve Prescription."*
- *"Delete the edge from P1.2 to P1.3."*
- *"Change the label on the edge from P1.1 to P1.2 to 'Submitted'."*
- *"Add a connection from Start to P1.2 as well."* (multiple edges from one step are allowed)

---

## Step 4: Add and delete nodes and decisions

**Goal:** Same as Step 3, plus the agent can **add new steps or decisions** and **delete existing steps or decisions**. It uses the same graph context to choose the right lane_id and process_id.

**Tools (in addition to update_node and edge tools):**

| # | Tool | Purpose |
|---|------|--------|
| 1 | **add_node** | Add a new step or decision. Arguments: `process_id` (optional), `lane_id` (e.g. P1 from the graph), `name`, `type` ("step" or "decision"). |
| 2 | **delete_node** | Remove a step or decision. Arguments: `process_id` (optional), `node_id` (step id, e.g. P1.2). Cannot delete start or end nodes. |

**What it can do in Step 4:**
- Everything from Step 1–3 (read, dialogue, edit steps, add/delete/update edges).
- **Add a step or decision:** e.g. "Add a step called Compliance check after P1.2" → add_node with lane_id from the process, name, and type "step" or "decision". Then add edges to connect it.
- **Delete a step or decision:** e.g. "Remove the step P1.2" → delete_node with that node_id. Start and end cannot be deleted.
- It does **not** create subprocesses or add/delete lanes.

**Possible prompts for Step 4 (nodes and decisions)**

- *"Add a step called Compliance check."*
- *"Add a decision node: Approved or Rejected."*
- *"Add a new step after Verify Prescription called Double-check."*
- *"Remove the step P1.2."* / *"Delete the Approve Prescription step."*
- *"Delete the decision node P2.2."*

---


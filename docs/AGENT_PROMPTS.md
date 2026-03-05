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

**Requests that should be declined in Step 2 (no add/delete/structure)**

- *"Add a new step called Compliance check."* → Agent says it can only edit existing steps.
- *"Delete the Approve Prescription step."* → Same.
- *"Connect P1.1 to P1.3."* / *"Add an edge from P1.1 to P1.3."* → Same.
- *"Create a subprocess for this."* → Same.

---


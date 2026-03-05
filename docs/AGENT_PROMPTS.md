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

## Next steps (later)

- **Step 2:** Add tools to edit the graph (update_node, add_node, delete_node, add_edge, delete_edge).
- **Step 3:** Add decisions, subprocess, create_subprocess_page.
- **Step 4:** Discovery and initial questions (company size, etc.) with edit capability.

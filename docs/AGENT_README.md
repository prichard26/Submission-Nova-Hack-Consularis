# Agent (Aurelius) – User Guide

The Consularis agent (**Aurelius**) is a process consul that helps you refine your process graphs through natural conversation. You describe what you want in plain language; the agent applies the changes to the JSON-native graph and confirms what it did.

---

## How to use the agent

1. **Open a session** (e.g. your company or project name). The app loads a baseline process graph for that session.
2. **Chat with Aurelius** in the chat panel. Say what you want to change, add, or remove.
3. **Refer to steps and phases by name.** You do not need to know or type step IDs (like `P1.2`). For example:
   - *"Set the duration of Verify Prescription to 5 minutes"*
   - *"Rename the Distribution phase to Order Fulfillment"*
   - *"Remove the link between Prescribe Medication and Verify Prescription"*
4. **Describe your organization or process.** The agent can adapt the graph to match: add steps, rename phases, reconnect flows, or create new subprocesses.

The agent resolves step and phase names to the underlying graph IDs itself. If your request is ambiguous, it will ask for clarification instead of guessing.

---

## What the agent can do

The agent can read and modify every part of your process graph (JSON-native, with BPMN export available). Capabilities are grouped below.

### Inspect and navigate

| Capability | What you can say (examples) |
|------------|-----------------------------|
| **View the graph** | "Show me the process", "What steps are in Prescription?" |
| **See step details** | "What does Verify Prescription do?", "Who is responsible for Dispensing?" |
| **List links** | "What comes after Prescribe Medication?", "Which steps connect to Storage?" |
| **Switch process** | "Open the Prescription subprocess", "Go back to the global map" |
| **List processes** | "What subprocesses exist?" |

The agent has access to a summary that includes step names, actors, and durations, so it can answer questions like "Which steps take the longest?" or "What does the pharmacist do?" without you specifying IDs.

### Steps (tasks)

| Capability | What you can say (examples) |
|------------|-----------------------------|
| **Change step data** | "Set Verify Prescription duration to 5 min", "Make the actor for P1.1 the Doctor", "Add a risk to Dispensing: stock-out" |
| **Rename a step** | "Rename Verify Prescription to Check Prescription" |
| **Add a step** | "Add a step in Prescription: Pharmacist review, 3 minutes" |
| **Remove a step** | "Remove the Approve Prescription step", "Delete step P1.3" |

Step metadata includes:

- **Core**: name, actor, duration, description, inputs, outputs, risks, automation potential, automation notes
- **Operational**: current state, frequency, annual volume, error rate, cost per execution, current systems, data format, external dependencies, regulatory constraints, SLA target, pain points

### Links (edges)

| Capability | What you can say (examples) |
|------------|-----------------------------|
| **Add a link** | "Connect Prescribe Medication to Verify Prescription", "Add a link from Storage to Dispensing with label In stock" |
| **Remove a link** | "Remove the link between P1.1 and P1.2", "Disconnect Verify from Approve" |
| **Change link label or condition** | "Rename the link between P2 and P3 to Standard flow", "Set the condition on the link to If approved" |
| **Reconnect** | "Move the link from Verify Prescription so it goes to Dispensing instead of Approve" |

### Phases (lanes)

| Capability | What you can say (examples) |
|------------|-----------------------------|
| **Add a phase** | "Add a new phase called Quality Control" |
| **Rename a phase** | "Rename Distribution to Order Fulfillment", "Change the Prescription phase name to Receipt of prescription" |
| **Delete a phase** | "Remove the Monitoring phase" (removes the phase and all its steps) |
| **Reorder phases** | "Put Prescription before Storage in the list" |
| **Move a step** | "Move Verify Prescription into the Distribution phase", "Put step P1.2 in phase P2" |
| **Reorder steps in a phase** | "In Prescription, put Approve before Verify" |

### Process and hierarchy

| Capability | What you can say (examples) |
|------------|-----------------------------|
| **Rename the process** | "Rename this process to Hospital medication circuit" |
| **Create a subprocess** | "Add a subprocess called Detailed dispensing", "Create a child process under Distribution" |
| **Navigate processes** | "Go into the Prescription subprocess", "Switch to the global map" |
| **List processes** | "What subprocesses are available?", "Show me the process tree" |

When you have multiple processes (e.g. a global map and phase subprocesses), you can navigate between them and the agent will work in the current process context.

### Other

| Capability | What you can say (examples) |
|------------|-----------------------------|
| **Validate** | "Check the graph for errors", "Validate the process" |

---

## How it works (brief)

- The agent receives a **graph summary** (phases, steps with names, actors, durations, costs, error rates, automation levels) so it knows the current state.
- When you refer to something by **name**, the agent uses an internal **resolve** step to map that name to the correct step or phase ID, then calls the right tool.
- All changes are made through **tools** that update the in-memory JSON graph; each mutation is persisted to SQLite and the API returns updated graph JSON so the React Flow canvas stays in sync.

For technical details (store, DB schema, API), see [GRAPH_STRUCTURE.md](GRAPH_STRUCTURE.md).

---

## Tips

- **Be specific when several steps match.** "Set duration of Verify Prescription to 5 min" is clearer than "Set duration to 5 min" if multiple steps could apply.
- **One change per request** is easier to track; for many changes, you can send several messages or list them clearly.
- **Hierarchy:** If you use a global map with subprocesses, say which process you mean when it matters (e.g. "In the Prescription subprocess, add a step…").

---

## Related docs

| Document | Content |
|----------|---------|
| [README.md](README.md) | Docs index and links. |
| [GRAPH_STRUCTURE.md](GRAPH_STRUCTURE.md) | JSON-native format, hierarchical model, SQLite schema, API contracts. |
| [DATA_FLOW.md](DATA_FLOW.md) | Backend module map, state ownership, request paths. |
| [backend/README.md](../backend/README.md) | Backend layout and run instructions. |

# Consularis documentation

This folder holds architecture and reference docs for the Consularis Nova Hack MVP. For quick start and run instructions, see the [root README](../README.md).

## Docs index

| Document | Purpose |
|----------|---------|
| [AGENT_README.md](AGENT_README.md) | **How to use the agent (Aurelius):** what you can ask, no need for step IDs, full list of capabilities with example phrases. |
| [DATA_FLOW.md](DATA_FLOW.md) | Data flow and ownership: where graph and chat state live, request path, backend structure (main, config, storage, graph_store, agent). |
| [GRAPH_STRUCTURE.md](GRAPH_STRUCTURE.md) | BPMN 2.0 as canonical format: XML structure, in-memory model (BpmnModel), lanes/tasks/flows, extension elements, validation, API contracts. |
| [GRAPH_OPERATIONS_VERIFICATION.md](GRAPH_OPERATIONS_VERIFICATION.md) | Post–BPMN migration verification: backend operation surface, agent tools, API responses, frontend behavior (Process + BPMN views). |
| [PHARMACY_BPMN_REVIEW.md](PHARMACY_BPMN_REVIEW.md) | Review of the pharmacy circuit BPMN: what works, connection issues (e.g. P3.2, P5.3), and suggested fixes. |
| [GIT_BASICS.md](GIT_BASICS.md) | Git basics: branches, pull, push, team flow. |
| [HACKATHON_RULES.md](HACKATHON_RULES.md) | Amazon Nova AI Hackathon rules summary (dates, eligibility, requirements, submission, judging, prizes). |

## Backend and frontend READMEs

- **[backend/README.md](../backend/README.md)** — Backend structure (routers, services, agent, bpmn, storage), run instructions, conventions.
- **[frontend/README.md](../frontend/README.md)** — Frontend stack, routes, data flow, project structure.

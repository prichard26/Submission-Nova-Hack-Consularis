# Consularis documentation

This folder holds architecture and reference docs for the Consularis Nova Hack MVP. For quick start and run instructions, see the [root README](../README.md).

## Docs index

| Document | Purpose |
|----------|---------|
| [AGENT_README.md](AGENT_README.md) | **How to use the agent (Aurelius):** what you can ask, no step IDs needed, full list of capabilities with example phrases. |
| [DATA_FLOW.md](DATA_FLOW.md) | Data flow and ownership: where graph and chat state live (SQLite), request path, backend module map. |
| [GRAPH_STRUCTURE.md](GRAPH_STRUCTURE.md) | BPMN 2.0 hierarchical model: process tree, registry, SQLite persistence, extension metadata, in-memory cache, API contracts. |

## Backend and frontend READMEs

- **[backend/README.md](../backend/README.md)** — Backend structure, run instructions, conventions.
- **[frontend/README.md](../frontend/README.md)** — Frontend stack, routes, data flow, project structure.

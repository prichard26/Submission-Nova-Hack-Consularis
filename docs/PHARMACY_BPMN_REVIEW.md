# Pharmacy circuit BPMN – review and status

This document records the review of the pharmacy medication circuit BPMN model and tracks which structural issues have been resolved during the hierarchical refactor.

## Current structure

The pharmacy circuit is now modeled as a **hierarchical process tree** (see [GRAPH_STRUCTURE.md](GRAPH_STRUCTURE.md)):

- **global.bpmn** — Root process with call activities linking to 7 subprocesses.
- **P1.bpmn – P7.bpmn** — Individual subprocess files, each with its own start/end events, tasks, gateways, and intra-phase sequence flows.
- **registry.json** — Process tree metadata (ids, names, parent-child, ownership, criticality).

The old monolithic `pharmacy_circuit.bpmn` has been archived to `backend/data/archive/`.

## What works well

- **Phases (lanes)** match the medication circuit: Prescription, Selection/Acquisition, Storage, Distribution, Dispensing, Administration, Monitoring/Waste.
- **Tasks** have clear names, actors, risks, and 19 extension metadata fields including operational data (frequency, annual volume, error rates, costs, systems, SLA targets, pain points).
- **Process hierarchy** allows drill-down from global overview to individual subprocess detail.
- **Each subprocess** is self-contained with proper start/end events and internal flow.

## Issues resolved during refactor

| Issue | Status | What was done |
|-------|--------|---------------|
| **P1: Phantom `Start_1` node** rendered as task | Fixed | Removed `Start_1` and its flows/DI; `Start_P1` now flows directly to `P1.1`. |
| **P7: Phantom `End_1` node** and disconnected `P7.1` | Fixed | Removed `End_1` and its flows/DI; added `flow_P7.1_P7.2` to connect the chain; `P7.3` now targets `End_P7`. |
| **P3: Generic exit label** on gateway `G3` | Fixed | Flow label changed from "Complete" to "Phase complete". |
| **Extension metadata was sparse** (only actor, duration, risks) | Fixed | Added 11 operational data fields to all 21 tasks across P1-P7. |
| **No process hierarchy or registry** | Fixed | Created `global.bpmn` with call activities, individual `P1-P7.bpmn` files, and `registry.json`. |

## Known limitations (by design)

These are architectural choices, not bugs:

- **Cross-phase flows** (e.g. in-stock shortcut from P2 to P5) are modeled as call activity connections in the global map rather than direct task-to-task flows across subprocess boundaries. This keeps each subprocess self-contained.
- **Inpatient path visual order** (P5 → P4) reflects the real process where dispensing happens before distribution for inpatients. The visual lane order differs from the flow direction — this is intentional and documented in flow labels.
- **In-memory SQLite**: Data is ephemeral by design for the MVP. Each restart reloads from baseline files.

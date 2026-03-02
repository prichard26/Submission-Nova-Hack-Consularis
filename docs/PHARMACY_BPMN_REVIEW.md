# Pharmacy circuit – model review and status

This document records the review of the pharmacy medication circuit model and tracks which structural issues have been resolved. The stack is now **JSON-native**: graphs are stored and edited as JSON; BPMN XML is generated on demand for download only.

## Current structure

The pharmacy circuit is modeled as a **hierarchical process tree** (see [GRAPH_STRUCTURE.md](GRAPH_STRUCTURE.md)):

- **workspace.json** — Process tree metadata (root, process ids, names, children, graph_file paths).
- **graphs/global.json** — Root process with subprocess steps (call activities) linking to P1–P7.
- **graphs/P1.json – P7.json** — Individual subprocess JSON documents (lanes, steps, flows, metadata).

The canonical format is JSON; BPMN export is available via the API for download compatibility.

## What works well

- **Phases (lanes)** match the medication circuit: Prescription, Selection/Acquisition, Storage, Distribution, Dispensing, Administration, Monitoring/Waste.
- **Steps** have clear names, actors, risks, and 19 metadata fields including operational data (frequency, annual volume, error rates, costs, systems, SLA targets, pain points).
- **Process hierarchy** allows drill-down from global overview to individual subprocess detail.
- **Each subprocess** is self-contained with proper start/end events and internal flow.

## Issues resolved during refactor

| Issue | Status | What was done |
|-------|--------|---------------|
| **P1: Phantom start node** rendered as task | Fixed | Start_P1 flows directly to P1.1. |
| **P7: Phantom end node** and disconnected steps | Fixed | Flow chain corrected; P7.3 targets End_P7. |
| **P3: Generic exit label** on gateway | Fixed | Flow label changed to "Phase complete". |
| **Extension metadata was sparse** | Fixed | Full set of operational data fields on tasks across P1–P7. |
| **No process hierarchy** | Fixed | workspace.json + global.json with subprocess steps; P1–P7 as separate JSON graphs. |

## Known limitations (by design)

- **Cross-phase flows** (e.g. in-stock shortcut from P2 to P5) are modeled as subprocess call activities in the global map rather than direct task-to-task flows across subprocess boundaries.
- **Inpatient path visual order** (P5 → P4) reflects the real process where dispensing happens before distribution for inpatients.
- **In-memory SQLite**: Data is ephemeral by design for the MVP. Each restart reloads from baseline JSON files.

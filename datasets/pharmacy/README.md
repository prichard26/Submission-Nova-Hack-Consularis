# Pharmacy Process Datasets

Baseline pharmacy process flows for the Consularis agentic flow. The agent uses these as a starting point, then refines with user input to identify bottlenecks and automation opportunities.

## Files

| File | Description |
|------|-------------|
| `tohm_pharmacy_medication_circuit.json` | Full 7-phase medication circuit (TOHM + BPMN-derived): phases, steps, actors, durations, risks, automation potential, standards, bottlenecks, and flow connections |
| `pharmacy_flowchart_structure.json` | Graph-ready node/edge structure for rendering (Mermaid, React Flow, D3) with x/y positions and phase colors |
| `pharmacy_flowchart.mermaid` | Mermaid diagram source for the full circuit |
| `hospital_pharmacy_bpm_model.json` | BPM process model from academic literature (Biyout et al. 2018, CC-BY 4.0): procurement chain, SWOT, value chain, actor analysis |
| `sources.json` | All source references with URLs and licenses |

## How the agent uses this

1. **Load baseline** from `tohm_pharmacy_medication_circuit.json`
2. **Show flowchart** from `pharmacy_flowchart_structure.json` or `.mermaid`
3. **Ask user** to confirm/modify steps for their specific pharmacy
4. **Analyze bottlenecks** using `common_bottlenecks` + user input
5. **Recommend automation** using `automation_potential` and `automation_notes` per step
6. **Cross-reference** with `hospital_pharmacy_bpm_model.json` for SWOT and value chain context

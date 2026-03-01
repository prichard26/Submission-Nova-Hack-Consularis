"""Legacy-to-BPMN migration adapter."""
from __future__ import annotations

from bpmn.model import BpmnModel, default_extension, default_lane, default_sequence_flow, default_task


def legacy_to_model(legacy: dict) -> BpmnModel:
    """Build BpmnModel from legacy { phases, flow_connections } (for migration)."""
    phases = legacy.get("phases") or []
    flow_connections = legacy.get("flow_connections") or []
    lanes = []
    tasks = []
    for phase in phases:
        lane = default_lane(phase["id"], phase.get("name", ""), phase.get("description", ""))
        refs = []
        for step in phase.get("steps", []):
            refs.append(step["id"])
            ext = default_extension()
            ext["actor"] = step.get("actor", "")
            ext["duration_min"] = step.get("duration_min", "—")
            ext["description"] = step.get("description", "")
            ext["inputs"] = step.get("inputs") if isinstance(step.get("inputs"), list) else []
            ext["outputs"] = step.get("outputs") if isinstance(step.get("outputs"), list) else []
            ext["risks"] = step.get("risks") if isinstance(step.get("risks"), list) else []
            if step.get("automation_potential"):
                ext["automation_potential"] = step["automation_potential"]
            if step.get("automation_notes"):
                ext["automation_notes"] = step["automation_notes"]
            task = default_task(step["id"], step.get("name", ""), phase["id"])
            task["extension"] = ext
            tasks.append(task)
        lane["flow_node_refs"] = refs
        lanes.append(lane)
    flows = []
    for i, conn in enumerate(flow_connections):
        flow_id = conn.get("id") or f"flow_{conn['from']}_{conn['to']}_{i}"
        flows.append(default_sequence_flow(
            flow_id, conn["from"], conn["to"],
            conn.get("label", ""),
            conn.get("condition"),
        ))
    return BpmnModel(
        process_id="Process_Pharmacy",
        process_name="Pharmacy medication circuit",
        lanes=lanes,
        tasks=tasks,
        sequence_flows=flows,
    )

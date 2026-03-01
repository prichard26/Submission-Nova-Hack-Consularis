"""Session-scoped BPMN store: same API as graph_store, BPMN under the hood."""
from __future__ import annotations

from config import BASELINE_GRAPH_PATH
from bpmn.model import (
    BpmnModel,
    EXTENSION_KEYS,
    default_extension,
    default_sequence_flow,
    default_task,
)
from bpmn.layout import GAP_X, GAP_Y, LANE_HEIGHT, layout_bounds, TASK_HEIGHT, TASK_WIDTH
from bpmn.parser import parse_bpmn_xml
from bpmn.serializer import serialize_bpmn_xml

_sessions: dict[str, BpmnModel] = {}
_cached_baseline: BpmnModel | None = None


def init_baseline() -> None:
    """Load baseline BPMN once. Call from app lifespan."""
    global _cached_baseline
    if _cached_baseline is None:
        if not BASELINE_GRAPH_PATH.exists():
            raise FileNotFoundError(
                f"Baseline graph not found: {BASELINE_GRAPH_PATH}. "
                "Check BASELINE_GRAPH_PATH in backend/.env or ensure backend/data/pharmacy_circuit.bpmn exists."
            )
        _cached_baseline = parse_bpmn_xml(BASELINE_GRAPH_PATH)


def get_or_create_session(session_id: str) -> BpmnModel:
    if _cached_baseline is None:
        init_baseline()
    if session_id not in _sessions:
        _sessions[session_id] = _cached_baseline.copy()
    return _sessions[session_id]


def set_session(session_id: str, graph: BpmnModel | str) -> None:
    """Inject a graph for a session. graph can be BpmnModel or BPMN XML string."""
    if isinstance(graph, str):
        model = parse_bpmn_xml(graph)
    else:
        model = graph.copy()
    _sessions[session_id] = model


def get_bpmn_xml(session_id: str) -> str:
    """Return BPMN XML string for export."""
    model = get_or_create_session(session_id)
    return serialize_bpmn_xml(model)


def get_graph_json(session_id: str) -> dict:
    """Return the session graph as JSON for custom frontend renderers."""
    model = get_or_create_session(session_id)
    full_bounds = layout_bounds(model)
    bounds = {nid: (x, y) for nid, (x, y, _w, _h) in full_bounds.items()}
    task_by_id = {task["id"]: task for task in model.tasks}

    lanes = []
    y_offset = 0
    max_lane_steps = 1
    for lane in model.lanes:
        refs = lane.get("flow_node_refs", [])
        max_lane_steps = max(max_lane_steps, len(refs))
        lanes.append({
            "id": lane["id"],
            "name": lane.get("name", ""),
            "description": lane.get("description", ""),
            "flow_node_refs": refs,
            "y": y_offset,
        })
        y_offset += LANE_HEIGHT + GAP_Y

    nodes = []
    for lane in model.lanes:
        for task_id in lane.get("flow_node_refs", []):
            task = task_by_id.get(task_id)
            if not task:
                continue
            ext = task.get("extension") or {}
            x, y = bounds.get(task_id, (0, 0))
            node = {
                "id": task["id"],
                "label": task.get("name", task["id"]),
                "lane_id": task.get("lane_id", ""),
                "position": {"x": x, "y": y},
            }
            for key in EXTENSION_KEYS:
                node[key] = ext.get(key)
            nodes.append(node)

    edges = [
        {
            "id": flow.get("id", f"flow_{flow['source_ref']}_{flow['target_ref']}"),
            "source": flow["source_ref"],
            "target": flow["target_ref"],
            "label": flow.get("name", ""),
            "condition": flow.get("condition", ""),
        }
        for flow in model.sequence_flows
    ]

    return {
        "process_id": model.process_id,
        "process_name": model.process_name,
        "layout": {
            "task_width": TASK_WIDTH,
            "task_height": TASK_HEIGHT,
            "lane_height": LANE_HEIGHT,
            "gap_x": GAP_X,
            "max_lane_steps": max_lane_steps,
        },
        "lanes": lanes,
        "nodes": nodes,
        "edges": edges,
    }


def get_task_ids(session_id: str) -> set[str]:
    """Return all task ids for a session."""
    model = get_or_create_session(session_id)
    return model.task_ids()


def get_graph_summary(session_id: str) -> str:
    """Build a compact lane/step summary for LLM context."""
    model = get_or_create_session(session_id)
    task_by_id = {task["id"]: task for task in model.tasks}
    parts = []
    for lane in model.lanes:
        refs = lane.get("flow_node_refs", [])
        listed = [task_id for task_id in refs if task_id in task_by_id]
        parts.append(f"{lane['id']} {lane.get('name', '')}: {', '.join(listed)}")
    return " | ".join(parts)


def _dedupe_risks(risks: list) -> list:
    seen = set()
    out = []
    for r in risks:
        s = (r or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def get_node(session_id: str, node_id: str) -> dict | None:
    model = get_or_create_session(session_id)
    task = model.get_task(node_id)
    if not task:
        return None
    lane = model.get_lane(task["lane_id"]) if task.get("lane_id") else None
    ext = task.get("extension") or {}
    out = {
        "id": task["id"],
        "name": task.get("name", ""),
        "actor": ext.get("actor", ""),
        "duration_min": ext.get("duration_min", "—"),
        "description": ext.get("description", ""),
        "inputs": ext.get("inputs") if isinstance(ext.get("inputs"), list) else [],
        "outputs": ext.get("outputs") if isinstance(ext.get("outputs"), list) else [],
        "risks": ext.get("risks") if isinstance(ext.get("risks"), list) else [],
        "phaseName": lane["name"] if lane else "",
        "phaseId": task.get("lane_id", ""),
    }
    if ext.get("automation_potential"):
        out["automation_potential"] = ext["automation_potential"]
    if ext.get("automation_notes"):
        out["automation_notes"] = ext["automation_notes"]
    return out


def update_node(session_id: str, node_id: str, updates: dict) -> dict | None:
    model = get_or_create_session(session_id)
    allowed = {"name", "actor", "duration_min", "description", "inputs", "outputs", "risks"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    if "risks" in updates and isinstance(updates["risks"], list):
        updates["risks"] = _dedupe_risks(updates["risks"])
    task = model.get_task(node_id)
    if not task:
        return None
    if "name" in updates:
        task["name"] = updates["name"]
    ext = task.setdefault("extension", default_extension())
    for key in ("actor", "duration_min", "description", "inputs", "outputs", "risks"):
        if key in updates:
            ext[key] = updates[key]
    return get_node(session_id, node_id)


def add_node(session_id: str, phase_id: str, step_data: dict) -> dict | None:
    model = get_or_create_session(session_id)
    lane = model.get_lane(phase_id)
    if not lane:
        return None
    refs = lane.get("flow_node_refs", [])
    step_num = 1
    for node_id in reversed(refs):
        if node_id in model.task_ids():
            parts = node_id.split(".")
            if len(parts) >= 2 and parts[-1].isdigit():
                step_num = int(parts[-1]) + 1
            break
    new_id = f"{phase_id}.{step_num}"
    ext = default_extension()
    ext["actor"] = step_data.get("actor", "Pharmacist")
    ext["duration_min"] = step_data.get("duration_min", "—")
    ext["description"] = step_data.get("description", "")
    ext["inputs"] = step_data.get("inputs", [])
    ext["outputs"] = step_data.get("outputs", [])
    ext["risks"] = step_data.get("risks", [])
    new_task = default_task(new_id, step_data.get("name", "New step"), phase_id)
    new_task["extension"] = ext
    model.tasks.append(new_task)
    lane["flow_node_refs"] = list(refs) + [new_id]
    return get_node(session_id, new_id)


def delete_node(session_id: str, node_id: str) -> bool:
    model = get_or_create_session(session_id)
    task = model.get_task(node_id)
    if not task:
        return False
    lane_id = task.get("lane_id")
    if lane_id:
        lane = model.get_lane(lane_id)
        if lane and "flow_node_refs" in lane:
            lane["flow_node_refs"] = [r for r in lane["flow_node_refs"] if r != node_id]
    model.tasks[:] = [t for t in model.tasks if t["id"] != node_id]
    model.sequence_flows[:] = [
        f for f in model.sequence_flows
        if f["source_ref"] != node_id and f["target_ref"] != node_id
    ]
    return True


def get_edges(session_id: str, source_id: str | None = None) -> list:
    model = get_or_create_session(session_id)
    flows = model.sequence_flows
    if source_id is not None:
        flows = [f for f in flows if f["source_ref"] == source_id]
    return [
        {
            "from": f["source_ref"],
            "to": f["target_ref"],
            "label": f.get("name", ""),
            **({"condition": f["condition"]} if f.get("condition") else {}),
        }
        for f in flows
    ]


def add_edge(session_id: str, source: str, target: str, label: str = "", condition: str | None = None) -> dict | None:
    model = get_or_create_session(session_id)
    ids = model.task_ids()
    if source not in ids or target not in ids:
        return None
    existing = model.get_flow(source, target)
    if existing:
        if label:
            existing["name"] = label
        if condition is not None:
            existing["condition"] = condition
        return {"from": source, "to": target, "label": existing.get("name", ""), **({"condition": existing["condition"]} if existing.get("condition") else {})}
    flow_id = f"flow_{source}_{target}"
    flow = default_sequence_flow(flow_id, source, target, label or f"{source} → {target}", condition)
    model.sequence_flows.append(flow)
    return {"from": source, "to": target, "label": flow.get("name", ""), **({"condition": flow["condition"]} if flow.get("condition") else {})}


def update_edge(session_id: str, source: str, target: str, updates: dict) -> dict | None:
    model = get_or_create_session(session_id)
    flow = model.get_flow(source, target)
    if not flow:
        return None
    if "label" in updates:
        flow["name"] = updates["label"]
    if "condition" in updates:
        if updates["condition"]:
            flow["condition"] = updates["condition"]
        else:
            flow.pop("condition", None)
    return {"from": source, "to": target, "label": flow.get("name", ""), **({"condition": flow["condition"]} if flow.get("condition") else {})}


def delete_edge(session_id: str, source: str, target: str) -> bool:
    model = get_or_create_session(session_id)
    for i, f in enumerate(model.sequence_flows):
        if f["source_ref"] == source and f["target_ref"] == target:
            model.sequence_flows.pop(i)
            return True
    return False


def validate_graph(session_id: str) -> dict:
    model = get_or_create_session(session_id)
    ids = model.all_flow_node_ids()
    issues = []
    for flow in model.sequence_flows:
        if flow["source_ref"] not in ids:
            issues.append(f"Edge source '{flow['source_ref']}' is not a valid flow node id.")
        if flow["target_ref"] not in ids:
            issues.append(f"Edge target '{flow['target_ref']}' is not a valid flow node id.")
    for lane in model.lanes:
        refs = lane.get("flow_node_refs", [])
        if len(refs) != len(set(refs)):
            issues.append(f"Phase {lane['id']} has duplicate step ids.")
        for task_id in refs:
            task = model.get_task(task_id)
            if task and not (task.get("name") or task.get("id")):
                issues.append(f"Step {task.get('id', '?')} has no name.")
    return {"valid": len(issues) == 0, "issues": issues}

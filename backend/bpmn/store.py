"""Session-scoped BPMN store supporting multiple processes per session."""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from config import (
    BASELINE_GRAPH_PATH,
    BASELINE_GRAPHS_DIR,
    BASELINE_GRAPH_REGISTRY_PATH,
    DEFAULT_PROCESS_ID,
)
from bpmn.model import (
    BpmnModel,
    EXTENSION_KEYS,
    default_call_activity,
    default_extension,
    default_end_event,
    default_lane,
    default_sequence_flow,
    default_start_event,
    default_task,
)
from bpmn.layout import GAP_X, GAP_Y, LANE_HEIGHT, layout_bounds, TASK_HEIGHT, TASK_WIDTH
from bpmn.parser import parse_bpmn_xml
from bpmn.serializer import serialize_bpmn_xml

_sessions: dict[str, dict[str, BpmnModel]] = {}
_session_registries: dict[str, list[dict[str, Any]]] = {}
_baseline_models: dict[str, BpmnModel] = {}
_baseline_registry: list[dict[str, Any]] = []


def _normalize_process_id(process_id: str | None) -> str:
    return (process_id or DEFAULT_PROCESS_ID).strip() or DEFAULT_PROCESS_ID


def _load_registry() -> list[dict[str, Any]]:
    if BASELINE_GRAPH_REGISTRY_PATH.exists():
        data = json.loads(BASELINE_GRAPH_REGISTRY_PATH.read_text(encoding="utf-8"))
        processes = data.get("processes")
        if isinstance(processes, list) and processes:
            return processes
    return []


def _copy_registry(registry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in registry]


def _registry_by_id(registry: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["process_id"]: item for item in registry if item.get("process_id")}


def init_baseline() -> None:
    """Load baseline BPMN(s) once. Call from app lifespan."""
    global _baseline_models, _baseline_registry
    if _baseline_models:
        return

    registry = _load_registry()
    models: dict[str, BpmnModel] = {}

    if registry:
        for item in registry:
            process_id = item.get("process_id")
            rel_file = item.get("bpmn_file")
            if not process_id or not rel_file:
                continue
            path = BASELINE_GRAPHS_DIR / rel_file
            if not path.exists():
                raise FileNotFoundError(f"Baseline process file not found for {process_id}: {path}")
            models[process_id] = parse_bpmn_xml(path)
    else:
        if not BASELINE_GRAPH_PATH.exists():
            raise FileNotFoundError(
                f"Baseline graph not found: {BASELINE_GRAPH_PATH}. "
                "Check BASELINE_GRAPH_PATH in backend/.env or ensure backend/data/pharmacy_circuit.bpmn exists."
            )
        model = parse_bpmn_xml(BASELINE_GRAPH_PATH)
        models[DEFAULT_PROCESS_ID] = model
        registry = [
            {
                "process_id": DEFAULT_PROCESS_ID,
                "name": model.process_name or "Global process",
                "parent_id": None,
                "bpmn_file": str(Path(BASELINE_GRAPH_PATH).name),
            }
        ]

    if not models:
        raise ValueError("No baseline process could be loaded.")

    _baseline_models = models
    _baseline_registry = registry


def get_or_create_session(session_id: str) -> dict[str, BpmnModel]:
    if not _baseline_models:
        init_baseline()
    if session_id not in _sessions:
        _sessions[session_id] = {pid: model.copy() for pid, model in _baseline_models.items()}
        _session_registries[session_id] = _copy_registry(_baseline_registry)
    return _sessions[session_id]


def get_baseline_bpmn_xml(process_id: str | None = None) -> str:
    if not _baseline_models:
        init_baseline()
    pid = _normalize_process_id(process_id)
    model = _baseline_models.get(pid)
    if model is None:
        model = _baseline_models.get(DEFAULT_PROCESS_ID) or next(iter(_baseline_models.values()))
    return serialize_bpmn_xml(model)


def get_process_ids(session_id: str) -> list[str]:
    models = get_or_create_session(session_id)
    return list(models.keys())


def get_process_registry(session_id: str) -> list[dict[str, Any]]:
    get_or_create_session(session_id)
    return _copy_registry(_session_registries.get(session_id, []))


def get_process_tree(session_id: str) -> list[dict[str, Any]]:
    registry = get_process_registry(session_id)
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for item in registry:
        parent_id = item.get("parent_id")
        by_parent.setdefault(parent_id, []).append(item)

    def _build(parent_id: str | None) -> list[dict[str, Any]]:
        out = []
        for node in by_parent.get(parent_id, []):
            process_id = node.get("process_id", "")
            out.append(
                {
                    "process_id": process_id,
                    "name": node.get("name", process_id),
                    "parent_id": node.get("parent_id"),
                    "children": _build(process_id),
                }
            )
        return out

    return _build(None)


def _get_model(session_id: str, process_id: str | None = None) -> BpmnModel:
    pid = _normalize_process_id(process_id)
    models = get_or_create_session(session_id)
    if pid in models:
        return models[pid]
    if DEFAULT_PROCESS_ID in models:
        return models[DEFAULT_PROCESS_ID]
    first_pid = next(iter(models))
    return models[first_pid]


def set_session(session_id: str, graph: BpmnModel | str, process_id: str | None = None) -> None:
    """Inject a graph for a session process. graph can be BpmnModel or BPMN XML string."""
    if isinstance(graph, str):
        model = parse_bpmn_xml(graph)
    else:
        model = graph.copy()
    pid = _normalize_process_id(process_id) if process_id else model.process_id
    models = get_or_create_session(session_id)
    models[pid] = model
    # Ensure registry contains this process id.
    registry = _session_registries.setdefault(session_id, _copy_registry(_baseline_registry))
    known = _registry_by_id(registry)
    if pid not in known:
        registry.append(
            {
                "process_id": pid,
                "name": model.process_name or pid,
                "parent_id": None,
                "bpmn_file": "",
            }
        )


def get_bpmn_xml(session_id: str, process_id: str | None = None) -> str:
    """Return BPMN XML string for export."""
    model = _get_model(session_id, process_id)
    return serialize_bpmn_xml(model)


def get_graph_json(session_id: str, process_id: str | None = None) -> dict:
    """Return one process graph as JSON for custom frontend renderers."""
    model = _get_model(session_id, process_id)
    full_bounds = layout_bounds(model)
    bounds = {nid: (x, y) for nid, (x, y, _w, _h) in full_bounds.items()}
    task_by_id = {task["id"]: task for task in model.tasks}
    call_by_id = {call["id"]: call for call in model.call_activities}

    lanes = []
    y_offset = 0
    max_lane_steps = 1
    for lane in model.lanes:
        refs = lane.get("flow_node_refs", [])
        max_lane_steps = max(max_lane_steps, len(refs))
        lanes.append(
            {
                "id": lane["id"],
                "name": lane.get("name", ""),
                "description": lane.get("description", ""),
                "flow_node_refs": refs,
                "y": y_offset,
            }
        )
        y_offset += LANE_HEIGHT + GAP_Y

    nodes = []
    for lane in model.lanes:
        for node_id in lane.get("flow_node_refs", []):
            x, y = bounds.get(node_id, (0, 0))
            task = task_by_id.get(node_id)
            if task:
                ext = task.get("extension") or {}
                node = {
                    "id": task["id"],
                    "label": task.get("name", task["id"]),
                    "lane_id": task.get("lane_id", ""),
                    "node_type": "task",
                    "position": {"x": x, "y": y},
                }
                for key in EXTENSION_KEYS:
                    node[key] = ext.get(key)
                nodes.append(node)
                continue
            call = call_by_id.get(node_id)
            if call:
                ext = call.get("extension") or {}
                node = {
                    "id": call["id"],
                    "label": call.get("name", call["id"]),
                    "lane_id": call.get("lane_id", ""),
                    "node_type": "callActivity",
                    "called_element": call.get("called_element", ""),
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


def get_task_ids(session_id: str, process_id: str | None = None) -> set[str]:
    """Return all task ids for one process in a session."""
    model = _get_model(session_id, process_id)
    return model.task_ids()


def get_graph_summary(session_id: str, process_id: str | None = None) -> str:
    """Build a compact lane/step summary for LLM context with names, actor, and duration."""
    model = _get_model(session_id, process_id)
    task_by_id = {task["id"]: task for task in model.tasks}
    call_by_id = {call["id"]: call for call in model.call_activities}
    parts = []
    for lane in model.lanes:
        refs = lane.get("flow_node_refs", [])
        listed = []
        for node_id in refs:
            task = task_by_id.get(node_id)
            if task:
                label = task.get("name", "").strip()
                ext = task.get("extension") or {}
                actor = (ext.get("actor") or "").strip()
                duration = (ext.get("duration_min") or "—").strip()
                suffix = ", ".join(filter(None, [actor, duration])) if (actor or duration != "—") else ""
                entry = f"{node_id} ({label})" if label else node_id
                if suffix:
                    entry = f"{entry}, {suffix}"
                listed.append(entry)
                continue
            call = call_by_id.get(node_id)
            if call:
                label = call.get("name", "").strip()
                ext = call.get("extension") or {}
                duration = (ext.get("duration_min") or "—").strip()
                suffix = duration if duration != "—" else ""
                entry = f"{node_id} ({label})" if label else node_id
                if suffix:
                    entry = f"{entry}, {suffix}"
                listed.append(entry)
        parts.append(f"{lane['id']} {lane.get('name', '')}: {', '.join(listed)}")
    return " | ".join(parts)


def _score_match(needle: str, name: str, id_val: str) -> float:
    if not name and not id_val:
        return 0.0
    name_l = (name or "").lower()
    id_l = (id_val or "").lower()
    if name_l == needle or id_l == needle:
        return 1.0
    if needle in name_l or needle in id_l:
        return 0.9
    return SequenceMatcher(a=needle, b=name_l or id_l).ratio()


def resolve_step(session_id: str, name_fragment: str, process_id: str | None = None) -> list[dict[str, Any]]:
    """Resolve step/process/lane names to ids. Searches tasks, call_activities, and lanes. Returns list with type field."""
    needle = (name_fragment or "").strip().lower()
    if not needle:
        return []

    results: list[tuple[float, dict[str, Any]]] = []
    process_ids = [process_id] if process_id else get_process_ids(session_id)
    for pid in process_ids:
        model = _get_model(session_id, pid)
        for task in model.tasks:
            name = (task.get("name") or "").strip()
            task_id = task.get("id", "")
            if not name and not task_id:
                continue
            score = _score_match(needle, name, task_id)
            if score >= 0.55:
                results.append(
                    (
                        score,
                        {
                            "type": "task",
                            "node_id": task_id,
                            "name": name,
                            "process_id": model.process_id,
                        },
                    )
                )
        for call in model.call_activities:
            name = (call.get("name") or "").strip()
            call_id = call.get("id", "")
            if not name and not call_id:
                continue
            score = _score_match(needle, name, call_id)
            if score >= 0.55:
                results.append(
                    (
                        score,
                        {
                            "type": "callActivity",
                            "node_id": call_id,
                            "name": name,
                            "process_id": model.process_id,
                        },
                    )
                )
        for lane in model.lanes:
            name = (lane.get("name") or "").strip()
            lane_id = lane.get("id", "")
            if not name and not lane_id:
                continue
            score = _score_match(needle, name, lane_id)
            if score >= 0.55:
                results.append(
                    (
                        score,
                        {
                            "type": "lane",
                            "lane_id": lane_id,
                            "name": name,
                            "process_id": model.process_id,
                        },
                    )
                )
    results.sort(key=lambda x: x[0], reverse=True)
    return [item for _score, item in results[:10]]


def _dedupe_risks(risks: list) -> list:
    seen = set()
    out = []
    for r in risks:
        s = (r or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def get_node(session_id: str, node_id: str, process_id: str | None = None) -> dict | None:
    model = _get_model(session_id, process_id)
    task = model.get_task(node_id)
    node_type = "task"
    if task is None:
        task = model.get_call_activity(node_id)
        node_type = "callActivity"
    if task is None:
        return None
    lane = model.get_lane(task.get("lane_id", "")) if task.get("lane_id") else None
    ext = task.get("extension") or {}
    out = {
        "id": task["id"],
        "name": task.get("name", ""),
        "node_type": node_type,
        "actor": ext.get("actor", ""),
        "duration_min": ext.get("duration_min", "—"),
        "description": ext.get("description", ""),
        "inputs": ext.get("inputs") if isinstance(ext.get("inputs"), list) else [],
        "outputs": ext.get("outputs") if isinstance(ext.get("outputs"), list) else [],
        "risks": ext.get("risks") if isinstance(ext.get("risks"), list) else [],
        "phaseName": lane["name"] if lane else "",
        "phaseId": task.get("lane_id", ""),
        "process_id": model.process_id,
    }
    if node_type == "callActivity":
        out["called_element"] = task.get("called_element", "")
    if ext.get("automation_potential"):
        out["automation_potential"] = ext["automation_potential"]
    if ext.get("automation_notes"):
        out["automation_notes"] = ext["automation_notes"]
    return out


def update_node(session_id: str, node_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    model = _get_model(session_id, process_id)
    allowed = {"name", "actor", "duration_min", "description", "inputs", "outputs", "risks", "automation_potential", "automation_notes"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    if "risks" in updates and isinstance(updates["risks"], list):
        updates["risks"] = _dedupe_risks(updates["risks"])
    task = model.get_task(node_id)
    is_call_activity = False
    if not task:
        task = model.get_call_activity(node_id)
        is_call_activity = True
    if not task:
        return None
    if "name" in updates:
        task["name"] = updates["name"]
    ext = task.setdefault("extension", default_extension())
    for key in ("actor", "duration_min", "description", "inputs", "outputs", "risks", "automation_potential", "automation_notes"):
        if key in updates:
            ext[key] = updates[key]
    if is_call_activity:
        return get_node(session_id, node_id, process_id=process_id)
    return get_node(session_id, node_id, process_id=process_id)


def add_node(session_id: str, phase_id: str, step_data: dict, process_id: str | None = None) -> dict | None:
    model = _get_model(session_id, process_id)
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
    ext["risks"] = _dedupe_risks(step_data.get("risks", []))
    ext["automation_potential"] = step_data.get("automation_potential", "")
    ext["automation_notes"] = step_data.get("automation_notes", "")
    new_task = default_task(new_id, step_data.get("name", "New step"), phase_id)
    new_task["extension"] = ext
    model.tasks.append(new_task)
    lane["flow_node_refs"] = list(refs) + [new_id]
    return get_node(session_id, new_id, process_id=process_id)


def delete_node(session_id: str, node_id: str, process_id: str | None = None) -> bool:
    model = _get_model(session_id, process_id)
    task = model.get_task(node_id)
    is_call_activity = False
    if not task:
        task = model.get_call_activity(node_id)
        is_call_activity = True
    if not task:
        return False
    lane_id = task.get("lane_id")
    if lane_id:
        lane = model.get_lane(lane_id)
        if lane and "flow_node_refs" in lane:
            lane["flow_node_refs"] = [r for r in lane["flow_node_refs"] if r != node_id]
    if is_call_activity:
        model.call_activities[:] = [c for c in model.call_activities if c["id"] != node_id]
    else:
        model.tasks[:] = [t for t in model.tasks if t["id"] != node_id]
    model.sequence_flows[:] = [
        f for f in model.sequence_flows
        if f["source_ref"] != node_id and f["target_ref"] != node_id
    ]
    return True


def get_edges(session_id: str, source_id: str | None = None, process_id: str | None = None) -> list:
    model = _get_model(session_id, process_id)
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


def add_edge(
    session_id: str,
    source: str,
    target: str,
    label: str = "",
    condition: str | None = None,
    process_id: str | None = None,
) -> dict | None:
    model = _get_model(session_id, process_id)
    ids = model.all_flow_node_ids()
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


def update_edge(session_id: str, source: str, target: str, updates: dict, process_id: str | None = None) -> dict | None:
    model = _get_model(session_id, process_id)
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


def delete_edge(session_id: str, source: str, target: str, process_id: str | None = None) -> bool:
    model = _get_model(session_id, process_id)
    for i, f in enumerate(model.sequence_flows):
        if f["source_ref"] == source and f["target_ref"] == target:
            model.sequence_flows.pop(i)
            return True
    return False


def validate_graph(session_id: str, process_id: str | None = None) -> dict:
    model = _get_model(session_id, process_id)
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


def _next_lane_id(model: BpmnModel) -> str:
    """Generate a unique lane id for the model."""
    existing = {ln["id"] for ln in model.lanes}
    n = 1
    while f"Lane_{n}" in existing:
        n += 1
    return f"Lane_{n}"


def add_lane(session_id: str, lane_data: dict, process_id: str | None = None) -> dict | None:
    """Create a new lane. lane_data: name (required), description (optional). Returns lane dict or None."""
    model = _get_model(session_id, process_id)
    name = (lane_data.get("name") or "").strip() or "New phase"
    description = (lane_data.get("description") or "").strip()
    lane_id = _next_lane_id(model)
    lane = default_lane(lane_id, name, description)
    model.lanes.append(lane)
    return {"id": lane_id, "name": name, "description": description, "flow_node_refs": []}


def update_lane(session_id: str, lane_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    """Rename lane or update description. updates: name, description."""
    model = _get_model(session_id, process_id)
    lane = model.get_lane(lane_id)
    if not lane:
        return None
    if "name" in updates and updates["name"] is not None:
        lane["name"] = str(updates["name"]).strip() or lane.get("name", "")
    if "description" in updates:
        lane["description"] = str(updates["description"]).strip() if updates["description"] is not None else ""
    return {"id": lane_id, "name": lane.get("name", ""), "description": lane.get("description", ""), "flow_node_refs": lane.get("flow_node_refs", [])}


def delete_lane(session_id: str, lane_id: str, process_id: str | None = None) -> bool:
    """Remove a lane and all tasks and call activities (and their edges) that belong to it."""
    model = _get_model(session_id, process_id)
    lane = model.get_lane(lane_id)
    if not lane:
        return False
    refs = list(lane.get("flow_node_refs", []))
    node_ids_to_remove = (set(refs) & model.task_ids()) | (set(refs) & model.call_activity_ids())
    for node_id in node_ids_to_remove:
        delete_node(session_id, node_id, process_id=process_id)
    model.lanes[:] = [ln for ln in model.lanes if ln["id"] != lane_id]
    return True


def reorder_lanes(session_id: str, lane_ids: list[str], process_id: str | None = None) -> bool:
    """Reorder model.lanes to match the given list of lane ids."""
    model = _get_model(session_id, process_id)
    current_ids = [ln["id"] for ln in model.lanes]
    if set(lane_ids) != set(current_ids) or len(lane_ids) != len(current_ids):
        return False
    by_id = {ln["id"]: ln for ln in model.lanes}
    model.lanes = [by_id[lid] for lid in lane_ids]
    return True


def move_node(
    session_id: str,
    node_id: str,
    target_lane_id: str,
    position: int | None = None,
    process_id: str | None = None,
) -> dict | None:
    """Move a task from one lane to another. position is 0-based index; if None, appends."""
    model = _get_model(session_id, process_id)
    task = model.get_task(node_id)
    if not task:
        return None
    target_lane = model.get_lane(target_lane_id)
    if not target_lane:
        return None
    old_lane_id = task.get("lane_id")
    old_lane = model.get_lane(old_lane_id) if old_lane_id else None
    if old_lane and "flow_node_refs" in old_lane:
        old_lane["flow_node_refs"] = [r for r in old_lane["flow_node_refs"] if r != node_id]
    refs = list(target_lane.get("flow_node_refs", []))
    if position is not None and 0 <= position <= len(refs):
        refs.insert(position, node_id)
    else:
        refs.append(node_id)
    target_lane["flow_node_refs"] = refs
    task["lane_id"] = target_lane_id
    return get_node(session_id, node_id, process_id=process_id)


def reorder_steps(session_id: str, lane_id: str, ordered_ids: list[str], process_id: str | None = None) -> bool:
    """Set the order of steps in a lane. All ids must exist and belong to that lane."""
    model = _get_model(session_id, process_id)
    lane = model.get_lane(lane_id)
    if not lane:
        return False
    current_refs = set(lane.get("flow_node_refs", []))
    all_ids = model.all_flow_node_ids()
    for nid in ordered_ids:
        if nid not in all_ids or nid not in current_refs:
            return False
    if set(ordered_ids) != current_refs:
        return False
    lane["flow_node_refs"] = list(ordered_ids)
    return True


def rename_process(session_id: str, new_name: str, process_id: str | None = None) -> bool:
    """Set the process display name and update the session registry entry."""
    pid = _normalize_process_id(process_id)
    model = _get_model(session_id, process_id)
    model.process_name = (new_name or "").strip() or model.process_name
    registry = _session_registries.get(session_id)
    if registry:
        for item in registry:
            if item.get("process_id") == pid:
                item["name"] = model.process_name
                break
    return True


def _slug_from_name(name: str) -> str:
    """Generate a safe id slug from a display name."""
    s = (name or "").strip() or "Sub"
    s = "".join(c if c.isalnum() or c in "_-" else "_" for c in s)
    s = s.strip("_") or "Sub"
    return s[:32]


def add_subprocess(
    session_id: str,
    name: str,
    parent_process_id: str | None = None,
) -> dict | None:
    """Create a new empty subprocess and a call activity in the parent. Returns {process_id, call_activity_id} or None."""
    models = get_or_create_session(session_id)
    parent_pid = _normalize_process_id(parent_process_id)
    if parent_pid not in models:
        return None
    parent = models[parent_pid]
    base_slug = _slug_from_name(name)
    new_process_id = f"Process_{base_slug}"
    n = 1
    while new_process_id in models:
        new_process_id = f"Process_{base_slug}_{n}"
        n += 1
    lane_id = "Lane_1"
    start_id = f"Start_{base_slug}"
    end_id = f"End_{base_slug}"
    sub = BpmnModel(
        process_id=new_process_id,
        process_name=(name or "").strip() or "Subprocess",
        lanes=[default_lane(lane_id, (name or "").strip() or "Subprocess")],
        tasks=[],
        call_activities=[],
        start_events=[default_start_event(start_id, "Start", lane_id)],
        end_events=[default_end_event(end_id, "End", lane_id)],
        gateways=[],
        sequence_flows=[
            default_sequence_flow(f"flow_{start_id}_{end_id}", start_id, end_id, "Start"),
        ],
    )
    sub.lanes[0]["flow_node_refs"] = [start_id, end_id]
    models[new_process_id] = sub
    _session_registries.setdefault(session_id, _copy_registry(_baseline_registry))
    registry = _session_registries[session_id]
    registry.append(
        {
            "process_id": new_process_id,
            "name": sub.process_name,
            "parent_id": parent_pid,
            "bpmn_file": "",
        }
    )
    call_id = f"Call_{base_slug}" if base_slug != "Sub" else f"Call_{base_slug}_{n}"
    n = 1
    while parent.get_call_activity(call_id) or parent.get_task(call_id):
        call_id = f"Call_{base_slug}_{n}"
        n += 1
    parent_lane = parent.lanes[0] if parent.lanes else None
    if not parent_lane:
        return None
    refs = list(parent_lane.get("flow_node_refs", []))
    end_events_in_lane = [e["id"] for e in parent.end_events if e["id"] in refs]
    insert_before = end_events_in_lane[0] if end_events_in_lane else None
    if insert_before and insert_before in refs:
        idx = refs.index(insert_before)
        refs.insert(idx, call_id)
    else:
        refs.append(call_id)
    parent_lane["flow_node_refs"] = refs
    call = default_call_activity(call_id, (name or "").strip() or "Subprocess", new_process_id, parent_lane["id"])
    parent.call_activities.append(call)
    prev_id = refs[refs.index(call_id) - 1] if refs.index(call_id) > 0 else None
    next_id = refs[refs.index(call_id) + 1] if refs.index(call_id) + 1 < len(refs) else None
    if prev_id:
        parent.sequence_flows.append(
            default_sequence_flow(f"flow_{prev_id}_{call_id}", prev_id, call_id, ""),
        )
    if next_id:
        parent.sequence_flows.append(
            default_sequence_flow(f"flow_{call_id}_{next_id}", call_id, next_id, ""),
        )
    if prev_id and next_id and parent.get_flow(prev_id, next_id):
        parent.sequence_flows[:] = [f for f in parent.sequence_flows if f["source_ref"] != prev_id or f["target_ref"] != next_id]
    return {"process_id": new_process_id, "call_activity_id": call_id}

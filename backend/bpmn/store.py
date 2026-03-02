"""Session-scoped BPMN store supporting multiple processes per session.

Backed by in-memory SQLite (db module).  An LRU cache of parsed BpmnModel
objects avoids re-parsing XML on every request within a session.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import db
from config import (
    BASELINE_GRAPH_REGISTRY_PATH,
    BASELINE_GRAPHS_DIR,
    DEFAULT_PROCESS_ID,
)
from bpmn.model import (
    BpmnModel,
    default_extension,
    default_lane,
    default_sequence_flow,
    default_task,
)
from bpmn.parser import parse_bpmn_xml
from bpmn.serializer import serialize_bpmn_xml

# (session_id, process_id) -> parsed BpmnModel
_cache: dict[tuple[str, str], BpmnModel] = {}


def _normalize_process_id(process_id: str | None) -> str:
    return (process_id or DEFAULT_PROCESS_ID).strip() or DEFAULT_PROCESS_ID


def init_baseline() -> None:
    """Seed baseline into SQLite from registry + BPMN files.  Call from app lifespan."""
    if not BASELINE_GRAPH_REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Registry not found: {BASELINE_GRAPH_REGISTRY_PATH}. "
            "Check BASELINE_GRAPHS_DIR in backend/.env or ensure backend/data/graphs/registry.json exists."
        )
    db.seed_baseline(BASELINE_GRAPH_REGISTRY_PATH, BASELINE_GRAPHS_DIR)


def _get_model(session_id: str, process_id: str | None = None) -> BpmnModel:
    pid = _normalize_process_id(process_id)
    key = (session_id, pid)
    if key in _cache:
        return _cache[key]

    xml = db.get_session_xml(session_id, pid)
    if xml is None:
        db.clone_baseline_to_session(session_id)
        xml = db.get_session_xml(session_id, pid)
    if xml is None:
        xml = db.get_baseline_xml(DEFAULT_PROCESS_ID)
    if xml is None:
        raise RuntimeError(f"No BPMN XML found for session={session_id} process={pid}")

    model = parse_bpmn_xml(xml)
    _cache[key] = model
    return model


def _persist(session_id: str, process_id: str | None = None) -> None:
    """Write the cached model back to the DB after a mutation. Saves previous XML to history before overwriting."""
    pid = _normalize_process_id(process_id)
    key = (session_id, pid)
    model = _cache.get(key)
    if model is None:
        return
    # Snapshot current session XML so bot actions can be undone
    current_xml = db.get_session_xml(session_id, pid)
    if current_xml:
        db.push_history(session_id, pid, current_xml)
    db.upsert_session_xml(session_id, pid, serialize_bpmn_xml(model))


def get_baseline_bpmn_xml(process_id: str | None = None) -> str:
    pid = _normalize_process_id(process_id)
    xml = db.get_baseline_xml(pid)
    if xml is None:
        xml = db.get_baseline_xml(DEFAULT_PROCESS_ID)
    if xml is None:
        raise RuntimeError(f"Baseline not found for process_id={pid}")
    model = parse_bpmn_xml(xml)
    return serialize_bpmn_xml(model)


def get_process_ids(session_id: str) -> list[str]:
    pids = db.get_session_process_ids(session_id)
    if not pids:
        db.clone_baseline_to_session(session_id)
        pids = db.get_session_process_ids(session_id)
    return pids


def set_session(session_id: str, graph: BpmnModel | str, process_id: str | None = None) -> None:
    """Inject a graph for a session process."""
    if isinstance(graph, str):
        model = parse_bpmn_xml(graph)
    else:
        model = graph.copy()
    pid = _normalize_process_id(process_id) if process_id else model.process_id
    _cache[(session_id, pid)] = model
    db.upsert_session_xml(session_id, pid, serialize_bpmn_xml(model))


def get_bpmn_xml(session_id: str, process_id: str | None = None) -> str:
    model = _get_model(session_id, process_id)
    return serialize_bpmn_xml(model)


def undo_graph(session_id: str, process_id: str | None = None) -> str | None:
    """Restore the previous graph state from history. Returns restored BPMN XML or None if nothing to undo."""
    pid = _normalize_process_id(process_id)
    prev_xml = db.pop_history(session_id, pid)
    if prev_xml is None:
        return None
    key = (session_id, pid)
    _cache.pop(key, None)
    db.upsert_session_xml(session_id, pid, prev_xml)
    return prev_xml


def get_task_ids(session_id: str, process_id: str | None = None) -> set[str]:
    model = _get_model(session_id, process_id)
    return model.task_ids()


def get_graph_summary(session_id: str, process_id: str | None = None) -> str:
    """Build a compact lane/step summary for LLM context."""
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
    """Resolve step/process/lane names to ids."""
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
                results.append((score, {"type": "task", "node_id": task_id, "name": name, "process_id": model.process_id}))
        for call in model.call_activities:
            name = (call.get("name") or "").strip()
            call_id = call.get("id", "")
            if not name and not call_id:
                continue
            score = _score_match(needle, name, call_id)
            if score >= 0.55:
                results.append((score, {"type": "callActivity", "node_id": call_id, "name": name, "process_id": model.process_id}))
        for lane in model.lanes:
            name = (lane.get("name") or "").strip()
            lane_id = lane.get("id", "")
            if not name and not lane_id:
                continue
            score = _score_match(needle, name, lane_id)
            if score >= 0.55:
                results.append((score, {"type": "lane", "lane_id": lane_id, "name": name, "process_id": model.process_id}))
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
    out: dict[str, Any] = {
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


_UPDATE_NODE_ALLOWED = {
    "name", "actor", "duration_min", "description", "inputs", "outputs", "risks",
    "automation_potential", "automation_notes",
    "current_state", "frequency", "annual_volume", "error_rate_percent",
    "cost_per_execution", "current_systems", "data_format",
    "external_dependencies", "regulatory_constraints", "sla_target", "pain_points",
}


def update_node(session_id: str, node_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    model = _get_model(session_id, process_id)
    updates = {k: v for k, v in updates.items() if k in _UPDATE_NODE_ALLOWED}
    if "risks" in updates and isinstance(updates["risks"], list):
        updates["risks"] = _dedupe_risks(updates["risks"])
    task = model.get_task(node_id)
    if not task:
        task = model.get_call_activity(node_id)
    if not task:
        return None
    if "name" in updates:
        task["name"] = updates["name"]
    ext = task.setdefault("extension", default_extension())
    for key in _UPDATE_NODE_ALLOWED - {"name"}:
        if key in updates:
            ext[key] = updates[key]
    _persist(session_id, process_id)
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
    for key in _UPDATE_NODE_ALLOWED - {"name"}:
        if key in step_data:
            ext[key] = step_data[key]
    if "risks" in step_data and isinstance(step_data["risks"], list):
        ext["risks"] = _dedupe_risks(step_data["risks"])
    new_task = default_task(new_id, step_data.get("name", "New step"), phase_id)
    new_task["extension"] = ext
    model.tasks.append(new_task)
    lane["flow_node_refs"] = list(refs) + [new_id]
    _persist(session_id, process_id)
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
    _persist(session_id, process_id)
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
        _persist(session_id, process_id)
        return {"from": source, "to": target, "label": existing.get("name", ""), **({"condition": existing["condition"]} if existing.get("condition") else {})}
    flow_id = f"flow_{source}_{target}"
    flow = default_sequence_flow(flow_id, source, target, label or f"{source} → {target}", condition)
    model.sequence_flows.append(flow)
    _persist(session_id, process_id)
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
    _persist(session_id, process_id)
    return {"from": source, "to": target, "label": flow.get("name", ""), **({"condition": flow["condition"]} if flow.get("condition") else {})}


def delete_edge(session_id: str, source: str, target: str, process_id: str | None = None) -> bool:
    model = _get_model(session_id, process_id)
    for i, f in enumerate(model.sequence_flows):
        if f["source_ref"] == source and f["target_ref"] == target:
            model.sequence_flows.pop(i)
            _persist(session_id, process_id)
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
    existing = {ln["id"] for ln in model.lanes}
    n = 1
    while f"Lane_{n}" in existing:
        n += 1
    return f"Lane_{n}"


def add_lane(session_id: str, lane_data: dict, process_id: str | None = None) -> dict | None:
    from bpmn.model import default_lane as _default_lane
    model = _get_model(session_id, process_id)
    name = (lane_data.get("name") or "").strip() or "New phase"
    description = (lane_data.get("description") or "").strip()
    lane_id = _next_lane_id(model)
    lane = _default_lane(lane_id, name, description)
    model.lanes.append(lane)
    _persist(session_id, process_id)
    return {"id": lane_id, "name": name, "description": description, "flow_node_refs": []}


def update_lane(session_id: str, lane_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    model = _get_model(session_id, process_id)
    lane = model.get_lane(lane_id)
    if not lane:
        return None
    if "name" in updates and updates["name"] is not None:
        lane["name"] = str(updates["name"]).strip() or lane.get("name", "")
    if "description" in updates:
        lane["description"] = str(updates["description"]).strip() if updates["description"] is not None else ""
    _persist(session_id, process_id)
    return {"id": lane_id, "name": lane.get("name", ""), "description": lane.get("description", ""), "flow_node_refs": lane.get("flow_node_refs", [])}


def delete_lane(session_id: str, lane_id: str, process_id: str | None = None) -> bool:
    model = _get_model(session_id, process_id)
    lane = model.get_lane(lane_id)
    if not lane:
        return False
    refs = list(lane.get("flow_node_refs", []))
    node_ids_to_remove = (set(refs) & model.task_ids()) | (set(refs) & model.call_activity_ids())
    for node_id in node_ids_to_remove:
        delete_node(session_id, node_id, process_id=process_id)
    model.lanes[:] = [ln for ln in model.lanes if ln["id"] != lane_id]
    _persist(session_id, process_id)
    return True


def reorder_lanes(session_id: str, lane_ids: list[str], process_id: str | None = None) -> bool:
    model = _get_model(session_id, process_id)
    current_ids = [ln["id"] for ln in model.lanes]
    if set(lane_ids) != set(current_ids) or len(lane_ids) != len(current_ids):
        return False
    by_id = {ln["id"]: ln for ln in model.lanes}
    model.lanes = [by_id[lid] for lid in lane_ids]
    _persist(session_id, process_id)
    return True


def move_node(
    session_id: str,
    node_id: str,
    target_lane_id: str,
    position: int | None = None,
    process_id: str | None = None,
) -> dict | None:
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
    _persist(session_id, process_id)
    return get_node(session_id, node_id, process_id=process_id)


def reorder_steps(session_id: str, lane_id: str, ordered_ids: list[str], process_id: str | None = None) -> bool:
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
    _persist(session_id, process_id)
    return True


def rename_process(session_id: str, new_name: str, process_id: str | None = None) -> bool:
    model = _get_model(session_id, process_id)
    model.process_name = (new_name or "").strip() or model.process_name
    _persist(session_id, process_id)
    return True

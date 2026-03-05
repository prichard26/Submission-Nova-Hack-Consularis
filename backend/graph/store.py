"""Session-scoped JSON-native process store.

Backed by in-memory SQLite (db module).  A cache of parsed ProcessGraph
objects avoids re-parsing JSON on every request within a session.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

import db
from config import (
    BASELINE_GRAPHS_DIR,
    BASELINE_WORKSPACE_PATH,
    DEFAULT_PROCESS_ID,
)
from graph.model import ProcessGraph, STEP_METADATA_KEYS, LIST_METADATA_KEYS, default_step_metadata
from graph.workspace import WorkspaceManifest
from graph.layout import auto_position

# caches: (session_id, process_id) -> ProcessGraph
_cache: dict[tuple[str, str], ProcessGraph] = {}
# workspace cache: session_id -> WorkspaceManifest
_ws_cache: dict[str, WorkspaceManifest] = {}


def _normalize_process_id(process_id: str | None) -> str:
    return (process_id or DEFAULT_PROCESS_ID).strip() or DEFAULT_PROCESS_ID


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

def init_baseline() -> None:
    """Seed baseline into SQLite from workspace.json + graph JSON files."""
    if not BASELINE_WORKSPACE_PATH.exists():
        raise FileNotFoundError(
            f"Workspace manifest not found: {BASELINE_WORKSPACE_PATH}. "
            "Run `python -m scripts.migrate_bpmn_to_json` first."
        )
    db.seed_baseline(BASELINE_WORKSPACE_PATH, BASELINE_GRAPHS_DIR)


def _get_graph(session_id: str, process_id: str | None = None) -> ProcessGraph:
    pid = _normalize_process_id(process_id)
    key = (session_id, pid)
    if key in _cache:
        return _cache[key]

    json_str = db.get_session_json(session_id, pid)
    if json_str is None:
        db.clone_baseline_to_session(session_id)
        _brand_session(session_id)
        json_str = db.get_session_json(session_id, pid)
    if json_str is None:
        json_str = db.get_baseline_json(DEFAULT_PROCESS_ID)
    if json_str is None:
        raise RuntimeError(f"No graph JSON found for session={session_id} process={pid}")

    graph = ProcessGraph.from_json(json_str)
    _cache[key] = graph
    return graph


def _persist(session_id: str, process_id: str | None = None, *, skip_history: bool = False) -> None:
    """Write the cached graph back to DB. Optionally saves previous JSON to history (skip for position-only updates)."""
    pid = _normalize_process_id(process_id)
    key = (session_id, pid)
    graph = _cache.get(key)
    if graph is None:
        return
    if not skip_history:
        current = db.get_session_json(session_id, pid)
        if current:
            db.push_history(session_id, pid, current)
        db.clear_redo(session_id, pid)
    db.upsert_session_json(session_id, pid, graph.to_json())


def _refresh_workspace_summary(session_id: str, process_id: str | None = None) -> None:
    """Recompute step/subprocess counts from the graph and update the workspace manifest."""
    pid = _normalize_process_id(process_id)
    try:
        graph = _get_graph(session_id, pid)
    except RuntimeError:
        return
    ws = _get_workspace(session_id)
    info = ws.get_process_info(pid)
    if info is None:
        return
    step_count = sum(1 for s in graph.steps if s.get("type") not in ("start", "end"))
    subprocess_count = sum(1 for s in graph.steps if s.get("type") == "subprocess")
    summary = dict(info.get("summary") or {})
    summary["step_count"] = step_count
    summary["subprocess_count"] = subprocess_count
    info["summary"] = summary
    db.upsert_session_workspace(session_id, ws.to_json())


def _brand_session(session_id: str) -> None:
    """Rename the root process to '{company}_map' after first clone."""
    map_name = f"{session_id}_map"
    ws_json = db.get_session_workspace(session_id)
    if ws_json is None:
        return
    ws = WorkspaceManifest.from_json(ws_json)
    root_id = ws.data.get("process_tree", {}).get("root", DEFAULT_PROCESS_ID)
    procs = ws.data.get("process_tree", {}).get("processes", {})
    if root_id in procs:
        procs[root_id]["name"] = map_name
    db.upsert_session_workspace(session_id, ws.to_json())

    graph_json = db.get_session_json(session_id, root_id)
    if graph_json:
        gdata = json.loads(graph_json)
        gdata["name"] = map_name
        db.upsert_session_json(session_id, root_id, json.dumps(gdata, ensure_ascii=False, indent=2))


def _get_workspace(session_id: str) -> WorkspaceManifest:
    if session_id in _ws_cache:
        return _ws_cache[session_id]
    ws_json = db.get_session_workspace(session_id)
    if ws_json is None:
        db.clone_baseline_to_session(session_id)
        _brand_session(session_id)
        ws_json = db.get_session_workspace(session_id)
    if ws_json is None:
        ws_json = db.get_baseline_workspace()
    if ws_json is None:
        try:
            init_baseline()
            ws_json = db.get_baseline_workspace()
            if ws_json:
                db.clone_baseline_to_session(session_id)
                _brand_session(session_id)
                ws_json = db.get_session_workspace(session_id) or ws_json
        except FileNotFoundError:
            pass
    if ws_json is None:
        raise RuntimeError("No workspace manifest found")
    ws = WorkspaceManifest.from_json(ws_json)
    expected_name = f"{session_id}_map"
    root_id = ws.data.get("process_tree", {}).get("root", DEFAULT_PROCESS_ID)
    procs = ws.data.get("process_tree", {}).get("processes", {})
    if root_id in procs and procs[root_id].get("name") != expected_name:
        _brand_session(session_id)
        ws.data["process_tree"]["processes"][root_id]["name"] = expected_name
    _ws_cache[session_id] = ws
    return ws


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_graph_json(session_id: str, process_id: str | None = None) -> str:
    graph = _get_graph(session_id, process_id)
    return graph.to_json()


def get_baseline_json(process_id: str | None = None) -> str:
    pid = _normalize_process_id(process_id)
    json_str = db.get_baseline_json(pid)
    if json_str is None:
        json_str = db.get_baseline_json(DEFAULT_PROCESS_ID)
    if json_str is None:
        raise RuntimeError(f"Baseline not found for process_id={pid}")
    return json_str


def get_workspace_json(session_id: str) -> str:
    ws = _get_workspace(session_id)
    return ws.to_json()


def get_process_ids(session_id: str) -> list[str]:
    pids = db.get_session_process_ids(session_id)
    if not pids:
        db.clone_baseline_to_session(session_id)
        _brand_session(session_id)
        pids = db.get_session_process_ids(session_id)
    return pids


def get_step_ids(session_id: str, process_id: str | None = None) -> set[str]:
    graph = _get_graph(session_id, process_id)
    return graph.all_step_ids()


def get_graph_summary(session_id: str, process_id: str | None = None) -> str:
    """Compact lane/step summary + edges for LLM context."""
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, process_id)
    parts = []
    for lane in graph.lanes:
        refs = set(lane.get("node_refs", []))
        listed = []
        for step in graph.steps:
            if step.get("id") not in refs:
                continue
            stype = step.get("type", "")
            if stype in ("start", "end"):
                continue
            sid = step.get("short_id") or step.get("id", "")
            label = step.get("name", "").strip()
            actor = (step.get("actor") or "").strip()
            duration = (step.get("duration_min") or "").strip()
            cost = (step.get("cost_per_execution") or "").strip()
            err = (step.get("error_rate_percent") or "").strip()
            auto = (step.get("automation_potential") or "").strip().upper()
            entry = f"{sid} ({label})" if label else sid
            extras = []
            if actor:
                extras.append(actor)
            if duration:
                extras.append(duration)
            if cost:
                extras.append(f"${cost}")
            if err:
                extras.append(f"{err}% err")
            if auto:
                extras.append(f"{auto} automation")
            if extras:
                entry += ", " + ", ".join(extras)
            listed.append(entry)
        parts.append(f"{lane.get('id', '')} {lane.get('name', '')}: {', '.join(listed)}")
    edges = [f"{f.get('from', '')}->{f.get('to', '')}" for f in graph.flows]
    if edges:
        parts.append("Edges: " + ", ".join(edges))
    try:
        ws = _get_workspace(session_id)
        root_id = ws.data.get("process_tree", {}).get("root", DEFAULT_PROCESS_ID)
        if pid == root_id:
            children = ws.get_children(pid)
            if children:
                sub_list = [f"{((ws.get_process_info(cid)) or {}).get('name', cid)}={cid}" for cid in children]
                parts.append("Subprocesses: " + ", ".join(sub_list))
    except Exception:
        pass
    return " | ".join(parts)


def _all_process_ids_in_tree_order(ws: WorkspaceManifest, root_id: str) -> list[str]:
    """Return all process IDs in depth-first order (root, then each branch)."""
    order: list[str] = []

    def visit(pid: str) -> None:
        order.append(pid)
        for c in ws.get_children(pid):
            visit(c)

    visit(root_id)
    return order


def get_full_graph_summary(session_id: str) -> str:
    """Return summaries for all processes in the workspace tree (any depth) for full context."""
    # Force fresh read from DB so agent sees latest edits (and new subprocesses)
    _ws_cache.pop(session_id, None)
    for key in list(_cache):
        if key[0] == session_id:
            del _cache[key]
    ws = _get_workspace(session_id)
    root_id = ws.data.get("process_tree", {}).get("root", DEFAULT_PROCESS_ID)
    procs = ws.data.get("process_tree", {}).get("processes", {})
    order = _all_process_ids_in_tree_order(ws, root_id)
    parts = []
    for pid in order:
        info = procs.get(pid) or {}
        name = info.get("name", pid)
        path = ws.get_path(pid)
        summary = get_graph_summary(session_id, process_id=pid)
        header = f"--- {pid} ({name}) ---"
        if path:
            header += f"\nPath: {path}"
        parts.append(f"{header}\n{summary}")
    return "\n\n".join(parts)


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
    """Resolve step/lane names to IDs via fuzzy matching."""
    needle = (name_fragment or "").strip().lower()
    if not needle:
        return []

    results: list[tuple[float, dict[str, Any]]] = []
    process_ids = [process_id] if process_id else get_process_ids(session_id)
    for pid in process_ids:
        graph = _get_graph(session_id, pid)
        for step in graph.steps:
            stype = step.get("type", "step")
            if stype in ("start", "end"):
                continue
            name = (step.get("name") or "").strip()
            step_id = step.get("id", "")
            short_id = step.get("short_id", "")
            if not name and not step_id:
                continue
            score = max(_score_match(needle, name, step_id), _score_match(needle, name, short_id))
            if score >= 0.55:
                results.append((score, {
                    "type": stype, "node_id": step_id, "name": name,
                    "process_id": graph.process_id,
                }))
        for lane in graph.lanes:
            name = (lane.get("name") or "").strip()
            lane_id = lane.get("id", "")
            score = _score_match(needle, name, lane_id)
            if score >= 0.55:
                results.append((score, {
                    "type": "lane", "lane_id": lane_id, "name": name,
                    "process_id": graph.process_id,
                }))
    results.sort(key=lambda x: x[0], reverse=True)
    return [item for _score, item in results[:10]]


def get_node(session_id: str, node_id: str, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    step = graph.get_step(node_id)
    if step is None:
        return None
    lane = graph.get_lane(step.get("lane_id", "")) if step.get("lane_id") else None
    out: dict[str, Any] = {
        "id": step["id"],
        "name": step.get("name", ""),
        "node_type": step.get("type", "step"),
        "process_id": graph.process_id,
        "phaseName": lane["name"] if lane else "",
        "phaseId": step.get("lane_id", ""),
    }
    if step.get("short_id"):
        out["short_id"] = step["short_id"]
    if step.get("called_element"):
        out["called_element"] = step["called_element"]
    for key in STEP_METADATA_KEYS:
        val = step.get(key)
        if val is not None and val != "" and val != []:
            out[key] = val
    return out


def get_edges(session_id: str, source_id: str | None = None, process_id: str | None = None) -> list:
    graph = _get_graph(session_id, process_id)
    flows = graph.flows
    if source_id is not None:
        flows = [f for f in flows if f.get("from") == source_id]
    return [
        {
            "from": f["from"],
            "to": f["to"],
            "label": f.get("label", ""),
            **({"source_handle": f["source_handle"]} if f.get("source_handle") else {}),
            **({"target_handle": f["target_handle"]} if f.get("target_handle") else {}),
            **({"condition": f["condition"]} if f.get("condition") else {}),
        }
        for f in flows
    ]


# ---------------------------------------------------------------------------
# Mutation operations
# ---------------------------------------------------------------------------

_UPDATE_NODE_ALLOWED = {"name", "called_element"} | STEP_METADATA_KEYS


def _dedupe_risks(risks: list) -> list:
    seen = set()
    out = []
    for r in risks:
        s = (r or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _next_custom_process_id(session_id: str, ws: WorkspaceManifest) -> str:
    existing = set(ws.all_process_ids())
    existing.update(get_process_ids(session_id))
    n = 1
    while f"Process_Custom_{n}" in existing:
        n += 1
    return f"Process_Custom_{n}"


def _starter_process_graph(process_id: str, name: str, parent_info: dict | None) -> dict[str, Any]:
    lane_id = "MAIN"
    start_id = f"Start_{process_id}"
    end_id = f"End_{process_id}"
    return {
        "format_version": "1.0",
        "process_id": process_id,
        "name": name,
        "metadata": {
            "owner": (parent_info or {}).get("owner", "Pharmacy Department"),
            "category": (parent_info or {}).get("category", "clinical"),
            "criticality": (parent_info or {}).get("criticality", "medium"),
        },
        "lanes": [
            {
                "id": lane_id,
                "name": name,
                "description": "",
                "node_refs": [start_id, end_id],
            }
        ],
        "steps": [
            {
                "id": start_id,
                "name": "Start",
                "type": "start",
                "lane_id": lane_id,
                "position": {"x": 280, "y": 78},
            },
            {
                "id": end_id,
                "name": "End",
                "type": "end",
                "lane_id": lane_id,
                "position": {"x": 740, "y": 78},
            },
        ],
        "flows": [
            {
                "from": start_id,
                "to": end_id,
                "label": "Start",
            }
        ],
    }


def update_node(session_id: str, node_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    updates = {k: v for k, v in updates.items() if k in _UPDATE_NODE_ALLOWED}
    if "risks" in updates and isinstance(updates["risks"], list):
        updates["risks"] = _dedupe_risks(updates["risks"])
    step = graph.get_step(node_id)
    if not step:
        return None
    for key, val in updates.items():
        step[key] = val
    _persist(session_id, process_id)
    return get_node(session_id, node_id, process_id=process_id)


def add_node(session_id: str, lane_id: str, step_data: dict, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    lane = graph.get_lane(lane_id)
    if not lane:
        return None

    refs = lane.get("node_refs", [])
    existing_ids = graph.all_step_ids()
    prefix = f"{lane_id}."
    max_suffix = 0
    for nid in existing_ids:
        if not nid.startswith(prefix):
            continue
        suffix = nid[len(prefix):]
        if suffix.isdigit():
            max_suffix = max(max_suffix, int(suffix))
    step_num = max_suffix + 1 if max_suffix > 0 else 1
    new_id = f"{lane_id}.{step_num}"
    while new_id in existing_ids:
        step_num += 1
        new_id = f"{lane_id}.{step_num}"

    provided_pos = step_data.get("position")
    if isinstance(provided_pos, dict) and "x" in provided_pos and "y" in provided_pos:
        pos = {"x": int(provided_pos.get("x", 0)), "y": int(provided_pos.get("y", 0))}
    else:
        pos = auto_position(graph, lane_id, new_step=step_data)
    new_step: dict[str, Any] = {
        "id": new_id,
        "name": step_data.get("name", "New step"),
        "type": step_data.get("type", "step"),
        "short_id": new_id,
        "lane_id": lane_id,
        "position": pos,
    }
    for key in STEP_METADATA_KEYS:
        if key in step_data:
            new_step[key] = step_data[key]
    if "risks" in new_step and isinstance(new_step["risks"], list):
        new_step["risks"] = _dedupe_risks(new_step["risks"])

    graph.steps.append(new_step)
    lane["node_refs"] = list(refs) + [new_id]

    _persist(session_id, process_id)
    _refresh_workspace_summary(session_id, process_id)
    return get_node(session_id, new_id, process_id=process_id)


def create_subprocess_page(
    session_id: str,
    parent_process_id: str,
    node_id: str,
    name: str | None = None,
) -> dict | None:
    parent_pid = _normalize_process_id(parent_process_id)
    parent_graph = _get_graph(session_id, parent_pid)
    step = parent_graph.get_step(node_id)
    if not step or step.get("type") != "subprocess":
        return None

    ws = _get_workspace(session_id)
    parent_info = ws.get_process_info(parent_pid)
    if parent_info is None:
        return None

    existing_called = step.get("called_element")
    if existing_called and ws.get_process_info(existing_called):
        return {
            "created": False,
            "process_id": existing_called,
            "node": get_node(session_id, node_id, process_id=parent_pid),
        }

    process_name = (name or step.get("name") or "New Subprocess").strip() or "New Subprocess"
    new_process_id = _next_custom_process_id(session_id, ws)
    new_graph_dict = _starter_process_graph(new_process_id, process_name, parent_info)
    db.upsert_session_json(session_id, new_process_id, json.dumps(new_graph_dict, ensure_ascii=False, indent=2))
    _cache[(session_id, new_process_id)] = ProcessGraph.from_dict(new_graph_dict)

    tree = ws.data.setdefault("process_tree", {})
    processes = tree.setdefault("processes", {})
    parent_children = parent_info.setdefault("children", [])
    if new_process_id not in parent_children:
        parent_children.append(new_process_id)

    new_depth = int(parent_info.get("depth", 0)) + 1
    new_path = f"{parent_info.get('path', '').rstrip('/')}/{new_process_id}"
    processes[new_process_id] = {
        "name": process_name,
        "depth": new_depth,
        "path": new_path,
        "children": [],
        "graph_file": f"{new_process_id}.json",
        "owner": parent_info.get("owner", "Pharmacy Department"),
        "category": parent_info.get("category", "clinical"),
        "criticality": parent_info.get("criticality", "medium"),
        "summary": {"step_count": 0, "subprocess_count": 0},
    }

    category = processes[new_process_id].get("category")
    if category:
        tags = ws.data.setdefault("tags", {})
        tagged = tags.setdefault(category, [])
        if new_process_id not in tagged:
            tagged.append(new_process_id)

    step["called_element"] = new_process_id
    _persist(session_id, parent_pid)
    db.upsert_session_workspace(session_id, ws.to_json())
    _ws_cache.pop(session_id, None)  # so next read gets updated tree from DB (e.g. chat agent)
    _refresh_workspace_summary(session_id, parent_pid)
    _refresh_workspace_summary(session_id, new_process_id)

    return {
        "created": True,
        "process_id": new_process_id,
        "node": get_node(session_id, node_id, process_id=parent_pid),
    }


def delete_node(session_id: str, node_id: str, process_id: str | None = None) -> bool:
    graph = _get_graph(session_id, process_id)
    step = graph.get_step(node_id)
    if not step:
        return False
    if step.get("type") in ("start", "end"):
        return False
    lane_id = step.get("lane_id")
    if lane_id:
        lane = graph.get_lane(lane_id)
        if lane and "node_refs" in lane:
            lane["node_refs"] = [r for r in lane["node_refs"] if r != node_id]
    graph.steps[:] = [s for s in graph.steps if s.get("id") != node_id]
    graph.flows[:] = [
        f for f in graph.flows
        if f.get("from") != node_id and f.get("to") != node_id
    ]
    _persist(session_id, process_id)
    _refresh_workspace_summary(session_id, process_id)
    return True


def add_edge(
    session_id: str,
    source: str,
    target: str,
    label: str = "",
    condition: str | None = None,
    source_handle: str | None = None,
    target_handle: str | None = None,
    process_id: str | None = None,
) -> dict | None:
    graph = _get_graph(session_id, process_id)
    ids = graph.all_step_ids()
    if source not in ids or target not in ids:
        return None
    existing = graph.get_flow(source, target)
    if existing:
        if label:
            existing["label"] = label
        if condition is not None:
            existing["condition"] = condition
        if source_handle:
            existing["source_handle"] = source_handle
        if target_handle:
            existing["target_handle"] = target_handle
        _persist(session_id, process_id)
        return {
            "from": source,
            "to": target,
            "label": existing.get("label", ""),
            **({"source_handle": existing["source_handle"]} if existing.get("source_handle") else {}),
            **({"target_handle": existing["target_handle"]} if existing.get("target_handle") else {}),
            **({"condition": existing["condition"]} if existing.get("condition") else {}),
        }
    flow: dict[str, Any] = {"from": source, "to": target}
    if label:
        flow["label"] = label
    if condition:
        flow["condition"] = condition
    if source_handle:
        flow["source_handle"] = source_handle
    if target_handle:
        flow["target_handle"] = target_handle
    graph.flows.append(flow)
    _persist(session_id, process_id)
    return {
        "from": source,
        "to": target,
        "label": flow.get("label", ""),
        **({"source_handle": flow["source_handle"]} if flow.get("source_handle") else {}),
        **({"target_handle": flow["target_handle"]} if flow.get("target_handle") else {}),
        **({"condition": flow["condition"]} if flow.get("condition") else {}),
    }


def update_edge(session_id: str, source: str, target: str, updates: dict, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    flow = graph.get_flow(source, target)
    if not flow:
        return None
    if "label" in updates:
        flow["label"] = updates["label"]
    if "condition" in updates:
        if updates["condition"]:
            flow["condition"] = updates["condition"]
        else:
            flow.pop("condition", None)
    _persist(session_id, process_id)
    return {"from": source, "to": target, "label": flow.get("label", ""),
            **({"condition": flow["condition"]} if flow.get("condition") else {})}


def delete_edge(session_id: str, source: str, target: str, process_id: str | None = None) -> bool:
    graph = _get_graph(session_id, process_id)
    for i, f in enumerate(graph.flows):
        if f.get("from") == source and f.get("to") == target:
            graph.flows.pop(i)
            _persist(session_id, process_id)
            return True
    return False


def validate_graph(session_id: str, process_id: str | None = None) -> dict:
    graph = _get_graph(session_id, process_id)
    ids = graph.all_step_ids()
    issues = []
    for flow in graph.flows:
        if flow.get("from") not in ids:
            issues.append(f"Edge source '{flow.get('from')}' is not a valid step id.")
        if flow.get("to") not in ids:
            issues.append(f"Edge target '{flow.get('to')}' is not a valid step id.")
    for lane in graph.lanes:
        refs = lane.get("node_refs", [])
        if len(refs) != len(set(refs)):
            issues.append(f"Lane {lane.get('id')} has duplicate step ids.")
    return {"valid": len(issues) == 0, "issues": issues}


def _next_lane_id(graph: ProcessGraph) -> str:
    existing = {ln.get("id") for ln in graph.lanes}
    n = 1
    while f"Lane_{n}" in existing:
        n += 1
    return f"Lane_{n}"


def add_lane(session_id: str, lane_data: dict, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    name = (lane_data.get("name") or "").strip() or "New phase"
    description = (lane_data.get("description") or "").strip()
    lane_id = _next_lane_id(graph)
    lane: dict[str, Any] = {
        "id": lane_id,
        "name": name,
        "description": description,
        "node_refs": [],
    }
    graph.lanes.append(lane)
    _persist(session_id, process_id)
    return {"id": lane_id, "name": name, "description": description, "node_refs": []}


def update_lane(session_id: str, lane_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    lane = graph.get_lane(lane_id)
    if not lane:
        return None
    if "name" in updates and updates["name"] is not None:
        lane["name"] = str(updates["name"]).strip() or lane.get("name", "")
    if "description" in updates:
        lane["description"] = str(updates["description"]).strip() if updates["description"] is not None else ""
    _persist(session_id, process_id)
    return {"id": lane_id, "name": lane.get("name", ""), "description": lane.get("description", ""),
            "node_refs": lane.get("node_refs", [])}


def delete_lane(session_id: str, lane_id: str, process_id: str | None = None) -> bool:
    graph = _get_graph(session_id, process_id)
    lane = graph.get_lane(lane_id)
    if not lane:
        return False
    refs = list(lane.get("node_refs", []))
    for nid in refs:
        delete_node(session_id, nid, process_id=process_id)
    graph.lanes[:] = [ln for ln in graph.lanes if ln.get("id") != lane_id]
    _persist(session_id, process_id)
    return True


def reorder_lanes(session_id: str, lane_ids: list[str], process_id: str | None = None) -> bool:
    graph = _get_graph(session_id, process_id)
    current_ids = [ln.get("id") for ln in graph.lanes]
    if set(lane_ids) != set(current_ids) or len(lane_ids) != len(current_ids):
        return False
    by_id = {ln["id"]: ln for ln in graph.lanes}
    graph.data["lanes"] = [by_id[lid] for lid in lane_ids]
    _persist(session_id, process_id)
    return True


def move_node(
    session_id: str,
    node_id: str,
    target_lane_id: str,
    position: int | None = None,
    process_id: str | None = None,
) -> dict | None:
    graph = _get_graph(session_id, process_id)
    step = graph.get_step(node_id)
    if not step:
        return None
    target_lane = graph.get_lane(target_lane_id)
    if not target_lane:
        return None
    old_lane_id = step.get("lane_id")
    old_lane = graph.get_lane(old_lane_id) if old_lane_id else None
    if old_lane and "node_refs" in old_lane:
        old_lane["node_refs"] = [r for r in old_lane["node_refs"] if r != node_id]
    refs = list(target_lane.get("node_refs", []))
    if position is not None and 0 <= position <= len(refs):
        refs.insert(position, node_id)
    else:
        refs.append(node_id)
    target_lane["node_refs"] = refs
    step["lane_id"] = target_lane_id
    _persist(session_id, process_id)
    return get_node(session_id, node_id, process_id=process_id)


def reorder_steps(session_id: str, lane_id: str, ordered_ids: list[str], process_id: str | None = None) -> bool:
    graph = _get_graph(session_id, process_id)
    lane = graph.get_lane(lane_id)
    if not lane:
        return False
    current_refs = set(lane.get("node_refs", []))
    if set(ordered_ids) != current_refs:
        return False
    lane["node_refs"] = list(ordered_ids)
    _persist(session_id, process_id)
    return True


def rename_process(session_id: str, new_name: str, process_id: str | None = None) -> bool:
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, pid)
    graph.name = (new_name or "").strip() or graph.name
    _persist(session_id, pid)
    # Sync process name into workspace manifest so directory/header/minimap show the new name
    try:
        ws = _get_workspace(session_id)
        procs = ws.data.get("process_tree", {}).get("processes", {})
        if pid in procs:
            procs[pid]["name"] = graph.name
            db.upsert_session_workspace(session_id, ws.to_json())
        _ws_cache.pop(session_id, None)
    except Exception:
        pass
    return True


def undo_graph(session_id: str, process_id: str | None = None) -> str | None:
    """Restore previous graph state from history. Returns restored JSON or None."""
    pid = _normalize_process_id(process_id)
    current_json = db.get_session_json(session_id, pid)
    prev_json = db.pop_history(session_id, pid)
    if prev_json is None:
        return None
    if current_json:
        db.push_redo(session_id, pid, current_json)
    key = (session_id, pid)
    _cache.pop(key, None)
    db.upsert_session_json(session_id, pid, prev_json)
    _refresh_workspace_summary(session_id, pid)
    return prev_json


def redo_graph(session_id: str, process_id: str | None = None) -> str | None:
    """Re-apply next graph state from redo stack. Returns restored JSON or None."""
    pid = _normalize_process_id(process_id)
    current_json = db.get_session_json(session_id, pid)
    next_json = db.pop_redo(session_id, pid)
    if next_json is None:
        return None
    if current_json:
        db.push_history(session_id, pid, current_json)
    key = (session_id, pid)
    _cache.pop(key, None)
    db.upsert_session_json(session_id, pid, next_json)
    _refresh_workspace_summary(session_id, pid)
    return next_json


def reset_to_baseline(session_id: str, process_id: str | None = None) -> str:
    """Reset process graph to baseline snapshot and clear undo/redo state."""
    pid = _normalize_process_id(process_id)
    baseline_json = db.get_baseline_json(pid) or db.get_baseline_json(DEFAULT_PROCESS_ID)
    if baseline_json is None:
        raise RuntimeError(f"Baseline not found for process_id={pid}")
    key = (session_id, pid)
    _cache.pop(key, None)
    db.upsert_session_json(session_id, pid, baseline_json)
    db.clear_history(session_id, pid)
    db.clear_redo(session_id, pid)
    _refresh_workspace_summary(session_id, pid)
    return baseline_json


def update_positions(session_id: str, process_id: str | None, positions: dict[str, dict]) -> bool:
    """Batch update step positions from drag-and-drop."""
    graph = _get_graph(session_id, process_id)
    changed = False
    for step_id, pos in positions.items():
        step = graph.get_step(step_id)
        if step and isinstance(pos, dict):
            step["position"] = {"x": pos.get("x", 0), "y": pos.get("y", 0)}
            changed = True
    if changed:
        _persist(session_id, process_id, skip_history=True)
    return changed


def set_session(session_id: str, graph: ProcessGraph | str, process_id: str | None = None) -> None:
    """Inject a graph for a session (used by tests)."""
    if isinstance(graph, str):
        g = ProcessGraph.from_json(graph)
    else:
        g = graph.copy()
    pid = _normalize_process_id(process_id) if process_id else g.process_id
    _cache[(session_id, pid)] = g
    db.upsert_session_json(session_id, pid, g.to_json())

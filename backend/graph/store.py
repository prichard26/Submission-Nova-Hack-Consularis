"""Session-scoped JSON-native process store.

Backed by in-memory SQLite (db module).  A cache of parsed ProcessGraph
objects avoids re-parsing JSON on every request within a session.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

import db
from config import (
    BASELINE_GRAPHS_DIR,
    BASELINE_WORKSPACE_PATH,
    DEFAULT_PROCESS_ID,
)
from graph.model import (
    ProcessGraph,
    STEP_METADATA_KEYS,
    LIST_METADATA_KEYS,
    default_step_metadata,
    _node_attrs,
)
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
    step_count = sum(1 for n in graph.nodes if n.get("type") not in ("start", "end"))
    subprocess_count = sum(1 for n in graph.nodes if n.get("type") == "subprocess")
    summary = dict(info.get("summary") or {})
    summary["step_count"] = step_count
    summary["subprocess_count"] = subprocess_count
    info["summary"] = summary
    db.upsert_session_workspace(session_id, ws.to_json())


def _brand_session(session_id: str) -> None:
    """Rename the root process to '{session_id}_map' after first clone."""
    map_name = f"{session_id}_map"
    ws_json = db.get_session_workspace(session_id)
    if ws_json is None:
        return
    ws = WorkspaceManifest.from_json(ws_json)
    root_id = ws.data.get("process_tree", {}).get("root", "global")
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
    root_id = ws.data.get("process_tree", {}).get("root", "global")
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


def get_graph_dict_for_client(session_id: str, process_id: str | None = None) -> dict[str, Any]:
    """Return graph as dict with process_id and synthetic lanes for UI (if not already present)."""
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, process_id)
    data = dict(graph.data)
    data["process_id"] = pid
    if not data.get("lanes"):
        data["lanes"] = [{
            "id": "default",
            "name": data.get("name", ""),
            "description": "",
            "node_refs": [n["id"] for n in data.get("nodes", []) if n.get("id")],
        }]
    return data


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


def get_process_id_for_step(session_id: str, step_id: str) -> str | None:
    """Return the process_id whose graph contains step_id, or None if not found."""
    if not step_id:
        return None
    try:
        for pid in get_process_ids(session_id):
            try:
                graph = _get_graph(session_id, pid)
                if step_id in graph.all_step_ids():
                    return pid
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_process_id_for_add_node(session_id: str, location_id: str) -> str | None:
    """Resolve where to add a new node. If location_id is a subprocess node, return its page id (node.id); else return the process that contains location_id."""
    pid = get_process_id_for_step(session_id, location_id)
    if not pid:
        return None
    try:
        graph = _get_graph(session_id, pid)
        node = graph.get_step(location_id)
        if node and node.get("type") == "subprocess":
            return node["id"]  # subprocess node id = page id (e.g. S1)
    except Exception:
        pass
    return pid


def get_process_id_for_proposed_id(session_id: str, proposed_id: str, step_type: str) -> str | None:
    """Infer which process a new node belongs to from its proposed id (for agent-created ids)."""
    if not proposed_id or not proposed_id.strip():
        return None
    proposed_id = proposed_id.strip()
    pids = set(get_process_ids(session_id))
    # Top-level subprocess on global: S1, S2, ... S8 (no dot)
    if re.match(r"^S\d+$", proposed_id):
        return "global"
    # Nested subprocess: S1.1, S1.1.1 → node lives in parent's graph (S1, S1.1)
    if step_type == "subprocess" and proposed_id.startswith("S") and "." in proposed_id:
        parent = proposed_id.rsplit(".", 1)[0]
        return parent if parent in pids else None
    # Step or decision: P1.4 → S1, P1_1.2 → S1.1, G1.1 → S1
    if proposed_id.startswith("P") or proposed_id.startswith("G"):
        prefix = proposed_id.split(".")[0]
        if len(prefix) < 2:
            return None
        num_part = prefix[1:]
        process_suffix = num_part.replace("_", ".")
        pid = "S" + process_suffix
        return pid if pid in pids else None
    return None


def get_full_graph(session_id: str) -> dict[str, Any]:
    """Return the full graph for all processes: each process has id, name, nodes (full node objects with id, name, type, attributes), edges (from, to, label). Agent uses this to see everything including node attributes."""
    ws = _get_workspace(session_id)
    root_id = ws.data.get("process_tree", {}).get("root", "global")
    processes_order = _all_process_ids_in_tree_order(ws, root_id)
    out: list[dict[str, Any]] = []
    for pid in processes_order:
        try:
            graph = _get_graph(session_id, pid)
        except Exception:
            continue
        # Full node objects so the agent sees id, name, type, and all attributes (actor, risks, description, etc.)
        nodes = []
        for n in graph.nodes:
            if not n.get("id"):
                continue
            attrs = _node_attrs(n)
            node_entry: dict[str, Any] = {
                "id": n.get("id"),
                "name": attrs.get("name") or n.get("name"),
                "type": n.get("type", ""),
            }
            if attrs:
                node_entry["attributes"] = dict(attrs)
            nodes.append(node_entry)
        edges = [{"from": e.get("from"), "to": e.get("to"), "label": e.get("label", "")} for e in graph.edges]
        out.append({
            "id": pid,
            "name": graph.name or pid,
            "nodes": nodes,
            "edges": edges,
        })
    return {"processes": out}


def _safe_str(val: Any) -> str:
    """Coerce to string and strip; handles numbers (e.g. error_rate_percent as int)."""
    if val is None:
        return ""
    return str(val).strip()


def get_graph_summary(session_id: str, process_id: str | None = None) -> str:
    """Compact step summary + edges for LLM context. Uses step_order."""
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, process_id)
    parts = []
    listed = []
    for step in graph.steps_in_order():
        stype = step.get("type", "")
        if stype in ("start", "end"):
            continue
        attrs = _node_attrs(step)
        sid = step.get("id", "")
        label = _safe_str(attrs.get("name"))
        actor = _safe_str(attrs.get("actor"))
        duration = _safe_str(attrs.get("duration_min"))
        cost = _safe_str(attrs.get("cost_per_execution"))
        err = _safe_str(attrs.get("error_rate_percent"))
        auto = _safe_str(attrs.get("automation_potential")).upper()
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
    if listed:
        parts.append(f"{graph.name or pid}: {', '.join(listed)}")
    edges = [f"{e.get('from', '')}->{e.get('to', '')}" for e in graph.edges]
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
        display_id = pid
        header = f"--- {display_id} ({name}) ---"
        if path:
            header += f"\nPath: {path}"
        parts.append(f"{header}\n{summary}")
    return "\n\n".join(parts)


def get_graph_summary_for_analysis(session_id: str, process_id: str | None = None) -> str:
    """Like get_graph_summary but includes automation_notes per step for the analyzer LLM. Uses step_order."""
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, process_id)
    parts = []
    listed = []
    for step in graph.steps_in_order():
        stype = step.get("type", "")
        if stype in ("start", "end"):
            continue
        attrs = _node_attrs(step)
        sid = step.get("id", "")
        label = _safe_str(attrs.get("name"))
        actor = _safe_str(attrs.get("actor"))
        duration = _safe_str(attrs.get("duration_min"))
        cost = _safe_str(attrs.get("cost_per_execution"))
        err = _safe_str(attrs.get("error_rate_percent"))
        auto = _safe_str(attrs.get("automation_potential")).upper()
        notes = _safe_str(attrs.get("automation_notes"))
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
        if notes:
            entry += " | Notes: " + notes
        listed.append(entry)
    if listed:
        parts.append(f"{graph.name or pid}: {', '.join(listed)}")
    edges = [f"{e.get('from', '')}->{e.get('to', '')}" for e in graph.edges]
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


def get_full_graph_summary_for_analysis(session_id: str) -> str:
    """Full graph summary with automation_notes included for the analyzer LLM."""
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
        summary = get_graph_summary_for_analysis(session_id, process_id=pid)
        header = f"--- {pid} ({name}) ---"
        if path:
            header += f"\nPath: {path}"
        parts.append(f"{header}\n{summary}")
    return "\n\n".join(parts)


def get_analysis_metrics(session_id: str) -> dict[str, Any]:
    """Compute metrics for the analyze page: counts by automation potential, overall score, categories."""
    _ws_cache.pop(session_id, None)
    for key in list(_cache):
        if key[0] == session_id:
            del _cache[key]
    ws = _get_workspace(session_id)
    root_id = ws.data.get("process_tree", {}).get("root", DEFAULT_PROCESS_ID)
    order = _all_process_ids_in_tree_order(ws, root_id)
    high = medium = low = none = 0
    processes_with_steps = 0
    for pid in order:
        graph = _get_graph(session_id, pid)
        step_count_here = 0
        for node in graph.nodes:
            if node.get("type") in ("start", "end"):
                continue
            step_count_here += 1
            attrs = _node_attrs(node)
            auto = _safe_str(attrs.get("automation_potential")).upper()
            if "HIGH" in auto or auto == "H":
                high += 1
            elif "MEDIUM" in auto or "MED" in auto or auto == "M":
                medium += 1
            elif "LOW" in auto or auto == "L":
                low += 1
            else:
                none += 1
        if step_count_here > 0:
            processes_with_steps += 1
    total_steps = high + medium + low + none
    # Overall score 0–100: weighted by potential (high=100, medium=60, low=30, none=0)
    if total_steps:
        raw = (high * 100 + medium * 60 + low * 30 + none * 0) / total_steps
        overall_score = round(min(100, max(0, raw)))
    else:
        overall_score = 0
    total_processes = len(order)
    # Category: automation potential is the same as overall; process coverage = % of processes that have steps
    process_coverage = round((processes_with_steps / total_processes * 100) if total_processes else 0)
    return {
        "overall_score": overall_score,
        "categories": {
            "automation_potential": overall_score,
            "process_coverage": process_coverage,
            "step_count": total_steps,
            "process_count": total_processes,
        },
        "counts": {
            "high": high,
            "medium": medium,
            "low": low,
            "none": none,
            "total_steps": total_steps,
            "processes": total_processes,
        },
    }


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
    """Resolve step names to IDs via fuzzy matching. process_id in results comes from request."""
    needle = (name_fragment or "").strip().lower()
    if not needle:
        return []

    results: list[tuple[float, dict[str, Any]]] = []
    process_ids = [process_id] if process_id else get_process_ids(session_id)
    for pid in process_ids:
        graph = _get_graph(session_id, pid)
        for node in graph.nodes:
            stype = node.get("type", "step")
            if stype in ("start", "end"):
                continue
            attrs = _node_attrs(node)
            name = (attrs.get("name") or "").strip()
            step_id = node.get("id", "")
            if not name and not step_id:
                continue
            score = _score_match(needle, name, step_id)
            if score >= 0.55:
                results.append((score, {
                    "type": stype, "node_id": step_id, "name": name,
                    "process_id": pid,
                }))
    results.sort(key=lambda x: x[0], reverse=True)
    return [item for _score, item in results[:10]]


def get_node(session_id: str, node_id: str, process_id: str | None = None) -> dict | None:
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, process_id)
    node = graph.get_step(node_id)
    if node is None:
        return None
    attrs = _node_attrs(node)
    out: dict[str, Any] = {
        "id": node["id"],
        "name": attrs.get("name", ""),
        "node_type": node.get("type", "step"),
        "process_id": pid,
    }
    if node.get("type") == "subprocess":
        out["called_element"] = node["id"]  # page id = node id (e.g. S1)
    elif node.get("called_element"):
        out["called_element"] = node["called_element"]
    for key in STEP_METADATA_KEYS:
        val = attrs.get(key)
        if val is not None and val != "" and val != []:
            out[key] = val
    return out


def get_edges(session_id: str, source_id: str | None = None, process_id: str | None = None) -> list:
    graph = _get_graph(session_id, process_id)
    edges = graph.edges
    if source_id is not None:
        edges = [e for e in edges if e.get("from") == source_id]
    return [
        {
            "from": e["from"],
            "to": e["to"],
            "label": e.get("label", ""),
            **({"source_handle": e["source_handle"]} if e.get("source_handle") else {}),
            **({"target_handle": e["target_handle"]} if e.get("target_handle") else {}),
        }
        for e in edges
    ]


# ---------------------------------------------------------------------------
# Mutation operations
# ---------------------------------------------------------------------------

_UPDATE_NODE_ALLOWED = {"name"} | STEP_METADATA_KEYS


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
    """New format: id, name, nodes, edges. Start/end ids = {process_id}_start, {process_id}_end."""
    start_id = f"{process_id}_start"
    end_id = f"{process_id}_end"
    return {
        "id": process_id,
        "name": name,
        "nodes": [
            {"id": start_id, "type": "start", "position": {"x": 280, "y": 78}},
            {"id": end_id, "type": "end", "position": {"x": 740, "y": 78}},
        ],
        "edges": [
            {"from": start_id, "to": end_id, "label": "Start"},
        ],
    }


def update_node(session_id: str, node_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    updates = {k: v for k, v in updates.items() if k in _UPDATE_NODE_ALLOWED}
    if "risks" in updates and isinstance(updates["risks"], list):
        updates["risks"] = _dedupe_risks(updates["risks"])
    node = graph.get_step(node_id)
    if not node:
        return None
    if "name" in updates:
        node["name"] = updates.pop("name", node.get("name", ""))
    attrs = node.setdefault("attributes", {})
    for key, val in updates.items():
        attrs[key] = val
    _persist(session_id, process_id)
    return get_node(session_id, node_id, process_id=process_id)


def add_node(session_id: str, lane_id: str, step_data: dict, process_id: str | None = None) -> dict | None:
    """Add a step/decision/subprocess. If step_data has 'id', use it as the new node's id (agent supplies next id); else infer location from process_id/lane and generate id."""
    step_type = step_data.get("type", "step")
    explicit_id = (step_data.get("id") or "").strip()

    if explicit_id:
        pid = get_process_id_for_proposed_id(session_id, explicit_id, step_type)
        if not pid:
            return None
        graph = _get_graph(session_id, pid)
        if explicit_id in graph.all_step_ids():
            return None  # id already exists
        new_id = explicit_id
        # step_data may have "id"; don't put it in the node's attributes
        step_data_clean = {k: v for k, v in step_data.items() if k != "id"}
    else:
        pid = _normalize_process_id(process_id)
        if not pid:
            return None
        graph = _get_graph(session_id, pid)
        existing_ids = graph.all_step_ids()
        if pid == "global":
            if step_type == "subprocess":
                new_id = _next_global_subprocess_id(graph)
            else:
                new_id = f"GLOBAL.{len(existing_ids) + 1}"
                while new_id in existing_ids:
                    new_id = f"GLOBAL.{int(new_id.split('.')[-1]) + 1}"
        else:
            if step_type == "subprocess":
                new_id = _next_nested_subprocess_id(graph, pid)
            else:
                num = pid[1:].replace(".", "_") if pid.startswith("S") else pid.replace(".", "_") or "1"
                step_prefix = f"P{num}"
                decision_prefix = f"G{num}"
                if step_type == "decision":
                    max_suffix = 0
                    for nid in existing_ids:
                        if nid.startswith(decision_prefix + ".") and nid[len(decision_prefix) + 1:].isdigit():
                            max_suffix = max(max_suffix, int(nid[len(decision_prefix) + 1:]))
                    new_id = f"{decision_prefix}.{max_suffix + 1}"
                else:
                    max_suffix = 0
                    for nid in existing_ids:
                        if nid.startswith(step_prefix + ".") and nid[len(step_prefix) + 1:].isdigit():
                            max_suffix = max(max_suffix, int(nid[len(step_prefix) + 1:]))
                    new_id = f"{step_prefix}.{max_suffix + 1 if max_suffix > 0 else 1}"
                while new_id in existing_ids:
                    if step_type == "decision":
                        new_id = f"{decision_prefix}.{int(new_id.split('.')[-1]) + 1}"
                    else:
                        new_id = f"{step_prefix}.{int(new_id.split('.')[-1]) + 1}"
        step_data_clean = step_data

    provided_pos = step_data_clean.get("position")
    if isinstance(provided_pos, dict) and "x" in provided_pos and "y" in provided_pos:
        pos = {"x": int(provided_pos.get("x", 0)), "y": int(provided_pos.get("y", 0))}
    else:
        pos = auto_position(graph, new_step={**step_data_clean, "type": step_type})
    new_node: dict[str, Any] = {
        "id": new_id,
        "name": step_data_clean.get("name", "New step"),
        "type": step_type,
        "position": pos,
    }
    meta = {k: step_data_clean[k] for k in STEP_METADATA_KEYS if k in step_data_clean}
    if meta:
        if "risks" in meta and isinstance(meta["risks"], list):
            meta["risks"] = _dedupe_risks(meta["risks"])
        new_node["attributes"] = meta

    # Insert before end node
    end_node = next((n for n in graph.nodes if n.get("type") == "end"), None)
    if end_node:
        idx = next((i for i, n in enumerate(graph.nodes) if n.get("id") == end_node.get("id")), len(graph.nodes))
        graph.data["nodes"].insert(idx, new_node)
    else:
        graph.nodes.append(new_node)

    _persist(session_id, pid)
    _refresh_workspace_summary(session_id, pid)

    if new_node.get("type") == "subprocess":
        subprocess_display_name = (step_data_clean.get("name") or new_node.get("name") or "").strip()
        create_subprocess_page(
            session_id,
            parent_process_id=pid,
            node_id=new_id,
            name=subprocess_display_name or None,
        )

    return get_node(session_id, new_id, process_id=pid)


def create_subprocess_page(
    session_id: str,
    parent_process_id: str,
    node_id: str,
    name: str | None = None,
) -> dict | None:
    """Create a subprocess page. Page id = node_id (e.g. S1)."""
    parent_pid = _normalize_process_id(parent_process_id)
    parent_graph = _get_graph(session_id, parent_pid)
    node = parent_graph.get_step(node_id)
    if not node or node.get("type") != "subprocess":
        return None

    ws = _get_workspace(session_id)
    parent_info = ws.get_process_info(parent_pid)
    if parent_info is None:
        return None

    new_process_id = node_id  # page id = node id (S1, S2, ...)
    if ws.get_process_info(new_process_id):
        return {
            "created": False,
            "process_id": new_process_id,
            "node": get_node(session_id, node_id, process_id=parent_pid),
        }

    process_name = (name or node.get("name") or "New Subprocess").strip() or "New Subprocess"
    if not (node.get("name") or "").strip():
        node["name"] = process_name
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

    _persist(session_id, parent_pid)
    db.upsert_session_workspace(session_id, ws.to_json())
    _ws_cache.pop(session_id, None)
    _refresh_workspace_summary(session_id, parent_pid)
    _refresh_workspace_summary(session_id, new_process_id)

    return {
        "created": True,
        "process_id": new_process_id,
        "node": get_node(session_id, node_id, process_id=parent_pid),
    }


def _collect_descendant_process_ids(ws: WorkspaceManifest, process_id: str) -> list[str]:
    """Return process_id and all its descendants (depth-first), so we can remove leaves first."""
    result: list[str] = []
    for child_id in ws.get_children(process_id):
        result.extend(_collect_descendant_process_ids(ws, child_id))
    result.append(process_id)
    return result


def _teardown_linked_subprocess(
    session_id: str, parent_pid: str, called_element: str
) -> None:
    """Remove the linked subprocess and all its descendants from the workspace and DB."""
    ws = _get_workspace(session_id)
    to_remove = _collect_descendant_process_ids(ws, called_element)

    for pid in to_remove:
        info = ws.get_process_info(pid)
        if not info:
            continue
        path = (info.get("path") or "").strip("/")
        parts = [p for p in path.split("/") if p]
        parent_id = parts[-2] if len(parts) >= 2 else None
        if parent_id is not None:
            parent_info = ws.get_process_info(parent_id)
            if parent_info and "children" in parent_info:
                parent_info["children"] = [c for c in parent_info["children"] if c != pid]
        tree = ws.data.get("process_tree", {})
        processes = tree.get("processes", {})
        if pid in processes:
            del processes[pid]
        db.delete_session_process(session_id, pid)
        _cache.pop((session_id, pid), None)

    for tag_list in ws.data.get("tags", {}).values():
        if isinstance(tag_list, list):
            for pid in to_remove:
                if pid in tag_list:
                    tag_list.remove(pid)

    db.upsert_session_workspace(session_id, ws.to_json())
    _ws_cache.pop(session_id, None)


def delete_subprocess(
    session_id: str,
    parent_process_id: str,
    node_id: str,
) -> dict | None:
    """Remove a subprocess node and its linked process. Delegates to delete_node (API compatibility)."""
    ok = delete_node(session_id, node_id, process_id=parent_process_id)
    return {"removed": ok, "node_id": node_id}


def delete_node(session_id: str, node_id: str, process_id: str | None = None) -> bool:
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, pid)
    node = graph.get_step(node_id)
    if not node:
        return False
    if node.get("type") in ("start", "end"):
        return False

    if node.get("type") == "subprocess":
        _teardown_linked_subprocess(session_id, pid, node["id"])  # page id = node id

    graph.data["nodes"] = [n for n in graph.nodes if n.get("id") != node_id]
    graph.data["edges"] = [e for e in graph.edges if e.get("from") != node_id and e.get("to") != node_id]
    _persist(session_id, pid)
    _refresh_workspace_summary(session_id, pid)
    return True


def _next_global_subprocess_id(graph: ProcessGraph) -> str:
    """Return next S<n> id for a subprocess on the global map (S8, S9, ...)."""
    max_n = 0
    for node in graph.nodes:
        nid = node.get("id") or ""
        if re.match(r"^S\d+$", nid):
            max_n = max(max_n, int(nid[1:]))
    return f"S{max_n + 1}"


def _next_nested_subprocess_id(graph: ProcessGraph, parent_pid: str) -> str:
    """Return next hierarchical subprocess id under parent (e.g. S1 -> S1.1, S1.1 -> S1.1.1)."""
    prefix = parent_pid + "."
    max_suffix = 0
    for nid in graph.all_step_ids():
        if not nid.startswith(prefix):
            continue
        rest = nid[len(prefix):]
        if rest.isdigit():
            max_suffix = max(max_suffix, int(rest))
    return prefix + str(max_suffix + 1)


def _rename_step_in_graph(graph: ProcessGraph, old_id: str, new_id: str) -> None:
    """Rename a node id throughout the graph (nodes, edges)."""
    node = graph.get_step(old_id)
    if not node:
        return
    node["id"] = new_id
    for e in graph.edges:
        if e.get("from") == old_id:
            e["from"] = new_id
        if e.get("to") == old_id:
            e["to"] = new_id


def _looks_like_global_map_step(step_id: str) -> bool:
    """True if step_id is on the global map (global_start, global_end, S1..S7)."""
    if not step_id:
        return False
    if step_id in ("global_start", "global_end"):
        return True
    if step_id.startswith("S") and step_id[1:].isdigit():
        return True
    return False


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
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, pid)
    ids = graph.all_step_ids()
    if source not in ids or target not in ids:
        if pid != DEFAULT_PROCESS_ID and (
            _looks_like_global_map_step(source) or _looks_like_global_map_step(target)
        ):
            graph = _get_graph(session_id, DEFAULT_PROCESS_ID)
            ids = graph.all_step_ids()
            if source in ids and target in ids:
                pid = DEFAULT_PROCESS_ID
            else:
                return None
        else:
            return None
    existing = graph.get_flow(source, target)
    if existing:
        if label:
            existing["label"] = label
        if source_handle:
            existing["source_handle"] = source_handle
        if target_handle:
            existing["target_handle"] = target_handle
        _persist(session_id, pid)
        return {"from": source, "to": target, "label": existing.get("label", "")}
    edge: dict[str, Any] = {"from": source, "to": target, "label": label or ""}
    if source_handle:
        edge["source_handle"] = source_handle
    if target_handle:
        edge["target_handle"] = target_handle
    graph.edges.append(edge)
    _persist(session_id, pid)
    return {"from": source, "to": target, "label": edge.get("label", "")}


def update_edge(session_id: str, source: str, target: str, updates: dict, process_id: str | None = None) -> dict | None:
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, pid)
    edge = graph.get_flow(source, target)
    if not edge:
        if pid != DEFAULT_PROCESS_ID and (
            _looks_like_global_map_step(source) or _looks_like_global_map_step(target)
        ):
            graph = _get_graph(session_id, DEFAULT_PROCESS_ID)
            edge = graph.get_flow(source, target)
            if edge:
                pid = DEFAULT_PROCESS_ID
        if not edge:
            return None
    if "label" in updates:
        edge["label"] = updates["label"]
    _persist(session_id, pid)
    return {"from": source, "to": target, "label": edge.get("label", "")}


def delete_edge(session_id: str, source: str, target: str, process_id: str | None = None) -> bool:
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, pid)
    for i, e in enumerate(graph.edges):
        if e.get("from") == source and e.get("to") == target:
            graph.edges.pop(i)
            _persist(session_id, pid)
            return True
    if pid != DEFAULT_PROCESS_ID and (
        _looks_like_global_map_step(source) or _looks_like_global_map_step(target)
    ):
        graph = _get_graph(session_id, DEFAULT_PROCESS_ID)
        for i, e in enumerate(graph.edges):
            if e.get("from") == source and e.get("to") == target:
                graph.edges.pop(i)
                _persist(session_id, DEFAULT_PROCESS_ID)
                return True
    return False


def validate_graph(session_id: str, process_id: str | None = None) -> dict:
    graph = _get_graph(session_id, process_id)
    ids = graph.all_step_ids()
    issues = []
    for e in graph.edges:
        if e.get("from") not in ids:
            issues.append(f"Edge source '{e.get('from')}' is not a valid node id.")
        if e.get("to") not in ids:
            issues.append(f"Edge target '{e.get('to')}' is not a valid node id.")
    return {"valid": len(issues) == 0, "issues": issues}


def _next_lane_id(graph: ProcessGraph) -> str:
    existing = {ln.get("id") for ln in graph.lanes}
    n = 1
    while f"Lane_{n}" in existing:
        n += 1
    return f"Lane_{n}"


def add_lane(session_id: str, lane_data: dict, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    if not graph.lanes:
        return None  # New format: single implicit lane, no add
    name = (lane_data.get("name") or "").strip() or "New phase"
    description = (lane_data.get("description") or "").strip()
    lane_id = _next_lane_id(graph)
    lane: dict[str, Any] = {
        "id": lane_id,
        "name": name,
        "description": description,
        "node_refs": [],
    }
    graph.data.setdefault("lanes", []).append(lane)
    _persist(session_id, process_id)
    return {"id": lane_id, "name": name, "description": description, "node_refs": []}


def update_lane(session_id: str, lane_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    graph = _get_graph(session_id, process_id)
    if not graph.lanes:
        return None
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
    if not graph.lanes:
        return False
    lane = graph.get_lane(lane_id)
    if not lane:
        return False
    refs = list(lane.get("node_refs", []))
    for nid in refs:
        delete_node(session_id, nid, process_id=process_id)
    graph.data["lanes"] = [ln for ln in graph.lanes if ln.get("id") != lane_id]
    _persist(session_id, process_id)
    return True


def reorder_lanes(session_id: str, lane_ids: list[str], process_id: str | None = None) -> bool:
    graph = _get_graph(session_id, process_id)
    if not graph.lanes:
        return False
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
    node = graph.get_step(node_id)
    if not node:
        return None
    if position is not None and 0 <= position <= len(graph.nodes):
        order = [n["id"] for n in graph.nodes if n.get("id") != node_id]
        order.insert(min(position, len(order)), node_id)
        graph.step_order = order
        _persist(session_id, process_id)
    return get_node(session_id, node_id, process_id=process_id)


def reorder_steps(session_id: str, lane_id: str, ordered_ids: list[str], process_id: str | None = None) -> bool:
    graph = _get_graph(session_id, process_id)
    current = set(graph.step_order)
    if set(ordered_ids) != current or len(ordered_ids) != len(graph.nodes):
        return False
    graph.step_order = list(ordered_ids)
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
    """Reset to baseline. If resetting the root (global) process, restore entire session (all pages + workspace) so subprocess links work again."""
    pid = _normalize_process_id(process_id)
    if pid == DEFAULT_PROCESS_ID:
        db.force_clone_baseline_to_session(session_id)
        _ws_cache.pop(session_id, None)
        for key in list(_cache):
            if key[0] == session_id:
                del _cache[key]
        baseline_json = db.get_baseline_json(pid) or db.get_baseline_json(DEFAULT_PROCESS_ID)
        if baseline_json is None:
            raise RuntimeError(f"Baseline not found for process_id={pid}")
        return baseline_json
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
    """Batch update node positions from drag-and-drop."""
    graph = _get_graph(session_id, process_id)
    changed = False
    for node_id, pos in positions.items():
        node = graph.get_step(node_id)
        if node and isinstance(pos, dict):
            node["position"] = {"x": pos.get("x", 0), "y": pos.get("y", 0)}
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

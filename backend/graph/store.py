"""Session-scoped JSON-native process store.

Backed by in-memory SQLite (db module).  A cache of parsed ProcessGraph
objects avoids re-parsing JSON on every request within a session.
"""
from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger("consularis.store")

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


def invalidate_session_cache(session_id: str) -> None:
    """Drop in-memory graph and workspace cache for a session so the next fetch reads from DB."""
    _ws_cache.pop(session_id, None)
    for key in list(_cache):
        if key[0] == session_id:
            del _cache[key]


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
    """Write the cached graph back to DB. History/undo is managed client-side."""
    pid = _normalize_process_id(process_id)
    key = (session_id, pid)
    graph = _cache.get(key)
    if graph is None:
        return
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


def _sync_subprocess_name_to_workspace(session_id: str, subprocess_id: str, new_name: str) -> None:
    """Keep subprocess display name consistent across workspace and subprocess graph."""
    normalized_name = (new_name or "").strip()
    if not normalized_name:
        return
    try:
        ws = _get_workspace(session_id)
        procs = ws.data.get("process_tree", {}).get("processes", {})
        if subprocess_id in procs:
            procs[subprocess_id]["name"] = normalized_name
            db.upsert_session_workspace(session_id, ws.to_json())
            _ws_cache.pop(session_id, None)
    except Exception:
        logger.warning(
            "_sync_subprocess_name_to_workspace: workspace sync failed for session_id=%s subprocess_id=%s",
            session_id,
            subprocess_id,
            exc_info=True,
        )

    try:
        subprocess_graph = _get_graph(session_id, subprocess_id)
        subprocess_graph.name = normalized_name
        _persist(session_id, subprocess_id)
    except Exception:
        logger.warning(
            "_sync_subprocess_name_to_workspace: subprocess graph sync failed for session_id=%s subprocess_id=%s",
            session_id,
            subprocess_id,
            exc_info=True,
        )


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
    # Do not overwrite root process name on load: session workspace is source of truth (user/agent may have renamed it). Branding only runs on first clone above.
    _ws_cache[session_id] = ws
    return ws


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_graph_json(session_id: str, process_id: str | None = None) -> str:
    graph = _get_graph(session_id, process_id)
    return graph.to_json()


def inject_lanes_for_client(data: dict, process_id: str) -> dict:
    """Inject process_id and synthetic default lanes into a graph dict for the UI."""
    data = dict(data)
    data["process_id"] = process_id
    if not data.get("lanes"):
        data["lanes"] = [{
            "id": "default",
            "name": data.get("name", ""),
            "description": "",
            "node_refs": [n["id"] for n in data.get("nodes", []) if n.get("id")],
        }]
    return data


def get_graph_dict_for_client(session_id: str, process_id: str | None = None) -> dict[str, Any]:
    """Return graph as dict with process_id and synthetic lanes for UI (if not already present)."""
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, process_id)
    return inject_lanes_for_client(dict(graph.data), pid)


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
    # Custom/freeform ids (e.g. pokemon_store_start): fall back to root process
    try:
        ws = _get_workspace(session_id)
        root_id = ws.data.get("process_tree", {}).get("root", "global")
        return root_id if root_id in pids else None
    except Exception:
        return "global" if "global" in pids else None


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


def get_graph_summary(session_id: str, process_id: str | None = None, *, include_automation_notes: bool = False) -> str:
    """Compact step summary + edges for LLM context. When include_automation_notes is True, appends automation_notes per step (for the analyzer LLM)."""
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
        if include_automation_notes:
            notes = _safe_str(attrs.get("automation_notes"))
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
        logger.warning("get_graph_summary: workspace lookup failed for session_id=%s", session_id, exc_info=True)
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


def get_full_graph_summary(session_id: str, *, include_automation_notes: bool = False) -> str:
    """Return summaries for all processes in the workspace tree (any depth) for full context. When include_automation_notes is True, each step includes its automation_notes (for the analyzer LLM)."""
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
        summary = get_graph_summary(session_id, process_id=pid, include_automation_notes=include_automation_notes)
        header = f"--- {pid} ({name}) ---"
        if path:
            header += f"\nPath: {path}"
        parts.append(f"{header}\n{summary}")
    return "\n\n".join(parts)


def get_full_graph_summary_for_analysis(session_id: str) -> str:
    """Convenience wrapper: full graph summary with automation_notes included."""
    return get_full_graph_summary(session_id, include_automation_notes=True)


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
            auto_key = _classify_automation(attrs.get("automation_potential"))
            if auto_key == "high":
                high += 1
            elif auto_key == "medium":
                medium += 1
            elif auto_key == "low":
                low += 1
            else:
                none += 1
        if step_count_here > 0:
            processes_with_steps += 1
    total_steps = high + medium + low + none
    if total_steps:
        raw = (high * _AUTOMATION_WEIGHTS["high"] + medium * _AUTOMATION_WEIGHTS["medium"] + low * _AUTOMATION_WEIGHTS["low"]) / total_steps
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


_AUTOMATION_WEIGHTS = {"high": 100, "medium": 60, "low": 30, "none": 0}
TOP_ISSUES_LIMIT = 10
RESOLVE_STEP_MIN_SCORE = 0.55


def _classify_automation(raw: str) -> str:
    """Normalize an automation_potential string to one of: high, medium, low, none."""
    v = (raw or "").strip().upper()
    if "HIGH" in v or v == "H":
        return "high"
    if "MEDIUM" in v or "MED" in v or v == "M":
        return "medium"
    if "LOW" in v or v == "L":
        return "low"
    return "none"


def _classify_current_state(raw: str) -> str:
    """Normalize a current_state string to one of: manual, semi_automated, automated, unknown."""
    v = (raw or "").strip().lower().replace(" ", "_")
    if "semi" in v:
        return "semi_automated"
    if "manual" in v:
        return "manual"
    if "automated" in v:
        return "automated"
    return "unknown"


def _parse_float_from_attr(val: Any) -> float:
    """Parse a numeric value from step attributes (e.g. '5.00 EUR', '43800', 3.5)."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return 0.0
    # Strip currency or units (e.g. "5.00 EUR", "15 min")
    for sep in (" ", "\t"):
        if sep in s:
            s = s.split(sep)[0]
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def get_report_metrics(session_id: str) -> dict[str, Any]:
    """Compute full report metrics: totals, per_process, per_step, distributions, top_issues.
    Used by the Company Process Intelligence Report."""
    _ws_cache.pop(session_id, None)
    for key in list(_cache):
        if key[0] == session_id:
            del _cache[key]
    ws = _get_workspace(session_id)
    root_id = ws.data.get("process_tree", {}).get("root", DEFAULT_PROCESS_ID)
    procs = ws.data.get("process_tree", {}).get("processes", {})
    order = _all_process_ids_in_tree_order(ws, root_id)

    totals_annual_cost = 0.0
    totals_annual_volume = 0.0
    total_weighted_error = 0.0
    step_count = 0
    decision_count = 0
    per_process: list[dict[str, Any]] = []
    per_step: list[dict[str, Any]] = []
    dist_automation: dict[str, int] = {"high": 0, "medium": 0, "low": 0, "none": 0}
    dist_current_state: dict[str, int] = {"manual": 0, "semi_automated": 0, "automated": 0, "unknown": 0}
    steps_for_issues: list[dict[str, Any]] = []  # id, process_id, name, annual_cost, error_rate, annual_volume, current_state, automation_potential

    for pid in order:
        if pid == root_id:
            # Root often has no steps (only subprocess refs); still count if it has steps
            pass
        try:
            graph = _get_graph(session_id, pid)
        except Exception:
            continue
        info = procs.get(pid) or {}
        proc_name = info.get("name", graph.name or pid)
        owner = info.get("owner", "")
        category = info.get("category", "")
        criticality = info.get("criticality", "")

        proc_annual_cost = 0.0
        proc_annual_volume = 0.0
        proc_error_sum = 0.0
        proc_error_weight = 0.0
        proc_automation: dict[str, int] = {"high": 0, "medium": 0, "low": 0, "none": 0}
        proc_steps: list[dict[str, Any]] = []

        for node in graph.nodes:
            ntype = node.get("type", "")
            if ntype in ("start", "end"):
                continue
            if ntype == "decision":
                decision_count += 1
                continue
            if ntype != "step":
                continue
            step_count += 1
            attrs = _node_attrs(node)
            node_id = node.get("id", "")
            name = _safe_str(attrs.get("name"))
            actor = _safe_str(attrs.get("actor"))
            duration = _safe_str(attrs.get("duration_min"))
            frequency = _safe_str(attrs.get("frequency"))
            cost_per = _parse_float_from_attr(attrs.get("cost_per_execution"))
            volume = _parse_float_from_attr(attrs.get("annual_volume"))
            err = _parse_float_from_attr(attrs.get("error_rate_percent"))
            auto_key = _classify_automation(attrs.get("automation_potential"))
            state_key = _classify_current_state(attrs.get("current_state"))

            annual_cost = cost_per * volume if volume else 0.0
            totals_annual_cost += annual_cost
            totals_annual_volume += volume
            total_weighted_error += err * volume
            proc_annual_cost += annual_cost
            proc_annual_volume += volume
            proc_error_sum += err * volume
            proc_error_weight += volume
            dist_automation[auto_key] = dist_automation.get(auto_key, 0) + 1
            dist_current_state[state_key] = dist_current_state.get(state_key, 0) + 1
            proc_automation[auto_key] = proc_automation.get(auto_key, 0) + 1

            pain_points = attrs.get("pain_points")
            if isinstance(pain_points, list):
                pain_points = list(pain_points)
            else:
                pain_points = []
            risks = attrs.get("risks")
            if isinstance(risks, list):
                risks = list(risks)
            else:
                risks = []

            step_entry: dict[str, Any] = {
                "id": node_id,
                "name": name,
                "process_id": pid,
                "actor": actor,
                "duration_min": duration,
                "frequency": frequency,
                "annual_volume": volume,
                "cost_per_execution": cost_per,
                "annual_cost": annual_cost,
                "error_rate_percent": err,
                "automation_potential": auto_key,
                "current_state": state_key,
                "pain_points": pain_points,
                "risks": risks,
            }
            per_step.append(step_entry)
            proc_steps.append(step_entry)
            steps_for_issues.append({
                "id": node_id,
                "process_id": pid,
                "name": name,
                "annual_cost": annual_cost,
                "error_rate_percent": err,
                "annual_volume": volume,
                "current_state": state_key,
                "automation_potential": auto_key,
            })

        avg_error = (proc_error_sum / proc_error_weight) if proc_error_weight else 0.0
        per_process.append({
            "id": pid,
            "name": proc_name,
            "owner": owner,
            "category": category,
            "criticality": criticality,
            "step_count": len(proc_steps),
            "annual_cost": round(proc_annual_cost, 2),
            "annual_volume": int(proc_annual_volume),
            "avg_error_rate": round(avg_error, 2),
            "automation_breakdown": dict(proc_automation),
            "steps": proc_steps,
        })

    weighted_avg_error = (total_weighted_error / totals_annual_volume) if totals_annual_volume else 0.0
    existing_metrics = get_analysis_metrics(session_id)
    overall_score = existing_metrics.get("overall_score", 0)

    steps_for_issues.sort(key=lambda x: x["error_rate_percent"], reverse=True)
    highest_error_steps = [{"id": s["id"], "process_id": s["process_id"], "name": s["name"], "error_rate_percent": s["error_rate_percent"]} for s in steps_for_issues[:TOP_ISSUES_LIMIT]]
    steps_for_issues.sort(key=lambda x: x["annual_cost"], reverse=True)
    highest_cost_steps = [{"id": s["id"], "process_id": s["process_id"], "name": s["name"], "annual_cost": s["annual_cost"]} for s in steps_for_issues[:TOP_ISSUES_LIMIT]]
    manual_high_volume = [s for s in steps_for_issues if s["current_state"] == "manual" and s["annual_volume"] > 0]
    manual_high_volume.sort(key=lambda x: x["annual_volume"], reverse=True)
    manual_high_volume_steps = [{"id": s["id"], "process_id": s["process_id"], "name": s["name"], "annual_volume": s["annual_volume"]} for s in manual_high_volume[:TOP_ISSUES_LIMIT]]

    return {
        "workspace_name": ws.data.get("name", ""),
        "totals": {
            "annual_cost": round(totals_annual_cost, 2),
            "annual_volume": int(totals_annual_volume),
            "weighted_avg_error_rate": round(weighted_avg_error, 2),
            "automation_readiness_score": overall_score,
            "step_count": step_count,
            "process_count": len(order),
            "decision_count": decision_count,
        },
        "per_process": per_process,
        "per_step": per_step,
        "distributions": {
            "automation_potential": dist_automation,
            "current_state": dist_current_state,
        },
        "top_issues": {
            "highest_error_steps": highest_error_steps,
            "highest_cost_steps": highest_cost_steps,
            "manual_high_volume_steps": manual_high_volume_steps,
        },
        "categories": existing_metrics.get("categories", {}),
        "counts": existing_metrics.get("counts", {}),
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
            if score >= RESOLVE_STEP_MIN_SCORE:
                results.append((score, {
                    "type": stype, "node_id": step_id, "name": name,
                    "process_id": pid,
                }))
    results.sort(key=lambda x: x[0], reverse=True)
    return [item for _score, item in results[:TOP_ISSUES_LIMIT]]


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
    """New format: id, name, nodes, edges. Start/end ids = {process_id}_start, {process_id}_end. No edge between start and end — user or agent adds steps and edges."""
    start_id = f"{process_id}_start"
    end_id = f"{process_id}_end"
    return {
        "id": process_id,
        "name": name,
        "nodes": [
            {"id": start_id, "type": "start", "position": {"x": 280, "y": 78}},
            {"id": end_id, "type": "end", "position": {"x": 740, "y": 78}},
        ],
        "edges": [],
    }


def update_node(session_id: str, node_id: str, updates: dict, process_id: str | None = None) -> dict | None:
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, pid)
    incoming_updates = dict(updates or {})
    dropped_keys = sorted(k for k in incoming_updates.keys() if k not in _UPDATE_NODE_ALLOWED)
    if dropped_keys:
        logger.warning(
            "update_node dropped unsupported keys session_id=%s process_id=%s node_id=%s keys=%s",
            session_id,
            pid,
            node_id,
            dropped_keys,
        )
    updates = {k: v for k, v in incoming_updates.items() if k in _UPDATE_NODE_ALLOWED}
    if "risks" in updates and isinstance(updates["risks"], list):
        updates["risks"] = _dedupe_risks(updates["risks"])
    node = graph.get_step(node_id)
    if not node:
        return None
    renamed_to: str | None = None
    if "name" in updates:
        renamed_to = updates.pop("name", node.get("name", ""))
        node["name"] = renamed_to
    attrs = node.setdefault("attributes", {})
    for key, val in updates.items():
        attrs[key] = val
    _persist(session_id, pid)
    _refresh_workspace_summary(session_id, pid)
    if node.get("type") == "subprocess" and renamed_to is not None:
        _sync_subprocess_name_to_workspace(session_id, node_id, renamed_to)
    return get_node(session_id, node_id, process_id=pid)


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
    return step_id.startswith("S") and step_id[1:].isdigit()


def _resolve_edge_graph(
    session_id: str, source: str, target: str, process_id: str | None = None
) -> tuple[ProcessGraph, str] | None:
    """Find the graph and pid that contains both source and target, falling back to the global map."""
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, pid)
    ids = graph.all_step_ids()
    if source in ids and target in ids:
        return graph, pid
    if pid != DEFAULT_PROCESS_ID and (
        _looks_like_global_map_step(source) or _looks_like_global_map_step(target)
    ):
        graph = _get_graph(session_id, DEFAULT_PROCESS_ID)
        ids = graph.all_step_ids()
        if source in ids and target in ids:
            return graph, DEFAULT_PROCESS_ID
    return None


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
    resolved = _resolve_edge_graph(session_id, source, target, process_id)
    if not resolved:
        return None
    graph, pid = resolved
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
    resolved = _resolve_edge_graph(session_id, source, target, process_id)
    if not resolved:
        return None
    graph, pid = resolved
    edge = graph.get_flow(source, target)
    if not edge:
        return None
    if "label" in updates:
        edge["label"] = updates["label"]
    _persist(session_id, pid)
    return {"from": source, "to": target, "label": edge.get("label", "")}


def delete_edge(session_id: str, source: str, target: str, process_id: str | None = None) -> bool:
    resolved = _resolve_edge_graph(session_id, source, target, process_id)
    if not resolved:
        return False
    graph, pid = resolved
    for i, e in enumerate(graph.edges):
        if e.get("from") == source and e.get("to") == target:
            graph.edges.pop(i)
            _persist(session_id, pid)
            return True
    return False



def rename_process(session_id: str, new_name: str, process_id: str | None = None) -> bool:
    pid = _normalize_process_id(process_id)
    graph = _get_graph(session_id, pid)
    graph.name = (new_name or "").strip() or graph.name
    _persist(session_id, pid)
    # Sync process name into workspace manifest so directory/header/minimap show the new name
    try:
        _ws_cache.pop(session_id, None)  # Load fresh from DB so we don't mutate stale cache
        ws = _get_workspace(session_id)
        procs = ws.data.get("process_tree", {}).get("processes", {})
        if pid in procs:
            procs[pid]["name"] = graph.name
            db.upsert_session_workspace(session_id, ws.to_json())
        _ws_cache.pop(session_id, None)
    except Exception:
        logger.warning("rename_process: workspace sync failed for session_id=%s pid=%s", session_id, pid, exc_info=True)
    return True


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

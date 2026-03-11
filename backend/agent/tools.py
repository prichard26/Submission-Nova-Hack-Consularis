"""Tool schemas and dispatch. Id-only tools; process inferred from id. Agent has get_full_graph to see everything and chooses new ids (next number) when adding."""
import json
import logging
import re
from typing import Callable

from graph.model import LIST_METADATA_KEYS
from graph.store import (
    add_edge as store_add_edge,
    add_node as store_add_node,
    delete_edge as store_delete_edge,
    delete_node as store_delete_node,
    get_full_graph as store_get_full_graph,
    get_process_id_for_proposed_id,
    get_process_id_for_step,
    insert_subprocess_between as store_insert_subprocess_between,
    insert_step_between as store_insert_step_between,
    rename_process as store_rename_process,
    update_edge as store_update_edge,
    update_node as store_update_node,
)

ToolHandler = Callable[[str, dict, str | None, str | None], str]
logger = logging.getLogger("consularis.agent")


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_full_graph",
            "description": "Return the full graph: every process with its node ids and edges (from, to, label). Call this to see all existing ids before adding or editing. Use the structure to choose the next id when adding (e.g. after P1.3 use P1.4; after S1 use S1.1 for nested subprocess).",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "Update a node by id. Process inferred from id. Use strings for all values. Fields: name, actor, duration_min, cost_per_execution, description, inputs, outputs, risks, automation_potential, automation_notes, current_state, frequency, annual_volume, error_rate_percent, current_systems, data_format, external_dependencies, regulatory_constraints, sla_target, pain_points.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Node id (e.g. P1.1, S1.1, G1.1). Must exist in the graph."},
                    "updates": {
                        "type": "object",
                        "description": "Fields to set. Use strings; lists as arrays of strings.",
                        "additionalProperties": True,
                    },
                },
                "required": ["id", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_edge",
            "description": "Connect two nodes. Process inferred from source/target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source node id."},
                    "target": {"type": "string", "description": "Target node id."},
                    "label": {"type": "string", "description": "Optional label."},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_edge",
            "description": "Remove an edge. Process inferred from source/target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source node id."},
                    "target": {"type": "string", "description": "Target node id."},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_edge",
            "description": "Update an edge by source and target ids. Process inferred from source/target. updates: { label: string }.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source node id."},
                    "target": {"type": "string", "description": "Target node id."},
                    "updates": {
                        "type": "object",
                        "description": "Object with label (string).",
                        "additionalProperties": True,
                    },
                },
                "required": ["source", "target", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_node",
            "description": "Add a node. You supply the new node's id (must not exist yet). Use get_full_graph to see existing ids; pick the next number (e.g. after P1.3 use P1.4; in S1 use S1.1 for first nested subprocess; on global use S8 for next top-level subprocess). Type: step | decision | subprocess.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The new node's id (e.g. P1.4, G1.1, S1.1, S8). Must follow naming and not already exist."},
                    "type": {"type": "string", "description": "step, decision, or subprocess.", "enum": ["step", "decision", "subprocess"]},
                    "name": {"type": "string", "description": "Optional display name."},
                },
                "required": ["id", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_step_between",
            "description": "Add a new step or decision between two consecutive steps. The new step gets the ordinal between them (e.g. P1.2); existing steps shift (old P1.2 becomes P1.3, etc.). Use when the user says 'add ... between X and Y'. Also use when the user says 'add a step after [step name]' and that step has a step or decision as its successor (check the graph); resolve step names to ids using the full graph: match node name to get after_id, then use edges to get the successor as before_id. Arguments: after_id, before_id (consecutive existing ids), name, optional type (step | decision). Process inferred from after_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "after_id": {"type": "string", "description": "Id of the step that will precede the new step (e.g. P1.1)."},
                    "before_id": {"type": "string", "description": "Id of the step that will follow the new step (e.g. P1.2); must be the next step after after_id in the graph."},
                    "name": {"type": "string", "description": "Display name for the new step."},
                    "type": {"type": "string", "description": "step or decision.", "enum": ["step", "decision"]},
                    "process_id": {"type": "string", "description": "Optional process id (e.g. S1). Inferred from after_id if omitted."},
                },
                "required": ["after_id", "before_id", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_subprocess_between",
            "description": "Insert a subprocess on the global map between two consecutive subprocess nodes (e.g. between S6 and S7). The new subprocess takes the id of before_id (new becomes S7) and existing S7 (and following) shift to S8, S9, etc. Use this when the user explicitly asks to add a subprocess between two existing subprocesses on the global map.",
            "parameters": {
                "type": "object",
                "properties": {
                    "after_id": {"type": "string", "description": "Existing global subprocess id that will precede the new subprocess (e.g. S6)."},
                    "before_id": {"type": "string", "description": "Existing global subprocess id that will follow the new subprocess (e.g. S7). Must be consecutive after after_id on the global map."},
                    "name": {"type": "string", "description": "Display name for the new subprocess."},
                },
                "required": ["after_id", "before_id", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Remove a node by id. Cannot delete start/end nodes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Node id (e.g. P1.1, S1.1, S2)."},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_process",
            "description": "Rename a process page by process id. Use id 'global' for the top-level map; use S1, S1.1, etc. for subprocesses. Updates graph name and workspace manifest (header/directory).",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Process id: 'global' for the global map, or S1, S1.1, S1.2, etc. for subprocess pages."},
                    "name": {"type": "string", "description": "New process display name."},
                },
                "required": ["id", "name"],
            },
        },
    },
]
# Planner tool: propose_plan only. Execution runs when user clicks Apply plan (run_chat_confirm).
PLANNER_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "propose_plan",
            "description": "REQUIRED for any graph change. Call this with concrete steps; the user sees the plan and an Apply button. Without this call, no changes can happen — text alone does not modify the graph. Never say changes were made without calling this tool first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {"type": "string", "description": "Optional short summary of what the plan does."},
                    "steps": {
                        "type": "array",
                        "description": "List of {tool_name, arguments}. Ids only.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {"type": "string"},
                                "arguments": {"type": "object", "additionalProperties": True},
                            },
                        },
                    },
                },
                "required": ["steps"],
            },
        },
    },
]

def _tool_ok(data: dict | None = None) -> str:
    result = {"ok": True}
    if data:
        result.update(data)
    return json.dumps(result)


def _tool_error(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg})


def _updates_to_strings(updates: dict, list_keys: frozenset) -> dict:
    """Coerce update values to strings so the graph always stores strings. Lists become list of strings."""
    out = {}
    for k, v in updates.items():
        if v is None:
            out[k] = ""
        elif k in list_keys and isinstance(v, list):
            out[k] = [str(x).strip() for x in v]
        else:
            out[k] = str(v).strip() if v != "" else ""
    return out


def _debug_tool_call(
    session_id: str,
    turn_id: str | None,
    name: str,
    arguments: dict,
    process_id_from_runtime: str | None,
    resolved_pid: str | None,
) -> None:
    """Log a readable line for every agent tool call."""
    args_copy = {k: v for k, v in arguments.items() if v is not None and v != ""}
    args_str = ", ".join(f"{k}={v!r}" for k, v in sorted(args_copy.items()))
    logger.info(
        "[%s] TOOL_CALL name=%s session_id=%s process_id(runtime)=%s resolved_process_id=%s args=%s",
        turn_id or "-",
        name,
        session_id,
        process_id_from_runtime,
        resolved_pid,
        args_str,
    )


def _resolve_pid(session_id: str, arguments: dict):
    pid_from_args = arguments.get("process_id")

    def resolve_pid(step_or_location_id: str) -> str | None:
        if pid_from_args:
            return pid_from_args
        return get_process_id_for_step(session_id, step_or_location_id)

    return pid_from_args, resolve_pid


def _edge_endpoints(arguments: dict) -> tuple[str, str]:
    source = (
        arguments.get("source")
        or arguments.get("from")
        or arguments.get("source_id")
        or arguments.get("from_id")
        or ""
    )
    target = (
        arguments.get("target")
        or arguments.get("to")
        or arguments.get("target_id")
        or arguments.get("to_id")
        or ""
    )
    return str(source).strip(), str(target).strip()

def _handle_get_full_graph(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    _ = arguments
    _debug_tool_call(session_id, turn_id, "get_full_graph", {}, process_id, process_id)
    data = store_get_full_graph(session_id)
    return json.dumps(data, indent=2, ensure_ascii=False)


def _normalize_update_node_updates(updates: dict) -> dict:
    """Flatten nested attributes so updates.attributes.name -> updates.name (avoids no-op when LLM sends attributes wrapper)."""
    if not updates or not isinstance(updates, dict):
        return dict(updates or {})
    if set(updates.keys()) == {"attributes"} and isinstance(updates.get("attributes"), dict):
        return dict(updates["attributes"])
    return dict(updates)


def _handle_update_node(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    pid_from_args, resolve_pid = _resolve_pid(session_id, arguments)
    node_id = arguments.get("id") or arguments.get("step_id")
    raw_updates = arguments.get("updates") or {}
    updates = _normalize_update_node_updates(raw_updates if isinstance(raw_updates, dict) else {})
    pid = resolve_pid(node_id) if node_id else pid_from_args
    _debug_tool_call(session_id, turn_id, "update_node", arguments, process_id, pid)
    if not node_id or not updates:
        return _tool_error("id and updates (object) are required")
    if not pid:
        return _tool_error(f"Process not found for node: {node_id}")
    if "cost" in updates and "cost_per_execution" not in updates:
        updates["cost_per_execution"] = updates.pop("cost")
    if "duration" in updates and "duration_min" not in updates:
        updates["duration_min"] = updates.pop("duration")
    if "time" in updates and "duration_min" not in updates:
        updates["duration_min"] = updates.pop("time")
    updates = _updates_to_strings(updates, LIST_METADATA_KEYS)
    result = store_update_node(session_id, node_id, updates, process_id=pid)
    if result is None:
        return _tool_error(f"Step not found: {node_id}")
    return _tool_ok({"node": result})


def _handle_add_edge(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    pid_from_args, resolve_pid = _resolve_pid(session_id, arguments)
    source, target = _edge_endpoints(arguments)
    pid = resolve_pid(source) if source else None
    if not pid and target:
        pid = resolve_pid(target)
    pid = pid or pid_from_args
    _debug_tool_call(session_id, turn_id, "add_edge", arguments, process_id, pid)
    if not source or not target:
        return _tool_error("source and target are required")
    if not pid:
        return _tool_error(f"Process not found for edge: {source} -> {target}")
    result = store_add_edge(session_id, source, target, label=arguments.get("label") or "", process_id=pid)
    if result is None:
        return _tool_error(f"Edge not added (step not found or invalid): {source} -> {target}")
    return _tool_ok({"edge": result})


def _handle_delete_edge(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    pid_from_args, resolve_pid = _resolve_pid(session_id, arguments)
    source, target = _edge_endpoints(arguments)
    pid = resolve_pid(source) if source else None
    if not pid and target:
        pid = resolve_pid(target)
    pid = pid or pid_from_args
    _debug_tool_call(session_id, turn_id, "delete_edge", arguments, process_id, pid)
    if not source or not target:
        return _tool_error("source and target are required")
    if not pid:
        return _tool_error(f"Process not found for edge: {source} -> {target}")
    ok = store_delete_edge(session_id, source, target, process_id=pid)
    if not ok:
        return _tool_error(f"Edge not found: {source} -> {target} (it may already have been removed when a node was deleted)")
    return json.dumps({"ok": True, "removed": True})


def _handle_update_edge(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    pid_from_args, resolve_pid = _resolve_pid(session_id, arguments)
    source, target = _edge_endpoints(arguments)
    updates = arguments.get("updates")
    pid = resolve_pid(source) if source else None
    if not pid and target:
        pid = resolve_pid(target)
    pid = pid or pid_from_args
    _debug_tool_call(session_id, turn_id, "update_edge", arguments, process_id, pid)
    if not source or not target or not isinstance(updates, dict):
        return _tool_error("source, target and updates (object) are required")
    if not pid:
        return _tool_error(f"Process not found for edge: {source} -> {target}")
    edge_updates = {}
    if "label" in updates:
        edge_updates["label"] = str(updates.get("label") or "").strip()
    result = store_update_edge(session_id, source, target, edge_updates, process_id=pid)
    if result is None:
        return _tool_error(f"Edge not found: {source} -> {target}")
    return _tool_ok({"edge": result})


def _handle_add_node(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    new_id = (arguments.get("id") or "").strip()
    step_type = arguments.get("type", "step")
    if step_type not in ("step", "decision", "subprocess"):
        step_type = "step"
    inferred_pid = get_process_id_for_proposed_id(session_id, new_id, step_type) if new_id else None
    pid = process_id or arguments.get("process_id") or inferred_pid or "global"
    _debug_tool_call(session_id, turn_id, "add_node", arguments, process_id, pid)
    if not new_id:
        return _tool_error("id and type are required")
    # Reject P2.3.1-style IDs in top-level processes: steps use one dot only (P2.4 not P2.3.1).
    if step_type in ("step", "decision") and pid and re.match(r"^S\d+$", pid):
        parts = new_id.split(".")
        if len(parts) > 2:
            return _tool_error(
                f"Step IDs in this process use a single suffix (e.g. P2.4). Use the next ordinal, not {new_id!r}."
            )
    name_val = (arguments.get("name") or "").strip()
    if not name_val:
        name_val = "New step" if step_type == "step" else "New decision" if step_type == "decision" else "New subprocess"
    result = store_add_node(session_id, pid, {"id": new_id, "name": name_val, "type": step_type})
    if result is None:
        return _tool_error(f"Could not add node: id may already exist or be invalid (id={new_id!r})")
    return _tool_ok({"node": result})


def _handle_insert_step_between(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    after_id = (arguments.get("after_id") or "").strip()
    before_id = (arguments.get("before_id") or "").strip()
    name_val = (arguments.get("name") or "").strip()
    step_type = arguments.get("type", "step")
    if step_type not in ("step", "decision"):
        step_type = "step"
    pid = (
        process_id
        or arguments.get("process_id")
        or get_process_id_for_proposed_id(session_id, after_id, step_type)
        or get_process_id_for_step(session_id, after_id)
        or get_process_id_for_step(session_id, before_id)
    )
    _debug_tool_call(session_id, turn_id, "insert_step_between", arguments, process_id, pid)
    if not after_id or not before_id:
        return _tool_error("after_id and before_id are required")
    if not name_val:
        name_val = "New step" if step_type == "step" else "New decision"
    if not pid:
        return _tool_error("Could not determine process; specify process_id or use after_id/before_id that exist in the graph")
    result = store_insert_step_between(
        session_id, pid, after_id, before_id, name_val, step_type=step_type
    )
    if result is None:
        return _tool_error(
            "insert_step_between failed: after_id and before_id must be consecutive steps in the same process"
        )
    return _tool_ok({"node": result["node"], "renames": result.get("renames", {})})


def _handle_insert_subprocess_between(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    _ = process_id  # always global
    after_id = (arguments.get("after_id") or "").strip()
    before_id = (arguments.get("before_id") or "").strip()
    name_val = (arguments.get("name") or "").strip()
    _debug_tool_call(session_id, turn_id, "insert_subprocess_between", arguments, process_id, "global")
    if not after_id or not before_id or not name_val:
        return _tool_error("after_id, before_id, and name are required")
    result = store_insert_subprocess_between(session_id, after_id, before_id, name_val)
    if result is None:
        return _tool_error("insert_subprocess_between failed: after_id and before_id must be consecutive subprocesses on the global map")
    return _tool_ok({"node": result})


def _handle_delete_node(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    pid_from_args, resolve_pid = _resolve_pid(session_id, arguments)
    node_id = arguments.get("id") or arguments.get("node_id")
    pid = resolve_pid(node_id) if node_id else pid_from_args
    _debug_tool_call(session_id, turn_id, "delete_node", arguments, process_id, pid)
    if not node_id:
        return _tool_error("id is required")
    if not pid:
        return _tool_error(f"Process not found for node: {node_id}")
    result = store_delete_node(session_id, node_id, process_id=pid)
    if result is None:
        return _tool_error(f"Node not found or cannot delete (start/end): {node_id}")
    return _tool_ok({"removed": True, "renames": result.get("renames", {})})


def _handle_rename_process(session_id: str, arguments: dict, process_id: str | None, turn_id: str | None) -> str:
    pid = (arguments.get("id") or arguments.get("process_id") or process_id or "").strip()
    new_name = (arguments.get("name") or "").strip()
    _debug_tool_call(session_id, turn_id, "rename_process", arguments, process_id, pid or None)
    if not pid or not new_name:
        return _tool_error("id and name are required")
    ok = store_rename_process(session_id, new_name, process_id=pid)
    if not ok:
        return _tool_error(f"Could not rename process: {pid}")
    return _tool_ok({"process_id": pid, "name": new_name})


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_full_graph": _handle_get_full_graph,
    "update_node": _handle_update_node,
    "add_edge": _handle_add_edge,
    "delete_edge": _handle_delete_edge,
    "update_edge": _handle_update_edge,
    "add_node": _handle_add_node,
    "insert_step_between": _handle_insert_step_between,
    "insert_subprocess_between": _handle_insert_subprocess_between,
    "delete_node": _handle_delete_node,
    "rename_process": _handle_rename_process,
}


def run_tool(
    session_id: str,
    name: str,
    arguments: dict,
    process_id: str | None = None,
    turn_id: str | None = None,
) -> str:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        logger.info("[%s] TOOL_UNKNOWN name=%s session_id=%s", turn_id or "-", name, session_id)
        return json.dumps({"ok": False, "error": f"Unknown tool: {name}"})
    return handler(session_id, arguments, process_id, turn_id)

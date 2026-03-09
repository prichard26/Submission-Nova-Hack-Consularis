"""Tool schemas and dispatch. Id-only tools; process inferred from id. Agent has get_full_graph to see everything and chooses new ids (next number) when adding."""
import json
import logging
from typing import Callable

from graph.model import LIST_METADATA_KEYS
from graph.store import (
    add_edge as store_add_edge,
    add_node as store_add_node,
    delete_edge as store_delete_edge,
    delete_node as store_delete_node,
    get_full_graph as store_get_full_graph,
    get_process_id_for_step,
    update_edge as store_update_edge,
    update_node as store_update_node,
)

ToolHandler = Callable[[str, dict, str | None], str]
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
]
TOOLS = TOOL_SCHEMAS

# Planner tool: propose_plan only. Execution runs when user clicks Apply plan (run_chat_confirm).
PLANNER_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "propose_plan",
            "description": "Propose a plan. Pass steps (list of {tool_name, arguments}). The user sees your plan and an Apply plan button; when they click it, the system runs the steps. You do not run or execute—only propose.",
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

TOOL_HANDLERS: dict[str, ToolHandler] = {}


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
    name: str,
    arguments: dict,
    process_id_from_runtime: str | None,
    resolved_pid: str | None,
) -> None:
    """Print a readable log line for every agent tool call."""
    # Build a compact args summary (skip process_id here, we show it separately)
    args_copy = {k: v for k, v in arguments.items() if v is not None and v != ""}
    args_str = ", ".join(f"{k}={v!r}" for k, v in sorted(args_copy.items()))
    print(
        f"[AGENT TOOL] {name} | session={session_id!r} | "
        f"process_id(runtime)={process_id_from_runtime!r} → resolved={resolved_pid!r} | {args_str}"
    )


def run_tool(session_id: str, name: str, arguments: dict, process_id: str | None = None) -> str:
    # Process is inferred from id when not in arguments (id-only tools)
    pid_from_args = arguments.get("process_id")

    def resolve_pid(step_or_location_id: str) -> str | None:
        if pid_from_args:
            return pid_from_args
        return get_process_id_for_step(session_id, step_or_location_id)

    _debug_tool_call(session_id, name, arguments, process_id, pid_from_args)

    if name == "get_full_graph":
        data = store_get_full_graph(session_id)
        return json.dumps(data, indent=2, ensure_ascii=False)
    if name == "update_node":
        node_id = arguments.get("id") or arguments.get("step_id")
        updates = dict(arguments.get("updates") or {})
        if not node_id or not updates:
            return json.dumps({"ok": False, "error": "id and updates (object) are required"})
        pid = resolve_pid(node_id)
        if not pid:
            return json.dumps({"ok": False, "error": f"Process not found for node: {node_id}"})
        if "cost" in updates and "cost_per_execution" not in updates:
            updates["cost_per_execution"] = updates.pop("cost")
        if "duration" in updates and "duration_min" not in updates:
            updates["duration_min"] = updates.pop("duration")
        if "time" in updates and "duration_min" not in updates:
            updates["duration_min"] = updates.pop("time")
        updates = _updates_to_strings(updates, LIST_METADATA_KEYS)
        result = store_update_node(session_id, node_id, updates, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Step not found: {node_id}"})
        return json.dumps({"ok": True, "node": result})
    if name == "add_edge":
        source = arguments.get("source")
        target = arguments.get("target")
        if not source or not target:
            return json.dumps({"ok": False, "error": "source and target are required"})
        pid = resolve_pid(source) or resolve_pid(target)
        if not pid:
            return json.dumps({"ok": False, "error": f"Process not found for edge: {source} -> {target}"})
        result = store_add_edge(session_id, source, target, label=arguments.get("label") or "", process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Edge not added (step not found or invalid): {source} -> {target}"})
        return json.dumps({"ok": True, "edge": result})
    if name == "delete_edge":
        source = arguments.get("source")
        target = arguments.get("target")
        if not source or not target:
            return json.dumps({"ok": False, "error": "source and target are required"})
        pid = resolve_pid(source) or resolve_pid(target)
        if not pid:
            return json.dumps({"ok": False, "error": f"Process not found for edge: {source} -> {target}"})
        ok = store_delete_edge(session_id, source, target, process_id=pid)
        return json.dumps({"ok": ok, "removed": ok})
    if name == "update_edge":
        source = arguments.get("source")
        target = arguments.get("target")
        updates = arguments.get("updates")
        if not source or not target or not isinstance(updates, dict):
            return json.dumps({"ok": False, "error": "source, target and updates (object) are required"})
        pid = resolve_pid(source) or resolve_pid(target)
        if not pid:
            return json.dumps({"ok": False, "error": f"Process not found for edge: {source} -> {target}"})
        edge_updates = {}
        if "label" in updates:
            edge_updates["label"] = str(updates.get("label") or "").strip()
        result = store_update_edge(session_id, source, target, edge_updates, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Edge not found: {source} -> {target}"})
        return json.dumps({"ok": True, "edge": result})
    if name == "add_node":
        new_id = (arguments.get("id") or "").strip()
        step_type = arguments.get("type", "step")
        if not new_id:
            return json.dumps({"ok": False, "error": "id and type are required"})
        if step_type not in ("step", "decision", "subprocess"):
            step_type = "step"
        name_val = (arguments.get("name") or "").strip()
        if not name_val:
            name_val = "New step" if step_type == "step" else "New decision" if step_type == "decision" else "New subprocess"
        result = store_add_node(session_id, "default", {"id": new_id, "name": name_val, "type": step_type})
        if result is None:
            return json.dumps({"ok": False, "error": f"Could not add node: id may already exist or be invalid (id={new_id!r})"})
        return json.dumps({"ok": True, "node": result})
    if name == "delete_node":
        node_id = arguments.get("id") or arguments.get("node_id")
        if not node_id:
            return json.dumps({"ok": False, "error": "id is required"})
        pid = resolve_pid(node_id)
        if not pid:
            return json.dumps({"ok": False, "error": f"Process not found for node: {node_id}"})
        ok = store_delete_node(session_id, node_id, process_id=pid)
        if not ok:
            return json.dumps({"ok": False, "error": f"Node not found or cannot delete (start/end): {node_id}"})
        return json.dumps({"ok": True, "removed": True})
    logger.info("[AGENT][GRAPH] %s (no handler) session_id=%s", name, session_id)
    return json.dumps({"error": "Unknown tool"})

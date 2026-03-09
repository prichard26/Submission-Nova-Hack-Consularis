"""Tool schemas and dispatch. Step 2 + 3: update_node, edges. Step 4: add_node, delete_node. Multi-agent: planner uses request_execution."""
import json
import logging
from typing import Callable

from graph.model import LIST_METADATA_KEYS
from graph.store import (
    add_edge as store_add_edge,
    add_node as store_add_node,
    delete_edge as store_delete_edge,
    delete_node as store_delete_node,
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
            "name": "update_node",
            "description": "Update a node by id. Process inferred from id. Use strings for all values (e.g. duration_min: '15 min', error_rate_percent: '5', cost_per_execution: '10'). Fields: name, actor, duration_min, cost_per_execution, description, inputs, outputs, risks, automation_potential, automation_notes, current_state, frequency, annual_volume, error_rate_percent, current_systems, data_format, external_dependencies, regulatory_constraints, sla_target, pain_points, called_element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Node id (e.g. P1.1, P7.2, p7.1.1). Process is inferred from it."},
                    "updates": {
                        "type": "object",
                        "description": "Fields to set. Use strings for every value (e.g. '15 min', '5', '10'). Lists (inputs, outputs, risks, etc.) as arrays of strings.",
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
            "description": "Update an edge by source and target ids. Process inferred from source/target. Use strings only: label and condition (e.g. label: 'Yes', condition: 'if approved'; empty string to clear condition).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source node id of the edge."},
                    "target": {"type": "string", "description": "Target node id of the edge."},
                    "updates": {
                        "type": "object",
                        "description": "Use strings: label (e.g. 'Yes'), condition (e.g. 'if approved'; '' to clear).",
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
            "description": "Add a node. location_id must be a node id (e.g. Start_Global, P1, P7.1). Type: step|decision|subprocess. Subprocess gets Start/End automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_id": {"type": "string", "description": "Node id only (e.g. Start_Global, P1, P7.1)"},
                    "type": {"type": "string", "description": "step, decision, or subprocess.", "enum": ["step", "decision", "subprocess"]},
                    "name": {"type": "string", "description": "Optional display name."},
                },
                "required": ["location_id", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Remove a node by its node id (e.g. P1, P2, P7.1). Cannot delete start/end.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Node id (e.g. P1, P2, P7.1)"},
                },
                "required": ["id"],
            },
        },
    },
]
TOOLS = TOOL_SCHEMAS

# Planner tools: propose_plan / request_execution. Steps = list of {tool_name, arguments} (ids only).
PLANNER_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "propose_plan",
            "description": "Propose plan so user can Apply. Pass steps (list of {tool_name, arguments}).",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {"type": "string", "description": "Optional. What to do, in order."},
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
    {
        "type": "function",
        "function": {
            "name": "request_execution",
            "description": "Run plan after user confirmed. Pass steps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {"type": "string", "description": "Optional. What to do, in order."},
                    "steps": {
                        "type": "array",
                        "description": "List of {tool_name, arguments}.",
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
        # Coerce to strings; only pass keys the agent sent so we don't clear the other
        edge_updates = {}
        if "label" in updates:
            edge_updates["label"] = str(updates.get("label") or "").strip()
        if "condition" in updates:
            edge_updates["condition"] = str(updates.get("condition") or "").strip()
        result = store_update_edge(session_id, source, target, edge_updates, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Edge not found: {source} -> {target}"})
        return json.dumps({"ok": True, "edge": result})
    if name == "add_node":
        location_id = arguments.get("location_id")
        step_type = arguments.get("type", "step")
        if not location_id:
            return json.dumps({"ok": False, "error": "location_id and type are required"})
        if step_type not in ("step", "decision", "subprocess"):
            step_type = "step"
        pid = get_process_id_for_step(session_id, location_id)
        if not pid:
            return json.dumps({"ok": False, "error": f"Process not found for location: {location_id}"})
        name_val = (arguments.get("name") or "").strip()
        if not name_val:
            name_val = "New step" if step_type == "step" else "New decision" if step_type == "decision" else "New subprocess"
        if " (" in name_val and name_val.endswith(")"):
            idx = name_val.find(" (")
            prefix = name_val[:idx].strip()
            if prefix and (prefix.startswith("P") and "." in prefix or prefix.startswith("GLOBAL.")):
                name_val = name_val[idx + 2 : -1].strip() or name_val
        result = store_add_node(session_id, "default", {"name": name_val, "type": step_type}, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": "Could not add node (invalid process)"})
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

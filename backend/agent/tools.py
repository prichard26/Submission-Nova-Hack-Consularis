"""Tool schemas and dispatch. Step 2 + 3: update_node, edges. Step 4: add_node, delete_node."""
import json
import logging
from typing import Callable

from graph.store import (
    add_edge as store_add_edge,
    add_node as store_add_node,
    delete_edge as store_delete_edge,
    delete_node as store_delete_node,
    update_edge as store_update_edge,
    update_node as store_update_node,
)

ToolHandler = Callable[[str, dict, str | None], str]
logger = logging.getLogger("consularis.agent")

# Step 2: update_node. Step 3: add_edge, delete_edge, update_edge. Step 4: add_node, delete_node.
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "Update a step (node) in the process graph. Use step id and process_id from the graph in context. Call multiple times per turn to update multiple steps. Format: duration_min with ' min', cost_per_execution with ' EUR'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process containing the step (e.g. Process_P1). Omit for root/current."},
                    "step_id": {"type": "string", "description": "Step id (e.g. P1.1, P2.2)."},
                    "updates": {"type": "object", "description": "Fields to set on the step.", "additionalProperties": True},
                },
                "required": ["step_id", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_edge",
            "description": "Add an edge between two steps in the same process. Use step ids: global map = P1, P2, P3, ... (and Start_Global, End_Global); inside a process = P1.1, P1.2, P1.4, ... Pass process_id (Process_Global or e.g. Process_P1). Same id pattern everywhere.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process that contains both steps (Process_Global for global map; Process_P1 etc. for inside that process)."},
                    "source": {"type": "string", "description": "Source step id (e.g. P1 or P1.1)."},
                    "target": {"type": "string", "description": "Target step id (e.g. P2 or P1.2)."},
                    "label": {"type": "string", "description": "Optional edge label."},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_edge",
            "description": "Remove an edge. Pass process_id and source/target step ids (same scheme: P1, P2 on global; P1.1, P1.2 inside a process).",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process that contains the edge."},
                    "source": {"type": "string", "description": "Source step id (e.g. P1, P1.1)."},
                    "target": {"type": "string", "description": "Target step id (e.g. P2, P1.2)."},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_edge",
            "description": "Update an existing edge's label or condition. Pass process_id and source/target (same id scheme: P1, P2 or P1.1, P1.2).",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process that contains the edge (e.g. Process_Global or Process_P1)."},
                    "source": {"type": "string", "description": "Source step id of the edge."},
                    "target": {"type": "string", "description": "Target step id of the edge."},
                    "updates": {"type": "object", "description": "Fields to set: label, condition.", "additionalProperties": True},
                },
                "required": ["source", "target", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_node",
            "description": "Add a step, decision, or subprocess. Level: global = Process_Global + GLOBAL (new subprocess ids P8, P9, ...); inside = e.g. Process_P1 + P1 (new subprocess ids P1.4, P1.5, ...). Response gives the new node id—use it for add_edge. Same id pattern everywhere (Px on global, Px.x inside).",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process at the level where you add (Process_Global for global map; Process_P1 etc. for inside that subprocess)."},
                    "lane_id": {"type": "string", "description": "Lane id at that level (GLOBAL for global map; P1, P2, etc. for inside that process)."},
                    "name": {"type": "string", "description": "Display name for the new step, decision, or subprocess."},
                    "type": {"type": "string", "description": "One of: 'step', 'decision', 'subprocess'.", "enum": ["step", "decision", "subprocess"]},
                },
                "required": ["lane_id", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Remove a step, decision, or subprocess from the process. Cannot delete start or end nodes. For subprocess nodes the linked page is deleted automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process containing the node (e.g. Process_P1). Omit for root/current."},
                    "node_id": {"type": "string", "description": "Step id to remove (e.g. P1.2, P1.4, P8)."},
                },
                "required": ["node_id"],
            },
        },
    },
]
TOOLS = TOOL_SCHEMAS

TOOL_HANDLERS: dict[str, ToolHandler] = {}


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
    pid = arguments.get("process_id") or process_id
    # Debug: log every tool call in a consistent format
    _debug_tool_call(session_id, name, arguments, process_id, pid)

    if name == "update_node":
        step_id = arguments.get("step_id")
        updates = arguments.get("updates")
        if not step_id or not isinstance(updates, dict):
            return json.dumps({"ok": False, "error": "step_id and updates (object) are required"})
        result = store_update_node(session_id, step_id, updates, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Step not found: {step_id}"})
        return json.dumps({"ok": True, "node": result})
    if name == "add_edge":
        source = arguments.get("source")
        target = arguments.get("target")
        if not source or not target:
            return json.dumps({"ok": False, "error": "source and target are required"})
        result = store_add_edge(session_id, source, target, label=arguments.get("label") or "", process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Edge not added (step not found or invalid): {source} -> {target}"})
        return json.dumps({"ok": True, "edge": result})
    if name == "delete_edge":
        source = arguments.get("source")
        target = arguments.get("target")
        if not source or not target:
            return json.dumps({"ok": False, "error": "source and target are required"})
        ok = store_delete_edge(session_id, source, target, process_id=pid)
        return json.dumps({"ok": ok, "removed": ok})
    if name == "update_edge":
        source = arguments.get("source")
        target = arguments.get("target")
        updates = arguments.get("updates")
        if not source or not target or not isinstance(updates, dict):
            return json.dumps({"ok": False, "error": "source, target and updates (object) are required"})
        result = store_update_edge(session_id, source, target, updates, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Edge not found: {source} -> {target}"})
        return json.dumps({"ok": True, "edge": result})
    if name == "add_node":
        lane_id = arguments.get("lane_id")
        name_val = arguments.get("name")
        if not lane_id or not name_val:
            return json.dumps({"ok": False, "error": "lane_id and name are required"})
        # Coerce to string so we never pass a number or object; use strip for subprocess display name.
        name_val = str(name_val).strip() if name_val is not None else ""
        if not name_val:
            return json.dumps({"ok": False, "error": "lane_id and name are required"})
        step_type = arguments.get("type", "step")
        if step_type not in ("step", "decision", "subprocess"):
            step_type = "step"
        result = store_add_node(session_id, lane_id, {"name": name_val, "type": step_type}, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Could not add node (invalid lane_id or process): {lane_id}"})
        return json.dumps({"ok": True, "node": result})
    if name == "delete_node":
        node_id = arguments.get("node_id")
        if not node_id:
            return json.dumps({"ok": False, "error": "node_id is required"})
        ok = store_delete_node(session_id, node_id, process_id=pid)
        if not ok:
            return json.dumps({"ok": False, "error": f"Node not found or cannot delete (start/end): {node_id}"})
        return json.dumps({"ok": True, "removed": True})
    logger.info("[AGENT][GRAPH] %s (no handler) session_id=%s", name, session_id)
    return json.dumps({"error": "Unknown tool"})

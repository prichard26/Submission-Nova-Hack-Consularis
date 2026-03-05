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
            "description": "Add an edge (connection) between two steps. Call multiple times per turn to add multiple edges. Use step ids from the graph (e.g. P1.1, P1.2). If an edge already exists from source to target, it is updated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process containing the steps (e.g. Process_P1). Omit for root/current."},
                    "source": {"type": "string", "description": "Source step id (e.g. P1.1)."},
                    "target": {"type": "string", "description": "Target step id (e.g. P1.2)."},
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
            "description": "Remove an edge (connection) between two steps. Call multiple times per turn to remove multiple edges. Use step ids from the graph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process containing the edge (e.g. Process_P1). Omit for root/current."},
                    "source": {"type": "string", "description": "Source step id of the edge."},
                    "target": {"type": "string", "description": "Target step id of the edge."},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_edge",
            "description": "Update an existing edge's label or condition. Call multiple times per turn to update multiple edges. The edge must already exist (source -> target).",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process containing the edge (e.g. Process_P1). Omit for root/current."},
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
            "description": "Add a new step or decision to a process. Use lane_id from the graph (e.g. P1 for a process with one lane). Pass type 'step' or 'decision' and a name. Call multiple times per turn to add multiple nodes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process to add the node to (e.g. Process_P1). Omit for root/current."},
                    "lane_id": {"type": "string", "description": "Lane id from the graph (e.g. P1, GLOBAL)."},
                    "name": {"type": "string", "description": "Display name for the new step or decision."},
                    "type": {"type": "string", "description": "Either 'step' or 'decision'.", "enum": ["step", "decision"]},
                },
                "required": ["lane_id", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Remove a step or decision from the process. Cannot delete start or end nodes. Use the step id from the graph (e.g. P1.2). Call multiple times per turn to remove multiple nodes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process containing the node (e.g. Process_P1). Omit for root/current."},
                    "node_id": {"type": "string", "description": "Step id to remove (e.g. P1.2)."},
                },
                "required": ["node_id"],
            },
        },
    },
]
TOOLS = TOOL_SCHEMAS

TOOL_HANDLERS: dict[str, ToolHandler] = {}


def run_tool(session_id: str, name: str, arguments: dict, process_id: str | None = None) -> str:
    pid = arguments.get("process_id") or process_id
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
        step_type = arguments.get("type", "step")
        if step_type not in ("step", "decision"):
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

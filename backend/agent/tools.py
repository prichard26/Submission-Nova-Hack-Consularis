"""Tool schemas and dispatch. Step 2 + 3: update_node + add_edge, delete_edge, update_edge."""
import json
import logging
from typing import Callable

from graph.store import (
    add_edge as store_add_edge,
    delete_edge as store_delete_edge,
    update_edge as store_update_edge,
    update_node as store_update_node,
)

ToolHandler = Callable[[str, dict, str | None], str]
logger = logging.getLogger("consularis.agent")

# Step 2: update_node. Step 3: add_edge, delete_edge, update_edge.
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
    logger.info("[AGENT][GRAPH] %s (no handler) session_id=%s", name, session_id)
    return json.dumps({"error": "Unknown tool"})

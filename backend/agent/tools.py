"""Tool schemas and dispatch. Step 2: full graph in context + update_node to edit one step."""
import json
import logging
from typing import Callable

from graph.store import update_node as store_update_node

ToolHandler = Callable[[str, dict, str | None], str]
logger = logging.getLogger("consularis.agent")

# Step 2: agent can modify a single node (step) via update_node.
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "Update a single step (node) in the process graph. Use the step id (e.g. P1.1, P2.3) and process_id (e.g. Process_P1) from the graph data in context. You can change the step's name and any of its metadata. ",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {
                        "type": "string",
                        "description": "Process containing the step (e.g. Process_P1, Process_Global). Omit or empty for root/current process.",
                    },
                    "step_id": {
                        "type": "string",
                        "description": "Step id from the graph (e.g. P1.1, P2.2, GLOBAL.1).",
                    },
                    "updates": {
                        "type": "object",
                        "description": "Fields to set on the step. Allowed: name, actor, duration_min, description, inputs, outputs, risks, cost_per_execution, etc. Format: duration_min with ' min' after the number (e.g. '5 min'), cost_per_execution with ' EUR' after the amount (e.g. '2.50 EUR').",
                        "additionalProperties": True,
                    },
                },
                "required": ["step_id", "updates"],
            },
        },
    },
]
TOOLS = TOOL_SCHEMAS

TOOL_HANDLERS: dict[str, ToolHandler] = {}


def run_tool(session_id: str, name: str, arguments: dict, process_id: str | None = None) -> str:
    if name == "update_node":
        pid = arguments.get("process_id") or process_id
        step_id = arguments.get("step_id")
        updates = arguments.get("updates")
        if not step_id or not isinstance(updates, dict):
            return json.dumps({"ok": False, "error": "step_id and updates (object) are required"})
        result = store_update_node(session_id, step_id, updates, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": f"Step not found: {step_id}"})
        return json.dumps({"ok": True, "node": result})
    logger.info("[AGENT][GRAPH] %s (no handler) session_id=%s", name, session_id)
    return json.dumps({"error": "Unknown tool"})

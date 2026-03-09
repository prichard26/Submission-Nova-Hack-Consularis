"""Tool schemas and dispatch. Step 2 + 3: update_node, edges. Step 4: add_node, delete_node. Multi-agent: planner uses request_execution."""
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

# All tools: always use IDs from the graph (step_id, process_id, source, target, node_id). Never pass display names.
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "Update a step. Pass step_id (step id from graph, e.g. P1.1, P3.3) and updates (object). Use cost_per_execution for cost (add ' EUR'), duration_min for duration (add ' min'). Never use process_id as step_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process id from graph (e.g. Process_P1). Omit for current."},
                    "step_id": {"type": "string", "description": "Step id from graph (e.g. P1.1, P2.2)."},
                    "updates": {"type": "object", "description": "Fields to set (name, actor, duration_min, description, etc.).", "additionalProperties": True},
                },
                "required": ["step_id", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_edge",
            "description": "Add an edge between two steps in the same process. source and target must be step ids that exist in that process (from the graph or returned by add_node). Pass process_id and both source and target step ids.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process id (Process_Global, Process_P1, etc.)—the process that contains both source and target."},
                    "source": {"type": "string", "description": "Source step id in that process (e.g. P7.1, or the id returned by add_node)."},
                    "target": {"type": "string", "description": "Target step id in that process (e.g. P7.2, or the id returned by add_node)."},
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
            "description": "Remove an edge. Pass source, target (step ids in that process), and process_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process id from graph."},
                    "source": {"type": "string", "description": "Source step id."},
                    "target": {"type": "string", "description": "Target step id."},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_edge",
            "description": "Update an edge's label or condition. Pass source, target (step ids in that process), process_id, updates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process id from graph."},
                    "source": {"type": "string", "description": "Source step id."},
                    "target": {"type": "string", "description": "Target step id."},
                    "updates": {"type": "object", "description": "e.g. {\"label\": \"...\"}.", "additionalProperties": True},
                },
                "required": ["source", "target", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_node",
            "description": "Add a step, decision, or subprocess. Pass process_id and name (display name only, e.g. 'Escalate to Physician'—do not include step id in the name). Type: step, decision, or subprocess. Response returns the new step id (e.g. P7.4)—use that exact id in add_edge for source or target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process id (Process_Global, Process_P1, etc.)."},
                    "name": {"type": "string", "description": "Display name only (e.g. 'Verify Data'). Do not put step id in name (e.g. not 'P7.4 (Verify Data)')."},
                    "type": {"type": "string", "description": "step, decision, or subprocess.", "enum": ["step", "decision", "subprocess"]},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Remove a step or subprocess. node_id must be the STEP ID from the graph (e.g. P1.2, P8, P1.4). On the global map, subprocess boxes are P1, P2, P8, P9—never use process_id (e.g. Process_P1, Process_Custom_4) as node_id. Cannot delete start or end.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process id from graph. Omit for current."},
                    "node_id": {"type": "string", "description": "Step id from graph (e.g. P1.2, P1.4, P8)."},
                },
                "required": ["node_id"],
            },
        },
    },
]
TOOLS = TOOL_SCHEMAS

# Planner-only tools: orchestrator proposes or requests execution. Handled in runtime, not in run_tool. All step/process references in steps must be IDs.
PLANNER_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "propose_plan",
            "description": "Call for any multi-step plan or when the plan includes deletes, or when you want the user to confirm. The UI will show Apply plan so the user can one-click apply. Write a short numbered plan in your reply, then call propose_plan with instructions and steps. In steps, use step_id/node_id = step ids (P1.2, P8), never process_id (Process_P1) as node_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Step-by-step instructions for the executor. Be specific (process_id, step ids).",
                    },
                    "steps": {
                        "type": "array",
                        "description": "Exact list of tool calls: each item { \"tool_name\": \"update_node\"|\"add_edge\"|\"delete_edge\"|\"update_edge\"|\"add_node\"|\"delete_node\", \"arguments\": {...} }.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {"type": "string"},
                                "arguments": {"type": "object", "additionalProperties": True},
                            },
                        },
                    },
                },
                "required": ["instructions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_execution",
            "description": "Run graph changes immediately. Use only for SIMPLE (one or two) actions, or after user confirmed. Use step ids (P1.1, P8) for step_id/node_id; use process_id (Process_Global, Process_P1) only for process. Never use process_id as node_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Step-by-step instructions for the executor: what to do, in what order, which process_id and step ids (e.g. Process_P1, P1.1, P1.2). Be specific.",
                    },
                    "steps": {
                        "type": "array",
                        "description": "Preferred: exact list of tool calls so the executor does only this. Each item: { \"tool_name\": \"update_node\" | \"add_edge\" | \"delete_edge\" | \"update_edge\" | \"add_node\" | \"delete_node\", \"arguments\": { step_id, process_id, source, target, lane_id, name, type, updates, ... } }.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {"type": "string"},
                                "arguments": {"type": "object", "additionalProperties": True},
                            },
                        },
                    },
                },
                "required": ["instructions"],
            },
        },
    },
]

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
        updates = dict(arguments.get("updates") or {})
        if not step_id or not updates:
            return json.dumps({"ok": False, "error": "step_id and updates (object) are required"})
        if "cost" in updates and "cost_per_execution" not in updates:
            updates["cost_per_execution"] = updates.pop("cost")
        if "duration" in updates and "duration_min" not in updates:
            updates["duration_min"] = updates.pop("duration")
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
        name_val = arguments.get("name")
        if not name_val:
            return json.dumps({"ok": False, "error": "name is required"})
        name_val = str(name_val).strip() if name_val is not None else ""
        if not name_val:
            return json.dumps({"ok": False, "error": "name is required"})
        # If model put step id in name (e.g. "P7.4 (Escalate to Physician)"), keep only the display part.
        if " (" in name_val and name_val.endswith(")"):
            idx = name_val.find(" (")
            prefix = name_val[:idx].strip()
            if prefix and (prefix.startswith("P") and "." in prefix or prefix.startswith("GLOBAL.")):
                name_val = name_val[idx + 2 : -1].strip() or name_val
        step_type = arguments.get("type", "step")
        if step_type not in ("step", "decision", "subprocess"):
            step_type = "step"
        result = store_add_node(session_id, "default", {"name": name_val, "type": step_type}, process_id=pid)
        if result is None:
            return json.dumps({"ok": False, "error": "Could not add node (invalid process)"})
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

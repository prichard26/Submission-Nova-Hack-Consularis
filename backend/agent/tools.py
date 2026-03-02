"""Tool schemas and dispatch for the agent (graph operations)."""
import json
import logging
from typing import Callable

from bpmn.store import (
    add_edge,
    add_lane,
    add_node,
    delete_edge,
    delete_lane,
    delete_node,
    get_edges,
    get_graph_summary,
    get_node,
    resolve_step,
    update_edge,
    update_lane,
    update_node,
    validate_graph,
)

ToolHandler = Callable[[str, dict, str | None], str]
logger = logging.getLogger("consularis.agent")


def _schema(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


TOOL_SCHEMAS = [
    _schema("get_graph_summary", "Get compact summary of phase IDs, step IDs, and step names."),
    _schema("resolve_step", "Resolve step ID from name fragment.", {"name_or_fragment": {"type": "string"}}, ["name_or_fragment"]),
    _schema("get_node", "Get one step by id.", {"node_id": {"type": "string"}}, ["node_id"]),
    _schema(
        "update_node",
        "Update a step name/metadata fields.",
        {
            "node_id": {"type": "string"},
            "updates": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "actor": {"type": "string"},
                    "duration_min": {"type": "string"},
                    "description": {"type": "string"},
                    "inputs": {"type": "array", "items": {"type": "string"}},
                    "outputs": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "automation_potential": {"type": "string"},
                    "automation_notes": {"type": "string"},
                },
            },
        },
        ["node_id", "updates"],
    ),
    _schema(
        "add_node",
        "Add a step to a phase/lane.",
        {
            "phase_id": {"type": "string"},
            "step_data": {"type": "object"},
        },
        ["phase_id", "step_data"],
    ),
    _schema("delete_node", "Delete one step.", {"node_id": {"type": "string"}}, ["node_id"]),
    _schema("get_edges", "List edges, optionally by source.", {"source_id": {"type": "string"}}),
    _schema(
        "update_edge",
        "Update edge label/condition.",
        {
            "source": {"type": "string"},
            "target": {"type": "string"},
            "updates": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "condition": {"type": "string"}},
            },
        },
        ["source", "target", "updates"],
    ),
    _schema(
        "add_edge",
        "Add an edge between two nodes.",
        {
            "source": {"type": "string"},
            "target": {"type": "string"},
            "label": {"type": "string"},
            "condition": {"type": "string"},
        },
        ["source", "target"],
    ),
    _schema("delete_edge", "Delete an edge.", {"source": {"type": "string"}, "target": {"type": "string"}}, ["source", "target"]),
    _schema(
        "add_lane",
        "Add a new phase/lane to the current process.",
        {"name": {"type": "string"}, "description": {"type": "string"}},
        ["name"],
    ),
    _schema(
        "update_lane",
        "Rename a lane or update its description.",
        {
            "lane_id": {"type": "string"},
            "updates": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}}},
        },
        ["lane_id", "updates"],
    ),
    _schema("delete_lane", "Delete a lane and all its steps.", {"lane_id": {"type": "string"}}, ["lane_id"]),
    _schema("validate_graph", "Validate current process graph."),
]


def get_active_process(session_id: str, process_id: str | None = None) -> str | None:
    """Return the process_id from the request (frontend sends it); no server-side state."""
    if process_id and str(process_id).strip():
        return str(process_id).strip()
    return None


def _handle_get_graph_summary(session_id: str, arguments: dict, process_id: str | None) -> str:
    del arguments
    return get_graph_summary(session_id, process_id=process_id)


def _handle_get_node(session_id: str, arguments: dict, process_id: str | None) -> str:
    n = get_node(session_id, arguments.get("node_id", ""), process_id=process_id)
    return json.dumps(n) if n else json.dumps({"error": "Node not found"})


def _handle_update_node(session_id: str, arguments: dict, process_id: str | None) -> str:
    n = update_node(session_id, arguments["node_id"], arguments.get("updates", {}), process_id=process_id)
    return json.dumps(n) if n else json.dumps({"error": "Node not found"})


def _handle_add_node(session_id: str, arguments: dict, process_id: str | None) -> str:
    n = add_node(session_id, arguments["phase_id"], arguments.get("step_data", {}), process_id=process_id)
    return json.dumps(n) if n else json.dumps({"error": "Phase not found or invalid"})


def _handle_delete_node(session_id: str, arguments: dict, process_id: str | None) -> str:
    ok = delete_node(session_id, arguments["node_id"], process_id=process_id)
    return json.dumps({"deleted": ok}) if ok else json.dumps({"error": "Node not found"})


def _handle_get_edges(session_id: str, arguments: dict, process_id: str | None) -> str:
    return json.dumps(get_edges(session_id, arguments.get("source_id"), process_id=process_id))


def _handle_update_edge(session_id: str, arguments: dict, process_id: str | None) -> str:
    e = update_edge(session_id, arguments["source"], arguments["target"], arguments.get("updates", {}), process_id=process_id)
    return json.dumps(e) if e else json.dumps({"error": "Edge not found"})


def _handle_add_edge(session_id: str, arguments: dict, process_id: str | None) -> str:
    e = add_edge(
        session_id,
        arguments["source"],
        arguments["target"],
        arguments.get("label", ""),
        arguments.get("condition"),
        process_id=process_id,
    )
    return json.dumps(e) if e else json.dumps({"error": "Invalid source/target or edge exists"})


def _handle_delete_edge(session_id: str, arguments: dict, process_id: str | None) -> str:
    ok = delete_edge(session_id, arguments["source"], arguments["target"], process_id=process_id)
    return json.dumps({"deleted": ok}) if ok else json.dumps({"error": "Edge not found"})


def _handle_validate_graph(session_id: str, arguments: dict, process_id: str | None) -> str:
    del arguments
    return json.dumps(validate_graph(session_id, process_id=process_id))


def _handle_resolve_step(session_id: str, arguments: dict, process_id: str | None) -> str:
    name = arguments.get("name_or_fragment", "")
    return json.dumps(resolve_step(session_id, name_fragment=name, process_id=process_id))


def _handle_add_lane(session_id: str, arguments: dict, process_id: str | None) -> str:
    lane_data = {"name": arguments.get("name", ""), "description": arguments.get("description", "")}
    out = add_lane(session_id, lane_data, process_id=process_id)
    return json.dumps(out) if out else json.dumps({"error": "Failed to add lane"})


def _handle_update_lane(session_id: str, arguments: dict, process_id: str | None) -> str:
    out = update_lane(
        session_id,
        arguments.get("lane_id", ""),
        arguments.get("updates", {}),
        process_id=process_id,
    )
    return json.dumps(out) if out else json.dumps({"error": "Lane not found"})


def _handle_delete_lane(session_id: str, arguments: dict, process_id: str | None) -> str:
    ok = delete_lane(session_id, arguments.get("lane_id", ""), process_id=process_id)
    return json.dumps({"deleted": ok}) if ok else json.dumps({"error": "Lane not found"})


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_graph_summary": _handle_get_graph_summary,
    "resolve_step": _handle_resolve_step,
    "get_node": _handle_get_node,
    "update_node": _handle_update_node,
    "add_node": _handle_add_node,
    "delete_node": _handle_delete_node,
    "get_edges": _handle_get_edges,
    "update_edge": _handle_update_edge,
    "add_edge": _handle_add_edge,
    "delete_edge": _handle_delete_edge,
    "add_lane": _handle_add_lane,
    "update_lane": _handle_update_lane,
    "delete_lane": _handle_delete_lane,
    "validate_graph": _handle_validate_graph,
}

TOOLS = TOOL_SCHEMAS


def run_tool(session_id: str, name: str, arguments: dict, process_id: str | None = None) -> str:
    effective_process = get_active_process(session_id, process_id)
    logger.info(
        "[AGENT][GRAPH] %s session_id=%s process_id=%s %s",
        name,
        session_id,
        effective_process,
        _log_args(name, arguments),
    )
    try:
        handler = TOOL_HANDLERS.get(name)
        if handler is not None:
            return handler(session_id, arguments, effective_process)
    except Exception as exc:
        logger.exception("[AGENT][GRAPH] %s -> exception: %s", name, exc)
        return json.dumps({"error": str(exc)})
    return json.dumps({"error": "Unknown tool"})


def _log_args(name: str, arguments: dict) -> str:
    if name == "get_node":
        return f"node_id={arguments.get('node_id', '')}"
    if name == "update_node":
        return f"node_id={arguments.get('node_id', '')}"
    if name == "add_node":
        return f"phase_id={arguments.get('phase_id', '')}"
    if name == "delete_node":
        return f"node_id={arguments.get('node_id', '')}"
    if name == "get_edges":
        return f"source_id={arguments.get('source_id', 'all')}"
    if name == "update_edge":
        return f"source={arguments.get('source', '')} target={arguments.get('target', '')}"
    if name == "add_edge":
        return f"source={arguments.get('source', '')} target={arguments.get('target', '')}"
    if name == "delete_edge":
        return f"source={arguments.get('source', '')} target={arguments.get('target', '')}"
    if name == "resolve_step":
        return f"name_or_fragment={arguments.get('name_or_fragment', '')}"
    if name == "add_lane":
        return f"name={arguments.get('name', '')}"
    if name == "update_lane":
        return f"lane_id={arguments.get('lane_id', '')}"
    if name == "delete_lane":
        return f"lane_id={arguments.get('lane_id', '')}"
    return ""

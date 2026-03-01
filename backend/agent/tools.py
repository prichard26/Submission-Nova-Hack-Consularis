"""Tool schemas and dispatch for the agent (graph operations)."""
import json
import logging
from typing import Callable

from graph_store import (
    get_bpmn_xml,
    get_node,
    update_node,
    add_node,
    delete_node,
    get_edges,
    update_edge,
    add_edge,
    delete_edge,
    validate_graph,
)

# Type for a tool handler: (session_id, arguments) -> JSON-serializable result (str or dict)
ToolHandler = Callable[[str, dict], str]

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "get_graph", "description": "Get the current process graph as BPMN 2.0 XML. Use this to inspect the canonical graph before making changes.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_node", "description": "Get one step by id (e.g. P1.2, P3.1).", "parameters": {"type": "object", "properties": {"node_id": {"type": "string", "description": "Step id, e.g. P1.2"}}, "required": ["node_id"]}}},
    {"type": "function", "function": {"name": "update_node", "description": "Update a step's name, actor, duration_min, description, inputs, outputs, or risks.", "parameters": {"type": "object", "properties": {"node_id": {"type": "string"}, "updates": {"type": "object", "properties": {"name": {"type": "string"}, "actor": {"type": "string"}, "duration_min": {"type": "string"}, "description": {"type": "string"}, "inputs": {"type": "array", "items": {"type": "string"}}, "outputs": {"type": "array", "items": {"type": "string"}}, "risks": {"type": "array", "items": {"type": "string"}}}}}, "required": ["node_id", "updates"]}}},
    {"type": "function", "function": {"name": "add_node", "description": "Add a new step to a phase. Use when the user wants to add a step. phase_id is e.g. P1, P2, ... P7.", "parameters": {"type": "object", "properties": {"phase_id": {"type": "string"}, "step_data": {"type": "object", "properties": {"name": {"type": "string"}, "actor": {"type": "string"}, "duration_min": {"type": "string"}, "description": {"type": "string"}}}}, "required": ["phase_id", "step_data"]}}},
    {"type": "function", "function": {"name": "delete_node", "description": "Remove a step and all its incoming/outgoing edges. Use when the user wants to remove one or more steps (call once per step).", "parameters": {"type": "object", "properties": {"node_id": {"type": "string"}}, "required": ["node_id"]}}},
    {"type": "function", "function": {"name": "get_edges", "description": "List edges. Optionally filter by source step id.", "parameters": {"type": "object", "properties": {"source_id": {"type": "string", "description": "Optional. If given, only edges from this step."}}, "required": []}}},
    {"type": "function", "function": {"name": "update_edge", "description": "Update an edge's label or condition. Edge is identified by source and target step ids.", "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "target": {"type": "string"}, "updates": {"type": "object", "properties": {"label": {"type": "string"}, "condition": {"type": "string"}}}}, "required": ["source", "target", "updates"]}}},
    {"type": "function", "function": {"name": "add_edge", "description": "Add a link between two steps. Use to connect steps or to reconnect (after removing an edge).", "parameters": {"type": "object", "properties": {"source": {"type": "string", "description": "Source step id, e.g. P1.1"}, "target": {"type": "string", "description": "Target step id, e.g. P1.2"}, "label": {"type": "string"}, "condition": {"type": "string"}}, "required": ["source", "target"]}}},
    {"type": "function", "function": {"name": "delete_edge", "description": "Remove a link between two steps.", "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "target": {"type": "string"}}, "required": ["source", "target"]}}},
    {"type": "function", "function": {"name": "validate_graph", "description": "Check the graph for consistency (orphan edges, duplicate ids, etc.). Call after making several changes.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]

logger = logging.getLogger("consularis.agent")


def _handle_get_graph(session_id: str, arguments: dict) -> str:
    out = get_bpmn_xml(session_id)
    logger.debug("[AGENT][GRAPH] get_graph -> returned BPMN XML")
    return out


def _handle_get_node(session_id: str, arguments: dict) -> str:
    n = get_node(session_id, arguments.get("node_id", ""))
    if n:
        logger.debug("[AGENT][GRAPH] get_node -> found %s", arguments.get("node_id"))
    else:
        logger.info("[AGENT][GRAPH] get_node -> node not found: %s", arguments.get("node_id"))
    return json.dumps(n) if n else json.dumps({"error": "Node not found"})


def _handle_update_node(session_id: str, arguments: dict) -> str:
    n = update_node(session_id, arguments["node_id"], arguments.get("updates", {}))
    if n:
        logger.info("[AGENT][GRAPH] update_node -> ok node_id=%s updates=%s", arguments["node_id"], arguments.get("updates"))
    else:
        logger.warning("[AGENT][GRAPH] update_node -> node not found: %s", arguments["node_id"])
    return json.dumps(n) if n else json.dumps({"error": "Node not found"})


def _handle_add_node(session_id: str, arguments: dict) -> str:
    n = add_node(session_id, arguments["phase_id"], arguments.get("step_data", {}))
    if n:
        logger.info("[AGENT][GRAPH] add_node -> ok phase_id=%s new_id=%s", arguments["phase_id"], n.get("id"))
    else:
        logger.warning("[AGENT][GRAPH] add_node -> failed phase_id=%s", arguments["phase_id"])
    return json.dumps(n) if n else json.dumps({"error": "Phase not found or invalid"})


def _handle_delete_node(session_id: str, arguments: dict) -> str:
    ok = delete_node(session_id, arguments["node_id"])
    if ok:
        logger.info("[AGENT][GRAPH] delete_node -> ok node_id=%s", arguments["node_id"])
    else:
        logger.warning("[AGENT][GRAPH] delete_node -> node not found: %s", arguments["node_id"])
    return json.dumps({"deleted": ok}) if ok else json.dumps({"error": "Node not found"})


def _handle_get_edges(session_id: str, arguments: dict) -> str:
    out = json.dumps(get_edges(session_id, arguments.get("source_id")))
    logger.debug("[AGENT][GRAPH] get_edges -> returned (source_id=%s)", arguments.get("source_id"))
    return out


def _handle_update_edge(session_id: str, arguments: dict) -> str:
    e = update_edge(session_id, arguments["source"], arguments["target"], arguments.get("updates", {}))
    if e:
        logger.info("[AGENT][GRAPH] update_edge -> ok source=%s target=%s updates=%s", arguments["source"], arguments["target"], arguments.get("updates"))
    else:
        logger.warning("[AGENT][GRAPH] update_edge -> edge not found: %s -> %s", arguments["source"], arguments["target"])
    return json.dumps(e) if e else json.dumps({"error": "Edge not found"})


def _handle_add_edge(session_id: str, arguments: dict) -> str:
    e = add_edge(session_id, arguments["source"], arguments["target"], arguments.get("label", ""), arguments.get("condition"))
    if e:
        logger.info("[AGENT][GRAPH] add_edge -> ok source=%s target=%s", arguments["source"], arguments["target"])
    else:
        logger.warning("[AGENT][GRAPH] add_edge -> failed source=%s target=%s", arguments["source"], arguments["target"])
    return json.dumps(e) if e else json.dumps({"error": "Invalid source/target or edge exists"})


def _handle_delete_edge(session_id: str, arguments: dict) -> str:
    ok = delete_edge(session_id, arguments["source"], arguments["target"])
    if ok:
        logger.info("[AGENT][GRAPH] delete_edge -> ok source=%s target=%s", arguments["source"], arguments["target"])
    else:
        logger.warning("[AGENT][GRAPH] delete_edge -> edge not found: %s -> %s", arguments["source"], arguments["target"])
    return json.dumps({"deleted": ok}) if ok else json.dumps({"error": "Edge not found"})


def _handle_validate_graph(session_id: str, arguments: dict) -> str:
    out = json.dumps(validate_graph(session_id))
    logger.info("[AGENT][GRAPH] validate_graph -> completed")
    return out


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_graph": _handle_get_graph,
    "get_node": _handle_get_node,
    "update_node": _handle_update_node,
    "add_node": _handle_add_node,
    "delete_node": _handle_delete_node,
    "get_edges": _handle_get_edges,
    "update_edge": _handle_update_edge,
    "add_edge": _handle_add_edge,
    "delete_edge": _handle_delete_edge,
    "validate_graph": _handle_validate_graph,
}

# Exposed to Groq API (runtime expects TOOLS)
TOOLS = TOOL_SCHEMAS


def run_tool(session_id: str, name: str, arguments: dict) -> str:
    args_snippet = _log_args(name, arguments)
    logger.info("[AGENT][GRAPH] %s session_id=%s %s", name, session_id, args_snippet)

    try:
        handler = TOOL_HANDLERS.get(name)
        if handler is not None:
            return handler(session_id, arguments)
    except Exception as exc:
        logger.exception("[AGENT][GRAPH] %s -> exception: %s", name, exc)
        return json.dumps({"error": str(exc)})
    logger.warning("[AGENT][GRAPH] %s -> unknown tool", name)
    return json.dumps({"error": "Unknown tool"})


def _log_args(name: str, arguments: dict) -> str:
    """Build a short, readable args snippet for logs."""
    if name == "get_node":
        return "node_id=%s" % arguments.get("node_id", "")
    if name == "update_node":
        return "node_id=%s updates=%s" % (arguments.get("node_id", ""), arguments.get("updates", {}))
    if name == "add_node":
        return "phase_id=%s step_data=%s" % (arguments.get("phase_id", ""), arguments.get("step_data", {}))
    if name == "delete_node":
        return "node_id=%s" % arguments.get("node_id", "")
    if name == "get_edges":
        return "source_id=%s" % arguments.get("source_id", "all")
    if name == "update_edge":
        return "source=%s target=%s updates=%s" % (arguments.get("source", ""), arguments.get("target", ""), arguments.get("updates", {}))
    if name == "add_edge":
        return "source=%s target=%s label=%s" % (arguments.get("source", ""), arguments.get("target", ""), arguments.get("label", ""))
    if name == "delete_edge":
        return "source=%s target=%s" % (arguments.get("source", ""), arguments.get("target", ""))
    return ""

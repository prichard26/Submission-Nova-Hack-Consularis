"""Tool schemas and dispatch for the agent (graph operations). Minimal 7-tool set."""
import json
import logging
from typing import Callable

from graph.store import (
    add_edge,
    add_node,
    create_subprocess_page,
    delete_edge,
    delete_node,
    get_graph_summary,
    resolve_step,
    update_node,
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


# 8 tools
TOOL_SCHEMAS = [
    _schema("get_graph_summary", "Phases, steps, edges. Optional process_id for other process.", {"process_id": {"type": "string"}}),
    _schema("resolve_step", "Name to node_id/lane_id.", {"name_or_fragment": {"type": "string"}}, ["name_or_fragment"]),
    _schema("update_node", "Set name, actor, duration_min, cost, etc. Units: 10 min, 8.50 EUR.", {"node_id": {"type": "string"}, "updates": {"type": "object"}}, ["node_id", "updates"]),
    _schema("add_node", "Add step, decision, or subprocess. step_data: name, type (step|decision|subprocess).", {"phase_id": {"type": "string"}, "step_data": {"type": "object"}}, ["phase_id", "step_data"]),
    _schema("delete_node", "Remove step, decision, or subprocess node and its edges.", {"node_id": {"type": "string"}}, ["node_id"]),
    _schema("add_edge", "Connect source->target. Optional label, condition.", {"source": {"type": "string"}, "target": {"type": "string"}, "label": {"type": "string"}, "condition": {"type": "string"}}, ["source", "target"]),
    _schema("delete_edge", "Remove source->target.", {"source": {"type": "string"}, "target": {"type": "string"}}, ["source", "target"]),
    _schema("create_subprocess_page", "Create a new process page for a subprocess node. Pass node_id (a step with type subprocess). Optional name for the new process. The node must exist and have type subprocess.", {"node_id": {"type": "string"}, "name": {"type": "string"}}, ["node_id"]),
]


def get_active_process(session_id: str, process_id: str | None = None) -> str | None:
    if process_id and str(process_id).strip():
        return str(process_id).strip()
    return None


def _handle_get_graph_summary(session_id: str, arguments: dict, process_id: str | None) -> str:
    effective = (arguments.get("process_id") or "").strip() or process_id
    return get_graph_summary(session_id, process_id=effective)


def _handle_resolve_step(session_id: str, arguments: dict, process_id: str | None) -> str:
    return json.dumps(resolve_step(session_id, name_fragment=arguments.get("name_or_fragment", ""), process_id=process_id))


def _handle_update_node(session_id: str, arguments: dict, process_id: str | None) -> str:
    n = update_node(session_id, arguments["node_id"], arguments.get("updates", {}), process_id=process_id)
    return json.dumps(n) if n else json.dumps({"error": "Node not found"})


def _handle_add_node(session_id: str, arguments: dict, process_id: str | None) -> str:
    n = add_node(session_id, arguments["phase_id"], arguments.get("step_data", {}), process_id=process_id)
    return json.dumps(n) if n else json.dumps({"error": "Phase not found or invalid"})


def _handle_delete_node(session_id: str, arguments: dict, process_id: str | None) -> str:
    ok = delete_node(session_id, arguments["node_id"], process_id=process_id)
    return json.dumps({"deleted": ok}) if ok else json.dumps({"error": "Node not found"})


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


def _handle_create_subprocess_page(session_id: str, arguments: dict, process_id: str | None) -> str:
    out = create_subprocess_page(
        session_id,
        parent_process_id=process_id or "",
        node_id=arguments.get("node_id", ""),
        name=arguments.get("name") or None,
    )
    return json.dumps(out) if out else json.dumps({"error": "Node not found or not a subprocess"})


TOOLS = TOOL_SCHEMAS  # alias for runtimes that use TOOLS

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_graph_summary": _handle_get_graph_summary,
    "resolve_step": _handle_resolve_step,
    "update_node": _handle_update_node,
    "add_node": _handle_add_node,
    "delete_node": _handle_delete_node,
    "add_edge": _handle_add_edge,
    "delete_edge": _handle_delete_edge,
    "create_subprocess_page": _handle_create_subprocess_page,
}


def run_tool(session_id: str, name: str, arguments: dict, process_id: str | None = None) -> str:
    effective_process = get_active_process(session_id, process_id)
    logger.info("[AGENT][GRAPH] %s session_id=%s process_id=%s", name, session_id, effective_process)
    try:
        handler = TOOL_HANDLERS.get(name)
        if handler is not None:
            return handler(session_id, arguments, effective_process)
    except Exception as exc:
        logger.exception("[AGENT][GRAPH] %s -> exception: %s", name, exc)
        return json.dumps({"error": str(exc)})
    return json.dumps({"error": "Unknown tool"})

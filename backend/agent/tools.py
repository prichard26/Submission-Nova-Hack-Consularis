"""Tool schemas and dispatch for the agent (graph operations)."""
import json
import logging
from typing import Callable

from graph_store import (
    add_edge,
    add_lane,
    add_node,
    add_subprocess,
    delete_edge,
    delete_lane,
    delete_node,
    get_bpmn_xml,
    get_edges,
    get_graph_summary,
    get_node,
    get_process_tree,
    move_node,
    reorder_lanes,
    reorder_steps,
    rename_process,
    resolve_step,
    set_session,
    update_edge,
    update_lane,
    update_node,
    validate_graph,
)

ToolHandler = Callable[[str, dict, str | None], str]
_active_process_by_session: dict[str, str] = {}
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
    _schema("get_graph", "Get the current process graph as BPMN 2.0 XML."),
    _schema("get_graph_summary", "Get compact summary of phase IDs, step IDs, and step names."),
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
    _schema("validate_graph", "Validate current process graph."),
    _schema("set_graph", "Replace current process with provided BPMN XML.", {"bpmn_xml": {"type": "string"}}, ["bpmn_xml"]),
    _schema("resolve_step", "Resolve step ID from name fragment.", {"name_or_fragment": {"type": "string"}}, ["name_or_fragment"]),
    _schema("list_processes", "List all processes/subprocesses in current session."),
    _schema("navigate_process", "Switch active process context.", {"process_id": {"type": "string"}}, ["process_id"]),
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
    _schema("reorder_lanes", "Reorder phases/lanes.", {"lane_ids": {"type": "array", "items": {"type": "string"}}}, ["lane_ids"]),
    _schema(
        "move_node",
        "Move a step to another phase/lane.",
        {
            "node_id": {"type": "string"},
            "target_lane_id": {"type": "string"},
            "position": {"type": "integer"},
        },
        ["node_id", "target_lane_id"],
    ),
    _schema(
        "reorder_steps",
        "Reorder steps within a lane.",
        {"lane_id": {"type": "string"}, "ordered_ids": {"type": "array", "items": {"type": "string"}}},
        ["lane_id", "ordered_ids"],
    ),
    _schema("rename_process", "Rename the current process.", {"new_name": {"type": "string"}}, ["new_name"]),
    _schema(
        "add_subprocess",
        "Create a new subprocess and a call activity in the parent.",
        {"name": {"type": "string"}, "parent_process_id": {"type": "string"}},
        ["name"],
    ),
]


def set_active_process(session_id: str, process_id: str | None) -> None:
    if process_id and process_id.strip():
        _active_process_by_session[session_id] = process_id.strip()


def get_active_process(session_id: str, process_id: str | None = None) -> str | None:
    if process_id and process_id.strip():
        return process_id.strip()
    return _active_process_by_session.get(session_id)


def _handle_get_graph(session_id: str, arguments: dict, process_id: str | None) -> str:
    del arguments
    return get_bpmn_xml(session_id, process_id=process_id)


def _handle_get_graph_summary(session_id: str, arguments: dict, process_id: str | None) -> str:
    del arguments
    return get_graph_summary(session_id, process_id=process_id)


def _handle_set_graph(session_id: str, arguments: dict, process_id: str | None) -> str:
    bpmn_xml = arguments.get("bpmn_xml", "")
    if not bpmn_xml or not bpmn_xml.strip():
        return json.dumps({"error": "bpmn_xml is required and must be non-empty"})
    try:
        set_session(session_id, bpmn_xml.strip(), process_id=process_id)
        return json.dumps({"ok": True})
    except Exception as exc:
        logger.exception("[AGENT][GRAPH] set_graph failed: %s", exc)
        return json.dumps({"error": str(exc)})


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


def _handle_list_processes(session_id: str, arguments: dict, process_id: str | None) -> str:
    del arguments, process_id
    return json.dumps(get_process_tree(session_id))


def _handle_navigate_process(session_id: str, arguments: dict, process_id: str | None) -> str:
    del process_id
    pid = (arguments.get("process_id") or "").strip()
    if not pid:
        return json.dumps({"error": "process_id is required"})
    set_active_process(session_id, pid)
    return json.dumps({"ok": True, "process_id": pid})


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


def _handle_reorder_lanes(session_id: str, arguments: dict, process_id: str | None) -> str:
    ok = reorder_lanes(session_id, arguments.get("lane_ids", []), process_id=process_id)
    return json.dumps({"ok": ok}) if ok else json.dumps({"error": "Invalid lane_ids"})


def _handle_move_node(session_id: str, arguments: dict, process_id: str | None) -> str:
    pos = arguments.get("position")
    out = move_node(
        session_id,
        arguments.get("node_id", ""),
        arguments.get("target_lane_id", ""),
        position=pos if isinstance(pos, int) else None,
        process_id=process_id,
    )
    return json.dumps(out) if out else json.dumps({"error": "Node or target lane not found"})


def _handle_reorder_steps(session_id: str, arguments: dict, process_id: str | None) -> str:
    ok = reorder_steps(
        session_id,
        arguments.get("lane_id", ""),
        arguments.get("ordered_ids", []),
        process_id=process_id,
    )
    return json.dumps({"ok": ok}) if ok else json.dumps({"error": "Invalid lane_id or ordered_ids"})


def _handle_rename_process(session_id: str, arguments: dict, process_id: str | None) -> str:
    rename_process(session_id, arguments.get("new_name", ""), process_id=process_id)
    return json.dumps({"ok": True})


def _handle_add_subprocess(session_id: str, arguments: dict, process_id: str | None) -> str:
    out = add_subprocess(
        session_id,
        arguments.get("name", ""),
        parent_process_id=arguments.get("parent_process_id") or process_id,
    )
    return json.dumps(out) if out else json.dumps({"error": "Failed to add subprocess"})


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_graph": _handle_get_graph,
    "get_graph_summary": _handle_get_graph_summary,
    "set_graph": _handle_set_graph,
    "get_node": _handle_get_node,
    "update_node": _handle_update_node,
    "add_node": _handle_add_node,
    "delete_node": _handle_delete_node,
    "get_edges": _handle_get_edges,
    "update_edge": _handle_update_edge,
    "add_edge": _handle_add_edge,
    "delete_edge": _handle_delete_edge,
    "validate_graph": _handle_validate_graph,
    "resolve_step": _handle_resolve_step,
    "list_processes": _handle_list_processes,
    "navigate_process": _handle_navigate_process,
    "add_lane": _handle_add_lane,
    "update_lane": _handle_update_lane,
    "delete_lane": _handle_delete_lane,
    "reorder_lanes": _handle_reorder_lanes,
    "move_node": _handle_move_node,
    "reorder_steps": _handle_reorder_steps,
    "rename_process": _handle_rename_process,
    "add_subprocess": _handle_add_subprocess,
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
    if name == "set_graph":
        return f"bpmn_xml_len={len(arguments.get('bpmn_xml', ''))}"
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
    if name == "navigate_process":
        return f"process_id={arguments.get('process_id', '')}"
    if name == "add_lane":
        return f"name={arguments.get('name', '')}"
    if name == "update_lane":
        return f"lane_id={arguments.get('lane_id', '')}"
    if name == "delete_lane":
        return f"lane_id={arguments.get('lane_id', '')}"
    if name == "reorder_lanes":
        return f"lane_ids={arguments.get('lane_ids', [])}"
    if name == "move_node":
        return f"node_id={arguments.get('node_id', '')} target_lane_id={arguments.get('target_lane_id', '')}"
    if name == "reorder_steps":
        return f"lane_id={arguments.get('lane_id', '')}"
    if name == "rename_process":
        return f"new_name={arguments.get('new_name', '')}"
    if name == "add_subprocess":
        return f"name={arguments.get('name', '')}"
    return ""

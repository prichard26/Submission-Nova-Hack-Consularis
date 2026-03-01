"""
Graph operations: session-scoped BPMN store.
Delegates to bpmn.store; BPMN XML is the only graph exchange format.
"""
from bpmn.store import (
    init_baseline,
    get_or_create_session,
    set_session,
    get_bpmn_xml,
    get_graph_json,
    get_task_ids,
    get_graph_summary,
    get_node,
    update_node,
    add_node,
    delete_node,
    get_edges,
    add_edge,
    update_edge,
    delete_edge,
    validate_graph,
)

__all__ = [
    "init_baseline",
    "get_or_create_session",
    "set_session",
    "get_bpmn_xml",
    "get_graph_json",
    "get_task_ids",
    "get_graph_summary",
    "get_node",
    "update_node",
    "add_node",
    "delete_node",
    "get_edges",
    "add_edge",
    "update_edge",
    "delete_edge",
    "validate_graph",
]

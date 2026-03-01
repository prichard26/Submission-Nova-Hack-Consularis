"""BPMN 2.0 store: parse/serialize XML, in-memory model, legacy migration helper."""
from bpmn.model import BpmnModel
from bpmn.parser import parse_bpmn_xml
from bpmn.serializer import serialize_bpmn_xml
from bpmn.adapter import legacy_to_model

__all__ = [
    "BpmnModel",
    "parse_bpmn_xml",
    "serialize_bpmn_xml",
    "legacy_to_model",
]

# Lazy import for store to avoid loading config when only using adapter/serializer
def __getattr__(name: str):
    if name in (
        "init_baseline", "get_or_create_session", "set_session",
        "get_node", "update_node", "add_node", "delete_node",
        "get_edges", "add_edge", "update_edge", "delete_edge",
        "validate_graph", "get_bpmn_xml", "get_task_ids", "get_graph_summary",
    ):
        from bpmn import store
        return getattr(store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Graph store: duplicate risks and session validation."""

from bpmn.store import update_node, get_node, add_edge


def test_update_node_risks_dedupe():
    sid = "test-dedupe"
    update_node(sid, "P1.1", {"risks": ["a", "b", "a", "b", "c"]}, process_id="Process_P1")
    node = get_node(sid, "P1.1", process_id="Process_P1")
    assert node is not None
    assert node["risks"] == ["a", "b", "c"]


def test_add_edge_idempotent():
    """Second add_edge for same (from, to) returns existing edge; no duplicate."""
    from bpmn.store import get_edges

    sid = "test-edge-idempotent"
    e1 = add_edge(sid, "P1.1", "P1.2", "first", process_id="Process_P1")
    e2 = add_edge(sid, "P1.1", "P1.2", "second", process_id="Process_P1")
    assert e1 is not None
    assert e2 is not None
    assert e1["from"] == e2["from"] and e1["to"] == e2["to"]
    edges = get_edges(sid, "P1.1", process_id="Process_P1")
    from_p1_1 = [x for x in edges if x["from"] == "P1.1" and x["to"] == "P1.2"]
    assert len(from_p1_1) == 1

"""Graph store: duplicate risks, ids, and protected node behavior."""

from graph.store import update_node, get_node, add_edge, get_edges, _get_graph, add_node, delete_node


def test_update_node_risks_dedupe():
    sid = "test-dedupe"
    update_node(sid, "P1.1", {"risks": ["a", "b", "a", "b", "c"]}, process_id="S1")
    node = get_node(sid, "P1.1", process_id="S1")
    assert node is not None
    assert node["risks"] == ["a", "b", "c"]


def test_add_edge_idempotent():
    """Second add_edge for same (from, to) returns existing edge; no duplicate."""
    sid = "test-edge-idempotent"
    e1 = add_edge(sid, "P1.1", "P1.2", "first", process_id="S1")
    e2 = add_edge(sid, "P1.1", "P1.2", "second", process_id="S1")
    assert e1 is not None
    assert e2 is not None
    assert e1["from"] == e2["from"] and e1["to"] == e2["to"]
    edges = get_edges(sid, "P1.1", process_id="S1")
    from_p1_1 = [x for x in edges if x["from"] == "P1.1" and x["to"] == "P1.2"]
    assert len(from_p1_1) == 1


def test_add_node_uses_unique_id_when_step_order_has_gaps():
    sid = "test-add-node-unique-id"
    graph = _get_graph(sid, "S1")
    if graph.get_step("P1.10") is None:
        graph.data.setdefault("nodes", []).append({
            "id": "P1.10",
            "name": "Synthetic step",
            "type": "step",
            "position": {"x": 0, "y": 0},
        })
    order = list(graph.step_order)
    if "P1.10" not in order:
        end_id = next((n["id"] for n in graph.nodes if n.get("type") == "end"), None)
        if end_id and end_id in order:
            idx = order.index(end_id)
            order = order[:idx] + ["P1.10"] + order[idx:]
        else:
            order.append("P1.10")
    graph.step_order = order

    created = add_node(sid, "default", {"name": "New step", "type": "step"}, process_id="S1")
    assert created is not None
    assert created["id"] == "P1.11"

    ids = [n["id"] for n in graph.nodes]
    assert len(ids) == len(set(ids))


def test_delete_node_rejects_start_and_end():
    sid = "test-delete-protected-nodes"
    assert delete_node(sid, "S1_start", process_id="S1") is False
    assert delete_node(sid, "S1_end", process_id="S1") is False


def test_subprocess_node_has_called_element():
    """Subprocess node get_node returns called_element equal to node id (page id)."""
    sid = "test-called-element"
    node = get_node(sid, "S1", process_id="global")
    assert node is not None
    assert node.get("called_element") == "S1"

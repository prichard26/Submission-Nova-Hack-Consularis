"""Graph store: duplicate risks, ids, and protected node behavior."""

import json

from graph.store import (
    update_node,
    get_node,
    add_edge,
    get_edges,
    _get_graph,
    add_node,
    delete_node,
    insert_subprocess_between,
    insert_step_between,
    set_session,
)


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


def test_insert_step_between_renumbers_and_wires():
    """Inserting a step between P1.1 and P1.2 gives the new step P1.2; old P1.2→P1.3, P1.3→P1.4; edges updated."""
    sid = "test-insert-step-between"
    result = insert_step_between(sid, "S1", "P1.1", "P1.2", "Verify prescription", step_type="step")
    assert result is not None
    node = result["node"]
    assert node["id"] == "P1.2"
    assert node["name"] == "Verify prescription"
    assert node.get("node_type") == "step"

    graph = _get_graph(sid, "S1")
    order = [n["id"] for n in graph.nodes if n.get("id") and n.get("type") not in ("start", "end")]
    assert "P1.2" in order
    assert "P1.3" in order
    assert "P1.4" in order
    assert order.index("P1.1") < order.index("P1.2") < order.index("P1.3") < order.index("P1.4")

    node_p1_3 = get_node(sid, "P1.3", process_id="S1")
    node_p1_4 = get_node(sid, "P1.4", process_id="S1")
    assert node_p1_3 is not None
    assert node_p1_4 is not None

    edges = get_edges(sid, None, process_id="S1")
    from_to = {(e["from"], e["to"]) for e in edges}
    assert ("P1.1", "P1.2") in from_to
    assert ("P1.2", "P1.3") in from_to
    assert ("P1.3", "P1.4") in from_to
    assert ("P1.1", "P1.3") not in from_to


def test_delete_node_rejects_start_and_end():
    sid = "test-delete-protected-nodes"
    assert delete_node(sid, "S1_start", process_id="S1") is None
    assert delete_node(sid, "S1_end", process_id="S1") is None


def test_delete_node_renumbers_following_steps():
    """Deleting P1.2 removes it and renumbers P1.3→P1.2, P1.4→P1.3; edges are updated."""
    sid = "test-delete-renumber"
    graph_dict = {
        "id": "S1",
        "name": "Process S1",
        "nodes": [
            {"id": "S1_start", "type": "start", "position": {"x": 0, "y": 0}},
            {"id": "S1_end", "type": "end", "position": {"x": 400, "y": 0}},
            {"id": "P1.1", "name": "Step 1", "type": "step", "position": {"x": 100, "y": 0}},
            {"id": "P1.2", "name": "Step 2", "type": "step", "position": {"x": 200, "y": 0}},
            {"id": "P1.3", "name": "Step 3", "type": "step", "position": {"x": 300, "y": 0}},
            {"id": "P1.4", "name": "Step 4", "type": "step", "position": {"x": 400, "y": 0}},
        ],
        "edges": [
            {"from": "S1_start", "to": "P1.1", "label": ""},
            {"from": "P1.1", "to": "P1.2", "label": ""},
            {"from": "P1.2", "to": "P1.3", "label": ""},
            {"from": "P1.3", "to": "P1.4", "label": ""},
            {"from": "P1.4", "to": "S1_end", "label": ""},
        ],
    }
    set_session(sid, json.dumps(graph_dict), "S1")

    result = delete_node(sid, "P1.2", process_id="S1")
    assert result is not None and result.get("removed") is True

    graph = _get_graph(sid, "S1")
    step_ids = [n["id"] for n in graph.nodes if n.get("type") not in ("start", "end")]
    assert step_ids == ["P1.1", "P1.2", "P1.3"]
    assert graph.get_step("P1.2") is not None
    assert graph.get_step("P1.2").get("name") == "Step 3"  # former P1.3
    assert graph.get_step("P1.3") is not None
    assert graph.get_step("P1.3").get("name") == "Step 4"  # former P1.4

    edges = get_edges(sid, None, process_id="S1")
    from_to = {(e["from"], e["to"]) for e in edges}
    assert ("P1.1", "P1.2") in from_to
    assert ("P1.2", "P1.3") in from_to
    assert ("P1.3", "S1_end") in from_to
    assert ("P1.1", "P1.3") not in from_to
    assert ("P1.2", "P1.4") not in from_to


def test_subprocess_node_has_called_element():
    """Subprocess node get_node returns called_element equal to node id (page id)."""
    sid = "test-called-element"
    node = get_node(sid, "S1", process_id="global")
    assert node is not None
    assert node.get("called_element") == "S1"


def test_insert_subprocess_between_shifts_ids_and_edges():
    """Inserting a global subprocess between S6 and S7 makes new S7 and shifts old S7 to S8."""
    sid = "test-insert-subprocess-between"
    created = insert_subprocess_between(sid, "S6", "S7", "Compliance check")
    assert created is not None
    assert created["id"] == "S7"
    assert created["name"] == "Compliance check"

    global_graph = _get_graph(sid, "global")
    ids = [n["id"] for n in global_graph.nodes if n.get("id")]
    assert "S7" in ids
    assert "S8" in ids  # old S7 shifted

    edges = get_edges(sid, None, process_id="global")
    from_to = {(e["from"], e["to"]) for e in edges}
    assert ("S6", "S7") in from_to
    assert ("S7", "S8") in from_to

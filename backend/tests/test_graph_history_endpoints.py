"""Graph history endpoints: undo, redo, reset."""


def test_undo_then_redo_restores_graph(client):
    sid = "history-undo-redo"
    params = {"session_id": sid, "process_id": "Process_P1"}

    create = client.post(
        "/api/graph/node",
        params=params,
        json={"lane_id": "P1", "name": "Temporary Step", "type": "step"},
    )
    assert create.status_code == 200
    node_id = create.json()["id"]

    undo = client.post("/api/graph/undo", params=params)
    assert undo.status_code == 200
    undone_ids = {s["id"] for s in undo.json()["graph_json"]["steps"]}
    assert node_id not in undone_ids

    redo = client.post("/api/graph/redo", params=params)
    assert redo.status_code == 200
    redone_ids = {s["id"] for s in redo.json()["graph_json"]["steps"]}
    assert node_id in redone_ids


def test_reset_clears_history_and_redo_stack(client):
    sid = "history-reset"
    params = {"session_id": sid, "process_id": "Process_P1"}

    create = client.post(
        "/api/graph/node",
        params=params,
        json={"lane_id": "P1", "name": "Will be reset", "type": "step"},
    )
    assert create.status_code == 200
    node_id = create.json()["id"]

    reset = client.post("/api/graph/reset", params=params)
    assert reset.status_code == 200
    reset_ids = {s["id"] for s in reset.json()["graph_json"]["steps"]}
    assert node_id not in reset_ids

    redo = client.post("/api/graph/redo", params=params)
    assert redo.status_code == 404


def test_delete_start_node_is_rejected(client):
    sid = "history-delete-start"
    resp = client.delete(
        "/api/graph/node",
        params={"session_id": sid, "process_id": "Process_P1", "node_id": "Start_P1"},
    )
    assert resp.status_code == 404

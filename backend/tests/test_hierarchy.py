"""Process-scoped APIs and name resolution (multi-process mode)."""
import json

from graph.store import resolve_step, get_workspace_json


def test_process_scoped_export_endpoint(client):
    sid = "export-process-test"
    resp = client.get("/api/graph/export", params={"session_id": sid, "process_id": "global"})
    assert resp.status_code == 200
    xml = resp.text
    assert "process" in xml.lower()


def test_json_graph_endpoint(client):
    sid = "json-graph-test"
    resp = client.get("/api/graph/json", params={"session_id": sid, "process_id": "global"})
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert "lanes" in data


def test_workspace_endpoint(client):
    sid = "workspace-test"
    resp = client.get("/api/graph/workspace", params={"session_id": sid})
    assert resp.status_code == 200
    data = resp.json()
    assert "process_tree" in data
    assert "processes" in data["process_tree"]


def test_resolve_step_endpoint(client):
    sid = "resolve-process-test"
    resp = client.get(
        "/api/graph/resolve",
        params={"session_id": sid, "process_id": "global", "name": "prescription"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    assert isinstance(data["matches"], list)


def test_store_resolve_step():
    sid = "resolve-store-test"
    matches = resolve_step(sid, "prescription", process_id="global")
    assert isinstance(matches, list)


def test_store_workspace_json():
    sid = "workspace-store-test"
    ws_str = get_workspace_json(sid)
    ws = json.loads(ws_str)
    assert "process_tree" in ws
    assert len(ws["process_tree"]["processes"]) >= 1


def test_create_linked_subprocess_page_endpoint(client):
    sid = "create-subprocess-page-test"

    # add_node with type=subprocess auto-creates the page
    create_node = client.post(
        "/api/graph/node",
        params={"session_id": sid, "process_id": "global"},
        json={"lane_id": "default", "name": "My New Subprocess", "type": "subprocess"},
    )
    assert create_node.status_code == 200
    node_id = create_node.json()["id"]
    linked_pid = node_id

    ws_resp = client.get("/api/graph/workspace", params={"session_id": sid})
    assert ws_resp.status_code == 200
    ws = ws_resp.json()
    processes = ws["process_tree"]["processes"]
    assert linked_pid in processes

    parent_resp = client.get(
        "/api/graph/json",
        params={"session_id": sid, "process_id": "global"},
    )
    assert parent_resp.status_code == 200
    parent_graph = parent_resp.json()
    created_node = next((n for n in parent_graph["nodes"] if n["id"] == node_id), None)
    assert created_node is not None

    child_resp = client.get(
        "/api/graph/json",
        params={"session_id": sid, "process_id": linked_pid},
    )
    assert child_resp.status_code == 200
    child_graph = child_resp.json()
    assert child_graph["process_id"] == linked_pid
    assert len(child_graph["nodes"]) >= 2

"""Process-scoped APIs and name resolution (multi-process mode)."""
import json

from graph.store import resolve_step, get_workspace_json


def test_process_scoped_export_endpoint(client):
    sid = "export-process-test"
    resp = client.get("/api/graph/export", params={"session_id": sid, "process_id": "Process_Global"})
    assert resp.status_code == 200
    xml = resp.text
    assert "Process_Global" in xml or "process" in xml.lower()


def test_json_graph_endpoint(client):
    sid = "json-graph-test"
    resp = client.get("/api/graph/json", params={"session_id": sid, "process_id": "Process_P1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "steps" in data
    assert "flows" in data
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
        params={"session_id": sid, "process_id": "Process_Global", "name": "prescription"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    assert isinstance(data["matches"], list)


def test_store_resolve_step():
    sid = "resolve-store-test"
    matches = resolve_step(sid, "prescription", process_id="Process_Global")
    assert isinstance(matches, list)


def test_store_workspace_json():
    sid = "workspace-store-test"
    ws_str = get_workspace_json(sid)
    ws = json.loads(ws_str)
    assert "process_tree" in ws
    assert len(ws["process_tree"]["processes"]) == 8


def test_create_linked_subprocess_page_endpoint(client):
    sid = "create-subprocess-page-test"

    # 1) Create a subprocess node in the global process.
    create_node = client.post(
        "/api/graph/node",
        params={"session_id": sid, "process_id": "Process_Global"},
        json={"lane_id": "GLOBAL", "name": "My New Subprocess", "type": "subprocess"},
    )
    assert create_node.status_code == 200
    node_id = create_node.json()["id"]

    # 2) Create and link a subprocess page for that node.
    create_page = client.post(
        "/api/graph/subprocess/create",
        params={"session_id": sid, "process_id": "Process_Global"},
        json={"node_id": node_id, "name": "My New Subprocess"},
    )
    assert create_page.status_code == 200
    payload = create_page.json()
    assert payload["created"] is True
    linked_pid = payload["process_id"]
    assert linked_pid.startswith("Process_Custom_")

    # 3) Workspace should now include this process and attach it under Process_Global.
    ws_resp = client.get("/api/graph/workspace", params={"session_id": sid})
    assert ws_resp.status_code == 200
    ws = ws_resp.json()
    processes = ws["process_tree"]["processes"]
    assert linked_pid in processes
    assert linked_pid in processes["Process_Global"]["children"]

    # 4) Parent graph node should be linked via called_element.
    parent_resp = client.get(
        "/api/graph/json",
        params={"session_id": sid, "process_id": "Process_Global"},
    )
    assert parent_resp.status_code == 200
    parent_graph = parent_resp.json()
    created_node = next((n for n in parent_graph["steps"] if n["id"] == node_id), None)
    assert created_node is not None
    assert created_node.get("called_element") == linked_pid

    # 5) Linked subprocess graph must exist and be readable.
    child_resp = client.get(
        "/api/graph/json",
        params={"session_id": sid, "process_id": linked_pid},
    )
    assert child_resp.status_code == 200
    child_graph = child_resp.json()
    assert child_graph["process_id"] == linked_pid
    assert len(child_graph["steps"]) >= 2

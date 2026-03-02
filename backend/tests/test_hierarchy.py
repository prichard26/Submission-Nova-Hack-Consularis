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

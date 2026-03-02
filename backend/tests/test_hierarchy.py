"""Hierarchical process tree, process-scoped APIs, and name resolution."""

from graph_store import get_or_create_session, get_process_tree, resolve_step
from agent.tools import run_tool, set_active_process, get_active_process


def test_process_tree_is_available():
    sid = "tree-test"
    get_or_create_session(sid)
    tree = get_process_tree(sid)
    assert isinstance(tree, list)
    assert len(tree) >= 1
    root = tree[0]
    assert root["process_id"] == "Process_Global"
    assert "children" in root


def test_process_scoped_export_endpoint(client):
    sid = "export-process-test"
    resp = client.get("/api/graph/export", params={"session_id": sid, "process_id": "Process_P1"})
    assert resp.status_code == 200
    xml = resp.text
    assert "Process_P1" in xml


def test_resolve_step_endpoint(client):
    sid = "resolve-process-test"
    resp = client.get(
        "/api/graph/resolve",
        params={"session_id": sid, "process_id": "Process_P1", "name": "Verify Prescription"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    assert isinstance(data["matches"], list)
    assert any(m.get("node_id") == "P1.2" for m in data["matches"])


def test_store_resolve_step():
    sid = "resolve-store-test"
    get_or_create_session(sid)
    matches = resolve_step(sid, "Verify Prescription", process_id="Process_P1")
    assert any(m["node_id"] == "P1.2" for m in matches)


def test_agent_navigate_process_tool_switches_context():
    sid = "tool-nav-test"
    set_active_process(sid, "Process_Global")
    out = run_tool(sid, "navigate_process", {"process_id": "Process_P4"})
    assert "Process_P4" in out
    assert get_active_process(sid) == "Process_P4"

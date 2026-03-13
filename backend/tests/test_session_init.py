"""Session init and template cloning (no full app import)."""
import json

import pytest

import db
from graph.store import init_baseline, get_workspace_json, get_graph_json, invalidate_session_cache


@pytest.fixture
def seeded_db():
    """Ensure DB and baseline are ready; clear session data."""
    db.get_conn()
    init_baseline()
    conn = db.get_conn()
    conn.execute("DELETE FROM session_processes")
    conn.execute("DELETE FROM session_workspace")
    conn.commit()
    yield
    conn.execute("DELETE FROM session_processes")
    conn.execute("DELETE FROM session_workspace")
    conn.commit()


def test_init_empty_session(seeded_db):
    sid = "blank-session"
    db.init_empty_session(sid)
    invalidate_session_cache(sid)
    ws = db.get_session_workspace(sid)
    graph = db.get_session_json(sid, "global")
    assert ws is not None
    assert graph is not None
    g = json.loads(graph)
    assert g["id"] == "global"
    assert len(g["nodes"]) == 2  # start, end
    assert len(g["edges"]) == 0


def test_force_clone_baseline_pharmacy(seeded_db):
    sid = "pharmacy-session"
    db.force_clone_baseline_to_session(sid)
    invalidate_session_cache(sid)
    ws = db.get_session_workspace(sid)
    graph = db.get_session_json(sid, "global")
    assert ws is not None
    assert graph is not None
    ws_data = json.loads(ws)
    assert "global" in ws_data["process_tree"]["processes"]
    g = json.loads(graph)
    assert g["id"] == "global"
    assert len(g["nodes"]) > 2


def test_clone_template_logistics(seeded_db):
    sid = "logistics-session"
    db.clone_template_to_session(sid, "logistics")
    invalidate_session_cache(sid)
    ws = db.get_session_workspace(sid)
    graph = db.get_session_json(sid, "global")
    assert ws is not None
    assert graph is not None
    ws_data = json.loads(ws)
    assert ws_data["process_tree"]["processes"]["global"]["name"] == "Logistics flow"
    g = json.loads(graph)
    assert g["name"] == "Logistics flow"
    assert len(g["nodes"]) == 5
    assert len(g["edges"]) == 4


def test_clone_template_manufacturing(seeded_db):
    sid = "manufacturing-session"
    db.clone_template_to_session(sid, "manufacturing")
    invalidate_session_cache(sid)
    ws = db.get_session_workspace(sid)
    graph = db.get_session_json(sid, "global")
    assert ws is not None
    assert graph is not None
    ws_data = json.loads(ws)
    assert ws_data["process_tree"]["processes"]["global"]["name"] == "Manufacturing flow"
    g = json.loads(graph)
    assert g["name"] == "Manufacturing flow"
    assert len(g["nodes"]) == 5
    assert len(g["edges"]) == 4


def test_get_workspace_and_graph_after_template_clone(seeded_db):
    """Store layer: get_workspace_json and get_graph_json return correct data after clone."""
    sid = "store-test-logistics"
    db.clone_template_to_session(sid, "logistics")
    invalidate_session_cache(sid)
    ws_str = get_workspace_json(sid)
    graph_str = get_graph_json(sid, "global")
    assert ws_str is not None
    assert graph_str is not None
    ws = json.loads(ws_str)
    graph = json.loads(graph_str)
    assert ws["process_tree"]["processes"]["global"]["name"] == "Logistics flow"
    assert graph["name"] == "Logistics flow"
    step_names = [n.get("name") for n in graph["nodes"] if n.get("type") == "step"]
    assert "Receive order" in step_names
    assert "Dispatch" in step_names
    assert "Deliver" in step_names

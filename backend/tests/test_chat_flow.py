"""Chat flow: run_chat returns (message, graph_json, tools_used, ...); API returns meta."""
import json

from agent import run_chat


def test_run_chat_returns_tools_used_flag():

    sid = "test-returns-three"
    result = run_chat(sid, [{"role": "user", "content": "What is P1.1?"}], max_rounds=1)
    msg, graph_json_str, tools_used, tools_called, api_calls, input_tokens, output_tokens, pending_plan, requires_confirmation = result
    assert isinstance(msg, str)
    assert isinstance(graph_json_str, str)
    data = json.loads(graph_json_str)
    assert "steps" in data
    assert isinstance(tools_used, bool)
    assert tools_used is False


def test_api_chat_returns_meta(client):
    resp = client.post("/api/chat", json={"session_id": "meta-test-session", "process_id": "Process_P1", "message": "Hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "graph_json" in data
    assert "meta" in data
    assert data["meta"]["session_id"] == "meta-test-session"
    assert data["meta"]["process_id"] == "Process_P1"
    assert "tools_used" in data["meta"]


def test_api_chat_rejects_empty_session_id(client):
    resp = client.post("/api/chat", json={"session_id": "", "message": "Hi"})
    assert resp.status_code == 422


def test_api_graph_endpoint_removed(client):
    resp = client.get("/api/graph", params={"session_id": "test-session"})
    assert resp.status_code == 404

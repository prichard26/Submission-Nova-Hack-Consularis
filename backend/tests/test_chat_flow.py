"""Chat flow: run_chat returns a ChatResult and API returns meta."""

from agent import run_chat


def test_run_chat_returns_tools_used_flag():

    sid = "test-returns-three"
    result = run_chat(sid, [{"role": "user", "content": "What is P1.1?"}])
    assert isinstance(result.message, str)
    assert isinstance(result.include_graph, bool)
    assert result.include_graph is True
    assert isinstance(result.tools_used, bool)
    assert result.tools_used is False


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

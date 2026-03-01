"""Chat flow: run_chat returns (message, bpmn_xml, tools_used); API returns meta."""
import os

from fastapi.testclient import TestClient

# Force no Groq key so run_chat returns without calling API
os.environ["GROQ_KEY"] = "missing"

from main import app

# Tests use the app's global store via TestClient
client = TestClient(app)


def test_run_chat_returns_tools_used_flag():
    from agent.runtime import run_chat
    from graph_store import get_or_create_session

    sid = "test-returns-three"
    get_or_create_session(sid)
    msg, bpmn_xml, tools_used = run_chat(sid, [{"role": "user", "content": "What is P1.1?"}], max_rounds=1)
    assert isinstance(msg, str)
    assert isinstance(bpmn_xml, str)
    assert "process" in bpmn_xml
    assert isinstance(tools_used, bool)
    # Without real Groq, we get the "GROQ_KEY is not set" message and no tools run
    assert tools_used is False


def test_api_chat_returns_meta():
    resp = client.post("/api/chat", json={"session_id": "meta-test-session", "message": "Hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "bpmn_xml" in data
    assert "meta" in data
    assert data["meta"]["session_id"] == "meta-test-session"
    assert "tools_used" in data["meta"]
    assert "fallback_used" in data["meta"]


def test_api_chat_rejects_empty_session_id():
    resp = client.post("/api/chat", json={"session_id": "", "message": "Hi"})
    assert resp.status_code == 422  # validation error


def test_api_graph_endpoint_removed():
    resp = client.get("/api/graph", params={"session_id": "test-session"})
    assert resp.status_code == 404

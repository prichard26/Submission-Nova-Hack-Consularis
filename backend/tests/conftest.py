"""Pytest fixtures: isolate BPMN store state per test; DI override for session store."""
import pytest


@pytest.fixture(autouse=True)
def reset_graph_store():
    """Reset in-memory session state so tests don't leak between runs."""
    from bpmn import store as bpmn_store
    bpmn_store._sessions.clear()
    bpmn_store._session_registries.clear()
    yield
    bpmn_store._sessions.clear()
    bpmn_store._session_registries.clear()


@pytest.fixture(autouse=True)
def force_missing_groq_key(monkeypatch):
    """Keep tests offline by forcing chat runtime into no-key mode."""
    monkeypatch.setenv("GROQ_KEY", "missing")
    import config as app_config
    import agent.runtime as runtime

    monkeypatch.setattr(app_config, "GROQ_KEY", "missing", raising=False)
    monkeypatch.setattr(runtime, "GROQ_KEY", "missing", raising=False)


@pytest.fixture
def test_store():
    """Fresh in-memory session store for one test. Use with client fixture for isolated API tests."""
    from storage import InMemorySessionStore
    return InMemorySessionStore()


@pytest.fixture
def client(test_store):
    """TestClient with session store overridden so tests don't depend on the global store."""
    from fastapi.testclient import TestClient
    from main import app
    from deps import get_session_store

    app.dependency_overrides[get_session_store] = lambda: test_store
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.clear()

"""Pytest fixtures: isolate BPMN store state per test."""
import pytest


@pytest.fixture(autouse=True)
def reset_graph_store():
    """Reset in-memory session state so tests don't leak between runs."""
    from bpmn import store as bpmn_store
    bpmn_store._sessions.clear()
    yield
    bpmn_store._sessions.clear()


@pytest.fixture(autouse=True)
def force_missing_groq_key(monkeypatch):
    """Keep tests offline by forcing chat runtime into no-key mode."""
    monkeypatch.setenv("GROQ_KEY", "missing")
    import config as app_config
    import agent.runtime as runtime

    monkeypatch.setattr(app_config, "GROQ_KEY", "missing", raising=False)
    monkeypatch.setattr(runtime, "GROQ_KEY", "missing", raising=False)

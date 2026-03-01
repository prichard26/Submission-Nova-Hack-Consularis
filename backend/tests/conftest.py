"""Pytest fixtures: isolate graph_store state per test."""
import pytest


@pytest.fixture(autouse=True)
def reset_graph_store():
    """Reset in-memory session state so tests don't leak between runs."""
    import graph_store as gs
    gs._sessions.clear()
    yield
    gs._sessions.clear()

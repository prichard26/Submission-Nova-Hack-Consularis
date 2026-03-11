"""Pytest fixtures: isolate graph store state per test."""
import pytest


@pytest.fixture(autouse=True)
def reset_db():
    """Reset in-memory SQLite state so tests don't leak between runs.
    Also ensures baseline is seeded."""
    import db as _db
    from graph.store import init_baseline
    from graph import store as graph_store

    _db.get_conn()
    init_baseline()

    conn = _db.get_conn()
    conn.execute("DELETE FROM session_processes")
    conn.execute("DELETE FROM session_workspace")
    conn.execute("DELETE FROM chat_messages")
    conn.commit()
    graph_store._cache.clear()
    graph_store._ws_cache.clear()
    yield
    conn.execute("DELETE FROM session_processes")
    conn.execute("DELETE FROM session_workspace")
    conn.execute("DELETE FROM chat_messages")
    conn.commit()
    graph_store._cache.clear()
    graph_store._ws_cache.clear()


@pytest.fixture
def client():
    """TestClient for API tests."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as tc:
        yield tc

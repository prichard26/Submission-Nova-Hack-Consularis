"""Pytest fixtures for Consularis backend tests.

- reset_db (autouse): before each test, (re)init DB, seed baseline, clear session tables and store caches;
  after the test, clear again. Ensures no cross-test leakage.
- client: FastAPI TestClient wrapping the main app for HTTP tests.
"""
import pytest


@pytest.fixture(autouse=True)
def reset_db():
    """Reset in-memory SQLite and graph store caches so each test sees a clean baseline. Runs before and after each test."""
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

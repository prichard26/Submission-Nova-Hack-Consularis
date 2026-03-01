"""Shared dependencies: session store. Avoids circular imports between main and routers."""
from config import STORAGE
from storage import InMemorySessionStore, FileSessionStore

# Single source of truth: one store for graph (via graph_store) + chat
_store = InMemorySessionStore() if STORAGE != "file" else FileSessionStore()


def get_session_store():
    """Return the application session store. Used by routers and (after 1.2) overridable in tests."""
    return _store

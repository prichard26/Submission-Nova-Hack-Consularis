"""In-memory SessionStore: graph from graph_store, chat in a dict. Single interface for both."""
from graph_store import get_graph, get_or_create_session


class InMemorySessionStore:
    """Holds chat history per session; graph lives in graph_store (same session_id)."""

    def __init__(self) -> None:
        self._chat: dict[str, list[dict]] = {}

    def ensure_session(self, session_id: str) -> None:
        get_or_create_session(session_id)
        if session_id not in self._chat:
            self._chat[session_id] = []

    def get_graph(self, session_id: str) -> dict:
        self.ensure_session(session_id)
        return get_graph(session_id)

    def get_chat_history(self, session_id: str) -> list[dict]:
        self.ensure_session(session_id)
        return list(self._chat[session_id])

    def append_chat_message(self, session_id: str, role: str, content: str) -> None:
        self.ensure_session(session_id)
        self._chat[session_id].append({"role": role, "content": content})

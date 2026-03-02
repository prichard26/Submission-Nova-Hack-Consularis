"""In-memory SessionStore: graphs from graph_store, chat in a dict."""
from graph_store import get_bpmn_xml, get_or_create_session, get_process_tree


class InMemorySessionStore:
    """Holds chat history per session; graph lives in graph_store (same session_id)."""

    def __init__(self) -> None:
        self._chat: dict[str, list[dict]] = {}

    def ensure_session(self, session_id: str) -> None:
        get_or_create_session(session_id)
        if session_id not in self._chat:
            self._chat[session_id] = []

    def get_bpmn_xml(self, session_id: str, process_id: str | None = None) -> str:
        self.ensure_session(session_id)
        return get_bpmn_xml(session_id, process_id=process_id)

    def get_process_tree(self, session_id: str) -> list[dict]:
        self.ensure_session(session_id)
        return get_process_tree(session_id)

    def get_chat_history(self, session_id: str) -> list[dict]:
        self.ensure_session(session_id)
        return list(self._chat[session_id])

    def append_chat_message(self, session_id: str, role: str, content: str) -> None:
        self.ensure_session(session_id)
        self._chat[session_id].append({"role": role, "content": content})

"""SessionStore protocol: one interface for graph + chat per session."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class SessionStore(Protocol):
    """Single source of truth for session state: graph and chat history."""

    def get_bpmn_xml(self, session_id: str, process_id: str | None = None) -> str:
        """Return BPMN XML for this session (creates from baseline if new)."""
        ...

    def get_process_tree(self, session_id: str) -> list[dict]:
        """Return hierarchical process tree for this session."""
        ...

    def get_chat_history(self, session_id: str) -> list[dict]:
        """Return list of messages: { role, content }."""
        ...

    def append_chat_message(self, session_id: str, role: str, content: str) -> None:
        """Append one message to the session's chat history."""
        ...

    def ensure_session(self, session_id: str) -> None:
        """Ensure a session exists (graph from baseline, empty chat if new)."""
        ...

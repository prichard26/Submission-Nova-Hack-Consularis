"""
File-backed SessionStore: one JSON file per session (graph as BPMN XML string + chat).
Use STORAGE=file and optionally SESSION_DATA_DIR to enable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from config import SESSION_DATA_DIR
from graph_store import get_bpmn_xml, get_or_create_session, set_session


def _safe_filename(session_id: str) -> str:
    """Sanitize session_id for use as filename (no path traversal, no invalid chars)."""
    s = re.sub(r'[^\w\-.]', '_', session_id)
    return s[:200] if s else "default"


class FileSessionStore:
    """Persists graph + chat to one JSON file per session. Graph mutations go through graph_store."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else SESSION_DATA_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._chat: dict[str, list[dict]] = {}

    def _path(self, session_id: str) -> Path:
        return self._data_dir / f"{_safe_filename(session_id)}.json"

    def _load(self, session_id: str) -> tuple[str | dict | None, list[dict] | None]:
        p = self._path(session_id)
        if not p.exists():
            return None, None
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("graph"), data.get("chat")
        except (json.JSONDecodeError, OSError):
            return None, None

    def _save(self, session_id: str) -> None:
        graph = get_bpmn_xml(session_id)
        chat = self._chat.get(session_id, [])
        p = self._path(session_id)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"graph": graph, "chat": chat}, f, indent=2, ensure_ascii=False)

    def ensure_session(self, session_id: str) -> None:
        graph, chat = self._load(session_id)
        if graph is not None and chat is not None:
            if isinstance(graph, dict):
                # Backward compatibility: migrate older JSON graph sessions to BPMN XML.
                from bpmn.adapter import legacy_to_model
                from bpmn.serializer import serialize_bpmn_xml
                graph = serialize_bpmn_xml(legacy_to_model(graph))
            set_session(session_id, graph)
            self._chat[session_id] = chat
        else:
            get_or_create_session(session_id)
            self._chat[session_id] = []
            self._save(session_id)

    def get_bpmn_xml(self, session_id: str) -> str:
        self.ensure_session(session_id)
        return get_bpmn_xml(session_id)

    def get_chat_history(self, session_id: str) -> list[dict]:
        self.ensure_session(session_id)
        return list(self._chat[session_id])

    def append_chat_message(self, session_id: str, role: str, content: str) -> None:
        self.ensure_session(session_id)
        self._chat[session_id].append({"role": role, "content": content})
        self._save(session_id)

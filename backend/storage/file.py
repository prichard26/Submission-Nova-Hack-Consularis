"""
File-backed SessionStore: one JSON file per session (graph as BPMN XML string + chat).
Use STORAGE=file and optionally SESSION_DATA_DIR to enable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from config import SESSION_DATA_DIR
from graph_store import (
    get_bpmn_xml,
    get_or_create_session,
    set_session,
    get_process_ids,
    get_process_tree,
)


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

    def _load(self, session_id: str) -> tuple[dict | None, list[dict] | None]:
        p = self._path(session_id)
        if not p.exists():
            return None, None
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return data, data.get("chat")
        except (json.JSONDecodeError, OSError):
            return None, None

    def _save(self, session_id: str) -> None:
        process_ids = get_process_ids(session_id)
        graphs = {pid: get_bpmn_xml(session_id, process_id=pid) for pid in process_ids}
        registry = []
        for root in get_process_tree(session_id):
            stack = [root]
            while stack:
                cur = stack.pop()
                registry.append(
                    {
                        "process_id": cur.get("process_id"),
                        "name": cur.get("name"),
                        "parent_id": cur.get("parent_id"),
                    }
                )
                stack.extend(cur.get("children", []))
        chat = self._chat.get(session_id, [])
        p = self._path(session_id)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"graphs": graphs, "registry": registry, "chat": chat}, f, indent=2, ensure_ascii=False)

    def ensure_session(self, session_id: str) -> None:
        payload, chat = self._load(session_id)
        if payload is not None and chat is not None:
            graphs = payload.get("graphs")
            legacy_graph = payload.get("graph")
            if isinstance(legacy_graph, dict):
                # Backward compatibility: migrate older JSON graph sessions to BPMN XML.
                from bpmn.adapter import legacy_to_model
                from bpmn.serializer import serialize_bpmn_xml
                set_session(session_id, serialize_bpmn_xml(legacy_to_model(legacy_graph)))
            elif isinstance(legacy_graph, str):
                set_session(session_id, legacy_graph)
            if isinstance(graphs, dict):
                for process_id, xml in graphs.items():
                    if isinstance(xml, str) and xml.strip():
                        set_session(session_id, xml, process_id=process_id)
            self._chat[session_id] = chat
        else:
            get_or_create_session(session_id)
            self._chat[session_id] = []
            self._save(session_id)

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
        self._save(session_id)

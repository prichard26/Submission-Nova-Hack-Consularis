"""Chat service: one turn (user message -> agent/fallback -> assistant message)."""
from __future__ import annotations

from typing import Any

from agent import run_chat, try_apply_message_update

from storage.base import SessionStore


def handle_chat_turn(
    store: SessionStore,
    session_id: str,
    user_message: str,
) -> tuple[str, str, dict[str, Any]]:
    """
    Append user message, run agent (or fallback), append assistant message.
    Returns (message, bpmn_xml, meta) where meta has tools_used, fallback_used, session_id.
    """
    store.append_chat_message(session_id, "user", user_message)

    message, bpmn_xml, tools_used = run_chat(session_id, store.get_chat_history(session_id))
    fallback_used = False
    if not tools_used:
        fallback_used = try_apply_message_update(session_id, user_message)
        bpmn_xml = store.get_bpmn_xml(session_id)

    store.append_chat_message(session_id, "assistant", message)

    meta = {
        "tools_used": tools_used,
        "fallback_used": fallback_used,
        "session_id": session_id,
    }
    return message, bpmn_xml, meta

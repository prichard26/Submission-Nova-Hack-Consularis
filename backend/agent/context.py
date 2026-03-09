"""Sliding-window chat context: rolling summary of older messages, recent messages verbatim."""
import logging

import db
from config import MAX_RECENT_MESSAGES, NOVA_CHEAP_MODEL_ID, SUMMARY_MODEL_MAX_TOKENS
from agent.bedrock_client import converse_with_retry, extract_response_text

logger = logging.getLogger("consularis.agent")

SUMMARY_SYSTEM = """You are a summarizer. Condense the conversation into a brief factual summary (one short paragraph, under 300 words). Keep: user goals, decisions made, graph changes mentioned or applied, and any pending items. Use plain prose, no bullet lists. Output only the summary."""


def _messages_to_text(messages: list[dict]) -> str:
    """Turn a list of {role, content} messages into a single text block for the model."""
    parts = []
    for m in messages:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        label = "User" if role == "user" else "Assistant"
        parts.append(f"{label}: {content}")
    return "\n\n".join(parts)


def summarize_older_messages(client, existing_summary: str, new_messages: list[dict]) -> str:
    """Produce or update a rolling summary. Single Bedrock call with NOVA_CHEAP_MODEL_ID."""
    if not new_messages:
        return existing_summary.strip()
    new_text = _messages_to_text(new_messages)
    if not new_text.strip():
        return existing_summary.strip()

    user_content = "Previous summary:\n" + (existing_summary.strip() or "(none)") + "\n\nNew messages to incorporate:\n" + new_text
    system_block = [{"text": SUMMARY_SYSTEM}]
    messages = [{"role": "user", "content": [{"text": user_content}]}]
    kwargs = {
        "modelId": NOVA_CHEAP_MODEL_ID,
        "system": system_block,
        "messages": messages,
        "inferenceConfig": {"maxTokens": SUMMARY_MODEL_MAX_TOKENS, "temperature": 0.2},
    }
    try:
        response = converse_with_retry(client, **kwargs)
        summary = extract_response_text(response)
        return (summary or existing_summary or "").strip()
    except Exception as e:
        logger.warning("summarize_older_messages failed: %s; keeping existing summary", e, exc_info=True)
        return existing_summary.strip()


def prepare_chat_context(client, session_id: str, messages: list[dict], max_recent: int | None = None) -> tuple[str, list[dict]]:
    """Return (summary_text, recent_messages). If len(messages) <= max_recent, summary_text is empty and recent_messages is all messages. Otherwise older messages are summarized and only the last max_recent are kept verbatim."""
    if max_recent is None:
        max_recent = MAX_RECENT_MESSAGES
    if len(messages) <= max_recent:
        return ("", messages)

    older = messages[:-max_recent]
    recent = messages[-max_recent:]
    last_older_id = older[-1]["id"] if older else None
    if last_older_id is None:
        return ("", recent)

    stored = db.get_conversation_summary(session_id)
    summarized_up_to = stored[1] if stored else 0
    summary_text = stored[0] if stored else ""

    if last_older_id > summarized_up_to:
        new_msgs = [m for m in older if m["id"] > summarized_up_to]
        summary_text = summarize_older_messages(client, summary_text, new_msgs)
        db.upsert_conversation_summary(session_id, summary_text, last_older_id)
        logger.info("[CONTEXT] session_id=%s summarized up to message id=%s", session_id, last_older_id)

    return (summary_text, recent)

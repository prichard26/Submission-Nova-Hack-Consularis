"""Chat endpoint: POST /api/chat."""
import asyncio
import json
import logging
import threading
from collections import OrderedDict

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

import db
import stats
from agent import run_chat
from config import SESSION_ID_MAX_LEN

logger = logging.getLogger("consularis")

# Tools that change graph structure; when any is used we set meta.structural_change so the frontend can auto-arrange.
STRUCTURAL_TOOLS = frozenset({
    "add_node", "delete_node", "add_edge", "delete_edge", "update_edge",
    "add_lane", "delete_lane", "move_node", "reorder_steps", "reorder_lanes",
})


def _handle_chat_turn(session_id: str, user_message: str, process_id: str | None):
    """Append user message, run agent, append assistant message."""
    db.append_chat_message(session_id, "user", user_message)
    message, graph_json_str, tools_used, tools_called, api_calls, input_tokens, output_tokens = run_chat(
        session_id, db.get_chat_history(session_id), process_id=process_id
    )
    db.append_chat_message(session_id, "assistant", message)
    structural_change = any(t in STRUCTURAL_TOOLS for t in tools_called)
    stats.add_usage(api_calls=api_calls, input_tokens=input_tokens, output_tokens=output_tokens)
    cumulative = stats.get_stats()
    meta = {
        "tools_used": tools_used,
        "structural_change": structural_change,
        "session_id": session_id,
        "process_id": process_id,
        "tool_calls_this_turn": tools_called,
        "api_calls_this_turn": api_calls,
        "input_tokens_this_turn": input_tokens,
        "output_tokens_this_turn": output_tokens,
        "total_api_calls": cumulative["total_api_calls"],
        "total_input_tokens": cumulative["total_input_tokens"],
        "total_output_tokens": cumulative["total_output_tokens"],
        "total_tokens": cumulative["total_tokens"],
    }
    return message, graph_json_str, meta


MAX_SESSION_LOCKS = 500
_session_locks: OrderedDict[str, threading.Lock] = OrderedDict()
_locks_guard = threading.Lock()


def _lock_for_session(session_id: str) -> threading.Lock:
    with _locks_guard:
        if session_id in _session_locks:
            _session_locks.move_to_end(session_id)
            return _session_locks[session_id]
        while len(_session_locks) >= MAX_SESSION_LOCKS:
            _session_locks.popitem(last=False)
        lock = threading.Lock()
        _session_locks[session_id] = lock
        return lock


router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str
    process_id: str | None = None

    @field_validator("session_id")
    @classmethod
    def session_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("session_id is required")
        if len(v) > SESSION_ID_MAX_LEN:
            raise ValueError(f"session_id must be at most {SESSION_ID_MAX_LEN} characters")
        return v.strip()


class ChatResponseMeta(BaseModel):
    tools_used: bool
    structural_change: bool = False
    session_id: str
    process_id: str | None = None
    tool_calls_this_turn: list[str] = []
    api_calls_this_turn: int = 0
    input_tokens_this_turn: int = 0
    output_tokens_this_turn: int = 0
    total_api_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    message: str
    graph_json: dict | None = None
    process_id: str | None = None
    meta: ChatResponseMeta


@router.get("/stats")
async def api_stats():
    """Return cumulative API usage: total_api_calls, total_input_tokens, total_output_tokens, total_tokens."""
    return stats.get_stats()


@router.post("/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest):
    session_id = req.session_id
    lock = _lock_for_session(session_id)
    with lock:
        message, graph_json_str, meta = await asyncio.to_thread(
            _handle_chat_turn, session_id, req.message, req.process_id
        )
        logger.info(
            "chat session_id=%s process_id=%s tools_used=%s",
            session_id, req.process_id, meta["tools_used"],
        )
        graph_dict = None
        if graph_json_str:
            try:
                graph_dict = json.loads(graph_json_str)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "message": message,
            "graph_json": graph_dict,
            "process_id": req.process_id,
            "meta": meta,
        }

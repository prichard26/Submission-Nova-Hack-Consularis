"""Chat endpoint: OPTIONS + POST /api/chat."""
import asyncio
import json
import logging
import threading
from collections import OrderedDict

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

import db
from agent import run_chat
from config import SESSION_ID_MAX_LEN

logger = logging.getLogger("consularis")


def _handle_chat_turn(session_id: str, user_message: str, process_id: str | None):
    """Append user message, run agent, append assistant message."""
    db.append_chat_message(session_id, "user", user_message)
    message, graph_json_str, tools_used = run_chat(session_id, db.get_chat_history(session_id), process_id=process_id)
    db.append_chat_message(session_id, "assistant", message)
    meta = {"tools_used": tools_used, "session_id": session_id, "process_id": process_id}
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
    session_id: str
    process_id: str | None = None


class ChatResponse(BaseModel):
    message: str
    graph_json: dict | None = None
    bpmn_xml: str | None = None
    process_id: str | None = None
    meta: ChatResponseMeta


@router.options("/chat")
def options_chat():
    return Response(status_code=200)


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

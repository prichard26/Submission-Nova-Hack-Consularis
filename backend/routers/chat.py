"""Chat endpoint: OPTIONS + POST /api/chat."""
import asyncio
import logging
import threading
from collections import OrderedDict
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from config import SESSION_ID_MAX_LEN
from deps import get_session_store
from storage.base import SessionStore
from services.chat import handle_chat_turn

logger = logging.getLogger("consularis")

# Per-session lock: at most one chat request at a time per session (bounded cache)
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
    fallback_used: bool
    session_id: str


class ChatResponse(BaseModel):
    message: str
    bpmn_xml: str
    meta: ChatResponseMeta


@router.options("/chat")
def options_chat():
    return Response(status_code=200)


@router.post("/chat", response_model=ChatResponse)
async def api_chat(
    req: ChatRequest,
    store: Annotated[SessionStore, Depends(get_session_store)],
):
    session_id = req.session_id
    lock = _lock_for_session(session_id)
    with lock:
        message, bpmn_xml, meta = await asyncio.to_thread(
            handle_chat_turn, store, session_id, req.message
        )
        logger.info(
            "chat session_id=%s tools_used=%s fallback_used=%s",
            session_id, meta["tools_used"], meta["fallback_used"],
        )
        return {"message": message, "bpmn_xml": bpmn_xml, "meta": meta}

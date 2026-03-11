"""Chat endpoint: POST /api/chat, POST /api/chat/confirm, GET /api/models."""
import asyncio
import json
import logging
import threading
from collections import OrderedDict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import db
import stats
from config import BEDROCK_MODELS, NOVA_MODEL_ID
from agent import run_chat
from agent.runtime_nova import run_chat_confirm
from graph.store import get_graph_dict_for_client
from routers.validation import validate_session_id

logger = logging.getLogger("consularis")

# Tools that change graph structure; when any is used we set meta.structural_change so the frontend can auto-arrange.
STRUCTURAL_TOOLS = frozenset({
    "add_node", "insert_step_between", "insert_subprocess_between", "delete_node", "add_edge", "delete_edge", "update_edge",
})


def _build_meta(
    session_id: str,
    process_id: str | None,
    tools_used: bool,
    tools_called: list[str],
    api_calls: int,
    input_tokens: int,
    output_tokens: int,
    requires_confirmation: bool = False,
    pending_plan: dict | None = None,
) -> dict:
    structural_change = any(t in STRUCTURAL_TOOLS for t in tools_called)
    stats.add_usage(api_calls=api_calls, input_tokens=input_tokens, output_tokens=output_tokens)
    cumulative = stats.get_stats()
    return {
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
        "requires_confirmation": requires_confirmation,
        "pending_plan": pending_plan,
    }


def _build_chat_response(message: str, session_id: str, process_id: str | None, meta: dict, include_graph: bool) -> dict:
    graph_dict = _try_get_graph_dict(session_id, process_id, include_graph, meta)
    workspace_dict = None
    if graph_dict is not None:
        try:
            ws_json = db.get_session_workspace(session_id)
            workspace_dict = json.loads(ws_json) if ws_json else None
        except Exception:
            logger.warning("workspace parse failed for session_id=%s", session_id, exc_info=True)
    return {
        "message": message,
        "graph_json": graph_dict,
        "workspace": workspace_dict,
        "process_id": process_id,
        "meta": meta,
    }


def _handle_chat_turn(session_id: str, user_message: str, process_id: str | None, model_id: str | None = None):
    """Append user message, run agent, append assistant message."""
    db.append_chat_message(session_id, "user", user_message)
    result = run_chat(session_id, db.get_chat_history(session_id), process_id=process_id, model_id=model_id)
    db.append_chat_message(session_id, "assistant", result.message)
    meta = _build_meta(
        session_id,
        process_id,
        result.tools_used,
        result.tools_called,
        result.api_calls,
        result.input_tokens,
        result.output_tokens,
        result.requires_confirmation,
        result.pending_plan,
    )
    return result.message, result.include_graph, meta


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


def _try_get_graph_dict(session_id: str, process_id: str | None, include_graph: bool, meta: dict) -> dict | None:
    if not (include_graph or meta.get("tools_used") or meta.get("structural_change")):
        return None
    try:
        return get_graph_dict_for_client(session_id, process_id)
    except Exception:
        logger.warning("get_graph_dict_for_client failed for session_id=%s", session_id, exc_info=True)
        return None


router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str
    process_id: str | None = None
    model_id: str | None = None

    @field_validator("session_id")
    @classmethod
    def session_id_non_empty(cls, v: str) -> str:
        return validate_session_id(v)


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
    requires_confirmation: bool = False
    pending_plan: dict | None = None


class ChatResponse(BaseModel):
    message: str
    graph_json: dict | None = None
    workspace: dict | None = None
    process_id: str | None = None
    meta: ChatResponseMeta


class ChatConfirmRequest(BaseModel):
    session_id: str
    process_id: str | None = None

    @field_validator("session_id")
    @classmethod
    def session_id_non_empty(cls, v: str) -> str:
        return validate_session_id(v)


@router.get("/stats")
async def api_stats():
    """Return cumulative API usage: total_api_calls, total_input_tokens, total_output_tokens, total_tokens."""
    return stats.get_stats()


@router.get("/models")
async def api_models():
    """Return the list of available Bedrock models for the planner/reasoning role."""
    models = []
    for model_id, info in BEDROCK_MODELS.items():
        models.append({
            "id": model_id,
            "label": info["label"],
            "family": info["family"],
            "tier": info["tier"],
            "description": info["description"],
            "is_default": model_id == NOVA_MODEL_ID,
        })
    return {"models": models, "default": NOVA_MODEL_ID}


@router.post("/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest):
    session_id = req.session_id
    lock = _lock_for_session(session_id)
    with lock:
        message, include_graph, meta = await asyncio.to_thread(
            _handle_chat_turn, session_id, req.message, req.process_id, req.model_id
        )
        logger.info(
            "chat session_id=%s process_id=%s tools_used=%s",
            session_id, req.process_id, meta["tools_used"],
        )
        return _build_chat_response(message, session_id, req.process_id, meta, include_graph)


@router.post("/chat/confirm", response_model=ChatResponse)
async def api_chat_confirm(req: ChatConfirmRequest):
    """Run the stored pending plan (from propose_plan). Returns same shape as /chat."""
    session_id = req.session_id
    lock = _lock_for_session(session_id)
    with lock:
        result = await asyncio.to_thread(run_chat_confirm, session_id, req.process_id)
    if result is None:
        raise HTTPException(status_code=400, detail="No pending plan to apply. Send a message and ask for a plan first.")
    db.append_chat_message(session_id, "assistant", result.message)
    meta = _build_meta(
        session_id,
        req.process_id,
        result.tools_used,
        result.tools_called,
        result.api_calls,
        result.input_tokens,
        result.output_tokens,
    )
    return _build_chat_response(result.message, session_id, req.process_id, meta, result.include_graph)

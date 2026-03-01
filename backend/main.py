import copy
import logging
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from config import GROQ_KEY, ALLOWED_CORS_ORIGINS, SESSION_ID_MAX_LEN, STORAGE
from storage import InMemorySessionStore, FileSessionStore
from agent import run_chat, try_apply_message_update
from graph_store import init_baseline

logger = logging.getLogger("consularis")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

# Single source of truth: one store for graph (via graph_store) + chat
store = InMemorySessionStore() if STORAGE != "file" else FileSessionStore()

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_baseline()
    if GROQ_KEY and GROQ_KEY != "missing" and not GROQ_KEY.startswith("your_"):
        logger.info("Consularis: GROQ_KEY is set — Aurelius chat enabled.")
    else:
        logger.info("Consularis: GROQ_KEY not set. Copy backend/env.example to backend/.env and set GROQ_KEY.")
    yield


app = FastAPI(title="Consularis API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def _validate_session_id(session_id: str) -> None:
    if not session_id or not str(session_id).strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    if len(session_id) > SESSION_ID_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"session_id must be at most {SESSION_ID_MAX_LEN} characters")


class DomainSelection(BaseModel):
    domain: str
    company_name: str


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
    graph: dict
    meta: ChatResponseMeta


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/select-domain")
def select_domain(selection: DomainSelection):
    return {
        "message": f"Great choice! We'll analyze {selection.company_name} in the {selection.domain} sector.",
        "domain": selection.domain,
        "company_name": selection.company_name,
        "next_step": "interview",
    }


@app.options("/api/chat")
def options_chat():
    return Response(status_code=200)


@app.get("/api/graph")
def api_get_graph(session_id: str = Query(..., description="Session id (e.g. company name)")):
    _validate_session_id(session_id)
    graph = store.get_graph(session_id)
    return graph


@app.post("/api/chat", response_model=None)
def api_chat(req: ChatRequest):
    session_id = req.session_id
    lock = _lock_for_session(session_id)
    with lock:
        store.append_chat_message(session_id, "user", req.message)

        message, graph, tools_used = run_chat(session_id, store.get_chat_history(session_id))
        fallback_used = False
        if not tools_used:
            fallback_used = try_apply_message_update(session_id, req.message)
            graph = store.get_graph(session_id)
        else:
            graph = store.get_graph(session_id)

        store.append_chat_message(session_id, "assistant", message)

        logger.info("chat session_id=%s tools_used=%s fallback_used=%s", session_id, tools_used, fallback_used)
        return {
            "message": message,
            "graph": copy.deepcopy(graph),
            "meta": {"tools_used": tools_used, "fallback_used": fallback_used, "session_id": session_id},
        }

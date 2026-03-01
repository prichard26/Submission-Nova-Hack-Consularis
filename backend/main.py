import logging
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from config import GROQ_KEY, ALLOWED_CORS_ORIGINS, SESSION_ID_MAX_LEN, STORAGE, BASELINE_GRAPH_PATH
from storage import InMemorySessionStore, FileSessionStore
from agent import run_chat, try_apply_message_update
from graph_store import init_baseline, get_bpmn_xml, get_graph_json
from bpmn.parser import parse_bpmn_xml
from bpmn.serializer import serialize_bpmn_xml

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
    bpmn_xml: str
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


@app.get("/api/graph/baseline")
def api_baseline_bpmn():
    """Return the baseline BPMN 2.0 XML with diagram interchange so bpmn-js can display it."""
    if not BASELINE_GRAPH_PATH.exists():
        raise HTTPException(status_code=404, detail="Baseline graph file not found")
    model = parse_bpmn_xml(BASELINE_GRAPH_PATH)
    xml = serialize_bpmn_xml(model)
    logger.info("graph/baseline served xml_len=%d", len(xml))
    return Response(content=xml, media_type="application/xml")


@app.get("/api/graph/export")
def api_export_bpmn(session_id: str = Query(..., description="Session id")):
    """Return the session graph as BPMN 2.0 XML for download."""
    _validate_session_id(session_id)
    store.ensure_session(session_id)
    xml = get_bpmn_xml(session_id)
    logger.info("graph/export session_id=%s xml_len=%d", session_id, len(xml))
    return Response(content=xml, media_type="application/xml")


@app.get("/api/graph/json")
def api_export_graph_json(session_id: str = Query(..., description="Session id")):
    """Return the session graph as JSON for custom renderers."""
    _validate_session_id(session_id)
    store.ensure_session(session_id)
    graph = get_graph_json(session_id)
    logger.info(
        "graph/json session_id=%s lanes=%d nodes=%d edges=%d",
        session_id,
        len(graph.get("lanes", [])),
        len(graph.get("nodes", [])),
        len(graph.get("edges", [])),
    )
    return graph


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest):
    session_id = req.session_id
    lock = _lock_for_session(session_id)
    with lock:
        store.append_chat_message(session_id, "user", req.message)

        message, bpmn_xml, tools_used = run_chat(session_id, store.get_chat_history(session_id))
        fallback_used = False
        if not tools_used:
            fallback_used = try_apply_message_update(session_id, req.message)
            bpmn_xml = store.get_bpmn_xml(session_id)

        store.append_chat_message(session_id, "assistant", message)

        logger.info("chat session_id=%s tools_used=%s fallback_used=%s", session_id, tools_used, fallback_used)
        return {
            "message": message,
            "bpmn_xml": bpmn_xml,
            "meta": {"tools_used": tools_used, "fallback_used": fallback_used, "session_id": session_id},
        }

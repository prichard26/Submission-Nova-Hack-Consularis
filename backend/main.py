from pathlib import Path
import copy
import os

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env")

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from graph_store import get_graph
from agent import run_chat, try_apply_message_update

app = FastAPI(title="Consularis API")


@app.on_event("startup")
def startup():
    """Log whether Groq key is available (no key value printed)."""
    key = os.getenv("GROQ_KEY", "")
    if key and key != "missing" and not key.startswith("your_"):
        print("Consularis: GROQ_KEY is set — Aurelius chat enabled.")
    else:
        print("Consularis: GROQ_KEY not set. Copy backend/env.example to backend/.env and set GROQ_KEY.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Chat history per session: session_id -> list of { "role": "user"|"assistant", "content": "..." }
_chat_history: dict[str, list[dict]] = {}


class DomainSelection(BaseModel):
    domain: str
    company_name: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


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
    """CORS preflight for POST /api/chat."""
    return Response(status_code=200)


@app.get("/api/graph")
def api_get_graph(session_id: str = Query(..., description="Session id (e.g. company name)")):
    """Return the process graph for this session. Creates one from default if new."""
    graph = get_graph(session_id)
    return graph


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    """Send a message to Aurelius; returns reply and updated graph."""
    session_id = req.session_id
    if session_id not in _chat_history:
        _chat_history[session_id] = []

    _chat_history[session_id].append({"role": "user", "content": req.message})

    # Apply fallback first so the graph is updated even when the model doesn't call tools.
    # Then run_chat can still reply nicely; we always return the graph after both.
    try_apply_message_update(session_id, req.message)
    message, graph = run_chat(session_id, _chat_history[session_id])
    try_apply_message_update(session_id, req.message)  # again in case fallback didn't match before
    graph = get_graph(session_id)

    _chat_history[session_id].append({"role": "assistant", "content": message})

    # Return a deep copy so the frontend always gets a new object and the diagram re-renders
    return {"message": message, "graph": copy.deepcopy(graph)}

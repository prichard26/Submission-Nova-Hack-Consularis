import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import GROQ_KEY, ALLOWED_CORS_ORIGINS
from db import get_conn
from graph.store import init_baseline
from routers import health_router, chat_router, graph_router, analyze_router, session_router

logger = logging.getLogger("consularis")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_conn()
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

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(graph_router)
app.include_router(analyze_router)
app.include_router(session_router)

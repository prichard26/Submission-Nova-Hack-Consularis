"""Analyze and appointment endpoints: automation analysis LLM and book-appointment email capture."""
import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import db
from agent.analyzer import run_analysis
from config import SESSION_ID_MAX_LEN
from graph.store import get_analysis_metrics

logger = logging.getLogger("consularis")

router = APIRouter(prefix="/api", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    session_id: str

    @field_validator("session_id")
    @classmethod
    def session_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("session_id is required")
        if len(v) > SESSION_ID_MAX_LEN:
            raise ValueError(f"session_id must be at most {SESSION_ID_MAX_LEN} characters")
        return v.strip()


class AnalyzeResponse(BaseModel):
    message: str
    metrics: dict | None = None  # overall_score, categories, counts


class AppointmentRequest(BaseModel):
    session_id: str
    email: str
    name: str | None = None

    @field_validator("session_id")
    @classmethod
    def session_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("session_id is required")
        if len(v) > SESSION_ID_MAX_LEN:
            raise ValueError(f"session_id must be at most {SESSION_ID_MAX_LEN} characters")
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("email is required")
        if len(v) > 320:
            raise ValueError("email too long")
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError("invalid email format")
        return v


class AppointmentResponse(BaseModel):
    ok: bool = True


@router.post("/analyze", response_model=AnalyzeResponse)
async def api_analyze(req: AnalyzeRequest):
    """Run the automation analyzer on the session's full graph. Returns markdown and metrics."""
    try:
        message = await asyncio.to_thread(run_analysis, req.session_id)
    except Exception as e:
        logger.exception("analyze session_id=%s error: %s", req.session_id, e)
        raise HTTPException(status_code=503, detail="Analysis temporarily unavailable.")
    metrics = None
    try:
        metrics = get_analysis_metrics(req.session_id)
    except Exception as e:
        logger.warning("analyze metrics session_id=%s error: %s", req.session_id, e)
    return AnalyzeResponse(message=message, metrics=metrics)


@router.post("/appointment", response_model=AppointmentResponse)
async def api_appointment(req: AppointmentRequest):
    """Store an appointment request (user email) for Consularis to contact about automation."""
    try:
        await asyncio.to_thread(
            db.insert_appointment_request,
            req.session_id,
            req.email,
            req.name,
        )
    except Exception as e:
        logger.exception("appointment session_id=%s error: %s", req.session_id, e)
        raise HTTPException(status_code=500, detail="Could not save request.")
    return AppointmentResponse(ok=True)

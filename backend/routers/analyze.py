"""
Analyze and report router: automation analysis and Company Process Intelligence Report.

- POST /api/analyze: run automation analyzer (Nova) on session graph; returns markdown + metrics.
- POST /api/report: compute report metrics and generate LLM narratives (executive summary, operations).
- POST /api/appointment: store user email/name for "book appointment" CTA.
"""
import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import db
from agent.analyzer import run_analysis
from agent.report_generator import run_report_narratives
from graph.store import get_analysis_metrics, get_report_metrics
from routers.validation import validate_session_id

logger = logging.getLogger("consularis")

router = APIRouter(prefix="/api", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    session_id: str

    @field_validator("session_id")
    @classmethod
    def session_id_non_empty(cls, v: str) -> str:
        return validate_session_id(v)


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
        return validate_session_id(v)

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


class ReportRequest(BaseModel):
    session_id: str

    @field_validator("session_id")
    @classmethod
    def session_id_non_empty(cls, v: str) -> str:
        return validate_session_id(v)


class ReportResponse(BaseModel):
    metrics: dict  # full get_report_metrics() output
    narratives: dict  # executive_summary, process_narratives, operations_analysis


@router.post("/report", response_model=ReportResponse)
async def api_report(req: ReportRequest):
    """Generate the full Company Process Intelligence Report: computed metrics first, then LLM narratives (executive summary + operations) using Nova."""
    try:
        metrics = await asyncio.to_thread(get_report_metrics, req.session_id)
    except Exception as e:
        logger.exception("report metrics session_id=%s error: %s", req.session_id, e)
        raise HTTPException(status_code=503, detail="Could not load report metrics.")
    try:
        narratives = await asyncio.to_thread(run_report_narratives, req.session_id, metrics)
    except Exception as e:
        logger.exception("report narratives session_id=%s error: %s", req.session_id, e)
        raise HTTPException(status_code=503, detail="Report narratives temporarily unavailable.")
    return ReportResponse(metrics=metrics, narratives=narratives)


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

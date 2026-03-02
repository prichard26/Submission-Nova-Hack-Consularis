"""Graph endpoints: baseline BPMN, export XML, and name resolution."""
import logging

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response

from config import SESSION_ID_MAX_LEN, DEFAULT_PROCESS_ID
from bpmn.store import (
    get_bpmn_xml,
    resolve_step,
    get_baseline_bpmn_xml,
)

logger = logging.getLogger("consularis")


def _validate_session_id(session_id: str) -> None:
    if not session_id or not str(session_id).strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    if len(session_id) > SESSION_ID_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"session_id must be at most {SESSION_ID_MAX_LEN} characters")


router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/baseline")
def api_baseline_bpmn(
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Return the baseline BPMN 2.0 XML with diagram interchange so bpmn-js can display it."""
    xml = get_baseline_bpmn_xml(process_id)
    logger.info("graph/baseline served process_id=%s xml_len=%d", process_id, len(xml))
    return Response(content=xml, media_type="application/xml")


@router.get("/export")
def api_export_bpmn(
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Return the session graph as BPMN 2.0 XML for download."""
    _validate_session_id(session_id)
    xml = get_bpmn_xml(session_id, process_id=process_id)
    logger.info("graph/export session_id=%s process_id=%s xml_len=%d", session_id, process_id, len(xml))
    return Response(content=xml, media_type="application/xml")


@router.get("/resolve")
def api_resolve_step(
    session_id: str = Query(..., description="Session id"),
    name: str = Query(..., description="Step name or id fragment"),
    process_id: str | None = Query(None, description="Optional process id scope"),
):
    """Resolve step names to technical ids for name-based chat."""
    _validate_session_id(session_id)
    matches = resolve_step(session_id, name_fragment=name, process_id=process_id)
    return {"matches": matches}

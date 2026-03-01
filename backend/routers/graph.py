"""Graph endpoints: baseline BPMN, export XML, export JSON."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response

from config import SESSION_ID_MAX_LEN, BASELINE_GRAPH_PATH
from deps import get_session_store
from storage.base import SessionStore
from graph_store import get_bpmn_xml, get_graph_json
from bpmn.parser import parse_bpmn_xml
from bpmn.serializer import serialize_bpmn_xml

logger = logging.getLogger("consularis")


def _validate_session_id(session_id: str) -> None:
    if not session_id or not str(session_id).strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    if len(session_id) > SESSION_ID_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"session_id must be at most {SESSION_ID_MAX_LEN} characters")


router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/baseline")
def api_baseline_bpmn():
    """Return the baseline BPMN 2.0 XML with diagram interchange so bpmn-js can display it."""
    if not BASELINE_GRAPH_PATH.exists():
        raise HTTPException(status_code=404, detail="Baseline graph file not found")
    model = parse_bpmn_xml(BASELINE_GRAPH_PATH)
    xml = serialize_bpmn_xml(model)
    logger.info("graph/baseline served xml_len=%d", len(xml))
    return Response(content=xml, media_type="application/xml")


@router.get("/export")
def api_export_bpmn(
    session_id: str = Query(..., description="Session id"),
    store: Annotated[SessionStore, Depends(get_session_store)],
):
    """Return the session graph as BPMN 2.0 XML for download."""
    _validate_session_id(session_id)
    store.ensure_session(session_id)
    xml = get_bpmn_xml(session_id)
    logger.info("graph/export session_id=%s xml_len=%d", session_id, len(xml))
    return Response(content=xml, media_type="application/xml")


@router.get("/json")
def api_export_graph_json(
    session_id: str = Query(..., description="Session id"),
    store: Annotated[SessionStore, Depends(get_session_store)],
):
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

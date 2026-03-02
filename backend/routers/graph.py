"""Graph endpoints: JSON graph, workspace, BPMN export, name resolution."""
import json
import logging

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from config import SESSION_ID_MAX_LEN, DEFAULT_PROCESS_ID
from graph.store import (
    get_graph_json,
    get_workspace_json,
    get_baseline_json,
    resolve_step,
    undo_graph,
    update_node,
    delete_node,
    add_node,
    update_positions,
)
from graph.bpmn_export import export_bpmn_xml
from graph.model import ProcessGraph

logger = logging.getLogger("consularis")


def _validate_session_id(session_id: str) -> None:
    if not session_id or not str(session_id).strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    if len(session_id) > SESSION_ID_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"session_id must be at most {SESSION_ID_MAX_LEN} characters")


router = APIRouter(prefix="/api/graph", tags=["graph"])


# ---------------------------------------------------------------------------
# JSON-native endpoints (new)
# ---------------------------------------------------------------------------

@router.get("/json")
def api_graph_json(
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Return the session graph as a JSON document."""
    _validate_session_id(session_id)
    graph_json = get_graph_json(session_id, process_id=process_id)
    return Response(content=graph_json, media_type="application/json")


@router.get("/workspace")
def api_workspace(
    session_id: str = Query(..., description="Session id"),
):
    """Return the workspace manifest JSON."""
    _validate_session_id(session_id)
    ws_json = get_workspace_json(session_id)
    return Response(content=ws_json, media_type="application/json")


class StepUpdateRequest(BaseModel):
    step_id: str
    updates: dict


@router.post("/step")
def api_update_step(
    req: StepUpdateRequest,
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Update step fields via direct GUI edit."""
    _validate_session_id(session_id)
    result = update_node(session_id, req.step_id, req.updates, process_id=process_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return result


class NodeCreateRequest(BaseModel):
    lane_id: str
    name: str = "New step"
    type: str = "step"


@router.post("/node")
def api_create_node(
    req: NodeCreateRequest,
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Create a new node in a lane."""
    _validate_session_id(session_id)
    result = add_node(session_id, req.lane_id, {"name": req.name, "type": req.type}, process_id=process_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Lane not found")
    return result


@router.delete("/node")
def api_delete_node(
    session_id: str = Query(..., description="Session id"),
    node_id: str = Query(..., description="Node id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Delete a node."""
    _validate_session_id(session_id)
    ok = delete_node(session_id, node_id, process_id=process_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"deleted": True}


class PositionUpdateRequest(BaseModel):
    positions: dict[str, dict]


@router.post("/position")
def api_update_positions(
    req: PositionUpdateRequest,
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Batch update step positions from drag-and-drop."""
    _validate_session_id(session_id)
    update_positions(session_id, process_id, req.positions)
    return {"ok": True}


# ---------------------------------------------------------------------------
# BPMN export (kept for download)
# ---------------------------------------------------------------------------

@router.get("/export")
def api_export_bpmn(
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Return the session graph as BPMN 2.0 XML for download."""
    _validate_session_id(session_id)
    graph_json = get_graph_json(session_id, process_id=process_id)
    graph = ProcessGraph.from_json(graph_json)
    xml = export_bpmn_xml(graph)
    return Response(content=xml, media_type="application/xml")


@router.get("/baseline")
def api_baseline_bpmn(
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Return baseline as BPMN 2.0 XML."""
    json_str = get_baseline_json(process_id)
    graph = ProcessGraph.from_json(json_str)
    xml = export_bpmn_xml(graph)
    return Response(content=xml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Resolve + Undo
# ---------------------------------------------------------------------------

@router.get("/resolve")
def api_resolve_step(
    session_id: str = Query(..., description="Session id"),
    name: str = Query(..., description="Step name or id fragment"),
    process_id: str | None = Query(None, description="Optional process id scope"),
):
    _validate_session_id(session_id)
    matches = resolve_step(session_id, name_fragment=name, process_id=process_id)
    return {"matches": matches}


@router.post("/undo")
def api_undo_graph(
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    _validate_session_id(session_id)
    restored_json = undo_graph(session_id, process_id=process_id)
    if restored_json is None:
        raise HTTPException(status_code=404, detail="Nothing to undo")
    return {"graph_json": json.loads(restored_json)}

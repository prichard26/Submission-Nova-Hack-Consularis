"""
Graph router: session graph and workspace CRUD, BPMN export, step resolution.

All graph endpoints under /api/graph: JSON get/update, node/edge CRUD, positions,
process rename, reset to baseline, resolve step by name, and BPMN XML export.
"""
import json
import logging

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from config import DEFAULT_PROCESS_ID
from routers.validation import validate_session_id_or_400
from graph.store import (
    get_graph_json,
    get_graph_dict_for_client,
    inject_lanes_for_client,
    get_workspace_json,
    get_baseline_json,
    resolve_step,
    reset_to_baseline,
    update_node,
    delete_node,
    add_node,
    create_subprocess_page,
    add_edge,
    update_edge,
    delete_edge,
    update_positions,
    rename_process,
)
from graph.bpmn_export import export_bpmn_xml
from graph.model import ProcessGraph

logger = logging.getLogger("consularis")


_validate_session_id = validate_session_id_or_400


router = APIRouter(prefix="/api/graph", tags=["graph"])


# ---------------------------------------------------------------------------
# JSON-native endpoints (new)
# ---------------------------------------------------------------------------

@router.get("/json")
def api_graph_json(
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Return the session graph as a JSON document (with process_id and lanes for UI)."""
    _validate_session_id(session_id)
    data = get_graph_dict_for_client(session_id, process_id)
    return Response(content=json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json")


@router.get("/workspace")
def api_workspace(
    session_id: str = Query(..., description="Session id"),
):
    """Return the workspace manifest JSON."""
    _validate_session_id(session_id)
    try:
        ws_json = get_workspace_json(session_id)
    except RuntimeError as e:
        if "No workspace manifest found" in str(e):
            raise HTTPException(
                status_code=503,
                detail="Workspace not ready. Ensure backend/data/pharmacy/workspace.json (or BASELINE_TEMPLATE dir) exists and retry.",
            ) from e
        raise
    return Response(content=ws_json, media_type="application/json")


@router.get("/baseline/json")
def api_baseline_json(
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Return baseline graph as JSON (no session required)."""
    graph_json = get_baseline_json(process_id=process_id)
    return Response(content=graph_json, media_type="application/json")


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
    position: dict | None = None


class SubprocessCreateRequest(BaseModel):
    node_id: str
    name: str | None = None
    parent_process_id: str | None = None


@router.post("/node")
def api_create_node(
    req: NodeCreateRequest,
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Create a new node in a lane."""
    _validate_session_id(session_id)
    result = add_node(
        session_id,
        req.lane_id,
        {"name": req.name, "type": req.type, "position": req.position},
        process_id=process_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Lane not found")
    return result


@router.post("/subprocess/create")
def api_create_subprocess_page(
    req: SubprocessCreateRequest,
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Current process id"),
):
    """Create and link a subprocess page for a subprocess node."""
    _validate_session_id(session_id)
    parent_pid = req.parent_process_id or process_id
    result = create_subprocess_page(session_id, parent_pid, req.node_id, req.name)
    if result is None:
        raise HTTPException(status_code=404, detail="Subprocess node or parent process not found")
    return result


@router.delete("/node")
def api_delete_node(
    session_id: str = Query(..., description="Session id"),
    node_id: str = Query(..., description="Node id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Delete a node."""
    _validate_session_id(session_id)
    result = delete_node(session_id, node_id, process_id=process_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"deleted": True}


class PositionUpdateRequest(BaseModel):
    positions: dict[str, dict]


class EdgeCreateRequest(BaseModel):
    source: str
    target: str
    label: str = ""
    condition: str | None = None
    source_handle: str | None = None
    target_handle: str | None = None


class EdgeUpdateRequest(BaseModel):
    source: str
    target: str
    label: str | None = None
    condition: str | None = None


@router.post("/edge")
def api_create_edge(
    req: EdgeCreateRequest,
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Create an edge (flow) between two nodes."""
    _validate_session_id(session_id)
    result = add_edge(
        session_id,
        req.source,
        req.target,
        label=req.label or "",
        condition=req.condition,
        source_handle=req.source_handle,
        target_handle=req.target_handle,
        process_id=process_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Source or target node not found, or invalid edge")
    return result


@router.put("/edge")
def api_update_edge(
    req: EdgeUpdateRequest,
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Update an existing edge's label or condition."""
    _validate_session_id(session_id)
    updates = {}
    if req.label is not None:
        updates["label"] = req.label
    if req.condition is not None:
        updates["condition"] = req.condition
    result = update_edge(session_id, req.source, req.target, updates, process_id=process_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Edge not found")
    return result


@router.delete("/edge")
def api_delete_edge(
    session_id: str = Query(..., description="Session id"),
    source: str = Query(..., description="Source node id"),
    target: str = Query(..., description="Target node id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Delete an edge between two nodes."""
    _validate_session_id(session_id)
    ok = delete_edge(session_id, source, target, process_id=process_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Edge not found")
    return {"deleted": True}


class ProcessRenameRequest(BaseModel):
    new_name: str


@router.post("/process/rename")
def api_rename_process(
    req: ProcessRenameRequest,
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Rename the current process."""
    _validate_session_id(session_id)
    rename_process(session_id, req.new_name or "", process_id=process_id)
    return {"ok": True}


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
    xml = export_bpmn_xml(graph, process_id=process_id)
    return Response(content=xml, media_type="application/xml")


@router.get("/baseline")
def api_baseline_bpmn(
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    """Return baseline as BPMN 2.0 XML."""
    json_str = get_baseline_json(process_id)
    graph = ProcessGraph.from_json(json_str)
    xml = export_bpmn_xml(graph, process_id=process_id)
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


def _inject_lanes_for_client(data: dict, process_id: str) -> dict:
    return inject_lanes_for_client(data, process_id)


@router.post("/reset")
def api_reset_graph(
    session_id: str = Query(..., description="Session id"),
    process_id: str = Query(DEFAULT_PROCESS_ID, description="Process id"),
):
    _validate_session_id(session_id)
    restored_json = reset_to_baseline(session_id, process_id=process_id)
    data = _inject_lanes_for_client(json.loads(restored_json), process_id)
    return {"graph_json": data}

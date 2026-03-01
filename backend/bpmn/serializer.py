"""Serialize BpmnModel to BPMN 2.0 XML with diagram interchange so bpmn-js can display it."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from bpmn.model import EXTENSION_KEYS

if TYPE_CHECKING:
    from bpmn.model import BpmnModel

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CONSULARIS_NS = "http://consularis.example/bpmn"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"

# Generous spacing to prevent titles, arrows, and boxes from overlapping
# Lane names stay in the left strip; nodes start after it
LANE_LABEL_WIDTH = 280
TASK_WIDTH = 220
TASK_HEIGHT = 112
EVENT_SIZE = 44
GATEWAY_SIZE = 56
LANE_HEIGHT = 200
GAP_Y = 24  # vertical gap between lanes so arrows don't sit on borders
GAP_X = 140


def _elem(tag: str, ns: str = BPMN_NS, text: str | None = None, **attrs: str) -> ET.Element:
    el = ET.Element(f"{{{ns}}}{tag}", **{k: v for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = text
    return el


def _sub(parent: ET.Element, tag: str, ns: str = BPMN_NS, text: str | None = None, **attrs: str) -> ET.Element:
    child = _elem(tag, ns, text, **attrs)
    parent.append(child)
    return child


def _extension_elements(task: dict) -> ET.Element | None:
    ext = task.get("extension") or {}
    if not any(ext.get(k) for k in EXTENSION_KEYS):
        return None
    ext_el = _elem("extensionElements", BPMN_NS)
    map_key_to_xml = {
        "actor": "actor",
        "duration_min": "durationMin",
        "description": "description",
        "inputs": "inputs",
        "outputs": "outputs",
        "risks": "risks",
        "automation_potential": "automationPotential",
        "automation_notes": "automationNotes",
    }
    for key in EXTENSION_KEYS:
        val = ext.get(key)
        if val is None:
            continue
        if key in ("inputs", "outputs", "risks"):
            if isinstance(val, list):
                val = json.dumps(val) if val else ""
            else:
                val = str(val)
        else:
            val = str(val) if val else ""
        if val:
            sub = ET.SubElement(ext_el, f"{{{CONSULARIS_NS}}}{map_key_to_xml[key]}")
            sub.text = val
    return ext_el if len(ext_el) > 0 else None


XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def _node_size(model: "BpmnModel", node_id: str) -> tuple[int, int]:
    """Return (width, height) for a flow node."""
    kind = model.flow_node_type(node_id)
    if kind == "task":
        return (TASK_WIDTH, TASK_HEIGHT)
    if kind in ("startEvent", "endEvent"):
        return (EVENT_SIZE, EVENT_SIZE)
    if kind == "exclusiveGateway":
        return (GATEWAY_SIZE, GATEWAY_SIZE)
    return (TASK_WIDTH, TASK_HEIGHT)


def _layout_bounds(model: "BpmnModel") -> dict[str, tuple[int, int, int, int]]:
    """Return node_id -> (x, y, width, height). Lane names in 0..LANE_LABEL_WIDTH; nodes start after; GAP_Y between lanes."""
    bounds: dict[str, tuple[int, int, int, int]] = {}
    y_offset = 0
    for lane in model.lanes:
        refs = lane.get("flow_node_refs", [])
        x = LANE_LABEL_WIDTH
        for node_id in refs:
            w, h = _node_size(model, node_id)
            dy = (LANE_HEIGHT - h) // 2
            bounds[node_id] = (x, y_offset + max(0, dy), w, h)
            x += w + GAP_X
        y_offset += LANE_HEIGHT + GAP_Y
    return bounds


def _segment_rect_intersections(
    ax: float, ay: float, bx: float, by: float,
    rx: float, ry: float, rw: float, rh: float,
) -> list[tuple[float, float]]:
    """Intersection points of segment (ax,ay)-(bx,by) with the boundary of rect (rx,ry,rw,rh). Returns 0, 1, or 2 points."""
    out: list[tuple[float, float]] = []
    dx = bx - ax
    dy = by - ay

    def on_segment(px: float, py: float, t: float) -> bool:
        return 0 <= t <= 1

    # left edge x = rx
    if abs(dx) > 1e-9:
        t = (rx - ax) / dx
        py = ay + t * dy
        if on_segment(ax + t * dx, py, t) and ry <= py <= ry + rh:
            out.append((rx, py))
    # right edge x = rx + rw
    if abs(dx) > 1e-9:
        t = (rx + rw - ax) / dx
        py = ay + t * dy
        if on_segment(rx + rw, py, t) and ry <= py <= ry + rh:
            out.append((rx + rw, py))
    # top edge y = ry
    if abs(dy) > 1e-9:
        t = (ry - ay) / dy
        px = ax + t * dx
        if on_segment(px, ry, t) and rx <= px <= rx + rw:
            out.append((px, ry))
    # bottom edge y = ry + rh
    if abs(dy) > 1e-9:
        t = (ry + rh - ay) / dy
        px = ax + t * dx
        if on_segment(px, ry + rh, t) and rx <= px <= rx + rw:
            out.append((px, ry + rh))

    # deduplicate (e.g. corner hits can be reported twice)
    seen: set[tuple[float, float]] = set()
    unique: list[tuple[float, float]] = []
    for p in out:
        key = (round(p[0], 4), round(p[1], 4))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _border_waypoints(
    x1: float, y1: float, x2: float, y2: float,
    sx: float, sy: float, sw: float, sh: float,
    tx: float, ty: float, tw: float, th: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """First waypoint = exit from source rect; last waypoint = entry to target rect. Fallback to center if no hit."""
    src_pts = _segment_rect_intersections(x1, y1, x2, y2, sx, sy, sw, sh)
    tgt_pts = _segment_rect_intersections(x1, y1, x2, y2, tx, ty, tw, th)
    start = (x1, y1)
    end = (x2, y2)
    if src_pts:
        start = min(src_pts, key=lambda p: (p[0] - x2) ** 2 + (p[1] - y2) ** 2)
    if tgt_pts:
        end = min(tgt_pts, key=lambda p: (p[0] - x1) ** 2 + (p[1] - y1) ** 2)
    return (start, end)


def _add_diagram_interchange(
    definitions: ET.Element, model: "BpmnModel", node_bounds: dict[str, tuple[int, int, int, int]]
) -> None:
    """Append bpmndi:BPMNDiagram with BPMNPlane, BPMNShape per lane, per flow node, BPMNEdge per flow."""
    definitions.set("xmlns:bpmndi", BPMNDI_NS)
    definitions.set("xmlns:dc", DC_NS)
    definitions.set("xmlns:di", DI_NS)

    diagram = ET.SubElement(definitions, f"{{{BPMNDI_NS}}}BPMNDiagram", id="BPMNDiagram_1")
    plane = ET.SubElement(diagram, f"{{{BPMNDI_NS}}}BPMNPlane", id="BPMNPlane_1", bpmnElement=model.process_id)

    max_x = max((x + w for x, y, w, h in node_bounds.values()), default=LANE_LABEL_WIDTH)
    diagram_width = max_x + 120

    # Lane shapes first (swimlanes); each lane has GAP_Y below it before the next
    y_offset = 0
    for lane in model.lanes:
        lane_id = lane["id"]
        shape = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNShape", id=f"BPMNShape_{lane_id}", bpmnElement=lane_id)
        ET.SubElement(
            shape, f"{{{DC_NS}}}Bounds", x="0", y=str(y_offset), width=str(diagram_width), height=str(LANE_HEIGHT)
        )
        y_offset += LANE_HEIGHT + GAP_Y

    # Flow node shapes (tasks, start/end events, gateways)
    for node_id, (x, y, w, h) in node_bounds.items():
        shape = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNShape", id=f"BPMNShape_{node_id}", bpmnElement=node_id)
        ET.SubElement(shape, f"{{{DC_NS}}}Bounds", x=str(x), y=str(y), width=str(w), height=str(h))

    # Edges: waypoints at shape borders (line–rect intersection) so arrows start/end on the outline
    for flow in model.sequence_flows:
        fid = flow["id"]
        src = flow["source_ref"]
        tgt = flow["target_ref"]
        sb = node_bounds.get(src, (0, 0, TASK_WIDTH, TASK_HEIGHT))
        tb = node_bounds.get(tgt, (0, 0, TASK_WIDTH, TASK_HEIGHT))
        sx, sy, sw, sh = sb
        tx, ty, tw, th = tb
        x1 = sx + sw / 2
        y1 = sy + sh / 2
        x2 = tx + tw / 2
        y2 = ty + th / 2
        (wx1, wy1), (wx2, wy2) = _border_waypoints(x1, y1, x2, y2, float(sx), float(sy), float(sw), float(sh), float(tx), float(ty), float(tw), float(th))
        edge = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNEdge", id=f"BPMNEdge_{fid}", bpmnElement=fid)
        ET.SubElement(edge, f"{{{DI_NS}}}waypoint", x=str(round(wx1)), y=str(round(wy1)))
        ET.SubElement(edge, f"{{{DI_NS}}}waypoint", x=str(round(wx2)), y=str(round(wy2)))


def serialize_bpmn_xml(model: "BpmnModel") -> str:
    """Serialize BpmnModel to BPMN 2.0 XML string including diagram interchange for bpmn-js."""
    definitions = _elem("definitions")
    definitions.set("xmlns:bpmn", BPMN_NS)
    definitions.set("xmlns:consularis", CONSULARIS_NS)
    definitions.set("xmlns:xsi", XSI_NS)
    definitions.set("id", "Definitions_1")
    definitions.set("targetNamespace", "http://bpmn.io/schema/bpmn")

    process = _sub(
        definitions,
        "process",
        id=model.process_id,
        name=model.process_name,
        isExecutable="false",
    )

    # LaneSet first
    if model.lanes:
        lane_set = _sub(process, "laneSet", id="LaneSet_1")
        for lane in model.lanes:
            lane_el = _sub(lane_set, "lane", id=lane["id"], name=lane.get("name", ""))
            for ref in lane.get("flow_node_refs", []):
                _sub(lane_el, "flowNodeRef", text=ref)

    # Start events
    for ev in model.start_events:
        _sub(process, "startEvent", id=ev["id"], name=ev.get("name", "Start"))

    # End events
    for ev in model.end_events:
        _sub(process, "endEvent", id=ev["id"], name=ev.get("name", "End"))

    # Exclusive gateways
    for gw in model.gateways:
        _sub(process, "exclusiveGateway", id=gw["id"], name=gw.get("name", ""))

    # Tasks
    for task in model.tasks:
        task_el = _sub(process, "task", id=task["id"], name=task.get("name", ""))
        ext_el = _extension_elements(task)
        if ext_el is not None:
            task_el.append(ext_el)

    # Sequence flows
    for flow in model.sequence_flows:
        flow_el = _sub(
            process,
            "sequenceFlow",
            id=flow["id"],
            sourceRef=flow["source_ref"],
            targetRef=flow["target_ref"],
            name=flow.get("name", ""),
        )
        if flow.get("condition"):
            cond = _sub(flow_el, "conditionExpression", text=flow["condition"])
            cond.set(f"{{{XSI_NS}}}type", "bpmn:tFormalExpression")

    # Diagram interchange so bpmn-js can display the diagram
    node_bounds = _layout_bounds(model)
    _add_diagram_interchange(definitions, model, node_bounds)

    ET.indent(definitions, space="  ")
    return ET.tostring(definitions, encoding="unicode", default_namespace="", method="xml")

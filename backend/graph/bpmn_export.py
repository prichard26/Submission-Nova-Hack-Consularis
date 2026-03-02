"""Export ProcessGraph to BPMN 2.0 XML for download compatibility."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from graph.model import ProcessGraph, STEP_METADATA_KEYS, LIST_METADATA_KEYS
from graph.layout import step_size

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CONSULARIS_NS = "http://consularis.example/bpmn"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

LANE_LABEL_WIDTH = 280
LANE_HEIGHT = 200
GAP_Y = 24

_KEY_TO_XML = {
    "actor": "actor",
    "duration_min": "durationMin",
    "description": "description",
    "inputs": "inputs",
    "outputs": "outputs",
    "risks": "risks",
    "automation_potential": "automationPotential",
    "automation_notes": "automationNotes",
    "current_state": "currentState",
    "frequency": "frequency",
    "annual_volume": "annualVolume",
    "error_rate_percent": "errorRatePercent",
    "cost_per_execution": "costPerExecution",
    "current_systems": "currentSystems",
    "data_format": "dataFormat",
    "external_dependencies": "externalDependencies",
    "regulatory_constraints": "regulatoryConstraints",
    "sla_target": "slaTarget",
    "pain_points": "painPoints",
}


def _elem(tag: str, ns: str = BPMN_NS, text: str | None = None, **attrs: str) -> ET.Element:
    el = ET.Element(f"{{{ns}}}{tag}", **{k: v for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = text
    return el


def _sub(parent: ET.Element, tag: str, ns: str = BPMN_NS, text: str | None = None, **attrs: str) -> ET.Element:
    child = _elem(tag, ns, text, **attrs)
    parent.append(child)
    return child


def _extension_elements(step: dict) -> ET.Element | None:
    has_any = False
    ext_el = _elem("extensionElements", BPMN_NS)
    for key in STEP_METADATA_KEYS:
        val = step.get(key)
        if val is None:
            continue
        xml_tag = _KEY_TO_XML.get(key)
        if not xml_tag:
            continue
        if key in LIST_METADATA_KEYS:
            if isinstance(val, list) and val:
                text = json.dumps(val)
            else:
                continue
        else:
            text = str(val) if val else ""
        if text:
            sub = ET.SubElement(ext_el, f"{{{CONSULARIS_NS}}}{xml_tag}")
            sub.text = text
            has_any = True
    return ext_el if has_any else None


def _segment_rect_intersections(
    ax: float, ay: float, bx: float, by: float,
    rx: float, ry: float, rw: float, rh: float,
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    dx = bx - ax
    dy = by - ay
    if abs(dx) > 1e-9:
        t = (rx - ax) / dx
        py = ay + t * dy
        if 0 <= t <= 1 and ry <= py <= ry + rh:
            out.append((rx, py))
        t = (rx + rw - ax) / dx
        py = ay + t * dy
        if 0 <= t <= 1 and ry <= py <= ry + rh:
            out.append((rx + rw, py))
    if abs(dy) > 1e-9:
        t = (ry - ay) / dy
        px = ax + t * dx
        if 0 <= t <= 1 and rx <= px <= rx + rw:
            out.append((px, ry))
        t = (ry + rh - ay) / dy
        px = ax + t * dx
        if 0 <= t <= 1 and rx <= px <= rx + rw:
            out.append((px, ry + rh))
    seen: set[tuple[float, float]] = set()
    unique: list[tuple[float, float]] = []
    for p in out:
        key = (round(p[0], 4), round(p[1], 4))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _border_waypoints(x1, y1, x2, y2, sx, sy, sw, sh, tx, ty, tw, th):
    src_pts = _segment_rect_intersections(x1, y1, x2, y2, sx, sy, sw, sh)
    tgt_pts = _segment_rect_intersections(x1, y1, x2, y2, tx, ty, tw, th)
    start = (x1, y1)
    end_pt = (x2, y2)
    if src_pts:
        start = min(src_pts, key=lambda p: (p[0] - x2) ** 2 + (p[1] - y2) ** 2)
    if tgt_pts:
        end_pt = min(tgt_pts, key=lambda p: (p[0] - x1) ** 2 + (p[1] - y1) ** 2)
    return start, end_pt


def export_bpmn_xml(graph: ProcessGraph) -> str:
    """Convert a ProcessGraph to BPMN 2.0 XML string with diagram interchange."""
    definitions = _elem("definitions")
    definitions.set("xmlns:bpmn", BPMN_NS)
    definitions.set("xmlns:consularis", CONSULARIS_NS)
    definitions.set("id", "Definitions_1")
    definitions.set("targetNamespace", "http://bpmn.io/schema/bpmn")

    process = _sub(definitions, "process", id=graph.process_id, name=graph.name, isExecutable="false")

    # Lanes
    if graph.lanes:
        lane_set = _sub(process, "laneSet", id="LaneSet_1")
        for lane in graph.lanes:
            lane_el = _sub(lane_set, "lane", id=lane["id"], name=lane.get("name", ""))
            for ref in lane.get("node_refs", []):
                _sub(lane_el, "flowNodeRef", text=ref)

    # Steps -> BPMN elements
    node_bounds: dict[str, tuple[int, int, int, int]] = {}
    for step in graph.steps:
        sid = step["id"]
        stype = step.get("type", "step")
        pos = step.get("position", {"x": 0, "y": 0})
        w, h = step_size(step)
        node_bounds[sid] = (pos["x"], pos["y"], w, h)

        if stype == "start":
            _sub(process, "startEvent", id=sid, name=step.get("name", "Start"))
        elif stype == "end":
            _sub(process, "endEvent", id=sid, name=step.get("name", "End"))
        elif stype == "decision":
            _sub(process, "exclusiveGateway", id=sid, name=step.get("name", ""))
        elif stype == "subprocess":
            call_el = _sub(process, "callActivity", id=sid,
                           name=step.get("name", ""),
                           calledElement=step.get("called_element", ""))
            ext = _extension_elements(step)
            if ext is not None:
                call_el.append(ext)
        else:
            task_el = _sub(process, "task", id=sid, name=step.get("name", ""))
            ext = _extension_elements(step)
            if ext is not None:
                task_el.append(ext)

    # Flows
    for i, flow in enumerate(graph.flows):
        src = flow["from"]
        tgt = flow["to"]
        fid = f"flow_{src}_{tgt}"
        flow_el = _sub(process, "sequenceFlow", id=fid, sourceRef=src, targetRef=tgt,
                        name=flow.get("label", ""))
        if flow.get("condition"):
            cond = _sub(flow_el, "conditionExpression", text=flow["condition"])
            cond.set(f"{{{XSI_NS}}}type", "bpmn:tFormalExpression")

    # Diagram interchange
    definitions.set("xmlns:bpmndi", BPMNDI_NS)
    definitions.set("xmlns:dc", DC_NS)
    definitions.set("xmlns:di", DI_NS)
    diagram = ET.SubElement(definitions, f"{{{BPMNDI_NS}}}BPMNDiagram", id="BPMNDiagram_1")
    plane = ET.SubElement(diagram, f"{{{BPMNDI_NS}}}BPMNPlane", id="BPMNPlane_1",
                          bpmnElement=graph.process_id)

    max_x = max((x + w for x, y, w, h in node_bounds.values()), default=LANE_LABEL_WIDTH)
    diagram_width = max_x + 120
    y_offset = 0
    for lane in graph.lanes:
        shape = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNShape",
                              id=f"BPMNShape_{lane['id']}", bpmnElement=lane["id"])
        ET.SubElement(shape, f"{{{DC_NS}}}Bounds", x="0", y=str(y_offset),
                      width=str(diagram_width), height=str(LANE_HEIGHT))
        y_offset += LANE_HEIGHT + GAP_Y

    for nid, (x, y, w, h) in node_bounds.items():
        shape = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNShape",
                              id=f"BPMNShape_{nid}", bpmnElement=nid)
        ET.SubElement(shape, f"{{{DC_NS}}}Bounds", x=str(x), y=str(y), width=str(w), height=str(h))

    for flow in graph.flows:
        src = flow["from"]
        tgt = flow["to"]
        sb = node_bounds.get(src, (0, 0, 220, 112))
        tb = node_bounds.get(tgt, (0, 0, 220, 112))
        x1 = sb[0] + sb[2] / 2
        y1 = sb[1] + sb[3] / 2
        x2 = tb[0] + tb[2] / 2
        y2 = tb[1] + tb[3] / 2
        (wx1, wy1), (wx2, wy2) = _border_waypoints(
            x1, y1, x2, y2,
            float(sb[0]), float(sb[1]), float(sb[2]), float(sb[3]),
            float(tb[0]), float(tb[1]), float(tb[2]), float(tb[3]),
        )
        fid = f"flow_{src}_{tgt}"
        edge = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNEdge",
                             id=f"BPMNEdge_{fid}", bpmnElement=fid)
        ET.SubElement(edge, f"{{{DI_NS}}}waypoint", x=str(round(wx1)), y=str(round(wy1)))
        ET.SubElement(edge, f"{{{DI_NS}}}waypoint", x=str(round(wx2)), y=str(round(wy2)))

    ET.indent(definitions, space="  ")
    return ET.tostring(definitions, encoding="unicode", default_namespace="", method="xml")

"""Export ProcessGraph to BPMN 2.0 XML for download compatibility (model only; no diagram layout)."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from graph.model import ProcessGraph, STEP_METADATA_KEYS, LIST_METADATA_KEYS

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CONSULARIS_NS = "http://consularis.example/bpmn"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

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


def export_bpmn_xml(graph: ProcessGraph) -> str:
    """Convert a ProcessGraph to BPMN 2.0 XML string (model only; no diagram interchange)."""
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
    for step in graph.steps:
        sid = step["id"]
        stype = step.get("type", "step")
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
    for flow in graph.flows:
        src = flow["from"]
        tgt = flow["to"]
        fid = f"flow_{src}_{tgt}"
        flow_el = _sub(process, "sequenceFlow", id=fid, sourceRef=src, targetRef=tgt,
                      name=flow.get("label", ""))
        if flow.get("condition"):
            cond = _sub(flow_el, "conditionExpression", text=flow["condition"])
            cond.set(f"{{{XSI_NS}}}type", "bpmn:tFormalExpression")

    ET.indent(definitions, space="  ")
    return ET.tostring(definitions, encoding="unicode", default_namespace="", method="xml")

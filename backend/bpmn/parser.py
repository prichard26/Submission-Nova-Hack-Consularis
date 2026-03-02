"""Parse BPMN 2.0 XML into BpmnModel."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from bpmn.model import (
    BpmnModel,
    LIST_EXTENSION_KEYS,
    default_call_activity,
    default_extension,
    default_end_event,
    default_gateway,
    default_lane,
    default_sequence_flow,
    default_start_event,
    default_task,
    EXTENSION_KEYS,
)

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CONSULARIS_NS = "http://consularis.example/bpmn"


def _tag(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def _find(elem: ET.Element, ns: str, local: str) -> ET.Element | None:
    return elem.find(_tag(ns, local))


def _findall(elem: ET.Element, ns: str, local: str) -> list[ET.Element]:
    return elem.findall(_tag(ns, local))


def _get(elem: ET.Element, key: str, default: str = "") -> str:
    return elem.get(key, default) or default


def _parse_extension(ext_el: ET.Element | None) -> dict:
    out = {k: None for k in EXTENSION_KEYS}
    if ext_el is None:
        return out
    map_xml_to_key = {
        "actor": "actor",
        "durationMin": "duration_min",
        "description": "description",
        "inputs": "inputs",
        "outputs": "outputs",
        "risks": "risks",
        "automationPotential": "automation_potential",
        "automationNotes": "automation_notes",
        "currentState": "current_state",
        "frequency": "frequency",
        "annualVolume": "annual_volume",
        "errorRatePercent": "error_rate_percent",
        "costPerExecution": "cost_per_execution",
        "currentSystems": "current_systems",
        "dataFormat": "data_format",
        "externalDependencies": "external_dependencies",
        "regulatoryConstraints": "regulatory_constraints",
        "slaTarget": "sla_target",
        "painPoints": "pain_points",
    }
    for child in ext_el:
        if child.tag.startswith("{" + CONSULARIS_NS + "}"):
            local = child.tag.split("}")[-1]
            key = map_xml_to_key.get(local)
            if key:
                text = (child.text or "").strip()
                if key in LIST_EXTENSION_KEYS and text:
                    try:
                        out[key] = json.loads(text)
                    except json.JSONDecodeError:
                        out[key] = [text] if text else []
                else:
                    out[key] = text if text else None
    # Merge with defaults so we always have lists/str
    default = default_extension()
    for k in EXTENSION_KEYS:
        if out.get(k) is not None:
            default[k] = out[k]
    return default


def parse_bpmn_xml(xml_content: str | Path) -> BpmnModel:
    """Parse BPMN XML string or file path into BpmnModel."""
    if isinstance(xml_content, Path):
        xml_content = xml_content.read_text(encoding="utf-8")
    root = ET.fromstring(xml_content)
    # Find process (may be under definitions)
    process = root
    if process.tag != _tag(BPMN_NS, "process"):
        process = root.find(_tag(BPMN_NS, "process"))
    if process is None:
        raise ValueError("No bpmn:process found in XML")
    process_id = _get(process, "id", "Process_1")
    process_name = _get(process, "name", "Process")
    lanes: list[dict] = []
    lane_refs: dict[str, list[str]] = {}  # lane_id -> [node_id] in order
    node_to_lane: dict[str, str] = {}
    tasks: list[dict] = []
    call_activities: list[dict] = []
    start_events: list[dict] = []
    end_events: list[dict] = []
    gateways: list[dict] = []
    sequence_flows: list[dict] = []
    # Lanes
    lane_set = _find(process, BPMN_NS, "laneSet")
    if lane_set is not None:
        for lane in _findall(lane_set, BPMN_NS, "lane"):
            lane_id = _get(lane, "id")
            lane_name = _get(lane, "name")
            refs: list[str] = []
            for ref in _findall(lane, BPMN_NS, "flowNodeRef"):
                if ref.text:
                    r = ref.text.strip()
                    refs.append(r)
                    node_to_lane[r] = lane_id
            lane_refs[lane_id] = refs
            lanes.append(default_lane(lane_id, lane_name))
    # Flow nodes and sequence flows (direct children of process)
    for elem in process:
        tag = elem.tag
        if tag == _tag(BPMN_NS, "task"):
            task_id = _get(elem, "id")
            task_name = _get(elem, "name")
            lane_id = node_to_lane.get(task_id, "")
            ext = _parse_extension(_find(elem, BPMN_NS, "extensionElements"))
            tasks.append(default_task(task_id, task_name, lane_id))
            tasks[-1]["extension"] = ext
        elif tag == _tag(BPMN_NS, "callActivity"):
            call_id = _get(elem, "id")
            call_name = _get(elem, "name")
            called_element = _get(elem, "calledElement")
            lane_id = node_to_lane.get(call_id, "")
            ext = _parse_extension(_find(elem, BPMN_NS, "extensionElements"))
            call_activities.append(default_call_activity(call_id, call_name, called_element, lane_id))
            call_activities[-1]["extension"] = ext
        elif tag == _tag(BPMN_NS, "startEvent"):
            ev_id = _get(elem, "id")
            ev_name = _get(elem, "name", "Start")
            lane_id = node_to_lane.get(ev_id, "")
            start_events.append(default_start_event(ev_id, ev_name, lane_id))
        elif tag == _tag(BPMN_NS, "endEvent"):
            ev_id = _get(elem, "id")
            ev_name = _get(elem, "name", "End")
            lane_id = node_to_lane.get(ev_id, "")
            end_events.append(default_end_event(ev_id, ev_name, lane_id))
        elif tag == _tag(BPMN_NS, "exclusiveGateway"):
            gw_id = _get(elem, "id")
            gw_name = _get(elem, "name", "")
            lane_id = node_to_lane.get(gw_id, "")
            gateways.append(default_gateway(gw_id, gw_name, lane_id))
        elif tag == _tag(BPMN_NS, "sequenceFlow"):
            flow_id = _get(elem, "id", f"flow_{_get(elem, 'sourceRef')}_{_get(elem, 'targetRef')}")
            src = _get(elem, "sourceRef")
            tgt = _get(elem, "targetRef")
            name = _get(elem, "name", f"{src} → {tgt}")
            cond_el = _find(elem, BPMN_NS, "conditionExpression")
            condition = (cond_el.text or "").strip() if cond_el is not None else None
            sequence_flows.append(default_sequence_flow(flow_id, src, tgt, name, condition))
    # Preserve lane order and flow_node_refs from XML
    for lane in lanes:
        lane["flow_node_refs"] = lane_refs.get(lane["id"], [])
    return BpmnModel(
        process_id=process_id,
        process_name=process_name,
        lanes=lanes,
        tasks=tasks,
        call_activities=call_activities,
        start_events=start_events,
        end_events=end_events,
        gateways=gateways,
        sequence_flows=sequence_flows,
    )

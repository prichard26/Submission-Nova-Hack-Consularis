"""Split flat pharmacy baseline BPMN into hierarchical global+phase BPMNs.

Usage:
  cd backend && python scripts/split_baseline.py
"""
from __future__ import annotations

import json
from pathlib import Path

from bpmn.model import (
    BpmnModel,
    default_call_activity,
    default_end_event,
    default_lane,
    default_sequence_flow,
    default_start_event,
)
from bpmn.parser import parse_bpmn_xml
from bpmn.serializer import serialize_bpmn_xml


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "pharmacy_circuit.bpmn"
OUT_DIR = ROOT / "data" / "graphs"
REGISTRY = OUT_DIR / "registry.json"


def _phase_file_name(phase_id: str) -> str:
    return f"{phase_id}.bpmn"


def _collect_lane_nodes(model: BpmnModel, lane_id: str) -> set[str]:
    lane = model.get_lane(lane_id)
    if not lane:
        return set()
    return set(lane.get("flow_node_refs", []))


def _build_global_model(source: BpmnModel) -> BpmnModel:
    process_id = "Process_Global"
    process_name = source.process_name or "Company process map"
    lane_id = "GLOBAL"
    lane = default_lane(lane_id, "Global map")
    out = BpmnModel(
        process_id=process_id,
        process_name=process_name,
        lanes=[lane],
        tasks=[],
        call_activities=[],
        start_events=[default_start_event("Start_Global", "Start", lane_id)],
        end_events=[default_end_event("End_Global", "End", lane_id)],
        gateways=[],
        sequence_flows=[],
    )

    node_order = ["Start_Global"]
    lane_order = []
    for lane_src in source.lanes:
        phase_id = lane_src["id"]
        call_id = f"Call_{phase_id}"
        call = default_call_activity(
            call_id=call_id,
            name=lane_src.get("name", phase_id),
            called_element=f"Process_{phase_id}",
            lane_id=lane_id,
        )
        out.call_activities.append(call)
        node_order.append(call_id)
        lane_order.append(phase_id)
    node_order.append("End_Global")
    out.lanes[0]["flow_node_refs"] = node_order

    for i in range(len(node_order) - 1):
        src = node_order[i]
        tgt = node_order[i + 1]
        name = "Start" if i == 0 else ("Complete" if i == len(node_order) - 2 else "")
        flow_id = f"flow_{src}_{tgt}"
        out.sequence_flows.append(default_sequence_flow(flow_id, src, tgt, name))
    return out


def _build_phase_model(source: BpmnModel, lane: dict) -> BpmnModel:
    phase_id = lane["id"]
    process_id = f"Process_{phase_id}"
    process_name = lane.get("name", phase_id)
    local_lane_id = phase_id

    refs = list(lane.get("flow_node_refs", []))
    node_set = set(refs)
    first = refs[0] if refs else None
    last = refs[-1] if refs else None
    start_id = f"Start_{phase_id}"
    end_id = f"End_{phase_id}"

    out = BpmnModel(
        process_id=process_id,
        process_name=process_name,
        lanes=[default_lane(local_lane_id, process_name)],
        tasks=[],
        call_activities=[],
        start_events=[default_start_event(start_id, "Start", local_lane_id)],
        end_events=[default_end_event(end_id, "End", local_lane_id)],
        gateways=[],
        sequence_flows=[],
    )

    # Copy tasks/gateways from this lane only.
    for ref in refs:
        t = source.get_task(ref)
        if t:
            copied = {
                "id": t["id"],
                "name": t.get("name", ""),
                "lane_id": local_lane_id,
                "extension": t.get("extension", {}).copy(),
            }
            out.tasks.append(copied)
            continue
        gw = next((g for g in source.gateways if g["id"] == ref), None)
        if gw:
            out.gateways.append({"id": gw["id"], "name": gw.get("name", ""), "lane_id": local_lane_id})

    out.lanes[0]["flow_node_refs"] = [start_id, *refs, end_id]

    if first:
        out.sequence_flows.append(default_sequence_flow(f"flow_{start_id}_{first}", start_id, first, "Start"))
    if last:
        out.sequence_flows.append(default_sequence_flow(f"flow_{last}_{end_id}", last, end_id, "Complete"))

    # Keep intra-lane edges only.
    for f in source.sequence_flows:
        src = f["source_ref"]
        tgt = f["target_ref"]
        if src in node_set and tgt in node_set:
            out.sequence_flows.append(
                default_sequence_flow(
                    f.get("id", f"flow_{src}_{tgt}"),
                    src,
                    tgt,
                    f.get("name", ""),
                    f.get("condition"),
                )
            )
    return out


def main() -> None:
    source = parse_bpmn_xml(INPUT)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    global_model = _build_global_model(source)
    (OUT_DIR / "global.bpmn").write_text(serialize_bpmn_xml(global_model), encoding="utf-8")

    registry_items: list[dict] = [
        {
            "process_id": "Process_Global",
            "name": global_model.process_name,
            "parent_id": None,
            "bpmn_file": "global.bpmn",
        }
    ]

    for lane in source.lanes:
        phase_id = lane["id"]
        model = _build_phase_model(source, lane)
        file_name = _phase_file_name(phase_id)
        (OUT_DIR / file_name).write_text(serialize_bpmn_xml(model), encoding="utf-8")
        registry_items.append(
            {
                "process_id": model.process_id,
                "name": model.process_name,
                "parent_id": "Process_Global",
                "bpmn_file": file_name,
            }
        )

    REGISTRY.write_text(json.dumps({"processes": registry_items}, indent=2), encoding="utf-8")
    print(f"Wrote {len(registry_items)} processes to {OUT_DIR}")


if __name__ == "__main__":
    main()

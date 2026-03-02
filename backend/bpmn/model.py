"""In-memory BPMN model: process, lanes, tasks, sequence flows."""
from __future__ import annotations

from typing import Any

# Extension keys we support on tasks (snake_case for API, stored in model)
EXTENSION_KEYS = (
    "actor",
    "duration_min",
    "description",
    "inputs",
    "outputs",
    "risks",
    "automation_potential",
    "automation_notes",
    "current_state",
    "frequency",
    "annual_volume",
    "error_rate_percent",
    "cost_per_execution",
    "current_systems",
    "data_format",
    "external_dependencies",
    "regulatory_constraints",
    "sla_target",
    "pain_points",
)

LIST_EXTENSION_KEYS = frozenset({
    "inputs", "outputs", "risks",
    "current_systems", "external_dependencies",
    "regulatory_constraints", "pain_points",
})


def default_extension() -> dict[str, Any]:
    return {
        "actor": "",
        "duration_min": "—",
        "description": "",
        "inputs": [],
        "outputs": [],
        "risks": [],
        "automation_potential": "",
        "automation_notes": "",
        "current_state": "",
        "frequency": "",
        "annual_volume": "",
        "error_rate_percent": "",
        "cost_per_execution": "",
        "current_systems": [],
        "data_format": "",
        "external_dependencies": [],
        "regulatory_constraints": [],
        "sla_target": "",
        "pain_points": [],
    }


def default_task(task_id: str, name: str, lane_id: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "name": name,
        "lane_id": lane_id,
        "extension": default_extension(),
    }


def default_call_activity(call_id: str, name: str, called_element: str, lane_id: str) -> dict[str, Any]:
    return {
        "id": call_id,
        "name": name,
        "called_element": called_element,
        "lane_id": lane_id,
        "extension": default_extension(),
    }


def default_lane(lane_id: str, name: str, description: str = "") -> dict[str, Any]:
    return {
        "id": lane_id,
        "name": name,
        "description": description,
        "flow_node_refs": [],
    }


def default_sequence_flow(
    flow_id: str, source_ref: str, target_ref: str, name: str, condition: str | None = None
) -> dict[str, Any]:
    flow: dict[str, Any] = {
        "id": flow_id,
        "source_ref": source_ref,
        "target_ref": target_ref,
        "name": name,
    }
    if condition:
        flow["condition"] = condition
    return flow


def default_start_event(event_id: str, name: str = "Start", lane_id: str = "") -> dict:
    return {"id": event_id, "name": name, "lane_id": lane_id}


def default_end_event(event_id: str, name: str = "End", lane_id: str = "") -> dict:
    return {"id": event_id, "name": name, "lane_id": lane_id}


def default_gateway(gateway_id: str, name: str = "", lane_id: str = "") -> dict:
    return {"id": gateway_id, "name": name, "lane_id": lane_id}


class BpmnModel:
    """Mutable in-memory BPMN model. process_id/name, lanes, tasks, start/end events, gateways, sequence_flows."""

    def __init__(
        self,
        process_id: str = "Process_1",
        process_name: str = "Process",
        lanes: list[dict] | None = None,
        tasks: list[dict] | None = None,
        call_activities: list[dict] | None = None,
        start_events: list[dict] | None = None,
        end_events: list[dict] | None = None,
        gateways: list[dict] | None = None,
        sequence_flows: list[dict] | None = None,
    ):
        self.process_id = process_id
        self.process_name = process_name
        self.lanes = list(lanes) if lanes else []
        self.tasks = list(tasks) if tasks else []
        self.call_activities = list(call_activities) if call_activities else []
        self.start_events = list(start_events) if start_events else []
        self.end_events = list(end_events) if end_events else []
        self.gateways = list(gateways) if gateways else []
        self.sequence_flows = list(sequence_flows) if sequence_flows else []

    def copy(self) -> BpmnModel:
        import copy as copy_mod
        return BpmnModel(
            process_id=self.process_id,
            process_name=self.process_name,
            lanes=copy_mod.deepcopy(self.lanes),
            tasks=copy_mod.deepcopy(self.tasks),
            call_activities=copy_mod.deepcopy(self.call_activities),
            start_events=copy_mod.deepcopy(self.start_events),
            end_events=copy_mod.deepcopy(self.end_events),
            gateways=copy_mod.deepcopy(self.gateways),
            sequence_flows=copy_mod.deepcopy(self.sequence_flows),
        )

    def get_task(self, task_id: str) -> dict | None:
        for t in self.tasks:
            if t["id"] == task_id:
                return t
        return None

    def get_call_activity(self, node_id: str) -> dict | None:
        for c in self.call_activities:
            if c["id"] == node_id:
                return c
        return None

    def get_lane(self, lane_id: str) -> dict | None:
        for ln in self.lanes:
            if ln["id"] == lane_id:
                return ln
        return None

    def get_flow(self, source_ref: str, target_ref: str) -> dict | None:
        for f in self.sequence_flows:
            if f["source_ref"] == source_ref and f["target_ref"] == target_ref:
                return f
        return None

    def task_ids(self) -> set[str]:
        return {t["id"] for t in self.tasks}

    def call_activity_ids(self) -> set[str]:
        return {c["id"] for c in self.call_activities}

    def all_flow_node_ids(self) -> set[str]:
        """All flow node ids (tasks, start/end events, gateways) for validation and layout."""
        out = set(self.task_ids())
        out.update(self.call_activity_ids())
        for e in self.start_events:
            out.add(e["id"])
        for e in self.end_events:
            out.add(e["id"])
        for g in self.gateways:
            out.add(g["id"])
        return out

    def flow_node_type(self, node_id: str) -> str:
        """Return 'task'|'callActivity'|'startEvent'|'endEvent'|'exclusiveGateway' for layout."""
        if any(t["id"] == node_id for t in self.tasks):
            return "task"
        if any(c["id"] == node_id for c in self.call_activities):
            return "callActivity"
        if any(e["id"] == node_id for e in self.start_events):
            return "startEvent"
        if any(e["id"] == node_id for e in self.end_events):
            return "endEvent"
        if any(g["id"] == node_id for g in self.gateways):
            return "exclusiveGateway"
        return "task"

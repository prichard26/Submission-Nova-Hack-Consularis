"""JSON-native process graph model.

ProcessGraph wraps a raw dict that IS the JSON document.
No parsing or serializing -- mutations are direct dict operations.
"""
from __future__ import annotations

import copy
import json

STEP_METADATA_KEYS = frozenset({
    "actor", "duration_min", "description", "inputs", "outputs", "risks",
    "automation_potential", "automation_notes", "current_state", "frequency",
    "annual_volume", "error_rate_percent", "cost_per_execution",
    "current_systems", "data_format", "external_dependencies",
    "regulatory_constraints", "sla_target", "pain_points",
})

LIST_METADATA_KEYS = frozenset({
    "inputs", "outputs", "risks", "current_systems",
    "external_dependencies", "regulatory_constraints", "pain_points",
})

STEP_TYPES = frozenset({"start", "end", "step", "decision", "subprocess"})


def default_step_metadata() -> dict:
    return {
        "actor": "",
        "duration_min": "",
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


class ProcessGraph:
    """JSON-native process graph.  ``self.data`` IS the JSON document."""

    def __init__(self, data: dict):
        self.data = data

    # -- properties --------------------------------------------------------

    @property
    def process_id(self) -> str:
        """Optional: set by API when serving graph; not stored in JSON."""
        return self.data.get("process_id", "")

    @property
    def name(self) -> str:
        return self.data.get("name", "")

    @name.setter
    def name(self, value: str) -> None:
        self.data["name"] = value

    @property
    def metadata(self) -> dict:
        return self.data.get("metadata", {})

    @property
    def steps(self) -> list[dict]:
        return self.data.setdefault("steps", [])

    @property
    def flows(self) -> list[dict]:
        return self.data.setdefault("flows", [])

    @property
    def step_order(self) -> list[str]:
        order = self.data.get("step_order")
        if order is not None:
            return order
        # Legacy: derive from lanes when present
        lanes = self.data.get("lanes") or []
        if lanes:
            result = []
            for lane in lanes:
                refs = lane.get("node_refs") or []
                result.extend(refs)
            return result
        return []

    @step_order.setter
    def step_order(self, value: list[str]) -> None:
        self.data["step_order"] = list(value) if value is not None else []

    @property
    def lanes(self) -> list[dict]:
        """Legacy: only present when graph has lanes in data. New format uses step_order only."""
        return self.data.get("lanes") or []

    def get_lane(self, lane_id: str) -> dict | None:
        """Legacy: return lane by id. New format has no lanes."""
        return next((ln for ln in self.lanes if ln.get("id") == lane_id), None)

    # -- lookups -----------------------------------------------------------

    def get_step(self, step_id: str) -> dict | None:
        return next((s for s in self.steps if s.get("id") == step_id), None)

    def get_flow(self, from_id: str, to_id: str) -> dict | None:
        return next(
            (f for f in self.flows if f.get("from") == from_id and f.get("to") == to_id),
            None,
        )

    def all_step_ids(self) -> set[str]:
        return {s["id"] for s in self.steps if "id" in s}

    def steps_in_order(self) -> list[dict]:
        """Return steps in step_order order; skip ids not found in steps."""
        step_by_id = {s.get("id"): s for s in self.steps if s.get("id")}
        return [step_by_id[sid] for sid in self.step_order if sid in step_by_id]

    def step_type(self, step_id: str) -> str | None:
        step = self.get_step(step_id)
        return step.get("type") if step else None

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return self.data

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> ProcessGraph:
        return cls(json.loads(json_str))

    @classmethod
    def from_dict(cls, d: dict) -> ProcessGraph:
        return cls(d)

    def copy(self) -> ProcessGraph:
        return ProcessGraph(copy.deepcopy(self.data))

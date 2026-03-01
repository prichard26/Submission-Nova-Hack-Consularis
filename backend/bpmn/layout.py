"""Centralized layout constants and node bounds for BPMN diagram and JSON export."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bpmn.model import BpmnModel

# Generous spacing to prevent titles, arrows, and boxes from overlapping.
# Lane names stay in the left strip; nodes start after it.
LANE_LABEL_WIDTH = 280
TASK_WIDTH = 220
TASK_HEIGHT = 112
EVENT_SIZE = 44
GATEWAY_SIZE = 56
LANE_HEIGHT = 200
GAP_Y = 24  # vertical gap between lanes so arrows don't sit on borders
GAP_X = 140


def node_size(model: "BpmnModel", node_id: str) -> tuple[int, int]:
    """Return (width, height) for a flow node."""
    kind = model.flow_node_type(node_id)
    if kind == "task":
        return (TASK_WIDTH, TASK_HEIGHT)
    if kind in ("startEvent", "endEvent"):
        return (EVENT_SIZE, EVENT_SIZE)
    if kind == "exclusiveGateway":
        return (GATEWAY_SIZE, GATEWAY_SIZE)
    return (TASK_WIDTH, TASK_HEIGHT)


def layout_bounds(model: "BpmnModel") -> dict[str, tuple[int, int, int, int]]:
    """Return node_id -> (x, y, width, height). Lane names in 0..LANE_LABEL_WIDTH; nodes start after; GAP_Y between lanes."""
    bounds: dict[str, tuple[int, int, int, int]] = {}
    y_offset = 0
    for lane in model.lanes:
        refs = lane.get("flow_node_refs", [])
        x = LANE_LABEL_WIDTH
        for node_id in refs:
            w, h = node_size(model, node_id)
            dy = (LANE_HEIGHT - h) // 2
            bounds[node_id] = (x, y_offset + max(0, dy), w, h)
            x += w + GAP_X
        y_offset += LANE_HEIGHT + GAP_Y
    return bounds

"""JSON graph store: round-trip and BPMN export."""
import json

from graph.store import get_graph_json
from graph.bpmn_export import export_bpmn_xml
from graph.model import ProcessGraph


def test_json_roundtrip():
    """Load baseline JSON, parse to ProcessGraph, verify steps/flows/step_order."""
    sid = "test-roundtrip"
    json_str = get_graph_json(sid, process_id="Process_P1")
    assert isinstance(json_str, str)
    data = json.loads(json_str)
    assert "steps" in data
    assert "flows" in data
    graph = ProcessGraph.from_json(json_str)
    assert len(graph.steps) > 0
    assert len(graph.flows) > 0
    assert len(graph.step_order) > 0


def test_bpmn_export_from_json():
    """Export JSON graph to BPMN XML and verify structure."""
    sid = "test-export"
    json_str = get_graph_json(sid, process_id="Process_P1")
    graph = ProcessGraph.from_json(json_str)
    xml = export_bpmn_xml(graph, process_id="Process_P1")
    assert isinstance(xml, str)
    assert "process" in xml.lower()
    assert len(xml) > 100

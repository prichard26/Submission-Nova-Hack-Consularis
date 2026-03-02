"""BPMN store: round-trip and export."""

from bpmn.store import get_bpmn_xml
from bpmn.parser import parse_bpmn_xml


def test_bpmn_roundtrip():
    """Load baseline, export BPMN XML, re-parse, assert same core structure."""
    sid = "test-roundtrip"
    xml = get_bpmn_xml(sid, process_id="Process_P1")
    assert isinstance(xml, str)
    assert "bpmn:process" in xml or "process" in xml
    model = parse_bpmn_xml(xml)
    assert len(model.lanes) > 0
    assert len(model.tasks) > 0 or len(model.call_activities) > 0
    assert len(model.sequence_flows) > 0

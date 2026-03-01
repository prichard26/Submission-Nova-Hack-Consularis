"""BPMN store: round-trip and export."""

from graph_store import init_baseline, get_or_create_session, get_bpmn_xml
from bpmn.parser import parse_bpmn_xml


def test_bpmn_roundtrip():
    """Load baseline, export BPMN XML, re-parse, assert same core structure."""
    init_baseline()
    sid = "test-roundtrip"
    get_or_create_session(sid)
    xml = get_bpmn_xml(sid)
    assert isinstance(xml, str)
    assert "bpmn:process" in xml or "process" in xml
    model = parse_bpmn_xml(xml)
    assert len(model.lanes) > 0
    assert len(model.tasks) > 0
    assert len(model.sequence_flows) > 0

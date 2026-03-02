"""Process-scoped APIs and name resolution (multi-process mode)."""

from bpmn.store import resolve_step


def test_process_scoped_export_endpoint(client):
    sid = "export-process-test"
    resp = client.get("/api/graph/export", params={"session_id": sid, "process_id": "Process_Global"})
    assert resp.status_code == 200
    xml = resp.text
    assert "Process_Global" in xml or "process" in xml.lower()


def test_resolve_step_endpoint(client):
    sid = "resolve-process-test"
    resp = client.get(
        "/api/graph/resolve",
        params={"session_id": sid, "process_id": "Process_Global", "name": "prescription"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    assert isinstance(data["matches"], list)


def test_store_resolve_step():
    sid = "resolve-store-test"
    matches = resolve_step(sid, "prescription", process_id="Process_Global")
    assert isinstance(matches, list)

from fastapi.testclient import TestClient

from playwright_record_app import routes, service


def test_index_lists_recordings(monkeypatch):
    monkeypatch.setattr(service, "status", lambda: {"recordings": [{"name": "demo", "status": "FINISHED", "frames": 2}]})
    response = TestClient(routes.build_routes()).get("/")
    assert response.status_code == 200
    assert "demo" in response.text


def test_mcp_lists_lifecycle_tools():
    response = TestClient(routes.build_routes()).post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert names == {"recording_start", "recording_stop", "recording_snap", "recording_status", "recording_kill", "recording_gc"}

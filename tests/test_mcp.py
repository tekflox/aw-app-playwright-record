import pytest

from playwright_record_app import service
from playwright_record_app.mcp.http_handler import handle


@pytest.mark.asyncio
async def test_initialize():
    result = await handle({"jsonrpc": "2.0", "id": 7, "method": "initialize"})
    assert result["result"]["serverInfo"]["name"] == "aw-playwright-record"
    assert result["result"]["serverInfo"]["version"] == "0.2.4"


@pytest.mark.asyncio
async def test_tools_list_and_status_call(monkeypatch):
    listed = await handle({"jsonrpc": "2.0", "id": 8, "method": "tools/list"})
    assert {tool["name"] for tool in listed["result"]["tools"]} >= {
        "recording_start", "recording_stop", "recording_status"
    }

    monkeypatch.setattr(service, "status", lambda: {"recordings": [{"name": "demo"}]})
    called = await handle({
        "jsonrpc": "2.0", "id": 9, "method": "tools/call",
        "params": {"name": "recording_status", "arguments": {}},
    })
    assert called["result"]["structuredContent"]["recordings"][0]["name"] == "demo"


@pytest.mark.asyncio
async def test_unknown_tool_returns_mcp_error():
    result = await handle({
        "jsonrpc": "2.0", "id": 10, "method": "tools/call",
        "params": {"name": "missing", "arguments": {}},
    })
    assert result["result"]["isError"] is True
    assert "unknown tool" in result["result"]["content"][0]["text"]

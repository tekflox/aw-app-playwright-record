import pytest

from playwright_record_app.mcp.http_handler import handle


@pytest.mark.asyncio
async def test_initialize():
    result = await handle({"jsonrpc": "2.0", "id": 7, "method": "initialize"})
    assert result["result"]["serverInfo"]["name"] == "aw-playwright-record"

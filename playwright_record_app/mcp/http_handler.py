from __future__ import annotations

import json
from fastapi.concurrency import run_in_threadpool

from .. import __version__, service

TOOLS = [
    {"name": "recording_start", "description": "Start observing the shared Playwright Chromium browser over CDP.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "fps": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10}, "force": {"type": "boolean", "default": False}, "pause_frame": {"type": "boolean", "default": True}}, "required": ["name"]}},
    {"name": "recording_stop", "description": "Stop and finalize a recording, producing trace, frames, GIF, MP4, logs, report, and AW presentation.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "publish": {"type": "boolean", "default": True}}}},
    {"name": "recording_snap", "description": "Capture a labeled screenshot in an active recording.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "label": {"type": "string"}}}},
    {"name": "recording_status", "description": "List active and completed recordings and their artifact status.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "recording_kill", "description": "Gracefully terminate a stuck recorder, escalating to SIGKILL if required.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "recording_gc", "description": "Delete completed recording bundles older than a duration such as 7d or 12h; active recordings are preserved.", "inputSchema": {"type": "object", "properties": {"older_than": {"type": "string", "default": "7d"}}}},
]


def _ok(req_id, value):
    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(value, indent=2)}], "structuredContent": value, "isError": False}}


def _err(req_id, exc):
    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True}}


async def handle(body: dict):
    req_id, method = body.get("id"), body.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "aw-playwright-record", "version": __version__}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "method not found"}}
    params = body.get("params") or {}
    name, args = params.get("name"), params.get("arguments") or {}
    funcs = {
        "recording_start": service.start,
        "recording_stop": service.stop,
        "recording_snap": service.snap,
        "recording_status": service.status,
        "recording_kill": service.kill,
        "recording_gc": service.gc,
    }
    if name not in funcs:
        return _err(req_id, f"unknown tool: {name}")
    try:
        return _ok(req_id, await run_in_threadpool(funcs[name], **args))
    except Exception as exc:
        return _err(req_id, exc)

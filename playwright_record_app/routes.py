from __future__ import annotations

import html
import mimetypes
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import service
from .mcp.http_handler import handle


def build_routes() -> FastAPI:
    app = FastAPI(title="Playwright Record")

    @app.get("/")
    async def index():
        rows = service.status()["recordings"]
        items = "".join(f'<li><a href="report/{html.escape(r["name"])}">{html.escape(r["name"])}</a> — {html.escape(r["status"])}, {r.get("frames", 0)} frames</li>' for r in reversed(rows))
        return HTMLResponse(f"<!doctype html><style>body{{font:14px system-ui;padding:20px;background:#0f1117;color:#e7eaf0}}a{{color:#6ea8ff}}</style><h1>Playwright recordings</h1><p>Recorder lifecycle is available through the app MCP tools.</p><ul>{items or '<li>No recordings yet.</li>'}</ul>")

    @app.get("/status")
    async def status():
        return service.status()

    @app.get("/report/{name}")
    async def report(name: str):
        path = service.safe_bundle(name) / "report.html"
        if not path.is_file():
            raise HTTPException(404, "recording report not found")
        return HTMLResponse(path.read_text(encoding="utf-8", errors="replace"))

    @app.get("/artifact/{name}/{artifact}")
    async def artifact(name: str, artifact: str):
        allowed = {"trace.zip", "session.gif", "session.mp4", "network.jsonl", "console.jsonl", "meta.json", "daemon.log"}
        if artifact not in allowed:
            raise HTTPException(404, "unknown artifact")
        path = service.safe_bundle(name) / artifact
        if not path.is_file():
            raise HTTPException(404, "artifact not found")
        return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0])

    @app.post("/mcp")
    async def mcp(body: dict):
        result = await handle(body)
        return JSONResponse(result or {}, status_code=200)

    return app

---
name: aw-playwright-record
description: Record a shared Playwright browser flow into trace, raw frames, GIF/MP4, network/console logs, and a self-contained AW report. Use for “record the browser”, “capture this flow”, “make a gif”, or browser-flow evidence.
---

# Playwright Recorder

Use the app's MCP tools; do not invoke package scripts directly.

The recorder attaches as an observer to the shared Chromium CDP endpoint. Drive that same browser with the plain shared `playwright` MCP. Do not use `playwright_local`/isolated mode: it launches a different browser and the recording would be empty.

Always pair start and stop like `try/finally`:

1. Call `recording_start` with a short path-safe `name` before browser actions.
2. Drive the flow using the shared Playwright MCP.
3. Optionally call `recording_snap` at important states.
4. Always call `recording_stop`, even if the browser flow failed.

`recording_stop` finalizes `trace.zip`, raw frames, `session.gif`, `session.mp4`, `network.jsonl`, `console.jsonl`, and `report.html`. By default it publishes the self-contained report to the Presentations app. Its result includes bundle and report paths and capture counts.

Lifecycle tools:

- `recording_start(name, fps=10, force=false, pause_frame=true)`
- `recording_stop(name?, publish=true)`
- `recording_snap(name?, label?)`
- `recording_status()`
- `recording_kill(name)` for a stuck daemon
- `recording_gc(older_than="7d")`; active recordings are never deleted

Report the recording name, duration, frames, request/console/error counts, bundle path, and presentation ID when available.

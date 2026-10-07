# Playwright Recorder

An aw-workspace app that observes the shared Chromium browser over CDP while Playwright drives it. Each session produces durable artifacts under `AW_WORKSPACE_HOME/data/playwright-record/recordings/<name>`:

- `trace.zip`
- raw JPEG frames and labeled snapshots
- `session.gif` and `session.mp4`
- `network.jsonl`
- `console.jsonl` including page errors
- a self-contained `report.html`

The app contributes a Recorder window in the Apps grid and proper MCP tools: `recording_start`, `recording_stop`, `recording_snap`, `recording_status`, `recording_kill`, and `recording_gc`. Completed reports are also published to the optional Presentations app.

## Architecture

This is a Tier-1 app. It does not launch another browser. It attaches as a second, observing CDP client to the browser app at `http://aw-app-browser:9223`; the regular shared Playwright MCP remains the driving client. The only capabilities are registered routes, outbound network access, app-owned data, and the idempotent ffmpeg installer.

## Development

```bash
python -m pytest -q
python tests/validate_manifest.py
python -m playwright_record_app
```

Releases use `.github/workflows/release.yml`, which validates/tests, tags the app, and syncs the `tekflox/aw-marketplace` catalog. Install the released catalog version with:

```bash
aw-workspace-cli marketplace install playwright-record --update
aw-workspace-cli restart mcp-gateway
aw-workspace-cli doctor
```

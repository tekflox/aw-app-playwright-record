import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from playwright_record_app.plugin import PlaywrightRecordAppPlugin


@pytest.mark.asyncio
async def test_activate_registers_routes_cli_and_mcp(monkeypatch, tmp_path):
    manifest = {"contributes": {"system_clis": [{"name": "ffmpeg", "installer": "scripts/install_ffmpeg.sh", "verify": "ffmpeg -version"}]}}
    (tmp_path / "aw-app.json").write_text(json.dumps(manifest))
    calls = []
    commands = SimpleNamespace(install_system_cli=lambda *a, **k: calls.append((a, k)))
    registered = []
    ctx = SimpleNamespace(package_dir=str(tmp_path), commands=commands, routes=SimpleNamespace(register=registered.append))
    monkeypatch.setattr("playwright_record_app.plugin.register_self", lambda package_dir, port: calls.append((package_dir, port)))
    await PlaywrightRecordAppPlugin().activate(ctx)
    assert registered
    assert calls[0][0][0] == "ffmpeg"

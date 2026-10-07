"""Unit tests for template_app/__main__.py's main() — the standalone-mode
entrypoint (`python -m template_app`). build_standalone_app()/SLUG/UI_DIST are
already covered by test_standalone.py; this file is just main() itself: the
"ui/dist not built yet" note, and the PORT/AW_APP_HOST env overrides.
uvicorn.run is mocked so this never actually binds a socket.

Run: .venv/aw/bin/python -m pytest tests/test_main.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import template_app.__main__ as main_mod  # noqa: E402


def test_main_starts_uvicorn_on_the_default_port_and_host():
    with patch.object(main_mod, "uvicorn") as mock_uvicorn:
        main_mod.main()

    mock_uvicorn.run.assert_called_once()
    _, kwargs = mock_uvicorn.run.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == main_mod.DEFAULT_PORT


def test_main_prints_a_note_and_honors_env_overrides_when_ui_dist_is_missing(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(main_mod, "UI_DIST", tmp_path / "not-built")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("AW_APP_HOST", "0.0.0.0")

    with patch.object(main_mod, "uvicorn") as mock_uvicorn:
        main_mod.main()

    assert "not built yet" in capsys.readouterr().out
    _, kwargs = mock_uvicorn.run.call_args
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9999

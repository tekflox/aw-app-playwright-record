"""Unit tests for template_app/plugin.py's TemplateAppPlugin — the app's whole
aw-workspace integration surface (activate()/deactivate()), previously
untested (0% coverage) despite being the pattern every aw-app-* Tier-1 app
copies verbatim (see plugin.py's module docstring).

`ctx` is a lightweight double, not the real F4 runtime — activate() only
touches two gated facades (ctx.commands, ctx.routes) plus ctx.package_dir and
ctx.config, so that's all the double needs to implement.

Run: .venv/aw/bin/python -m pytest tests/test_plugin.py -q
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from template_app.plugin import TemplateAppPlugin  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "aw-app.json").read_text())


def _make_ctx(config=None):
    ctx = MagicMock()
    ctx.package_dir = str(ROOT)
    ctx.config = config or {}
    return ctx


def test_activate_installs_every_manifest_cli_through_the_gated_facade():
    ctx = _make_ctx({"greeting": "Yo"})

    asyncio.run(TemplateAppPlugin().activate(ctx))

    clis = MANIFEST["contributes"]["system_clis"]
    assert ctx.commands.install_system_cli.call_count == len(clis)
    for cli, call in zip(clis, ctx.commands.install_system_cli.call_args_list):
        args, kwargs = call
        assert args[0] == cli["name"]
        assert args[1] == cli["installer"]
        assert kwargs["uninstall"] == "scripts/uninstall.sh"
        assert kwargs["verify"] == cli.get("verify")


def test_activate_registers_routes_and_sets_greeting_env():
    ctx = _make_ctx({"greeting": "Yo"})

    asyncio.run(TemplateAppPlugin().activate(ctx))

    assert os.environ["AW_APP_TEMPLATE_GREETING"] == "Yo"
    ctx.routes.register.assert_called_once()


def test_activate_defaults_greeting_to_hello_without_config():
    ctx = _make_ctx(config={})

    asyncio.run(TemplateAppPlugin().activate(ctx))

    assert os.environ["AW_APP_TEMPLATE_GREETING"] == "Hello"


def test_deactivate_completes_without_touching_ctx():
    # deactivate() takes no ctx — the framework's journal reverse-replay
    # handles revert; this just proves the coroutine returns cleanly.
    assert asyncio.run(TemplateAppPlugin().deactivate()) is None

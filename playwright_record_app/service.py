from __future__ import annotations

import contextlib
import io
import json
from argparse import Namespace
from pathlib import Path

from . import record


def _call(fn, **kwargs):
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            fn(Namespace(**kwargs))
    except SystemExit as exc:
        raise RuntimeError(str(exc)) from exc
    text = output.getvalue().strip()
    return json.loads(text) if text else {"ok": True}


def start(name: str, fps: int = 10, force: bool = False, pause_frame: bool = True):
    return _call(record.cmd_start, name=name, fps=fps, force=force, no_pause_frame=not pause_frame)


def stop(name: str | None = None, publish: bool = True):
    return _call(record.cmd_stop, name=name, no_open=True, no_presentation=not publish)


def snap(name: str | None = None, label: str | None = None):
    return _call(record.cmd_snap, name=name, label=label)


def status():
    return _call(record.cmd_status)


def kill(name: str):
    return _call(record.cmd_kill, name=name)


def gc(older_than: str = "7d"):
    return _call(record.cmd_gc, older_than=older_than)


def safe_bundle(name: str) -> Path:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("recording name must be a single path-safe segment")
    return record.bundle_path(name)

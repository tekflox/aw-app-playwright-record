"""TestClient coverage for template_app/routes.py's build_routes() (ADR
Decision 6 item 6, docs/knowledge_base/docs/architecture/
adr-app-front-back-routes-dual-mode.md).

TEMPLATE: this is the pattern every aw-app-* backend-routes app uses — build
the sub-app fresh per test (build_routes() must be call-idempotent), assert
HTTP + WS against it directly, no framework runtime needed.

Run: .venv/aw/bin/python -m pytest tests/test_routes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from template_app.routes import build_routes  # noqa: E402


def test_template():
    client = TestClient(build_routes())
    resp = client.get("/template")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Hello from the aw-app-template sub-app"}


def test_ws_echo_sends_aw_ws_1_init_frame_first():
    client = TestClient(build_routes())
    with client.websocket_connect("/ws/echo") as ws:
        assert ws.receive_json() == {
            "type": "aw_app_template_init",
            "data": {"protocol": 1},
        }


def test_ws_echo_round_trip_preserves_re():
    client = TestClient(build_routes())
    with client.websocket_connect("/ws/echo") as ws:
        ws.receive_json()  # init
        ws.send_json({"type": "aw_app_template_echo", "data": {"n": 1}, "id": "abc"})
        assert ws.receive_json() == {
            "type": "aw_app_template_echo",
            "data": {"n": 1},
            "re": "abc",
        }

        # id is optional — no id in, no re out
        ws.send_json({"type": "aw_app_template_echo", "data": {"n": 2}})
        assert ws.receive_json() == {"type": "aw_app_template_echo", "data": {"n": 2}}


def test_ws_echo_malformed_frame_gets_literal_error_type_and_stays_open():
    client = TestClient(build_routes())
    with client.websocket_connect("/ws/echo") as ws:
        ws.receive_json()  # init

        ws.send_text("not json")
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert set(reply["data"]) == {"code", "message"}

        # a non-conforming-but-valid-JSON frame is also an error
        ws.send_json({"type": "aw_app_template_echo"})  # missing "data"
        reply = ws.receive_json()
        assert reply["type"] == "error"

        # socket is still open — a conforming frame right after still echoes
        ws.send_json({"type": "aw_app_template_echo", "data": {"ok": True}})
        assert ws.receive_json() == {"type": "aw_app_template_echo", "data": {"ok": True}}


def test_ws_echo_ignores_unknown_type_and_stays_open():
    client = TestClient(build_routes())
    with client.websocket_connect("/ws/echo") as ws:
        ws.receive_json()  # init

        ws.send_json({"type": "some_other_type", "data": {}})
        # no reply for the unrecognised type — the next reply is this one
        ws.send_json({"type": "aw_app_template_echo", "data": {"still": "open"}})
        assert ws.receive_json() == {
            "type": "aw_app_template_echo",
            "data": {"still": "open"},
        }

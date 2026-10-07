"""
template_app's mode-agnostic FastAPI sub-app (ADR Decision 2/6:
docs/knowledge_base/docs/architecture/adr-app-front-back-routes-dual-mode.md).

``build_routes()`` returns the SAME sub-app object used in both modes:

* **integrated** — ``plugin.py`` hands it to ``ctx.routes.register(...)``,
  which mounts it at ``/api/apps/<slug>`` behind the runtime's
  ``IdentityGuard`` (aw-workspace ``src/apps/runtime.py``). Apps never
  implement their own auth in this mode.
* **standalone** — ``__main__.py`` mounts it at the SAME prefix itself, with
  no ``IdentityGuard`` (see that file's docstring for the auth posture).

Keep every path here RELATIVE (no ``/api/apps/<slug>`` prefix) so client
code and docs use one path shape in both modes:

    integrated: /api/apps/aw-app-template/template     /api/apps/aw-app-template/ws/echo
    standalone: /api/apps/aw-app-template/template     /api/apps/aw-app-template/ws/echo

Integrated in-process WS path shape (Decision 2):
``/api/apps/<slug>/ws/<name>`` — this sub-app declares
``@app.websocket("/ws/<name>")``. Browser-facing app-owned WebSockets that
need a top-level edge namespace belong under ``/ws/apps/<slug>/...``. Root
``/ws/*`` stays reserved for core/control-plane sockets
(``/ws/terminal``, ``/ws/notifications``, ...) — never add a new root-level
WS route for an app feature.

Message layer — ``aw-ws/1`` (docs/standards/app-backend-websocket-messaging.md
in the aw-workspace repo; this restates only what a new socket needs). Every
JSON frame, either direction, is this envelope and nothing else:

    {"type": "<domain>_<event>", "data": {...}, "id": "...", "re": "..."}

* ``type`` *(required, str)* — snake_case ``<domain>_<event>``. ``<domain>``
  is the app slug with every ``-`` collapsed to ``_`` — mechanically, not by
  taste. Here that makes it ``aw_app_template`` (from this app's
  ``aw-app.json`` ``"id"``). It reads oddly stacked next to ``_init``; that
  ugliness is the point of a mechanical rule, so resist "fixing" it.
* ``data`` *(required, object)* — the payload, always an object even when
  empty (``{}``), never a bare scalar/array. Never inline a payload you did
  not author into the envelope itself — that is how one upstream field
  happening to be named ``type`` silently corrupts a message elsewhere in
  this workspace.
* ``id`` *(optional, str)* — sender-assigned correlation id, present only
  when a reply is expected.
* ``re`` *(optional, str)* — echoes the ``id`` of the frame being answered.

Recipe for a new app socket (standard §8):

1. Declare ``@app.websocket("/ws/<name>")`` on the sub-app returned by
   ``build_routes()`` — relative path, no ``/api/apps/<slug>`` prefix.
2. Do not write auth code and do not re-verify identity. Read
   ``ws.scope["aw_identity"]`` only if you need to know who is calling;
   ``IdentityGuard`` already checked in integrated mode, and standalone mode
   has nothing to verify.
3. First frame, unconditionally: ``{"type": "<domain>_init", "data":
   {"protocol": 1, ...}}``.
4. Subsequent frames: ``{"type": "<domain>_<event>", "data": {...}}``.
5. Ignore any inbound frame whose ``type`` you do not recognise — never
   close the socket over one. That is what makes adding a message type a
   backwards-compatible change later.
6. Answer anything that is not valid JSON or not a conforming envelope with
   the literal ``{"type": "error", "data": {"code": "...", "message":
   "..."}}`` — not a domain-prefixed variant, so one client handler covers
   every socket.

Binary frames are exempt from all of the above and must stay exempt (standard
§4.5): a raw byte stream (a PTY, a screencast) is not a socket to wrap in
this envelope — the base64 hop buys nothing. ``/ws/echo`` below is pure JSON,
so the exemption does not apply to it.

``/ws/echo`` is the reference implementation of this recipe: it sends the
init frame, echoes back any conforming ``aw_app_template_echo`` frame
(preserving ``re``), answers anything malformed with the ``error`` shape
above, and silently ignores any other conforming-but-unrecognised ``type``.

``local_paths`` escape (Decision 2): an app that needs an endpoint callable
without a JWT from inside the workspace's own network namespace (e.g. an
agent-driven eval endpoint, like aw-app-devctl's planned ``/eval``/``/tabs``)
declares it in ``aw-app.json``:

    "contributes": { "routes": [ { "prefix": "/api/apps/<slug>",
                                    "local_paths": ["/eval", "/tabs"] } ] }

gated by a ``routes:local`` capability. TODO(framework, 2026-07-28): neither
``routes:local`` nor the IdentityGuard bypass it needs exist yet in
aw-workspace (``src/apps/capabilities.py``, ``src/apps/runtime.py``) — this
template ships no ``local_paths`` route and its manifest does not request
the capability; see ``skills/aw-create-app/SKILL.md`` for the documented
(not-yet-live) shape.
"""
from __future__ import annotations

import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# aw-app.json's "id" ("aw-app-template") with "-" -> "_" (aw-ws/1 §4.1) —
# mechanical, see the module docstring; do not rename this to look tidier.
_DOMAIN = "aw_app_template"
_PROTOCOL = 1
_ECHO_TYPE = f"{_DOMAIN}_echo"


def _error(code: str, message: str) -> dict:
    return {"type": "error", "data": {"code": code, "message": message}}


def build_routes() -> FastAPI:
    """Mode-agnostic factory — call this fresh for each mode (plugin.py /
    __main__.py both call it exactly once)."""
    app = FastAPI(title="template")

    @app.get("/template")
    async def template() -> dict:
        return {"message": "Hello from the aw-app-template sub-app"}

    @app.websocket("/ws/echo")
    async def ws_echo(ws: WebSocket) -> None:
        """Reference aw-ws/1 socket — see the module docstring's recipe."""
        await ws.accept()
        await ws.send_json({"type": f"{_DOMAIN}_init", "data": {"protocol": _PROTOCOL}})
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_json(_error("invalid_json", "frame was not valid JSON"))
                    continue
                if (
                    not isinstance(envelope, dict)
                    or not isinstance(envelope.get("type"), str)
                    or not isinstance(envelope.get("data"), dict)
                ):
                    await ws.send_json(
                        _error("invalid_envelope", "frame must be {type: str, data: object}")
                    )
                    continue
                if envelope["type"] != _ECHO_TYPE:
                    continue  # unknown type — ignore, keep the connection open (§6.4)
                reply = {"type": _ECHO_TYPE, "data": envelope["data"]}
                if isinstance(envelope.get("id"), str):
                    reply["re"] = envelope["id"]
                await ws.send_json(reply)
        except WebSocketDisconnect:
            pass

    return app

// Framework-free client core (ADR Decision 4) — the actual app logic,
// completely unaware of whether it's running integrated (inside the AW SPA,
// behind IdentityGuard) or standalone (its own page, no auth). Both
// plugin.js and standalone.js build the same {apiUrl, wsUrl} shape and hand
// it here; nothing else differs between the two modes.
//
//   apiUrl:    (sub) => string        e.g. sub="/template"   -> ".../api/apps/aw-app-template/template"
//   wsUrl:     (sub) => string        e.g. sub="/ws/echo" -> "ws(s)://.../api/apps/aw-app-template/ws/echo"
//
// App-owned top-level WebSocket namespaces are reserved at /ws/apps/<slug>/...
// so apps never claim root /ws/*; root /ws/* stays AW core/control-plane only.
//   fetchImpl: (path, init) => Promise<Response>   defaults to plain fetch
//
// connectEcho() speaks the aw-ws/1 envelope the server implements
// (template_app/routes.py) — every frame in or out is {type, data, id?,
// re?}, never a bare string. onMessage receives the PARSED envelope,
// including the aw_app_template_init handshake and any {"type":"error",
// ...} frame; send(data) wraps `data` in an aw_app_template_echo envelope
// with a fresh correlation id, so the reply's `re` proves the round-trip.
// This is deliberately not a reconnect/close-code-aware client — that is
// the shared hook's job (standard §7, a separate card); this stays the
// minimal shape a new app copies.

export function createClient({ apiUrl, wsUrl, fetchImpl = fetch }) {
  async function template() {
    const res = await fetchImpl(apiUrl('/template'));
    if (!res.ok) throw new Error(`GET /template -> ${res.status}`);
    return res.json();
  }

  function connectEcho({ onOpen, onMessage, onClose } = {}) {
    const ws = new WebSocket(wsUrl('/ws/echo'));
    if (onOpen) ws.addEventListener('open', onOpen);
    if (onMessage) {
      ws.addEventListener('message', (ev) => {
        // /ws/echo never sends non-JSON, but a reader copying this file into
        // a socket that mixes binary frames (aw-ws/1 §4.5) needs the guard.
        let envelope;
        try {
          envelope = JSON.parse(ev.data);
        } catch {
          return;
        }
        onMessage(envelope);
      });
    }
    if (onClose) ws.addEventListener('close', onClose);
    let nextId = 0;
    return {
      send: (data) => ws.send(JSON.stringify({ type: 'aw_app_template_echo', data, id: String(nextId++) })),
      close: () => ws.close(),
      raw: ws,
    };
  }

  return { template, connectEcho };
}

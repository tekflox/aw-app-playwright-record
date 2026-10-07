function w({ apiUrl: a, wsUrl: o, fetchImpl: s = fetch }) {
  async function e() {
    const t = await s(a("/template"));
    if (!t.ok) throw new Error(`GET /template -> ${t.status}`);
    return t.json();
  }
  function c({ onOpen: t, onMessage: p, onClose: l } = {}) {
    const n = new WebSocket(o("/ws/echo"));
    t && n.addEventListener("open", t), p && n.addEventListener("message", (r) => {
      let d;
      try {
        d = JSON.parse(r.data);
      } catch {
        return;
      }
      p(d);
    }), l && n.addEventListener("close", l);
    let f = 0;
    return {
      send: (r) => n.send(JSON.stringify({ type: "aw_app_template_echo", data: r, id: String(f++) })),
      close: () => n.close(),
      raw: n
    };
  }
  return { template: e, connectEcho: c };
}
const i = "aw-app-template";
function u(a) {
  const s = w({
    apiUrl: (e) => `/api/apps/${i}${e}`,
    wsUrl: (e) => a.sdk.api.wsUrl(`/api/apps/${i}${e}`),
    fetchImpl: (e, c) => a.sdk.api.fetch(e, c)
  }).connectEcho({
    onMessage: (e) => console.debug(`[${i}] ws:`, e.type, e.data)
  });
  a.onDispose(() => s.close());
}
export {
  u as default,
  u as register
};

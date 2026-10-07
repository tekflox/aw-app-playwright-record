"""Render a recording bundle into a self-contained report.html."""

import argparse
import base64
import json
import sys
from pathlib import Path


REPORT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{
    --bg: #0f1117;
    --panel: #161922;
    --border: #2a2f3d;
    --text: #e7eaf0;
    --muted: #8a93a6;
    --accent: #6ea8ff;
    --ok: #4caf50;
    --warn: #f5b041;
    --err: #ef5350;
    --code-bg: #0a0c12;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text);
    font-size: 14px;
  }}
  header {{
    padding: 16px 24px; border-bottom: 1px solid var(--border);
    background: var(--panel); display: flex; align-items: center; gap: 16px;
  }}
  header h1 {{ margin: 0; font-size: 18px; font-weight: 600; }}
  header .meta {{ color: var(--muted); font-size: 13px; }}
  nav.tabs {{
    display: flex; border-bottom: 1px solid var(--border);
    background: var(--panel);
  }}
  nav.tabs button {{
    background: none; border: none; color: var(--muted);
    padding: 12px 18px; cursor: pointer; font-size: 14px;
    border-bottom: 2px solid transparent;
  }}
  nav.tabs button.active {{
    color: var(--text); border-bottom-color: var(--accent);
  }}
  nav.tabs button:hover {{ color: var(--text); }}
  main {{ padding: 24px; }}
  section.tab {{ display: none; }}
  section.tab.active {{ display: block; }}
  .video-wrap {{
    border: 1px solid var(--border); border-radius: 6px; padding: 12px;
    background: var(--panel); margin-bottom: 24px; max-width: 950px;
  }}
  .video-wrap img,
  .video-wrap video {{
    max-width: 100%; display: block; border-radius: 4px;
    background: #000;
  }}
  .video-wrap video {{ width: 100%; }}
  .video-shortcuts {{
    margin-top: 10px; font-size: 12px; color: var(--muted);
  }}
  .video-shortcuts kbd {{
    background: #1c202b; border: 1px solid var(--border); border-radius: 3px;
    padding: 1px 6px; font-family: 'SF Mono', Menlo, monospace; font-size: 11px;
    color: var(--text);
  }}
  .timing-info {{
    margin-top: 8px; font-size: 13px; color: var(--text);
  }}
  .timing-info .muted {{ color: var(--muted); }}
  .stats {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }}
  .stat {{
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 6px; padding: 12px 16px;
  }}
  .stat .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .stat .value {{ font-size: 22px; font-weight: 600; margin-top: 4px; }}
  .stat.err .value {{ color: var(--err); }}
  .stat.warn .value {{ color: var(--warn); }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
    overflow: hidden;
  }}
  th, td {{
    padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  th {{ background: #1c202b; font-weight: 600; color: var(--muted); position: sticky; top: 0; }}
  tr:hover td {{ background: #1c202b; }}
  tr.expanded {{ background: #1c202b; }}
  .status-2xx {{ color: var(--ok); }}
  .status-3xx {{ color: var(--accent); }}
  .status-4xx {{ color: var(--warn); }}
  .status-5xx {{ color: var(--err); }}
  .url {{ color: var(--text); word-break: break-all; max-width: 700px; }}
  .console-row {{
    padding: 6px 12px; border-bottom: 1px solid var(--border);
    font-family: 'SF Mono', Menlo, monospace; font-size: 12px;
    white-space: pre-wrap; word-break: break-word;
  }}
  .console-row.error {{ color: var(--err); }}
  .console-row.warning, .console-row.warn {{ color: var(--warn); }}
  .console-row.info {{ color: var(--accent); }}
  .console-row .ts {{ color: var(--muted); margin-right: 12px; }}
  .filter-bar {{
    margin-bottom: 12px; display: flex; gap: 8px; align-items: center;
  }}
  .filter-bar input {{
    background: var(--code-bg); color: var(--text);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 6px 10px; font-size: 13px; min-width: 280px;
  }}
  .filter-bar button {{
    background: var(--panel); color: var(--text);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 6px 12px; cursor: pointer; font-size: 12px;
  }}
  .filter-bar button.active {{ background: var(--accent); color: #000; border-color: var(--accent); }}
  pre.json {{
    background: var(--code-bg); border: 1px solid var(--border);
    padding: 12px; border-radius: 4px; overflow: auto; font-size: 12px;
    color: var(--muted);
  }}
  .frames-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 8px;
  }}
  .frames-grid img {{
    width: 100%; border: 1px solid var(--border); border-radius: 4px; cursor: pointer;
  }}
  code {{ background: var(--code-bg); padding: 2px 6px; border-radius: 3px; }}
  .empty {{ color: var(--muted); padding: 40px; text-align: center; font-style: italic; }}
</style>
</head>
<body>
<header>
  <h1>📹 {title}</h1>
  <div class="meta">
    Started <strong>{started_at}</strong> · Duration <strong>{duration_s}s</strong> ·
    <code>{bundle_path}</code>
  </div>
</header>

<nav class="tabs">
  <button class="active" data-tab="overview">Overview</button>
  <button data-tab="network">Network ({network_count})</button>
  <button data-tab="console">Console ({console_count})</button>
  <button data-tab="frames">Frames ({frame_count})</button>
  <button data-tab="trace">Trace</button>
</nav>

<main>
  <section id="overview" class="tab active">
    {gif_block}
    <div class="stats">
      <div class="stat"><div class="label">Frames</div><div class="value">{frame_count}</div></div>
      <div class="stat"><div class="label">Network requests</div><div class="value">{network_count}</div></div>
      <div class="stat"><div class="label">Console messages</div><div class="value">{console_count}</div></div>
      <div class="stat {error_class}"><div class="label">Errors</div><div class="value">{error_count}</div></div>
      <div class="stat {failed_req_class}"><div class="label">Failed requests</div><div class="value">{failed_count}</div></div>
    </div>
  </section>

  <section id="network" class="tab">
    <div class="filter-bar">
      <input id="network-filter" placeholder="Filter by URL, method, status..." />
      <button data-net-filter="all" class="active">All</button>
      <button data-net-filter="4xx">4xx</button>
      <button data-net-filter="5xx">5xx</button>
      <button data-net-filter="failed">Failed</button>
    </div>
    <table id="network-table">
      <thead>
        <tr><th>Method</th><th>Status</th><th>URL</th><th>Type</th><th>Page</th></tr>
      </thead>
      <tbody></tbody>
    </table>
  </section>

  <section id="console" class="tab">
    <div class="filter-bar">
      <input id="console-filter" placeholder="Filter messages..." />
      <button data-con-filter="all" class="active">All</button>
      <button data-con-filter="error">Errors</button>
      <button data-con-filter="warning">Warnings</button>
    </div>
    <div id="console-list"></div>
  </section>

  <section id="frames" class="tab">
    {frames_block}
  </section>

  <section id="trace" class="tab">
    <p>Open the Playwright trace viewer for the deepest forensic dive (actions, DOM snapshots, source):</p>
    <pre class="json">npx playwright show-trace {trace_abs_path}</pre>
    <p>Or use the online viewer at <a href="https://trace.playwright.dev/" target="_blank">trace.playwright.dev</a> and drag <code>trace.zip</code> onto the page.</p>
  </section>
</main>

<script>
const NETWORK_LOG = {network_json};
const CONSOLE_LOG = {console_json};

// ─── Tabs ───
document.querySelectorAll('nav.tabs button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('nav.tabs button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('section.tab').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
  }});
}});

// ─── Video keyboard shortcuts ───
const video = document.getElementById('session-video');
if (video) {{
  // Don't capture keys when user is typing in a filter
  document.addEventListener('keydown', (e) => {{
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    // Only act when overview tab is active (video is visible)
    const overview = document.getElementById('overview');
    if (!overview.classList.contains('active')) return;

    const FRAME_STEP = 1 / 10;  // ~100ms — close to typical screencast cadence
    switch (e.key) {{
      case ' ':
      case 'k':
        e.preventDefault();
        if (video.paused) video.play(); else video.pause();
        break;
      case 'ArrowLeft':
      case 'j':
        e.preventDefault();
        video.currentTime = Math.max(0, video.currentTime - 1);
        break;
      case 'ArrowRight':
      case 'l':
        e.preventDefault();
        video.currentTime = Math.min(video.duration, video.currentTime + 1);
        break;
      case ',':
        e.preventDefault();
        video.pause();
        video.currentTime = Math.max(0, video.currentTime - FRAME_STEP);
        break;
      case '.':
        e.preventDefault();
        video.pause();
        video.currentTime = Math.min(video.duration, video.currentTime + FRAME_STEP);
        break;
      case 'Home':
        e.preventDefault();
        video.currentTime = 0;
        break;
      case 'End':
        e.preventDefault();
        video.currentTime = video.duration;
        break;
      case '0': case '1': case '2': case '3': case '4':
      case '5': case '6': case '7': case '8': case '9':
        e.preventDefault();
        video.currentTime = video.duration * (parseInt(e.key, 10) / 10);
        break;
    }}
  }});
}}

// ─── Network ───
function statusClass(s) {{
  if (!s) return '';
  if (s >= 500) return 'status-5xx';
  if (s >= 400) return 'status-4xx';
  if (s >= 300) return 'status-3xx';
  if (s >= 200) return 'status-2xx';
  return '';
}}

function renderNetwork(filter, kind) {{
  // Coalesce: prefer "response" rows over "request"; show failures.
  // Group by url+method+timestamp_window — but simplest: show response rows + failed rows.
  const rows = NETWORK_LOG.filter(r => r.kind === 'response' || r.kind === 'request_failed');
  const f = filter ? filter.toLowerCase() : '';
  const tbody = document.querySelector('#network-table tbody');
  tbody.innerHTML = '';
  let shown = 0;
  for (const r of rows) {{
    if (kind === '4xx' && !(r.status >= 400 && r.status < 500)) continue;
    if (kind === '5xx' && !(r.status >= 500)) continue;
    if (kind === 'failed' && r.kind !== 'request_failed') continue;
    if (f && !((r.url||'').toLowerCase().includes(f) || (r.method||'').toLowerCase().includes(f) || String(r.status||'').includes(f))) continue;
    const tr = document.createElement('tr');
    const status = r.status ? `<span class="${{statusClass(r.status)}}">${{r.status}}</span>` : (r.kind === 'request_failed' ? `<span class="status-5xx">FAIL</span>` : '');
    tr.innerHTML = `<td><code>${{r.method||''}}</code></td><td>${{status}}</td>` +
                   `<td class="url">${{r.url||''}}</td>` +
                   `<td>${{r.resource_type||''}}</td>` +
                   `<td><code>${{(r.page_url||'').slice(0,60)}}</code></td>`;
    tbody.appendChild(tr);
    shown++;
  }}
  if (shown === 0) tbody.innerHTML = '<tr><td colspan="5"><div class="empty">No requests match the filter.</div></td></tr>';
}}
renderNetwork('', 'all');
document.getElementById('network-filter').addEventListener('input', e => {{
  const kind = document.querySelector('[data-net-filter].active').dataset.netFilter;
  renderNetwork(e.target.value, kind);
}});
document.querySelectorAll('[data-net-filter]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-net-filter]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderNetwork(document.getElementById('network-filter').value, btn.dataset.netFilter);
  }});
}});

// ─── Console ───
function renderConsole(filter, kind) {{
  const list = document.getElementById('console-list');
  list.innerHTML = '';
  const f = filter ? filter.toLowerCase() : '';
  let shown = 0;
  for (const m of CONSOLE_LOG) {{
    if (kind === 'error' && !(m.type === 'error' || m.type === 'pageerror')) continue;
    if (kind === 'warning' && !(m.type === 'warning' || m.type === 'warn')) continue;
    if (f && !(m.text||'').toLowerCase().includes(f)) continue;
    const div = document.createElement('div');
    div.className = `console-row ${{m.type||''}}`;
    const ts = (m.ts||'').slice(11, 19);
    div.innerHTML = `<span class="ts">${{ts}}</span><strong>[${{m.type||'log'}}]</strong> ${{escapeHtml(m.text||'')}}` +
                    (m.url ? `<div class="ts">${{m.url}}:${{m.line||''}}</div>` : '');
    list.appendChild(div);
    shown++;
  }}
  if (shown === 0) list.innerHTML = '<div class="empty">No messages match the filter.</div>';
}}
function escapeHtml(s) {{ return s.replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]); }}
renderConsole('', 'all');
document.getElementById('console-filter').addEventListener('input', e => {{
  const kind = document.querySelector('[data-con-filter].active').dataset.conFilter;
  renderConsole(e.target.value, kind);
}});
document.querySelectorAll('[data-con-filter]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-con-filter]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderConsole(document.getElementById('console-filter').value, btn.dataset.conFilter);
  }});
}});
</script>
</body>
</html>
"""


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def render_report(bundle: Path) -> Path:
    """Render report.html in the bundle. Returns path."""
    bundle = Path(bundle)
    meta = json.loads((bundle / "meta.json").read_text())
    network = read_jsonl(bundle / "network.jsonl")
    console = read_jsonl(bundle / "console.jsonl")

    failed_count = sum(1 for r in network if r.get("kind") == "request_failed"
                       or (r.get("status") and r["status"] >= 400))

    mp4_path = bundle / "session.mp4"
    gif_path = bundle / "session.gif"
    timing_info = ""
    real_d = meta.get("gif_real_duration_s")
    gif_d = meta.get("gif_playback_duration_s")
    pauses = meta.get("gif_pauses_compressed", 0)
    if real_d is not None and gif_d is not None:
        timing_info = (
            f'<div class="timing-info">'
            f'Real session: <strong>{real_d}s</strong> → playback: <strong>{gif_d}s</strong>'
        )
        if pauses > 0:
            timing_info += f' · <span class="muted">{pauses} pause(s) capped at {meta.get("gif_max_frame_gap_s", 5)}s</span>'
        timing_info += '</div>'

    if mp4_path.exists():
        mp4_b64 = base64.b64encode(mp4_path.read_bytes()).decode()
        gif_block = (
            '<div class="video-wrap">'
            f'<video id="session-video" src="data:video/mp4;base64,{mp4_b64}" '
            'controls preload="metadata" playsinline></video>'
            '<div class="video-shortcuts">'
            '<kbd>Space</kbd> play/pause &nbsp; '
            '<kbd>←</kbd>/<kbd>→</kbd> ±1s &nbsp; '
            '<kbd>,</kbd>/<kbd>.</kbd> step frame &nbsp; '
            '<kbd>0</kbd>-<kbd>9</kbd> jump 0–90% &nbsp; '
            '<kbd>Home</kbd>/<kbd>End</kbd> '
            '</div>'
            f'{timing_info}'
            '</div>'
        )
    elif gif_path.exists():
        gif_b64 = base64.b64encode(gif_path.read_bytes()).decode()
        gif_block = (
            '<div class="video-wrap">'
            f'<img src="data:image/gif;base64,{gif_b64}" alt="Session recording" />'
            '<div class="video-shortcuts muted">GIF only — no pause/seek. '
            'Run <code>ffmpeg</code> on bundle frames to produce mp4 for full controls.</div>'
            f'{timing_info}'
            '</div>'
        )
    else:
        gif_block = '<div class="empty">No video (frame_count was 0 or ffmpeg failed)</div>'

    frames_dir = bundle / "frames"
    if frames_dir.exists():
        frames = sorted(frames_dir.glob("*.jpg"))
        if frames:
            n = len(frames)
            step = max(1, n // 24)
            sample = frames[::step][:24]
            thumbs = []
            for f in sample:
                b64 = base64.b64encode(f.read_bytes()).decode()
                thumbs.append(f'<img src="data:image/jpeg;base64,{b64}" title="{f.name}" />')
            frames_block = '<div class="frames-grid">' + "".join(thumbs) + '</div>'
        else:
            frames_block = '<div class="empty">No frames captured.</div>'
    else:
        frames_block = '<div class="empty">No frames directory.</div>'

    title = f"Recording: {meta.get('name', bundle.name)}"
    html = REPORT_TEMPLATE.format(
        title=title,
        started_at=meta.get("started_at", "?"),
        duration_s=meta.get("duration_s", "?"),
        bundle_path=str(bundle),
        frame_count=meta.get("frame_count", 0),
        network_count=len([r for r in network if r.get("kind") == "response"
                          or r.get("kind") == "request_failed"]),
        console_count=len(console),
        error_count=meta.get("error_count", 0),
        error_class="err" if meta.get("error_count", 0) > 0 else "",
        failed_count=failed_count,
        failed_req_class="warn" if failed_count > 0 else "",
        gif_block=gif_block,
        frames_block=frames_block,
        trace_abs_path=str((bundle / "trace.zip").resolve()),
        network_json=json.dumps(network),
        console_json=json.dumps(console),
    )

    out = bundle / "report.html"
    out.write_text(html)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", required=True, help="Path to recording bundle dir")
    args = p.parse_args()
    out = render_report(Path(args.bundle))
    print(json.dumps({"ok": True, "report_html": str(out)}, indent=2))


if __name__ == "__main__":
    main()

"""
aw-playwright-record — record a playwright (CDP-attached) session into a bundle.

Attaches via CDP to the existing browser-aw2 Chromium container at
localhost:9223 (or $CDP_ENDPOINT) and observes:
  - trace.zip (Playwright trace: actions, screenshots, DOM, network, console)
  - frames/NNNN.jpg (raw CDP screencast frames, stitched into session.gif)
  - network.jsonl (every request/response, append-only)
  - console.jsonl (console messages + page errors, append-only)

Subcommands:
  start --name <n> [--fps 10] [--force]   → daemonize, return bundle path
  stop  [--name <n>]                       → signal daemon, wait, print summary
  snap  [--name <n>] [--label foo]         → discrete extra screenshot
  status                                   → list active and finished bundles
  kill  --name <n>                         → SIGTERM a stuck daemon
  gc    --older-than 7d                    → remove old bundles

Daemon lifetime is bounded by start↔stop. Safety nets:
  - max duration (default 30 min) → auto-finalize
  - idle timeout (default 10 min) → auto-finalize
  - SIGTERM/SIGINT → finalize gracefully
"""

import argparse
import asyncio
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(os.environ.get("AW_WORKSPACE_CONTAINER_DIR", "/opt/aw-workspace"))
WORKSPACE_HOME = Path(os.environ.get("AW_WORKSPACE_HOME", WORKSPACE_ROOT / ".aw-workspace"))
RECORDINGS_DIR = Path(
    os.environ.get("PLAYWRIGHT_RECORD_DATA_DIR", WORKSPACE_HOME / "data" / "playwright-record" / "recordings")
)
CDP_ENDPOINT = os.environ.get("CDP_ENDPOINT", "http://aw-app-browser:9223")

# awserv runs INSIDE the container on a fixed port (driven by aw.json#default_port).
# AW_PORT only changes the host-side publish port. From here we always hit 9123.
AWSERV_URL = os.environ.get("AW_WORKSPACE_API_URL", f"http://127.0.0.1:{os.environ.get('AW_PORT', '9030')}")

DEFAULT_FPS = 10
MAX_DURATION_S = 30 * 60
IDLE_TIMEOUT_S = 10 * 60
LOG_LINE_LIMIT = 4000

MAX_FRAME_GAP_S = 5.0
MIN_FRAME_GAP_S = 0.05
LAST_FRAME_GAP_S = 1.5



def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def bundle_path(name: str) -> Path:
    return RECORDINGS_DIR / name


def is_alive(pid: int) -> bool:
    """True iff the process exists AND is not a zombie.

    Plain `kill(pid, 0)` returns True on zombies (the entry still exists in the
    kernel's process table waiting to be reaped), which made `gc-presentations` and
    `find_active_bundle` think a finalized recorder was still running. Reading
    /proc/<pid>/status filters those out.
    """
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("State:"):
                    # State line looks like: "State:\tZ (zombie)" or "S (sleeping)" etc.
                    return "Z" not in line.split(maxsplit=2)[1:2]
    except FileNotFoundError:
        return False
    except OSError:
        pass
    return True


def find_active_bundle() -> Path | None:
    """Return the bundle of the only running daemon, or None / raise if ambiguous."""
    if not RECORDINGS_DIR.exists():
        return None
    candidates = []
    for d in RECORDINGS_DIR.iterdir():
        pid_file = d / "recorder.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                if is_alive(pid):
                    candidates.append(d)
            except (ValueError, OSError):
                pass
    if len(candidates) == 0:
        return None
    if len(candidates) > 1:
        names = ", ".join(c.name for c in candidates)
        raise SystemExit(f"Multiple active recordings ({names}); pass --name to disambiguate.")
    return candidates[0]


def append_jsonl(path: Path, obj: dict):
    line = json.dumps(obj, default=str)[:LOG_LINE_LIMIT]
    with path.open("a") as f:
        f.write(line + "\n")



def cmd_start(args):
    name = args.name
    bundle = bundle_path(name)

    if bundle.exists():
        if not args.force:
            sys.exit(
                f"Error: {bundle} already exists.\n"
                f"  Pass --force to overwrite, or pick a different name."
            )
        shutil.rmtree(bundle)

    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "frames").mkdir()

    meta = {
        "name": name,
        "started_at": utc_now_iso(),
        "ended_at": None,
        "status": "starting",
        "cdp_endpoint": CDP_ENDPOINT,
        "fps": args.fps,
        "pause_frame_enabled": not args.no_pause_frame,
    }
    (bundle / "meta.json").write_text(json.dumps(meta, indent=2))

    pid = os.fork()
    if pid == 0:
        os.setsid()
        os.umask(0)
        log = (bundle / "daemon.log").open("ab", buffering=0)
        # Use process-standard descriptors directly. MCP/HTTP callers capture
        # Python's stdout with StringIO, which intentionally has no fileno().
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        with open(os.devnull, "rb") as devnull:
            os.dup2(devnull.fileno(), 0)
        try:
            asyncio.run(daemon_main(bundle, args.fps))
        except Exception as e:
            print(f"[daemon] FATAL: {e!r}", flush=True)
            (bundle / "ERROR").write_text(f"{e!r}\n")
        os._exit(0)

    (bundle / "recorder.pid").write_text(str(pid))

    print(f"[start] daemon pid={pid}, waiting for READY...", file=sys.stderr)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if (bundle / "READY").exists():
            break
        if (bundle / "ERROR").exists():
            sys.exit(f"Error: daemon failed.\nSee: {bundle / 'daemon.log'}")
        if not is_alive(pid):
            sys.exit(f"Error: daemon exited before READY.\nSee: {bundle / 'daemon.log'}")
        time.sleep(0.2)
    else:
        sys.exit(f"Error: daemon did not become READY in 15s.\nSee: {bundle / 'daemon.log'}")

    print(json.dumps({
        "ok": True,
        "name": name,
        "bundle_path": str(bundle),
        "pid": pid,
        "live_view": "http://localhost:7900",
    }, indent=2))



def cmd_stop(args):
    if args.name:
        bundle = bundle_path(args.name)
        if not bundle.exists():
            sys.exit(f"Error: no bundle at {bundle}")
    else:
        bundle = find_active_bundle()
        if bundle is None:
            sys.exit("Error: no active recording. Pass --name to stop a specific one.")

    pid_file = bundle / "recorder.pid"
    if not pid_file.exists():
        sys.exit(f"Error: no recorder.pid in {bundle}")

    pid = int(pid_file.read_text().strip())
    if not is_alive(pid):
        sys.exit(f"Error: daemon pid={pid} is not alive (probably already finished).\n"
                 f"Bundle: {bundle}")

    print(f"[stop] signaling daemon pid={pid}...", file=sys.stderr)
    os.kill(pid, signal.SIGUSR1)

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if (bundle / "DONE").exists():
            break
        if not is_alive(pid):
            break
        time.sleep(0.25)
    else:
        sys.exit(f"Error: daemon did not finalize in 60s.\nSee: {bundle / 'daemon.log'}")

    meta = json.loads((bundle / "meta.json").read_text())
    summary = {
        "ok": True,
        "name": meta["name"],
        "bundle_path": str(bundle),
        "duration_s": meta.get("duration_s"),
        "frames": meta.get("frame_count", 0),
        "network_requests": meta.get("network_count", 0),
        "console_messages": meta.get("console_count", 0),
        "errors": meta.get("error_count", 0),
        "trace": str(bundle / "trace.zip") if (bundle / "trace.zip").exists() else None,
        "gif": str(bundle / "session.gif") if (bundle / "session.gif").exists() else None,
        "report_html": str(bundle / "report.html") if (bundle / "report.html").exists() else None,
    }

    # Push to AW presentation (visible in the dashboard) — opt-out via --no-presentation.
    # Failures are non-fatal: stop should still report the bundle even if awserv
    # is down or auth fails.
    if not args.no_presentation:
        presentation = push_presentation_for_bundle(bundle)
        if presentation and presentation.get("id"):
            summary["presentation_id"] = presentation["id"]
            summary["presentation_url"] = f"{AWSERV_URL}/#/presentation/{presentation['id']}"

    print(json.dumps(summary, indent=2))

    if not args.no_open and summary["report_html"] and sys.platform == "darwin":
        subprocess.Popen(["open", summary["report_html"]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



def cmd_snap(args):
    bundle = bundle_path(args.name) if args.name else find_active_bundle()
    if bundle is None:
        sys.exit("Error: no active recording.")
    (bundle / "SNAP_REQUEST").write_text(args.label or "snap")
    pid = int((bundle / "recorder.pid").read_text().strip())
    os.kill(pid, signal.SIGUSR2)
    print(json.dumps({"ok": True, "bundle": str(bundle), "label": args.label}, indent=2))



def cmd_status(args):
    if not RECORDINGS_DIR.exists():
        print(json.dumps({"recordings": []}, indent=2))
        return
    out = []
    for d in sorted(RECORDINGS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            continue
        pid_file = d / "recorder.pid"
        alive = False
        if pid_file.exists():
            try:
                alive = is_alive(int(pid_file.read_text().strip()))
            except (ValueError, OSError):
                pass
        out.append({
            "name": meta.get("name", d.name),
            "status": "RUNNING" if alive else meta.get("status", "?"),
            "started_at": meta.get("started_at"),
            "ended_at": meta.get("ended_at"),
            "duration_s": meta.get("duration_s"),
            "frames": meta.get("frame_count", 0),
            "bundle_path": str(d),
        })
    print(json.dumps({"recordings": out}, indent=2))



def cmd_kill(args):
    bundle = bundle_path(args.name)
    pid_file = bundle / "recorder.pid"
    if not pid_file.exists():
        sys.exit(f"Error: no recorder.pid in {bundle}")
    pid = int(pid_file.read_text().strip())
    if not is_alive(pid):
        print(json.dumps({"ok": False, "reason": "daemon not alive"}, indent=2))
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if not is_alive(pid):
            break
        time.sleep(0.25)
    else:
        os.kill(pid, signal.SIGKILL)
    print(json.dumps({"ok": True, "killed_pid": pid}, indent=2))



def cmd_gc(args):
    if not RECORDINGS_DIR.exists():
        print(json.dumps({"removed": []}, indent=2))
        return
    cutoff = time.time() - parse_duration(args.older_than)
    removed = []
    for d in RECORDINGS_DIR.iterdir():
        if not d.is_dir():
            continue
        pid_file = d / "recorder.pid"
        if pid_file.exists():
            try:
                if is_alive(int(pid_file.read_text().strip())):
                    continue
            except (ValueError, OSError):
                pass
        if d.stat().st_mtime < cutoff:
            shutil.rmtree(d)
            removed.append(d.name)
    print(json.dumps({"removed": removed}, indent=2))


def parse_duration(s: str) -> float:
    """e.g. '7d' → 604800, '1h' → 3600, '30m' → 1800."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if s[-1] in units and s[:-1].isdigit():
        return int(s[:-1]) * units[s[-1]]
    return float(s)


def _awserv_request(method: str, path: str, body: dict | None = None, timeout: float = 10.0):
    """POST/PUT/GET against awserv. Returns parsed JSON or {'error': ...}.

    Mirrors the auth pattern in src/mcp/presentation-server.py — re-reads the api key
    each call so it survives awserv restarts that rotate it.
    """
    url = f"{AWSERV_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    try:
        api_key = os.environ.get("AW_WORKSPACE_API_KEY", "").strip()
        if api_key:
            headers["x-api-key"] = api_key
    except OSError:
        pass
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
        return {"error": repr(e), "success": False}


def push_presentation_for_bundle(bundle: Path) -> dict | None:
    """Upsert a presentation in awserv that displays the bundle's report.html.

    Presentation id is `recording-<name>` so re-recording the same name replaces the
    same presentation in place. Returns the awserv response (or None if no report).
    Failures are non-fatal — printed to stderr, swallowed.
    """
    report = bundle / "report.html"
    if not report.exists():
        print(f"[presentation] skip: no report.html in {bundle}", file=sys.stderr)
        return None
    try:
        meta = json.loads((bundle / "meta.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        meta = {"name": bundle.name}

    name = meta.get("name", bundle.name)
    presentation_id = f"recording-{name}"
    duration = meta.get("duration_s")
    title_suffix = f" — {duration:.1f}s" if isinstance(duration, (int, float)) else ""
    title = f"Recording: {name}{title_suffix}"

    html = report.read_text(encoding="utf-8", errors="replace")

    # Upsert: GET first; PUT if it exists, else POST. Same pattern as presentation-server.py.
    base = "/api/apps/presentations/presentations"
    existing = _awserv_request("GET", f"{base}/{presentation_id}")
    if existing.get("id"):
        result = _awserv_request("PUT", f"{base}/{presentation_id}",
                                 {"title": title, "html": html})
    else:
        result = _awserv_request("POST", base,
                                 {"id": presentation_id, "title": title, "html": html})

    if result.get("error"):
        print(f"[presentation] push failed: {result['error']}", file=sys.stderr)
        return result

    print(f"[presentation] pushed: id={presentation_id} ({len(html):,} bytes)", file=sys.stderr)
    return result


PRESENTATION_ID_PREFIX = "recording-"


def cmd_gc_presentations(args):
    """Delete recording presentations from awserv.

    Two modes:
      - default (--orphans-only): delete only presentations whose underlying bundle
        no longer exists on disk. Safe to run anytime.
      - --all: delete every presentation with id prefix 'recording-' regardless of
        bundle state. Use after a `gc` to fully reset the dashboard.

    Optional --older-than filter applies to either mode (compares to bundle
    mtime if the bundle still exists; orphan presentations are always eligible).
    """
    base = "/api/apps/presentations/presentations"
    listing = _awserv_request("GET", base)
    if isinstance(listing, dict) and listing.get("error"):
        sys.exit(f"Error: could not list presentations: {listing['error']}")
    if not isinstance(listing, list):
        sys.exit(f"Error: unexpected /api/presentations response: {listing!r}")

    cutoff = time.time() - parse_duration(args.older_than) if args.older_than else None
    removed, kept = [], []

    for c in listing:
        cid = c.get("id", "")
        if not cid.startswith(PRESENTATION_ID_PREFIX):
            continue
        name = cid[len(PRESENTATION_ID_PREFIX):]
        bundle = bundle_path(name)
        bundle_exists = bundle.exists()

        # Skip presentations whose bundle is owned by a live daemon — never yank
        # something mid-recording.
        if bundle_exists:
            pid_file = bundle / "recorder.pid"
            if pid_file.exists():
                try:
                    if is_alive(int(pid_file.read_text().strip())):
                        kept.append({"id": cid, "reason": "daemon alive"})
                        continue
                except (ValueError, OSError):
                    pass

        if args.orphans_only and bundle_exists:
            kept.append({"id": cid, "reason": "bundle present"})
            continue

        if cutoff is not None and bundle_exists:
            if bundle.stat().st_mtime >= cutoff:
                kept.append({"id": cid, "reason": "newer than cutoff"})
                continue

        result = _awserv_request("DELETE", f"{base}/{cid}")
        if isinstance(result, dict) and result.get("success") is False:
            kept.append({"id": cid, "reason": f"delete failed: {result.get('error')}"})
        else:
            removed.append(cid)

    print(json.dumps({"removed": removed, "kept": kept}, indent=2))



class DaemonState:
    def __init__(self, bundle: Path, fps: int):
        self.bundle = bundle
        self.fps = fps
        self.frame_count = 0
        self.network_count = 0
        self.console_count = 0
        self.error_count = 0
        self.last_event_ts = time.monotonic()
        self.start_ts = time.monotonic()
        self.should_stop = False
        self.snap_requested = False
        self.cdp_session = None
        self.context = None
        self.tracked_pages: set = set()


async def daemon_main(bundle: Path, fps: int):
    from playwright.async_api import async_playwright

    state = DaemonState(bundle, fps)

    loop = asyncio.get_running_loop()

    def on_sigusr1():
        print("[daemon] SIGUSR1 received → stopping", flush=True)
        state.should_stop = True

    def on_sigusr2():
        print("[daemon] SIGUSR2 received → snap requested", flush=True)
        state.snap_requested = True

    def on_sigterm():
        print("[daemon] SIGTERM/SIGINT received → stopping", flush=True)
        state.should_stop = True

    loop.add_signal_handler(signal.SIGUSR1, on_sigusr1)
    loop.add_signal_handler(signal.SIGUSR2, on_sigusr2)
    loop.add_signal_handler(signal.SIGTERM, on_sigterm)
    loop.add_signal_handler(signal.SIGINT, on_sigterm)

    print(f"[daemon] connecting to {CDP_ENDPOINT}...", flush=True)
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(CDP_ENDPOINT)
    except Exception as e:
        raise RuntimeError(f"connect_over_cdp failed: {e}") from e

    if not browser.contexts:
        raise RuntimeError("Browser has no contexts")
    context = browser.contexts[0]
    state.context = context
    print(f"[daemon] attached, contexts={len(browser.contexts)}, "
          f"pages={len(context.pages)}", flush=True)

    try:
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        print("[daemon] tracing started", flush=True)
    except Exception as e:
        print(f"[daemon] tracing.start warning: {e!r}", flush=True)

    for page in context.pages:
        await attach_page_listeners(state, page)

    context.on("page", lambda p: asyncio.create_task(attach_page_listeners(state, p)))

    state.cdp_session = None

    if not context.pages:
        for _ in range(20):
            await asyncio.sleep(0.25)
            if context.pages:
                break
    if not context.pages:
        raise RuntimeError("Context has no pages after waiting")

    (bundle / "READY").touch()
    print("[daemon] READY (using trace.zip as frame source)", flush=True)

    while not state.should_stop:
        if state.snap_requested:
            await handle_snap(state)
            state.snap_requested = False

        elapsed = time.monotonic() - state.start_ts
        idle = time.monotonic() - state.last_event_ts
        if elapsed > MAX_DURATION_S:
            print(f"[daemon] max duration ({MAX_DURATION_S}s) exceeded, finalizing", flush=True)
            break
        if idle > IDLE_TIMEOUT_S:
            print(f"[daemon] idle timeout ({IDLE_TIMEOUT_S}s) exceeded, finalizing", flush=True)
            break

        await asyncio.sleep(0.25)

    print("[daemon] finalizing...", flush=True)

    try:
        await context.tracing.stop(path=str(bundle / "trace.zip"))
        print("[daemon] trace.zip written", flush=True)
    except Exception as e:
        print(f"[daemon] tracing.stop warning: {e!r}", flush=True)

    try:
        n_frames = extract_frames_from_trace(bundle)
        state.frame_count = n_frames
        print(f"[daemon] extracted {n_frames} frames from trace.zip", flush=True)
    except Exception as e:
        print(f"[daemon] frame extraction failed: {e!r}", flush=True)

    meta = json.loads((bundle / "meta.json").read_text())
    meta["ended_at"] = utc_now_iso()
    meta["duration_s"] = round(time.monotonic() - state.start_ts, 2)
    meta["status"] = "FINISHED"
    meta["frame_count"] = state.frame_count
    meta["network_count"] = state.network_count
    meta["console_count"] = state.console_count
    meta["error_count"] = state.error_count
    (bundle / "meta.json").write_text(json.dumps(meta, indent=2))

    if state.frame_count > 0:
        try:
            stats = run_ffmpeg_gif(bundle, fps)
            meta.update({
                "gif_real_duration_s": stats["real_duration_s"],
                "gif_playback_duration_s": stats["gif_duration_s"],
                "gif_pauses_compressed": stats["pauses_compressed"],
                "gif_max_frame_gap_s": stats["max_frame_gap_s"],
            })
            print(f"[daemon] session.gif written "
                  f"(real {stats['real_duration_s']}s → gif {stats['gif_duration_s']}s, "
                  f"{stats['pauses_compressed']} pauses compressed)", flush=True)
        except Exception as e:
            print(f"[daemon] gif ffmpeg failed: {e!r}", flush=True)

        try:
            run_ffmpeg_mp4(bundle, fps)
            print("[daemon] session.mp4 written", flush=True)
        except Exception as e:
            print(f"[daemon] mp4 ffmpeg failed: {e!r}", flush=True)

        (bundle / "meta.json").write_text(json.dumps(meta, indent=2))

    try:
        from render_report import render_report
        render_report(bundle)
        print("[daemon] report.html written", flush=True)
    except Exception as e:
        print(f"[daemon] render_report failed: {e!r}", flush=True)

    try:
        await browser.close()
    except Exception:
        pass
    await pw.stop()

    (bundle / "DONE").touch()
    print("[daemon] DONE", flush=True)


async def attach_page_listeners(state: DaemonState, page):
    if id(page) in state.tracked_pages:
        return
    state.tracked_pages.add(id(page))

    bundle = state.bundle

    def on_console(msg):
        state.console_count += 1
        if msg.type == "error":
            state.error_count += 1
        state.last_event_ts = time.monotonic()
        loc = msg.location or {}
        append_jsonl(bundle / "console.jsonl", {
            "ts": utc_now_iso(),
            "type": msg.type,
            "text": msg.text,
            "url": loc.get("url"),
            "line": loc.get("lineNumber"),
            "page_url": page.url,
        })

    def on_pageerror(err):
        state.error_count += 1
        state.last_event_ts = time.monotonic()
        append_jsonl(bundle / "console.jsonl", {
            "ts": utc_now_iso(),
            "type": "pageerror",
            "text": str(err),
            "page_url": page.url,
        })

    def on_request_finished(req):
        try:
            response = req.response()
        except Exception:
            response = None
        state.network_count += 1
        state.last_event_ts = time.monotonic()
        append_jsonl(bundle / "network.jsonl", {
            "ts": utc_now_iso(),
            "method": req.method,
            "url": req.url,
            "resource_type": req.resource_type,
            "status": None,
            "page_url": page.url,
        })

    def on_response(resp):
        state.network_count += 1
        state.last_event_ts = time.monotonic()
        try:
            timing = resp.request.timing or {}
        except Exception:
            timing = {}
        append_jsonl(bundle / "network.jsonl", {
            "ts": utc_now_iso(),
            "kind": "response",
            "method": resp.request.method,
            "url": resp.url,
            "status": resp.status,
            "status_text": resp.status_text,
            "resource_type": resp.request.resource_type,
            "from_cache": resp.from_service_worker if hasattr(resp, "from_service_worker") else None,
            "page_url": page.url,
        })

    def on_request_failed(req):
        state.error_count += 1
        state.last_event_ts = time.monotonic()
        append_jsonl(bundle / "network.jsonl", {
            "ts": utc_now_iso(),
            "kind": "request_failed",
            "method": req.method,
            "url": req.url,
            "failure": req.failure,
            "page_url": page.url,
        })

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("response", on_response)
    page.on("requestfailed", on_request_failed)
    print(f"[daemon] listeners attached to page: {page.url}", flush=True)


async def handle_snap(state: DaemonState):
    bundle = state.bundle
    label_file = bundle / "SNAP_REQUEST"
    label = label_file.read_text().strip() if label_file.exists() else "snap"
    if label_file.exists():
        label_file.unlink()
    if state.context and state.context.pages:
        page = state.context.pages[0]
        path = bundle / f"snap-{label}-{state.frame_count:05d}.png"
        try:
            await page.screenshot(path=str(path))
            print(f"[daemon] snap saved: {path.name}", flush=True)
        except Exception as e:
            print(f"[daemon] snap failed: {e!r}", flush=True)


def extract_frames_from_trace(bundle: Path) -> int:
    """Extract screencast frames from trace.zip into bundle/frames/ +
    write frames.jsonl with monotonic timestamps (normalized so first frame = 0.0).

    Trace events of interest:
      {"type": "screencast-frame",
       "pageId": "page@...", "sha1": "page@...-NNNN.jpeg",
       "timestamp": 565.582,        ← monotonic ms (Playwright's clock)
       "frameSwapWallTime": 1777395487388.947}

    Returns frame count.
    """
    import zipfile
    trace_zip = bundle / "trace.zip"
    if not trace_zip.exists():
        return 0

    frames_dir = bundle / "frames"
    frames_dir.mkdir(exist_ok=True)
    for f in frames_dir.glob("*.jpg"):
        f.unlink()

    fjsonl = bundle / "frames.jsonl"
    if fjsonl.exists():
        fjsonl.unlink()

    events = []
    with zipfile.ZipFile(trace_zip, "r") as z:
        try:
            with z.open("trace.trace") as f:
                for line in f.read().decode().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("type") == "screencast-frame":
                        events.append(ev)
        except KeyError:
            return 0

        if not events:
            return 0

        events.sort(key=lambda e: e.get("timestamp", 0))
        t0 = events[0].get("timestamp", 0)

        zinfo_by_name = {info.filename: info for info in z.infolist()}

        n = 0
        for ev in events:
            sha1 = ev.get("sha1")
            if not sha1:
                continue
            candidates = [
                f"resources/{sha1}",
                f"resources/{sha1}.jpeg",
                f"resources/{sha1}.jpg",
            ]
            zinfo = next((zinfo_by_name[c] for c in candidates if c in zinfo_by_name), None)
            if zinfo is None:
                continue

            n += 1
            with z.open(zinfo) as src:
                (frames_dir / f"{n:05d}.jpg").write_bytes(src.read())

            ts_mono = round((ev.get("timestamp", 0) - t0) / 1000.0, 3)
            append_jsonl(fjsonl, {
                "frame": n,
                "ts_mono": ts_mono,
                "page_id": ev.get("pageId"),
            })

        return n


def _render_pause_frame(prev_frame: Path, out_path: Path, paused_seconds: float):
    """Render a pause-marker frame: dim the previous frame and overlay
    '⏸ Paused for Xs' text. Uses Pillow (homebrew ffmpeg often lacks drawtext).
    """
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance

    if paused_seconds < 60:
        text = f"⏸  Paused for {paused_seconds:.1f}s"
    elif paused_seconds < 3600:
        text = f"⏸  Paused for {paused_seconds/60:.1f} min"
    else:
        text = f"⏸  Paused for {paused_seconds/3600:.1f} h"

    img = Image.open(prev_frame).convert("RGB")
    img = ImageEnhance.Brightness(img).enhance(0.45)
    draw = ImageDraw.Draw(img, "RGBA")

    font = None
    for path, size in [
        ("/System/Library/Fonts/Helvetica.ttc", 48),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", 48),
        ("/System/Library/Fonts/SFNS.ttf", 48),
    ]:
        if Path(path).exists():
            try:
                font = ImageFont.truetype(path, size)
                break
            except (OSError, IOError):
                pass
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    W, H = img.size
    x = (W - tw) // 2
    y = (H - th) // 2 - 20

    pad = 24
    draw.rounded_rectangle(
        [(x - pad, y - pad), (x + tw + pad, y + th + pad)],
        radius=12, fill=(0, 0, 0, 180),
    )
    draw.text((x - bbox[0], y - bbox[1]), text, font=font, fill=(255, 255, 255, 255))

    img.save(out_path, "JPEG", quality=85)


def _prepare_concat_list(bundle: Path, fps: int):
    """Build ffmpeg concat list with per-frame durations honoring real timing
    (capped at MAX_FRAME_GAP_S, floored at MIN_FRAME_GAP_S).

    Returns (concat_path, durations, real_duration_s, pauses_compressed) or None.
    Caller is responsible for unlinking concat_path.
    """
    frames_dir = bundle / "frames"
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        return None

    ts_map = {}
    fjsonl = bundle / "frames.jsonl"
    if fjsonl.exists():
        for line in fjsonl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ts_map[obj["frame"]] = float(obj["ts_mono"])
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
    if not ts_map:
        ts_map = {i + 1: i * (1.0 / fps) for i in range(len(frames))}

    pause_frame_enabled = True
    meta_path = bundle / "meta.json"
    if meta_path.exists():
        try:
            pause_frame_enabled = bool(
                json.loads(meta_path.read_text()).get("pause_frame_enabled", True)
            )
        except json.JSONDecodeError:
            pass

    pause_dir = bundle / "pause_frames"
    pause_dir.mkdir(exist_ok=True)
    for old in pause_dir.glob("*.jpg"):
        old.unlink()

    sequence = []
    pauses_compressed = 0
    real_duration = 0.0
    for i, f in enumerate(frames):
        n = int(f.stem)
        cur_ts = ts_map.get(n, i * (1.0 / fps))
        if i + 1 < len(frames):
            next_n = int(frames[i + 1].stem)
            next_ts = ts_map.get(next_n, (i + 1) * (1.0 / fps))
            real_gap = max(0.0, next_ts - cur_ts)
            real_duration += real_gap
            if real_gap > MAX_FRAME_GAP_S:
                sequence.append((f, MAX_FRAME_GAP_S))
                pauses_compressed += 1
                if pause_frame_enabled:
                    marker = pause_dir / f"pause-{pauses_compressed:03d}.jpg"
                    try:
                        _render_pause_frame(f, marker, real_gap)
                        sequence.append((marker, 1.2))
                    except Exception as e:
                        print(f"[ffmpeg] pause-marker render failed ({e!r}), skipping",
                              flush=True)
            else:
                d = max(real_gap, MIN_FRAME_GAP_S)
                sequence.append((f, d))
        else:
            sequence.append((f, LAST_FRAME_GAP_S))

    concat_path = bundle / "concat.txt"
    lines = []
    for path, d in sequence:
        lines.append(f"file '{path.resolve()}'")
        lines.append(f"duration {d:.3f}")
    lines.append(f"file '{sequence[-1][0].resolve()}'")
    concat_path.write_text("\n".join(lines) + "\n")

    durations = [d for _, d in sequence]
    return concat_path, durations, real_duration, pauses_compressed


def run_ffmpeg_gif(bundle: Path, fps: int) -> dict:
    """Real-timed gif. Long pauses capped at MAX_FRAME_GAP_S."""
    prep = _prepare_concat_list(bundle, fps)
    if prep is None:
        return {"real_duration_s": 0, "gif_duration_s": 0, "pauses_compressed": 0,
                "max_frame_gap_s": MAX_FRAME_GAP_S}
    concat_path, durations, real_duration, pauses_compressed = prep

    gif_path = bundle / "session.gif"
    palette = bundle / "palette.png"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-vf", "scale=900:-1:flags=lanczos,palettegen=stats_mode=full",
            "-update", "1", "-frames:v", "1",
            str(palette),
        ], check=True, capture_output=True)
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-i", str(palette),
            "-lavfi", "scale=900:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5",
            "-loop", "0",
            str(gif_path),
        ], check=True, capture_output=True)
    finally:
        palette.unlink(missing_ok=True)
        concat_path.unlink(missing_ok=True)

    return {
        "real_duration_s": round(real_duration, 2),
        "gif_duration_s": round(sum(durations), 2),
        "pauses_compressed": pauses_compressed,
        "max_frame_gap_s": MAX_FRAME_GAP_S,
    }


def run_ffmpeg_mp4(bundle: Path, fps: int) -> dict:
    """Real-timed h264 MP4. Use this in <video controls> for pause/seek/scrub."""
    prep = _prepare_concat_list(bundle, fps)
    if prep is None:
        return {"ok": False, "reason": "no frames"}
    concat_path, durations, real_duration, pauses_compressed = prep

    mp4_path = bundle / "session.mp4"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-vf", "scale=900:-1:flags=lanczos,pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-vsync", "vfr",
            "-movflags", "+faststart",
            "-preset", "veryfast", "-crf", "23",
            str(mp4_path),
        ], check=True, capture_output=True)
    finally:
        concat_path.unlink(missing_ok=True)

    return {
        "ok": True,
        "playback_duration_s": round(sum(durations), 2),
        "size_bytes": mp4_path.stat().st_size if mp4_path.exists() else 0,
    }



def main():
    p = argparse.ArgumentParser(prog="record.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start")
    sp.add_argument("--name", required=True)
    sp.add_argument("--fps", type=int, default=DEFAULT_FPS)
    sp.add_argument("--force", action="store_true")
    sp.add_argument(
        "--no-pause-frame",
        action="store_true",
        help="Don't insert visual 'Paused for Xs' marker frames between long gaps. "
             "Long gaps are still capped at MAX_FRAME_GAP_S, but the dimmed-overlay "
             "frame is skipped — the cap-frame plays for 5s and then jumps to the next.",
    )
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("stop")
    sp.add_argument("--name")
    sp.add_argument("--no-open", action="store_true")
    sp.add_argument(
        "--no-presentation",
        action="store_true",
        help="Don't push the report to an AW presentation. Default is to upsert a "
             "presentation with id 'recording-<name>' so the recording is visible "
             "in the dashboard sidebar.",
    )
    sp.set_defaults(func=cmd_stop)

    sp = sub.add_parser("snap")
    sp.add_argument("--name")
    sp.add_argument("--label", default="snap")
    sp.set_defaults(func=cmd_snap)

    sp = sub.add_parser("status")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("kill")
    sp.add_argument("--name", required=True)
    sp.set_defaults(func=cmd_kill)

    sp = sub.add_parser("gc")
    sp.add_argument("--older-than", default="7d")
    sp.set_defaults(func=cmd_gc)

    sp = sub.add_parser(
        "gc-presentations",
        help="Delete recording-* presentations from awserv. Default: orphans only "
             "(presentations whose on-disk bundle is gone). Use --all to wipe every "
             "recording presentation regardless of bundle state.",
    )
    sp.add_argument(
        "--all",
        dest="orphans_only",
        action="store_false",
        help="Delete every recording-* presentation, not just orphans. Live daemons "
             "are still skipped to avoid nuking an in-flight recording.",
    )
    sp.add_argument(
        "--older-than",
        default=None,
        help="Optional max age (e.g. 7d, 24h). Presentations whose bundle is newer "
             "than this are kept. Orphan presentations (no bundle) are always eligible.",
    )
    sp.set_defaults(func=cmd_gc_presentations, orphans_only=True)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

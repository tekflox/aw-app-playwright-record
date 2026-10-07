import asyncio
import json
import sys
import types

from playwright_record_app import record


def test_report_renderer_is_package_importable():
    from playwright_record_app.render_report import render_report
    assert callable(render_report)
    assert record.RECORDINGS_DIR.name == "recordings"


def test_daemon_state_initializes_every_lifecycle_field(tmp_path):
    state = record.DaemonState(tmp_path, 12)
    assert state.bundle == tmp_path
    assert state.fps == 12
    assert state.frame_count == state.network_count == state.console_count == state.error_count == 0
    assert state.should_stop is state.snap_requested is False
    assert state.cdp_session is state.context is None
    assert state.tracked_pages == set()
    assert state.start_ts <= state.last_event_ts


def test_daemon_lifecycle_finalizes_complete_artifact_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "lifecycle"
    (bundle / "frames").mkdir(parents=True)
    (bundle / "meta.json").write_text(json.dumps({"name": "lifecycle", "status": "starting"}))
    (bundle / "network.jsonl").write_text("")
    (bundle / "console.jsonl").write_text("")

    class FakeTracing:
        async def start(self, **kwargs):
            self.started = kwargs

        async def stop(self, path):
            (bundle / "trace.zip").write_bytes(b"trace")

    class FakePage:
        url = "https://example.test/"

        def on(self, event, callback):
            return None

    class FakeContext:
        def __init__(self):
            self.pages = [FakePage()]
            self.tracing = FakeTracing()

        def on(self, event, callback):
            return None

    class FakeBrowser:
        def __init__(self):
            self.contexts = [FakeContext()]

        async def close(self):
            return None

    class FakeChromium:
        async def connect_over_cdp(self, endpoint):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        async def stop(self):
            return None

    class FakeManager:
        async def start(self):
            return FakePlaywright()

    fake_async_api = types.ModuleType("playwright.async_api")
    fake_async_api.async_playwright = lambda: FakeManager()
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_async_api)
    monkeypatch.setattr(
        asyncio.unix_events._UnixSelectorEventLoop,
        "add_signal_handler",
        lambda *args: None,
    )
    monkeypatch.setattr(record, "MAX_DURATION_S", -1)

    def extract(_bundle):
        (_bundle / "frames" / "00001.jpg").write_bytes(b"frame")
        (_bundle / "frames.jsonl").write_text('{"frame": 1, "ts_mono": 0.0}\n')
        return 1

    def gif(_bundle, _fps):
        (_bundle / "session.gif").write_bytes(b"gif")
        return {"real_duration_s": 1.0, "gif_duration_s": 1.0,
                "pauses_compressed": 0, "max_frame_gap_s": 5.0}

    def mp4(_bundle, _fps):
        (_bundle / "session.mp4").write_bytes(b"mp4")

    monkeypatch.setattr(record, "extract_frames_from_trace", extract)
    monkeypatch.setattr(record, "run_ffmpeg_gif", gif)
    monkeypatch.setattr(record, "run_ffmpeg_mp4", mp4)

    asyncio.run(record.daemon_main(bundle, 10))

    expected = {"trace.zip", "frames.jsonl", "session.gif", "session.mp4",
                "network.jsonl", "console.jsonl", "report.html", "DONE"}
    assert expected <= {path.name for path in bundle.iterdir()}
    meta = json.loads((bundle / "meta.json").read_text())
    assert meta["status"] == "FINISHED"
    assert meta["frame_count"] == 1

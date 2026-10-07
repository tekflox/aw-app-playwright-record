from playwright_record_app import record


def test_report_renderer_is_package_importable():
    from playwright_record_app.render_report import render_report
    assert callable(render_report)
    assert record.RECORDINGS_DIR.name == "recordings"

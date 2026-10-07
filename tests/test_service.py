import json
from pathlib import Path

import pytest

from playwright_record_app import service


def test_safe_bundle_rejects_traversal():
    with pytest.raises(ValueError):
        service.safe_bundle("../escape")


def test_status_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(service.record, "RECORDINGS_DIR", tmp_path)
    assert service.status() == {"recordings": []}


def test_status_reads_completed_bundle(monkeypatch, tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    (root / "meta.json").write_text(json.dumps({"name": "demo", "status": "FINISHED", "frame_count": 3}))
    monkeypatch.setattr(service.record, "RECORDINGS_DIR", tmp_path)
    rows = service.status()["recordings"]
    assert rows[0]["name"] == "demo"
    assert rows[0]["frames"] == 3

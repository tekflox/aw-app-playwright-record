import json
import re
from pathlib import Path

from playwright_record_app import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_all_version_metadata_is_synchronized():
    manifest_version = json.loads((ROOT / "aw-app.json").read_text())["version"]
    project_version = re.search(
        r'^version = "([^"]+)"$', (ROOT / "pyproject.toml").read_text(), re.MULTILINE
    ).group(1)
    assert manifest_version == project_version == __version__

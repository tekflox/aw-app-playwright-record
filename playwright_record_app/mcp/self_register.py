import json
import os
import socket


def register_self(package_dir: str, port: int) -> None:
    entry = {"type": "http", "url": f"http://{socket.gethostname()}:{port}/api/apps/playwright-record/mcp", "enabled": True}
    key = os.environ.get("AW_WORKSPACE_API_KEY")
    if key:
        entry["headers"] = {"X-Api-Key": key}
    path = os.path.join(package_dir, "mcp.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"mcpServers": {"playwright-record": entry}}, fh, indent=2)
    os.replace(tmp, path)

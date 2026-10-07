import json
import os
from pathlib import Path

from .mcp.self_register import register_self
from .routes import build_routes


class PlaywrightRecordAppPlugin:
    async def activate(self, ctx) -> None:
        manifest = json.loads(Path(ctx.package_dir, "aw-app.json").read_text())
        for cli in manifest.get("contributes", {}).get("system_clis", []):
            ctx.commands.install_system_cli(cli["name"], cli["installer"], uninstall="scripts/uninstall.sh", verify=cli.get("verify"))
        ctx.routes.register(build_routes())
        register_self(ctx.package_dir, int(os.environ.get("AW_PORT", "9030")))

    async def deactivate(self) -> None:
        return None

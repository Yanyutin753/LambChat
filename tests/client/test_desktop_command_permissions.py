"""An app ACL must preserve the existing desktop command surface."""

import json
import tomllib
from pathlib import Path


def test_registered_desktop_commands_respect_window_boundaries():
    root = Path(__file__).resolve().parents[2] / "frontend" / "src-tauri"
    source = (root / "src" / "lib.rs").read_text()
    handler = source.split("tauri::generate_handler![", 1)[1].split("]", 1)[0]
    commands = {entry.strip().split("::")[-1] for entry in handler.split(",") if entry.strip()}
    capability = json.loads((root / "capabilities" / "default.json").read_text())
    toolbar = json.loads((root / "capabilities" / "desktop-control.json").read_text())
    assert toolbar["windows"] == ["cua-control"]
    allowed = set()
    toolbar_allowed = set()
    for path in (root / "permissions").glob("*.toml"):
        for permission in tomllib.loads(path.read_text()).get("permission", []):
            if permission["identifier"] in capability["permissions"]:
                allowed.update(permission.get("commands", {}).get("allow", []))
            if permission["identifier"] in toolbar["permissions"]:
                toolbar_allowed.update(permission.get("commands", {}).get("allow", []))
    control_commands = {"desktop_control_status", "desktop_control_set_paused"}
    assert toolbar_allowed == control_commands
    assert not control_commands & allowed
    assert not commands - allowed - toolbar_allowed, (
        f"Desktop commands denied by app ACL: {sorted(commands - allowed - toolbar_allowed)}"
    )

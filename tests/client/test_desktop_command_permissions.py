"""An app ACL must preserve the existing desktop command surface."""

import json
import tomllib
from pathlib import Path


def test_main_window_can_call_all_registered_desktop_commands():
    root = Path(__file__).resolve().parents[2] / "frontend" / "src-tauri"
    source = (root / "src" / "lib.rs").read_text()
    handler = source.split("tauri::generate_handler![", 1)[1].split("]", 1)[0]
    commands = {entry.strip().split("::")[-1] for entry in handler.split(",") if entry.strip()}
    capability = json.loads((root / "capabilities" / "default.json").read_text())
    allowed = set()
    for path in (root / "permissions").glob("*.toml"):
        for permission in tomllib.loads(path.read_text()).get("permission", []):
            if permission["identifier"] in capability["permissions"]:
                allowed.update(permission.get("commands", {}).get("allow", []))
    assert not commands - allowed, (
        f"Desktop commands denied by app ACL: {sorted(commands - allowed)}"
    )

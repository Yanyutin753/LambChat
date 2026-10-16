import json
import os
import subprocess
import sys


def test_dev_manifest_is_separate_and_pins_downloads(tmp_path):
    for name in (
        "app_x64-setup.exe.sig",
        "app-macOS-Apple-Silicon.app.tar.gz.sig",
        "app-macOS-Intel.app.tar.gz.sig",
    ):
        (tmp_path / name).write_text("signature")
    env = {**os.environ, "RELEASE_TAG": "v2.15.2-dev.3", "ASSET_DIR": str(tmp_path)}
    subprocess.run([sys.executable, "scripts/generate_updater_manifest.py"], env=env, check=True)
    assert not (tmp_path / "latest.json").exists()
    manifest = json.loads((tmp_path / "dev-latest.json").read_text())
    assert manifest["version"] == "2.15.2-dev.3"
    assert len(manifest["platforms"]) == 3
    assert all(
        value["url"].endswith("?tag=v2.15.2-dev.3") for value in manifest["platforms"].values()
    )

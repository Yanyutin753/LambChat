import base64
import json
import os
import subprocess
import sys

import pytest


def signature(version):
    return base64.b64encode(
        f"untrusted comment: test\nAA==\ntrusted comment: timestamp:1\tfile:app\tversion:{version}\nAA==\n".encode()
    ).decode()


def write_signatures(directory, version):
    for name in (
        "app_x64-setup.exe.sig",
        "app-macOS-Apple-Silicon.app.tar.gz.sig",
        "app-macOS-Intel.app.tar.gz.sig",
    ):
        (directory / name).write_text(signature(version))


def generate(directory, tag):
    return subprocess.run(
        [sys.executable, "scripts/generate_updater_manifest.py"],
        env={**os.environ, "RELEASE_TAG": tag, "ASSET_DIR": str(directory)},
        capture_output=True,
        text=True,
    )


def test_dev_manifest_is_separate_and_pins_downloads(tmp_path):
    write_signatures(tmp_path, "2.15.2-dev.3")
    env = {**os.environ, "RELEASE_TAG": "v2.15.2-dev.3", "ASSET_DIR": str(tmp_path)}
    subprocess.run([sys.executable, "scripts/generate_updater_manifest.py"], env=env, check=True)
    assert not (tmp_path / "latest.json").exists()
    manifest = json.loads((tmp_path / "dev-latest.json").read_text())
    assert manifest["version"] == "2.15.2-dev.3"
    assert len(manifest["platforms"]) == 3
    assert all(
        value["url"].endswith("?tag=v2.15.2-dev.3") for value in manifest["platforms"].values()
    )


@pytest.mark.parametrize(
    "platform_file",
    [
        "app_x64-setup.exe.sig",
        "app-macOS-Apple-Silicon.app.tar.gz.sig",
        "app-macOS-Intel.app.tar.gz.sig",
    ],
)
@pytest.mark.parametrize(
    "invalid", [signature("2.15.3"), signature("2.15.3-dev.1"), "signature", ""]
)
def test_dev_manifest_rejects_wrong_or_missing_signed_version(tmp_path, platform_file, invalid):
    write_signatures(tmp_path, "2.15.3-dev.2")
    (tmp_path / platform_file).write_text(invalid)
    result = generate(tmp_path, "v2.15.3-dev.2")
    assert result.returncode != 0
    assert not (tmp_path / "dev-latest.json").exists()


def test_stable_manifest_keeps_legacy_windows_signature_name(tmp_path):
    write_signatures(tmp_path, "2.15.3")
    assert generate(tmp_path, "v2.15.3").returncode == 0
    assert json.loads((tmp_path / "latest.json").read_text())["version"] == "2.15.3"


def test_manifest_prefers_canonical_windows_signature(tmp_path):
    write_signatures(tmp_path, "2.15.3-dev.2")
    (tmp_path / "app_x64-setup.exe.sig").write_text(signature("2.15.3"))
    (tmp_path / "LambChat-v2.15.3-dev.2-Windows-x64-setup.exe.sig").write_text(
        signature("2.15.3-dev.2")
    )
    assert generate(tmp_path, "v2.15.3-dev.2").returncode == 0
    windows = json.loads((tmp_path / "dev-latest.json").read_text())["platforms"]["windows-x86_64"]
    assert windows["signature"] == signature("2.15.3-dev.2")


def test_missing_platform_cannot_create_ready_manifest(tmp_path):
    write_signatures(tmp_path, "2.15.3-dev.2")
    (tmp_path / "app-macOS-Intel.app.tar.gz.sig").unlink()
    assert generate(tmp_path, "v2.15.3-dev.2").returncode != 0
    assert not (tmp_path / "dev-latest.json").exists()


def test_native_verification_and_installation_gate_all_desktop_uploads():
    from pathlib import Path

    import yaml

    workflow = yaml.safe_load(Path(".github/workflows/app-release.yml").read_text())
    steps = workflow["jobs"]["desktop"]["steps"]
    names = [s.get("name") for s in steps]
    signing = names.index("Bind native updater signature to full release version")
    verify = names.index("Verify real native updater signature and version checks")
    upload = names.index("Upload desktop artifacts")
    assert signing < verify < upload
    assert 'signer sign --app-version "${RELEASE_TAG#v}"' in steps[signing]["run"]
    assert "cargo test" in steps[verify]["run"] and "cargo run" in steps[verify]["run"]
    assert steps[verify]["if"] == "matrix.updater_key != ''"
    for name in (
        "Native Windows update installation regression",
        "Native macOS update installation regression",
    ):
        assert verify < names.index(name) < upload

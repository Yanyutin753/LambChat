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


def test_windows_installation_compares_the_verified_installer_payload():
    from pathlib import Path

    script = Path("scripts/test_windows_native_update.ps1").read_text()
    # Tauri patches the NSIS bundle marker, then restores the portable EXE.
    assert "$ExpectedExe" not in script
    assert script.index("& $Verifier $Artifact $Signature $Version") < script.index("& 7z x")
    assert "Get-ChildItem $unpacked -Recurse -Filter lambchat.exe" in script


def test_manual_release_retry_keeps_builds_and_manifest_on_the_original_tag():
    from pathlib import Path

    import yaml

    workflow = yaml.safe_load(Path(".github/workflows/app-release.yml").read_text())
    jobs = workflow["jobs"]
    assert jobs["release_guard"]["outputs"]["source_sha"] == "${{ steps.source.outputs.sha }}"
    guard = next(step for step in jobs["release_guard"]["steps"] if step.get("id") == "source")
    assert 'git merge-base --is-ancestor "$source" origin/main' in guard["run"]
    assert '--commit "$source" --status success' in guard["run"]
    assert "refs/heads/main" in guard["run"]
    for job in ("desktop", "android", "ios", "release"):
        checkout = next(
            step for step in jobs[job]["steps"] if step.get("uses") == "actions/checkout@v4"
        )
        assert checkout["with"]["ref"] == "${{ needs.release_guard.outputs.source_sha }}"
    signing = next(
        step
        for step in jobs["release"]["steps"]
        if step.get("name") == "Sign immutable release assets"
    )
    assert '--commit "$(git rev-parse HEAD)"' in signing["run"]
    windows = next(
        step
        for step in jobs["desktop"]["steps"]
        if step.get("name") == "Native Windows update installation regression"
    )
    assert "?ref=$env:GITHUB_SHA" in windows["run"]
    assert "-ExpectedExe" not in windows["run"]


@pytest.mark.parametrize(
    ("nested_merge", "event", "ref", "allowed"),
    [
        (False, "push", "refs/tags/v9.9.9-dev.1", True),
        (True, "push", "refs/tags/v9.9.9-dev.1", False),
        (False, "workflow_dispatch", "refs/heads/feature", False),
    ],
)
def test_release_guard_rejects_nested_merges_and_unprotected_manual_retries(
    tmp_path, nested_merge, event, ref, allowed
):
    from pathlib import Path

    import yaml

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=release@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                f"core.hooksPath={tmp_path / 'no-hooks'}",
                *args,
            ],
            cwd=tmp_path,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()

    git("init", "--initial-branch=main")
    git("commit", "--allow-empty", "-m", "base")
    git("checkout", "-b", "develop")
    git("checkout", "-b", "feature")
    git("commit", "--allow-empty", "-m", "feature")
    git("checkout", "develop")
    git("commit", "--allow-empty", "-m", "develop")
    git("merge", "--no-ff", "feature", "-m", "nested merge")
    nested = git("rev-parse", "HEAD")
    git("checkout", "main")
    git("merge", "--no-ff", "develop", "-m", "main merge")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("tag", "v9.9.9-dev.1", nested if nested_merge else "HEAD")
    workflow = yaml.safe_load(Path(".github/workflows/app-release.yml").read_text())
    guard = next(s for s in workflow["jobs"]["release_guard"]["steps"] if s.get("id") == "source")
    result = subprocess.run(
        ["bash", "-c", guard["run"].split("gh run list", 1)[0]],
        cwd=tmp_path,
        env={
            **os.environ,
            "GITHUB_EVENT_NAME": event,
            "GITHUB_REF": ref,
            "RELEASE_TAG": "v9.9.9-dev.1",
        },
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is allowed

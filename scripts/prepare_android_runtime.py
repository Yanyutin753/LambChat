#!/usr/bin/env python3
"""Prepare pinned Android assets; run through scripts/run_validation.py (Python 3.12+)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
import os
import posixpath
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "scripts/android-runtime/sources.json"
OUTPUT = ROOT / "frontend/android/app/build/generated/localDevice"


def archive_path(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Unsafe archive path: {name!r}")
    return str(path)


def fetch(url: str, digest: str, cache: Path) -> bytes:
    path = cache / digest
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return path.read_bytes()
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Checksum mismatch: {url}")
    path.write_bytes(data)
    return data


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    files = [
        LOCK,
        Path(__file__).resolve(),
        *sorted((ROOT / "client/lambchat_sandbox").glob("*.py")),
    ]
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def prepare(source: Path | None = None) -> None:
    fingerprint = source_fingerprint()
    lock = json.loads(LOCK.read_text())
    cache = Path.home() / ".cache/lambchat/android-runtime"
    cache.mkdir(parents=True, exist_ok=True)
    assets = OUTPUT / "assets/local-device"
    native = OUTPUT / "jniLibs/arm64-v8a"
    assets.mkdir(parents=True, exist_ok=True)
    native.mkdir(parents=True, exist_ok=True)
    blobs = {}
    for name, digest in lock["files"].items():
        data = (
            (source / name).read_bytes()
            if source
            else fetch(
                f"https://raw.githubusercontent.com/wangzan101/Mika/{lock['mika_commit']}/{name}",
                digest,
                cache,
            )
        )
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Checksum mismatch: {name}")
        blobs[Path(name).name] = data
    for name in ("libproot.so", "libproot_loader.so", "libmikarun.so"):
        (native / name).write_bytes(blobs[name])
    (assets / "packages.json").write_bytes(blobs["packages.json"])
    (assets / "NOTICE.txt").write_bytes((ROOT / "scripts/android-runtime/NOTICE.md").read_bytes())
    manifest = {"links": {}, "executables": []}
    target = assets / "runtime.zip"
    pending = target.with_suffix(".pending")
    with zipfile.ZipFile(pending, "w", zipfile.ZIP_DEFLATED) as output:
        written = set()

        def put(name: str, data: bytes, executable: bool = False) -> None:
            name = archive_path(name)
            if name in written:
                raise ValueError(f"Duplicate runtime member: {name}")
            written.add(name)
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, data)
            if executable:
                manifest["executables"].append(name)

        with tarfile.open(
            fileobj=io.BytesIO(lzma.decompress(blobs["rootfs.tar.xz"])), mode="r:"
        ) as archive:
            for entry in archive:
                name = archive_path(entry.name)
                if entry.isdir():
                    continue
                if entry.issym():
                    dest = entry.linkname
                    resolved = posixpath.normpath(
                        dest.lstrip("/")
                        if dest.startswith("/")
                        else posixpath.join(posixpath.dirname(name), dest)
                    )
                    archive_path(resolved)
                    manifest["links"][name] = posixpath.relpath(
                        resolved, posixpath.dirname(name) or "."
                    )
                elif entry.isfile() or entry.islnk():
                    stream = archive.extractfile(entry)
                    if stream is None:
                        raise ValueError(f"Missing runtime member: {name}")
                    put(name, stream.read(), bool(entry.mode & 0o111))
                else:
                    raise ValueError(f"Unsupported runtime member: {name}")
        # Own dependencies are first on PYTHONPATH, independent of upstream packages.
        for wheel in lock["wheels"]:
            print(f"Preparing Android dependency: {wheel['name']}", flush=True)
            data = fetch(wheel["url"], wheel["sha256"], cache)
            with zipfile.ZipFile(io.BytesIO(data)) as package:
                for member in package.infolist():
                    if not member.is_dir():
                        put("opt/lambchat/" + archive_path(member.filename), package.read(member))
        for path in sorted((ROOT / "client/lambchat_sandbox").glob("*.py")):
            put("opt/lambchat/lambchat_sandbox/" + path.name, path.read_bytes())
        put("lambchat-runtime.json", json.dumps(manifest, sort_keys=True).encode())
    if source_fingerprint() != fingerprint:
        pending.unlink(missing_ok=True)
        raise ValueError("Daemon sources changed during preparation; prepare the runtime again")
    os.replace(pending, target)
    (assets / "runtime.sha256").write_text(hashlib.sha256(target.read_bytes()).hexdigest())
    (assets / "source.sha256").write_text(fingerprint)
    print(f"Android runtime prepared: {target}")


def sources() -> None:
    """Ship corresponding source alongside the APK, including upstream native/runtime sources."""
    lock = json.loads(LOCK.read_text())
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        url = f"https://codeload.github.com/wangzan101/Mika/tar.gz/{lock['mika_commit']}"
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            archive.extractall(work, filter="data")
        upstream = work / f"Mika-{lock['mika_commit']}"
        out = work / "corresponding-source"
        shutil.copytree(upstream, out / "Mika")
        for line in (upstream / "tools/sandbox/sources.lock").read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            name, version, source_url, digest = line.split()
            (out / f"{name}-{version}.tar.gz").write_bytes(fetch(source_url, digest, work))
        subprocess.run(
            [
                os.sys.executable,
                str(upstream / "tools/sandbox/runtime-sources.py"),
                str(out / "runtime"),
            ],
            check=True,
        )
        shutil.copytree(ROOT / "scripts/android-runtime", out / "lambchat-lock")
        OUTPUT.mkdir(parents=True, exist_ok=True)
        with tarfile.open(OUTPUT / "android-runtime-sources.tar.gz", "w:gz") as archive:
            archive.add(out, arcname="android-runtime-sources")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, help="Local Mika checkout; all shipped assets still verified"
    )
    parser.add_argument(
        "--sources",
        action="store_true",
        help="Also assemble corresponding source for APK distribution",
    )
    args = parser.parse_args()
    prepare(args.source)
    if args.sources:
        sources()

#!/usr/bin/env python3
"""Fetch the reviewed native driver and helpers at build time, never at runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]


def install_archive(archive: Path, destination: Path, digest: str) -> None:
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != digest:
        raise ValueError("agent-desktop checksum mismatch")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            if (
                not member.isfile()
                or "/" in member.name
                or "\\" in member.name
                or not member.name.startswith("agent-desktop")
                or member.size > 150 * 1024 * 1024
            ):
                raise ValueError("invalid agent-desktop archive entry")
        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            source = tar.extractfile(member)
            assert source is not None
            target = destination / member.name
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--triple")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--out", type=Path, default=CLIENT / "resources/agent-desktop")
    args = parser.parse_args()
    arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
    suffix = {"Darwin": "apple-darwin", "Linux": "unknown-linux-gnu", "Windows": "pc-windows-msvc"}[
        platform.system()
    ]
    triple = args.triple or f"{arch}-{suffix}"
    lock = json.loads((CLIENT / "agent-desktop.lock.json").read_text())
    digest = lock["assets"][triple]
    with tempfile.TemporaryDirectory(prefix="lambchat-driver-download-") as tmp:
        archive = args.archive or Path(tmp) / "driver.tar.gz"
        if args.archive is None:
            version = lock["version"]
            url = f"https://github.com/{lock['repository']}/releases/download/v{version}/agent-desktop-v{version}-{triple}.tar.gz"
            with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        install_archive(archive, args.out, digest)
    print(f"agent-desktop {lock['version']} {triple}: checksum verified")


if __name__ == "__main__":
    main()

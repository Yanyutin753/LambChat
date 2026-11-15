import hashlib
import io
import runpy
import tarfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["agent-desktop", "../escape", "agent-desktop-macos-helper"])
def test_driver_archive_only_extracts_safe_root_files(tmp_path, name):
    install = runpy.run_path(
        str(Path(__file__).parents[2] / "client/scripts/fetch-agent-desktop.py")
    )["install_archive"]
    archive = tmp_path / "driver.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo(name)
        member.size = 4
        tar.addfile(member, io.BytesIO(b"test"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    dest = tmp_path / "output"
    if name.startswith("../"):
        with pytest.raises(ValueError):
            install(archive, dest, digest)
        assert not (tmp_path / "escape").exists()
    else:
        install(archive, dest, digest)
        assert (dest / name).read_bytes() == b"test"


def test_driver_bad_digest_leaves_existing_binary_untouched(tmp_path):
    install = runpy.run_path(
        str(Path(__file__).parents[2] / "client/scripts/fetch-agent-desktop.py")
    )["install_archive"]
    archive = tmp_path / "driver.tar.gz"
    archive.write_bytes(b"invalid archive")
    dest = tmp_path / "output"
    dest.mkdir()
    (dest / "agent-desktop").write_bytes(b"original")
    with pytest.raises(ValueError, match="checksum"):
        install(archive, dest, "0" * 64)
    assert (dest / "agent-desktop").read_bytes() == b"original"

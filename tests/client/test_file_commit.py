import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from lambchat_sandbox import file_commit


def test_file_version_accepts_different_path_and_descriptor_ctime(tmp_path, monkeypatch):
    target = tmp_path / "existing.txt"
    target.write_bytes(b"existing content")
    original_stat = Path.stat

    def creation_time_stat(path, **kwargs):
        value = original_stat(path, **kwargs)
        if path != target:
            return value
        # Windows stat reports creation time, while fstat reports change time.
        fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
        fields["st_ctime_ns"] -= 1_000_000_000
        return SimpleNamespace(**fields)

    expected = file_commit.file_version(target)
    monkeypatch.setattr(Path, "stat", creation_time_stat)
    assert file_commit.file_version(target) == expected


@pytest.mark.parametrize("change", ["content", "replacement", "ctime"])
def test_file_version_rejects_changes_during_hashing(tmp_path, monkeypatch, change):
    target = tmp_path / "existing.txt"
    target.write_bytes(b"before")
    digest = hashlib.file_digest
    fstat = os.fstat
    changed = False

    def hash_then_change(stream, algorithm):
        nonlocal changed
        result = digest(stream, algorithm)
        if change == "content":
            target.write_bytes(b"after!")
        changed = True
        return result

    def observed_stat(descriptor):
        value = fstat(descriptor)
        if changed and change == "ctime":
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
            fields["st_ctime_ns"] += 1
            return SimpleNamespace(**fields)
        return value

    fdopen = os.fdopen

    @contextmanager
    def close_then_replace(*args, **kwargs):
        with fdopen(*args, **kwargs) as stream:
            yield stream
        if changed and change == "replacement":
            replacement = tmp_path / "replacement.txt"
            replacement.write_bytes(b"before")
            os.replace(replacement, target)

    monkeypatch.setattr(hashlib, "file_digest", hash_then_change)
    monkeypatch.setattr(os, "fstat", observed_stat)
    monkeypatch.setattr(os, "fdopen", close_then_replace)
    with pytest.raises(file_commit.FileCommitError, match="file_conflict"):
        file_commit.file_version(target)

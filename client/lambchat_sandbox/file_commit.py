"""Execution-host file commits. Advisory locks only coordinate participating writers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path


class FileCommitError(Exception):
    pass


def file_version(path: Path) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise FileCommitError("not_a_file")
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())

        def identity(st):
            return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

        # Windows stat().ctime is creation time, but fstat().ctime is change time.
        # Reopen the path to detect replacement using the same metadata API.
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        try:
            current = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if identity(before) != identity(after) or identity(after) != identity(current):
            raise FileCommitError("file_conflict: file changed while reading")
        return hashlib.sha256(f"{identity(after)}:{digest}".encode()).hexdigest()
    except FileNotFoundError:
        return "missing"


@contextmanager
def file_lock(path: Path, state_root: Path):
    """Keep the lock inode stable across commits; never delete the lock file."""
    locks = state_root / "locks"
    locks.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest()
    descriptor = os.open(locks / key, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        try:
            if sys.platform == "win32":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise FileCommitError("file_busy: another file operation is committing") from exc
        yield
    finally:
        if acquired:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def commit_file(
    staged: Path | None,
    destination: Path,
    expected_version: str,
    state_root: Path,
    *,
    actor: dict | None = None,
) -> None:
    """Preserve prior bytes before replacement, rejecting stale or redirected writes."""
    if destination.resolve() != destination or (
        staged is not None and staged.parent.resolve() != destination.parent
    ):
        raise FileCommitError("file_conflict: destination path changed")
    with file_lock(destination, state_root):
        if destination.resolve() != destination or file_version(destination) != expected_version:
            raise FileCommitError("file_conflict: reread the current file before writing")
        if expected_version != "missing" and destination.stat().st_nlink > 1:
            raise FileCommitError(
                "file_conflict: hard-linked destination requires explicit resolution"
            )
        snapshots = state_root / "snapshots"
        snapshots.mkdir(parents=True, exist_ok=True, mode=0o700)
        operation_id = uuid.uuid4().hex
        snapshot = snapshots / f"{operation_id}.blob"
        if expected_version != "missing":
            with destination.open("rb") as source, snapshot.open("xb") as output:
                os.chmod(snapshot, 0o600)
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            if staged is not None:
                staged.chmod(stat.S_IMODE(destination.stat().st_mode))
        result_digest = None
        if staged is not None:
            with staged.open("rb") as stream:
                result_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        # A prepared receipt is retained even if replacement fails; it is not proof of success.
        receipt = {
            "operation_id": operation_id,
            "path": str(destination),
            "expected_version": expected_version,
            "result_digest": result_digest,
            "snapshot": snapshot.name if expected_version != "missing" else None,
            "actor": actor or {},
            "state": "prepared",
        }
        with (snapshots / f"{operation_id}.json").open("x", encoding="utf-8") as output:
            json.dump(receipt, output)
            output.flush()
            os.fsync(output.fileno())
        if destination.resolve() != destination or file_version(destination) != expected_version:
            raise FileCommitError("file_conflict: destination changed during snapshot")
        if staged is None:
            destination.unlink()
        else:
            os.replace(staged, destination)

        receipt["state"] = "committed"
        receipt["result_version"] = file_version(destination)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=snapshots, prefix=".receipt-", delete=False
        ) as output:
            receipt_stage = Path(output.name)
            try:
                json.dump(receipt, output)
                output.flush()
                os.fsync(output.fileno())
            except BaseException:
                output.close()
                receipt_stage.unlink(missing_ok=True)
                raise
        try:
            os.replace(receipt_stage, snapshots / f"{operation_id}.json")
        finally:
            receipt_stage.unlink(missing_ok=True)

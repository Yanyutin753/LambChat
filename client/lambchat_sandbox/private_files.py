"""Owner-only files; permissions must be in place before writing secrets."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

_IS_WINDOWS = os.name == "nt"
_WINDOWS_OWNER_ACL = """
$ErrorActionPreference = 'Stop'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$item = Get-Item -LiteralPath $env:LAMBCHAT_CREDENTIAL_PATH -Force
if ($item.PSIsContainer) {
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity.User, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
} else {
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity.User, 'FullControl', 'Allow')
}
$acl.SetOwner($identity.User)
$acl.SetAccessRuleProtection($true, $false)
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $env:LAMBCHAT_CREDENTIAL_PATH -AclObject $acl
"""


def _restrict_windows_owner(path: Path) -> None:
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_OWNER_ACL],
            env={**os.environ, "LAMBCHAT_CREDENTIAL_PATH": str(path)},
            capture_output=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError("Unable to secure credential file") from exc


def check_private(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise OSError("Private storage must not be a link or special file")
    if _IS_WINDOWS:
        _restrict_windows_owner(path)
    elif info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise OSError("Private storage permissions are unsafe")


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    check_private(path, directory=True)


def write_private_bytes(path: Path, content: bytes) -> None:
    with private_writer(path) as stream:
        stream.write(content)


@contextmanager
def private_writer(path: Path):
    """Commit only a successfully completed stream; protect it before first write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            if _IS_WINDOWS:
                _restrict_windows_owner(Path(temporary))
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def private_lock(path: Path, *, blocking: bool = True):
    """Serialize identity creation across controller and daemon processes."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        check_private(path)
        if _IS_WINDOWS:
            import msvcrt

            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            if _IS_WINDOWS:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)

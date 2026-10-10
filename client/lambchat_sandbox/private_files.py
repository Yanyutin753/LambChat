"""Owner-only files; permissions must be in place before writing secrets."""

from __future__ import annotations

import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

_IS_WINDOWS = os.name == "nt"


def _restrict_windows_owner(path: Path) -> None:
    # Resolve the current process SID locally. Set-Acl can consult an unavailable
    # domain controller even when given a SecurityIdentifier, blocking pairing.
    import ctypes
    from ctypes import WinDLL, WinError, get_last_error, wintypes  # type: ignore[attr-defined]

    advapi = WinDLL("advapi32", use_last_error=True)
    kernel = WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
    token = wintypes.HANDLE()
    sid_text = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise WinError(get_last_error())
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not size.value:
            raise WinError(get_last_error())
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise WinError(get_last_error())
        # TOKEN_USER starts with SID_AND_ATTRIBUTES.Sid (a pointer).
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise WinError(get_last_error())
        owner = ctypes.wstring_at(sid_text)
        inheritance = "OICI" if path.is_dir() else ""
        sddl = f"O:{owner}D:P(A;{inheritance};FA;;;{owner})"
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None
        ):
            raise WinError(get_last_error())
        # OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION |
        # PROTECTED_DACL_SECURITY_INFORMATION: replace inherited/broad ACEs.
        present = wintypes.BOOL()
        defaulted = wintypes.BOOL()
        dacl = ctypes.c_void_p()
        if (
            not advapi.GetSecurityDescriptorDacl(
                descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
            )
            or not present.value
            or not dacl.value
        ):
            raise OSError("Missing private credential DACL")
        # Unlike SetFileSecurity, this propagates inheritable ACE changes to
        # existing children, matching DirectorySecurity/Set-Acl semantics.
        status = advapi.SetNamedSecurityInfoW(str(path), 1, 0x80000005, sid, None, dacl, None)
        if status:
            raise WinError(status)
    except OSError as exc:
        raise OSError(f"Unable to secure credential file: {exc}") from exc
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)
        if sid_text.value:
            kernel.LocalFree(sid_text)
        if token.value:
            kernel.CloseHandle(token)


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

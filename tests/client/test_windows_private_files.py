"""Real Windows ACL regression: no PowerShell or domain account resolution."""

import ctypes
import os
from ctypes import wintypes

import pytest

from lambchat_sandbox import private_files

pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows ACLs")


def _security_sddl(path):
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.GetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    size = wintypes.DWORD()
    advapi.GetFileSecurityW(str(path), 5, None, 0, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    assert advapi.GetFileSecurityW(str(path), 5, buffer, size, ctypes.byref(size))
    text = ctypes.c_void_p()
    assert advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
        buffer, 1, 5, ctypes.byref(text), None
    )
    try:
        return ctypes.wstring_at(text.value)
    finally:
        kernel.LocalFree(text)


def test_private_file_is_owner_only_without_launching_powershell(monkeypatch, tmp_path):
    # Credential writer holds the file open while its ACL is secured.
    path = tmp_path / "pat"

    def no_process(*args, **kwargs):
        pytest.fail("securing credentials must not start PowerShell")

    import subprocess

    monkeypatch.setattr(subprocess, "run", no_process)
    with path.open("wb") as stream:
        private_files._restrict_windows_owner(path)
        stream.write(b"synthetic-credential")
    sddl = _security_sddl(path)
    owner = sddl.split("D:")[0].removeprefix("O:")
    assert sddl.replace("D:PAI", "D:P") == f"O:{owner}D:P(A;;FA;;;{owner})"
    assert path.read_bytes() == b"synthetic-credential"


def test_private_directory_propagates_only_owner_access(tmp_path):
    path = tmp_path / "private"
    path.mkdir()
    existing_child = path / "existing"
    existing_child.write_bytes(b"synthetic")
    private_files.private_directory(path)
    sddl = _security_sddl(path)
    owner = sddl.split("D:")[0].removeprefix("O:")
    assert sddl.replace("D:PAI", "D:P") == f"O:{owner}D:P(A;OICI;FA;;;{owner})"
    assert _security_sddl(existing_child).count("(A;") == 1
    child = path / "child"
    child.write_bytes(b"synthetic")
    assert _security_sddl(child).count("(A;") == 1


def test_private_acl_treats_path_as_data_and_fails_for_missing_target(tmp_path):
    path = tmp_path / "quote'; $(command)"
    path.mkdir()
    credential = path / "pat"
    credential.touch()
    private_files._restrict_windows_owner(credential)
    with pytest.raises(OSError):
        private_files._restrict_windows_owner(path / "missing")

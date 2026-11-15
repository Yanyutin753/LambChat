"""Runtime archive paths must never write outside the installation directory."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "android_runtime", Path(__file__).parents[2] / "scripts/prepare_android_runtime.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape", "a\\b", ""])
def test_archive_path_rejects_escape(name):
    with pytest.raises(ValueError):
        module.archive_path(name)


def test_archive_path_accepts_rootfs_member():
    assert module.archive_path("./usr/bin/python3") == "usr/bin/python3"


def test_fetch_retries_transient_http_failure_but_still_checks_digest(monkeypatch, tmp_path):
    import hashlib
    import io
    import urllib.error

    calls = []

    def open_url(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 503, "temporary unavailable", {}, None)
        return io.BytesIO(b"verified source")

    monkeypatch.setattr(module.urllib.request, "urlopen", open_url)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    data = module.fetch(
        "https://source.invalid/archive", hashlib.sha256(b"verified source").hexdigest(), tmp_path
    )
    assert data == b"verified source"
    assert len(calls) == 2
    with pytest.raises(ValueError, match="Checksum mismatch"):
        module.fetch("https://source.invalid/archive", "0" * 64, tmp_path)
    assert len(calls) == 3


@pytest.mark.parametrize("status,attempts", [(503, 3), (404, 1)])
def test_fetch_has_bounded_retries_and_does_not_retry_missing_source(
    monkeypatch, tmp_path, status, attempts
):
    import urllib.error

    calls = []

    def open_url(url, timeout):
        calls.append(url)
        raise urllib.error.HTTPError(url, status, "unavailable", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", open_url)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    with pytest.raises(urllib.error.HTTPError):
        module.fetch("https://source.invalid/archive", "0" * 64, tmp_path)
    assert len(calls) == attempts

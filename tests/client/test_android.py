"""Android uses the same daemon and approval policy, with a private workspace."""

import pytest

from lambchat_sandbox.android import parse_pairing
from lambchat_sandbox.config import ConfigError


def pairing(**overrides):
    return {
        "serverUrl": "https://chat.example",
        "pat": "pat-test",
        "machineId": "012345abcdef",
        "machineName": "Pixel",
        "confirmPolicy": "all",
        **overrides,
    }


def test_android_pairing_keeps_machine_and_approval_policy():
    cfg, token = parse_pairing(pairing())
    assert cfg.machine_id == "012345abcdef"
    assert cfg.confirm_policy == "all"
    assert str(cfg.data_root) == "/lambchat/workspaces"
    assert cfg.embedded_python is False
    assert token == "pat-test"


@pytest.mark.parametrize(
    "change",
    [
        {"serverUrl": "http://remote.example"},
        {"confirmPolicy": "unknown"},
        {"machineId": "../other"},
        {"pat": "bad\ntoken"},
    ],
)
def test_android_rejects_invalid_pairing(change):
    with pytest.raises((ValueError, ConfigError)):
        parse_pairing(pairing(**change))


def test_android_announces_phone_platform(monkeypatch):
    from lambchat_sandbox.platform import daemon_platform

    monkeypatch.setenv("LAMBCHAT_ANDROID", "1")
    assert daemon_platform() == "android"


def test_android_never_loads_desktop_backend(monkeypatch):
    from lambchat_sandbox import cua_backend

    monkeypatch.setenv("LAMBCHAT_ANDROID", "1")
    monkeypatch.setattr(cua_backend, "_BACKEND", None)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    with pytest.raises(cua_backend.UnsupportedBackendError, match="android"):
        cua_backend.backend()


def test_overlay_activity_tracks_concurrent_calls_without_command_text(tmp_path):
    from lambchat_sandbox.android import ActivityAuditor

    events = []
    audit = ActivityAuditor(tmp_path, events.append)
    audit.log("session", {"event": "allowed", "call_id": "one", "op": "exec", "command": "private"})
    audit.log("session", {"event": "allowed", "call_id": "two", "op": "fs_read"})
    assert events[-1] == {"state": "executing", "active": 2}
    audit.log("session", {"event": "executed", "call_id": "one", "status": "ok"})
    assert events[-1] == {"state": "executing", "active": 1}
    audit.log("session", {"event": "executed", "call_id": "two", "status": "error"})
    assert events[-1] == {"state": "failed", "active": 0}
    assert "private" not in str(events)
    assert "private" in (tmp_path / "session.jsonl").read_text()


def test_overlay_duplicate_terminal_does_not_invent_completion(tmp_path):
    from lambchat_sandbox.android import ActivityAuditor

    events = []
    audit = ActivityAuditor(tmp_path, events.append)
    audit.log("session", {"event": "executed", "call_id": "unknown", "status": "ok"})
    assert events == []

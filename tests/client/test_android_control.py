"""Android control must remain authenticated and fail closed on stale bridges."""

import json

import pytest


def test_android_control_rejects_non_loopback_bridge(tmp_path, monkeypatch):
    from lambchat_sandbox.android_control import request

    config = tmp_path / "phone-bridge.json"
    config.write_text(json.dumps({"host": "example.com", "port": 1234, "token": "a" * 64}))
    monkeypatch.setenv("LAMBCHAT_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="loopback"):
        request("cua_apps", {})


def test_android_control_requires_an_active_private_bridge(tmp_path, monkeypatch):
    from lambchat_sandbox.android_control import handle

    monkeypatch.setenv("LAMBCHAT_HOME", str(tmp_path))
    assert handle("cua_apps", {})["error"] == "phone_control_unavailable"


def test_android_bridge_authenticates_and_preserves_session(tmp_path, monkeypatch):
    import socket
    import threading

    from lambchat_sandbox.android_control import request

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(3)
    received = []

    def respond():
        with listener:
            with listener.accept()[0] as connection:
                connection.settimeout(3)
                received.append(json.loads(connection.makefile("rb").readline()))
                connection.sendall(b'{"platform":"android","apps":[]}\n')

    thread = threading.Thread(target=respond)
    thread.start()
    (tmp_path / "phone-bridge.json").write_text(
        json.dumps({"host": "127.0.0.1", "port": listener.getsockname()[1], "token": "a" * 64})
    )
    monkeypatch.setenv("LAMBCHAT_HOME", str(tmp_path))
    assert request("cua_apps", {"session_id": "selected"}) == {"platform": "android", "apps": []}
    thread.join(4)
    assert not thread.is_alive()
    assert received == [
        {"token": "a" * 64, "op": "cua_apps", "payload": {"session_id": "selected"}}
    ]


def test_android_cua_dispatch_never_uses_desktop_driver(monkeypatch):
    from lambchat_sandbox import android_control, cua_ops

    monkeypatch.setenv("LAMBCHAT_ANDROID", "1")
    monkeypatch.setattr(
        android_control,
        "handle",
        lambda op, payload: {"op": op, "session_id": payload["session_id"]},
    )
    assert cua_ops.handle_cua_op("cua_state", {"session_id": "phone"}) == {
        "op": "cua_state",
        "session_id": "phone",
    }

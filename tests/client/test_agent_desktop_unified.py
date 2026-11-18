"""All desktop operations must use the pinned driver, without native delegation."""

import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from lambchat_sandbox.agent_desktop import AgentDesktopBackend


@pytest.mark.parametrize(
    "flags,state,locked", [(0, 0, True), (1, 0, False), (1, 4, True), (-1, 0, None)]
)
def test_windows_lock_state_uses_session_flags(monkeypatch, flags, state, locked):
    import ctypes
    import struct

    from lambchat_sandbox import agent_desktop

    buffer = ctypes.create_string_buffer(struct.pack("<I4xIIi", 1, 7, state, flags))
    freed = []

    def query(server, session, info_class, output, size):
        assert session == 0xFFFFFFFF and info_class == 25
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(buffer)
        ctypes.cast(size, ctypes.POINTER(ctypes.c_uint32))[0] = len(buffer)
        return True

    class Api:
        WTSQuerySessionInformationW = staticmethod(query)
        WTSFreeMemory = staticmethod(lambda pointer: freed.append(pointer.value))

    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: Api(), raising=False)
    if locked is None:
        with pytest.raises(OSError, match="Unknown Windows session lock state"):
            agent_desktop._windows_desktop_locked()
    else:
        assert agent_desktop._windows_desktop_locked() is locked
    assert freed == [ctypes.addressof(buffer)]


@pytest.fixture
def driver(monkeypatch, tmp_path):
    backend = AgentDesktopBackend(tmp_path / "agent-desktop")
    monkeypatch.setattr(backend, "_enable_cursor", lambda: None)
    return backend


def test_permissions_and_focus_come_from_driver(driver, monkeypatch):
    def call(*args):
        if args[0] == "permissions":
            return {"accessibility": {"state": "granted"}}
        return [{"pid": 7, "is_focused": True}]

    monkeypatch.setattr(driver, "_call", call)
    assert driver.ax_trusted()
    assert driver.frontmost_pid() == 7
    assert not hasattr(driver, "native")


def test_keys_are_bound_to_observed_driver_window(driver, monkeypatch):
    calls = []
    monkeypatch.setattr(driver, "_call", lambda *a, **k: calls.append((a, k)) or {})
    driver.press_chord(["enter"], ["ctrl"], {"driver_window_id": "w-42"})
    assert calls == [(("--headed", "press", "ctrl+return", "--window-id", "w-42"), {})]


def test_coordinate_scroll_is_single_driver_operation(driver, monkeypatch):
    calls = []
    monkeypatch.setattr(driver, "_call", lambda *a, **k: calls.append(a) or {})
    driver.scroll_point(-20, 50, "left", 3)
    assert calls == [("--headed", "mouse-wheel", "--x=-20", "--y=50", "--dx=-3")]


def test_text_uses_fresh_focused_reference_and_stdin(driver, monkeypatch):
    calls = []

    def call(*a, **k):
        calls.append((a, k))
        return (
            {
                "window": {"id": "w-42"},
                "tree": {
                    "ref_id": "@fresh:e0",
                    "role": "window",
                    "children": [{"ref_id": "@fresh:e2", "states": ["focused"], "role": "textbox"}],
                },
            }
            if a[0] == "snapshot"
            else {}
        )

    monkeypatch.setattr(driver, "_call", call)
    driver.type_text("中文\nhello", {"driver_window_id": "w-42"})
    assert calls[-1] == (("--headed", "type", "@fresh:e2", "--stdin"), {"text": "中文\nhello"})
    assert "--window-id" in calls[0][0] and "focused" in calls[0][0]


def test_window_screenshot_crops_using_actual_pixel_scale(driver, monkeypatch):
    data = io.BytesIO()
    Image.new("RGB", (200, 100), "red").save(data, format="PNG")
    calls = []
    monkeypatch.setattr(
        driver,
        "_call",
        lambda *a: (
            calls.append(a)
            or {"data": base64.b64encode(data.getvalue()).decode(), "width": 200, "height": 100}
        ),
    )
    image = driver.screenshot(
        [20, 30, 40, 20], {"driver_window_id": "w-42", "bounds": [10, 20, 100, 50]}
    )
    assert image.size == (80, 40)
    assert calls == [("screenshot", "--window-id", "w-42")]


def test_driver_missing_never_imports_old_platform_backends(monkeypatch):
    from lambchat_sandbox import agent_desktop, cua_backend

    monkeypatch.setattr(cua_backend, "_BACKEND", None)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    monkeypatch.setattr(agent_desktop, "binary_path", lambda: None)
    with pytest.raises(cua_backend.UnsupportedBackendError, match="agent_desktop_missing"):
        cua_backend.backend()
    source = Path(cua_backend.__file__).read_text()
    assert not any(name in source for name in ("cua_mac", "cua_win", "cua_linux"))


def test_minimized_mac_window_does_not_start_expensive_tree_walk(driver, monkeypatch):
    from lambchat_sandbox import cua_backend
    from lambchat_sandbox.cua_ops import CuaOpError

    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "darwin")
    monkeypatch.setattr(
        driver, "_call", lambda *a, **k: pytest.fail("minimized window must not be traversed")
    )
    with pytest.raises(CuaOpError, match="window_minimized"):
        driver.row_of({"_pid": 7, "_window": {"driver_window_id": "w-42", "minimized": True}})


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_minimized_window_preserves_available_driver_observation(driver, monkeypatch, platform):
    from lambchat_sandbox import cua_backend

    monkeypatch.setattr(cua_backend, "backend_platform", lambda: platform)
    calls = []

    def call(*args):
        calls.append(args[0])
        if args[0] == "snapshot":
            return {
                "app": "Editor",
                "window": {"id": "w-42"},
                "tree": {"role": "window", "name": "Editor", "states": ["offscreen"]},
                "complete": True,
            }
        assert args[0] == "list-windows"
        return [{"id": "w-42", "pid": 7}]

    monkeypatch.setattr(driver, "_call", call)
    row = driver.row_of({"_pid": 7, "_window": {"driver_window_id": "w-42", "minimized": True}})
    assert row["title"] == "Editor"
    assert row["states"] == ["offscreen"]
    assert calls == ["snapshot", "list-windows"]


def test_explicit_activate_restores_minimized_window_through_driver(driver, monkeypatch):
    calls = []
    monkeypatch.setattr(
        driver, "pick_window", lambda *a: ({}, {"driver_window_id": "w-42", "minimized": True})
    )
    monkeypatch.setattr(driver, "_call", lambda *a: calls.append(a) or {})
    driver.activate_window(7, 42)
    assert calls == [("restore", "--window-id", "w-42"), ("focus-window", "--window-id", "w-42")]


def test_raw_typing_requires_unique_focused_element(driver, monkeypatch):
    from lambchat_sandbox.cua_ops import CuaOpError

    calls = []
    monkeypatch.setattr(
        driver,
        "_call",
        lambda *a, **k: (
            calls.append(a)
            or {"window": {"id": "w-42"}, "tree": {"ref_id": "@s:e0", "role": "window"}}
        ),
    )
    with pytest.raises(CuaOpError, match="element_unavailable"):
        driver.type_text("private", {"driver_window_id": "w-42"})
    assert len(calls) == 1


@pytest.mark.parametrize("recovers", [True, False])
def test_blank_window_retries_the_same_target_once(driver, monkeypatch, recovers):
    from lambchat_sandbox.cua_ops import CuaOpError

    def frame(color):
        stream = io.BytesIO()
        Image.new("RGB", (80, 60), color).save(stream, format="PNG")
        return {"data": base64.b64encode(stream.getvalue()).decode()}

    frames = iter([frame("black"), frame("red" if recovers else "black")])
    calls = []

    def capture(*args):
        calls.append(args)
        return next(frames)

    monkeypatch.setattr(driver, "_call", capture)
    window = {"driver_window_id": "w-42", "bounds": [0, 0, 80, 60]}
    if recovers:
        assert driver.screenshot(window["bounds"], window).getpixel((30, 30)) == (255, 0, 0)
    else:
        with pytest.raises(CuaOpError, match="window_capture_blank"):
            driver.screenshot(window["bounds"], window)
    assert calls == [("screenshot", "--window-id", "w-42")] * 2

"""cua_ops 单元测试:用假后端驱动平台无关语义(索引/缓存/预算/错误收敛)。

CI(Linux)上不依赖任何平台库——cua_backend 被 monkeypatch 为假实现。
"""

from __future__ import annotations

from typing import Any

import pytest

from lambchat_sandbox import cua_backend, cua_ops


class _FakeElement:
    def __init__(self, kind: str, title: str = "", children: list | None = None):
        self.kind = kind
        self.title = title
        self.children = children or []


class _FakeBackend:
    platform_name = "fake"

    def __init__(self):
        self.performed: list[tuple[Any, str]] = []
        self.set_values: list[tuple[Any, str]] = []
        self.focused: list[Any] = []
        self.activated: list[tuple[int, int | None]] = []
        self.set_value_error: Exception | None = None
        self.window = _FakeElement(
            "AXWindow",
            "Main",
            [_FakeElement("AXButton", "确定"), _FakeElement("AXTextField", "搜索")],
        )

    def ax_trusted(self) -> bool:
        return True

    def frontmost_pid(self) -> int | None:
        return 4242

    def list_apps(self) -> list[dict[str, Any]]:
        return [{"pid": 4242, "name": "Notes"}, {"pid": 100, "name": "Finder"}]

    def windows(self, pid: int) -> list[dict[str, Any]]:
        return [
            {
                "window_id": 0,
                "title": "Main",
                "subrole": "AXStandardWindow",
                "main": True,
                "focused": True,
                "bounds": [10.0, 20.0, 800.0, 600.0],
                "handle": self.window,
            }
        ]

    def pick_window(self, pid: int, window_id: int | None) -> tuple[Any, dict[str, Any]]:
        assert pid == 4242
        if window_id is not None and window_id != 0:
            raise KeyError("window index out of range")
        return self.window, {
            "window_id": 0,
            "title": "Main",
            "bounds": [10.0, 20.0, 800.0, 600.0],
            "focused": True,
        }

    def children(self, element: Any) -> list[Any]:
        return element.children

    def row_of(self, element: Any) -> dict[str, Any]:
        return {
            "kind": element.kind,
            "title": element.title,
            "value": None,
            "actions": ["AXPress"],
            "bounds": [1.0, 2.0, 100.0, 40.0],
        }

    def perform(self, element: Any, action: str) -> None:
        self.performed.append((element, action))

    def set_value(self, element: Any, text: str) -> None:
        if self.set_value_error is not None:
            raise self.set_value_error
        self.set_values.append((element, text))

    def set_focus(self, element: Any) -> None:
        self.focused.append(element)

    def activate_window(self, pid: int, window_id: int | None) -> None:
        self.activated.append((pid, window_id))


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> _FakeBackend:
    fake = _FakeBackend()
    monkeypatch.setattr(cua_backend, "_BACKEND", fake)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "fake")
    cua_ops._OBSERVATIONS.clear()
    return fake


def test_apps_marks_frontmost(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_apps", {})
    by_name = {row["name"]: row for row in result["apps"]}
    assert by_name["Notes"]["active"] is True
    assert by_name["Finder"]["active"] is False


@pytest.mark.parametrize("clicks", [1, 2, 3])
def test_native_coordinate_click_preserves_click_count(fake_backend, monkeypatch, clicks):
    calls = []
    monkeypatch.setattr(
        fake_backend, "click_point", lambda *args: calls.append(args), raising=False
    )
    result = cua_ops.handle_cua_op(
        "cua_click",
        {"pid": 4242, "target": {"x": 30, "y": 40}, "click_count": clicks},
    )
    assert result["ok"]
    assert calls == [(30.0, 40.0, "left")] * clicks


def test_state_walks_tree_and_stores_indices(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert result["element_count"] == 3  # 窗口 + 按钮 + 输入框
    assert "[0] AXWindow 'Main'" in result["state"]
    assert "[1] AXButton '确定'" in result["state"]
    observed = cua_ops._OBSERVATIONS[(None, 4242, 0)]
    assert len(observed.elements) == 3


def test_state_can_observe_a_subtree_and_replaces_its_indices(fake_backend):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_state", {"pid": 4242, "target": {"type": "element", "index": 1}}
    )
    assert result["element_count"] == 1
    assert "[0] AXButton '确定'" in result["state"]
    assert result["subtree"] is True
    assert result["window"]["title"] == "Main"
    cua_ops.handle_cua_op("cua_click", {"pid": 4242, "target": {"type": "element", "index": 0}})
    assert fake_backend.performed[-1][0] is fake_backend.window.children[0]


@pytest.mark.parametrize("index,error", [(0, "stale_state"), (999, "element_unavailable")])
def test_subtree_observation_rejects_missing_or_invalid_prior_index(fake_backend, index, error):
    if index:
        cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_state", {"pid": 4242, "target": {"type": "element", "index": index}}
    )
    assert result["error"] == error


def test_click_element_uses_latest_observation(fake_backend: _FakeBackend) -> None:
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_click", {"pid": 4242, "target": {"type": "element", "index": 1}}
    )
    assert result == {"ok": True, "strategy": "a11y", "action": "click"}
    element, action = fake_backend.performed[0]
    assert element.kind == "AXButton"
    assert action == "click"


def test_acting_without_observation_reports_stale_state(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op(
        "cua_click", {"pid": 4242, "target": {"type": "element", "index": 0}}
    )
    assert result["error"] == "stale_state"


def test_out_of_range_index_fails_closed(fake_backend: _FakeBackend) -> None:
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_click", {"pid": 4242, "target": {"type": "element", "index": 99}}
    )
    assert result["error"] == "element_unavailable"


def test_set_value_passes_text_to_backend(fake_backend: _FakeBackend) -> None:
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_set_value", {"pid": 4242, "target": {"type": "element", "index": 2}, "value": "hello"}
    )
    assert result == {"ok": True}
    assert fake_backend.set_values[0][1] == "hello"


def test_unknown_app_name_reports_not_found(fake_backend: _FakeBackend) -> None:
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op("cua_state", {"name": "不存在的应用"})
    assert result["error"] == "app_not_found"


def test_truncation_when_tree_exceeds_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBackend()
    fake.window = _FakeElement(
        "AXWindow", "Big", [_FakeElement("AXStaticText", f"t{i}") for i in range(500)]
    )
    monkeypatch.setattr(cua_backend, "_BACKEND", fake)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    cua_ops._OBSERVATIONS.clear()
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert result["truncated"] is True
    assert result["element_count"] == cua_ops.STATE_MAX_ELEMENTS


def test_untrusted_ax_converges_to_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Denied(_FakeBackend):
        def ax_trusted(self) -> bool:
            return False

    monkeypatch.setattr(cua_backend, "_BACKEND", _Denied())
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert result["error"] == "ax_not_trusted"


def test_status_without_backend_reports_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cua_backend, "_BACKEND", None)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", "backend_import_failed:nope")
    result = cua_ops.handle_cua_op("cua_status", {})
    assert result["platform"] == "unsupported"
    assert result["ready"] is False


def test_invalid_arguments_for_non_status_actions(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_state", {})
    assert result["error"] == "invalid_arguments"


# ---------------------------------------------------------------------------
# 2026-10-08 生产质量回修:type 免前台路径 / activate / 异常结构化
# ---------------------------------------------------------------------------


def test_type_with_index_writes_value_without_foreground(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """带 index 的 type 走 focus+set_value 免前台——后台窗口也能输入,
    不再一律 foreground_required(生产实测 Windows Edge 地址框即此坑)。"""
    # 前台是别的应用,元素路径仍必须成功
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: 9999)
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op("cua_type", {"pid": 4242, "index": 2, "text": "今日新闻"})
    assert result == {"ok": True, "strategy": "a11y", "method": "set_value"}
    assert fake_backend.set_values[0][1] == "今日新闻"
    assert fake_backend.focused  # 先聚焦过元素


def test_type_without_index_still_requires_foreground(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: 9999)
    result = cua_ops.handle_cua_op("cua_type", {"pid": 4242, "text": "hello"})
    assert result["error"] == "foreground_required"


def test_type_index_unsettable_element_hints_activate(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """元素不可直写且不在前台:报 foreground_required 并指路 activate。"""
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: 9999)
    fake_backend.set_value_error = KeyError("not settable")
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op("cua_type", {"pid": 4242, "index": 1, "text": "x"})
    assert result["error"] == "foreground_required"
    assert "activate" in result["detail"]


def test_activate_routes_to_backend(fake_backend: _FakeBackend) -> None:
    result = cua_ops.handle_cua_op("cua_activate", {"pid": 4242, "window_id": 0})
    assert result == {"ok": True, "pid": 4242}
    assert fake_backend.activated == [(4242, 0)]


def test_unexpected_exception_converges_structured(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """COMError 等三方异常不再裸穿 daemon 层(生产 dispatch_failed 主因)。
    在模型可读层收敛为 op_failed,错误类型与原文都在 detail 里。"""

    def _boom(payload: dict) -> dict:
        raise RuntimeError("COMError: element gone")

    monkeypatch.setitem(cua_ops._CUA_HANDLERS, "cua_apps", _boom)
    result = cua_ops.handle_cua_op("cua_apps", {})
    assert result["error"] == "op_failed"
    assert "RuntimeError" in result["detail"]
    assert "COMError" in result["detail"]


def test_cua_activate_in_ops_registry() -> None:
    assert "cua_activate" in cua_ops.CUA_OPS
    assert "cua_activate" in cua_ops._CUA_HANDLERS


# ---------------------------------------------------------------------------
# 2026-10-08 xiaoxin 真机回修:单键原生合成 / launch 裸名解析
# ---------------------------------------------------------------------------


def test_single_key_prefers_native_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wayland 无 X11 时 pyautogui 不可用;单键(回车等)必须走 AT-SPI
    原生合成——真机实测回车失败逼 agent 绕 URL 导航。"""
    pressed: list[str] = []

    class _NativeBackend(_FakeBackend):
        def press_key(self, key: str) -> None:
            pressed.append(key)

        def press_chord(self, keys, modifiers) -> None:
            raise AssertionError("single keys must not require X11 chords")

    monkeypatch.delenv("DISPLAY", raising=False)
    fake = _NativeBackend()
    monkeypatch.setattr(cua_backend, "_BACKEND", fake)
    monkeypatch.setattr(cua_backend, "_BACKEND_ERROR", None)
    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "fake")
    cua_ops._OBSERVATIONS.clear()

    def _no_pyautogui() -> Any:
        raise AssertionError("native path must not touch pyautogui")

    monkeypatch.setattr(cua_ops, "_pyautogui", _no_pyautogui)
    result = cua_ops.handle_cua_op("cua_key", {"pid": 4242, "text": "return"})
    assert result == {"ok": True, "strategy": "a11y-event", "key": "enter"}
    assert pressed == ["enter"]


def test_chord_key_falls_back_to_pyautogui(fake_backend: _FakeBackend) -> None:
    """修饰键和弦没有原生通道,仍走 pyautogui。"""
    pressed: list[str] = []

    class _FakePyautogui:
        def hotkey(self, *keys: str) -> None:
            pressed.extend(keys)

    import lambchat_sandbox.cua_ops as ops_mod

    original = ops_mod._pyautogui
    ops_mod._pyautogui = lambda: _FakePyautogui()  # type: ignore[assignment]
    try:
        result = cua_ops.handle_cua_op("cua_key", {"pid": 4242, "text": "l", "modifiers": "ctrl"})
    finally:
        ops_mod._pyautogui = original  # type: ignore[assignment]
    assert result == {"ok": True}
    assert "ctrl" in pressed and "l" in pressed


def test_key_chord_text_keeps_modifiers(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    pressed: list[tuple[str, ...]] = []

    class Keyboard:
        def hotkey(self, *keys: str) -> None:
            pressed.append(keys)

        def press(self, key: str) -> None:
            pressed.append((key,))

    monkeypatch.setattr(cua_ops, "_pyautogui", lambda: Keyboard())
    result = cua_ops.handle_cua_op("cua_key", {"pid": 4242, "text": "ctrl+shift+a"})
    assert result == {"ok": True}
    assert pressed == [("ctrl", "shift", "a")]


def test_scroll_targets_the_observed_element(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple] = []

    class Mouse:
        def moveTo(self, x: float, y: float) -> None:  # noqa: N802 - pyautogui API
            events.append(("move", x, y))

        def scroll(self, amount: int) -> None:
            events.append(("scroll", amount))

    monkeypatch.setattr(cua_ops, "_pyautogui", lambda: Mouse())
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_scroll",
        {"pid": 4242, "target": {"type": "element", "index": 1}, "scroll_direction": "down"},
    )
    assert result == {"ok": True, "clicks": 10}
    assert events == [("move", 51.0, 22.0), ("scroll", -10)]


def test_unknown_foreground_refuses_keyboard_injection(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: None)
    result = cua_ops.handle_cua_op("cua_key", {"pid": 4242, "text": "return"})
    assert result["error"] == "foreground_required"


def test_raw_text_pastes_literally_and_restores_clipboard(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    from types import SimpleNamespace

    clipboard = ["original clipboard"]
    pasted: list[str] = []
    pyperclip = SimpleNamespace(
        paste=lambda: clipboard[0], copy=lambda text: clipboard.__setitem__(0, text)
    )

    class Keyboard:
        def typewrite(self, text: str, **kwargs) -> None:
            pasted.append("IME-corrupted")

        def hotkey(self, *keys: str) -> None:
            pasted.append(clipboard[0])

    monkeypatch.setitem(sys.modules, "pyperclip", pyperclip)
    monkeypatch.setattr(cua_ops, "_pyautogui", lambda: Keyboard())
    result = cua_ops.handle_cua_op("cua_type", {"pid": 4242, "text": "hello 中文"})
    assert result["ok"] is True
    assert pasted == ["hello 中文"]
    assert clipboard == ["original clipboard"]


def test_screenshot_denied_preserves_the_accessibility_tree(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_bounds):
        raise cua_ops.CuaOpError("screen_recording_denied", "grant permission")

    monkeypatch.setattr(cua_ops, "_capture", denied)
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "include_screenshot": True})
    assert result["element_count"] == 3
    assert "AXButton" in result["state"]
    assert result["screenshot"] == {
        "error": "screen_recording_denied",
        "detail": "grant permission",
    }


def test_macos_capture_checks_real_screen_recording_permission(
    fake_backend: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    from types import SimpleNamespace

    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "darwin")
    monkeypatch.setitem(
        sys.modules, "Quartz", SimpleNamespace(CGPreflightScreenCaptureAccess=lambda: False)
    )
    with pytest.raises(cua_ops.CuaOpError, match="screen_recording_denied"):
        cua_ops._capture([0, 0, 100, 100])


def test_launch_resolves_bare_name_from_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """裸名 app(firefox)按 PATH 解析,不再直接 launch_failed。"""
    import shutil as shutil_mod

    monkeypatch.setattr(
        shutil_mod, "which", lambda name: f"/usr/bin/{name}" if name == "firefox" else None
    )
    import subprocess as subprocess_mod

    class _FakeProc:
        pid = 4242

    monkeypatch.setattr(subprocess_mod, "Popen", lambda *a, **k: _FakeProc())
    import lambchat_sandbox.cua_backend as cb

    monkeypatch.setattr(cb, "backend_platform", lambda: "linux")
    result = cua_ops.handle_cua_op("cua_launch", {"app": "firefox", "args": ["https://x"]})
    assert result["ok"] is True
    assert result["target"] == "/usr/bin/firefox"
    assert result["launcher_pid"] == 4242
    assert "pid" not in result


def test_type_reads_index_from_tool_target_shape(fake_backend: _FakeBackend) -> None:
    """工具层把 index 放在 target.index(与 click/set_value 同形);daemon
    只读顶层会让元素输入路径在真实链路上静默失效。"""
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    result = cua_ops.handle_cua_op(
        "cua_type",
        {"pid": 4242, "target": {"type": "element", "index": 2}, "text": "hi"},
    )
    assert result["method"] == "set_value"
    assert fake_backend.set_values[0][1] == "hi"


def test_failed_screenshot_probe_is_not_reported_as_ready(fake_backend, monkeypatch):
    def failed(bounds):
        raise cua_ops.CuaOpError("screenshot_failed", "desktop unavailable")

    monkeypatch.setattr(cua_ops, "_capture", failed)
    result = cua_ops.handle_cua_op("cua_status", {"probe_screen": True})
    assert result["ready"] is False
    assert "desktop unavailable" in result["message"]


def test_element_scroll_prefers_native_accessibility_without_foreground(fake_backend, monkeypatch):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    calls = []
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: None)
    monkeypatch.setattr(
        fake_backend, "scroll_element", lambda *args: calls.append(args), raising=False
    )
    result = cua_ops.handle_cua_op(
        "cua_scroll",
        {
            "pid": 4242,
            "target": {"type": "element", "index": 1},
            "scroll_direction": "down",
            "scroll_amount": 2,
        },
    )
    assert result["ok"] and result["strategy"] == "a11y"
    assert calls[0][1:] == ("down", 2)


def test_optional_input_library_exit_becomes_a_structured_error(monkeypatch):
    import builtins

    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "pyautogui":
            raise SystemExit("tkinter missing")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    with pytest.raises(cua_ops.CuaOpError):
        cua_ops._pyautogui()


@pytest.mark.parametrize(
    "bounds",
    [
        None,
        [],
        [0, 0, 0, 100],
        [0, 0, -5, 100],
        [0, 0, float("nan"), 100],
        [0, float("inf"), 100, 100],
        ["0", 0, 100, 100],
    ],
)
def test_capture_rejects_invalid_window_bounds_before_reading_pixels(
    fake_backend, monkeypatch, bounds
):
    def capture(_bounds):
        pytest.fail("invalid bounds must never capture desktop pixels")

    monkeypatch.setattr(fake_backend, "screenshot", capture, raising=False)
    with pytest.raises(cua_ops.CuaOpError, match="screenshot_failed"):
        cua_ops._capture(bounds)


def test_background_state_keeps_tree_but_refuses_screen_region(fake_backend, monkeypatch):
    monkeypatch.setattr(fake_backend, "frontmost_pid", lambda: 100)
    monkeypatch.setattr(
        cua_ops, "_capture", lambda bounds: pytest.fail("background pixels captured")
    )
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "include_screenshot": True})
    assert "AXButton" in result["state"]
    assert result["screenshot"]["error"] == "foreground_required"
    assert result["foreground_pid"] == 100


def test_state_preserves_observation_when_foreground_pid_is_unavailable(fake_backend, monkeypatch):
    def unavailable():
        raise RuntimeError("desktop unavailable")

    monkeypatch.setattr(fake_backend, "frontmost_pid", unavailable)
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    assert "AXButton" in result["state"]
    assert "foreground_pid" not in result


@pytest.mark.parametrize("window_id", [None, 0])
def test_element_indices_resolve_only_the_same_conversation(fake_backend, window_id):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": "chat-a"})
    first = fake_backend.window.children[0]
    fake_backend.window = _FakeElement("AXWindow", "Other", [_FakeElement("AXButton", "Delete")])
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": "chat-b"})
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "session_id": "chat-a",
            "window_id": window_id,
            "target": {"type": "element", "index": 1},
        },
    )
    assert result["ok"] is True
    assert fake_backend.performed == [(first, "click")]


@pytest.mark.parametrize(
    "observed_session,action_session", [(None, "chat-a"), ("chat-a", None), ("chat-a", "chat-b")]
)
def test_other_conversation_or_legacy_observation_cannot_authorize_an_element(
    fake_backend, observed_session, action_session
):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": observed_session})
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "session_id": action_session,
            "target": {"type": "element", "index": 1},
        },
    )
    assert result["error"] == "stale_state"
    assert fake_backend.performed == []


def test_conversation_observation_still_expires(fake_backend, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(cua_ops.time, "monotonic", lambda: clock[0])
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": "chat-a"})
    clock[0] = cua_ops.ELEMENT_CACHE_TTL + 1
    result = cua_ops.handle_cua_op(
        "cua_click",
        {
            "pid": 4242,
            "session_id": "chat-a",
            "target": {"type": "element", "index": 1},
        },
    )
    assert result["error"] == "stale_state"
    assert fake_backend.performed == []


def test_concurrent_daemon_threads_keep_conversation_indices_separate(fake_backend, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local

    thread = local()
    observed = Barrier(2)
    monkeypatch.setattr(
        fake_backend,
        "pick_window",
        lambda pid, wid: (
            thread.window,
            {"window_id": 0, "title": "Main", "bounds": [0, 0, 100, 100]},
        ),
    )

    monkeypatch.setattr(
        fake_backend, "perform", lambda element, action: setattr(thread, "clicked", element)
    )

    def act(session):
        button = _FakeElement("AXButton", session)
        thread.window = _FakeElement("AXWindow", "Main", [button])
        cua_ops.handle_cua_op("cua_state", {"pid": 4242, "session_id": session})
        observed.wait(timeout=5)
        result = cua_ops.handle_cua_op(
            "cua_click",
            {"pid": 4242, "session_id": session, "target": {"type": "element", "index": 1}},
        )
        return result, button, thread.clicked

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(act, ["chat-a", "chat-b"]))
    assert all(result["ok"] and clicked is button for result, button, clicked in results)


@pytest.mark.parametrize(
    "active",
    [
        {"window_id": 1, "bounds": [10.0, 20.0, 800.0, 600.0], "focused": True},
        {"window_id": 0, "bounds": [100.0, 200.0, 800.0, 600.0], "focused": True},
        {"bounds": [10.0, 20.0, 800.0, 600.0], "focused": True},
        None,
    ],
)
def test_same_app_other_or_unknown_active_window_refuses_screenshot(
    fake_backend, monkeypatch, active
):
    requested = {"window_id": 0, "title": "Main", "bounds": [10.0, 20.0, 800.0, 600.0]}

    def pick(pid, window_id):
        if window_id == 0:
            return fake_backend.window, requested
        if active is None:
            raise RuntimeError("cannot determine active window")
        return fake_backend.window, active

    monkeypatch.setattr(fake_backend, "pick_window", pick)
    monkeypatch.setattr(
        cua_ops, "_capture", lambda bounds: pytest.fail("wrong window pixels captured")
    )
    result = cua_ops.handle_cua_op(
        "cua_state",
        {
            "pid": 4242,
            "window_id": 0,
            "include_screenshot": True,
        },
    )
    assert "AXButton" in result["state"]
    assert result["screenshot"]["error"] == "foreground_required"


def test_same_app_active_window_allows_target_region_capture(fake_backend, monkeypatch):
    captures = []
    monkeypatch.setattr(
        cua_ops, "_capture", lambda bounds: captures.append(bounds) or {"mime": "image/jpeg"}
    )
    result = cua_ops.handle_cua_op(
        "cua_state",
        {
            "pid": 4242,
            "window_id": 0,
            "include_screenshot": True,
        },
    )
    assert result["screenshot"] == {"mime": "image/jpeg"}
    assert captures == [[10.0, 20.0, 800.0, 600.0]]


@pytest.mark.parametrize("focused", [False, None])
def test_unknown_or_unfocused_window_never_captures_pixels(fake_backend, monkeypatch, focused):
    info = {"window_id": 0, "title": "Main", "bounds": [0, 0, 100, 100], "focused": focused}
    monkeypatch.setattr(fake_backend, "pick_window", lambda pid, wid: (fake_backend.window, info))
    monkeypatch.setattr(
        cua_ops, "_capture", lambda bounds: pytest.fail("unfocused pixels captured")
    )
    result = cua_ops.handle_cua_op("cua_state", {"pid": 4242, "include_screenshot": True})
    assert result["screenshot"]["error"] == "foreground_required"
    assert "AXButton" in result["state"]


@pytest.mark.parametrize("args", [[], ["--safe-mode", "file with spaces.xlsx"]])
def test_launch_opens_macos_app_bundle(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    import subprocess
    from types import SimpleNamespace

    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 10
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "darwin")
    monkeypatch.setattr(subprocess, "run", run)
    app = "/Applications/Numbers Creator Studio.app"
    result = cua_ops.handle_cua_op("cua_launch", {"app": app, "args": args})
    assert result["ok"] is True
    assert result["target"] == app
    assert calls == [["open", "-a", app, *(["--args", *args] if args else [])]]


@pytest.mark.parametrize("error", ["exit", "timeout"])
def test_launch_macos_bundle_reports_opener_failure(
    monkeypatch: pytest.MonkeyPatch, error: str
) -> None:
    import subprocess

    def run(argv, **kwargs):
        if error == "exit":
            raise subprocess.CalledProcessError(1, argv)
        raise subprocess.TimeoutExpired(argv, 10)

    monkeypatch.setattr(cua_backend, "backend_platform", lambda: "darwin")
    monkeypatch.setattr(subprocess, "run", run)
    result = cua_ops.handle_cua_op("cua_launch", {"app": "/missing/Office.app"})
    assert result["error"] == "launch_failed"


def test_state_omits_empty_layout_nodes_without_renumbering_controls():
    rows = [
        {"kind": "frame", "title": "Calc", "depth": 0},
        {"kind": "filler", "depth": 1},
        {"kind": "panel", "title": "Font Name", "actions": ["press"], "depth": 2},
        {"kind": "panel", "depth": 2},
        {"kind": "text", "value": "中文测试", "depth": 3},
        {"kind": "Pane", "depth": 1},
        {"kind": "Window", "depth": 2},
        {"kind": "Pane", "actions": ["Invoke"], "depth": 2},
    ]
    state = cua_ops._render_tree(rows, {"title": "Calc", "window_id": 0}, False)
    assert "[1] filler" not in state
    assert "[3] panel" not in state
    assert "[2] panel 'Font Name' actions=press" in state
    assert "[4] text value='中文测试'" in state
    assert "[5] Pane" not in state
    assert "[6] Window" not in state
    assert "[7] Pane actions=Invoke" in state


@pytest.mark.parametrize("foreground", [True, False])
def test_click_unactionable_cell_falls_back_only_in_foreground(
    fake_backend, monkeypatch, foreground
):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242})
    fake_backend.frontmost_pid = lambda: 4242 if foreground else 202

    def unsupported(*args):
        raise KeyError("no actions")

    monkeypatch.setattr(fake_backend, "perform", unsupported)
    clicks = []
    fake_backend.click_point = lambda x, y, button: clicks.append((x, y, button))
    payload = {"pid": 4242, "target": {"type": "element", "index": 1}}
    if foreground:
        result = cua_ops.handle_cua_op("cua_click", payload)
        assert result["ok"] is True
        assert clicks == [(51.0, 22.0, "left")]
    else:
        result = cua_ops.handle_cua_op("cua_click", payload)
        assert result["error"] == "foreground_required"
        assert clicks == []


@pytest.mark.parametrize("bounds", [[0, 0, 0, 10], [0, 0, float("nan"), 10]])
def test_element_click_center_rejects_invalid_bounds(fake_backend, monkeypatch, bounds):
    monkeypatch.setattr(fake_backend, "row_of", lambda e: {"bounds": bounds})
    with pytest.raises(cua_ops.CuaOpError, match="element_unavailable"):
        cua_ops._element_center(fake_backend.window)


def test_element_coordinate_fallback_rejects_background_window_of_same_app(
    fake_backend, monkeypatch
):
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "window_id": 0})
    original = fake_backend.pick_window

    def background(pid, window_id):
        element, info = original(pid, window_id)
        return element, {**info, "focused": False}

    def unsupported(*args):
        raise KeyError("no actions")

    monkeypatch.setattr(fake_backend, "pick_window", background)
    monkeypatch.setattr(fake_backend, "perform", unsupported)
    fake_backend.click_point = lambda *args: pytest.fail("background coordinates must not click")
    result = cua_ops.handle_cua_op(
        "cua_click", {"pid": 4242, "window_id": 0, "target": {"type": "element", "index": 1}}
    )
    assert result["error"] == "foreground_required"


def test_state_omits_unnamed_uia_invoke_groups_but_keeps_controls():
    rows = [
        {"depth": 0, "kind": "Group", "actions": ["Invoke"]},
        {"depth": 1, "kind": "Button", "actions": ["Invoke"]},
        {"depth": 1, "kind": "Group", "title": "Document", "actions": ["Invoke"]},
        {"depth": 1, "kind": "Group", "actions": ["Expand"]},
    ]
    state = cua_ops._render_tree(rows, {"title": "WPS", "window_id": 0}, False)
    assert "[0]" not in state
    assert "[1] Button" in state
    assert "[2] Group 'Document'" in state
    assert "[3] Group" in state


@pytest.mark.parametrize("direction,expected", [("down", (False, -1)), ("right", (True, 1))])
def test_fine_scroll_uses_native_wheel_after_positioning(
    fake_backend, monkeypatch, direction, expected
):
    events = []
    mouse = type("Mouse", (), {"moveTo": lambda self, x, y: events.append(("move", x, y))})()
    monkeypatch.setattr(cua_ops, "_pyautogui", lambda: mouse)
    monkeypatch.setattr(
        fake_backend, "scroll_wheel", lambda *args: events.append(args), raising=False
    )
    result = cua_ops.handle_cua_op(
        "cua_scroll",
        {
            "pid": 4242,
            "target": {"type": "coordinate", "x": 100, "y": 200},
            "scroll_direction": direction,
            "scroll_amount": 0.05,
        },
    )
    assert result == {"ok": True, "clicks": 1}
    assert events == [("move", 100.0, 200.0), expected]


def test_scroll_without_target_positions_inside_active_window(fake_backend, monkeypatch):
    events = []
    mouse = type(
        "Mouse",
        (),
        {
            "moveTo": lambda self, x, y: events.append(("move", x, y)),
            "scroll": lambda self, amount: events.append(("scroll", amount)),
        },
    )()
    monkeypatch.setattr(cua_ops, "_pyautogui", lambda: mouse)
    result = cua_ops.handle_cua_op("cua_scroll", {"pid": 4242, "scroll_direction": "down"})
    assert result == {"ok": True, "clicks": 10}
    assert events == [("move", 410.0, 320.0), ("scroll", -10)]


def test_event_scroll_rejects_background_window_of_same_app(fake_backend, monkeypatch):
    original = fake_backend.pick_window
    monkeypatch.setattr(
        fake_backend,
        "pick_window",
        lambda *args: (original(*args)[0], {**original(*args)[1], "focused": False}),
    )
    monkeypatch.setattr(
        cua_ops, "_pyautogui", lambda: pytest.fail("background window must not receive wheel input")
    )
    result = cua_ops.handle_cua_op("cua_scroll", {"pid": 4242, "scroll_direction": "down"})
    assert result["error"] == "foreground_required"


def _two_windows(fake_backend, monkeypatch):
    a = fake_backend.window
    b = _FakeElement("AXWindow", "Other", [_FakeElement("AXButton", "B button")])

    def pick(pid, window_id):
        selected = 0 if window_id is None else window_id
        root = a if selected == 0 else b
        return root, {
            "window_id": selected,
            "title": root.title,
            "bounds": [0, 0, 800, 600],
            "focused": selected == 0,
        }

    monkeypatch.setattr(fake_backend, "pick_window", pick)
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "window_id": 0})
    cua_ops.handle_cua_op("cua_state", {"pid": 4242, "window_id": 1})
    return a, b


def test_subtree_without_window_id_uses_latest_window(fake_backend, monkeypatch):
    _two_windows(fake_backend, monkeypatch)
    result = cua_ops.handle_cua_op(
        "cua_state",
        {"pid": 4242, "target": {"type": "element", "index": 1}, "include_screenshot": True},
    )
    assert result["window"]["window_id"] == 1
    assert "[0] AXButton 'B button'" in result["state"]
    assert result["screenshot"]["error"] == "foreground_required"


@pytest.mark.parametrize("op", ["cua_click", "cua_scroll", "cua_type"])
def test_element_event_fallback_checks_its_observed_window(fake_backend, monkeypatch, op):
    _two_windows(fake_backend, monkeypatch)

    def unsupported(*args):
        raise KeyError("unsupported")

    monkeypatch.setattr(fake_backend, "perform", unsupported)
    monkeypatch.setattr(fake_backend, "set_value", unsupported)

    def unexpected(*args):
        pytest.fail("must reject event input on a background observation")

    monkeypatch.setattr(cua_ops, "_pyautogui", unexpected)
    monkeypatch.setattr(cua_ops, "_type_text", unexpected)
    result = cua_ops.handle_cua_op(
        op,
        {
            "pid": 4242,
            "target": {"type": "element", "index": 1},
            "scroll_direction": "down",
            "text": "X",
        },
    )
    assert result["error"] == "foreground_required"

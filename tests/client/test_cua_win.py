"""cua_win 跨平台单元测试:pywinauto 懒加载后本模块在任意平台可导入,
用假元素/假窗口驱动纯逻辑(语义映射/聚焦/激活/apps 过滤)。

真机行为(UIA 真实枚举、set_focus 真激活)仍靠发版前的 Windows 抽检。
"""

from __future__ import annotations

from typing import Any

import pytest

from lambchat_sandbox import cua_win


@pytest.fixture(autouse=True)
def uia_definitions(monkeypatch):
    import sys
    from types import ModuleType

    class NoPatternInterfaceError(Exception):
        pass

    definitions = ModuleType("pywinauto.uia_defines")
    definitions.NoPatternInterfaceError = NoPatternInterfaceError
    monkeypatch.setitem(sys.modules, "pywinauto.uia_defines", definitions)
    return definitions


class _FakeWinElement:
    def __init__(self, methods: list[str] | None = None, legacy: Any = None, pid: int = 1):
        self.calls: list[str] = []
        self._methods = methods or []
        self.iface_legacy = legacy
        self._pid = pid

    def __getattr__(self, name: str) -> Any:
        # hasattr 探测的方法只有列在 _methods 里的才算存在
        if name.startswith("__"):
            raise AttributeError(name)

        def _call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            return True

        if name in self._methods or name in ("set_focus", "process_id"):
            return _call
        raise AttributeError(name)

    def process_id(self) -> int:
        self.calls.append("process_id")
        return self._pid


class _Legacy:
    def __init__(self) -> None:
        self.default_action_called = False

    def DoDefaultAction(self) -> None:  # noqa: N802 - COM 命名
        self.default_action_called = True


def test_perform_maps_semantic_click_to_invoke() -> None:
    """生产事故回归(2026-10-08):click 语义没映射,Windows 元素点击整体
    KeyError「action click not available on element」。"""
    element = _FakeWinElement(methods=["invoke"])
    cua_win.perform(element, "click")
    assert "invoke" in element.calls


def test_perform_maps_press_and_axpress() -> None:
    element = _FakeWinElement(methods=["invoke"])
    cua_win.perform(element, "press")
    cua_win.perform(element, "AXPress")
    assert element.calls.count("invoke") == 2


def test_perform_falls_back_to_legacy_default_action() -> None:
    legacy = _Legacy()
    element = _FakeWinElement(methods=["select"], legacy=legacy)
    cua_win.perform(element, "click")
    assert legacy.default_action_called


def test_perform_unavailable_raises_key_error() -> None:
    element = _FakeWinElement(methods=["select"])
    with pytest.raises(KeyError):
        cua_win.perform(element, "click")


def test_perform_unsupported_invoke_uses_legacy(uia_definitions):
    legacy = _Legacy()
    element = _FakeWinElement(legacy=legacy)

    def invoke():
        raise uia_definitions.NoPatternInterfaceError()

    element.invoke = invoke
    cua_win.perform(element, "click")
    assert legacy.default_action_called


def test_perform_does_not_hide_action_failure():
    legacy = _Legacy()
    element = _FakeWinElement(legacy=legacy)

    def invoke():
        raise RuntimeError("application failed")

    element.invoke = invoke
    with pytest.raises(RuntimeError, match="application failed"):
        cua_win.perform(element, "click")
    assert not legacy.default_action_called


def test_rows_advertise_only_available_uia_patterns(uia_definitions):
    from types import SimpleNamespace

    class Element(_FakeWinElement):
        element_info = SimpleNamespace(control_type="Button", name="Save")
        iface_selection_item = object()

        @property
        def iface_invoke(self):
            raise uia_definitions.NoPatternInterfaceError()

    element = Element(methods=["invoke", "select", "expand", "toggle"])
    assert cua_win.row_of(element)["actions"] == ["Select"]


def test_set_focus_delegates_to_wrapper() -> None:
    element = _FakeWinElement()
    cua_win.set_focus(element)
    assert "set_focus" in element.calls


def test_activate_window_focuses_pinned_window(monkeypatch: pytest.MonkeyPatch) -> None:
    handles = [_FakeWinElement(pid=7), _FakeWinElement(pid=7)]

    def _fake_windows(pid: int) -> list[dict[str, Any]]:
        assert pid == 7
        return [
            {"window_id": 0, "title": "A", "handle": handles[0]},
            {"window_id": 1, "title": "B", "handle": handles[1]},
        ]

    monkeypatch.setattr(cua_win, "windows", _fake_windows)
    cua_win.activate_window(7, 1)
    assert "set_focus" in handles[1].calls
    assert "set_focus" not in handles[0].calls


def test_activate_window_without_id_picks_main(monkeypatch: pytest.MonkeyPatch) -> None:
    handle = _FakeWinElement(pid=7)
    monkeypatch.setattr(
        cua_win, "windows", lambda pid: [{"window_id": 0, "title": "A", "handle": handle}]
    )
    cua_win.activate_window(7, None)
    assert "set_focus" in handle.calls


def test_activate_window_no_windows_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cua_win, "windows", lambda pid: [])
    with pytest.raises(KeyError):
        cua_win.activate_window(7, None)


def test_list_apps_keeps_only_window_owning_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生产事故回归(2026-10-08):全量 tasklist 数百行系统进程,模型只能
    盲探 pid(连续 6 次 no_windows)。只回持有窗口的 GUI 进程。"""
    monkeypatch.setattr(
        cua_win, "_desktop_windows", lambda: [_FakeWinElement(pid=100), _FakeWinElement(pid=300)]
    )

    class _Tasklist:
        stdout = (
            '"System","4","N/A"\n'
            '"svchost.exe","200","N/A"\n'
            '"msedge.exe","100","N/A"\n'
            '"chrome.exe","300","N/A"\n'
        )

    monkeypatch.setattr("subprocess.run", lambda *a, **k: _Tasklist())
    monkeypatch.setattr(cua_win, "frontmost_pid", lambda: 300)
    rows = cua_win.list_apps()
    assert [r["pid"] for r in rows] == [300, 100]  # 前台优先
    assert all(r["name"] in ("msedge", "chrome") for r in rows)


def test_list_apps_without_gui_windows_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cua_win, "_desktop_windows", lambda: [])
    assert cua_win.list_apps() == []


def test_activate_window_rejects_invalid_pinned_index(monkeypatch):
    handle = _FakeWinElement(pid=7)
    monkeypatch.setattr(
        cua_win, "windows", lambda pid: [{"window_id": 0, "title": "A", "handle": handle}]
    )
    with pytest.raises(KeyError):
        cua_win.activate_window(7, 4)
    assert handle.calls == []


def test_windows_capture_includes_negative_monitor_coordinates(monkeypatch):
    from PIL import Image, ImageGrab

    calls = []
    monkeypatch.setattr(
        ImageGrab, "grab", lambda **kw: calls.append(kw) or Image.new("RGB", (640, 480))
    )
    assert cua_win.screenshot([-1280, 40, 640, 480]).size == (640, 480)
    assert calls == [{"bbox": (-1280, 40, -640, 520), "all_screens": True}]


def test_windows_text_uses_literal_unicode_without_clipboard(monkeypatch):
    import sys
    from types import ModuleType

    keyboard = ModuleType("pywinauto.keyboard")
    calls = []
    keyboard.send_keys = lambda *args, **kw: calls.append((args, kw))
    monkeypatch.setitem(sys.modules, "pywinauto.keyboard", keyboard)
    cua_win.type_text("literal 中文 {ENTER}+^%~()\n")
    assert calls[0][0] == ("literal 中文 {{}ENTER{}}{+}{^}{%}{~}{(}{)}{ENTER}{PAUSE 0.15}",)
    assert calls[0][1]["with_spaces"] and calls[0][1]["with_newlines"]


def test_windows_bulk_text_waits_for_cell_transitions_and_normalizes_crlf(monkeypatch):
    import sys
    from types import ModuleType

    keyboard = ModuleType("pywinauto.keyboard")
    calls = []
    keyboard.send_keys = lambda text, **kwargs: calls.append(text)
    monkeypatch.setitem(sys.modules, "pywinauto.keyboard", keyboard)
    cua_win.type_text("品名\r\n键盘\t3\n显示器")
    assert calls == ["品名{ENTER}{PAUSE 0.15}键盘{TAB}{PAUSE 0.15}3{ENTER}{PAUSE 0.15}显示器"]


def test_windows_text_preserves_supplementary_unicode(monkeypatch):
    import sys
    from types import ModuleType

    keyboard = ModuleType("pywinauto.keyboard")
    calls = []
    keyboard.send_keys = lambda text, **kwargs: calls.append(text)
    monkeypatch.setitem(sys.modules, "pywinauto.keyboard", keyboard)
    cua_win.type_text("😀𠀀")
    assert calls == ["\ud83d\ude00\ud840\udc00"]


@pytest.mark.parametrize("protected", [True, 1, None, -1, "false", 0.0])
def test_windows_protected_or_unknown_field_does_not_read_value(protected):
    from types import SimpleNamespace

    class Element:
        element_info = SimpleNamespace(element=SimpleNamespace(CurrentIsPassword=protected))

        def legacy_properties(self):
            pytest.fail("protected or unknown value must never be read")

    assert cua_win._read_value(Element()) is None


@pytest.mark.parametrize("protected", [False, 0])
def test_regular_windows_field_retains_its_value(protected):
    from types import SimpleNamespace

    element = SimpleNamespace(
        element_info=SimpleNamespace(element=SimpleNamespace(CurrentIsPassword=protected)),
        legacy_properties=lambda: {"value": "ordinary"},
    )
    assert cua_win._read_value(element) == "ordinary"


@pytest.mark.parametrize("state,expected", [(0, "off"), (1, "on"), (2, "mixed"), (3, None)])
@pytest.mark.parametrize("protected", [False, 0])
def test_windows_toggle_controls_report_their_current_state(state, expected, protected):
    from types import SimpleNamespace

    element = SimpleNamespace(
        element_info=SimpleNamespace(
            control_type="CheckBox",
            name="Bold",
            element=SimpleNamespace(CurrentIsPassword=protected),
        ),
        iface_toggle=SimpleNamespace(CurrentToggleState=state),
    )
    row = cua_win.row_of(element)
    assert row["value"] == expected
    assert row["actions"] == ["Toggle"]


@pytest.mark.parametrize("protected", [True, 1, None, -1, "false", 0.0])
def test_windows_toggle_state_respects_protected_or_unknown_controls(protected):
    from types import SimpleNamespace

    class Toggle:
        @property
        def CurrentToggleState(self):  # noqa: N802 - COM property name
            pytest.fail("protected or unknown state must never be read")

    element = SimpleNamespace(
        element_info=SimpleNamespace(element=SimpleNamespace(CurrentIsPassword=protected)),
        iface_toggle=Toggle(),
    )
    assert cua_win.row_of(element)["value"] is None


def test_windows_stale_toggle_state_keeps_the_control_available():
    from types import SimpleNamespace

    class Toggle:
        @property
        def CurrentToggleState(self):  # noqa: N802 - COM property name
            raise OSError("stale provider")

    element = SimpleNamespace(
        element_info=SimpleNamespace(element=SimpleNamespace(CurrentIsPassword=False)),
        iface_toggle=Toggle(),
    )
    row = cua_win.row_of(element)
    assert row["value"] is None
    assert row["actions"] == ["Toggle"]


@pytest.mark.parametrize("foreground", [22, None])
@pytest.mark.parametrize("handle_source", ["wrapper", "element_info"])
def test_windows_selection_uses_native_foreground_handle(monkeypatch, foreground, handle_source):
    import ctypes
    from types import SimpleNamespace

    def get_foreground():
        return foreground

    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(GetForegroundWindow=get_foreground)),
        raising=False,
    )
    rect = SimpleNamespace(left=0, top=0, width=lambda: 100, height=lambda: 100)
    handles = [
        SimpleNamespace(
            process_id=lambda: 7,
            handle=hwnd if handle_source == "wrapper" else None,
            element_info=SimpleNamespace(name=str(hwnd), rectangle=rect, handle=hwnd),
        )
        for hwnd in (11, 22)
    ]
    monkeypatch.setattr(cua_win, "_desktop_windows", lambda: handles)
    element, info = cua_win.pick_window(7, None)
    assert element is handles[1 if foreground else 0]
    assert info["focused"] is (foreground is not None)
    assert get_foreground.restype is ctypes.c_void_p


def test_children_omit_hidden_documents_and_keep_visible_siblings():
    from types import SimpleNamespace

    def unavailable():
        raise RuntimeError("provider disconnected")

    visible = SimpleNamespace(is_visible=lambda: True)
    hidden = SimpleNamespace(is_visible=lambda: False)
    disconnected = SimpleNamespace(is_visible=unavailable)
    parent = SimpleNamespace(children=lambda: [hidden, disconnected, visible])

    assert cua_win.children(parent) == [visible]


@pytest.mark.parametrize("foreground", [None, 11, 22])
@pytest.mark.parametrize("handle_source", ["wrapper", "info"])
def test_desktop_windows_include_active_owned_dialog(monkeypatch, foreground, handle_source):
    import sys
    from types import SimpleNamespace

    main = SimpleNamespace(
        handle=11 if handle_source == "wrapper" else None,
        element_info=SimpleNamespace(handle=11),
    )
    dialog = SimpleNamespace(handle=22)
    requested = []

    def window(*, handle):
        requested.append(handle)
        return SimpleNamespace(wrapper_object=lambda: dialog)

    desktop = SimpleNamespace(windows=lambda: [main], window=window)
    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Desktop=lambda **kwargs: desktop))
    monkeypatch.setattr(cua_win, "_foreground_hwnd", lambda: foreground)

    assert cua_win._desktop_windows() == ([main, dialog] if foreground == 22 else [main])
    assert requested == ([22] if foreground == 22 else [])


def test_unavailable_active_dialog_keeps_discovered_windows(monkeypatch):
    import sys
    from types import SimpleNamespace

    main = SimpleNamespace(handle=11)

    def unavailable(**kwargs):
        raise RuntimeError("secure desktop denied")

    desktop = SimpleNamespace(windows=lambda: [main], window=unavailable)
    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Desktop=lambda **kwargs: desktop))
    monkeypatch.setattr(cua_win, "_foreground_hwnd", lambda: 22)

    assert cua_win._desktop_windows() == [main]


@pytest.mark.parametrize("horizontal,clicks,flag", [(False, -1, 0x0800), (True, 2, 0x1000)])
def test_windows_wheel_uses_native_delta_and_horizontal_axis(monkeypatch, horizontal, clicks, flag):
    import ctypes
    from types import SimpleNamespace

    class MouseEvent:
        def __init__(self):
            self.calls = []

        def __call__(self, *args):
            self.calls.append(args)

    event = MouseEvent()
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda name: SimpleNamespace(mouse_event=event), raising=False
    )
    cua_win.scroll_wheel(horizontal, clicks)
    assert event.calls == [(flag, 0, 0, ctypes.c_uint32(clicks * 120).value, 0)]
    assert event.argtypes[-1] is ctypes.c_size_t


def test_windows_wheel_preserves_shared_pyautogui_mouse_signature(monkeypatch):
    import ctypes
    from types import SimpleNamespace

    shared = SimpleNamespace(argtypes=None, restype=ctypes.c_int)
    isolated = SimpleNamespace()
    monkeypatch.setattr(
        ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(mouse_event=shared)), raising=False
    )
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name: SimpleNamespace(mouse_event=isolated),
        raising=False,
    )
    cua_win.scroll_wheel(False, 0)
    assert shared.argtypes is None
    assert shared.restype is ctypes.c_int


def test_windows_chord_uses_extended_virtual_keys_and_releases_modifiers(monkeypatch):
    import sys
    from types import ModuleType

    keyboard = ModuleType("pywinauto.keyboard")
    keyboard.CODES = {"HOME": 36, "VK_CONTROL": 17}
    events = []

    class Action:
        def __init__(self, key, up=True, down=True):
            self.key, self.up, self.down = key, up, down

        def run(self):
            events.append((self.key, self.up, self.down))
            if self.key == 36:
                raise RuntimeError("input failed")

    keyboard.VirtualKeyAction = Action
    keyboard.parse_keys = lambda text, **kwargs: [Action(36)]
    monkeypatch.setitem(sys.modules, "pywinauto.keyboard", keyboard)
    with pytest.raises(RuntimeError, match="input failed"):
        cua_win.press_chord(["home"], ["ctrl"])
    assert events == [(17, False, True), (36, True, True), (17, True, False)]


def test_windows_chord_parses_literal_letters_and_navigation_aliases(monkeypatch):
    import sys
    from types import ModuleType

    keyboard = ModuleType("pywinauto.keyboard")
    keyboard.CODES = {"PGDN": 34}
    keyboard.VirtualKeyAction = lambda *args, **kwargs: None
    calls = []
    keyboard.parse_keys = lambda text, **kwargs: calls.append((text, kwargs)) or []
    monkeypatch.setitem(sys.modules, "pywinauto.keyboard", keyboard)
    cua_win.press_chord(["a", "pagedown", "+"], [])
    assert calls == [("a{PGDN}{+}", {"vk_packet": False})]


def test_large_windows_scroll_keeps_each_wheel_delta_in_message_range(monkeypatch):
    import ctypes
    from types import SimpleNamespace

    class MouseEvent:
        def __init__(self):
            self.calls = []

        def __call__(self, *args):
            self.calls.append(args)

    event = MouseEvent()
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda name: SimpleNamespace(mouse_event=event), raising=False
    )
    cua_win.scroll_wheel(False, -1000)
    deltas = [ctypes.c_int32(args[3]).value for args in event.calls]
    assert sum(deltas) == -120000
    assert all(-32768 <= delta <= 32767 for delta in deltas)

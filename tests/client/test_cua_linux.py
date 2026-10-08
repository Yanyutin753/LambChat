"""Linux native accessibility and X11 window routing regression tests."""

from types import SimpleNamespace

import pytest

from lambchat_sandbox import cua_linux


def test_x11_activate_uses_matching_process_and_selected_window(monkeypatch):
    monkeypatch.setattr(cua_linux, "pick_window", lambda pid, wid: (None, {"title": "Pinned"}))
    calls = []

    def run(args, **kw):
        calls.append(args)
        return SimpleNamespace(stdout="0x001 0 8 host Other\n0x002 0 7 host Pinned\n", returncode=0)

    monkeypatch.setattr("subprocess.run", run)
    cua_linux.activate_window(7, 1)
    assert calls == [["wmctrl", "-lp"], ["wmctrl", "-ia", "0x002"]]


def test_linux_activate_does_not_guess_another_window(monkeypatch):
    monkeypatch.setattr(cua_linux, "pick_window", lambda pid, wid: (None, {"title": "Missing"}))
    calls = []

    def run(args, **kw):
        calls.append(args)
        return SimpleNamespace(stdout="0x001 0 7 host Other\n", returncode=0)

    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(KeyError):
        cua_linux.activate_window(7, 1)
    assert calls == [["wmctrl", "-lp"]]


def test_linux_scroll_uses_accessible_range_without_global_input(monkeypatch):
    value = SimpleNamespace(minimumValue=0, maximumValue=1000, currentValue=100, minimumIncrement=5)
    bar = SimpleNamespace(
        getRoleName=lambda: "scroll bar",
        queryValue=lambda: value,
        getState=lambda: SimpleNamespace(contains=lambda state: False),
    )
    pane = SimpleNamespace(getRoleName=lambda: "scroll pane")
    monkeypatch.setattr(cua_linux, "children", lambda e: [bar] if e is pane else [])
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_HORIZONTAL=1))
    cua_linux.scroll_element(pane, "down", 1)
    assert value.currentValue == 150
    cua_linux.scroll_element(pane, "up", 1)
    assert value.currentValue == 100


def test_linux_scroll_rejects_a_range_that_ignores_writes(monkeypatch):
    class Value:
        minimumValue = 0  # noqa: N815 - AT-SPI interface
        maximumValue = 1000  # noqa: N815
        minimumIncrement = 5  # noqa: N815

        @property
        def currentValue(self):  # noqa: N802 - AT-SPI interface
            return 100

        @currentValue.setter
        def currentValue(self, value):  # noqa: N802
            pass

    bar = SimpleNamespace(
        getRoleName=lambda: "scroll bar",
        queryValue=Value,
        getState=lambda: SimpleNamespace(contains=lambda state: False),
    )
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_HORIZONTAL=1))
    with pytest.raises(KeyError):
        cua_linux.scroll_element(bar, "down", 1)


def test_linux_capture_uses_x11_without_pyautogui(monkeypatch):
    from PIL import Image, ImageGrab

    calls = []
    monkeypatch.setenv("DISPLAY", ":97")
    monkeypatch.setattr(
        ImageGrab, "grab", lambda **kw: calls.append(kw) or Image.new("RGB", (640, 480))
    )
    assert cua_linux.screenshot([10, 20, 640, 480]).size == (640, 480)
    assert calls == [{"bbox": (10, 20, 650, 500), "xdisplay": ":97"}]


def test_native_chord_releases_pressed_keys_when_injection_fails(monkeypatch):
    import sys
    from types import ModuleType

    xlib = ModuleType("Xlib")
    xlib.XK = SimpleNamespace(string_to_keysym=lambda name: name)
    xlib.display = SimpleNamespace(
        Display=lambda: SimpleNamespace(keysym_to_keycode=lambda sym: sym, close=lambda: None)
    )
    monkeypatch.setitem(sys.modules, "Xlib", xlib)
    calls = []

    def event(code, text, kind):
        calls.append((code, kind))
        if code == "a" and kind == 1:
            raise RuntimeError("injection failed")

    monkeypatch.setattr(
        cua_linux,
        "_pyatspi",
        lambda: SimpleNamespace(
            KEY_PRESS=1, KEY_RELEASE=2, Registry=SimpleNamespace(generateKeyboardEvent=event)
        ),
    )
    with pytest.raises(RuntimeError):
        cua_linux.press_chord(["a"], ["ctrl"])
    assert calls[-2:] == [("a", 2), ("Control_L", 2)]


def test_linux_unicode_typing_replaces_only_the_focused_selection(monkeypatch):
    value = ["keep XXXXX end"]
    written = []
    text = SimpleNamespace(
        getText=lambda a, b: value[0],
        getNSelections=lambda: 1,
        getSelection=lambda n: (5, 10),
        caretOffset=0,
        setCaretOffset=lambda n: written.append(n),
    )

    def replace(content):
        value[0] = content
        return True

    element = SimpleNamespace(
        getState=lambda: SimpleNamespace(contains=lambda state: True),
        queryText=lambda: text,
        queryEditableText=lambda: SimpleNamespace(setTextContents=replace),
    )
    app = SimpleNamespace(
        get_process_id=lambda: 7,
        getState=lambda: SimpleNamespace(contains=lambda state: False),
    )
    desktop = SimpleNamespace(childCount=1, getChildAtIndex=lambda i: app)
    monkeypatch.setattr(cua_linux, "_desktop", lambda: desktop)
    monkeypatch.setattr(cua_linux, "frontmost_pid", lambda: 7)
    monkeypatch.setattr(cua_linux, "children", lambda e: [element] if e is app else [])
    monkeypatch.setattr(
        cua_linux,
        "_pyatspi",
        lambda: SimpleNamespace(
            STATE_FOCUSED=1,
            Registry=SimpleNamespace(
                generateKeyboardEvent=lambda *a: pytest.fail("Unicode must not use KEY_STRING")
            ),
        ),
    )
    cua_linux.type_text("中文 😀𠀀")
    assert value[0] == "keep 中文 😀𠀀 end"
    assert written == [10]


@pytest.mark.parametrize(
    "text,symbol", [("escape", "Escape"), ("delete", "BackSpace"), ("forwarddelete", "Delete")]
)
def test_normalized_special_keys_reach_linux_native_backend(monkeypatch, text, symbol):
    from lambchat_sandbox import cua_ops

    events = []
    monkeypatch.setattr(cua_ops, "_backend", lambda: cua_linux)
    monkeypatch.setattr(cua_ops, "_require_ax", lambda: None)
    monkeypatch.setattr(cua_ops, "_resolve_app_ref", lambda payload: 7)
    monkeypatch.setattr(cua_ops, "_require_foreground", lambda pid: None)
    monkeypatch.setattr(
        cua_linux,
        "_pyatspi",
        lambda: SimpleNamespace(
            KEY_SYM=2,
            Registry=SimpleNamespace(generateKeyboardEvent=lambda *args: events.append(args)),
        ),
    )
    monkeypatch.setattr(cua_ops, "_pyautogui", lambda: pytest.fail("native key must work"))
    cua_ops._op_key({"text": text})
    assert events == [(0, symbol, 2)]

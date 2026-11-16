"""Linux native accessibility and X11 window routing regression tests."""

from types import SimpleNamespace

import pytest

from lambchat_sandbox import cua_linux


def test_desktop_refresh_clears_stale_accessibility_tree(monkeypatch):
    calls = []
    desktop = SimpleNamespace(clear_cache=lambda: calls.append("clear"))
    registry = SimpleNamespace(getDesktop=lambda index: desktop)
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(Registry=registry))
    assert cua_linux._desktop() is desktop
    assert calls == ["clear"]


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


@pytest.fixture
def window_capture(monkeypatch):
    import sys
    from types import ModuleType
    from unittest.mock import MagicMock

    from PIL import ImageGrab

    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(ImageGrab, "grab", lambda **kw: pytest.fail("screen includes toolbar"))
    connection = MagicMock()
    root = connection.screen.return_value.root
    root.id = 1
    root.get_full_property.return_value.value = [42]
    root.translate_coords.return_value = SimpleNamespace(x=10, y=20)
    window = connection.create_resource_object.return_value
    window.id = 42
    window.get_geometry.return_value = SimpleNamespace(width=2, height=2, border_width=0, depth=24)
    window.get_attributes.return_value = SimpleNamespace(visual=3)
    pixmap = window.composite_name_window_pixmap.return_value
    pixmap.get_image.return_value = SimpleNamespace(data=bytes([0, 0, 255, 0]) * 4)
    connection.has_extension.return_value = True
    connection.display.info = SimpleNamespace(
        image_byte_order=0,
        pixmap_formats=[SimpleNamespace(depth=24, bits_per_pixel=32, scanline_pad=32)],
    )
    connection.screen.return_value.allowed_depths = [
        SimpleNamespace(
            visuals=[
                SimpleNamespace(visual_id=3, red_mask=0xFF0000, green_mask=0xFF00, blue_mask=0xFF)
            ]
        )
    ]
    xlib = ModuleType("Xlib")
    xlib.X = SimpleNamespace(AnyPropertyType=0, ZPixmap=2, LSBFirst=0)
    xlib.display = SimpleNamespace(Display=lambda: connection)
    extension = ModuleType("Xlib.ext")
    extension.composite = SimpleNamespace(RedirectAutomatic=0)
    monkeypatch.setitem(sys.modules, "Xlib", xlib)
    monkeypatch.setitem(sys.modules, "Xlib.ext", extension)
    return connection, pixmap


def test_linux_capture_reads_window_pixmap_not_overlaid_screen(window_capture):
    connection, pixmap = window_capture
    image = cua_linux.screenshot([10, 20, 2, 2])
    assert image.size == (2, 2)
    assert image.getpixel((1, 1)) == (255, 0, 0)
    pixmap.free.assert_called_once()
    connection.close.assert_called_once()


def test_linux_capture_creates_backing_store_when_desktop_has_no_compositor(window_capture):
    from unittest.mock import MagicMock

    connection, pixmap = window_capture
    window = connection.create_resource_object.return_value
    invalid = MagicMock()
    calls = 0

    def name_pixmap(onerror=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            if onerror:
                onerror(SimpleNamespace(code=8), None)
            return invalid
        return pixmap

    window.composite_name_window_pixmap.side_effect = name_pixmap
    image = cua_linux.screenshot([10, 20, 2, 2])
    assert image.getpixel((1, 1)) == (255, 0, 0)
    window.composite_redirect_window.assert_called_once()
    invalid.free.assert_called_once()
    pixmap.free.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("failure", ["window_gone", "redirect_denied", "still_unavailable"])
def test_linux_capture_does_not_return_pixels_when_backing_store_recovery_fails(
    window_capture, failure
):
    connection, pixmap = window_capture
    window = connection.create_resource_object.return_value

    def unavailable(onerror=None):
        onerror(SimpleNamespace(code=3 if failure == "window_gone" else 8), None)
        return pixmap

    window.composite_name_window_pixmap.side_effect = unavailable
    if failure == "redirect_denied":
        window.composite_redirect_window.side_effect = lambda _, onerror: onerror(
            SimpleNamespace(code=10), None
        )
    with pytest.raises(RuntimeError, match="unavailable"):
        cua_linux.screenshot([10, 20, 2, 2])
    pixmap.get_image.assert_not_called()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "failure", ["no_composite", "outside_window", "focus_changed", "pixel_read"]
)
def test_linux_capture_fails_closed_and_releases_resources(window_capture, failure):
    connection, pixmap = window_capture
    root = connection.screen.return_value.root
    window = connection.create_resource_object.return_value
    if failure == "no_composite":
        connection.has_extension.return_value = False
    elif failure == "outside_window":
        window.get_geometry.return_value.width = 1
        window.query_tree.return_value.parent = root
    elif failure == "focus_changed":
        root.get_full_property.side_effect = [
            SimpleNamespace(value=[42]),
            SimpleNamespace(value=[99]),
        ]
    else:
        pixmap.get_image.side_effect = RuntimeError("native capture failed")
    with pytest.raises(RuntimeError):
        cua_linux.screenshot([10, 20, 2, 2])
    connection.close.assert_called_once()
    if failure in {"focus_changed", "pixel_read"}:
        pixmap.free.assert_called_once()


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
        clear_cache=lambda: None,
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
            STATE_SHOWING=2,
            Registry=SimpleNamespace(
                generateKeyboardEvent=lambda *a: pytest.fail("Unicode must not use KEY_STRING")
            ),
        ),
    )
    cua_linux.type_text("中文 😀𠀀")
    assert value[0] == "keep 中文 😀𠀀 end"
    assert written == [10]


@pytest.mark.parametrize(
    "text,symbol,keyval",
    [
        ("escape", "Escape", 0xFF1B),
        ("delete", "BackSpace", 0xFF08),
        ("forwarddelete", "Delete", 0xFFFF),
        ("f2", "F2", 0xFFBF),
        ("enter", "Return", 0xFF0D),
    ],
)
def test_normalized_special_keys_reach_linux_native_backend(monkeypatch, text, symbol, keyval):
    import sys
    from types import ModuleType

    from lambchat_sandbox import cua_ops

    xlib = ModuleType("Xlib")

    def string_to_keysym(name):
        assert name == symbol
        return keyval

    xlib.XK = SimpleNamespace(string_to_keysym=string_to_keysym)
    monkeypatch.setitem(sys.modules, "Xlib", xlib)
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
    assert events == [(keyval, "", 2)]


def test_linux_password_field_does_not_read_text(monkeypatch):
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(ROLE_PASSWORD_TEXT=77))

    class Element:
        def getRole(self):  # noqa: N802 - Native AT-SPI interface.
            return 77

        def queryText(self):  # noqa: N802 - Native AT-SPI interface.
            pytest.fail("password text must never be read")

    assert cua_linux._text_value(Element()) is None


def test_regular_linux_field_retains_its_value(monkeypatch):
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(ROLE_PASSWORD_TEXT=77))
    element = SimpleNamespace(
        getRole=lambda: 1,
        queryText=lambda: SimpleNamespace(characterCount=8, getText=lambda a, b: "ordinary"),
    )
    assert cua_linux._text_value(element) == "ordinary"


@pytest.mark.parametrize("active", [True, None])
def test_linux_selection_uses_native_active_state(monkeypatch, active):
    def state(index):
        if active is None:
            raise RuntimeError("focus unavailable")
        return SimpleNamespace(contains=lambda flag: flag == 77 and index == 1)

    handles = [
        SimpleNamespace(
            name=str(i),
            clear_cache=lambda: None,
            getRoleName=lambda: "frame",
            getState=lambda i=i: state(i),
            get_extents=lambda coord: SimpleNamespace(x=0, y=0, width=100, height=100),
        )
        for i in range(2)
    ]
    app = SimpleNamespace(
        clear_cache=lambda: None,
        get_process_id=lambda: 7,
        childCount=2,
        getChildAtIndex=lambda i: handles[i],
    )
    monkeypatch.setattr(
        cua_linux, "_desktop", lambda: SimpleNamespace(childCount=1, getChildAtIndex=lambda i: app)
    )
    monkeypatch.setattr(
        cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_ACTIVE=77, DESKTOP_COORDS=0)
    )
    element, info = cua_linux.pick_window(7, None)
    assert element is handles[1 if active else 0]
    assert info["focused"] is (active is not None)


def test_unicode_typing_ignores_hidden_menu_items(monkeypatch):
    written = []
    focused = SimpleNamespace(
        clear_cache=lambda: None,
        getState=lambda: SimpleNamespace(contains=lambda state: True),
        queryText=lambda: SimpleNamespace(
            getText=lambda a, b: written[-1] if written else "",
            getNSelections=lambda: 0,
            caretOffset=0,
            setCaretOffset=lambda n: None,
        ),
        queryEditableText=lambda: SimpleNamespace(
            insertText=lambda position, text, length: written.append(text) or True
        ),
    )
    hidden = SimpleNamespace(getState=lambda: SimpleNamespace(contains=lambda state: False))
    app = SimpleNamespace(
        get_process_id=lambda: 7, getState=lambda: SimpleNamespace(contains=lambda state: False)
    )
    monkeypatch.setattr(
        cua_linux, "_desktop", lambda: SimpleNamespace(childCount=1, getChildAtIndex=lambda i: app)
    )
    monkeypatch.setattr(cua_linux, "frontmost_pid", lambda: 7)
    monkeypatch.setattr(
        cua_linux, "children", lambda e: [hidden] * 450 + [focused] if e is app else []
    )
    monkeypatch.setattr(
        cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_FOCUSED=1, STATE_SHOWING=2)
    )
    cua_linux.type_text("中文办公")
    assert written == ["中文办公"]


def test_linux_children_bounds_large_spreadsheet_nodes(monkeypatch):
    calls = []
    children = [
        SimpleNamespace(getState=lambda: SimpleNamespace(contains=lambda state: True))
        for _ in range(400)
    ]
    element = SimpleNamespace(
        childCount=1_000_000, getChildAtIndex=lambda i: calls.append(i) or children[i]
    )
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_SHOWING=2))
    assert cua_linux.children(element) == children
    assert len(calls) == 400


def test_linux_tree_excludes_hidden_controls(monkeypatch):
    visible = SimpleNamespace(getState=lambda: SimpleNamespace(contains=lambda state: True))
    hidden = SimpleNamespace(getState=lambda: SimpleNamespace(contains=lambda state: False))
    element = SimpleNamespace(childCount=2, getChildAtIndex=lambda i: [hidden, visible][i])
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_SHOWING=2))
    assert cua_linux.children(element) == [visible]


def test_linux_typing_inserts_utf8_at_caret_without_replacing_editor_buffer(monkeypatch):
    value = ["keep  end"]
    calls = []
    text = SimpleNamespace(
        getText=lambda a, b: value[0],
        getNSelections=lambda: 0,
        caretOffset=5,
        setCaretOffset=lambda offset: calls.append(("caret", offset)),
    )

    def insert(position, content, length):
        calls.append((position, content, length))
        value[0] = value[0][:position] + content + value[0][position:]
        return True

    element = SimpleNamespace(
        getState=lambda: SimpleNamespace(contains=lambda state: True),
        queryText=lambda: text,
        clear_cache=lambda: None,
        queryEditableText=lambda: SimpleNamespace(
            insertText=insert,
            setTextContents=lambda content: pytest.fail("typing must preserve editor buffer"),
        ),
    )
    desktop = SimpleNamespace(childCount=1, getChildAtIndex=lambda i: element)
    element.get_process_id = lambda: 7
    monkeypatch.setattr(cua_linux, "_desktop", lambda: desktop)
    monkeypatch.setattr(cua_linux, "frontmost_pid", lambda: 7)
    monkeypatch.setattr(cua_linux, "children", lambda e: [])
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_FOCUSED=1))
    cua_linux.type_text("中文 😀")
    assert value[0] == "keep 中文 😀 end"
    assert calls == [(5, "中文 😀", 11), ("caret", 9)]


def test_linux_set_value_rejects_provider_that_reports_success_without_editing():
    element = SimpleNamespace(
        clear_cache=lambda: None,
        queryEditableText=lambda: SimpleNamespace(setTextContents=lambda text: True),
        queryText=lambda: SimpleNamespace(characterCount=0, getText=lambda a, b: ""),
    )
    with pytest.raises(KeyError, match="did not change"):
        cua_linux.set_value(element, "中文测试")


@pytest.mark.parametrize("content", ["中文 😀", "=B1*2", "LambChat CUA"])
def test_linux_typing_uses_x11_unicode_without_clipboard(monkeypatch, content):
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr(cua_linux, "_desktop", lambda: SimpleNamespace(childCount=0))
    monkeypatch.setattr(cua_linux, "frontmost_pid", lambda: 7)
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace())
    calls = []
    monkeypatch.setattr(cua_linux, "_type_x11_text", calls.append, raising=False)
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("keyboard text must not synthesize Shift")
    )
    cua_linux.type_text(content)
    assert calls == [content]


def test_linux_unicode_keyboard_fallback_does_not_guess_wayland_support(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(cua_linux, "_desktop", lambda: SimpleNamespace(childCount=0))
    monkeypatch.setattr(cua_linux, "frontmost_pid", lambda: 7)
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace())
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("no X11 fallback on Wayland"))
    with pytest.raises(KeyError, match="focused editable"):
        cua_linux.type_text("中文")


@pytest.mark.parametrize("role", ["dialog", "file chooser"])
def test_linux_windows_refreshes_app_cache_to_discover_save_dialog(monkeypatch, role):
    class App:
        childCount = 1  # noqa: N815 - Native interface.

        def clear_cache(self):
            self.childCount = 2

        def get_process_id(self):
            return 7

        def getChildAtIndex(self, index):  # noqa: N802
            return windows[index]

    windows = [
        SimpleNamespace(
            name=title,
            clear_cache=lambda: None,
            getRoleName=lambda: role,
            getState=lambda active=active: SimpleNamespace(contains=lambda state: active),
        )
        for title, active in [("Calc", False), ("Save", True)]
    ]
    app = App()
    monkeypatch.setattr(
        cua_linux, "_desktop", lambda: SimpleNamespace(childCount=1, getChildAtIndex=lambda i: app)
    )
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_ACTIVE=1))
    monkeypatch.setattr(cua_linux, "_extents", lambda e: [0, 0, 100, 100])
    rows = cua_linux.windows(7)
    assert [row["title"] for row in rows] == ["Calc", "Save"]
    assert rows[1]["focused"] is True


def test_linux_children_refreshes_visibility_after_menu_opens(monkeypatch):
    showing = [False]
    child = SimpleNamespace(
        clear_cache=lambda: showing.__setitem__(0, True),
        getState=lambda: SimpleNamespace(contains=lambda state: showing[0]),
    )
    parent = SimpleNamespace(
        clear_cache=lambda: None, childCount=1, getChildAtIndex=lambda i: child
    )
    monkeypatch.setattr(cua_linux, "_pyatspi", lambda: SimpleNamespace(STATE_SHOWING=1))
    assert cua_linux.children(parent) == [child]


@pytest.mark.parametrize("fail", [False, True])
def test_x11_unicode_keys_restore_mapping_even_when_injection_fails(monkeypatch, fail):
    import sys
    from types import ModuleType

    mapping = {code: (0, 0) for code in range(10, 15)}
    events = []
    closed = []

    def change(code, rows):
        mapping[code] = tuple(rows[0])

    connection = SimpleNamespace(
        display=SimpleNamespace(info=SimpleNamespace(min_keycode=10, max_keycode=14)),
        get_keyboard_mapping=lambda start, count: list(mapping.values()),
        get_modifier_mapping=lambda: [[13]],
        change_keyboard_mapping=change,
        sync=lambda: None,
        close=lambda: closed.append(True),
    )

    def inject(conn, kind, code):
        assert conn is connection
        events.append((kind, code, mapping[code][0]))
        if fail and kind == 2 and code == 12:
            raise RuntimeError("input failed")

    xlib = ModuleType("Xlib")
    xlib.X = SimpleNamespace(KeyPress=2, KeyRelease=3)
    xlib.display = SimpleNamespace(Display=lambda: connection)
    extension = ModuleType("Xlib.ext")
    extension.xtest = SimpleNamespace(fake_input=inject)
    monkeypatch.setitem(sys.modules, "Xlib", xlib)
    monkeypatch.setitem(sys.modules, "Xlib.ext", extension)
    monkeypatch.setattr("time.sleep", lambda duration: None)
    if fail:
        with pytest.raises(RuntimeError, match="input failed"):
            cua_linux._type_x11_text("Aa中\n")
    else:
        cua_linux._type_x11_text("Aa中\n")
        assert [symbol for kind, code, symbol in events if kind == 2] == [
            0x01000041,
            0x01000061,
            0x01004E2D,
            0xFF0D,
        ]
        assert all(code != 13 for kind, code, symbol in events)
    assert mapping == {code: (0, 0) for code in range(10, 15)}
    assert closed == [True]


@pytest.mark.parametrize(
    "case", ["unique", "framed", "duplicate", "wrong_active", "hidden", "changed"]
)
def test_foreground_window_requires_unique_viewable_native_identity(window_capture, case):
    import sys
    from unittest.mock import MagicMock

    connection, _ = window_capture
    sys.modules["Xlib"].X.IsViewable = 2
    connection.intern_atom.side_effect = lambda name: name
    root = connection.screen.return_value.root
    reads = 0

    def prop(atom, kind):
        nonlocal reads
        if atom == "_NET_CLIENT_LIST":
            return SimpleNamespace(value=[42, 43] if case == "duplicate" else [42])
        reads += 1
        return SimpleNamespace(
            value=[99 if case == "wrong_active" or (case == "changed" and reads > 1) else 42]
        )

    root.get_full_property.side_effect = prop
    windows = {}
    for xid in [42, 43]:
        window = MagicMock()
        window.get_full_property.return_value = SimpleNamespace(value=[7])
        window.get_attributes.return_value = SimpleNamespace(map_state=0 if case == "hidden" else 2)
        window.get_geometry.return_value = SimpleNamespace(width=800, height=600)
        window.query_tree.return_value.parent = root
        windows[xid] = window
    if case == "framed":
        frame = MagicMock()
        frame.id = 50
        frame.get_geometry.return_value = SimpleNamespace(width=802, height=627)
        frame.query_tree.return_value.parent = root
        windows[42].query_tree.return_value.parent = frame
        root.translate_coords.side_effect = lambda window, x, y: (
            SimpleNamespace(x=9, y=-6) if window is frame else SimpleNamespace(x=10, y=20)
        )
    connection.create_resource_object.side_effect = lambda kind, xid: windows[xid]
    result = cua_linux.foreground_window()
    expected = {"pid": 7, "bounds": [10, 20, 800, 600]} if case in ("unique", "framed") else None
    if case == "framed":
        expected["frame_bounds"] = [9, -6, 802, 627]
    assert result == expected
    connection.close.assert_called_once()


@pytest.mark.parametrize("case", ["confirmed", "ambiguous", "unconfirmed"])
def test_native_activation_requires_unique_match_and_confirms_delivery(
    window_capture, monkeypatch, case
):
    import sys
    from types import ModuleType

    from lambchat_sandbox.cua_ops import CuaOpError

    connection, _ = window_capture
    x = sys.modules["Xlib"].X
    x.CurrentTime, x.SubstructureRedirectMask, x.SubstructureNotifyMask = 0, 1, 2
    protocol = ModuleType("Xlib.protocol")
    protocol.event = SimpleNamespace(ClientMessage=lambda **kwargs: kwargs)
    monkeypatch.setitem(sys.modules, "Xlib.protocol", protocol)
    target = {"pid": 7, "bounds": [1, 2, 800, 600]}
    monkeypatch.setattr(
        cua_linux,
        "_x11_clients",
        lambda conn: {42: target, 43: target} if case == "ambiguous" else {42: target},
    )
    monkeypatch.setattr(
        cua_linux, "foreground_window", lambda: target if case == "confirmed" else None
    )
    ticks = iter([0, 0, 3])
    monkeypatch.setattr("time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    if case == "confirmed":
        assert (
            cua_linux.activate_window_bounds(7, target["bounds"])["disposition"]["delivery"]
            == "delivered_verified"
        )
    else:
        with pytest.raises(CuaOpError) as error:
            cua_linux.activate_window_bounds(7, target["bounds"])
        if case == "unconfirmed":
            assert error.value.context["disposition"] == {
                "delivery": "delivered_unverified",
                "retry": "unsafe",
            }
    assert connection.screen.return_value.root.send_event.call_count == (
        0 if case == "ambiguous" else 1
    )
    connection.close.assert_called_once()

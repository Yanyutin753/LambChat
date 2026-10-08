"""macOS native adapter contracts, without requiring native libraries in CI."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def mac_backend():
    spec = importlib.util.spec_from_file_location(
        "cua_mac_test", Path(__file__).resolve().parents[2] / "client/lambchat_sandbox/cua_mac.py"
    )
    mac = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"atomacos": SimpleNamespace(_a11y=SimpleNamespace())}):
        spec.loader.exec_module(mac)
    return mac


def test_window_list_and_observation_share_a_stable_window_id(mac_backend) -> None:
    window = SimpleNamespace(
        AXTitle="Main",
        AXSubrole="AXStandardWindow",
        AXMain=True,
        AXFocused=True,
        AXPosition=(10, 20),
        AXSize=(800, 600),
    )
    with patch.object(
        mac_backend, "app_by_pid", return_value=SimpleNamespace(windows=lambda: [window])
    ):
        assert mac_backend.windows(42)[0]["window_id"] == 0
        _, info = mac_backend.pick_window(42, 0)
        assert info["window_id"] == 0


def test_focus_uses_the_actual_accessibility_attribute(mac_backend) -> None:
    class Element:
        AXFocused = False

        def __setattr__(self, name, value):
            if name == "AXFocused":
                object.__setattr__(self, name, value)
            # atomacos silently ignores unknown AX attribute names.

    element = Element()
    mac_backend.set_focus(element)
    assert element.AXFocused is True


def test_frontmost_uses_application_identity_when_system_ax_is_unavailable(mac_backend) -> None:
    with (
        patch.object(mac_backend, "ax_trusted", return_value=True),
        patch(
            "subprocess.run",
            side_effect=[
                SimpleNamespace(stdout="ASN:0x0-0x123:"),
                SimpleNamespace(stdout="pid = 42 !cgsConnection"),
            ],
        ) as run,
    ):
        assert mac_backend.frontmost_pid() == 42
        assert run.call_args_list[1].args[0] == [
            "/usr/bin/lsappinfo",
            "info",
            "-only",
            "pid",
            "ASN:0x0-0x123:",
        ]


def test_native_paste_restores_every_clipboard_format(mac_backend) -> None:
    saved = {"public.png": b"image", "public.utf8-plain-text": b"original"}

    class Item:
        def __init__(self):
            self.data = {}

        def types(self):
            return list(self.data)

        def dataForType_(self, kind):  # noqa: N802
            return self.data[kind]

        def setData_forType_(self, data, kind):  # noqa: N802
            self.data[kind] = bytes(data)

        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

    item = Item()
    item.data = saved.copy()

    class Board:
        items = [item]

        def pasteboardItems(self):  # noqa: N802
            return self.items

        def clearContents(self):  # noqa: N802
            self.items = []

        def setString_forType_(self, text, kind):  # noqa: N802
            entry = Item()
            entry.data = {kind: text.encode()}
            self.items = [entry]

        def writeObjects_(self, items):  # noqa: N802
            self.items = items

    board = Board()
    pasted = []
    appkit = SimpleNamespace(
        NSPasteboard=SimpleNamespace(generalPasteboard=lambda: board),
        NSPasteboardItem=Item,
        NSPasteboardTypeString="public.utf8-plain-text",
        NSData=SimpleNamespace(dataWithBytes_length_=lambda data, length: data),
    )
    events = []

    def post(_tap, event):
        events.append(event)
        if event["down"] and event["code"] == 9:
            pasted.append(board.items[0].data.copy())

    quartz = SimpleNamespace(
        CGEventCreateKeyboardEvent=lambda source, code, down: {"code": code, "down": down},
        CGEventSetFlags=lambda event, flags: event.update(flags=flags),
        CGEventPost=post,
        kCGHIDEventTap=0,
        kCGEventFlagMaskCommand=1,
        kCGEventFlagMaskControl=2,
        kCGEventFlagMaskAlternate=4,
        kCGEventFlagMaskShift=8,
    )
    with patch.dict(
        sys.modules,
        {
            "AppKit": appkit,
            "Quartz": quartz,
            "pyautogui": SimpleNamespace(isShiftCharacter=lambda key: key == "?"),
            "pyautogui._pyautogui_osx": SimpleNamespace(keyboardMapping={"v": 9, "?": 44}),
        },
    ):
        mac_backend.type_text("hello 中文")
        mac_backend.press_chord(["?"], ["command"])
    assert pasted == [{"public.utf8-plain-text": "hello 中文".encode()}]
    assert board.items[0].data == saved
    assert events == [
        {"code": 9, "down": True, "flags": 1},
        {"code": 9, "down": False, "flags": 0},
        {"code": 44, "down": True, "flags": 9},
        {"code": 44, "down": False, "flags": 0},
    ]


def test_window_capture_uses_native_screen_coordinates_on_retina(mac_backend) -> None:
    from PIL import Image

    def run(command, **kwargs):
        assert "-R100,100,800,600" in command
        assert kwargs["check"] and kwargs["timeout"] == 10
        Image.new("RGB", (1600, 1200), color="blue").save(command[-1])
        return SimpleNamespace(returncode=0)

    with patch("subprocess.run", side_effect=run):
        image = mac_backend.screenshot([100, 100, 800, 600])
    assert image.size == (1600, 1200)
    assert image.getpixel((1599, 1199)) == (0, 0, 255)

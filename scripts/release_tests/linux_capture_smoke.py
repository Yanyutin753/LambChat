"""Verify pinned agent-desktop captures a real GTK target beneath an overlay."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.pop("WAYLAND_DISPLAY", None)
os.environ["GDK_BACKEND"] = "x11"
os.environ["XDG_SESSION_TYPE"] = "x11"


def fixture(destination):
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk

    windows = []
    for title, x, y, width, height, color in [
        ("LambChat Capture Target", 20, 30, 200, 150, (1, 0, 0)),
        ("LambChat Capture Cover", 40, 50, 100, 80, (0, 1, 0)),
    ]:
        window = Gtk.Window(title=title)
        window.set_decorated(False)
        window.set_default_size(width, height)
        window.move(x, y)
        window.set_keep_above(True)
        window.set_name("target" if color == (1, 0, 0) else "cover")
        provider = Gtk.CssProvider()
        provider.load_from_data(b"#target { background: #ff0000; } #cover { background: #00ff00; }")
        window.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        window.show_all()
        windows.append(window)
    GLib.timeout_add(
        800,
        lambda: (
            Path(destination).write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "windows": [
                            {
                                "title": w.get_title(),
                                "mapped": w.get_mapped(),
                                "visible": w.get_visible(),
                                "size": list(w.get_size()),
                                "position": list(w.get_position()),
                            }
                            for w in windows
                        ],
                    }
                )
            )
            and False
        ),
    )
    Gtk.main()


def main():
    from PIL import ImageGrab

    from lambchat_sandbox.agent_desktop import AgentDesktopBackend, binary_path

    binary = binary_path()
    assert binary, "Pinned driver missing"
    driver = AgentDesktopBackend(binary)
    with tempfile.TemporaryDirectory(prefix="lambchat-capture-") as directory:
        ready = Path(directory) / "ready.json"
        wm = subprocess.Popen(["openbox"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        assert wm.poll() is None, "Isolated window manager exited"
        compositor = subprocess.Popen(
            ["xcompmgr"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(0.3)
        assert compositor.poll() is None, "Isolated compositor exited"
        child = subprocess.Popen([sys.executable, __file__, "--fixture", str(ready)])
        try:
            deadline = time.monotonic() + 15
            while not ready.exists() and time.monotonic() < deadline:
                assert child.poll() is None, "GTK fixture exited"
                time.sleep(0.1)
            assert ready.exists(), "GTK fixture did not map"
            windows = driver.windows(child.pid)
            targets = [w for w in windows if w["title"] == "LambChat Capture Target"]
            assert len(targets) == 1, {
                "windows": windows,
                "apps": driver.list_apps(),
                "unfiltered": driver._call("list-windows"),
            }
            target = targets[0]
            bounds = target["bounds"]
            x, y, width, height = map(int, bounds)
            raw = ImageGrab.grab(bbox=(x, y, x + width, y + height), xdisplay=os.environ["DISPLAY"])
            assert raw.getpixel((30, 30)) == (0, 255, 0), "Cover must be visible before capture"
            image = driver.screenshot(bounds, target).convert("RGB")
            assert image.getpixel((30, 30)) == (255, 0, 0), "Overlay leaked into driver screenshot"
            crop = driver.screenshot([x + 25, y + 25, 20, 20], target).convert("RGB")
            assert crop.size == (20, 20) and crop.getpixel((0, 0)) == (255, 0, 0)
            after = ImageGrab.grab(
                bbox=(x, y, x + width, y + height), xdisplay=os.environ["DISPLAY"]
            )
            assert after.getpixel((30, 30)) == (0, 255, 0), "Capture must leave the cover visible"
            driver.activate_window(child.pid, target["window_id"])
            element, active = driver.pick_window(child.pid, target["window_id"])
            assert active["focused"], "Driver did not verify the activated window"
            assert driver.row_of(element)["title"] == "LambChat Capture Target"
            print(
                "PASS: driver-only discovery, focus, snapshot and overlay-free window/crop pixels"
            )
        finally:
            child.terminate()
            child.wait(timeout=5)
            compositor.terminate()
            compositor.wait(timeout=5)
            wm.terminate()
            wm.wait(timeout=5)
            for session in driver.sessions.values():
                driver._run(["--session", session, "session", "end"])


if __name__ == "__main__":
    if "--fixture" in sys.argv:
        fixture(sys.argv[-1])
    else:
        main()

import os

os.environ.pop("WAYLAND_DISPLAY", None)
from PIL import ImageGrab
from Xlib import X, Xatom, display

from lambchat_sandbox.cua_linux import screenshot

c = display.Display()
r = c.screen().root
w = r.create_window(
    20,
    30,
    200,
    150,
    0,
    c.screen().root_depth,
    X.InputOutput,
    X.CopyFromParent,
    background_pixel=0xFF0000,
)
w.map()
c.sync()
r.change_property(c.intern_atom("_NET_ACTIVE_WINDOW"), Xatom.WINDOW, 32, [w.id])
# Prime the window's offscreen storage before an always-on-top sibling covers it.
w.composite_redirect_window(0)
c.sync()
o = r.create_window(
    40,
    50,
    100,
    80,
    0,
    c.screen().root_depth,
    X.InputOutput,
    X.CopyFromParent,
    background_pixel=0x00FF00,
    override_redirect=1,
)
o.map()
c.sync()
try:
    raw = ImageGrab.grab(bbox=(20, 30, 220, 180), xdisplay=os.environ["DISPLAY"])
    assert raw.getpixel((30, 30)) == (0, 255, 0), raw.getpixel((30, 30))
    image = screenshot([20, 30, 200, 150])
    assert image.getpixel((30, 30)) == (255, 0, 0), image.getpixel((30, 30))
    assert image.size == (200, 150)
    assert o.get_attributes().map_state == X.IsViewable
    crop = screenshot([45, 55, 20, 20])
    assert crop.getpixel((0, 0)) == (255, 0, 0)
    print(
        "PASS: overlapping toolbar visible; full-window and subtree screenshots retain underlying target pixels"
    )
finally:
    o.destroy()
    w.destroy()
    c.sync()
    c.close()

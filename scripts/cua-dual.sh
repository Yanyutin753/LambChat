set -eu
cat > /tmp/cua-xorg.conf <<'XORG'
Section "Device"
 Identifier "dummy"
 Driver "dummy"
 VideoRam 512000
EndSection
Section "Monitor"
 Identifier "desktop"
 HorizSync 28-120
 VertRefresh 45-100
 Modeline "1440x900" 106.50 1440 1520 1672 1904 900 903 909 934 -hsync +vsync
EndSection
Section "Screen"
 Identifier "screen"
 Device "dummy"
 Monitor "desktop"
 DefaultDepth 24
 SubSection "Display"
 Depth 24
 Modes "1440x900"
 Virtual 2880 900
 EndSubSection
EndSection
XORG
sudo Xorg :97 -noreset -ac -config /tmp/cua-xorg.conf >/tmp/cua-xorg.log 2>&1 &
export DISPLAY=:97
for i in {1..45}; do xdpyinfo >/dev/null 2>&1 && break; sleep .25; done
xrandr --addmode DUMMY1 1440x900
xrandr --output DUMMY0 --primary --mode 1440x900 --pos 0x0 --output DUMMY1 --mode 1440x900 --pos 1440x0
xrandr --listmonitors
openbox >/tmp/cua-openbox.log 2>&1 &
sleep .5
xcompmgr &
sleep .5
GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 /usr/bin/python3 scripts/run_validation.py /usr/bin/python3 scripts/fullscreen_evidence.py |tee /tmp/cua-dual.log
grep -q 'displays=2 geometry=true transparent=true' /tmp/cua-dual.log

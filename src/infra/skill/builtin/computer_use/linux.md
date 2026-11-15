## Linux

Accessibility needs the user's graphical session and AT-SPI/session D-Bus. X11 and
Wayland expose different capture and input capabilities; trust status, not an assumed
display backend. Prefer accessibility actions where available. Missing display/capture
support is a capability failure, not evidence of a blank screen. Keep the control overlay
out of screenshot evidence through the daemon's capture path, never by disabling control.

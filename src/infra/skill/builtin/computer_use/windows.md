## Windows

Control requires an unlocked interactive user desktop. Session 0, the sign-in screen,
UAC secure desktop and a higher-integrity target may be inaccessible; do not interpret
missing controls as an empty app or bypass elevation boundaries. Prefer UI Automation
elements, refresh after dialogs open, and check foreground before keyboard input.
Use Windows key names and paths only when the tool or task requires them. For Save As,
verify the selected destination and resulting file rather than treating Enter as saved.

export const RIGHT_PANEL_WIDTH_CHANGED_EVENT = "right-panel-width-changed";

export function notifyRightPanelWidthChanged(
  target: EventTarget = window,
): void {
  target.dispatchEvent(new CustomEvent(RIGHT_PANEL_WIDTH_CHANGED_EVENT));
}

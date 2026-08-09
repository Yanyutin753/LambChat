import type { RightPanelLayoutSnapshot } from "./rightPanelLayout";

export const RIGHT_PANEL_WIDTH_CHANGED_EVENT = "right-panel-width-changed";

export function notifyRightPanelWidthChanged(
  detail: RightPanelLayoutSnapshot | null = null,
  target: EventTarget = window,
): void {
  target.dispatchEvent(
    new CustomEvent(RIGHT_PANEL_WIDTH_CHANGED_EVENT, { detail }),
  );
}

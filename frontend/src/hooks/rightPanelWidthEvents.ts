import type { RightPanelLayoutSnapshot } from "./rightPanelLayout";

export const RIGHT_PANEL_WIDTH_CHANGED_EVENT = "right-panel-width-changed";

let latestLayoutSnapshot: RightPanelLayoutSnapshot | null = null;

export function getRightPanelLayoutSnapshot(): RightPanelLayoutSnapshot | null {
  return latestLayoutSnapshot;
}

export function notifyRightPanelWidthChanged(
  detail: RightPanelLayoutSnapshot | null = null,
  target: EventTarget = window,
): void {
  latestLayoutSnapshot = detail;
  target.dispatchEvent(
    new CustomEvent(RIGHT_PANEL_WIDTH_CHANGED_EVENT, { detail }),
  );
}

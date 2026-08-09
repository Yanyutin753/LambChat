import type { RightPanelLayoutSnapshot } from "../../../hooks/rightPanelLayout";
import {
  notifyRightPanelWidthChanged,
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
} from "../../../hooks/rightPanelWidthEvents";

export { notifyRightPanelWidthChanged, RIGHT_PANEL_WIDTH_CHANGED_EVENT };

export const MINIMUM_WORKSPACE_WITH_NAVIGATION_PX = 820;

export function shouldTemporarilyCollapseNavigation({
  layout,
  minimumWorkspaceWithNavigationPx,
  userOverrode,
}: {
  layout: RightPanelLayoutSnapshot | null;
  minimumWorkspaceWithNavigationPx: number;
  userOverrode: boolean;
}): boolean {
  if (!layout?.open || layout.presentation !== "docked" || userOverrode) {
    return false;
  }

  return (
    layout.viewportWidth - layout.widthPx < minimumWorkspaceWithNavigationPx
  );
}

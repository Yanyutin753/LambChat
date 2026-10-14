import type { RightPanelLayoutSnapshot } from "../../../hooks/rightPanelLayout";
import {
  notifyRightPanelWidthChanged,
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
} from "../../../hooks/rightPanelWidthEvents";

export { notifyRightPanelWidthChanged, RIGHT_PANEL_WIDTH_CHANGED_EVENT };

// Keep the default 264px navigation plus roughly 416px for chat.
export const MINIMUM_WORKSPACE_WITH_NAVIGATION_PX = 680;

export function shouldTemporarilyCollapseNavigation({
  layout,
  viewportWidth,
  minimumWorkspaceWithNavigationPx,
  userOverrode,
}: {
  layout: RightPanelLayoutSnapshot | null;
  viewportWidth: number;
  minimumWorkspaceWithNavigationPx: number;
  userOverrode: boolean;
}): boolean {
  if (userOverrode) return false;
  if (viewportWidth < minimumWorkspaceWithNavigationPx) return true;
  if (!layout?.open || layout.presentation !== "docked") return false;

  return (
    viewportWidth - layout.widthPx < minimumWorkspaceWithNavigationPx
  );
}

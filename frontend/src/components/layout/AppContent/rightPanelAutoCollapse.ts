import type { RightPanelLayoutSnapshot } from "../../../hooks/rightPanelLayout";
import {
  notifyRightPanelWidthChanged,
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
} from "../../../hooks/rightPanelWidthEvents";

export { notifyRightPanelWidthChanged, RIGHT_PANEL_WIDTH_CHANGED_EVENT };

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
  if (viewportWidth < 640 || userOverrode) return false;
  if (viewportWidth < minimumWorkspaceWithNavigationPx) return true;
  if (!layout?.open || layout.presentation !== "docked") return false;

  return (
    viewportWidth - layout.widthPx < minimumWorkspaceWithNavigationPx
  );
}

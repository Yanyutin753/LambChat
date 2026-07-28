import {
  notifyRightPanelWidthChanged,
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
} from "../../../hooks/rightPanelWidthEvents";

export { notifyRightPanelWidthChanged, RIGHT_PANEL_WIDTH_CHANGED_EVENT };

export const WIDE_RIGHT_PANEL_THRESHOLD_PCT = 50;
export const SIDEBAR_PREVIEW_WIDTH_KEY = "sidebar-preview-width";
export const EDITOR_SIDEBAR_WIDTH_KEY = "editor-sidebar-width";

export function getRightPanelWidthPct({
  previewOpen,
  editorOpen,
  previewWidthPct,
  editorWidthPct,
}: {
  previewOpen: boolean;
  editorOpen: boolean;
  previewWidthPct: number;
  editorWidthPct: number;
}): number {
  let total = 0;
  if (previewOpen) total += previewWidthPct;
  if (editorOpen) total += editorWidthPct;
  return total;
}

export function nextTempAutoCollapsed({
  isDesktop,
  rightPanelWidthPct,
  userOverrode,
  thresholdPct = WIDE_RIGHT_PANEL_THRESHOLD_PCT,
}: {
  isDesktop: boolean;
  rightPanelWidthPct: number;
  userOverrode: boolean;
  thresholdPct?: number;
}): boolean {
  if (!isDesktop || userOverrode) return false;
  return rightPanelWidthPct >= thresholdPct;
}

export function nextUserOverrode({
  userOverrode,
  wideOpen,
  userExpanded,
}: {
  userOverrode: boolean;
  wideOpen: boolean;
  userExpanded: boolean;
}): boolean {
  if (!wideOpen) return false;
  if (userExpanded) return true;
  return userOverrode;
}

export function parseWidthPct(
  raw: string | null | undefined,
  fallback: number,
): number {
  const value = parseInt(raw || String(fallback), 10);
  return Number.isFinite(value) ? value : fallback;
}

export function readDomRightPanelWidthPct(
  root: Element = document.documentElement,
  storage: Pick<Storage, "getItem"> = localStorage,
): number {
  return getRightPanelWidthPct({
    previewOpen: root.getAttribute("data-sidebar-preview") === "open",
    editorOpen: root.getAttribute("data-editor-sidebar") === "open",
    previewWidthPct: parseWidthPct(
      storage.getItem(SIDEBAR_PREVIEW_WIDTH_KEY),
      60,
    ),
    editorWidthPct: parseWidthPct(
      storage.getItem(EDITOR_SIDEBAR_WIDTH_KEY),
      30,
    ),
  });
}

import type { ActiveRevealPreviewState } from "./revealPreviewState";
import { createPanelTabsStore } from "./createPanelTabsStore";

const store = createPanelTabsStore<ActiveRevealPreviewState>(
  (state) => `reveal-preview:${state.request.previewKey}`,
);
export const getRevealPreviewTabs = store.getAll;
export const clearRevealPreviewTabs = store.clear;
export const getActiveRevealPreviewState = store.get;
export const subscribeActiveRevealPreviewState = store.subscribe;

export function closeRevealPreviewTab(key: string): void {
  store.close(`reveal-preview:${key}`);
}
export function setActiveRevealPreviewState(
  next: ActiveRevealPreviewState | null,
): void {
  if (next) store.open(next);
  else store.close();
}
export function updateActiveRevealPreviewState(
  updater: (
    current: ActiveRevealPreviewState | null,
  ) => ActiveRevealPreviewState | null,
): void {
  const next = updater(store.get());
  if (next) store.update(() => next);
  else store.close();
}

export {
  getSidebarHistoryLength as getRevealPreviewHistoryLength,
  goBackSidebar as goBackRevealPreviewState,
  clearSidebarHistory as clearRevealPreviewHistory,
  subscribeSidebarHistory as subscribeSidebarHistoryStore,
} from "./sidebarHistoryStore";

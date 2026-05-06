import { createSingletonStore } from "./createSingletonStore";
import type { ActiveRevealPreviewState } from "./revealPreviewState";
import {
  registerPanelCapture,
  pushCurrentPanelToHistory,
} from "./sidebarHistoryStore";

const store = createSingletonStore<ActiveRevealPreviewState | null>(null);

registerPanelCapture(() => {
  const state = store.get();
  if (state) {
    const captured = state;
    return { restore: () => store.set(captured) };
  }
  return null;
});

export function getActiveRevealPreviewState(): ActiveRevealPreviewState | null {
  return store.get();
}

export function setActiveRevealPreviewState(
  next: ActiveRevealPreviewState | null,
): void {
  if (next !== null) {
    pushCurrentPanelToHistory();
  }
  store.set(next);
}

export function updateActiveRevealPreviewState(
  updater: (
    current: ActiveRevealPreviewState | null,
  ) => ActiveRevealPreviewState | null,
): void {
  store.set(updater(store.get()));
}

export function subscribeActiveRevealPreviewState(
  listener: () => void,
): () => void {
  return store.subscribe(listener);
}

export {
  getSidebarHistoryLength as getRevealPreviewHistoryLength,
  goBackSidebar as goBackRevealPreviewState,
  clearSidebarHistory as clearRevealPreviewHistory,
  subscribeSidebarHistory as subscribeSidebarHistoryStore,
} from "./sidebarHistoryStore";

import { createSingletonStore } from "./createSingletonStore";
import type { ActiveRevealPreviewState } from "./revealPreviewState";

const store = createSingletonStore<ActiveRevealPreviewState | null>(null);

export function getActiveRevealPreviewState(): ActiveRevealPreviewState | null {
  return store.get();
}

export function setActiveRevealPreviewState(
  next: ActiveRevealPreviewState | null,
): void {
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

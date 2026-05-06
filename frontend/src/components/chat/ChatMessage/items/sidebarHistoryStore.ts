import { createSingletonStore } from "./createSingletonStore";
import { clearToolPanelRegistry } from "./toolPanelRegistry";

export interface SidebarHistoryEntry {
  restore: () => void;
}

type CaptureFn = () => SidebarHistoryEntry | null;

const captures: CaptureFn[] = [];
let history: SidebarHistoryEntry[] = [];
let isRestoring = false;

const countStore = createSingletonStore<number>(0);

export function registerPanelCapture(fn: CaptureFn): void {
  captures.push(fn);
}

function captureCurrentPanel(): SidebarHistoryEntry | null {
  for (const fn of captures) {
    const entry = fn();
    if (entry) return entry;
  }
  return null;
}

export function pushCurrentPanelToHistory(): void {
  if (isRestoring) return;
  const entry = captureCurrentPanel();
  if (entry) {
    history = [...history, entry];
    countStore.set(history.length);
  }
}

export function goBackSidebar(): boolean {
  if (history.length === 0) return false;
  const entry = history[history.length - 1];
  history = history.slice(0, -1);
  countStore.set(history.length);
  isRestoring = true;
  clearToolPanelRegistry();
  try {
    entry.restore();
  } finally {
    isRestoring = false;
  }
  return true;
}

export function getSidebarHistoryLength(): number {
  return history.length;
}

export function clearSidebarHistory(): void {
  history = [];
  countStore.set(0);
}

export function subscribeSidebarHistory(listener: () => void): () => void {
  return countStore.subscribe(listener);
}

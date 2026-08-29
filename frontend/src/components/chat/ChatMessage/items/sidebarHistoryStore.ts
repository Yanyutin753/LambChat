import { createSingletonStore } from "./createSingletonStore";
import { clearToolPanelRegistry } from "./toolPanelRegistry";
import {
  captureActiveSidebarPanelSnapshot,
  clearSidebarPanelSnapshots,
  queueSidebarPanelSnapshot,
  type SidebarPanelSnapshot,
} from "./sidebarPanelSnapshot";

export interface SidebarHistoryEntry {
  restore: () => void;
  snapshot?: SidebarPanelSnapshot | null;
}

type CaptureFn = () => SidebarHistoryEntry | null;
/** 返回历史时直接收起对应面板（不再入栈），避免多面板叠加显示 */
type DeactivateFn = () => void;

const captures: CaptureFn[] = [];
const deactivators: DeactivateFn[] = [];
let history: SidebarHistoryEntry[] = [];
let isRestoring = false;

const countStore = createSingletonStore<number>(0);

export function registerPanelCapture(fn: CaptureFn): void {
  captures.push(fn);
}

export function registerPanelDeactivate(fn: DeactivateFn): void {
  deactivators.push(fn);
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
    history = [
      ...history,
      { ...entry, snapshot: captureActiveSidebarPanelSnapshot() },
    ];
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
    // 先把所有面板源收起（旧 store 残留会导致恢复后双面板叠加），再恢复目标
    deactivators.forEach((deactivate) => deactivate());
    queueSidebarPanelSnapshot(entry.snapshot ?? null);
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
  clearSidebarPanelSnapshots();
}

export function subscribeSidebarHistory(listener: () => void): () => void {
  return countStore.subscribe(listener);
}

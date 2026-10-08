import type { ReactNode } from "react";

export type RightPanelKind = "editor" | "content";

export interface RightPanelEntry {
  id: symbol;
  kind: RightPanelKind;
  automatic: boolean;
  close: () => void;
  opener: HTMLElement | null;
  title?: string;
  path?: string;
  fileType?: string;
  icon?: ReactNode;
  panelId?: string;
  registryKey?: string;
  parentId?: symbol | null;
}

export interface RightPanelSnapshot {
  entries: readonly RightPanelEntry[];
  activeId: symbol | null;
  activeKind: RightPanelKind | null;
  depth: number;
  collapsed: boolean;
  hasDeliberatePanel: boolean;
}

let entries: RightPanelEntry[] = [];
let activeId: symbol | null = null;
let collapsed = false;
const closingIds = new Set<symbol>();
const listeners = new Set<() => void>();

let snapshot: RightPanelSnapshot = {
  entries,
  activeId: null,
  activeKind: null,
  depth: 0,
  collapsed: false,
  hasDeliberatePanel: false,
};

function emit(): void {
  const active = entries.find((entry) => entry.id === activeId) ?? null;
  snapshot = {
    entries,
    activeId: active?.id ?? null,
    activeKind: collapsed ? null : (active?.kind ?? null),
    depth: entries.length,
    collapsed,
    hasDeliberatePanel: entries.some((entry) => !entry.automatic),
  };
  listeners.forEach((listener) => listener());
}

export function registerRightPanel(entry: RightPanelEntry): boolean {
  const index = entries.findIndex((candidate) => candidate.id === entry.id);
  if (index >= 0) {
    entries = entries.map((candidate) =>
      candidate.id === entry.id ? entry : candidate,
    );
    activeId = entry.id;
    collapsed = false;
    closingIds.delete(entry.id);
    emit();
    return true;
  }

  if (entry.automatic && entries.length > 0) return false;

  if (!entry.automatic) {
    const automaticEntries = entries.filter((candidate) => candidate.automatic);
    entries = entries.filter((candidate) => !candidate.automatic);
    automaticEntries.forEach((candidate) => candidate.close());
  }

  collapsed = false;
  entries = [...entries, entry];
  if (
    !entries.some(
      (candidate) =>
        candidate.id === activeId && candidate.parentId === entry.id,
    )
  ) {
    activeId = entry.id;
  }
  closingIds.delete(entry.id);
  emit();
  return true;
}

export function updateRightPanel(entry: RightPanelEntry): void {
  const index = entries.findIndex((candidate) => candidate.id === entry.id);
  if (index < 0) return;

  entries = entries.map((candidate, candidateIndex) =>
    candidateIndex === index ? entry : candidate,
  );
  emit();
}

export function unregisterRightPanel(id: symbol): void {
  const next = entries.filter((entry) => entry.id !== id);
  if (next.length === entries.length) return;

  const index = entries.findIndex((entry) => entry.id === id);
  entries = next;
  if (!entries.length) collapsed = false;
  if (activeId === id) {
    const adjacent = entries[Math.min(index, entries.length - 1)];
    activeId = adjacent?.id ?? null;
  }
  closingIds.delete(id);
  emit();
}

export function getRightPanelSnapshot(): RightPanelSnapshot {
  return snapshot;
}

export function subscribeRightPanels(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function hasDeliberateRightPanel(): boolean {
  return getRightPanelSnapshot().hasDeliberatePanel;
}

export function hasOpenRightPanel(): boolean {
  return getRightPanelSnapshot().depth > 0;
}

export function activateRightPanel(id: symbol): void {
  const entry = entries.find((candidate) => candidate.id === id);
  if (!entry || (activeId === id && !collapsed)) return;
  const select = () => {
    if (!entries.some((candidate) => candidate.id === id)) return;
    collapsed = false;
    activeId = id;
    emit();
  };
  if (typeof document !== "undefined" && document.fullscreenElement) {
    void document
      .exitFullscreen()
      .then(select)
      .catch(() => {});
  } else {
    select();
  }
}

export function activateRightPanelByKey(key: string): void {
  const entry = entries.find((candidate) => candidate.registryKey === key);
  if (entry) activateRightPanel(entry.id);
}

export function closeRightPanel(id: symbol): void {
  const entry = entries.find((candidate) => candidate.id === id);
  if (!entry || closingIds.has(id)) return;
  closingIds.add(id);
  entry.close();
}

export function closeActiveRightPanel(): void {
  if (activeId && !collapsed) closeRightPanel(activeId);
}

export function resetRightPanelCoordinator(): void {
  entries = [];
  activeId = null;
  collapsed = false;
  closingIds.clear();
  emit();
}

/** Hide the lane without unmounting its tabs or discarding drafts. */
export function collapseRightPanel(): void {
  if (!activeId || collapsed) return;
  const collapse = () => {
    if (!activeId) return;
    collapsed = true;
    emit();
  };
  if (typeof document !== "undefined" && document.fullscreenElement) {
    void document.exitFullscreen().then(collapse).catch(() => {});
  } else {
    collapse();
  }
}

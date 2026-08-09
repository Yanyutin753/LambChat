export type RightPanelKind = "editor" | "content";

export interface RightPanelEntry {
  id: symbol;
  kind: RightPanelKind;
  automatic: boolean;
  close: () => void;
  opener: HTMLElement | null;
}

export interface RightPanelSnapshot {
  activeId: symbol | null;
  activeKind: RightPanelKind | null;
  depth: number;
  hasDeliberatePanel: boolean;
}

let entries: RightPanelEntry[] = [];
let closingId: symbol | null = null;
const listeners = new Set<() => void>();

let snapshot: RightPanelSnapshot = {
  activeId: null,
  activeKind: null,
  depth: 0,
  hasDeliberatePanel: false,
};

function emit(): void {
  const active = entries.at(-1) ?? null;
  snapshot = {
    activeId: active?.id ?? null,
    activeKind: active?.kind ?? null,
    depth: entries.length,
    hasDeliberatePanel: entries.some((entry) => !entry.automatic),
  };
  listeners.forEach((listener) => listener());
}

export function registerRightPanel(entry: RightPanelEntry): boolean {
  const index = entries.findIndex((candidate) => candidate.id === entry.id);
  if (index >= 0) {
    entries = [...entries.slice(0, index), ...entries.slice(index + 1), entry];
    closingId = null;
    emit();
    return true;
  }

  if (entry.automatic && entries.length > 0) return false;

  if (!entry.automatic) {
    const automaticEntries = entries.filter((candidate) => candidate.automatic);
    entries = entries.filter((candidate) => !candidate.automatic);
    automaticEntries.forEach((candidate) => candidate.close());
  }

  entries = [...entries, entry];
  closingId = null;
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

  entries = next;
  if (closingId === id) closingId = null;
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

export function closeActiveRightPanel(): void {
  const active = entries.at(-1);
  if (!active || closingId === active.id) return;

  closingId = active.id;
  active.close();
}

export function resetRightPanelCoordinator(): void {
  entries = [];
  closingId = null;
  emit();
}

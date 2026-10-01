import {
  activateRightPanelByKey,
  getRightPanelSnapshot,
  subscribeRightPanels,
} from "../../../common/rightPanelCoordinator";

/** Preview sources share keyed retention; the coordinator owns visual selection. */
export function createPanelTabsStore<T>(keyOf: (value: T) => string) {
  let tabs: readonly T[] = [];
  let selected: string | null = null;
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((listener) => listener());
  const get = () => tabs.find((tab) => keyOf(tab) === selected) ?? null;
  subscribeRightPanels(() => {
    const snapshot = getRightPanelSnapshot();
    const key = snapshot.entries.find((entry) => entry.id === snapshot.activeId)
      ?.registryKey;
    if (key && key !== selected && tabs.some((tab) => keyOf(tab) === key)) {
      selected = key;
      notify();
    }
  });
  return {
    get,
    getAll: () => tabs,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    open(value: T) {
      const key = keyOf(value);
      const existing = tabs.find((tab) => keyOf(tab) === key);
      const changed = existing !== value || selected !== key;
      tabs =
        existing === value
          ? tabs
          : existing
            ? tabs.map((tab) => (keyOf(tab) === key ? value : tab))
            : [...tabs, value];
      selected = key;
      if (changed) notify();
      activateRightPanelByKey(key);
    },
    update(updater: (value: T) => T, key = selected) {
      const current = tabs.find((tab) => keyOf(tab) === key);
      if (!current) return;
      const next = updater(current);
      if (next === current) return;
      tabs = tabs.map((tab) => (tab === current ? next : tab));
      notify();
    },
    close(key = selected) {
      const index = tabs.findIndex((tab) => keyOf(tab) === key);
      if (index < 0) return;
      tabs = tabs.filter((tab) => keyOf(tab) !== key);
      if (selected === key)
        selected = tabs[Math.min(index, tabs.length - 1)]
          ? keyOf(tabs[Math.min(index, tabs.length - 1)])
          : null;
      notify();
    },
    clear() {
      if (!tabs.length) return;
      tabs = [];
      selected = null;
      notify();
    },
  };
}

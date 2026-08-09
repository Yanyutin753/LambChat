/** @vitest-environment jsdom */

import { beforeEach, expect, test, vi } from "vitest";

import {
  clearSidebarHistory,
  getSidebarHistoryLength,
  goBackSidebar,
  pushCurrentPanelToHistory,
  registerPanelCapture,
} from "../sidebarHistoryStore";
import {
  clearSidebarPanelSnapshots,
  queueSidebarPanelSnapshot,
  registerActiveSidebarSnapshotTarget,
  restorePendingSidebarPanelSnapshot,
  type SidebarPanelSnapshot,
} from "../sidebarPanelSnapshot";

let currentRestore: (() => void) | null = null;

registerPanelCapture(() =>
  currentRestore ? { restore: currentRestore } : null,
);

beforeEach(() => {
  currentRestore = null;
  clearSidebarHistory();
  clearSidebarPanelSnapshots();
});

test("restores the latest captured legacy preview and clears history", () => {
  const restore = vi.fn();
  currentRestore = restore;
  pushCurrentPanelToHistory();

  expect(getSidebarHistoryLength()).toBe(1);
  expect(goBackSidebar()).toBe(true);
  expect(restore).toHaveBeenCalledOnce();

  clearSidebarHistory();
  expect(getSidebarHistoryLength()).toBe(0);
});

function createScrolledPanel(panelKey: string, scrollTop: number) {
  const root = document.createElement("section");
  const scroller = document.createElement("div");
  scroller.dataset.sidebarSnapshotKey = "body";
  scroller.scrollTop = scrollTop;
  root.append(scroller);
  registerActiveSidebarSnapshotTarget(panelKey, root);
  return { root, scroller };
}

test("restores immutable view snapshots in LIFO history order", async () => {
  const restoreA = vi.fn();
  currentRestore = restoreA;
  createScrolledPanel("panel:a", 120);
  pushCurrentPanelToHistory();

  const restoreB = vi.fn();
  currentRestore = restoreB;
  createScrolledPanel("panel:b", 260);
  pushCurrentPanelToHistory();

  const restoredB = createScrolledPanel("panel:b", 0);
  expect(goBackSidebar()).toBe(true);
  expect(restoreB).toHaveBeenCalledOnce();
  await expect(
    restorePendingSidebarPanelSnapshot("panel:b", restoredB.root),
  ).resolves.toBe(true);
  expect(restoredB.scroller.scrollTop).toBe(260);

  const restoredA = createScrolledPanel("panel:a", 0);
  expect(goBackSidebar()).toBe(true);
  expect(restoreA).toHaveBeenCalledOnce();
  await expect(
    restorePendingSidebarPanelSnapshot("panel:a", restoredA.root),
  ).resolves.toBe(true);
  expect(restoredA.scroller.scrollTop).toBe(120);
});

test("clearing history also clears pending panel restoration", async () => {
  const pending: SidebarPanelSnapshot = {
    panelKey: "panel:a",
    expanded: [],
    pressed: [],
    details: [],
    scroll: [],
  };
  queueSidebarPanelSnapshot(pending);
  clearSidebarHistory();

  await expect(
    restorePendingSidebarPanelSnapshot(
      "panel:a",
      document.createElement("section"),
    ),
  ).resolves.toBe(false);
});

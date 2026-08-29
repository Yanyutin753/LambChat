/** @vitest-environment jsdom */

import { afterEach, expect, test } from "vitest";

import {
  captureActiveSidebarPanelSnapshot,
  clearSidebarPanelSnapshots,
  queueSidebarPanelSnapshot,
  registerActiveSidebarSnapshotTarget,
  restorePendingSidebarPanelSnapshot,
  type SidebarPanelSnapshot,
} from "../sidebarPanelSnapshot";

afterEach(() => {
  clearSidebarPanelSnapshots();
  document.body.replaceChildren();
});

function setScrollableMetrics(
  element: HTMLElement,
  metrics: {
    scrollHeight: number;
    clientHeight: number;
    scrollWidth: number;
    clientWidth: number;
  },
): void {
  Object.entries(metrics).forEach(([key, value]) => {
    Object.defineProperty(element, key, { configurable: true, value });
  });
}

test("captures expanded controls, details, and every nested scroll position", () => {
  const root = document.createElement("section");
  const args = document.createElement("button");
  args.dataset.sidebarSnapshotKey = "args";
  args.setAttribute("aria-expanded", "true");
  const details = document.createElement("details");
  details.dataset.sidebarSnapshotKey = "raw";
  details.open = true;
  const nestedScroller = document.createElement("div");
  nestedScroller.dataset.sidebarSnapshotKey = "results";
  setScrollableMetrics(root, {
    scrollHeight: 900,
    clientHeight: 400,
    scrollWidth: 400,
    clientWidth: 400,
  });
  setScrollableMetrics(nestedScroller, {
    scrollHeight: 600,
    clientHeight: 200,
    scrollWidth: 500,
    clientWidth: 300,
  });
  root.scrollTop = 240;
  nestedScroller.scrollTop = 75;
  nestedScroller.scrollLeft = 36;
  root.append(args, details, nestedScroller);
  document.body.append(root);
  registerActiveSidebarSnapshotTarget("panel:a", root);

  expect(captureActiveSidebarPanelSnapshot()).toEqual({
    panelKey: "panel:a",
    expanded: [{ locator: { key: "args" }, expanded: true }],
    pressed: [],
    details: [{ locator: { key: "raw" }, open: true }],
    scroll: [
      { locator: { path: [] }, top: 240, left: 0 },
      { locator: { key: "results" }, top: 75, left: 36 },
    ],
  });
});

test("uses deterministic paths for elements without explicit snapshot keys", () => {
  const root = document.createElement("section");
  const wrapper = document.createElement("div");
  const control = document.createElement("button");
  control.setAttribute("aria-expanded", "true");
  const scroller = document.createElement("div");
  setScrollableMetrics(scroller, {
    scrollHeight: 500,
    clientHeight: 200,
    scrollWidth: 200,
    clientWidth: 200,
  });
  scroller.scrollTop = 91;
  wrapper.append(control, scroller);
  root.append(wrapper);
  registerActiveSidebarSnapshotTarget("panel:path", root);

  expect(captureActiveSidebarPanelSnapshot()).toEqual({
    panelKey: "panel:path",
    expanded: [{ locator: { path: [0, 0] }, expanded: true }],
    pressed: [],
    details: [],
    scroll: [{ locator: { path: [0, 1] }, top: 91, left: 0 }],
  });
});

test("replays expansion before scroll and skips missing snapshot elements", async () => {
  const root = document.createElement("section");
  const args = document.createElement("button");
  args.dataset.sidebarSnapshotKey = "args";
  args.setAttribute("aria-expanded", "false");
  const results = document.createElement("div");
  results.dataset.sidebarSnapshotKey = "results";
  const replayOrder: string[] = [];
  args.addEventListener("click", () => {
    replayOrder.push("args");
    args.setAttribute("aria-expanded", "true");
  });
  let restoredScrollTop = 0;
  Object.defineProperty(results, "scrollTop", {
    configurable: true,
    get: () => restoredScrollTop,
    set: (value: number) => {
      replayOrder.push("scroll");
      restoredScrollTop = value;
    },
  });
  root.append(args, results);
  document.body.append(root);

  const snapshot: SidebarPanelSnapshot = {
    panelKey: "panel:a",
    expanded: [
      { locator: { key: "args" }, expanded: true },
      { locator: { key: "removed-section" }, expanded: true },
    ],
    pressed: [],
    details: [{ locator: { key: "removed-details" }, open: true }],
    scroll: [
      { locator: { key: "results" }, top: 180, left: 24 },
      { locator: { key: "removed-scroller" }, top: 999, left: 0 },
    ],
  };
  queueSidebarPanelSnapshot(snapshot);

  await expect(
    restorePendingSidebarPanelSnapshot("panel:a", root),
  ).resolves.toBe(true);

  expect(args.getAttribute("aria-expanded")).toBe("true");
  expect(results.scrollTop).toBe(180);
  expect(results.scrollLeft).toBe(24);
  expect(replayOrder[0]).toBe("args");
  expect(replayOrder.indexOf("scroll")).toBeGreaterThan(
    replayOrder.indexOf("args"),
  );
});

test("drops a pending snapshot that belongs to a different panel", async () => {
  const root = document.createElement("section");
  const scroller = document.createElement("div");
  scroller.dataset.sidebarSnapshotKey = "results";
  root.append(scroller);
  const snapshot: SidebarPanelSnapshot = {
    panelKey: "panel:a",
    expanded: [],
    pressed: [],
    details: [],
    scroll: [{ locator: { key: "results" }, top: 64, left: 0 }],
  };
  queueSidebarPanelSnapshot(snapshot);

  // 不匹配的面板打开时旧快照直接丢弃，不残留等误命中
  await expect(
    restorePendingSidebarPanelSnapshot("panel:b", root),
  ).resolves.toBe(false);
  await expect(
    restorePendingSidebarPanelSnapshot("panel:a", root),
  ).resolves.toBe(false);
  expect(scroller.scrollTop).toBe(0);
});

test("captures and restores pressed panel controls", async () => {
  const sourceRoot = document.createElement("section");
  const sourceControl = document.createElement("button");
  sourceControl.dataset.sidebarSnapshotKey = "explorer";
  sourceControl.setAttribute("aria-pressed", "true");
  sourceRoot.append(sourceControl);
  registerActiveSidebarSnapshotTarget("panel:pressed", sourceRoot);
  const snapshot = captureActiveSidebarPanelSnapshot();

  expect(snapshot).toMatchObject({
    pressed: [{ locator: { key: "explorer" }, pressed: true }],
  });

  const restoredRoot = document.createElement("section");
  const restoredControl = document.createElement("button");
  restoredControl.dataset.sidebarSnapshotKey = "explorer";
  restoredControl.setAttribute("aria-pressed", "false");
  restoredControl.addEventListener("click", () =>
    restoredControl.setAttribute("aria-pressed", "true"),
  );
  restoredRoot.append(restoredControl);
  queueSidebarPanelSnapshot(snapshot);

  await restorePendingSidebarPanelSnapshot("panel:pressed", restoredRoot);

  expect(restoredControl.getAttribute("aria-pressed")).toBe("true");
});

test("retries nested expansion after a parent mounts its child control", async () => {
  const root = document.createElement("section");
  const parent = document.createElement("button");
  parent.dataset.sidebarSnapshotKey = "folder:parent";
  parent.setAttribute("aria-expanded", "false");
  parent.addEventListener("click", () => {
    parent.setAttribute("aria-expanded", "true");
    queueMicrotask(() => {
      const child = document.createElement("button");
      child.dataset.sidebarSnapshotKey = "folder:child";
      child.setAttribute("aria-expanded", "false");
      child.addEventListener("click", () =>
        child.setAttribute("aria-expanded", "true"),
      );
      root.append(child);
    });
  });
  root.append(parent);
  queueSidebarPanelSnapshot({
    panelKey: "panel:nested",
    expanded: [
      { locator: { key: "folder:parent" }, expanded: true },
      { locator: { key: "folder:child" }, expanded: true },
    ],
    pressed: [],
    details: [],
    scroll: [],
  });

  await restorePendingSidebarPanelSnapshot("panel:nested", root);

  expect(parent.getAttribute("aria-expanded")).toBe("true");
  expect(
    root.querySelector('[data-sidebar-snapshot-key="folder:child"]'),
  ).toHaveAttribute("aria-expanded", "true");
});

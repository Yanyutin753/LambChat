/** @vitest-environment jsdom */

import { beforeEach, expect, test, vi } from "vitest";

import {
  registerRightPanel,
  resetRightPanelCoordinator,
} from "../../../../common/rightPanelCoordinator";
import { clearSidebarHistory } from "../sidebarHistoryStore";
import { clearToolPanelRegistry } from "../toolPanelRegistry";
import {
  closePersistentToolPanel,
  getPersistentToolPanelState,
  openPersistentToolPanel,
  subscribePersistentToolPanel,
  updatePersistentToolPanel,
} from "../persistentToolPanelState.tsx";

beforeEach(() => {
  closePersistentToolPanel();
  clearSidebarHistory();
  clearToolPanelRegistry();
  resetRightPanelCoordinator();
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});

test("keyed panel updates do not replace another open panel", () => {
  closePersistentToolPanel();
  openPersistentToolPanel({
    title: "Tool result",
    status: "success",
    children: "tool body",
    panelKey: "tool:1",
  });

  updatePersistentToolPanel(
    (prev) => ({
      ...prev,
      title: "Summary",
      children: "summary body",
    }),
    "summary:1",
  );

  expect(getPersistentToolPanelState()?.title).toBe("Tool result");
  expect(getPersistentToolPanelState()?.children).toBe("tool body");

  closePersistentToolPanel();
});

test("same-reference panel update does not notify listeners", () => {
  closePersistentToolPanel();
  const calls: number[] = [];
  const unsubscribe = subscribePersistentToolPanel(() => {
    calls.push(calls.length + 1);
  });

  openPersistentToolPanel({
    title: "Tool result",
    status: "success",
    children: "tool body",
    panelKey: "tool:1",
  });
  const before = getPersistentToolPanelState();

  updatePersistentToolPanel((prev) => prev, "tool:1");

  expect(getPersistentToolPanelState()).toBe(before);
  expect(calls.length).toBe(1);

  unsubscribe();
  closePersistentToolPanel();
});

test("automatic panels do not replace deliberate work in the shared lane", () => {
  registerRightPanel({
    id: Symbol("editor"),
    kind: "editor",
    automatic: false,
    close: vi.fn(),
    opener: null,
  });

  openPersistentToolPanel({
    title: "Background task",
    status: "loading",
    children: "progress",
    panelKey: "subagent:1",
    auto: true,
  });

  expect(getPersistentToolPanelState()).toBeNull();
});

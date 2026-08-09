import { beforeEach, expect, test, vi } from "vitest";

import {
  clearSidebarHistory,
  getSidebarHistoryLength,
  goBackSidebar,
  pushCurrentPanelToHistory,
  registerPanelCapture,
} from "../sidebarHistoryStore";

beforeEach(clearSidebarHistory);

test("restores the latest captured legacy preview and clears history", () => {
  const restore = vi.fn();
  registerPanelCapture(() => ({ restore }));
  pushCurrentPanelToHistory();

  expect(getSidebarHistoryLength()).toBe(1);
  expect(goBackSidebar()).toBe(true);
  expect(restore).toHaveBeenCalledOnce();

  clearSidebarHistory();
  expect(getSidebarHistoryLength()).toBe(0);
});

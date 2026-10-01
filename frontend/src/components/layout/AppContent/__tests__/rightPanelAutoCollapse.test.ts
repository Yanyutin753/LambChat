import { expect, test } from "vitest";

import { RIGHT_PANEL_WIDTH_CHANGED_EVENT } from "../rightPanelAutoCollapse";
import {
  MINIMUM_WORKSPACE_WITH_NAVIGATION_PX,
  shouldTemporarilyCollapseNavigation,
} from "../rightPanelAutoCollapse";

const docked = {
  open: true,
  kind: "content" as const,
  presentation: "docked" as const,
  widthPct: 48,
  widthPx: 691,
  viewportWidth: 1440,
};

test("collapses navigation only when active docked width leaves too little room", () => {
  expect(
    shouldTemporarilyCollapseNavigation({
      layout: docked,
      minimumWorkspaceWithNavigationPx: 820,
      userOverrode: false,
    }),
  ).toBe(true);
  expect(
    shouldTemporarilyCollapseNavigation({
      layout: { ...docked, widthPx: 500 },
      minimumWorkspaceWithNavigationPx: 820,
      userOverrode: false,
    }),
  ).toBe(false);
  expect(
    shouldTemporarilyCollapseNavigation({
      layout: { ...docked, presentation: "overlay" },
      minimumWorkspaceWithNavigationPx: 820,
      userOverrode: false,
    }),
  ).toBe(false);
  expect(
    shouldTemporarilyCollapseNavigation({
      layout: docked,
      minimumWorkspaceWithNavigationPx: 820,
      userOverrode: true,
    }),
  ).toBe(false);
});

test("does not collapse navigation without an active panel", () => {
  expect(
    shouldTemporarilyCollapseNavigation({
      layout: null,
      minimumWorkspaceWithNavigationPx: 820,
      userOverrode: false,
    }),
  ).toBe(false);
  expect(
    shouldTemporarilyCollapseNavigation({
      layout: { ...docked, open: false },
      minimumWorkspaceWithNavigationPx: 820,
      userOverrode: false,
    }),
  ).toBe(false);
});

test("exports a stable width-changed event name for layout sync", () => {
  expect(RIGHT_PANEL_WIDTH_CHANGED_EVENT).toBe("right-panel-width-changed");
});

test("keeps both sidebars open until workspace is genuinely cramped", () => {
  for (const remainingWidth of [749, 680, 679]) {
    expect(
      shouldTemporarilyCollapseNavigation({
        layout: { ...docked, widthPx: docked.viewportWidth - remainingWidth },
        minimumWorkspaceWithNavigationPx: MINIMUM_WORKSPACE_WITH_NAVIGATION_PX,
        userOverrode: false,
      }),
    ).toBe(remainingWidth < 680);
  }
});

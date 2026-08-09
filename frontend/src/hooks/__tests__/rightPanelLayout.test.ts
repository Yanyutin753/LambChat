import { expect, test, vi } from "vitest";

import {
  clampPanelWidthPct,
  getRightPanelPresentation,
  resizePanelWidthPct,
  sanitizePanelWidthPct,
  shouldAllowAutomaticRightPanel,
  type RightPanelLayoutSnapshot,
} from "../rightPanelLayout";
import {
  getRightPanelLayoutSnapshot,
  notifyRightPanelWidthChanged,
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
} from "../rightPanelWidthEvents";

test("selects docked overlay and fullscreen presentations", () => {
  expect(getRightPanelPresentation(1200)).toBe("docked");
  expect(getRightPanelPresentation(1199)).toBe("overlay");
  expect(getRightPanelPresentation(640)).toBe("overlay");
  expect(getRightPanelPresentation(639)).toBe("fullscreen");
});

test("allows automatic panels only in an empty docked lane", () => {
  expect(
    shouldAllowAutomaticRightPanel({
      presentation: "docked",
      laneOccupied: false,
    }),
  ).toBe(true);
  expect(
    shouldAllowAutomaticRightPanel({
      presentation: "docked",
      laneOccupied: true,
    }),
  ).toBe(false);
  expect(
    shouldAllowAutomaticRightPanel({
      presentation: "overlay",
      laneOccupied: false,
    }),
  ).toBe(false);
  expect(
    shouldAllowAutomaticRightPanel({
      presentation: "fullscreen",
      laneOccupied: false,
    }),
  ).toBe(false);
});

test("sanitizes and clamps stored widths to preserve panel and workspace", () => {
  expect(sanitizePanelWidthPct("nope", 48)).toBe(48);
  expect(
    clampPanelWidthPct({
      requestedPct: 75,
      viewportWidth: 1200,
      minPanelPx: 320,
      minMainPx: 560,
    }),
  ).toBe(53);
  expect(
    clampPanelWidthPct({
      requestedPct: 10,
      viewportWidth: 1440,
      minPanelPx: 360,
      minMainPx: 560,
    }),
  ).toBe(25);
});

test("resizes with normal and shifted keyboard steps and resets home", () => {
  const base = {
    currentPct: 48,
    viewportWidth: 1440,
    minPanelPx: 360,
    minMainPx: 560,
    defaultPct: 48,
  };

  expect(
    resizePanelWidthPct({ ...base, key: "ArrowLeft", shiftKey: false }),
  ).toBe(47);
  expect(
    resizePanelWidthPct({ ...base, key: "ArrowRight", shiftKey: true }),
  ).toBe(53);
  expect(
    resizePanelWidthPct({
      ...base,
      currentPct: 60,
      key: "Home",
      shiftKey: false,
    }),
  ).toBe(48);
  expect(
    resizePanelWidthPct({ ...base, key: "Enter", shiftKey: false }),
  ).toBeNull();
});

test("publishes the active layout snapshot with the width event", () => {
  const target = new EventTarget();
  const listener = vi.fn();
  const snapshot: RightPanelLayoutSnapshot = {
    open: true,
    kind: "content",
    presentation: "docked",
    widthPct: 48,
    widthPx: 691,
    viewportWidth: 1440,
  };
  target.addEventListener(RIGHT_PANEL_WIDTH_CHANGED_EVENT, listener);

  notifyRightPanelWidthChanged(snapshot, target);

  expect(listener).toHaveBeenCalledOnce();
  expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual(snapshot);
  expect(getRightPanelLayoutSnapshot()).toEqual(snapshot);

  notifyRightPanelWidthChanged(null, target);
  expect(getRightPanelLayoutSnapshot()).toBeNull();
});

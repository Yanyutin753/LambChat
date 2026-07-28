import {
  getRightPanelWidthPct,
  nextTempAutoCollapsed,
  nextUserOverrode,
  parseWidthPct,
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
  WIDE_RIGHT_PANEL_THRESHOLD_PCT,
} from "../rightPanelAutoCollapse";

test("getRightPanelWidthPct sums open panel widths only", () => {
  expect(
    getRightPanelWidthPct({
      previewOpen: true,
      editorOpen: false,
      previewWidthPct: 60,
      editorWidthPct: 30,
    }),
  ).toBe(60);

  expect(
    getRightPanelWidthPct({
      previewOpen: true,
      editorOpen: true,
      previewWidthPct: 40,
      editorWidthPct: 30,
    }),
  ).toBe(70);

  expect(
    getRightPanelWidthPct({
      previewOpen: false,
      editorOpen: false,
      previewWidthPct: 60,
      editorWidthPct: 30,
    }),
  ).toBe(0);
});

test("nextTempAutoCollapsed collapses only when desktop wide and not overridden", () => {
  expect(
    nextTempAutoCollapsed({
      isDesktop: true,
      rightPanelWidthPct: WIDE_RIGHT_PANEL_THRESHOLD_PCT,
      userOverrode: false,
    }),
  ).toBe(true);

  expect(
    nextTempAutoCollapsed({
      isDesktop: true,
      rightPanelWidthPct: WIDE_RIGHT_PANEL_THRESHOLD_PCT - 1,
      userOverrode: false,
    }),
  ).toBe(false);

  expect(
    nextTempAutoCollapsed({
      isDesktop: true,
      rightPanelWidthPct: 80,
      userOverrode: true,
    }),
  ).toBe(false);

  expect(
    nextTempAutoCollapsed({
      isDesktop: false,
      rightPanelWidthPct: 80,
      userOverrode: false,
    }),
  ).toBe(false);
});

test("nextUserOverrode sets override on expand while wide and clears when not wide", () => {
  expect(
    nextUserOverrode({
      userOverrode: false,
      wideOpen: true,
      userExpanded: true,
    }),
  ).toBe(true);

  expect(
    nextUserOverrode({
      userOverrode: true,
      wideOpen: true,
      userExpanded: false,
    }),
  ).toBe(true);

  expect(
    nextUserOverrode({
      userOverrode: true,
      wideOpen: false,
      userExpanded: false,
    }),
  ).toBe(false);
});

test("exports a stable width-changed event name for resize sync", () => {
  expect(RIGHT_PANEL_WIDTH_CHANGED_EVENT).toBe("right-panel-width-changed");
});

test("parseWidthPct falls back on invalid values", () => {
  expect(parseWidthPct(null, 60)).toBe(60);
  expect(parseWidthPct("40", 60)).toBe(40);
  expect(parseWidthPct("nope", 60)).toBe(60);
  expect(parseWidthPct("", 30)).toBe(30);
});

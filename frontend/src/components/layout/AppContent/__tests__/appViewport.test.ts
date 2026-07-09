import {
  getAppViewportState,
  getAppViewportHeightCssValue,
  isKeyboardViewport,
  shouldPreferVisibleViewportHeight,
  shouldUpdateAppViewportHeight,
} from "../appViewport.ts";

test("uses visual viewport height only when the keyboard has reduced the viewport", () => {
  expect(
    getAppViewportHeightCssValue({
      visualViewportHeight: 512.4,
      windowInnerHeight: 800,
    }),
  ).toBe("512px");
});

test("lets CSS dynamic viewport units handle normal fullscreen sizing", () => {
  expect(
    getAppViewportHeightCssValue({
      visualViewportHeight: 760,
      windowInnerHeight: 800,
    }),
  ).toBe(null);
});

test("uses visible viewport height for direct mobile browser chrome", () => {
  expect(
    getAppViewportHeightCssValue({
      visualViewportHeight: 724.6,
      windowInnerHeight: 800,
      preferVisibleViewportHeight: true,
    }),
  ).toBe("725px");
});

test("keeps standalone fullscreen sizing even when visual viewport is shorter", () => {
  expect(
    getAppViewportHeightCssValue({
      visualViewportHeight: 724.6,
      windowInnerHeight: 800,
      preferVisibleViewportHeight: false,
    }),
  ).toBe(null);
});

test("does not force a height without visual viewport data", () => {
  expect(
    getAppViewportHeightCssValue({
      visualViewportHeight: null,
      windowInnerHeight: 760,
    }),
  ).toBe(null);
});

test("does not force a height when no measured height is available", () => {
  expect(
    getAppViewportHeightCssValue({
      visualViewportHeight: null,
      windowInnerHeight: null,
    }),
  ).toBe(null);
});

test("detects keyboard viewport only after a significant visual viewport reduction", () => {
  expect(
    isKeyboardViewport({
      visualViewportHeight: 690,
      windowInnerHeight: 800,
    }),
  ).toBe(true);
  expect(
    isKeyboardViewport({
      visualViewportHeight: 720,
      windowInnerHeight: 800,
    }),
  ).toBe(false);
});

test("ignores tiny visual viewport height jitter", () => {
  expect(shouldUpdateAppViewportHeight("512px", "512px")).toBe(false);
  expect(shouldUpdateAppViewportHeight("512px", "513px")).toBe(false);
  expect(shouldUpdateAppViewportHeight("512px", "516px")).toBe(true);
});

test("tracks keyboard viewport height, top offset, and covered bottom area", () => {
  expect(
    getAppViewportState({
      visualViewportHeight: 512.4,
      visualViewportOffsetTop: 36.2,
      windowInnerHeight: 800,
      editableFocused: true,
    }),
  ).toEqual({
    heightCssValue: "512px",
    offsetTopCssValue: "36px",
    keyboardInsetCssValue: "252px",
    keyboardOpen: true,
  });
});

test("does not force keyboard viewport variables when no editable field is focused", () => {
  expect(
    getAppViewportState({
      visualViewportHeight: 512.4,
      visualViewportOffsetTop: 36.2,
      windowInnerHeight: 800,
      editableFocused: false,
      preferVisibleViewportHeight: true,
    }),
  ).toEqual({
    heightCssValue: "512px",
    offsetTopCssValue: null,
    keyboardInsetCssValue: null,
    keyboardOpen: false,
  });
});

test("does not use visible viewport preference when visual viewport is taller", () => {
  expect(
    getAppViewportState({
      visualViewportHeight: 820,
      visualViewportOffsetTop: 0,
      windowInnerHeight: 800,
      editableFocused: false,
      preferVisibleViewportHeight: true,
    }),
  ).toEqual({
    heightCssValue: null,
    offsetTopCssValue: null,
    keyboardInsetCssValue: null,
    keyboardOpen: false,
  });
});

test("prefers visible viewport height only for direct mobile browser access", () => {
  expect(
    shouldPreferVisibleViewportHeight({
      isMobileDevice: true,
      isStandaloneDisplayMode: false,
      hasVisualViewport: true,
    }),
  ).toBe(true);
  expect(
    shouldPreferVisibleViewportHeight({
      isMobileDevice: true,
      isStandaloneDisplayMode: true,
      hasVisualViewport: true,
    }),
  ).toBe(false);
  expect(
    shouldPreferVisibleViewportHeight({
      isMobileDevice: false,
      isStandaloneDisplayMode: false,
      hasVisualViewport: true,
    }),
  ).toBe(false);
  expect(
    shouldPreferVisibleViewportHeight({
      isMobileDevice: true,
      isStandaloneDisplayMode: false,
      hasVisualViewport: false,
    }),
  ).toBe(false);
});

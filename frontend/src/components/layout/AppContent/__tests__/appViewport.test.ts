import test from "node:test";
import assert from "node:assert/strict";
import {
  getAppViewportState,
  getAppViewportHeightCssValue,
  isKeyboardViewport,
  shouldUpdateAppViewportHeight,
} from "../appViewport.ts";

test("uses visual viewport height only when the keyboard has reduced the viewport", () => {
  assert.equal(
    getAppViewportHeightCssValue({
      visualViewportHeight: 512.4,
      windowInnerHeight: 800,
    }),
    "512px",
  );
});

test("lets CSS dynamic viewport units handle normal fullscreen sizing", () => {
  assert.equal(
    getAppViewportHeightCssValue({
      visualViewportHeight: 760,
      windowInnerHeight: 800,
    }),
    null,
  );
});

test("does not force a height without visual viewport data", () => {
  assert.equal(
    getAppViewportHeightCssValue({
      visualViewportHeight: null,
      windowInnerHeight: 760,
    }),
    null,
  );
});

test("does not force a height when no measured height is available", () => {
  assert.equal(
    getAppViewportHeightCssValue({
      visualViewportHeight: null,
      windowInnerHeight: null,
    }),
    null,
  );
});

test("detects keyboard viewport only after a significant visual viewport reduction", () => {
  assert.equal(
    isKeyboardViewport({
      visualViewportHeight: 690,
      windowInnerHeight: 800,
    }),
    true,
  );
  assert.equal(
    isKeyboardViewport({
      visualViewportHeight: 720,
      windowInnerHeight: 800,
    }),
    false,
  );
});

test("ignores tiny visual viewport height jitter", () => {
  assert.equal(shouldUpdateAppViewportHeight("512px", "512px"), false);
  assert.equal(shouldUpdateAppViewportHeight("512px", "513px"), false);
  assert.equal(shouldUpdateAppViewportHeight("512px", "516px"), true);
});

test("tracks keyboard viewport height, top offset, and covered bottom area", () => {
  assert.deepEqual(
    getAppViewportState({
      visualViewportHeight: 512.4,
      visualViewportOffsetTop: 36.2,
      windowInnerHeight: 800,
      editableFocused: true,
    }),
    {
      heightCssValue: "512px",
      offsetTopCssValue: "36px",
      keyboardInsetCssValue: "252px",
      keyboardOpen: true,
    },
  );
});

test("does not force keyboard viewport variables when no editable field is focused", () => {
  assert.deepEqual(
    getAppViewportState({
      visualViewportHeight: 512.4,
      visualViewportOffsetTop: 36.2,
      windowInnerHeight: 800,
      editableFocused: false,
    }),
    {
      heightCssValue: null,
      offsetTopCssValue: null,
      keyboardInsetCssValue: null,
      keyboardOpen: false,
    },
  );
});

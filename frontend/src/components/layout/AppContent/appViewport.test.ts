import test from "node:test";
import assert from "node:assert/strict";
import { getAppViewportHeightCssValue } from "./appViewport.ts";

test("uses visual viewport height when available", () => {
  assert.equal(
    getAppViewportHeightCssValue({
      visualViewportHeight: 512.4,
      windowInnerHeight: 800,
    }),
    "512px",
  );
});

test("falls back to window inner height without visual viewport", () => {
  assert.equal(
    getAppViewportHeightCssValue({
      visualViewportHeight: null,
      windowInnerHeight: 760,
    }),
    "760px",
  );
});

test("falls back to dynamic viewport units when no measured height is available", () => {
  assert.equal(
    getAppViewportHeightCssValue({
      visualViewportHeight: null,
      windowInnerHeight: null,
    }),
    "100dvh",
  );
});

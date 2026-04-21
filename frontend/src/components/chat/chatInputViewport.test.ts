import test from "node:test";
import assert from "node:assert/strict";
import {
  getTextareaMaxHeightPx,
  resizeTextareaForContent,
} from "./chatInputViewport.ts";

test("resizeTextareaForContent keeps the newest typed content visible", () => {
  const textarea = {
    style: { height: "" },
    scrollHeight: 420,
    scrollTop: 0,
  };

  resizeTextareaForContent(textarea, 250);

  assert.equal(textarea.style.height, "250px");
  assert.equal(textarea.scrollTop, 420);
});

test("getTextareaMaxHeightPx uses a comfortable fraction of small mobile viewports", () => {
  assert.equal(
    getTextareaMaxHeightPx({ isMobile: true, viewportHeight: 500 }),
    160,
  );
});

test("getTextareaMaxHeightPx keeps the default cap on desktop and roomy mobile viewports", () => {
  assert.equal(
    getTextareaMaxHeightPx({ isMobile: false, viewportHeight: 500 }),
    250,
  );
  assert.equal(
    getTextareaMaxHeightPx({ isMobile: true, viewportHeight: 900 }),
    250,
  );
});

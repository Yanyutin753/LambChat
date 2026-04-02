import assert from "node:assert/strict";
import test from "node:test";

import { shouldHandleGlobalFileDrop } from "./globalFileDropGuards";

function createEventTarget(
  closest: (selector: string) => unknown,
): EventTarget & { closest: typeof closest } {
  return {
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
    closest,
  };
}

test("ignores global file drop when the event target opts out", () => {
  const guardElement = createEventTarget((selector: string) =>
    selector === "[data-disable-global-file-drop='true']" ? guardElement : null,
  );

  assert.equal(
    shouldHandleGlobalFileDrop({
      target: guardElement,
      composedPath: () => [],
    }),
    false,
  );
});

test("handles global file drop for normal targets", () => {
  const regularElement = createEventTarget(() => null);

  assert.equal(
    shouldHandleGlobalFileDrop({
      target: regularElement,
      composedPath: () => [],
    }),
    true,
  );
});

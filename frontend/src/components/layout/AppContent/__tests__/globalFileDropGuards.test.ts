import { shouldHandleGlobalFileDrop } from "../globalFileDropGuards";

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

  expect(
    shouldHandleGlobalFileDrop({
      target: guardElement,
      composedPath: () => [],
    }),
  ).toBe(false);
});

test("handles global file drop for normal targets", () => {
  const regularElement = createEventTarget(() => null);

  expect(
    shouldHandleGlobalFileDrop({
      target: regularElement,
      composedPath: () => [],
    }),
  ).toBe(true);
});

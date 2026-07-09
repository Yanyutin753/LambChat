import { expect, test } from "vitest";
import { getFileUploadDropdownStyle } from "../fileUploadDropdownStyle";

function rect(overrides: Partial<DOMRect>): DOMRect {
  return {
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: 0,
    bottom: 0,
    width: 0,
    height: 0,
    toJSON: () => ({}),
    ...overrides,
  } as DOMRect;
}

test("file upload dropdown clamps to the viewport right edge", () => {
  expect(
    getFileUploadDropdownStyle(rect({ left: 1735, top: 520 }), {
      viewportWidth: 1920,
      viewportHeight: 900,
    }),
  ).toMatchObject({
    left: 1704,
    width: 208,
    bottom: 388,
  });
});

test("file upload dropdown keeps a left gutter on narrow screens", () => {
  expect(
    getFileUploadDropdownStyle(rect({ left: -20, top: 120 }), {
      viewportWidth: 180,
      viewportHeight: 640,
    }),
  ).toMatchObject({
    left: 8,
    width: 164,
    bottom: 528,
  });
});

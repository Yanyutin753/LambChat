import { expect, test } from "vitest";
import { isKeyboardEventDuringComposition } from "../keyboardComposition";

test("isKeyboardEventDuringComposition detects active composition", () => {
  expect(isKeyboardEventDuringComposition({ isComposing: true })).toBe(true);
  expect(isKeyboardEventDuringComposition({ keyCode: 229 })).toBe(true);
});

test("isKeyboardEventDuringComposition passes through regular keys", () => {
  expect(isKeyboardEventDuringComposition({})).toBe(false);
  expect(
    isKeyboardEventDuringComposition({ isComposing: false, keyCode: 38 }),
  ).toBe(false);
});

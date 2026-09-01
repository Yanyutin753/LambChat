/** @vitest-environment jsdom */
import { isEditableEventTarget } from "../askHumanKeyboardGuard";

test("yields ask-human shortcuts for text inputs like the other-opinion field", () => {
  expect(isEditableEventTarget(document.createElement("input"))).toBe(true);
});

test("yields ask-human shortcuts for textareas, selects and contenteditable regions", () => {
  expect(isEditableEventTarget(document.createElement("textarea"))).toBe(true);
  expect(isEditableEventTarget(document.createElement("select"))).toBe(true);
  // jsdom 不计算 isContentEditable，这里直接桩掉只读属性来验证分支逻辑
  const richText = document.createElement("div");
  Object.defineProperty(richText, "isContentEditable", { value: true });
  expect(isEditableEventTarget(richText)).toBe(true);
});

test("keeps ask-human shortcuts for the card surface and choice buttons", () => {
  expect(isEditableEventTarget(document.createElement("div"))).toBe(false);
  expect(isEditableEventTarget(document.createElement("button"))).toBe(false);
  expect(isEditableEventTarget(null)).toBe(false);
});

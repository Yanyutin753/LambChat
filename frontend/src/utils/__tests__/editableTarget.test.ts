/** @vitest-environment jsdom */
import { isEditableEventTarget } from "../editableTarget";

function element(tag: string, attrs: Record<string, string> = {}): HTMLElement {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    el.setAttribute(key, value);
  }
  return el;
}

describe("isEditableEventTarget", () => {
  it("treats text inputs as editable", () => {
    expect(isEditableEventTarget(element("input"))).toBe(true);
    expect(isEditableEventTarget(element("textarea"))).toBe(true);
  });

  it("treats contenteditable elements as editable", () => {
    expect(isEditableEventTarget(element("div", { contenteditable: "true" }))).toBe(true);
  });

  it("does not treat plain elements as editable", () => {
    expect(isEditableEventTarget(element("div"))).toBe(false);
    expect(isEditableEventTarget(element("button"))).toBe(false);
    expect(isEditableEventTarget(document.body)).toBe(false);
  });

  it("returns false for missing or non-element targets", () => {
    expect(isEditableEventTarget(null)).toBe(false);
    expect(isEditableEventTarget(undefined)).toBe(false);
    expect(isEditableEventTarget(window)).toBe(false);
  });
});

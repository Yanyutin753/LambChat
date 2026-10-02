/** @vitest-environment jsdom */
import { afterEach, expect, test, vi } from "vitest";
import { copyToClipboard } from "../clipboard";
afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

test("legacy copy rejection is not reported as success and removes its temporary field", async () => {
  vi.stubGlobal("navigator", { clipboard: undefined });
  const exec = vi.fn(() => false);
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: exec,
  });
  await expect(copyToClipboard("Result")).rejects.toThrow();
  expect(document.querySelector("textarea")).toBeNull();
});

test("legacy copy cleans up and returns keyboard focus after a thrown failure", async () => {
  vi.stubGlobal("navigator", { clipboard: undefined });
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: () => {
      throw new Error("Unavailable");
    },
  });
  const button = document.createElement("button");
  document.body.append(button);
  button.focus();
  await expect(copyToClipboard("Result")).rejects.toThrow("Unavailable");
  expect(document.querySelector("textarea")).toBeNull();
  expect(document.activeElement).toBe(button);
});

import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");

test("desktop composer indicates focus with a single border", () => {
  const focusRule = css.match(/\.chat-input-container:focus-within\s*\{([^}]+)\}/)?.[1];
  expect(focusRule).toMatch(/border-color:\s*var\(--theme-ring\)/);
  expect(focusRule).toMatch(/outline:\s*none/);
  expect(focusRule).not.toMatch(/outline-offset/);
});

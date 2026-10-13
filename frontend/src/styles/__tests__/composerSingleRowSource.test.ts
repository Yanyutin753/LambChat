import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
test("composer actions stay on one row even in narrow columns", () => {
  expect(css).toMatch(/flex-wrap:\s*nowrap/);
  expect(css).not.toMatch(/flex-wrap:\s*wrap/);
  const chatCss = readFileSync(new URL("../chat.css", import.meta.url), "utf8");
  expect(chatCss).not.toMatch(/\.chat-input-container \.chat-input-toolbar\s*\{[^}]*flex-wrap:\s*wrap/);
  expect(css).toMatch(/container-type:\s*inline-size/);
  expect(css).toMatch(/@container composer[^}]+composer-sandbox-label/s);
  expect(css).toMatch(/@container composer[^}]+composer-usage-amount/s);
});


test("narrow composer hides toolbar labels before they truncate", () => {
  const compact = css.match(/@container composer \(max-width: 600px\) \{([\s\S]*?)\n\}/)?.[1];
  expect(compact).toMatch(/composer-toolbar-label/);
  expect(compact).toMatch(/composer-run-mode-label/);
  expect(compact).toMatch(/display: none/);
  const chip = readFileSync(new URL("../../components/chat/ToolbarChip.tsx", import.meta.url), "utf8");
  expect(chip).toContain("composer-toolbar-label");
});

test("smallest composer hides run modes together with their separators", () => {
  const smallest = css.match(/@container composer \(max-width: 320px\) \{([\s\S]*?)\n\}/)?.[1];
  expect(smallest).toMatch(/\.chat-input-toolbar \[data-composer-run-modes\]\s*\{\s*display: none;/);
  expect(smallest).toMatch(/padding-inline:\s*0/);
  expect(smallest).toMatch(/\.chat-input-toolbar > div\s*\{\s*gap:\s*0/);
});

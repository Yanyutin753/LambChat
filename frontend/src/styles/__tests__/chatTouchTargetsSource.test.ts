import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("mobile composer and scroll actions keep 44px targets; message actions compact to 36px", () => {
  const css = read("../chat.css");
  expect(css).toMatch(
    /@media \(max-width: 639px\)\s*\{[\s\S]*\.chat-input-toolbar,\s*\.chat-input-toolbar > div,\s*\.chat-message-actions\s*\{\s*gap:\s*0;/,
  );
  expect(css).toMatch(
    /\.chat-input-toolbar button,\s*\.chat-scroll-actions button\s*\{[^}]*min-width:\s*2\.75rem;[^}]*min-height:\s*2\.75rem;/,
  );
  expect(css).toMatch(
    /\.chat-message-actions button,\s*\.chat-message-feedback > \.contents > span\s*\{[^}]*min-width:\s*2\.25rem;[^}]*min-height:\s*2\.25rem;/,
  );
  expect(css).toMatch(/\.chat-message-actions\s*\{\s*flex-wrap:\s*wrap;/);
});

test("mobile and coarse-pointer code and table actions retain content padding", () => {
  const css = read("../markdown.css");
  expect(css).toMatch(
    /@media \(max-width: 639px\), \(pointer: coarse\)\s*\{\s*\.ai-code-block__copy,\s*\.ai-data-table__action\s*\{[^}]*min-width:\s*2\.75rem;[^}]*min-height:\s*2\.75rem;/,
  );
  expect(css).toMatch(/\.ai-data-table__actions\s*\{\s*gap:\s*0;/);
});

test("chat scroll controls have names and cannot focus while invisible", () => {
  const source = read("../../components/layout/AppContent/ChatView.tsx");
  expect(source).toContain('aria-label={t("common.scrollToTop")}');
  expect(source).toContain('aria-label={t("common.scrollToBottom")}');
  expect(source).toContain("disabled={isNearTop}");
  expect(source).toContain("disabled={isNearBottom}");
  expect(source).toContain("aria-hidden={isNearTop}");
  expect(source).toContain("aria-hidden={isNearBottom}");
});

test("smallest phones show a clean identity icon instead of a one-character label", () => {
  expect(read("../chat.css")).toMatch(
    /@media \(max-width: 359px\)\s*\{[\s\S]*\.chat-input-toolbar \.chat-tool-btn > div > span:nth-child\(2\)\s*\{\s*display:\s*none;/,
  );
});

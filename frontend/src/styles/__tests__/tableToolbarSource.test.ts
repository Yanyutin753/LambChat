import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(
  new URL("../../components/chat/ChatMessage/MarkdownContent.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../markdown.css", import.meta.url), "utf8");

test("table actions share the ghost button primitive and theme color", () => {
  const table = source.slice(
    source.indexOf("function TableBlock"),
    source.indexOf("const markdownComponents"),
  );
  expect(table).toMatch(/<Button\s+variant="ghost"\s+size="sm"/);
  expect(table).not.toMatch(/text-stone-|dark:text-stone-/);
  expect(css).toMatch(
    /\.ai-data-table__title,\s*\.ai-data-table__action\s*\{[^}]*color:\s*var\(--theme-text-secondary\)/,
  );
});

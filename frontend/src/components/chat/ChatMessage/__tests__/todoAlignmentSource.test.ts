import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(
  new URL("../TodoBlock.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("../../../../styles/chat.css", import.meta.url),
  "utf8",
);

test("todo header shares the body scale and centers every control on one line", () => {
  expect(source).toMatch(/chat-process-todo__header[^"\n]*items-center/);
  expect(source).toMatch(/ml-auto flex shrink-0 items-center/);
  expect(source).toMatch(/tabular-nums leading-6/);
  expect(css).toMatch(
    /\.chat-process-todo\s*\{[^}]*font-family: var\(--chat-font-family\);[^}]*font-size: var\(--tool-font-size\);/,
  );
  expect(css).toMatch(
    /\.chat-process-todo__header \.interactive-action-icon > div\s*\{[^}]*display: flex;[^}]*width: 1rem;[^}]*height: 1rem;/,
  );
});

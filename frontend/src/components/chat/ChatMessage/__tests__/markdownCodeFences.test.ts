import { normalizeMarkdownCodeFences } from "../markdownCodeFences.ts";

test("adds line breaks around fenced code markers attached to surrounding text", () => {
  expect(
    normalizeMarkdownCodeFences('before```json\n{"ok":true}\n```after'),
  ).toBe('before\n```json\n{"ok":true}\n```\nafter');
});

test("keeps inline code spans untouched", () => {
  expect(normalizeMarkdownCodeFences("Use `const value = 1` inline.")).toBe(
    "Use `const value = 1` inline.",
  );
});

test("does not add extra line breaks to already valid fenced code blocks", () => {
  const markdown = "before\n```ts\nconst value = 1;\n```\nafter";

  expect(normalizeMarkdownCodeFences(markdown)).toBe(markdown);
});

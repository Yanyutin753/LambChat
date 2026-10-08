import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../AuthPage.tsx", import.meta.url), "utf8");
test("authentication uses branded artwork without pointer-driven decoration", () => {
  expect(source).toContain('auth-brand-workspace.webp');
  expect(source).toContain('auth-brand-story');
  expect(source).not.toContain('handleGlobalCharacterPointerMove');
  expect(source).not.toContain('auth-character-purple');
});

test("auth editorial headings use the existing serif typography", () => {
  expect(source).toMatch(/<h2 className="font-serif"/);
  expect(source).toMatch(/<h1 className="font-serif /);
});

test("auth mode prompt and action share serif typography for text alignment", () => {
  const classes = source.match(/className="(auth-mode-switch[^"]*)"/)?.[1];
  expect(classes?.split(/\s+/)).toContain("font-serif");
});

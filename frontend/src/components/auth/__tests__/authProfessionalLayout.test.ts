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

test("download navigation keeps its back label accessible without crowding mobile controls", () => {
  const download = readFileSync(new URL("../../download/DownloadPage.tsx", import.meta.url), "utf8");
  expect(download).toContain('className="sr-only sm:not-sr-only"');
});

import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("profile fallback avatar uses the same yellow background and white text as user avatars", () => {
  const css = readFileSync(new URL("../profile.css", import.meta.url), "utf8");
  const fallback = css.match(/\.profile-avatar-fallback\s*\{([^}]+)\}/)?.[1];

  expect(fallback).toContain(
    "@apply bg-gradient-to-br from-amber-400 to-orange-500 text-white;",
  );
  expect(fallback).not.toMatch(/\b(?:background|color):/);
});

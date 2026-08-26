import { readFileSync } from "node:fs";
import { join } from "node:path";

const sharedPageSource = readFileSync(
  join(import.meta.dirname, "../SharedPage.tsx"),
  "utf8",
);
const sharedProjectPageSource = readFileSync(
  join(import.meta.dirname, "../SharedProjectPage.tsx"),
  "utf8",
);
const sharedPageThemeHookSource = readFileSync(
  join(import.meta.dirname, "../useSharedPageTheme.ts"),
  "utf8",
);

test("shared page top-level surfaces use theme tokens for light and dark modes", () => {
  expect(sharedPageSource).toMatch(
    /min-h-dvh bg-theme-bg text-theme-text flex items-center justify-center/,
  );
  expect(sharedPageSource).toMatch(
    /flex flex-col bg-theme-bg text-theme-text min-h-dvh font-sans border-r border-theme-border/,
  );
  expect(sharedPageSource).toMatch(/border-b border-theme-border/);
  expect(sharedPageSource).toMatch(
    /bg-\[color-mix\(in_srgb,var\(--theme-bg-card\)_82%,transparent\)\]/,
  );
  expect(sharedPageSource).toMatch(
    /max-w-6xl mx-auto px-4 sm:px-8 h-14 flex items-center justify-between/,
  );
  expect(sharedPageSource).toMatch(/bg-theme-bg-card rounded-2xl/);
  expect(sharedPageSource).toMatch(/border border-theme-border/);
  expect(sharedPageSource).not.toMatch(/bg-\[#faf9f7\]/);
  expect(sharedPageSource).not.toMatch(/dark:bg-\[#0f0e0d\]/);
});

test("shared pages route theme switching through the shared hook", () => {
  for (const source of [sharedPageSource, sharedProjectPageSource]) {
    expect(source).toMatch(
      /import \{ useSharedPageTheme \} from "\.\/useSharedPageTheme"/,
    );
    expect(source).not.toMatch(/lamb-agent-theme/);
    expect(source).not.toMatch(/localStorage\.(get|set)Item\("lambchat-theme"/);
  }
});

test("shared page theme toggle is a three-state cycle including sepia", () => {
  for (const source of [sharedPageSource, sharedProjectPageSource]) {
    expect(source).toMatch(/theme\.switchToSepia/);
    expect(source).toMatch(/<Coffee/);
  }
});

test("shared page theme hook replaces all theme classes via themeDom", () => {
  expect(sharedPageThemeHookSource).toMatch(/applyThemeToDocument\(theme\)/);
  expect(sharedPageThemeHookSource).toMatch(/resolveNextTheme/);
  expect(sharedPageThemeHookSource).toMatch(/getInitialThemePreference/);
  expect(sharedPageThemeHookSource).toMatch(/THEME_STORAGE_KEY/);
});

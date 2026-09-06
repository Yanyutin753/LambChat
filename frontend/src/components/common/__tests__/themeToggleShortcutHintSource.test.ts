import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../ThemeToggle.tsx", import.meta.url),
  "utf8",
);

test("ThemeToggle tooltip advertises the theme cycle shortcut", () => {
  expect(source).toMatch(/theme\.shortcutHint/);
});

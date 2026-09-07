import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

test("sepia secondary text meets AA contrast on the beige background", () => {
  // #7c715c on #f3edde 仅 4.11:1，加深到 #6d634e（5.07:1）
  expect(source).toMatch(/--theme-text-secondary: #6d634e;/);
});

test("sepia stays a light-family variant without the dark class contract", () => {
  expect(source).toMatch(/\.theme-sepia \{/);
  // 暗色块不被 sepia 误伤
  expect(source).toMatch(/\.dark \{\s*\n\s*\/\* ── Primary ── \*\//);
});

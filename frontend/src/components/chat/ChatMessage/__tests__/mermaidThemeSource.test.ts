import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../MermaidDiagram.tsx", import.meta.url),
  "utf8",
);

test("chat mermaid follows the active theme instead of hardcoding the default theme", () => {
  expect(source).toMatch(/useAppThemeMode\(\)/);
  expect(source).not.toMatch(/theme: "default"/);
  expect(source).toMatch(/themeMode === "sepia"/);
  // sepia 暖底对齐米黄卡片底
  expect(source).toMatch(/background: "#faf6ea"/);
});

test("chat mermaid PNG export paints the background per current theme", () => {
  expect(source).toMatch(/themeExportBackground/);
  expect(source).not.toMatch(/classList\.contains\("dark"\)/);
});

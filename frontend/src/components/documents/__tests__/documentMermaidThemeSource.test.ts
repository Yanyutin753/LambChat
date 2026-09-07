import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../previews/MermaidDiagram.tsx", import.meta.url),
  "utf8",
);

test("document mermaid preview follows the active theme via the shared hook", () => {
  expect(source).toMatch(/from ["'].*hooks\/useAppThemeMode["']/);
  expect(source).toMatch(/useAppThemeMode\(\)/);
  expect(source).not.toMatch(/classList\.contains\("dark"\)/);
  // sepia 暖底与聊天版保持一致
  expect(source).toMatch(/themeMode === "sepia"/);
  expect(source).toMatch(/background: "#faf6ea"/);
});

test("document mermaid PNG export paints the background per current theme", () => {
  expect(source).toMatch(/themeExportBackground\(themeMode\)/);
});

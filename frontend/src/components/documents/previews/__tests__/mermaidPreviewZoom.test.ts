import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../MermaidDiagram.tsx", import.meta.url),
  "utf8",
);

test("document Mermaid preview captures wheel zoom locally instead of letting the page zoom", () => {
  expect(source).toMatch(/handleWheel/);
  expect(source).toMatch(/event\.(?:ctrlKey|metaKey)/);
  expect(source).toMatch(/event\.preventDefault\(\)/);
  expect(source).toMatch(/onWheel=\{handleWheel\}/);
});

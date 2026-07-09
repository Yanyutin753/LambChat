import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../MermaidDiagram.tsx", import.meta.url),
  "utf8",
);

test("Mermaid preview captures wheel zoom locally instead of letting the page zoom", () => {
  const handleWheelMatches = source.match(/const handleWheel = useCallback/g);
  expect(handleWheelMatches?.length).toBe(2);
  expect(source).toMatch(/event\.(?:ctrlKey|metaKey)/);
  expect(source).toMatch(/event\.preventDefault\(\)/);
  expect(source).toMatch(/onWheel=\{handleWheel\}/);
});

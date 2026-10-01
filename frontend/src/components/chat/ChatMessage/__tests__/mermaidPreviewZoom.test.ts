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

test("Mermaid starts within its canvas even when the SVG has an inline max-width", () => {
  const css = readFileSync(
    new URL("../../../../styles/markdown.css", import.meta.url),
    "utf8",
  );
  expect(source).toMatch(/ref=\{ref\}\s+className="min-w-0 max-w-full"/);
  expect(css).toMatch(
    /\.mermaid-diagram svg\s*\{[^}]*max-width: 100% !important/,
  );
  expect(css).toMatch(
    /\.mermaid-diagram svg\s*\{[^}]*min-width: min\(200px, 100%\)/,
  );
});

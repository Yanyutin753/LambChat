import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../ExcalidrawPreview.tsx", import.meta.url),
  "utf8",
);

test("Excalidraw preview captures wheel zoom locally instead of letting the page zoom", () => {
  expect(source).toMatch(/handleNativeWheel/);
  expect(source).toMatch(/event\.preventDefault\(\)/);
  expect(source).toMatch(
    /addEventListener\("wheel", handleNativeWheel, \{ passive: false \}\)/,
  );
  expect(source).toMatch(/removeEventListener\("wheel", handleNativeWheel\)/);
});

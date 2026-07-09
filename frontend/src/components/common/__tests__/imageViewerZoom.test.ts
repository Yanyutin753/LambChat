import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../ImageViewer.tsx", import.meta.url),
  "utf8",
);

test("ImageViewer captures wheel zoom locally instead of letting the page zoom", () => {
  expect(source).toMatch(/addEventListener\("wheel",\s*handleNativeWheel/);
  expect(source).toMatch(/passive:\s*false/);
  expect(source).toMatch(/event\.preventDefault\(\)/);
  expect(source).toMatch(/setScale/);
});

test("ImageViewer fullscreen chrome uses CSS viewport variables for safe-area handling", () => {
  expect(source).toMatch(/--app-viewport-height/);
  expect(source).toMatch(/--app-viewport-offset-top/);
});

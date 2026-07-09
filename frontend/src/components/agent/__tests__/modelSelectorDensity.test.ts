import { readFileSync } from "node:fs";
const source = readFileSync(new URL("../ModelSelector.tsx", import.meta.url), {
  encoding: "utf8",
});

test("model selector dropdown keeps a compact visual density", () => {
  expect(source).toMatch(/w-\[min\(calc\(100vw-0\.75rem\),24rem\)\]/);
  expect(source).toMatch(/const dropdownWidth = Math\.min\(384,/);
  expect(source).toMatch(/min-h-\[38px\]/);
  expect(source).toMatch(/px-2\.5 py-1\.5/);
  expect(source).toMatch(/px-3 py-2/);
  expect(source).not.toMatch(/min-h-\[46px\]/);
  expect(source).not.toMatch(/w-\[min\(calc\(100vw-1rem\),28rem\)\]/);
});

test("model selector dropdown stays above mobile panels and fullscreen viewers", () => {
  expect(source).toMatch(
    /className="fixed z-\[10000\][^"]*w-\[min\(calc\(100vw-0\.75rem\),24rem\)\]/,
  );
});

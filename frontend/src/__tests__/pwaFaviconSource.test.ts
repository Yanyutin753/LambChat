import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

test("public assets expose a root favicon for search and browser crawlers", () => {
  const publicDir = resolve(import.meta.dirname, "../../public");
  const faviconPath = resolve(publicDir, "favicon.ico");

  expect(existsSync(faviconPath)).toBe(true);

  const faviconHeader = readFileSync(faviconPath).subarray(0, 4);
  expect([...faviconHeader]).toEqual([0, 0, 1, 0]);
});

test("index declares the root favicon before modern icon variants", () => {
  const indexHtml = readFileSync(
    resolve(import.meta.dirname, "../../index.html"),
    "utf8",
  );

  const faviconIndex = indexHtml.indexOf('href="/favicon.ico"');
  const svgIconIndex = indexHtml.indexOf('href="/icons/icon.svg"');

  expect(faviconIndex).not.toBe(-1);
  expect(svgIconIndex).not.toBe(-1);
  expect(faviconIndex < svgIconIndex).toBeTruthy();
});

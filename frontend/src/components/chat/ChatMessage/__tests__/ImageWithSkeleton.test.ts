import { readFileSync } from "node:fs";
test("block image skeleton overlays the image while loading to avoid extra blank space", () => {
  const source = readFileSync(
    new URL("../ImageWithSkeleton.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(
    /className=\{`relative my-2 overflow-hidden rounded-lg shadow/,
  );
  expect(source).toMatch(/className="skeleton-line w-full rounded-lg"/);
  expect(source).toMatch(
    /className=\{`\s*\$\{\s*!isLoaded \? "absolute inset-0 pointer-events-none" : ""\s*\}/s,
  );
});

test("image rendering keeps upload URLs web-compatible instead of forcing native proxy mode", () => {
  const source = readFileSync(
    new URL("../ImageWithSkeleton.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/getFullUrl/);
  expect(source).not.toMatch(/buildUploadProxyUrl/);
});

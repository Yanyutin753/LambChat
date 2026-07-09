import { readFileSync } from "node:fs";
test("excalidraw reveal files render with the thumbnail card preview", () => {
  const source = readFileSync(
    new URL("../FileRevealItem.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/ExcalidrawCardPreview/);
  expect(source).toMatch(/const isExcalidraw = isExcalidrawFile/);
  expect(source).toMatch(/canPreview \|\| isExcalidraw/);
  expect(source).toMatch(/<ExcalidrawCardPreview url=\{parsed\.s3Url\} \/>/);
});

test("legacy file_reveal results resolve s3_url for inline previews", () => {
  const source = readFileSync(
    new URL("../FileRevealItem.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/s3Url\s*=\s*getFullUrl\(r\.file\.s3_url\)/);
});

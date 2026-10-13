import { readFileSync } from "node:fs";
test("inline artifact thumbnails and glyphs share the same size and text alignment", () => {
  const source = readFileSync(
    new URL("../RevealArtifactsSummary.tsx", import.meta.url),
    "utf8",
  );
  expect(source).toMatch(/<span\s+className=\{inline \? "flex h-8 w-8 shrink-0 items-center justify-center" : "contents"\}\s*>\s*<ImageWithSkeleton/);
  expect(source).toMatch(/inline \? "w-6 h-6" : "w-9 h-9"/);
  expect(source).toMatch(/<FileIcon size=\{24\}/);
  expect(source).toMatch(/<Icon\s+size=\{24\}/);
  expect(source).toMatch(/<FolderIcon size=\{24\}/);
});

test("reveal artifacts summary mirrors the file tree view row details", () => {
  const summarySource = readFileSync(
    new URL("../RevealArtifactsSummary.tsx", import.meta.url),
    "utf8",
  );

  expect(summarySource).toMatch(/const imageSrc = isImageFile\(ext\)/);
  expect(summarySource).toMatch(/<ImageWithSkeleton[\s\S]*src=\{imageSrc\}/);
  expect(summarySource).toMatch(/formatSize\(dirSize\)/);
});

test("all files image rows open an ImageViewer gallery with navigation", () => {
  const summarySource = readFileSync(
    new URL("../RevealArtifactsSummary.tsx", import.meta.url),
    "utf8",
  );

  expect(summarySource).toMatch(
    /import\s+\{[^}]*ImageViewer[^}]*\}\s+from\s+"..\/..\/common"/,
  );
  expect(summarySource).toMatch(/getRevealArtifactImagePreviewItems/);
  expect(summarySource).toMatch(/onOpenImagePreview=/);
  expect(summarySource).toMatch(/<ImageViewer[\s\S]*?\bonPrevious=/);
  expect(summarySource).toMatch(/<ImageViewer[\s\S]*?\bonNext=/);
  expect(summarySource).toMatch(/<ImageViewer[\s\S]*?\bpositionLabel=/);
});

test("all files summary waits until the message stops streaming", () => {
  const summarySource = readFileSync(
    new URL("../RevealArtifactsSummary.tsx", import.meta.url),
    "utf8",
  );

  expect(summarySource).toMatch(
    /if\s*\(\s*isStreaming\s*\|\|\s*artifacts\.length\s*===\s*0\s*\)/,
  );
});

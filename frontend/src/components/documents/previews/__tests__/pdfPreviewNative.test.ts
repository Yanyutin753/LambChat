import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../PdfPreview.tsx", import.meta.url),
  "utf8",
);
const frontendPackage = JSON.parse(
  readFileSync(new URL("../../../../../package.json", import.meta.url), "utf8"),
);

test("PDF preview renders through PDF.js instead of a native embedded viewer", () => {
  expect(source).toMatch(/from\s+"react-pdf"/);
  expect(source).toMatch(/\bDocument\b/);
  expect(source).toMatch(/\bPage\b/);
  expect(source).not.toMatch(/<iframe\b/);
});

test("PDF preview renders all pages in a continuous scroll surface", () => {
  expect(source).toMatch(/numPages/);
  expect(source).toMatch(/Array\.from\(\{\s*length:\s*numPages\s*\}/);
  expect(source).toMatch(/pageNumber=\{pageNumber \+ 1\}/);
  expect(source).toMatch(/DocumentViewerFrame/);
});

test("PDF preview uses shared fit-relative zoom controls without page navigation", () => {
  expect(source).toMatch(/DocumentViewerFrame/);
  expect(source).not.toMatch(/goToPrevPage|goToNextPage/);
  expect(source).not.toMatch(/ChevronLeft|ChevronRight/);
  expect(source).not.toMatch(/previousPage|nextPage/);
  expect(source).not.toMatch(/Maximize2|Minus|Plus/);
});

test("PDF preview leaves wheel, pointer, and touch movement to native scrolling", () => {
  expect(source).not.toMatch(/handleWheel|onWheel=/);
  expect(source).not.toMatch(/handleDoubleTapZoom|onDoubleClick=/);
  expect(source).not.toMatch(/handleTouchStart|handleTouchMove|handleTouchEnd/);
  expect(source).not.toMatch(/touchAction:\s*"none"/);
  expect(source).not.toMatch(/event\.preventDefault\(\)/);
});

test("PDF preview keeps a user-facing fallback when rendering fails", () => {
  expect(source).toMatch(/loadFailed/);
  expect(source).toMatch(/documents\.pdfPreviewUnavailable/);
  expect(source).toMatch(/documents\.openInNewTab/);
});

test("PDF preview uses a PDF.js worker version compatible with react-pdf", () => {
  expect(frontendPackage.dependencies["react-pdf"]).toBe("^10.5.0");
  expect(frontendPackage.dependencies["pdfjs-dist"]).toBe("^5.4.296");
});

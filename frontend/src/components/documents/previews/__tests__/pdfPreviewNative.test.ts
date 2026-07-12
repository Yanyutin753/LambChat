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
  expect(source).toMatch(/overflow-auto/);
});

test("PDF preview keeps zoom controls without page navigation controls", () => {
  expect(source).toMatch(/zoomIn/);
  expect(source).toMatch(/zoomOut/);
  expect(source).toMatch(/fitWidth/);
  expect(source).not.toMatch(/goToPrevPage|goToNextPage/);
  expect(source).not.toMatch(/ChevronLeft|ChevronRight/);
  expect(source).not.toMatch(/previousPage|nextPage/);
});

test("PDF preview captures wheel zoom locally instead of letting the page zoom", () => {
  expect(source).toMatch(/handleWheel/);
  expect(source).toMatch(/event\.(?:ctrlKey|metaKey)/);
  expect(source).toMatch(/event\.preventDefault\(\)/);
  expect(source).toMatch(/onWheel=\{handleWheel\}/);
});

test("PDF preview supports ImageViewer-style mobile gestures", () => {
  expect(source).toMatch(/getPinchDistance/);
  expect(source).toMatch(/handleTouchStart/);
  expect(source).toMatch(/handleTouchMove/);
  expect(source).toMatch(/handleTouchEnd/);
  expect(source).toMatch(/handleDoubleTapZoom/);
  expect(source).toMatch(/touchAction:\s*"none"/);
  expect(source).toMatch(/scrollLeft/);
  expect(source).toMatch(/scrollTop/);
});

test("PDF preview keeps a user-facing fallback when rendering fails", () => {
  expect(source).toMatch(/loadFailed/);
  expect(source).toMatch(/documents\.pdfPreviewUnavailable/);
  expect(source).toMatch(/documents\.openInNewTab/);
});

test("PDF preview uses a PDF.js worker version compatible with react-pdf", () => {
  expect(frontendPackage.dependencies["react-pdf"]).toBe("^10.4.0");
  expect(frontendPackage.dependencies["pdfjs-dist"]).toBe("^5.4.296");
});

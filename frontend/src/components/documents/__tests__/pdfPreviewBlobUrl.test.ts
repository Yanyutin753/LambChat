import { readFileSync } from "node:fs";
const stateSource = readFileSync(
  new URL("../useDocumentPreviewState.ts", import.meta.url),
  "utf8",
);
const contentSource = readFileSync(
  new URL("../DocumentPreviewContent.tsx", import.meta.url),
  "utf8",
);

test("PDF preview uses a local PDF blob URL instead of embedding the download URL directly", () => {
  const pdfBranch = stateSource.match(
    /if \(advancedFileViewersEnabled && resolvedPdfFile\) \{(?<body>[\s\S]*?)\r?\n\s*\}\r?\n\r?\n\s*if \(resolvedVideoFile\)/,
  )?.groups?.body;

  expect(pdfBranch).toBeTruthy();
  expect(pdfBranch).toMatch(/fetchDocumentArrayBuffer\(readUrl\)/);
  expect(pdfBranch).toMatch(
    /new Blob\(\[.*\], \{ type: "application\/pdf" \}\)/s,
  );
  expect(pdfBranch).toMatch(/URL\.createObjectURL/);
  expect(pdfBranch).not.toMatch(/setPdfUrl\(url\)/);
});

test("PDF preview revokes generated blob URLs", () => {
  expect(stateSource).toMatch(/if \(pdfUrl\?\.startsWith\("blob:"\)\)/);
  expect(stateSource).toMatch(/URL\.revokeObjectURL\(pdfUrl\)/);
});

test("unsupported preview files render a guardrail instead of auto-downloading", () => {
  const unsupportedBranch = stateSource.match(
    /else if \(unsupportedPreviewFile\) \{(?<body>[\s\S]*?)\n\s*\}\s*else if \(advancedFileViewersEnabled && \(wordPreviewFile/,
  )?.groups?.body;

  expect(unsupportedBranch).toBeTruthy();
  expect(unsupportedBranch).not.toMatch(/document\.createElement\("a"\)/);
  expect(contentSource).toMatch(/documents\.unsupportedFilePreview/);
  expect(contentSource).toMatch(/documents\.unsupportedFileHint/);
});

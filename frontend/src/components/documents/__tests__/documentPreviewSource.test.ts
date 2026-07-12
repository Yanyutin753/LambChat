import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../useDocumentPreviewState.ts", import.meta.url),
  "utf8",
);

test("DocumentPreview resolves signed URLs before loading from storage", () => {
  expect(source).toMatch(/buildUploadProxyUrl/);
  expect(source).toMatch(/buildUploadProxyUrlFromKey/);
  expect(source).toMatch(/getFullUrl/);
  expect(source).toMatch(
    /const resolvedSignedUrl = getFullUrl\(signedUrl\) \|\| signedUrl/,
  );
  expect(source).toMatch(/setResolvedUrl\(url\)/);
  expect(source).not.toMatch(/const url =\s+signedUrl \|\|/);
});

test("DocumentPreview fetches file content through the upload proxy", () => {
  expect(source).toMatch(/const readUrl = buildUploadProxyUrl\(url\) \|\| url/);
  expect(source).toMatch(/fetchDocumentArrayBuffer\(readUrl\)/);
  expect(source).toMatch(/fetchDocumentText\(readUrl\)/);
});

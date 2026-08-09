import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../WordPreview.tsx", import.meta.url),
  "utf8",
);

test("successful DOCX previews use the shared paged document reader", () => {
  expect(source).toMatch(/DocumentViewerFrame/);
  expect(source).toMatch(/ScaledDocumentContent/);
  expect(source).not.toMatch(/max-w-\[816px\]/);
  expect(source).not.toMatch(/min-h-\[1056px\]/);
});

test("reflowed Word fallbacks remain a constrained reading card", () => {
  expect(source).toMatch(/max-w-3xl/);
  expect(source).toMatch(/processedHtml/);
});

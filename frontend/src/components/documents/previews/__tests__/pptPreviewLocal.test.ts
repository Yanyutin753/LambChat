import { readFileSync } from "node:fs";
const previewSource = readFileSync(
  new URL("../PptPreview.tsx", import.meta.url),
  "utf8",
);
const stateSource = readFileSync(
  new URL("../../useDocumentPreviewState.ts", import.meta.url),
  "utf8",
);
const frontendPackage = JSON.parse(
  readFileSync(new URL("../../../../../package.json", import.meta.url), "utf8"),
);

test("PPT preview renders locally instead of embedding Office Online", () => {
  expect(previewSource).toMatch(/from\s+"@jvmr\/pptx-to-html"/);
  expect(previewSource).not.toMatch(/from\s+"pptx-preview"/);
  expect(previewSource).not.toMatch(/view\.officeapps\.live\.com/);
  expect(previewSource).not.toMatch(/<iframe\b/);
  expect(previewSource).not.toMatch(/https:\/\/.*office/i);
});

test("PPT preview receives file bytes for browser-side rendering", () => {
  const pptBranch = stateSource.match(
    /if \(pptFile\) \{(?<body>[\s\S]*?)\n\s*\}\n\n\s*if \(htmlFile\)/,
  )?.groups?.body;

  expect(pptBranch).toBeTruthy();
  expect(pptBranch).toMatch(/fetchDocumentArrayBuffer\(readUrl\)/);
  expect(pptBranch).toMatch(/setPptxBuffer\(buffer\)/);
  expect(pptBranch).not.toMatch(/setPptUrl\(url\)/);
});

test("PPT preview does not let placeholder text content bypass storage bytes", () => {
  expect(stateSource).toMatch(
    /content !== undefined && !\(pptFile && \(s3Key \|\| signedUrl\)\)/,
  );
});

test("PPT preview dependency is declared for bundled local rendering", () => {
  expect(frontendPackage.dependencies["@jvmr/pptx-to-html"]).toBe("^1.0.1");
  expect(frontendPackage.dependencies["pptx-preview"]).toBe(undefined);
});

test("PPT preview normalizes mislabeled SVG image data URLs before injection", async () => {
  const { normalizePptxRenderedHtml } = await import("../pptHtmlPreview.ts");
  const svgBase64 = btoa('<svg xmlns="http://www.w3.org/2000/svg"></svg>');

  const html = normalizePptxRenderedHtml(
    `<img src="data:image/png;base64,${svgBase64}" />`,
  );

  expect(html).toMatch(/data:image\/svg\+xml;base64,/);
  expect(html).not.toMatch(/data:image\/png;base64,/);
});

test("PPT preview does not rerender slides from resize measurements", () => {
  expect(previewSource).not.toMatch(/containerWidth/);
  expect(previewSource).not.toMatch(/\[arrayBuffer,\s*previewWidth\]/);
  expect(previewSource).toMatch(
    /pptxToHtml\(arrayBuffer\.slice\(0\),\s*\{[\s\S]*width:\s*PPT_PREVIEW_WIDTH/,
  );
  expect(previewSource).toMatch(/\[arrayBuffer\]/);
});

test("PPT preview uses the shared scrollable document reader", () => {
  expect(previewSource).toMatch(/DocumentViewerFrame/);
  expect(previewSource).toMatch(/ScaledDocumentContent/);
  expect(previewSource).not.toMatch(/addEventListener\("wheel"/);
  expect(previewSource).not.toMatch(/handleNativeWheel/);
  expect(previewSource).not.toMatch(/event\.preventDefault\(\)/);
  expect(previewSource).not.toMatch(/handleMouseDown|onMouseDown=/);
  expect(previewSource).not.toMatch(
    /handleTouchStart|handleTouchMove|handleTouchEnd/,
  );
  expect(previewSource).not.toMatch(/position\.x|position\.y/);
});

test("PPT preview treats 100 percent zoom as fitting the sidebar width", () => {
  expect(previewSource).toMatch(
    /DocumentViewerFrame\s+naturalWidth=\{PPT_PREVIEW_WIDTH\}/,
  );
  expect(previewSource).toMatch(/displayScale/);
  expect(previewSource).toMatch(/naturalHeight=\{contentHeight\}/);
});

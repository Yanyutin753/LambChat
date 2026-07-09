import {
  getFileTypeInfo,
  getFileLinkInfo,
  isCadFile,
  isDwgFile,
  isDxfFile,
  isFileLink,
  isPreviewableFile,
} from "../index";

Object.defineProperty(globalThis, "window", {
  value: { location: { origin: "https://example.test" } },
  configurable: true,
});

test("recognizes CAD file extensions", () => {
  expect(isCadFile("dxf")).toBe(true);
  expect(isCadFile("dwg")).toBe(true);
  expect(isDxfFile("dxf")).toBe(true);
  expect(isDxfFile("dwg")).toBe(false);
  expect(isDwgFile("dwg")).toBe(true);
  expect(isDwgFile("dxf")).toBe(false);
});

test("treats CAD files as previewable links", () => {
  expect(isPreviewableFile("dxf")).toBe(true);
  expect(isPreviewableFile("dwg")).toBe(true);

  const dxfLink = isFileLink("/uploads/site-plan.dxf");
  expect(dxfLink.isFile).toBe(true);
  expect(dxfLink.fileName).toBe("site-plan.dxf");

  const dwgLink = isFileLink("/uploads/site-plan.dwg");
  expect(dwgLink.isFile).toBe(true);
  expect(dwgLink.fileName).toBe("site-plan.dwg");
});

test("does not mark ebook formats as previewable without a renderer", () => {
  expect(isPreviewableFile("epub")).toBe(false);
  expect(isPreviewableFile("mobi")).toBe(false);
});

test("recognizes CAD links from labels and download query metadata", () => {
  const labelled = getFileLinkInfo(
    "/api/upload/file/opaque-key",
    "site-plan.dwg",
  );
  expect(labelled.isFile).toBe(true);
  expect(labelled.fileName).toBe("site-plan.dwg");

  const queryNamed = getFileLinkInfo(
    "/api/upload/file/opaque-key?filename=site-plan.dxf",
  );
  expect(queryNamed.isFile).toBe(true);
  expect(queryNamed.fileName).toBe("site-plan.dxf");
});

test("maps CAD files to a document-style file type", () => {
  const dxfInfo = getFileTypeInfo("site-plan.dxf");
  expect(dxfInfo.label).toBe("DXF");
  expect(dxfInfo.category).toBe("document");

  const dwgInfo = getFileTypeInfo("site-plan.dwg");
  expect(dwgInfo.label).toBe("DWG");
  expect(dwgInfo.category).toBe("document");
});

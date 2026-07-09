import { isLegacyDocFile, isWordPreviewFile } from "../index";

test("treats legacy .doc files as Word preview candidates", () => {
  expect(isWordPreviewFile("doc")).toBe(true);
  expect(isWordPreviewFile("docx")).toBe(true);
  expect(isLegacyDocFile("doc")).toBe(false);
});

import { isLegacyDocArrayBuffer } from "../legacyDocPreviewUtils";

test("detects legacy Word compound document signatures", () => {
  const doc = new Uint8Array([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]);
  expect(isLegacyDocArrayBuffer(doc.buffer)).toBe(true);

  const docx = new Uint8Array([0x50, 0x4b, 0x03, 0x04]);
  expect(isLegacyDocArrayBuffer(docx.buffer)).toBe(false);
});

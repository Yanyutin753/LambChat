import assert from "node:assert/strict";
import test from "node:test";

import {
  decodeTextLikeArrayBuffer,
  isDocxZipArrayBuffer,
} from "../wordPreviewUtils.ts";

test("detects DOCX zip signatures before attempting preview conversion", () => {
  const regularZip = new Uint8Array([0x50, 0x4b, 0x03, 0x04]);
  const emptyZip = new Uint8Array([0x50, 0x4b, 0x05, 0x06]);
  const splitZip = new Uint8Array([0x50, 0x4b, 0x07, 0x08]);
  const mixedZipMarker = new Uint8Array([0x50, 0x4b, 0x03, 0x08]);
  const htmlResponse = new TextEncoder().encode("<!doctype html>");

  assert.equal(isDocxZipArrayBuffer(regularZip.buffer), true);
  assert.equal(isDocxZipArrayBuffer(emptyZip.buffer), true);
  assert.equal(isDocxZipArrayBuffer(splitZip.buffer), true);
  assert.equal(isDocxZipArrayBuffer(mixedZipMarker.buffer), false);
  assert.equal(isDocxZipArrayBuffer(htmlResponse.buffer), false);
});

test("decodes text-like buffers for mislabeled Word preview files", () => {
  const text = new TextEncoder().encode("入党申请书\n\n敬爱的党组织：");
  const binary = new Uint8Array([0x00, 0x01, 0x02, 0x03, 0xff]);

  assert.equal(
    decodeTextLikeArrayBuffer(text.buffer),
    "入党申请书\n\n敬爱的党组织：",
  );
  assert.equal(decodeTextLikeArrayBuffer(binary.buffer), null);
});

import { expect, test } from "vitest";
import { decodePreviewText, formatHexPreview } from "../fileBytesPreview";
test("decodes legacy Chinese text without a response charset", () => {
  expect(decodePreviewText(new Uint8Array([0xd6, 0xd0, 0xce, 0xc4]))).toBe(
    "中文",
  );
});
test("keeps explicit charset and BOM authoritative over legacy fallback", () => {
  expect(decodePreviewText(new Uint8Array([0xd6, 0xd0]), "utf-8")).toBeNull();
  expect(
    decodePreviewText(new Uint8Array([0xef, 0xbb, 0xbf, 0xd6, 0xd0])),
  ).toBeNull();
});
test("decodes UTF-8 and Windows UTF-16 scripts without executing content", () => {
  expect(
    decodePreviewText(new TextEncoder().encode("Write-Output '中文'")),
  ).toBe("Write-Output '中文'");
  expect(decodePreviewText(new Uint8Array([255, 254, 36, 0, 65, 0]))).toBe(
    "$A",
  );
  expect(decodePreviewText(new Uint8Array([254, 255, 0, 36, 0, 65]))).toBe(
    "$A",
  );
});
test("binary bytes have an exact offset, hexadecimal and safe ASCII preview", () => {
  const bytes = new Uint8Array([80, 75, 0, 255, 60]);
  expect(decodePreviewText(bytes)).toBeNull();
  expect(formatHexPreview(bytes)).toContain("00000000  50 4b 00 ff 3c");
  expect(formatHexPreview(bytes)).toContain("PK..<");
});

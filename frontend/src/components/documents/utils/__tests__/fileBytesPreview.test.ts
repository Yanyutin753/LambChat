import { expect, test } from "vitest";
import { decodePreviewText, formatHexPreview } from "../fileBytesPreview";
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

import { expect, test } from "vitest";
import { formatFileSize } from "../fileSize";
test("unknown file sizes are not presented as empty files", () => {
  expect(formatFileSize(null)).toBe("");
  expect(formatFileSize(undefined)).toBe("");
  expect(formatFileSize(Number.NaN)).toBe("");
  expect(formatFileSize(-1)).toBe("");
  expect(formatFileSize(0)).toBe("0 B");
  expect(formatFileSize(2048)).toBe("2.0 KB");
});

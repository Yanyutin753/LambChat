import { readLineRangeLabel } from "../toolUtils.ts";

test("returns empty string when neither offset nor limit is given", () => {
  expect(readLineRangeLabel(undefined, undefined)).toBe("");
});

test("formats inclusive start-end range from 0-based offset and limit", () => {
  expect(readLineRangeLabel(0, 100)).toBe(":L1-100");
  expect(readLineRangeLabel(99, 200)).toBe(":L100-299");
});

test("starts from line 1 when only limit is given", () => {
  expect(readLineRangeLabel(undefined, 80)).toBe(":L1-80");
});

test("shows start line only when limit is absent", () => {
  expect(readLineRangeLabel(130, undefined)).toBe(":L131");
});

test("treats zero limit as absent", () => {
  expect(readLineRangeLabel(0, 0)).toBe(":L1");
});

import { getFileAccept } from "../fileAccept";
import type { FileCategory } from "../../../types";

test("omits accept when all four categories are permitted so Android opens the full picker", () => {
  expect(getFileAccept(["image", "video", "audio", "document"])).toBe("");
});

test("omits accept regardless of category order when all four are permitted", () => {
  expect(getFileAccept(["document", "audio", "image", "video"])).toBe("");
});

test("keeps precise filtering for permitted-category subsets", () => {
  const accept = getFileAccept(["image", "document"]);
  expect(accept).toContain("image/*");
  expect(accept).toContain(".pdf");
});

test("subset accept excludes non-permitted category filters", () => {
  const accept = getFileAccept(["document"] as FileCategory[]);
  expect(accept).not.toContain("image/*");
  expect(accept).not.toContain("video/*");
  expect(accept).not.toContain("audio/*");
});

test("empty category list yields no accept restriction", () => {
  expect(getFileAccept([])).toBe("");
});

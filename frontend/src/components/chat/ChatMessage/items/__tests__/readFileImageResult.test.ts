import { readFileSync } from "node:fs";
import { extractReadFileImageResult } from "../readFileImageResult.ts";

const binaryReadResult = {
  key: "revealed_files/6999be7275bdd6b1d868075b/20260920_174200_41fef6_shot.png",
  url: "https://lambchat.com/api/upload/file/revealed_files/6999be7275bdd6b1d868075b/20260920_174200_41fef6_shot.png",
  name: "20260920_174200_41fef6_shot.png",
  mime_type: "image/png",
  size: 12345,
  _meta: { path: "/workspace/shot.png", source: "read_file_binary_upload" },
};

test("extracts image preview from binary read_file JSON string result", () => {
  expect(
    extractReadFileImageResult(JSON.stringify(binaryReadResult)),
  ).toEqual({
    url: "https://lambchat.com/api/upload/file/revealed_files/6999be7275bdd6b1d868075b/20260920_174200_41fef6_shot.png",
    name: "20260920_174200_41fef6_shot.png",
    contentType: "image/png",
    size: 12345,
  });
});

test("accepts already-parsed object results", () => {
  expect(extractReadFileImageResult(binaryReadResult)?.name).toBe(
    "20260920_174200_41fef6_shot.png",
  );
});

test("resolves relative binary read_file URLs through the configured API base", () => {
  expect(
    extractReadFileImageResult(
      JSON.stringify({
        ...binaryReadResult,
        url: "/api/upload/file/revealed_files/local.png",
      }),
      "https://chat.example.com/",
    )?.url,
  ).toBe("https://chat.example.com/api/upload/file/revealed_files/local.png");
});

test("falls back to the URL extension when mime_type is missing", () => {
  expect(
    extractReadFileImageResult(
      JSON.stringify({ ...binaryReadResult, mime_type: undefined }),
    ),
  ).not.toBeNull();
});

test("ignores non-image binary read_file results", () => {
  expect(
    extractReadFileImageResult(
      JSON.stringify({
        ...binaryReadResult,
        url: "https://lambchat.com/api/upload/file/revealed_files/report.pdf",
        mime_type: "application/pdf",
      }),
    ),
  ).toBeNull();
});

test("ignores results that are not binary read_file uploads", () => {
  expect(extractReadFileImageResult("plain text content")).toBeNull();
  expect(extractReadFileImageResult("{ not json")).toBeNull();
  expect(extractReadFileImageResult(undefined)).toBeNull();
  expect(
    extractReadFileImageResult(
      JSON.stringify({
        ...binaryReadResult,
        _meta: { path: "/a.png", source: "something_else" },
      }),
    ),
  ).toBeNull();
  expect(
    extractReadFileImageResult({ url: "https://x.example.com/a.png" }),
  ).toBeNull();
});

test("read_file image previews open the shared image viewer", () => {
  const source = readFileSync(
    new URL("../ReadFileItem.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/extractReadFileImageResult/);
  expect(source).toMatch(/<ImageWithSkeleton/);
  expect(source).toMatch(/useImagePreviewFallback/);
});

test("image analyze previews render clickable thumbnail groups", () => {
  const source = readFileSync(
    new URL("../ImageAnalyzeItem.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/<ImageWithSkeleton/);
  expect(source).toMatch(/buildChatThumbUrl/);
  expect(source).toMatch(/useImagePreviewFallback/);
  // 网格分组展示，而不是逐行 URL 文本
  expect(source).toMatch(/grid/);
  expect(source).not.toMatch(/break-all">\{truncate\(url/);
});

test("image preview fallback hook wires the session gallery with a standalone viewer", () => {
  const source = readFileSync(
    new URL("../imagePreviewFallback.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/useSessionImageGallery/);
  expect(source).toMatch(/<ImageViewer/);
});

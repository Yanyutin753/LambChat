import { readFileSync } from "node:fs";
import {
  extractGeneratedImageResults,
  extractSingleImageResult,
} from "../toolImageResults.ts";

test("extracts generated image uploads from Image Generate tool results", () => {
  const result = {
    success: true,
    images: [
      {
        url: "https://lambchat.com/api/upload/file/generated-images/6999be7275bdd6b1d868075b/20260527_164547_8ee7dae2_generated-20260527_164547-1.png",
        key: "generated-images/6999be7275bdd6b1d868075b/20260527_164547_8ee7dae2_generated-20260527_164547-1.png",
        content_type: "image/png",
      },
    ],
  };

  expect(extractGeneratedImageResults(result)).toEqual([
    {
      url: "https://lambchat.com/api/upload/file/generated-images/6999be7275bdd6b1d868075b/20260527_164547_8ee7dae2_generated-20260527_164547-1.png",
      name: "20260527_164547_8ee7dae2_generated-20260527_164547-1.png",
      contentType: "image/png",
    },
  ]);
});

test("resolves generated image upload URLs through the configured API base", () => {
  const result = {
    success: true,
    images: [
      {
        url: "/api/upload/file/generated-images/local.png",
        content_type: "image/png",
      },
    ],
  };

  expect(
    extractGeneratedImageResults(result, "https://chat.example.com/"),
  ).toEqual([
    {
      url: "https://chat.example.com/api/upload/file/generated-images/local.png",
      name: "local.png",
      contentType: "image/png",
    },
  ]);
});

test("ignores non-image upload entries", () => {
  expect(
    extractGeneratedImageResults({
      success: true,
      images: [
        {
          url: "https://lambchat.com/api/upload/file/report.pdf",
          content_type: "application/pdf",
        },
      ],
    }),
  ).toEqual([]);
});

test("generated image result previews open the shared ImageViewer", () => {
  const source = readFileSync(
    new URL("../McpBlockPreview.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(
    /import\s+\{[^}]*ImageViewer[^}]*\}\s+from\s+"..\/..\/..\/common"/s,
  );
  expect(source).toMatch(/<ImageViewer[\s\S]*?\bsrc=\{activeImage\.url\}/);
  expect(source).toMatch(/<ImageViewer[\s\S]*?\bonPrevious=/);
  expect(source).toMatch(/<ImageViewer[\s\S]*?\bonNext=/);
});

test("generated image result previews load eagerly for browser captures", () => {
  const source = readFileSync(
    new URL("../McpBlockPreview.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/<ImageWithSkeleton[\s\S]*?\bloading="eager"/);
});

test("image generation prompt can be copied from the detail panel", () => {
  const source = readFileSync(
    new URL("../ImageGenerateItem.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(
    /import\s+\{[^}]*CopyButton[^}]*\}\s+from\s+"..\/..\/..\/common"/s,
  );
  expect(source).toMatch(/<CopyButton[\s\S]*?\btext=\{prompt\}/);
});

test("extractSingleImageResult recognizes single image upload payloads", () => {
  expect(
    extractSingleImageResult({
      url: "https://lambchat.com/api/upload/file/revealed_files/shot.png",
      mime_type: "image/png",
      size: 1024,
    }),
  ).toEqual({
    url: "https://lambchat.com/api/upload/file/revealed_files/shot.png",
    name: "shot.png",
  });

  expect(
    extractSingleImageResult(
      JSON.stringify({ url: "/api/upload/file/x/frame.jpg" }),
      "https://chat.example.com/",
    ),
  ).toEqual({
    url: "https://chat.example.com/api/upload/file/x/frame.jpg",
    name: "frame.jpg",
  });

  // 非图片 / 非对象 / 缺 url 一律不识别
  expect(
    extractSingleImageResult({
      url: "https://lambchat.com/api/upload/file/report.pdf",
      mime_type: "application/pdf",
    }),
  ).toBeNull();
  expect(extractSingleImageResult("plain text")).toBeNull();
  expect(extractSingleImageResult({ url: "https://x.example.com/page" })).toBeNull();
});

test("generic tool results with a single image payload render the shared preview", () => {
  const source = readFileSync(
    new URL("../McpBlockPreview.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/extractSingleImageResult/);
});

test("video analyze previews play inline instead of dumping URLs", () => {
  const source = readFileSync(
    new URL("../VideoAnalyzeItem.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/<video/);
  expect(source).toMatch(/mediaProxyFallbackSrc/);
  expect(source).not.toMatch(/break-all">\{truncate\(url/);
});

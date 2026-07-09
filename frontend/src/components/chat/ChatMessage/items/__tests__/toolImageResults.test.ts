import { readFileSync } from "node:fs";
import { extractGeneratedImageResults } from "../toolImageResults.ts";

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

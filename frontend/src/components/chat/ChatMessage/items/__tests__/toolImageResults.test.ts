import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
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

  assert.deepEqual(extractGeneratedImageResults(result), [
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

  assert.deepEqual(
    extractGeneratedImageResults(result, "https://chat.example.com/"),
    [
      {
        url: "https://chat.example.com/api/upload/file/generated-images/local.png",
        name: "local.png",
        contentType: "image/png",
      },
    ],
  );
});

test("ignores non-image upload entries", () => {
  assert.deepEqual(
    extractGeneratedImageResults({
      success: true,
      images: [
        {
          url: "https://lambchat.com/api/upload/file/report.pdf",
          content_type: "application/pdf",
        },
      ],
    }),
    [],
  );
});

test("generated image result previews open the shared ImageViewer", () => {
  const source = readFileSync(
    new URL("../McpBlockPreview.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    source,
    /import\s+\{[^}]*ImageViewer[^}]*\}\s+from\s+"..\/..\/..\/common"/s,
    "generated image results should use the shared image viewer",
  );
  assert.match(
    source,
    /<ImageViewer[\s\S]*?\bsrc=\{activeImage\.url\}/,
    "clicking a generated image should open ImageViewer with that image URL",
  );
  assert.match(
    source,
    /<ImageViewer[\s\S]*?\bonPrevious=/,
    "generated image ImageViewer should support previous navigation",
  );
  assert.match(
    source,
    /<ImageViewer[\s\S]*?\bonNext=/,
    "generated image ImageViewer should support next navigation",
  );
});

test("generated image result previews load eagerly for browser captures", () => {
  const source = readFileSync(
    new URL("../McpBlockPreview.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    source,
    /<ImageWithSkeleton[\s\S]*?\bloading="eager"/,
    "generated image previews should not rely on native lazy loading",
  );
});

test("image generation prompt can be copied from the detail panel", () => {
  const source = readFileSync(
    new URL("../ImageGenerateItem.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    source,
    /import\s+\{[^}]*CopyButton[^}]*\}\s+from\s+"..\/..\/..\/common"/s,
    "image generation item should import the shared copy button",
  );
  assert.match(
    source,
    /<CopyButton[\s\S]*?\btext=\{prompt\}/,
    "the full prompt block should expose a copy action for the prompt",
  );
});

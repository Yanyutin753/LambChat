import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "vitest";

// 所有拉取上传文件内容的调用点必须走 documentFetchCache 的统一入口，
// 享受 ?proxy=true 兜底（OSS 直连不可达时经应用源代理重试），
// 禁止裸 fetch() 绕过——新增预览/导出路径时此测试会拦截回归。

const textConsumers = [
  "../previews/ExcalidrawCardPreview.tsx",
  "../previews/ExcalidrawDirectViewer.tsx",
  "../../common/ExcalidrawThumbnail.tsx",
  "../../fileLibrary/hooks/useCodePreview.ts",
  "../../chat/ChatMessage/items/revealPreviewData.ts",
];

const binaryConsumers = ["../../../utils/exportProjectZip.ts"];

const rawFetchPattern = /(^|[^a-zA-Z_.])fetch\(/;

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

function listSourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    if (name === "__tests__" || name.startsWith(".")) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      out.push(...listSourceFiles(p));
    } else if (/\.(ts|tsx)$/.test(name)) {
      out.push(p);
    }
  }
  return out;
}

test("text consumers fetch document content via fetchDocumentText", () => {
  for (const path of textConsumers) {
    const src = readSource(path);
    expect(src, `${path} 应使用 fetchDocumentText`).toMatch(
      /fetchDocumentText\(/,
    );
    expect(src, `${path} 不应裸 fetch()`).not.toMatch(rawFetchPattern);
  }
});

test("binary consumers download via fetchUploadFile", () => {
  for (const path of binaryConsumers) {
    const src = readSource(path);
    expect(src, `${path} 应使用 fetchUploadFile`).toMatch(/fetchUploadFile\(/);
    expect(src, `${path} 不应裸 fetch()`).not.toMatch(rawFetchPattern);
  }
});

test("no source file combines buildUploadProxyUrl with a raw fetch()", () => {
  const srcDir = new URL("../../../", import.meta.url).pathname;
  const offenders: string[] = [];
  for (const file of listSourceFiles(srcDir)) {
    const src = readFileSync(file, "utf8");
    if (src.includes("buildUploadProxyUrl(") && rawFetchPattern.test(src)) {
      offenders.push(file);
    }
  }
  // 允许清单：目前为空；media 元素走 mediaProxyFallbackSrc onError 换源
  expect(offenders).toEqual([]);
});

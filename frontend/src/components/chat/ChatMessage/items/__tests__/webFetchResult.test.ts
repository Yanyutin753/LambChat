import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

import { hostFromUrl, parseWebFetchResult } from "../webFetchResult";

const repoRoot = resolve(__dirname, "../../../../../../..");

describe("parseWebFetchResult", () => {
  test("parses JSON string result with snake_case fields", () => {
    const raw = JSON.stringify({
      success: true,
      url: "https://example.com/page",
      final_url: "https://example.com/page?from=redirect",
      provider: "jina",
      title: "Page Title",
      content: "# Heading\n\nBody text.",
      content_chars: 20,
      truncated: true,
      content_type: "text/markdown",
    });
    const summary = parseWebFetchResult(raw);
    expect(summary).not.toBeNull();
    expect(summary?.url).toBe("https://example.com/page");
    expect(summary?.finalUrl).toBe("https://example.com/page?from=redirect");
    expect(summary?.provider).toBe("jina");
    expect(summary?.title).toBe("Page Title");
    expect(summary?.contentChars).toBe(20);
    expect(summary?.truncated).toBe(true);
    expect(summary?.contentType).toBe("text/markdown");
  });

  test("accepts object result and camelCase fallbacks", () => {
    const summary = parseWebFetchResult({
      url: "https://example.com/a",
      provider: "direct",
      content: "plain body",
    });
    expect(summary?.provider).toBe("direct");
    expect(summary?.content).toBe("plain body");
    expect(summary?.truncated).toBe(false);
  });

  test("returns null for failure payloads", () => {
    expect(parseWebFetchResult({ success: false, error: "x" })).toBeNull();
  });

  test("returns null for non-JSON string or missing content", () => {
    expect(parseWebFetchResult("not json")).toBeNull();
    expect(parseWebFetchResult({ url: "https://example.com" })).toBeNull();
  });

  test("hostFromUrl extracts hostname and tolerates junk", () => {
    expect(hostFromUrl("https://blog.example.com/x?y=1")).toBe(
      "blog.example.com",
    );
    expect(hostFromUrl("junk")).toBeNull();
  });
});

test("web fetch item presents url, content reader and live panel", () => {
  const source = readFileSync(
    resolve(repoRoot, "frontend/src/components/chat/ChatMessage/items/WebFetchItem.tsx"),
    "utf8",
  );
  expect(source).toMatch(/toolWebFetch/);
  expect(source).toMatch(/args\.url/);
  expect(source).toMatch(/BookOpen size=\{12\}/);
  expect(source).toMatch(/openToolLivePanel/);
  expect(source).toMatch(/ToolInlineDetails/);
  expect(source).toMatch(/parseWebFetchResult/);
});

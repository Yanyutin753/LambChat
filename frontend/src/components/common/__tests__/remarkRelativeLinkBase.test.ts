import { expect, test } from "vitest";
import type { Root } from "mdast";
import { remarkRelativeLinkBase } from "../markdownRemarkPlugins";

function transform(baseUrl: string, urls: string[]): string[] {
  const tree: Root = {
    type: "root",
    children: urls.map((url) => ({
      type: "link",
      url,
      children: [{ type: "text", value: "x" }],
    })),
  };
  const plugin = remarkRelativeLinkBase(baseUrl) as unknown as () => (
    tree: Root,
  ) => void;
  plugin()(tree);
  return tree.children.map(
    (node) => (node as { url?: string }).url as string,
  );
}

test("relative links resolve against the markdown file's own URL", () => {
  const base = "/api/upload/file/ws-1/report/README.md";
  expect(transform(base, ["./summary.pdf", "docs/intro.md", "images/logo.png"]))
    .toEqual([
      "http://localhost/api/upload/file/ws-1/report/summary.pdf",
      "http://localhost/api/upload/file/ws-1/report/docs/intro.md",
      "http://localhost/api/upload/file/ws-1/report/images/logo.png",
    ]);
});

test("non-relative targets stay untouched", () => {
  const base = "/api/upload/file/ws-1/README.md";
  expect(
    transform(base, [
      "https://example.com/a.pdf",
      "//cdn.example.com/a.png",
      "#section",
      "mailto:a@b.c",
      "/api/upload/file/ws-1/other/b.pdf",
    ]),
  ).toEqual([
    "https://example.com/a.pdf",
    "//cdn.example.com/a.png",
    "#section",
    "mailto:a@b.c",
    "/api/upload/file/ws-1/other/b.pdf",
  ]);
});

test("external base (e.g. presigned S3) disables rewriting", () => {
  const base = "https://bucket.s3.example.com/ws/README.md?X=1";
  expect(transform(base, ["./a.pdf"])).toEqual(["./a.pdf"]);
});

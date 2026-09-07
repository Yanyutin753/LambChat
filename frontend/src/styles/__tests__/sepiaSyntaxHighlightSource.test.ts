import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../syntax-highlight.css", import.meta.url),
  "utf8",
);

test("sepia theme deepens the syntax tokens that fail contrast on the beige code background", () => {
  // 关键字（fuchsia 系）→ #a21caf（混合代码底 #f4eedf 上 5.46:1）
  expect(source).toMatch(
    /\.theme-sepia \.hljs-doctag,[\s\S]*?\.theme-sepia \.hljs-keyword[\s\S]*?color: #a21caf/,
  );
  // 注释（zinc 系）→ #5f6368（5.23:1）
  expect(source).toMatch(
    /\.theme-sepia \.hljs-comment,[\s\S]*?color: #5f6368/,
  );
  // 内置/符号（amber 系）→ #9a4a08（5.40:1）
  expect(source).toMatch(
    /\.theme-sepia \.hljs-built_in,[\s\S]*?color: #9a4a08/,
  );
  // 标签（orange 系）→ #a63a0a（5.61:1）
  expect(source).toMatch(
    /\.theme-sepia \.hljs-name,[\s\S]*?color: #a63a0a/,
  );
  // 属性/数字（cyan 系）→ #0d6a7e（最差底 #efe8d4 上 5.08:1）
  expect(source).toMatch(
    /\.theme-sepia \.hljs-attr,[\s\S]*?color: #0d6a7e/,
  );
  // 字符串（emerald 系）→ #046d51（最差底 5.18:1）
  expect(source).toMatch(
    /\.theme-sepia \.hljs-regexp,[\s\S]*?\.theme-sepia \.hljs-string[\s\S]*?color: #046d51/,
  );
});

test("sepia overrides only recolor tokens and never repaint the dark palette", () => {
  expect(source).not.toMatch(/\.theme-sepia \.hljs \{/);
  expect(source).toMatch(/\.dark \.hljs \{\s*color: #fafafa/);
});

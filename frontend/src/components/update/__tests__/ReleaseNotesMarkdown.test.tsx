/** @vitest-environment jsdom */
import { renderToStaticMarkup } from "react-dom/server";

import { ReleaseNotesMarkdown } from "../ReleaseNotesMarkdown.tsx";

const GITHUB_RELEASE_NOTES = `## What's Changed

* fix: 修复 /stream 路由被 helper 劫持 by [@yanyutin](https://github.com/yanyutin) in [PR #431](https://github.com/lambchat/lambchat/pull/431)
* perf: **性能优化**，支持 ~~旧参数~~

**Full Changelog**: https://github.com/lambchat/lambchat/compare/v2.8.1...v2.8.2`;

test("renders github release notes headings, lists and emphasis", () => {
  const html = renderToStaticMarkup(
    <ReleaseNotesMarkdown content={GITHUB_RELEASE_NOTES} />,
  );

  // React 将撇号转义为 &#x27;，正则需容忍实体形式
  expect(html).toMatch(/<h2[^>]*>What(?:&#x27;|')s Changed<\/h2>/);
  expect(html).toMatch(
    /<li[^>]*>[\s\S]*fix: 修复 \/stream 路由被 helper 劫持[\s\S]*<\/li>/,
  );
  expect(html).toMatch(/<strong[^>]*>性能优化<\/strong>/);
  expect(html).toMatch(/<del[^>]*>旧参数<\/del>/);
});

test("opens release note links in a new tab", () => {
  const html = renderToStaticMarkup(
    <ReleaseNotesMarkdown
      content={"[PR #431](https://github.com/lambchat/lambchat/pull/431)"}
    />,
  );

  expect(html).toMatch(
    /<a[^>]*href="https:\/\/github\.com\/lambchat\/lambchat\/pull\/431"[^>]*target="_blank"[^>]*rel="noopener noreferrer"[^>]*>PR #431<\/a>/,
  );
});

test("keeps heavyweight elements out of the update dialog", () => {
  const html = renderToStaticMarkup(
    <ReleaseNotesMarkdown
      content={
        "![banner](https://example.com/banner.png)\n\n```\ncode block\n```"
      }
    />,
  );

  expect(html).not.toMatch(/<img\b/);
  expect(html).not.toMatch(/<pre\b/);
  // img 是 void 元素，unwrapDisallowed 直接整体丢弃；代码块文本经 code 元素保留
  expect(html).not.toContain("banner.png");
  expect(html).toContain("code block");
});

test("renders plain text release notes without markdown syntax", () => {
  const html = renderToStaticMarkup(
    <ReleaseNotesMarkdown content="普通的一行更新说明" />,
  );

  expect(html).toContain("普通的一行更新说明");
});

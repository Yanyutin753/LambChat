import { readFileSync } from "node:fs";

/**
 * 工具卡片里的图片溢出角标（+N）必须是打开实时面板的按钮，面板里不再截断；
 * 多图卡片的灯箱要能在本卡片图片间翻页（useImagePreviewFallback + siblings）。
 * 这组用例来自用户反馈「点击 +2 不会展开所有图片」「多图预览不能切换」。
 */

function readItem(name: string): string {
  return readFileSync(new URL(`../${name}`, import.meta.url), "utf8");
}

/** 每个溢出角标所在的 JSX 片段：从外层条件渲染 `&& (` 到角标文本之间 */
function overflowBadgeMarkup(source: string, badge: string): string[] {
  const markups: string[] = [];
  let from = 0;
  for (;;) {
    const at = source.indexOf(badge, from);
    if (at < 0) break;
    markups.push(source.slice(source.lastIndexOf("&& (", at), at));
    from = at + badge.length;
  }
  return markups;
}

function expectBadgeOpensPanel(source: string, badge: string, opener: RegExp) {
  const markups = overflowBadgeMarkup(source, badge);
  expect(markups.length).toBeGreaterThan(0);
  for (const markup of markups) {
    expect(markup).toMatch(/<button\b/);
    expect(markup).not.toMatch(/<div\b/);
    expect(markup).toMatch(opener);
  }
}

function count(source: string, pattern: RegExp): number {
  return source.match(pattern)?.length ?? 0;
}

test("ImageAnalyzeItem: +N opens the live panel and the panel shows every image", () => {
  const source = readItem("ImageAnalyzeItem.tsx");

  // 收起态卡片只显示 4 张；面板详情不得再截断
  expect(count(source, /\bimages\.slice\(0, 4\)/g)).toBe(1);
  expect(count(source, /\+\{images\.length - 4\}/g)).toBe(1);
  expectBadgeOpensPanel(
    source,
    "+{images.length - 4}",
    /onClick=\{openPanel\}/,
  );
  expect(source).toMatch(/aria-label=\{t\("chat\.message\.toolMoreImages"/);

  // 多图预览：把本卡片的图片列表交给灯箱，缺少会话画廊时也能翻页
  expect(source).toMatch(/useImagePreviewFallback\(previewSiblings\)/);
});

test("ImageGenerateItem: reference and result overflow badges open the panel, panel shows all references", () => {
  const source = readItem("ImageGenerateItem.tsx");

  expect(count(source, /\binputImages\.slice\(0, 4\)/g)).toBe(1);
  expect(count(source, /\+\{inputImages\.length - 4\}/g)).toBe(1);
  expect(count(source, /\+\{images\.length - 4\}/g)).toBe(1);
  expectBadgeOpensPanel(
    source,
    "+{inputImages.length - 4}",
    /onClick=\{openPanel\}/,
  );
  expectBadgeOpensPanel(
    source,
    "+{images.length - 4}",
    /onClick=\{openPanel\}/,
  );

  // 参考图缩略图必须是真按钮（键盘可达），不再是带 onClick 的 div
  expect(source).not.toMatch(/<div[^>]*\n?[^>]*onClick=\{\(\) => open/);

  // 统一走 useImagePreviewFallback：不再各自维护单图 ImageViewer
  expect(source).toMatch(/useImagePreviewFallback\(previewSiblings\)/);
  expect(source).not.toMatch(/<ImageViewer/);
  expect(source).not.toMatch(/openImagePreview/);
});

test("WebSearchItem: panel lists every image and the lightbox pages through them", () => {
  const source = readItem("WebSearchItem.tsx");

  expect(source).not.toMatch(/summary\.images\.slice\(0, 9\)/);
  expectBadgeOpensPanel(
    source,
    "+{summary.images.length - 3}",
    /onClick=\{openSearchPanel\}/,
  );
  expect(source).toMatch(/useImagePreviewFallback\(previewSiblings\)/);
  expect(source).not.toMatch(/<ImageViewer/);
});

test("imagePreviewFallback forwards siblings to the session gallery and pages locally otherwise", () => {
  const source = readItem("imagePreviewFallback.tsx");

  expect(source).toMatch(/resolveImageListNavigation/);
  expect(source).toMatch(/siblings/);
  expect(source).toMatch(/onPrevious=/);
  expect(source).toMatch(/onNext=/);
  expect(source).toMatch(/positionLabel=/);
});

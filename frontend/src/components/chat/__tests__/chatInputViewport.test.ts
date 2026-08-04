import {
  COMPOSER_EXPAND_MIN_LINES,
  getComposerContentLineCount,
  getTextareaMaxHeightPx,
  resizeTextareaForContent,
  shouldShowComposerExpandButton,
} from "../chatInputViewport.ts";

test("resizeTextareaForContent keeps the newest typed content visible", () => {
  // 追加输入场景：光标在末尾，视口原本就在底部
  const textarea = {
    style: { height: "" },
    scrollHeight: 420,
    scrollTop: 200,
    clientHeight: 220, // 200 + 220 = 420 ≥ 419 → 已在底部
    value: "hello",
    selectionEnd: 5,
  };

  resizeTextareaForContent(textarea, 250);

  expect(textarea.style.height).toBe("250px");
  expect(textarea.scrollTop).toBe(420);
});

test("resizeTextareaForContent sticks to bottom when caret is at the end", () => {
  // 追加输入但高度刚撑开时，wasAtBottom 可能为 false；光标在末尾仍应贴底
  const textarea = {
    style: { height: "" },
    scrollHeight: 420,
    scrollTop: 0,
    clientHeight: 150,
    value: "line\n".repeat(20),
    selectionEnd: "line\n".repeat(20).length,
  };

  resizeTextareaForContent(textarea, 150);

  expect(textarea.scrollTop).toBe(420);
});

test("resizeTextareaForContent preserves scroll position when editing mid-text", () => {
  // 编辑中间内容场景：光标在文本中间，视口不在底部
  const textarea = {
    style: { height: "" },
    scrollHeight: 420,
    scrollTop: 50,
    clientHeight: 220, // 50 + 220 = 270 < 419 → 未在底部
    value: "abcdefghij",
    selectionEnd: 4,
  };

  resizeTextareaForContent(textarea, 250);

  expect(textarea.style.height).toBe("250px");
  expect(textarea.scrollTop).toBe(50);
});

test("getTextareaMaxHeightPx uses a comfortable fraction of small mobile viewports", () => {
  expect(getTextareaMaxHeightPx({ isMobile: true, viewportHeight: 500 })).toBe(
    120,
  );
});

test("getTextareaMaxHeightPx keeps the default cap on desktop and roomy mobile viewports", () => {
  expect(getTextareaMaxHeightPx({ isMobile: false, viewportHeight: 500 })).toBe(
    150,
  );
  expect(getTextareaMaxHeightPx({ isMobile: true, viewportHeight: 900 })).toBe(
    150,
  );
});

test("getComposerContentLineCount rounds content height into visual lines", () => {
  expect(
    getComposerContentLineCount({
      scrollHeight: 34,
      lineHeight: 24,
      verticalPadding: 10,
    }),
  ).toBe(1);
  expect(
    getComposerContentLineCount({
      scrollHeight: 82,
      lineHeight: 24,
      verticalPadding: 10,
    }),
  ).toBe(3);
  expect(
    getComposerContentLineCount({
      scrollHeight: 106,
      lineHeight: 24,
      verticalPadding: 10,
    }),
  ).toBe(4);
});

test("shouldShowComposerExpandButton only after content exceeds three lines", () => {
  expect(COMPOSER_EXPAND_MIN_LINES).toBe(3);
  expect(shouldShowComposerExpandButton(1)).toBe(false);
  expect(shouldShowComposerExpandButton(3)).toBe(false);
  expect(shouldShowComposerExpandButton(4)).toBe(true);
});

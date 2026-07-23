import {
  getTextareaMaxHeightPx,
  resizeTextareaForContent,
} from "../chatInputViewport.ts";

test("resizeTextareaForContent keeps the newest typed content visible", () => {
  // 追加输入场景：光标在末尾，视口原本就在底部
  const textarea = {
    style: { height: "" },
    scrollHeight: 420,
    scrollTop: 200,
    clientHeight: 220, // 200 + 220 = 420 ≥ 419 → 已在底部
  };

  resizeTextareaForContent(textarea, 250);

  expect(textarea.style.height).toBe("250px");
  expect(textarea.scrollTop).toBe(420);
});

test("resizeTextareaForContent preserves scroll position when editing mid-text", () => {
  // 编辑中间内容场景：光标在文本中间，视口不在底部
  const textarea = {
    style: { height: "" },
    scrollHeight: 420,
    scrollTop: 50,
    clientHeight: 220, // 50 + 220 = 270 < 419 → 未在底部
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

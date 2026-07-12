import {
  getTextareaMaxHeightPx,
  resizeTextareaForContent,
} from "../chatInputViewport.ts";

test("resizeTextareaForContent keeps the newest typed content visible", () => {
  const textarea = {
    style: { height: "" },
    scrollHeight: 420,
    scrollTop: 0,
  };

  resizeTextareaForContent(textarea, 250);

  expect(textarea.style.height).toBe("250px");
  expect(textarea.scrollTop).toBe(420);
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

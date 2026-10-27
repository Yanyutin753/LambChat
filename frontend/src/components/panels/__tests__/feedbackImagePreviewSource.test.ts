import { readFileSync } from "node:fs";

/**
 * 反馈附件常常不止一张：详情弹窗和列表卡片的灯箱都要能在附件间翻页，
 * 「+N」角标应直接跳到第一张被折叠的附件。
 */
test("FeedbackPanel attachment previews page through the feedback's attachments", () => {
  const source = readFileSync(
    new URL("../FeedbackPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/useImagePreviewFallback/);
  expect(source).not.toMatch(/<ImageViewer/);
  expect(source).toMatch(/onImageClick\(shown\.length\)/);
});

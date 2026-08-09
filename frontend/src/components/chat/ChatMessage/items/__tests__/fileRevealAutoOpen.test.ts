import { expect, test } from "vitest";

import {
  clearFileRevealAutoOpenState,
  markFileRevealPreviewAutoOpened,
  shouldAutoOpenFileRevealPreview,
} from "../fileRevealAutoOpen";

test("auto-opens each successful file key at most once", () => {
  clearFileRevealAutoOpenState();
  const input = {
    success: true,
    filePath: "report.md",
    isImage: false,
    showPreview: false,
    hasClosedPreview: false,
    isDesktop: true,
    allowAutoPreview: true,
    previewKey: "report.md",
  };

  expect(shouldAutoOpenFileRevealPreview(input)).toBe(true);
  markFileRevealPreviewAutoOpened("report.md");
  expect(shouldAutoOpenFileRevealPreview(input)).toBe(false);
});

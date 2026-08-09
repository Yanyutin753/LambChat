import { expect, test } from "vitest";

import {
  clearProjectRevealAutoOpenState,
  markProjectRevealPreviewAutoOpened,
  shouldAutoOpenProjectRevealPreview,
} from "../projectRevealAutoOpen";

test("auto-opens each successful project key at most once", () => {
  clearProjectRevealAutoOpenState();
  const input = {
    success: true,
    showFullPreview: false,
    hasClosedPreview: false,
    isDesktop: true,
    allowAutoPreview: true,
    previewKey: "project-a",
  };

  expect(shouldAutoOpenProjectRevealPreview(input)).toBe(true);
  markProjectRevealPreviewAutoOpened("project-a");
  expect(shouldAutoOpenProjectRevealPreview(input)).toBe(false);
});

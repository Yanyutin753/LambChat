import {
  getActiveRevealPreviewState,
  setActiveRevealPreviewState,
} from "../items/activeRevealPreviewStore.ts";
import { openRevealPreview } from "../items/revealPreviewActions.ts";

const preview = {
  kind: "file" as const,
  previewKey: "preview:file:1",
  filePath: "src/index.ts",
};

test("opens the global preview state when manual open has no callback", () => {
  setActiveRevealPreviewState(null);

  const opened = openRevealPreview(preview, "manual");

  expect(opened).toBe(true);
  expect(getActiveRevealPreviewState()?.request).toEqual(preview);

  setActiveRevealPreviewState(null);
});

test("does not auto-open without a callback", () => {
  setActiveRevealPreviewState(null);

  const opened = openRevealPreview(preview, "auto");

  expect(opened).toBe(false);
  expect(getActiveRevealPreviewState()).toBe(null);
});

test("uses the provided callback when present", () => {
  setActiveRevealPreviewState(null);

  let called = 0;
  const opened = openRevealPreview(preview, "manual", () => {
    called += 1;
    return true;
  });

  expect(opened).toBe(true);
  expect(called).toBe(1);
  expect(getActiveRevealPreviewState()).toBe(null);
});

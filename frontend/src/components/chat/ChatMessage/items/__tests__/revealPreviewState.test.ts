import test from "node:test";
import assert from "node:assert/strict";
import {
  createActiveRevealPreviewState,
  shouldAcceptRevealPreviewOpen,
} from "../revealPreviewState.ts";

test("marks external previews as already interacted", () => {
  const previewState = createActiveRevealPreviewState(
    {
      kind: "file",
      previewKey: "external-file:file-1",
      filePath: "/tmp/demo.txt",
    },
    "external",
  );

  assert.equal(previewState.source, "external");
  assert.equal(previewState.userInteracted, true);
});

test("blocks auto preview from replacing an external navigation preview", () => {
  const activePreview = createActiveRevealPreviewState(
    {
      kind: "file",
      previewKey: "external-file:file-1",
      filePath: "/tmp/demo.txt",
    },
    "external",
  );

  assert.equal(
    shouldAcceptRevealPreviewOpen({
      activePreview,
      nextPreview: {
        kind: "file",
        previewKey: "session-file:file-2",
        filePath: "/tmp/other.txt",
      },
      source: "auto",
      dismissedPreviewKeys: new Set<string>(),
    }),
    false,
  );
});

test("still allows manual preview to replace an external navigation preview", () => {
  const activePreview = createActiveRevealPreviewState(
    {
      kind: "file",
      previewKey: "external-file:file-1",
      filePath: "/tmp/demo.txt",
    },
    "external",
  );

  assert.equal(
    shouldAcceptRevealPreviewOpen({
      activePreview,
      nextPreview: {
        kind: "file",
        previewKey: "manual-file:file-2",
        filePath: "/tmp/other.txt",
      },
      source: "manual",
      dismissedPreviewKeys: new Set<string>(),
    }),
    true,
  );
});

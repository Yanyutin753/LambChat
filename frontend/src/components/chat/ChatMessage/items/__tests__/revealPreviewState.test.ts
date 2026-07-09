import {
  createActiveRevealPreviewState,
  shouldAcceptRevealPreviewOpen,
  shouldStabilizeScrollForAutoPreviewOpen,
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

  expect(previewState.source).toBe("external");
  expect(previewState.userInteracted).toBe(true);
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

  expect(
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
  ).toBe(false);
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

  expect(
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
  ).toBe(true);
});

test("stabilizes chat scroll only when an auto preview opens near the bottom", () => {
  const autoPreview = createActiveRevealPreviewState(
    {
      kind: "project",
      previewKey: "project:/tmp/demo",
      project: {
        version: 1,
        name: "demo",
        path: "/tmp/demo",
        template: "static",
        mode: "folder",
        files: {},
        fileCount: 0,
      },
    },
    "auto",
  );

  expect(
    shouldStabilizeScrollForAutoPreviewOpen({
      previousPreview: null,
      nextPreview: autoPreview,
      isNearBottom: true,
    }),
  ).toBe(true);
  expect(
    shouldStabilizeScrollForAutoPreviewOpen({
      previousPreview: null,
      nextPreview: autoPreview,
      isNearBottom: false,
    }),
  ).toBe(false);
  expect(
    shouldStabilizeScrollForAutoPreviewOpen({
      previousPreview: autoPreview,
      nextPreview: autoPreview,
      isNearBottom: true,
    }),
  ).toBe(false);
});

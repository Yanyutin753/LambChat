import {
  buildExternalNavigationStateForFile,
  buildExternalNavigationPreviewRequest,
  getExternalNavigationPreviewRequest,
  getExternalNavigationTargetFile,
  shouldOpenExternalNavigationPreview,
  shouldResetExternalNavigateFlag,
  shouldScrollToBottomAfterExternalNavigation,
} from "../externalNavigationState.ts";

test("resets the external navigation flag only when present", () => {
  expect(shouldResetExternalNavigateFlag({ externalNavigate: true })).toBe(
    true,
  );
  expect(shouldResetExternalNavigateFlag({ externalNavigate: false })).toBe(
    false,
  );
  expect(shouldResetExternalNavigateFlag({})).toBe(false);
  expect(shouldResetExternalNavigateFlag(null)).toBe(false);
});

test("marks external navigation requests that should scroll to bottom", () => {
  expect(
    shouldScrollToBottomAfterExternalNavigation({
      externalNavigate: true,
      scrollToBottom: true,
    }),
  ).toBe(true);
  expect(
    shouldScrollToBottomAfterExternalNavigation({
      externalNavigate: true,
      scrollToBottom: false,
    }),
  ).toBe(false);
  expect(
    shouldScrollToBottomAfterExternalNavigation({
      externalNavigate: false,
      scrollToBottom: true,
    }),
  ).toBe(false);
  expect(shouldScrollToBottomAfterExternalNavigation(null)).toBe(false);
});

test("extracts the target file only for external navigation", () => {
  expect(
    getExternalNavigationTargetFile({
      externalNavigate: true,
      targetFile: {
        fileId: "file-123",
        originalPath: "/tmp/demo.txt",
        traceId: "trace-123",
        source: "reveal_file",
      },
    }),
  ).toEqual({
    fileId: "file-123",
    originalPath: "/tmp/demo.txt",
    traceId: "trace-123",
    source: "reveal_file",
  });
  expect(
    getExternalNavigationTargetFile({
      externalNavigate: true,
      targetFile: {},
    }),
  ).toBe(null);
  expect(
    getExternalNavigationTargetFile({
      externalNavigate: false,
      targetFile: {
        fileId: "file-123",
      },
    }),
  ).toBe(null);
  expect(getExternalNavigationTargetFile(null)).toBe(null);
});

test("builds a file preview request for external navigation", () => {
  expect(
    buildExternalNavigationPreviewRequest({
      id: "file-1",
      file_key: "revealed/file-1",
      file_name: "demo.txt",
      file_size: 128,
      url: "/api/upload/file/revealed/file-1",
      source: "reveal_file",
      original_path: "/tmp/demo.txt",
      project_meta: null,
    }),
  ).toEqual({
    kind: "file",
    previewKey: "external-file:file-1",
    filePath: "/tmp/demo.txt",
    s3Key: "revealed/file-1",
    signedUrl: "/api/upload/file/revealed/file-1",
    fileSize: 128,
  });
});

test("does not auto-open preview for externally opened image files", () => {
  expect(
    buildExternalNavigationStateForFile({
      id: "file-image-1",
      file_key: "revealed/file-image-1",
      file_name: "diagram.png",
      file_size: 256,
      url: "/api/upload/file/revealed/file-image-1",
      source: "reveal_file",
      original_path: "/tmp/diagram.png",
      trace_id: "",
      project_meta: null,
    }),
  ).toEqual({
    externalNavigate: true,
    targetFile: {
      fileId: "file-image-1",
      fileKey: "revealed/file-image-1",
      fileName: "diagram.png",
      originalPath: "/tmp/diagram.png",
      source: "reveal_file",
    },
    targetPreview: null,
  });
});

test("keeps auto-open preview for non-image external navigation files", () => {
  expect(
    buildExternalNavigationStateForFile({
      id: "file-text-1",
      file_key: "revealed/file-text-1",
      file_name: "notes.txt",
      file_size: 64,
      url: "/api/upload/file/revealed/file-text-1",
      source: "reveal_file",
      original_path: "/tmp/notes.txt",
      trace_id: "",
      project_meta: null,
    }),
  ).toEqual({
    externalNavigate: true,
    targetFile: {
      fileId: "file-text-1",
      fileKey: "revealed/file-text-1",
      fileName: "notes.txt",
      originalPath: "/tmp/notes.txt",
      source: "reveal_file",
    },
    targetPreview: {
      kind: "file",
      previewKey: "external-file:file-text-1",
      filePath: "/tmp/notes.txt",
      s3Key: "revealed/file-text-1",
      signedUrl: "/api/upload/file/revealed/file-text-1",
      fileSize: 64,
    },
  });
});

test("builds a project preview request for external navigation", () => {
  expect(
    buildExternalNavigationPreviewRequest({
      id: "file-2",
      file_key: "revealed/project-1",
      file_name: "demo-app",
      file_size: 0,
      url: null,
      source: "reveal_project",
      original_path: "/workspace/demo-app",
      project_meta: {
        template: "vanilla",
        entry: "index.html",
        file_count: 1,
        files: {
          "index.html": {
            url: "/api/upload/file/demo/index.html",
            size: 42,
            is_binary: false,
            content_type: "text/html",
          },
        },
      },
    }),
  ).toEqual({
    kind: "project",
    previewKey: "external-project:file-2",
    project: {
      version: 2,
      name: "demo-app",
      mode: "project",
      path: "/workspace/demo-app",
      template: "vanilla",
      entry: "index.html",
      fileCount: 1,
      files: {
        "index.html": {
          url: "/api/upload/file/demo/index.html",
          size: 42,
          is_binary: false,
          content_type: "text/html",
        },
      },
    },
  });
});

test("extracts the preview request only for external navigation", () => {
  expect(
    getExternalNavigationPreviewRequest({
      externalNavigate: true,
      targetPreview: {
        kind: "file",
        previewKey: "external-file:file-1",
        filePath: "/tmp/demo.txt",
      },
    }),
  ).toEqual({
    kind: "file",
    previewKey: "external-file:file-1",
    filePath: "/tmp/demo.txt",
  });

  expect(
    getExternalNavigationPreviewRequest({
      externalNavigate: false,
      targetPreview: {
        kind: "file",
        previewKey: "external-file:file-1",
        filePath: "/tmp/demo.txt",
      },
    }),
  ).toBe(null);
});

test("reopens an external preview after the target session changes", () => {
  expect(
    shouldOpenExternalNavigationPreview({
      externalNavigationToken: "nav-1",
      externalNavigationPreview: {
        kind: "file",
        previewKey: "external-file:file-1",
        filePath: "/tmp/demo.txt",
      },
      handledToken: "nav-1",
      handledSessionId: "session-old",
      sessionId: "session-new",
    }),
  ).toBe(true);

  expect(
    shouldOpenExternalNavigationPreview({
      externalNavigationToken: "nav-1",
      externalNavigationPreview: {
        kind: "file",
        previewKey: "external-file:file-1",
        filePath: "/tmp/demo.txt",
      },
      handledToken: "nav-1",
      handledSessionId: "session-new",
      sessionId: "session-new",
    }),
  ).toBe(false);
});

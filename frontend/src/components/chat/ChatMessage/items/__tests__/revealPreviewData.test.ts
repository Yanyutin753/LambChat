import {
  parseProjectRevealSummary,
  shouldShowProjectRevealLoadingError,
} from "../revealPreviewData.ts";

test("parses folder mode from reveal_project results", () => {
  const summary = parseProjectRevealSummary({
    args: { project_path: "/workspace/backend-service" },
    result: JSON.stringify({
      type: "project_reveal",
      version: 2,
      name: "backend-service",
      mode: "folder",
      template: "vanilla",
      files: {
        "/README.md": {
          url: "/api/upload/file/demo-readme",
          is_binary: false,
          size: 10,
        },
      },
    }),
    parseErrorMessage: "parse error",
  });

  expect(summary.parsed?.mode).toBe("folder");
});

test("defaults legacy reveal_project results to project mode", () => {
  const summary = parseProjectRevealSummary({
    args: { project_path: "/workspace/site" },
    result: JSON.stringify({
      type: "project_reveal",
      version: 2,
      name: "site",
      template: "react",
      entry: "/src/main.jsx",
      files: {
        "/src/main.jsx": {
          url: "/api/upload/file/demo-entry",
          is_binary: false,
          size: 20,
        },
      },
    }),
    parseErrorMessage: "parse error",
  });

  expect(summary.parsed?.mode).toBe("project");
});

test("does not mark pure binary reveal_project folders as failed loads", () => {
  const showError = shouldShowProjectRevealLoadingError({
    files: {},
    binaryFiles: {
      "/main.png": "https://example.com/main.png",
      "/detail.png": "https://example.com/detail.png",
    },
    manifestFiles: {
      "/main.png": {
        url: "https://example.com/main.png",
        is_binary: true,
        size: 100,
      },
      "/detail.png": {
        url: "https://example.com/detail.png",
        is_binary: true,
        size: 100,
      },
    },
  });

  expect(showError).toBe(false);
});

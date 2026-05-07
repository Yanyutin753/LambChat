import assert from "node:assert/strict";
import test from "node:test";

import { parseProjectRevealSummary } from "../revealPreviewData.ts";

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

  assert.equal(summary.parsed?.mode, "folder");
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

  assert.equal(summary.parsed?.mode, "project");
});

import { vi } from "vitest";
import {
  clearProjectRevealFilesCache,
  getCachedProjectRevealFiles,
  loadProjectRevealFiles,
  loadProjectRevealFilesCached,
  parseProjectRevealSummary,
  shouldShowProjectRevealLoadingError,
  type FileManifestEntry,
  type ManifestProjectRevealData,
} from "../revealPreviewData.ts";

function makeTextManifest(count: number): Record<string, FileManifestEntry> {
  const files: Record<string, FileManifestEntry> = {};
  for (let index = 0; index < count; index++) {
    files[`/file-${index}.txt`] = {
      url: `/api/upload/file/revealed_projects/perf/file-${index}`,
      is_binary: false,
      size: 7,
    };
  }
  return files;
}

function makeV2Project(
  files: Record<string, FileManifestEntry>,
): ManifestProjectRevealData {
  return {
    version: 2,
    name: "perf-project",
    mode: "project",
    template: "vanilla",
    fileCount: Object.keys(files).length,
    files,
  };
}

function stubFetchTrackingConcurrency(): {
  maxInFlight: () => number;
  restore: () => void;
} {
  const originalFetch = globalThis.fetch;
  let inFlight = 0;
  let maxInFlight = 0;
  globalThis.fetch = (async () => {
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    await new Promise((resolve) => setTimeout(resolve, 5));
    inFlight -= 1;
    return new Response(`content`, { status: 200 });
  }) as typeof fetch;
  return {
    maxInFlight: () => maxInFlight,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

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

test("parses v3 list manifests that keep paths as item values", () => {
  const summary = parseProjectRevealSummary({
    args: { project_path: "/workspace/parrot-bike" },
    result: JSON.stringify({
      type: "project_reveal",
      version: 3,
      name: "鹦鹉的兜风日",
      mode: "project",
      template: "static",
      entry: "/index.html",
      files: [
        {
          path: "/index.html",
          url: "/api/upload/file/revealed_projects/parrot_ab12cd34/20261012_104859_8abe77e1_index.html",
          is_binary: false,
          size: 12443,
        },
      ],
    }),
    parseErrorMessage: "parse error",
  });

  expect(summary.parsed).toMatchObject({
    version: 3,
    name: "鹦鹉的兜风日",
    template: "static",
    entry: "/index.html",
    fileCount: 1,
  });
  expect(Object.keys(summary.parsed?.files ?? {})).toEqual(["/index.html"]);
});

test("restores dotted path keys of legacy v2 manifests mangled by event key sanitization", () => {
  // dual_writer 落库会把含 '.' 的 dict key 改写成 '_'，v2 manifest 的路径 key
  // 全部中招（/index.html → /index_html）而 entry 是值幸免。上传 URL 的文件名
  // 保留原始点号（{YYYYMMDD_HHMMSS}_{hash}_{原名}），可据此精确还原。
  const summary = parseProjectRevealSummary({
    args: { project_path: "/workspace/parrot-bike" },
    result: JSON.stringify({
      type: "project_reveal",
      version: 2,
      name: "parrot",
      mode: "project",
      template: "static",
      entry: "/index.html",
      files: {
        "/index_html": {
          url: "/api/upload/file/revealed_projects/parrot_ab12cd34/20261012_104859_8abe77e1_index.html",
          is_binary: false,
          size: 12443,
        },
        "/src/App_vue": {
          url: "/api/upload/file/revealed_projects/parrot_ab12cd34/20261012_104859_8abe77e2_App.vue",
          is_binary: false,
          size: 800,
        },
        "/assets/app_min_js": {
          url: "/api/upload/file/revealed_projects/parrot_ab12cd34/20261012_104859_8abe77e3_app.min.js",
          is_binary: false,
          size: 900,
        },
      },
    }),
    parseErrorMessage: "parse error",
  });

  expect(Object.keys(summary.parsed?.files ?? {}).sort()).toEqual(
    ["/assets/app.min.js", "/index.html", "/src/App.vue"].sort(),
  );
  expect(summary.parsed?.entry).toBe("/index.html");
});

test("keeps legacy v2 manifest keys when the url does not decode a mangled form", () => {
  const summary = parseProjectRevealSummary({
    args: { project_path: "/workspace/site" },
    result: JSON.stringify({
      type: "project_reveal",
      version: 2,
      name: "site",
      mode: "folder",
      template: "vanilla",
      files: {
        // URL basename 是 notes_v2.txt，mangle 后 notes_v2_txt ≠ key 的
        // notes_txt——无法证明 key 被消毒，必须原样保留
        "/notes_txt": {
          url: "/api/upload/file/revealed_projects/site_ab12cd34/20261012_104859_8abe77e4_notes_v2.txt",
          is_binary: false,
          size: 10,
        },
      },
    }),
    parseErrorMessage: "parse error",
  });

  expect(Object.keys(summary.parsed?.files ?? {})).toEqual(["/notes_txt"]);
});

test("loadProjectRevealFiles caps concurrent text file fetches", async () => {
  const fetchStub = stubFetchTrackingConcurrency();
  try {
    const result = await loadProjectRevealFiles(
      makeV2Project(makeTextManifest(20)),
    );

    expect(Object.keys(result.files)).toHaveLength(20);
    expect(result.failed).toHaveLength(0);
    // 旧实现用无上限 Promise.all，20 个文件会同时全部在飞
    expect(fetchStub.maxInFlight()).toBeLessThanOrEqual(6);
    expect(fetchStub.maxInFlight()).toBeGreaterThan(1);
  } finally {
    fetchStub.restore();
  }
});

test("project reveal file cache evicts least recently used entries", async () => {
  clearProjectRevealFilesCache();
  const fetchStub = stubFetchTrackingConcurrency();
  try {
    const load = (key: string) =>
      loadProjectRevealFilesCached({
        previewKey: key,
        project: makeV2Project(makeTextManifest(1)),
      });

    await load("project-1");
    await load("project-2");
    await load("project-3");
    await load("project-4");
    // 命中刷新 project-1 的新鲜度
    expect(getCachedProjectRevealFiles("project-1")).not.toBeNull();
    await load("project-5");

    expect(getCachedProjectRevealFiles("project-1")).not.toBeNull();
    expect(getCachedProjectRevealFiles("project-2")).toBeNull();
    expect(getCachedProjectRevealFiles("project-5")).not.toBeNull();
  } finally {
    fetchStub.restore();
    clearProjectRevealFilesCache();
  }
});

vi.mock("../../../../../services/api/uploadFileUrl", async (original) => ({
  ...(await original<
    typeof import("../../../../../services/api/uploadFileUrl")
  >()),
  resolveUploadFileUrl: vi.fn(async (url: string) => url),
}));

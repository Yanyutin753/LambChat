import {
  clearProjectRevealFilesCache,
  getCachedProjectRevealFiles,
  loadProjectRevealFiles,
  loadProjectRevealFilesCached,
  parseProjectRevealSummary,
  shouldShowProjectRevealLoadingError,
  type FileManifestEntry,
  type ParsedProjectRevealData,
} from "../revealPreviewData.ts";

function makeTextManifest(count: number): Record<string, FileManifestEntry> {
  const files: Record<string, FileManifestEntry> = {};
  for (let index = 0; index < count; index++) {
    files[`/file-${index}.txt`] = {
      url: `/api/upload/file/file-${index}`,
      is_binary: false,
      size: 7,
    };
  }
  return files;
}

function makeV2Project(
  files: Record<string, FileManifestEntry>,
): ParsedProjectRevealData {
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

test("loadProjectRevealFiles caps concurrent text file fetches", async () => {
  const fetchStub = stubFetchTrackingConcurrency();
  try {
    const result = await loadProjectRevealFiles(
      makeV2Project(makeTextManifest(20)) as Extract<
        ParsedProjectRevealData,
        { version: 2 }
      >,
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
        project: makeV2Project(makeTextManifest(1)) as Extract<
          ParsedProjectRevealData,
          { version: 2 }
        >,
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

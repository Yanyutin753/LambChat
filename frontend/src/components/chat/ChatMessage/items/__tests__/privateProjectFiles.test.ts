/** @vitest-environment jsdom */
import { beforeEach, expect, test, vi } from "vitest";
import { fetchDocumentText } from "../../../../documents/documentFetchCache";
import { resolveUploadFileUrl } from "../../../../../services/api/uploadFileUrl";
import {
  clearProjectRevealFilesCache,
  loadProjectRevealFilesCached,
  type ManifestProjectRevealData,
} from "../revealPreviewData";
vi.mock("../../../../../services/api/uploadFileUrl", async (original) => ({
  ...(await original<
    typeof import("../../../../../services/api/uploadFileUrl")
  >()),
  resolveUploadFileUrl: vi.fn(async (url: string) =>
    url.includes("file_token=") ? url : `${url}?file_token=project-capability`,
  ),
}));
vi.mock("../../../../documents/documentFetchCache", () => ({
  fetchDocumentText: vi.fn(async () => '<img src="./asset.png">'),
}));
const project: ManifestProjectRevealData = {
  version: 2,
  name: "private",
  mode: "project",
  template: "vanilla",
  fileCount: 2,
  files: {
    "/index.html": {
      url: "/api/upload/file/revealed_projects/site/index.html",
      is_binary: false,
      size: 20,
    },
    "/asset.png": {
      url: "/api/upload/file/revealed_projects/site/asset.png",
      is_binary: true,
      size: 10,
    },
  },
};
beforeEach(() => {
  clearProjectRevealFilesCache();
  vi.mocked(resolveUploadFileUrl).mockClear();
  vi.mocked(fetchDocumentText).mockClear();
  localStorage.setItem("access_token", "owner-a");
});

test("project binary resources receive capabilities before being embedded", async () => {
  const loaded = await loadProjectRevealFilesCached({
    previewKey: "private-project",
    project,
  });
  expect(loaded.binaryFiles["/asset.png"]).toContain(
    "file_token=project-capability",
  );
  expect(loaded.files["/index.html"]).toContain(
    "file_token=project-capability",
  );
});

test("project preview cache is isolated by account", async () => {
  await loadProjectRevealFilesCached({
    previewKey: "private-project",
    project,
  });
  localStorage.setItem("access_token", "owner-b");
  await loadProjectRevealFilesCached({
    previewKey: "private-project",
    project,
  });
  expect(resolveUploadFileUrl).toHaveBeenCalledTimes(2);
});

test("shared signed manifest URLs retain restored dotted filenames", async () => {
  const { parseProjectRevealSummary } = await import("../revealPreviewData");
  const summary = parseProjectRevealSummary({
    args: { project_path: "/workspace/site" },
    result: JSON.stringify({
      type: "project_reveal",
      version: 2,
      name: "shared",
      mode: "project",
      template: "vanilla",
      files: {
        "/index_html": {
          url: "/api/upload/file/revealed_projects/site/20261012_104859_8abe77e4_index.html?file_token=share",
          is_binary: false,
          size: 20,
        },
      },
    }),
    parseErrorMessage: "parse error",
  });
  expect(Object.keys(summary.parsed?.files ?? {})).toEqual(["/index.html"]);
});

test("a same-account token refresh during project loading remains valid", async () => {
  const payload = btoa(JSON.stringify({ sub: "owner" }));
  localStorage.setItem("access_token", `header.${payload}.old`);
  vi.mocked(resolveUploadFileUrl).mockImplementationOnce(async (url) => {
    localStorage.setItem("access_token", `header.${payload}.new`);
    return `${url}?file_token=refreshed-project`;
  });
  await expect(
    loadProjectRevealFilesCached({ previewKey: "refresh", project }),
  ).resolves.toMatchObject({
    binaryFiles: {
      "/asset.png": expect.stringContaining("file_token=refreshed-project"),
    },
  });
});

test.each([
  [
    "foreign entry",
    "https://evil.example/index.html",
    "/api/upload/file/revealed_projects/site/asset.png",
    "/index.html",
  ],
  [
    "non-project entry",
    "/api/upload/file/uploads/index.html",
    "/api/upload/file/revealed_projects/site/asset.png",
    "/index.html",
  ],
  [
    "other private namespace",
    "/api/upload/file/revealed_projects/site/index.html",
    "/api/upload/file/uploads/viewer-secret.png",
    "/index.html",
  ],
  [
    "another project root",
    "/api/upload/file/revealed_projects/site/index.html",
    "/api/upload/file/revealed_projects/victim/secret.png",
    "/index.html",
  ],
  [
    "missing entry",
    "/api/upload/file/revealed_projects/site/index.html",
    "/api/upload/file/revealed_projects/site/asset.png",
    "/missing.html",
  ],
  [
    "foreign signed entry with private asset",
    "https://evil.example/index.html?file_token=attacker",
    "/api/upload/file/revealed_projects/site/asset.png",
    "/index.html",
  ],
  [
    "mixed roots without entry",
    "/api/upload/file/revealed_projects/site/index.html",
    "/api/upload/file/revealed_projects/victim/secret.png",
    undefined,
  ],
] as const)(
  "project preview rejects %s before fetching or signing any resource",
  async (_label, entryUrl, assetUrl, entry) => {
    const unsafe: ManifestProjectRevealData = {
      ...project,
      entry,
      files: {
        "/index.html": { url: entryUrl, is_binary: false, size: 20 },
        "/asset.png": { url: assetUrl, is_binary: true, size: 10 },
      },
    };
    const loaded = await loadProjectRevealFilesCached({
      previewKey: "unsafe",
      project: unsafe,
    });
    expect(loaded.files).toEqual({});
    expect(loaded.binaryFiles).toEqual({});
    expect(loaded.failed.sort()).toEqual(["/asset.png", "/index.html"]);
    expect(resolveUploadFileUrl).not.toHaveBeenCalled();
    expect(fetchDocumentText).not.toHaveBeenCalled();
  },
);

test("project preview preserves a server-root entry and preauthorized companion capability", async () => {
  const authorized: ManifestProjectRevealData = {
    ...project,
    entry: "/index.html",
    files: {
      ...project.files,
      "/asset.png": {
        url: "/api/upload/file/revealed_projects/site/asset.png?file_token=share",
        is_binary: true,
        size: 10,
      },
    },
  };
  const loaded = await loadProjectRevealFilesCached({
    previewKey: "authorized",
    project: authorized,
  });
  expect(loaded.failed).toEqual([]);
  expect(loaded.binaryFiles["/asset.png"]).toContain("file_token=share");
  expect(loaded.files["/index.html"]).toContain("file_token=share");
});

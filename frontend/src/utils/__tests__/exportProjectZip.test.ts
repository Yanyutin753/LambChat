/** @vitest-environment jsdom */

import { afterEach, expect, test, vi } from "vitest";
import { exportProjectZip } from "../exportProjectZip";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("strict binary export rejects instead of downloading a partial ZIP", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      arrayBuffer: vi.fn(),
    }),
  );
  const createObjectUrl = vi.fn(() => "blob:partial");
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: createObjectUrl,
    revokeObjectURL: vi.fn(),
  });

  await expect(
    exportProjectZip(
      {},
      "files",
      { "broken.pdf": "/api/upload/file/broken" },
      { failOnBinaryError: true },
    ),
  ).rejects.toThrow("Failed to download 1 binary file: broken.pdf");
  expect(createObjectUrl).not.toHaveBeenCalled();
});

test("default export keeps the existing best-effort binary contract", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      arrayBuffer: vi.fn(),
    }),
  );
  const createObjectUrl = vi.fn(() => "blob:best-effort");
  const revokeObjectUrl = vi.fn();
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: createObjectUrl,
    revokeObjectURL: revokeObjectUrl,
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

  await expect(
    exportProjectZip({ "readme.txt": "kept" }, "project", {
      "broken.pdf": "/api/upload/file/broken",
    }),
  ).resolves.toBeUndefined();
  expect(createObjectUrl).toHaveBeenCalledOnce();
  expect(revokeObjectUrl).toHaveBeenCalledWith("blob:best-effort");
});

test("default export does not silently apply strict resource limits", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    headers: { get: () => String(30 * 1024 * 1024) },
    arrayBuffer: vi.fn().mockResolvedValue(new Uint8Array([1]).buffer),
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:legacy"),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const binaryFiles = Object.fromEntries(
    Array.from({ length: 51 }, (_, index) => [
      `file-${index}.bin`,
      `/api/upload/file/${index}`,
    ]),
  );

  await expect(
    exportProjectZip({}, "legacy", binaryFiles),
  ).resolves.toBeUndefined();
  expect(fetchMock).toHaveBeenCalledTimes(51);
});

test("preserves non-Latin letters in the downloaded ZIP name", async () => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:localized-name"),
    revokeObjectURL: vi.fn(),
  });
  let downloadedName = "";
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    downloadedName = this.download;
  });

  await exportProjectZip({}, "すべてのファイル");

  expect(downloadedName).toBe("すべてのファイル.zip");
});

test("normalizes and preserves combining marks in the downloaded ZIP name", async () => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:localized-name"),
    revokeObjectURL: vi.fn(),
  });
  let downloadedName = "";
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    downloadedName = this.download;
  });

  await exportProjectZip({}, "Cafe\u0301 हिंदी");

  expect(downloadedName).toBe("Café_हिंदी.zip");
});

test("rejects strict exports above the binary file limit before fetching", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const binaryFiles = Object.fromEntries(
    Array.from({ length: 3 }, (_, index) => [
      `file-${index}.bin`,
      `/api/upload/file/${index}`,
    ]),
  );

  await expect(
    exportProjectZip({}, "files", binaryFiles, {
      failOnBinaryError: true,
      maxBinaryFiles: 2,
    }),
  ).rejects.toThrow("Binary ZIP limit exceeded: at most 2 files");
  expect(fetchMock).not.toHaveBeenCalled();
});

test("limits binary fetch concurrency", async () => {
  let active = 0;
  let maxActive = 0;
  let started = 0;
  const releases: Array<() => void> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async () => {
      active += 1;
      started += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise<void>((resolve) => releases.push(resolve));
      active -= 1;
      return {
        ok: true,
        headers: { get: () => "1" },
        arrayBuffer: vi.fn().mockResolvedValue(new Uint8Array([1]).buffer),
      };
    }),
  );
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:limited"),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

  const exportPromise = exportProjectZip(
    {},
    "files",
    Object.fromEntries(
      Array.from({ length: 5 }, (_, index) => [
        `file-${index}.bin`,
        `/api/upload/file/${index}`,
      ]),
    ),
    { binaryConcurrency: 2 },
  );
  await vi.waitFor(() => expect(started).toBe(2));
  releases.splice(0).forEach((release) => release());
  await vi.waitFor(() => expect(started).toBe(4));
  releases.splice(0).forEach((release) => release());
  await vi.waitFor(() => expect(started).toBe(5));
  releases.splice(0).forEach((release) => release());
  await exportPromise;

  expect(maxActive).toBe(2);
});

test("rejects a strict export when downloaded bytes exceed the limit", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => "4" },
      arrayBuffer: vi.fn().mockResolvedValue(new Uint8Array(4).buffer),
    }),
  );

  await expect(
    exportProjectZip(
      {},
      "files",
      { "large.bin": "/api/upload/file/large" },
      { failOnBinaryError: true, maxBinaryBytes: 3 },
    ),
  ).rejects.toThrow("Failed to download 1 binary file: large.bin");
});

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

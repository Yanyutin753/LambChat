/** @vitest-environment jsdom */
import { expect, test, vi } from "vitest";
const mocks = vi.hoisted(() => ({ hash: vi.fn(), direct: vi.fn() }));
vi.mock("../../../utils/fileHash", () => ({ computeFileHash: mocks.hash }));
vi.mock("../directUpload", () => ({ uploadDirect: mocks.direct }));
import { uploadApi } from "../upload";

test("all upload callers reuse an owned matching object without sending bytes", async () => {
  mocks.hash.mockResolvedValue("a".repeat(64));
  const check = vi.spyOn(uploadApi, "checkFile").mockResolvedValue({
    exists: true,
    key: "video/me/a.mp4",
    url: "/api/upload/file/video/me/a.mp4",
    name: "old.mp4",
    type: "video",
    mimeType: "video/mp4",
    size: 3,
  });
  const result = await uploadApi.uploadFile(
    new File(["abc"], "renamed.mp4", { type: "video/mp4" }),
  ).promise;
  expect(result.key).toBe("video/me/a.mp4");
  expect(result.name).toBe("renamed.mp4");
  expect(mocks.direct).not.toHaveBeenCalled();
  check.mockRestore();
});

test("aborting while hashing never starts a lookup or upload", async () => {
  mocks.direct.mockClear();
  let finish!: (hash: string) => void;
  mocks.hash.mockReturnValue(
    new Promise<string>((resolve) => {
      finish = resolve;
    }),
  );
  const check = vi.spyOn(uploadApi, "checkFile");
  const handle = uploadApi.uploadFile(new File(["abc"], "cancelled.txt"));
  handle.abort();
  finish("a".repeat(64));
  await expect(handle.promise).rejects.toMatchObject({ name: "AbortError" });
  expect(check).not.toHaveBeenCalled();
  expect(mocks.direct).not.toHaveBeenCalled();
  check.mockRestore();
});

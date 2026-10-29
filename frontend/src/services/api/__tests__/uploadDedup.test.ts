/** @vitest-environment jsdom */
import { afterEach, expect, test, vi } from "vitest";
const mocks = vi.hoisted(() => ({ hash: vi.fn(), direct: vi.fn() }));
vi.mock("../../../utils/fileHash", () => ({ computeFileHash: mocks.hash }));
vi.mock("../directUpload", () => ({ uploadDirect: mocks.direct }));
import { uploadApi } from "../upload";
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  localStorage.clear();
  mocks.direct.mockClear();
});

test.each(["renamed.mp4", "scan.tiff"])(
  "%s reuses an owned matching object without sending bytes",
  async (name) => {
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
    const result = await uploadApi.uploadFile(new File(["abc"], name)).promise;
    expect(result.key).toBe("video/me/a.mp4");
    expect(result.name).toBe(name);
    expect(mocks.direct).not.toHaveBeenCalled();
    check.mockRestore();
  },
);

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

test.each(["hash", "lookup"])(
  "a stalled %s cannot indefinitely block the actual upload",
  async (phase) => {
    vi.useFakeTimers();
    const result = {
      key: "image/me/result.jpg",
      name: "scan.tiff",
      type: "image",
      mimeType: "image/jpeg",
      size: 3,
      url: "/image/me/result.jpg",
    };
    let preparationSignal: AbortSignal | undefined;
    const never = new Promise<string>(() => {});
    mocks.hash.mockImplementation((_file, signal) => {
      preparationSignal = signal;
      return phase === "hash" ? never : Promise.resolve("a".repeat(64));
    });
    const check = vi
      .spyOn(uploadApi, "checkFile")
      .mockImplementation((_hash, _size, _name, _mime, signal) => {
        preparationSignal = signal;
        return new Promise(() => {});
      });
    mocks.direct
      .mockClear()
      .mockReturnValue({ promise: Promise.resolve(result), abort: vi.fn() });
    const finished = vi.fn();
    const handle = uploadApi.uploadFile(new File(["abc"], "scan.txt"));
    const pending = handle.promise.then(finished);
    await vi.advanceTimersByTimeAsync(3000);
    expect(preparationSignal?.aborted).toBe(true);
    expect(finished).toHaveBeenCalledWith(result);
    await pending;
    expect(vi.getTimerCount()).toBe(0);
    check.mockRestore();
    vi.useRealTimers();
  },
);

test("an unavailable optional dedup endpoint does not prevent uploading", async () => {
  mocks.hash.mockResolvedValue("a".repeat(64));
  const check = vi
    .spyOn(uploadApi, "checkFile")
    .mockRejectedValue(new TypeError("Failed to fetch"));
  const result = { key: "document/me/file.txt" };
  mocks.direct.mockReturnValue({
    promise: Promise.resolve(result),
    abort: vi.fn(),
  });
  await expect(
    uploadApi.uploadFile(new File(["abc"], "file.txt")).promise,
  ).resolves.toEqual(result);
  check.mockRestore();
});

test.each([401, 403])(
  "dedup authorization failure %s must not start a fallback upload",
  async (status) => {
    mocks.hash.mockResolvedValue("a".repeat(64));
    const check = vi
      .spyOn(uploadApi, "checkFile")
      .mockRejectedValue(Object.assign(new Error("denied"), { status }));
    mocks.direct.mockClear();
    await expect(
      uploadApi.uploadFile(new File(["abc"], "file.txt")).promise,
    ).rejects.toMatchObject({ status });
    expect(mocks.direct).not.toHaveBeenCalled();
    check.mockRestore();
  },
);

test("cancellation settles immediately even if a preparation dependency does not reject", async () => {
  vi.useFakeTimers();
  mocks.hash.mockReturnValue(new Promise(() => {}));
  mocks.direct.mockClear();
  const handle = uploadApi.uploadFile(new File(["abc"], "cancelled.txt"));
  const rejected = vi.fn();
  const settled = handle.promise.catch(rejected);
  handle.abort();
  await vi.advanceTimersByTimeAsync(0);
  expect(rejected).toHaveBeenCalledWith(
    expect.objectContaining({ name: "AbortError" }),
  );
  expect(mocks.direct).not.toHaveBeenCalled();
  await settled;
});

test("a result from an upload started by the previous account is discarded", async () => {
  mocks.hash.mockRejectedValue(new Error("unsupported worker"));
  let finish!: (value: unknown) => void;
  mocks.direct.mockReturnValue({
    promise: new Promise((resolve) => {
      finish = resolve;
    }),
    abort: vi.fn(),
  });
  localStorage.setItem("access_token", "old-account");
  const handle = uploadApi.uploadFile(new File(["abc"], "file.txt"));
  await vi.waitFor(() => expect(mocks.direct).toHaveBeenCalled());
  localStorage.setItem("access_token", "new-account");
  finish({ key: "document/old-account/file.txt" });
  await expect(handle.promise).rejects.toMatchObject({ name: "AbortError" });
  localStorage.clear();
});

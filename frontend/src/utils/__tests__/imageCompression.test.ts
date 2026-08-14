/** @vitest-environment jsdom */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { compressImageFile } from "../imageCompression";

class SuccessfulCompressionWorker {
  static terminations = 0;
  onmessage:
    | ((
        event: MessageEvent<{
          ok: true;
          blob: Blob;
          mimeType: string;
          extension: string;
        }>,
      ) => void)
    | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;

  postMessage() {
    queueMicrotask(() => {
      this.onmessage?.({
        data: {
          ok: true,
          blob: new Blob([new Uint8Array(64)], { type: "image/jpeg" }),
          mimeType: "image/jpeg",
          extension: ".jpg",
        },
      } as MessageEvent<{
        ok: true;
        blob: Blob;
        mimeType: string;
        extension: string;
      }>);
    });
  }

  terminate() {
    SuccessfulCompressionWorker.terminations += 1;
  }
}

class UnsupportedCompressionWorker {
  onmessage:
    | ((
        event: MessageEvent<{
          ok: false;
          code: "unsupported";
          message: string;
        }>,
      ) => void)
    | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;

  postMessage() {
    queueMicrotask(() => {
      this.onmessage?.({
        data: {
          ok: false,
          code: "unsupported",
          message: "unsupported",
        },
      } as MessageEvent<{
        ok: false;
        code: "unsupported";
        message: string;
      }>);
    });
  }

  terminate() {}
}

class PendingCompressionWorker {
  static terminations = 0;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;

  postMessage() {}

  terminate() {
    PendingCompressionWorker.terminations += 1;
  }
}

beforeEach(() => {
  SuccessfulCompressionWorker.terminations = 0;
  vi.stubGlobal("Worker", SuccessfulCompressionWorker);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("compresses supported images in a worker without creating a DOM canvas", async () => {
  const createElement = vi.spyOn(document, "createElement");
  const input = new File([new Uint8Array(300 * 1024)], "photo.webp", {
    type: "image/webp",
  });

  const output = await compressImageFile(input);

  expect(output.name).toBe("photo.jpg");
  expect(output.type).toBe("image/jpeg");
  expect(output.size).toBe(64);
  expect(SuccessfulCompressionWorker.terminations).toBe(1);
  expect(createElement).not.toHaveBeenCalledWith("canvas");
});

test("returns the original image when worker compression is unsupported", async () => {
  vi.stubGlobal("Worker", UnsupportedCompressionWorker);
  const input = new File([new Uint8Array(300 * 1024)], "photo.png", {
    type: "image/png",
  });

  await expect(
    compressImageFile(input, { fallback: "original" }),
  ).resolves.toBe(input);
});

test("uses the main-thread fallback only when explicitly requested", async () => {
  vi.stubGlobal("Worker", UnsupportedCompressionWorker);
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(async () => ({ width: 100, height: 100, close: vi.fn() })),
  );
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ({ drawImage: vi.fn() }),
    toBlob: (callback: BlobCallback) =>
      callback(new Blob([new Uint8Array(64)], { type: "image/jpeg" })),
  } as unknown as HTMLCanvasElement;
  vi.spyOn(document, "createElement").mockReturnValue(canvas);
  const input = new File([new Uint8Array(300 * 1024)], "photo.jpg", {
    type: "image/jpeg",
  });

  const output = await compressImageFile(input, { fallback: "main-thread" });

  expect(output.size).toBe(64);
  expect(createImageBitmap).toHaveBeenCalledWith(input);
});

test("aborting compression terminates the worker and rejects with AbortError", async () => {
  PendingCompressionWorker.terminations = 0;
  vi.stubGlobal("Worker", PendingCompressionWorker);
  const controller = new AbortController();
  const input = new File([new Uint8Array(300 * 1024)], "photo.jpg", {
    type: "image/jpeg",
  });

  const compression = compressImageFile(input, { signal: controller.signal });
  controller.abort();

  await expect(
    Promise.race([
      compression,
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("compression did not abort")), 20),
      ),
    ]),
  ).rejects.toMatchObject({ name: "AbortError" });
  expect(PendingCompressionWorker.terminations).toBe(1);
});

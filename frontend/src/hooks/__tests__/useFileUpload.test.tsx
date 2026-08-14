/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MessageAttachment } from "../../types";
import i18n from "../../i18n";
import { useFileUpload } from "../useFileUpload";

const apiMocks = vi.hoisted(() => ({
  getConfig: vi.fn(async () => ({
    uploadLimits: {
      image: 10,
      video: 10,
      audio: 10,
      document: 10,
      maxFiles: 10,
    },
  })),
  checkFile: vi.fn(
    async (_hash: string, size: number, name: string, mimeType: string) => ({
      exists: true,
      key: `documents/test/${name}`,
      url: `/api/upload/file/documents/test/${name}`,
      name,
      type: mimeType.startsWith("image/") ? "image" : "document",
      mimeType,
      size,
    }),
  ),
  uploadFile: vi.fn(),
}));

const toastMocks = vi.hoisted(() => ({ error: vi.fn() }));

vi.mock("../../services/api", () => ({
  uploadApi: apiMocks,
}));

vi.mock("react-hot-toast", () => ({
  default: toastMocks,
}));

class HashWorker {
  static starts = 0;
  onmessage: ((event: MessageEvent<{ hash: string }>) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;

  constructor() {
    HashWorker.starts += 1;
  }

  postMessage() {
    queueMicrotask(
      () =>
        this.onmessage?.({ data: { hash: "a".repeat(64) } } as MessageEvent<{
          hash: string;
        }>),
    );
  }

  terminate() {}
}

function useUploadHarness() {
  const [attachments, setAttachments] = useState<MessageAttachment[]>([]);
  const upload = useFileUpload({
    attachments,
    onAttachmentsChange: setAttachments,
  });
  return { ...upload, attachments };
}

beforeEach(async () => {
  vi.clearAllMocks();
  HashWorker.starts = 0;
  vi.stubGlobal("Worker", HashWorker);
  await i18n.changeLanguage("en");
});

test("zero-byte files never enter attachment state or hashing", async () => {
  const { result } = renderHook(() => useUploadHarness());

  act(() => result.current.uploadFile(new File([], "bpm_r5.bin")));

  await waitFor(() =>
    expect(toastMocks.error).toHaveBeenCalledWith(
      "This file is empty and cannot be uploaded.",
    ),
  );
  expect(result.current.attachments).toEqual([]);
  expect(HashWorker.starts).toBe(0);
  expect(apiMocks.checkFile).not.toHaveBeenCalled();
  expect(apiMocks.uploadFile).not.toHaveBeenCalled();
});

test("mixed batches skip empty files and keep uploading valid files", async () => {
  const { result } = renderHook(() => useUploadHarness());
  const empty = new File([], "stale.bin");
  const valid = new File(["valid contents"], "notes.txt", {
    type: "text/plain",
  });

  act(() => result.current.uploadFiles([empty, valid]));

  await waitFor(() =>
    expect(result.current.attachments).toEqual([
      expect.objectContaining({
        name: "notes.txt",
        size: valid.size,
        mimeType: "text/plain",
      }),
    ]),
  );
  expect(toastMocks.error).toHaveBeenCalledWith(
    "This file is empty and cannot be uploaded.",
  );
  expect(HashWorker.starts).toBe(1);
  expect(apiMocks.checkFile).toHaveBeenCalledOnce();
});

test("file-count validation ignores empty files in a mixed batch", async () => {
  apiMocks.getConfig.mockResolvedValueOnce({
    uploadLimits: {
      image: 10,
      video: 10,
      audio: 10,
      document: 10,
      maxFiles: 1,
    },
  });
  const { result } = renderHook(() => useUploadHarness());
  const empty = new File([], "stale.bin");
  const valid = new File(["valid contents"], "only-valid-file.txt", {
    type: "text/plain",
  });

  await waitFor(() => expect(result.current.uploadLimits?.maxFiles).toBe(1));
  act(() => result.current.uploadFiles([empty, valid]));

  await waitFor(() =>
    expect(result.current.attachments).toEqual([
      expect.objectContaining({
        name: "only-valid-file.txt",
        size: valid.size,
        mimeType: "text/plain",
      }),
    ]),
  );
  expect(toastMocks.error).toHaveBeenCalledTimes(1);
  expect(toastMocks.error).toHaveBeenCalledWith(
    "This file is empty and cannot be uploaded.",
  );
  expect(HashWorker.starts).toBe(1);
  expect(apiMocks.checkFile).toHaveBeenCalledOnce();
});

test("moves an upload from preparing through throttled uploading and server processing", async () => {
  apiMocks.checkFile.mockResolvedValueOnce({ exists: false } as never);
  let resolveUpload!: (value: {
    key: string;
    url: string;
    name: string;
    type: "document";
    mimeType: string;
    size: number;
  }) => void;
  const uploadPromise = new Promise<{
    key: string;
    url: string;
    name: string;
    type: "document";
    mimeType: string;
    size: number;
  }>((resolve) => {
    resolveUpload = resolve;
  });
  apiMocks.uploadFile.mockReturnValueOnce({
    promise: uploadPromise,
    abort: vi.fn(),
  });
  const { result } = renderHook(() => useUploadHarness());
  const file = new File(["upload body"], "notes.txt", {
    type: "text/plain",
  });

  act(() => result.current.uploadFile(file));

  expect(result.current.attachments[0]).toMatchObject({
    name: "notes.txt",
    isUploading: true,
    uploadProgress: 0,
    uploadStage: "preparing",
  });
  await waitFor(() => expect(apiMocks.uploadFile).toHaveBeenCalledOnce());
  const options = apiMocks.uploadFile.mock.calls[0]?.[1] as {
    onProgress?: (progress: number) => void;
  };

  act(() => options.onProgress?.(35));
  expect(result.current.attachments[0]).toMatchObject({
    uploadProgress: 35,
    uploadStage: "uploading",
  });

  act(() => options.onProgress?.(100));
  expect(result.current.attachments[0]).toMatchObject({
    uploadProgress: 99,
    uploadStage: "processing",
  });

  act(() =>
    resolveUpload({
      key: "documents/test/notes.txt",
      url: "/api/upload/file/documents/test/notes.txt",
      name: "notes.txt",
      type: "document",
      mimeType: "text/plain",
      size: file.size,
    }),
  );
  await waitFor(() =>
    expect(result.current.attachments[0]).toEqual(
      expect.objectContaining({ key: "documents/test/notes.txt" }),
    ),
  );
  expect(result.current.attachments[0]).not.toHaveProperty("isUploading");
  expect(result.current.attachments[0]).not.toHaveProperty("uploadProgress");
  expect(result.current.attachments[0]).not.toHaveProperty("uploadStage");
});

test("shows preparing immediately and terminates image work when cancelled", async () => {
  class PendingImageWorker {
    static terminations = 0;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onerror: ((event: ErrorEvent) => void) | null = null;
    postMessage() {}
    terminate() {
      PendingImageWorker.terminations += 1;
    }
  }
  vi.stubGlobal("Worker", PendingImageWorker);
  const { result } = renderHook(() => useUploadHarness());
  const file = new File([new Uint8Array(300 * 1024)], "capture.png", {
    type: "image/png",
  });

  act(() => result.current.uploadFile(file));

  expect(result.current.attachments[0]).toMatchObject({
    name: "capture.png",
    uploadStage: "preparing",
  });
  const tempId = result.current.attachments[0].id;
  act(() => result.current.cancelUpload(tempId));

  expect(result.current.attachments).toEqual([]);
  expect(PendingImageWorker.terminations).toBe(1);
  expect(apiMocks.uploadFile).not.toHaveBeenCalled();
});
